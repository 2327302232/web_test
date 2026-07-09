import time
import gc

from machine import Pin, SoftI2C

from detect_collision.mpu6050 import MPU6050
from detect_collision.preprocessor import DataPreprocessor
from detect_collision.FeatureExtractor import FeatureExtractor
from detect_collision.DecisionEngine import DecisionEngine
from detect_collision.config import Config


class EventDetector:
    """
    碰撞/跌倒事件检测器（入口）

    完整流水线：
    MPU6050(原始加速度/角速度)
        → preprocessor.py(低通滤波、互补滤波姿态解算、去重力)
        → FeatureExtractor.py(提取峰值/jerk/脉宽/方向/相关性等特征)
        → DecisionEngine.py(五层决策树：冲击筛选→主动/被动区分→跌倒检测→报警级别→冷却抑制)
        → _stabilize_event(连续N帧防抖确认)
        → 返回 {"event":"collision"} 或 {"event":"fall"}
    """

    def __init__(self, config=None):
        self.cfg = config or Config()

        # ── 采样/算法频率解耦 ──
        # sensor_rate_hz: MPU6050每秒钟读多少次
        # algo_rate_hz:   算法每秒钟跑多少次（可以比采样率低，省CPU）
        self.sensor_rate_hz = int(getattr(self.cfg, "SAMPLE_RATE", 100))
        self.algo_rate_hz = 20

        if self.sensor_rate_hz <= 0:
            self.sensor_rate_hz = 100
        if self.algo_rate_hz <= 0:
            self.algo_rate_hz = 20
        if self.algo_rate_hz > self.sensor_rate_hz:
            self.algo_rate_hz = self.sensor_rate_hz

        self.sample_interval_ms = max(1, int(1000 / self.sensor_rate_hz))
        self.algo_div = max(1, int(self.sensor_rate_hz / self.algo_rate_hz))  # 每读algo_div次传感器，跑一次算法

        # ── 上电预热 ──
        # 刚上电时MPU6050数据不稳定，预热期间不输出检测结果
        self.warmup_seconds = int(getattr(self.cfg, "WARMUP_SECONDS", 8))
        if self.warmup_seconds < 0:
            self.warmup_seconds = 0
        self.warmup_ms = self.warmup_seconds * 1000

        # ── 流水线各模块实例（懒初始化） ──
        self.imu = None             # MPU6050 I2C驱动
        self.processor = None       # 预处理：低通滤波 + 互补滤波姿态解算 + 去重力
        self.extractor = None       # 特征提取：从预处理数据中计算各种特征
        self.decision_engine = None # 决策引擎：根据特征分类事件类型
        self._runtime_inited = False

        self.next_tick = time.ticks_ms()  # 下次采样时间戳（用于非阻塞轮询）
        self.start_ms = 0                  # 检测开始时间（用于预热判断）
        self.sensor_ticks = 0              # 累计采样次数

        self._alert_streak = 0  # 连续触发告警的帧数计数器，≥CONSEC_FRAMES才算真事件（防抖）

        gc.enable()

    def _init_sensor(self):
        """初始化MPU6050传感器(SoftI2C: PF14-SDA, PE11-SCL),然后校准零偏"""
        i2c = SoftI2C(sda=Pin("PF14"), scl=Pin("PE11"), freq=400000)
        self.imu = MPU6050(i2c)
        time.sleep(0.2)
        self.imu.calibrate(samples=100)

    def _init_algorithm(self):
        """初始化预处理→特征提取→决策引擎三级流水线"""
        self.processor = DataPreprocessor(self.cfg)
        self.extractor = FeatureExtractor(self.cfg)
        self.decision_engine = DecisionEngine(self.cfg)

    def _init_runtime_if_needed(self):
        """懒初始化：第一次检测时初始化传感器和算法（异常时标记不可用）"""
        if self._runtime_inited:
            return
        try:
            self._init_sensor()
            gc.collect()
            self._init_algorithm()
            self._runtime_inited = True
        except Exception:
            self._runtime_inited = False

    def is_ready(self):
        """传感器和算法是否初始化成功"""
        return self._runtime_inited

    def _stabilize_event(self, evt, sev, conf, alert):
        """
        防抖:单次检测可能误报,要求连续N帧都触发才真正报警
        evt: 事件类型 (5=前碰,6=侧碰,7=后碰,8=摔,9=严重摔)
        sev: 严重度 0-10
        conf: 置信度 0-1
        alert: 报警级别 (0=无,1=信息,2=警告,3=紧急,4=SOS)
        """
        alert_min_sev = float(getattr(self.cfg, "ALERT_MIN_SEV", 4.2))
        alert_min_conf = float(getattr(self.cfg, "ALERT_MIN_CONF", 0.65))
        alert_consec_frames = int(getattr(self.cfg, "ALERT_CONSEC_FRAMES", 2))

        # 碰撞/跌倒(5,6,7)严重度或置信度不够 → 降为无事件
        if evt in (5, 6, 7) and (sev < alert_min_sev or conf < alert_min_conf):
            evt, sev, conf, alert = 0, 0.0, 0.0, 0

        if evt > 0 and sev >= alert_min_sev and conf >= alert_min_conf:
            self._alert_streak += 1
            if self._alert_streak < alert_consec_frames:
                alert = 0  # 连续帧数不够，暂时不报警
            else:
                alert = max(1, int(alert))
        else:
            self._alert_streak = 0
            alert = 0

        return int(evt), float(sev), float(conf), int(alert)

    def _format_event_only(self, evt):
        """将决策引擎的事件类型ID映射为外部统一格式"""
        collision_types = (
            self.decision_engine.EVENT_COLLISION_FRONT,
            self.decision_engine.EVENT_COLLISION_SIDE,
            self.decision_engine.EVENT_COLLISION_REAR,
        )
        fall_types = (
            self.decision_engine.EVENT_FALL,
            self.decision_engine.EVENT_SEVERE_FALL,
        )

        if evt in collision_types:
            return {"event": "collision"}
        if evt in fall_types:
            return {"event": "fall"}
        return None

    def _build_event_only(self, accel, gyro, now_ms):
        """
        执行一轮完整检测流水线：
        预处理 → 特征提取 → 决策引擎 → 防抖 → 格式化输出
        """
        processed = self.processor.preprocess_data(accel, gyro)
        if not processed:
            return None

        self.extractor.update_buffer(processed)
        features = self.extractor.calculate_features()
        if features is None:
            return None

        result = self.decision_engine.process(features, processed)
        if result is None:
            return None

        # 预热期间不输出检测结果
        in_warmup = time.ticks_diff(now_ms, self.start_ms) < self.warmup_ms
        if in_warmup:
            return None

        evt = int(result.get("type", 0))
        sev = float(result.get("severity", 0.0))
        conf = float(result.get("confidence", 0.0))
        alert = int(result.get("alert_level", 0))

        evt, sev, conf, alert = self._stabilize_event(evt, sev, conf, alert)
        return self._format_event_only(evt)

    def check_once(self):
        """
        非阻塞轮询，主循环里每帧调一次
        没事返回None,有事件返回{"event": "collision"}或{"event": "fall"}

        时序控制:按sample_interval_ms间隔采样,每algo_div次采样跑一次算法
        """
        if not self._runtime_inited or not self.imu:
            return None
        now = time.ticks_ms()
        if time.ticks_diff(now, self.next_tick) < 0:
            return None
        self.next_tick = time.ticks_add(self.next_tick, self.sample_interval_ms)
        self.sensor_ticks += 1
        try:
            accel, gyro, _ = self.imu.get_data(calibrated=True)
            if (self.sensor_ticks % self.algo_div) == 0:
                return self._build_event_only(accel, gyro, now)
        except Exception:
            pass
        return None

    def wait_for_event(self):
        """
        阻塞等待，直到检测到碰撞/跌倒才返回
        用于event_monitor_thread（独立线程），效率比check_once高
        """
        self._init_runtime_if_needed()

        self.next_tick = time.ticks_ms()
        self.start_ms = self.next_tick
        self.sensor_ticks = 0

        try:
            while True:
                now = time.ticks_ms()

                if time.ticks_diff(now, self.next_tick) >= 0:
                    self.next_tick = time.ticks_add(self.next_tick, self.sample_interval_ms)
                    self.sensor_ticks += 1

                    try:
                        accel, gyro, _ = self.imu.get_data(calibrated=True)

                        if (self.sensor_ticks % self.algo_div) == 0:
                            event_info = self._build_event_only(accel, gyro, now)
                            if event_info:
                                return event_info
                    except Exception:
                        pass

                time.sleep_ms(2)

        except KeyboardInterrupt:
            return None

    def iter_events(self):
        """
        生成器：持续产生检测到的事件(yield)
        用于event_monitor_thread(voice_service.py)，一个线程不断监听碰撞
        """
        self._init_runtime_if_needed()
        if not self._runtime_inited:
            return

        self.next_tick = time.ticks_ms()
        self.start_ms = self.next_tick
        self.sensor_ticks = 0

        while True:
            now = time.ticks_ms()

            if time.ticks_diff(now, self.next_tick) >= 0:
                self.next_tick = time.ticks_add(self.next_tick, self.sample_interval_ms)
                self.sensor_ticks += 1

                try:
                    accel, gyro, _ = self.imu.get_data(calibrated=True)

                    if (self.sensor_ticks % self.algo_div) == 0:
                        event_info = self._build_event_only(accel, gyro, now)
                        if event_info:
                            yield event_info
                except Exception:
                    pass

            time.sleep_ms(2)