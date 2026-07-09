import time

from detect_collision.detector import EventDetector
from sensor.heart_rate import TaiyangStepper
from sensor.battery import get_battery_soc
try:
    from sensor.gnss import get_cached_location, refresh_location
except Exception:
    from sensor.gnss import get_basic_location as get_cached_location
    def refresh_location():
        return None
try:
    from sensor.lbs import lbs_module, get_cached_location as get_lbs_location
except Exception:
    lbs_module = None
    get_lbs_location = None

try:
    import qwiic_i2c
    from ahtx0 import AHT20
except Exception:
    qwiic_i2c = None
    AHT20 = None


class DataPackager:
    def __init__(
        self,
        heart_ms=20000,
        gnss_timeout=30,
        i2c_id=1,
        i2c_freq=400000,
        gnss_refresh_ms=1000,
    ):
        # 事件检测：碰撞/跌倒
        self.event_detector = EventDetector()
        # 心率测量时长与GNSS超时
        self.heart_ms = int(heart_ms)
        self.gnss_timeout = int(gnss_timeout)
        self._heart_window_ms = 8000
        self._heart_emit_ms = 3000
        self._heart_stepper = TaiyangStepper(self._heart_emit_ms)
        self._last_heart_rate = 0
        self._stop = False
        self._gnss_refresh_ms = int(gnss_refresh_ms)
        self._last_location = None

        # GNSS位置源管理
        self._gnss_initialized = False
        self._last_gnss_check_ms = 0
        self._gnss_check_interval_ms = 30000
        self._lbs_requested = False

        # 温湿度传感器
        self._env_sensor = None
        if qwiic_i2c and AHT20:
            try:
                qwiic = qwiic_i2c.get_i2c_driver(freq=i2c_freq)
                i2c = qwiic.i2cbus
                self._env_sensor = AHT20(i2c)
            except Exception:
                self._env_sensor = None

    def get_realtime_payload(self):
        # 实时数据打包：心率/位置/温湿度
        try:
            self.update()
        except Exception:
            pass

        env = None
        if self._env_sensor:
            try:
                env = {
                    "temperature_c": round(float(self._env_sensor.temperature), 2),
                    "humidity": round(float(self._env_sensor.relative_humidity), 2),
                }
            except Exception:
                env = None

        now = time.ticks_ms()
        try:
            loc = get_cached_location(0)
        except Exception:
            loc = None
        if loc and loc.get("latitude") is not None:
            self._last_location = loc
        elif get_lbs_location:
            lbs_loc = get_lbs_location()
            if lbs_loc and lbs_loc.get("latitude") is not None:
                self._last_location = lbs_loc
            elif loc is not None:
                self._last_location = loc
        else:
            self._last_location = loc
        # 电量读取失败时返回None，不阻塞
        try:
            bat_soc = get_battery_soc()
        except Exception:
            bat_soc = None
        return {
            "ts_ms": now,
            "heart_rate": self._last_heart_rate,
            "location": self._last_location,
            "env": env,
            "battery_soc": bat_soc,
        }

    def manage_location_source(self):
        """
        管理GNSS/LBS位置源:
          - 首次调用:立即检查GNSS,无数据则启动LBS(只有一次）
          - 后续每30秒检查GNSS是否恢复
          - GNSS恢复后清除LBS缓存,重置lbs_requested标记
        """
        now = time.ticks_ms()
        if self._gnss_initialized:
            elapsed = time.ticks_diff(now, self._last_gnss_check_ms)
            if elapsed < self._gnss_check_interval_ms:
                return

        self._last_gnss_check_ms = now
        self._gnss_initialized = True

        try:
            loc = refresh_location()
        except Exception:
            loc = None
        has_gnss = loc and loc.get("latitude") is not None
        if has_gnss:
            if lbs_module:
                lbs_module.clear()
            self._lbs_requested = False
        elif lbs_module and not self._lbs_requested and not lbs_module.is_busy:
            self._lbs_requested = True
            lbs_module.request_location()

    def update(self):
        # 高频心率采样（主线程调用，避免多线程 I2C 冲突）
        if self._heart_stepper and self._heart_stepper.ok():
            bpm = self._heart_stepper.step()
            if bpm is not None:
                self._last_heart_rate = bpm

    def wait_for_event_payload(self):
        # 只在碰撞/跌倒发生时返回事件包
        evt = self.event_detector.wait_for_event()
        if not evt:
            return None
        return {
            "ts_ms": time.ticks_ms(),
            "event": evt.get("event"),
        }

    def poll_event_payload(self):
        # 非阻塞轮询事件
        if not hasattr(self.event_detector, "poll_event"):
            return None
        evt = self.event_detector.poll_event()
        if not evt:
            return None
        return {
            "ts_ms": time.ticks_ms(),
            "event": evt.get("event"),
        }

    def stop(self):
        # 终止后台线程
        self._stop = True

    def power_down_sensors(self):
        """低功耗模式：关闭心率传感器和温湿度传感器的I2C通信，节省电力"""
        # 关闭心率传感器 MAX3010x
        if self._heart_stepper and self._heart_stepper.ok():
            try:
                monitor = self._heart_stepper.monitor
                if monitor.sensor:
                    monitor.sensor.softReset()
                    # 设置LED电流为0，关闭光发射
                    monitor.sensor.setPulseAmplitudeIR(0)
                    monitor.sensor.setPulseAmplitudeRed(0)
                    monitor.sensor.shutDown()
            except Exception:
                pass
            self._heart_stepper._ok = False
        # 关闭温湿度传感器 AHT20
        if self._env_sensor:
            try:
                self._env_sensor = None  # 释放I2C对象
            except Exception:
                pass
        # 关闭电池I2C
        from sensor.battery import _battery
        if _battery and _battery._i2c:
            try:
                _battery._ok = False
            except Exception:
                pass

    def power_up_sensors(self):
        """退出低功耗模式：重新初始化心率传感器和温湿度传感器"""
        # 重新初始化心率传感器
        try:
            self._heart_stepper = TaiyangStepper(self._heart_emit_ms)
        except Exception:
            pass
        # 重新初始化温湿度传感器
        if qwiic_i2c and AHT20:
            try:
                qwiic = qwiic_i2c.get_i2c_driver(freq=400000)
                i2c = qwiic.i2cbus
                self._env_sensor = AHT20(i2c)
            except Exception:
                self._env_sensor = None
        # 重新启用电池读取
        from sensor.battery import _battery
        if _battery:
            try:
                _battery._init_sensor()
                _battery._fail_count = 0
            except Exception:
                pass
