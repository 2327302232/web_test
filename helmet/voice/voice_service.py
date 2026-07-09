import _thread
import time
import ubinascii

from at_port import at_lock

try:
    from sensor.data_packager import DataPackager
except Exception:
    DataPackager = None

from voice.voice_tts import VoiceSystem
from voice.voice_asr import VoiceASR

class SystemState:
    """系统状态管理：唤醒/休眠、碰撞状态、多线程锁"""

    def __init__(self):
        # 唤醒相关
        self.awake = False              # 当前是否处于唤醒状态
        self.last_command_time = 0      # 上次收到语音指令的时间，用来算超时
        self.command_count = 0
        self.awake_timeout = 8          # 唤醒后多久没操作就自动休眠（秒）
        self.command_cooldown = 1.5     # 两次指令最短间隔，防抖

        # 碰撞相关
        self.collision_detected = False # 是否检测到碰撞
        self.collision_count = 0
        self.alert_playing = False      # 碰撞警报是否在播放

        # 碰撞报警线程
        self.alert_thread_id = None
        self.alert_thread_active = False

        # 锁：碰撞状态和语音播报各一把，避免多线程同时改
        self.collision_lock = _thread.allocate_lock()
        self.voice_lock = _thread.allocate_lock()

    def wake_up(self):
        """唤醒系统，如果有报警线程在跑就先停掉"""
        with self.collision_lock:
            if not self.awake:
                self.awake = True
                self.last_command_time = time.time()
                self.command_count = 0

                if self.alert_thread_active:
                    self.stop_alert_thread()
                return True
        return False

    def sleep(self):
        """休眠，碰撞报警中不允许休眠"""
        with self.collision_lock:
            if self.awake and not self.collision_detected:
                self.awake = False
                self.last_command_time = 0
                self.command_count = 0

                if self.alert_thread_active:
                    self.stop_alert_thread()

                return True
        return False

    def stop_alert_thread(self):
        if self.alert_thread_active:
            self.alert_thread_active = False
            self.collision_detected = False
            self.alert_playing = False

    def process_command(self):
        """处理一条指令前的检查：冷却时间、超时休眠"""
        with self.collision_lock:
            current_time = time.time()

            # 太快来不及处理，忽略
            if current_time - self.last_command_time < self.command_cooldown:
                return False

            # 唤醒状态下超时了就自动休眠
            if self.awake and current_time - self.last_command_time > self.awake_timeout:
                self.sleep()
                return False

            self.last_command_time = current_time
            self.command_count += 1
            return True

    def is_awake(self):
        """检查是否处于唤醒态，顺便处理超时自动休眠"""
        with self.collision_lock:
            if not self.awake:
                return False

            if time.time() - self.last_command_time > self.awake_timeout:
                if not self.collision_detected:
                    self.sleep()
                return False

            return self.awake

    def trigger_collision(self):
        """触发碰撞报警,返回True表示是新触发"""
        with self.collision_lock:
            if not self.collision_detected:
                self.collision_detected = True
                self.collision_count += 1
                self.alert_playing = True
                return True
        return False

    def get_collision_status(self):
        with self.collision_lock:
            return self.collision_detected, self.alert_playing


def collision_alert_thread(thread_id, system_state, voice_sys):
    """碰撞报警线程:每隔alert_interval秒播报一次,每3次加一声提示音"""
    alert_count = 0
    last_alert_time = 0
    alert_interval = 2.0  # 两次播报间隔（秒）

    try:
        while system_state.alert_thread_active:
            collision_detected, alert_playing = system_state.get_collision_status()

            if collision_detected and alert_playing:
                current_time = time.time()

                if current_time - last_alert_time >= alert_interval:
                    alert_count += 1
                    last_alert_time = current_time

                    if alert_count % 3 == 1:
                        voice_sys.collision_alert_tone()
                else:
                    time.sleep(0.1)
            else:
                time.sleep(0.2)
    except Exception:
        pass


class SensorSystem:
    """封装DataPackager,给CommandProcessor提供各个传感器的简短接口,带2秒缓存"""

    def __init__(self, packager):
        self.packager = packager
        self.last_payload = None
        self.last_payload_ms = 0
        self.cache_ms = 2000  # 缓存有效期，避免短时间内重复读传感器

    def _refresh_payload(self):
        self.last_payload = self.packager.get_realtime_payload()
        self.last_payload_ms = time.ticks_ms()
        return self.last_payload

    def _get_payload(self):
        if self.last_payload is None:
            return self._refresh_payload()

        if time.ticks_diff(time.ticks_ms(), self.last_payload_ms) > self.cache_ms:
            self.last_payload = None
            at_lock.try_gc()
            return self._refresh_payload()

        return self.last_payload

    def get_heart_rate(self):
        payload = self._get_payload()
        return payload.get("heart_rate", 0)

    def get_temperature(self):
        payload = self._get_payload()
        env = payload.get("env") or {}
        return env.get("temperature_c", 0.0)

    def get_humidity(self):
        payload = self._get_payload()
        env = payload.get("env") or {}
        return env.get("humidity", 0.0)

    def get_battery(self):
        from sensor.battery import get_battery_soc
        return get_battery_soc()

    def get_location(self):
        payload = self._get_payload()
        loc = payload.get("location")
        if not loc:
            return "位置不可用"
        return "经度{}，纬度{}，海拔{}米".format(
            loc.get("longitude"),
            loc.get("latitude"),
            loc.get("altitude"),
        )

    def get_speed(self):
        payload = self._get_payload()
        loc = payload.get("location")
        if not loc:
            return "速度不可用"
        speed = loc.get("speed_kmh")
        if speed is None:
            return "速度不可用"
        return "当前速度{}公里每小时".format(speed)


def event_monitor_thread(system_state, cmd_processor, packager, on_collision=None):
    """后台线程：持续监听碰撞/跌倒事件，触发后启动语音报警"""
    for evt in packager.event_detector.iter_events():
        if evt and evt.get("event") in ("collision", "fall"):
            if system_state.trigger_collision():
                if on_collision:
                    try:
                        on_collision(evt)
                    except Exception:
                        pass
                cmd_processor.start_collision_alert()


class CommandProcessor:
    """语音指令处理器:根据ASR发来的字节码查表执行对应动作"""

    def __init__(self, voice_sys, sensor_sys, system_state, low_power_callback=None, normal_mode_callback=None, light_on_callback=None, light_off_callback=None):
        self.voice = voice_sys
        self.sensor = sensor_sys
        self.state = system_state
        self.low_power_callback = low_power_callback
        self.normal_mode_callback = normal_mode_callback
        self.light_on_callback = light_on_callback
        self.light_off_callback = light_off_callback
        self._low_power_mode = False

        self.command_map = {
            b"\x01": {
                "name": "唤醒指令",
                "action": self._handle_wakeup,
                "requires_awake": False,
                "allow_in_low_power": True,
                "description": "唤醒系统",
            },
            b"\x02": {
                "name": "心率查询",
                "action": self._handle_heart_rate,
                "requires_awake": True,
                "description": "查询心率",
            },
            b"\x03": {
                "name": "温度查询",
                "action": self._handle_temperature,
                "requires_awake": True,
                "description": "查询温度",
            },
            b"\x04": {
                "name": "湿度查询",
                "action": self._handle_humidity,
                "requires_awake": True,
                "description": "查询湿度",
            },
            b"\x05": {
                "name": "电量查询",
                "action": self._handle_battery,
                "requires_awake": True,
                "description": "查询电量",
            },
            b"\x06": {
                "name": "位置查询",
                "action": self._handle_location,
                "requires_awake": True,
                "description": "查询位置",
            },
            b"\x07": {
                "name": "全部查询",
                "action": self._handle_all,
                "requires_awake": True,
                "description": "查询全部数据",
            },
            b"\x08": {
                "name": "低功耗模式",
                "action": self._handle_low_power,
                "requires_awake": False,
                "allow_in_low_power": True,
                "description": "进入低功耗模式",
            },
            b"\x09": {
                "name": "正常模式",
                "action": self._handle_enter_normal,
                "requires_awake": False,
                "allow_in_low_power": True,
                "description": "进入正常模式",
            },
            b"\x10": {
                "name": "开灯",
                "action": self._handle_light_on,
                "requires_awake": True,
                "description": "开灯",
            },
            b"\x11": {
                "name": "关灯",
                "action": self._handle_light_off,
                "requires_awake": True,
                "description": "关灯",
            },
            b"\x12": {
                "name": "速度查询",
                "action": self._handle_speed,
                "requires_awake": True,
                "description": "查询当前速度",
            },
        }

    def _handle_wakeup(self):
        if self.state.wake_up():
            self.voice.wakeup_tone()
            self.voice.speak("我在呢", wait_for_complete=False)
            self.state.last_command_time = time.time()
        return True

    def _handle_heart_rate(self):
        hr = self.sensor.get_heart_rate()
        if hr < 50:
            status = "心率偏低"
        elif hr <= 110:
            status = "心率正常"
        else:
            status = "注意心率偏高"
        self.voice.speak("心率{}，{}".format(hr, status), wait_for_complete=True)
        return True

    def _handle_temperature(self):
        temp = self.sensor.get_temperature()
        if temp < 10:
            status = "温度较低，注意保暖"
        elif temp <= 30:
            status = "温度舒适"
        elif temp <= 35:
            status = "注意防晒"
        else:
            status = "高温警告，注意防暑"
        self.voice.speak("温度{}度，{}".format(temp, status), wait_for_complete=True)
        return True

    def _handle_humidity(self):
        humidity = self.sensor.get_humidity()
        if humidity < 30:
            status = "湿度过低，注意保湿"
        elif humidity <= 70:
            status = "湿度舒适"
        else:
            status = "湿度过高，注意通风"
        self.voice.speak("湿度{}%，{}".format(humidity, status), wait_for_complete=True)
        return True

    def _handle_battery(self):
        from sensor.battery import get_battery_soc
        soc = get_battery_soc()
        if soc is not None:
            self.voice.speak("电量{}%".format(soc), wait_for_complete=True)
        else:
            self.voice.speak("电量信息不可用", wait_for_complete=True)
        return True

    def _handle_location(self):
        location = self.sensor.get_location()
        self.voice.speak(location, wait_for_complete=True)
        return True

    def _handle_speed(self):
        speed_text = self.sensor.get_speed()
        self.voice.speak(speed_text, wait_for_complete=True)
        return True

    def _handle_all(self):
        hr = self.sensor.get_heart_rate()
        temp = self.sensor.get_temperature()
        humidity = self.sensor.get_humidity()
        battery = self.sensor.get_battery()
        location = self.sensor.get_location()
        speed = self.sensor.get_speed()
        battery_str = "电量{}%".format(battery) if battery is not None else "电量不可用"
        self.voice.speak(
            "心率{}，温度{}度，湿度{}%，{}，{}，{}".format(hr, temp, humidity, battery_str, location, speed),
            wait_for_complete=True,
        )
        return True

    def _handle_low_power(self):
        self._low_power_mode = True
        self.voice.speak("已进入低功耗模式", wait_for_complete=True)
        if self.low_power_callback:
            self.low_power_callback()
        return True

    def _handle_enter_normal(self):
        if self._low_power_mode:
            self._low_power_mode = False
            self.voice.speak("已进入正常模式", wait_for_complete=True)
        if self.normal_mode_callback:
            self.normal_mode_callback()
        return True

    def _handle_light_on(self):
        # 低功耗模式下灯不可用
        if self._low_power_mode:
            self.voice.speak("低功耗模式下灯不可用", wait_for_complete=False)
            return False
        try:
            if self.light_on_callback:
                self.light_on_callback()
            self.voice.speak("已开灯", wait_for_complete=False)
        except Exception:
            self.voice.error_tone()
            return False
        return True

    def _handle_light_off(self):
        # 低功耗模式下灯不可用
        if self._low_power_mode:
            self.voice.speak("低功耗模式下灯不可用", wait_for_complete=False)
            return False
        try:
            if self.light_off_callback:
                self.light_off_callback()
            self.voice.speak("已关灯", wait_for_complete=False)
        except Exception:
            self.voice.error_tone()
            return False
        return True

    def start_collision_alert(self):
        """启动碰撞报警线程,4096字节栈空间"""
        if not self.state.alert_thread_active:
            self.state.alert_thread_active = True

            try:
                old_stack_size = _thread.stack_size()
                _thread.stack_size(4096)

                thread_args = (1, self.state, self.voice)
                self.state.alert_thread_id = _thread.start_new_thread(collision_alert_thread, thread_args)

                _thread.stack_size(old_stack_size)
                return True
            except Exception:
                self.state.alert_thread_active = False
                return False
        return False

    def process_command(self, command_byte):
        """入口:收到语音字节后查command_map执行,不在表里的响错误提示音"""
        if command_byte not in self.command_map:
            self.voice.error_tone()
            return False

        cmd_info = self.command_map[command_byte]

        if self._low_power_mode and not cmd_info.get("allow_in_low_power", False):
            self.voice.speak("低功耗模式下该功能不可用", wait_for_complete=False)
            return False

        if cmd_info["requires_awake"] and not self.state.is_awake():
            self.voice.speak("请说你好头盔唤醒", wait_for_complete=False)
            return False

        if not self.state.process_command():
            return False

        self.voice.command_ack_tone()

        try:
            result = cmd_info["action"]()
            return result
        except Exception:
            self.voice.error_tone()
            return False


class VoiceService:
    """最外层门面类，把状态管理/指令处理/传感器/语音全串起来"""

    def __init__(self, packager=None, asr=None, voice=None, low_power_callback=None, normal_mode_callback=None, on_collision=None, light_on_callback=None, light_off_callback=None):
        self.packager = packager
        self.voice_sys = voice or VoiceSystem()
        self.system_state = SystemState()
        self.sensor_sys = SensorSystem(self.packager)
        self.cmd_processor = CommandProcessor(
            self.voice_sys,
            self.sensor_sys,
            self.system_state,
            low_power_callback=low_power_callback,
            normal_mode_callback=normal_mode_callback,
            light_on_callback=light_on_callback,
            light_off_callback=light_off_callback,
        )
        self.asr = asr or VoiceASR()
        self.on_collision = on_collision
        self.sensor_enabled = True
        self._low_power = False
        self._running = False

    def set_low_power(self, enabled):
        """设置低功耗模式：关闭/开启传感器采集"""
        self._low_power = enabled
        self.sensor_enabled = not enabled
        # 清理传感器缓存数据，释放内存
        self.sensor_sys.last_payload = None
        if not enabled:
            at_lock.try_gc()

    def _voice_main_loop(self):
        """语音主循环（无线程启动），供外部线程调用"""
        while self._running:
            # 低功耗模式下不采集传感器数据（心率、温湿度、电量、位置）
            if self.sensor_enabled and not self._low_power:
                try:
                    self.packager.update()
                except Exception:
                    pass

            cmd = self.asr.read_command()
            if cmd:
                self.cmd_processor.process_command(cmd)

            if self.system_state.awake and self.voice_sys.last_tts_complete_time:
                if self.voice_sys.last_tts_complete_time > self.system_state.last_command_time:
                    self.system_state.last_command_time = self.voice_sys.last_tts_complete_time

            if self.system_state.awake and time.time() - self.system_state.last_command_time > self.system_state.awake_timeout:
                if not self.system_state.collision_detected:
                    self.voice_sys.speak("无操作，休眠", wait_for_complete=False)
                    self.voice_sys.sleep_tone()
                    self.system_state.sleep()

            time.sleep(0.1)

    def start(self):
        """完整启动（含线程），适合独立调试"""
        if self.asr.uart is None:
            return

        _thread.start_new_thread(
            event_monitor_thread,
            (self.system_state, self.cmd_processor, self.packager, self.on_collision),
        )

        self._running = True
        self._voice_main_loop()

    def stop(self):
        self._running = False
        self.system_state.stop_alert_thread()
