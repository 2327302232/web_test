import time
import gc

try:
    import ujson as json
except Exception:
    import json

from detect_collision.config import Config
from umqtt.simple import MQTTClient
import tls
import ubinascii

try:
    from sensor.data_packager import DataPackager
except Exception:
    DataPackager = None

from at_port import at_lock

# _publish_obj 返回值
_PUB_OK = 1       # 发送成功
_PUB_BUSY = 0     # AT口被占用（锁超时），非连接错误
_PUB_FAIL = -1    # 连接断开或序列化失败

class MqttUploader:
    """
    MQTT数据上传器
    负责采集传感器数据 -> 打包 -> 放队列 -> 通过MQTT发到服务器
    三级频率控制：传感器采样 > 算法处理 > 网络上传
    """

    def __init__(self, debug=False, mqtt_port=None, packager=None):
        self.debug = debug
        self.cfg = Config()

        # 三级频率：传感器采样(100Hz) > 算法(20Hz) > 上传(8Hz)
        self.sensor_rate_hz = int(getattr(self.cfg, "SAMPLE_RATE", 100))
        self.algo_rate_hz = 20
        self.upload_rate_hz = 1

        if self.sensor_rate_hz <= 0:
            self.sensor_rate_hz = 100
        if self.algo_rate_hz <= 0:
            self.algo_rate_hz = 20
        if self.upload_rate_hz <= 0:
            self.upload_rate_hz = 8
        if self.algo_rate_hz > self.sensor_rate_hz:
            self.algo_rate_hz = self.sensor_rate_hz
        if self.upload_rate_hz > self.algo_rate_hz:
            self.upload_rate_hz = self.algo_rate_hz

        self.sample_interval_ms = max(1, int(1000 / self.sensor_rate_hz))
        self.algo_div = max(1, int(self.sensor_rate_hz / self.algo_rate_hz))
        self.upload_interval_ms = max(1, int(1000 / self.upload_rate_hz))

        # 预热期：上电后数据不准先不上传
        self.warmup_seconds = int(getattr(self.cfg, "WARMUP_SECONDS", 8))
        if self.warmup_seconds < 0:
            self.warmup_seconds = 0
        self.warmup_ms = self.warmup_seconds * 1000

        # 碰撞/跌倒事件触发后，这段时间内提高上传频率（burst模式）
        self.event_upload_burst_ms = int(getattr(self.cfg, "EVENT_UPLOAD_BURST_MS", 1500))
        if self.event_upload_burst_ms < 0:
            self.event_upload_burst_ms = 0

        # 发送队列相关参数
        self.tx_queue_max = 16           # 队列最大长度，满了丢最老的包
        self.tx_budget_per_loop = 1      # 每次pump只发1个包，避免长时间占用AT口
        self.tx_guard_ms = 10            # 距离下次采样不足这个时间就别发了
        self.tx_force_watermark = 8      # 队列积压到这个数就强制发送
        self.max_catchup_cycles = 1      # 一次run_step最多追1帧采样

        self.tx_pump_interval_ms = int(getattr(self.cfg, "TX_PUMP_INTERVAL_MS", 500))
        if self.tx_pump_interval_ms < 200:
            self.tx_pump_interval_ms = 200
        self._next_tx_pump_ms = 0

        self.MQTT_BROKER = getattr(self.cfg, "MQTT_BROKER", "e3133611.ala.cn-hangzhou.emqxsl.cn")
        if mqtt_port is None:
            self.MQTT_PORT = int(getattr(self.cfg, "MQTT_PORT", 8883))
        else:
            self.MQTT_PORT = int(mqtt_port)
        self.MQTT_USERNAME = getattr(self.cfg, "MQTT_USERNAME", "Device")
        self.MQTT_PASSWORD = getattr(self.cfg, "MQTT_PASSWORD", "mqtt")
        self.CA_CERT_PATH = getattr(self.cfg, "CA_CERT_PATH", "/flash/emqxsl-ca.crt")

        self.mqtt_retry_interval_ms = int(getattr(self.cfg, "MQTT_RETRY_INTERVAL_MS", 10000))
        if self.mqtt_retry_interval_ms < 1000:
            self.mqtt_retry_interval_ms = 1000

        self._mqtt_backoff_ms = self.mqtt_retry_interval_ms
        self._mqtt_backoff_max_ms = int(getattr(self.cfg, "MQTT_RETRY_MAX_MS", 60000))
        if self._mqtt_backoff_max_ms < self._mqtt_backoff_ms:
            self._mqtt_backoff_max_ms = self._mqtt_backoff_ms

        # 上电后先等这么久再尝试MQTT连接，给网络和时间同步留余量
        self.mqtt_startup_delay_ms = int(getattr(self.cfg, "MQTT_STARTUP_DELAY_MS", 15000))
        if self.mqtt_startup_delay_ms < 0:
            self.mqtt_startup_delay_ms = 0

        # 时间门控：RTC时间没同步前不上传数据，避免证书验证失败
        self.time_gate_ms = int(getattr(self.cfg, "TIME_GATE_MS", 30000))
        if self.time_gate_ms < 0:
            self.time_gate_ms = 0

        self.connect_first_window_ms = int(getattr(self.cfg, "CONNECT_FIRST_WINDOW_MS", 10000))
        if self.connect_first_window_ms < 0:
            self.connect_first_window_ms = 0

        # MQTT连接前最低要求的空闲内存，不够就延迟重试
        self.mqtt_min_free_mem = int(getattr(self.cfg, "MQTT_MIN_FREE_MEM", 25000))
        if self.mqtt_min_free_mem < 20000:
            self.mqtt_min_free_mem = 20000

        # 内存预留：提前占一块内存，MQTT连接时释放出来应急
        self.mqtt_reserve_bytes = int(getattr(self.cfg, "MQTT_RESERVE_BYTES", 8192))
        if self.mqtt_reserve_bytes < 0:
            self.mqtt_reserve_bytes = 0
        self._mqtt_reserve = None
        if self.mqtt_reserve_bytes > 0:
            try:
                self._mqtt_reserve = bytearray(self.mqtt_reserve_bytes)
            except Exception:
                self._mqtt_reserve = None

        self.time_valid_year = int(getattr(self.cfg, "TIME_VALID_YEAR", 2024))
        self._last_time_not_sync_log_ms = 0
        self._time_gate_released_logged = False

        self._boot_ms = time.ticks_ms()
        self._next_mqtt_retry_ms = time.ticks_add(self._boot_ms, self.mqtt_startup_delay_ms)

        self.client_id = self._get_device_id()
        self.device_id = getattr(self.cfg, "MQTT_DEVICE_ID", "dev-001")

        # MQTT主题：telemetry发传感器数据，status发上下线通知，cmd接收命令，ack发命令确认
        dev = self.device_id.encode()
        self.TOPIC_DATA = b"v1/devices/" + dev + b"/telemetry"
        self.TOPIC_STATUS = b"v1/devices/" + dev + b"/status"
        self.TOPIC_CMD = b"v1/devices/" + dev + b"/cmd"
        self.TOPIC_ACK = b"v1/devices/" + dev + b"/ack"
        self.mqtt = None
        self.mqtt_connected = False

        self.is_running = False
        self.next_tick = time.ticks_ms()
        self.start_ms = 0
        self.seq = 0
        self.sensor_ticks = 0
        self.last_upload_ms = 0
        self.event_only_until_ms = 0
        self._last_event = None

        self.tx_queue = []  # 待发送队列，先进先出
        self._pending_cmds = []  # 待回复的命令队列
        self._subscribed = False  # 是否已订阅cmd topic
        self._next_check_msg_ms = 0  # 低功耗模式下次check_msg时间
        self._lp_notification_pending = False  # 待发送的低功耗通知
        self._web_power_pending = None  # 网站省电命令待处理 (target_lp, cmd_id)
        self._web_power_ack = None      # 网站省电ACK待发送 (cmd_id, target_lp)

        # 低功耗模式标志
        self._low_power_mode = False
        self._low_power_alert_active = False
        self._low_power_just_entered = False  # 标记刚进入低功耗，碰撞时需要重新启动
        self._consecutive_send_failures = 0   # 连续发送失败计数
        self._last_publish_ok_ms = 0          # 上次成功publish的时间戳，用于检测连接卡死
        self._next_keepalive_ms = 0           # 下次心跳时间

        if packager:
            self.packager = packager
        elif DataPackager is not None:
            self.packager = DataPackager()
        else:
            self.packager = None

    def _log(self, msg):
        if self.debug:
            print("[{}] {}".format(time.ticks_ms(), msg))

    def _get_device_id(self):
        try:
            from machine import unique_id
            if unique_id:
                return "helmet_{}".format(ubinascii.hexlify(unique_id()).decode()[-8:])
        except Exception:
            pass
        return "helmet_{}".format(int(time.time()))

    def _safe_json(self, obj):
        try:
            return json.dumps(obj)
        except Exception:
            return None

    def _close_mqtt(self):
        # 不做任何AT操作（避免跟TTS抢AT口），只清Python状态
        self.mqtt = None
        self.mqtt_connected = False
        self._subscribed = False
        self._lp_notification_pending = False
        self._web_power_ack = None
        now = time.ticks_ms()
        self._next_mqtt_retry_ms = time.ticks_add(now, self.mqtt_retry_interval_ms)
        self._last_publish_ok_ms = 0

    def _read_ca(self):
        paths = (
            self.CA_CERT_PATH,
            "/flash/emqxsl-ca.crt",
            "/flash/mqtt_ca.cer",
            "./emqxsl-ca.crt",
        )
        for path in paths:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if self.debug:
                    print("[MQTT] loaded CA from", path)
                return data
            except Exception:
                continue
        return None

    def _subscribe_cmd(self):
        """订阅命令topic,返回True=成功"""
        if not self.mqtt_connected or not self.mqtt:
            return False
        if not at_lock.acquire(10000):
            return False
        try:
            self.mqtt.set_callback(self._on_cmd)
            self.mqtt.subscribe(self.TOPIC_CMD)
            if self.debug:
                print("[MQTT] subscribed:", self.TOPIC_CMD)
            return True
        except Exception as e:
            print("[MQTT] subscribe failed:", e)
            return False
        finally:
            at_lock.release()

    def _sync_time(self):
        """同步NTP时间,解决证书验证时间不对的问题"""
        try:
            import ntptime
            ntptime.settime()
            print("[TIME] synced:", time.time())
            return True
        except Exception as e:
            print("[TIME] NTP failed:", e)
            return False

    def _init_mqtt(self):
        self._close_mqtt()
        at_lock.try_gc(force=True)
        time.sleep_ms(100)
        at_lock.try_gc(force=True)

        self._sync_time()

        ssl_ctx = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
        ssl_ctx.verify_mode = tls.CERT_REQUIRED

        ca = self._read_ca()
        if ca is None:
            ssl_ctx.verify_mode = tls.CERT_NONE
            if self.debug:
                print("[MQTT] CA not found, using CERT_NONE")
        else:
            try:
                ssl_ctx.load_verify_locations(ca)
            except Exception as e:
                ssl_ctx.verify_mode = tls.CERT_NONE
                if self.debug:
                    print("[MQTT] CA load failed:", e)

        self.mqtt = MQTTClient(
            client_id=self.client_id,
            server=self.MQTT_BROKER,
            port=self.MQTT_PORT,
            user=self.MQTT_USERNAME,
            password=self.MQTT_PASSWORD,
            ssl=ssl_ctx,
            keepalive=60,
        )

        try:
            self.mqtt.connect()
        except Exception as e:
            self._close_mqtt()
            at_lock.try_gc(force=True)
            raise

        self.mqtt_connected = True
        self._mqtt_backoff_ms = self.mqtt_retry_interval_ms
        self._next_keepalive_ms = time.ticks_add(time.ticks_ms(), 40000)
        self._next_check_msg_ms = time.ticks_add(time.ticks_ms(), 2000)

    def _ensure_mqtt(self):
        """确保MQTT连接就绪,带退避重试"""
        if self.mqtt_connected and self.mqtt:
            return True

        if not self.is_running:
            return False

        now = time.ticks_ms()

        # 重试间隔检查（简单退避：失败后等10秒再试）
        if time.ticks_diff(now, self._next_mqtt_retry_ms) < 0:
            return False

        # 释放预留内存给MQTT连接用
        if self._mqtt_reserve is not None:
            self._mqtt_reserve = None
            at_lock.try_gc(force=True)

        if not at_lock.acquire(15000):
            self._next_mqtt_retry_ms = time.ticks_add(now, 10000)
            return False
        try:
            self._init_mqtt()
            self._mqtt_backoff_ms = self.mqtt_retry_interval_ms
            return True
        except Exception as e:
            print("[MQTT] 连接失败:", e)
            self._next_mqtt_retry_ms = time.ticks_add(now, 10000)
            self._close_mqtt()
            return False
        finally:
            at_lock.release()
            at_lock.try_gc()

    def _queue_push(self, pkt):
        """入队，满了丢最老的包"""
        if len(self.tx_queue) >= self.tx_queue_max:
            try:
                self.tx_queue.pop(0)
            except Exception:
                pass
        self.tx_queue.append(pkt)

    def _queue_unshift(self, pkt):
        self.tx_queue.insert(0, pkt)

    def _publish_obj(self, topic, obj, ensure=True):
        if ensure and (not self._ensure_mqtt()):
            return _PUB_FAIL
        payload = self._safe_json(obj)
        if payload is None:
            return _PUB_FAIL
        if not at_lock.acquire(5000):
            return _PUB_BUSY       # AT口忙，非连接错误
        try:
            self.mqtt.publish(topic, payload)
            self._last_publish_ok_ms = time.ticks_ms()
            del payload
            gc.collect()
            return _PUB_OK
        except Exception:
            del payload
            gc.collect()
            # 锁在手，安全做AT操作：先sock.close（发QICLOSE停firmware重试），再disconnect（优雅断开）
            try:
                self.mqtt.sock.close()
            except Exception:
                pass
            try:
                self.mqtt.disconnect()
            except Exception:
                pass
            self._close_mqtt()
            return _PUB_FAIL
        finally:
            at_lock.release()

    def _send_lp_notification(self):
        """发送低功耗模式通知（只发一次,由MQTT线程调用)"""
        ts = int(time.time() * 1000)
        if ts < 1000000000000:
            ts += 946684800000
        payload = self._safe_json({
            "deviceId": self.device_id,
            "ts": ts,
            "low_power": True,
        })
        if payload is None:
            return
        if not at_lock.acquire(5000):
            return
        try:
            self.mqtt.publish(self.TOPIC_DATA, payload)
        except Exception:
            pass
        finally:
            at_lock.release()
        at_lock.try_gc()

    def set_low_power_mode(self, enabled):
        """设置低功耗模式：停止采集和普通上传,但保持MQTT连接(碰撞报警仍需发送)"""
        self._low_power_mode = enabled
        if enabled:
            # 进入低功耗：标记待发送通知，清空待发队列释放内存
            self._lp_notification_pending = True
            self.tx_queue = []
            self._low_power_just_entered = True
        at_lock.try_gc()

    def clear_alert(self):
        """清除碰撞报警状态，停止发送碰撞事件数据"""
        self._low_power_alert_active = False
        self.event_only_until_ms = 0
        self._last_event = None

    def pop_web_power_pending(self):
        """取出网站下发的省电命令，返回 (target_lp, cmd_id) 或 None"""
        v = self._web_power_pending
        self._web_power_pending = None
        return v

    def set_web_power_ack(self, cmd_id, target_lp):
        """设置网站省电命令的ACK,由主循环发送"""
        self._web_power_ack = (cmd_id, target_lp)

    def _pump_tx(self):
        """发送队列里的包:连续失败累计到3次才断连,避免临时异常误触发"""
        if not self.tx_queue:
            return
        if not self._ensure_mqtt():
            self.tx_queue = []
            self._consecutive_send_failures = 0
            at_lock.try_gc()
            return

        sent = 0
        while self.tx_queue and sent < self.tx_budget_per_loop:
            now = time.ticks_ms()
            until_next = time.ticks_diff(self.next_tick, now)

            if until_next <= self.tx_guard_ms and len(self.tx_queue) < self.tx_force_watermark:
                break

            pkt = self.tx_queue.pop(0)
            result = self._publish_obj(self.TOPIC_DATA, pkt, ensure=False)
            if result == _PUB_OK:
                self._consecutive_send_failures = 0
            elif result == _PUB_BUSY:
                self._queue_unshift(pkt)
                break
            else:
                # 真正的发送失败（连接断开或超时）
                self._queue_unshift(pkt)
                self._consecutive_send_failures += 1
                if self._consecutive_send_failures >= 3:
                    self._close_mqtt()
                    self.tx_queue = []
                    self._consecutive_send_failures = 0
                    at_lock.try_gc()
                break
            sent += 1

        if sent > 0:
            self._consecutive_send_failures = 0
            at_lock.try_gc()

    def _should_enqueue(self, pkt, now_ms):
        """判断这个包该不该入队：事件包高频入，普通包按上传间隔节流"""
        in_event_mode = (
            self._low_power_alert_active
            or time.ticks_diff(self.event_only_until_ms, now_ms) > 0
        )
        if in_event_mode:
            self.event_only_until_ms = time.ticks_add(now_ms, self.event_upload_burst_ms)
            min_gap = max(40, self.upload_interval_ms // 2)
            if time.ticks_diff(now_ms, self.last_upload_ms) >= min_gap:
                self.last_upload_ms = now_ms
                return True
            return False

        if time.ticks_diff(now_ms, self.last_upload_ms) >= self.upload_interval_ms:
            self.last_upload_ms = now_ms
            return True

        return False

    def _build_data_packet(self, now_ms):
        """组装一个要上传的数据包"""
        if self.packager is None:
            return None

        try:
            realtime = self.packager.get_realtime_payload()
        except Exception:
            at_lock.try_gc(force=True)
            return None
        if realtime is None:
            return None

        loc = realtime.get("location") or {}
        env = realtime.get("env") or {}

        # Unix毫秒时间戳
        ts = int(time.time() * 1000)
        if ts < 1000000000000:
            ts += 946684800000

        # 扁平telemetry格式
        pkt = {
            "deviceId": self.device_id,
            "ts": ts,
            "lng": loc.get("longitude"),
            "lat": loc.get("latitude"),
            "speed": loc.get("speed_kmh"),
            "altitude": loc.get("altitude"),
            "accuracy": loc.get("accuracy") or loc.get("hdop"),
            "location_source": loc.get("source") or loc.get("loc_type"),
            "heart_rate": realtime.get("heart_rate", 0) or 0,
            "temperature": env.get("temperature_c") if env else None,
            "humidity": env.get("humidity") if env else None,
            "battery": realtime.get("battery_soc"),
            "low_power": self._low_power_mode,
        }

        event_payload = self.packager.poll_event_payload()
        if event_payload:
            self._last_event = event_payload.get("event")
            self.event_only_until_ms = time.ticks_add(now_ms, self.event_upload_burst_ms)
            del event_payload

        # 报警模式：碰撞/SOS触发后只发位置+事件字段
        in_event_only = (
            time.ticks_diff(self.event_only_until_ms, now_ms) > 0
            or self._low_power_alert_active
        )

        if in_event_only:
            pkt = {
                "deviceId": self.device_id,
                "ts": ts,
                "lng": loc.get("longitude"),
                "lat": loc.get("latitude"),
                "speed": loc.get("speed_kmh"),
                "altitude": loc.get("altitude"),
                "accuracy": loc.get("accuracy") or loc.get("hdop"),
                "location_source": loc.get("source") or loc.get("loc_type"),
                "battery": realtime.get("battery_soc"),
                "low_power": self._low_power_mode,
                "collision": True,
            }
            if self._last_event:
                pkt["event"] = self._last_event

        self.seq += 1
        at_lock.try_gc()
        return pkt

    def start(self):
        """启动：重置所有计数器，发一条上线通知"""
        self.is_running = True
        self.next_tick = time.ticks_ms()
        self.start_ms = self.next_tick
        self._next_tx_pump_ms = self.next_tick
        self.seq = 0
        self.sensor_ticks = 0
        self.last_upload_ms = self.next_tick
        self.event_only_until_ms = 0
        self.tx_queue = []
        at_lock.try_gc(force=True)

        ts = int(time.time() * 1000)
        if ts < 1000000000000:
            ts += 946684800000
        status_msg = {
            "deviceId": self.device_id,
            "status": "start",
            "online": True,
            "ts": ts,
        }
        self._publish_obj(self.TOPIC_STATUS, status_msg)
        del status_msg
        at_lock.try_gc(force=True)

    def stop(self):
        """停止：清空队列,断MQTT"""
        self.is_running = False
        self.tx_queue = []
        # stop时尝试拿锁做AT操作，保证socket被关闭
        if self.mqtt and at_lock.acquire(5000):
            try:
                try:
                    self.mqtt.disconnect()
                except Exception:
                    pass
                try:
                    self.mqtt.sock.close()
                except Exception:
                    pass
            finally:
                at_lock.release()
        self._close_mqtt()

    def run_step(self):
        """主循环每帧调一次：采样计数 -> 打包 -> 入队 -> 发送"""
        if not self.is_running:
            return

        # 低功耗模式（无碰撞报警时）：精简循环，只处理心跳和命令
        if self._low_power_mode and not self._low_power_alert_active:
            now_lp = time.ticks_ms()
            if self._lp_notification_pending:
                if at_lock.acquire(5000):
                    try:
                        self.mqtt.publish(self.TOPIC_STATUS, b'{"status":"low_power"}')
                        self._lp_notification_pending = False
                    except Exception:
                        pass
                    finally:
                        at_lock.release()
                if self._lp_notification_pending:
                    self._lp_notification_pending = False
                    self._send_lp_notification()
            if time.ticks_diff(now_lp, self._next_check_msg_ms) >= 0:
                self._next_check_msg_ms = time.ticks_add(now_lp, 3000)
                if not self._subscribed:
                    self._subscribed = self._subscribe_cmd()
                if at_lock.acquire(50):
                    try:
                        self.mqtt.check_msg()
                    except Exception:
                        pass
                    finally:
                        at_lock.release()
                self._process_pending_cmds()
                if self._web_power_ack:
                    cmd_id, target_lp = self._web_power_ack
                    self._web_power_ack = None
                    self._send_power_ack(cmd_id, target_lp)
            if time.ticks_diff(now_lp, self._next_keepalive_ms) >= 0:
                if at_lock.acquire(5000):
                    try:
                        self.mqtt.ping()
                    except Exception:
                        self._close_mqtt()
                    finally:
                        at_lock.release()
                self._next_keepalive_ms = time.ticks_add(now_lp, 50000)
                at_lock.try_gc()
            time.sleep_ms(100)
            return

        # 低功耗模式下碰撞报警刚触发：重新初始化采集和发送
        if self._low_power_mode and self._low_power_alert_active and self._low_power_just_entered:
            self._low_power_just_entered = False
            self.start()
            at_lock.try_gc()

        now = time.ticks_ms()

        # 刚启动还没连上MQTT，在首次连接窗口内专心连MQTT
        if (not self.mqtt_connected) and (time.ticks_diff(now, self.start_ms) < self.connect_first_window_ms):
            self._ensure_mqtt()
            return

        # 首次连接窗口后也要周期性尝试重连（断开/失败后自动重连）
        if not self.mqtt_connected and time.ticks_diff(now, self._next_mqtt_retry_ms) >= 0:
            self._ensure_mqtt()

        catchup = 0
        while time.ticks_diff(now, self.next_tick) >= 0 and catchup < self.max_catchup_cycles:
            self.next_tick = time.ticks_add(self.next_tick, self.sample_interval_ms)
            self.sensor_ticks += 1

            try:
                if (self.sensor_ticks % self.algo_div) == 0:
                    if (not self.mqtt_connected) and (len(self.tx_queue) >= self.tx_queue_max):
                        pass
                    else:
                        pkt = self._build_data_packet(now)
                        if pkt and self._should_enqueue(pkt, now):
                            self._queue_push(pkt)
            except Exception:
                pass

            catchup += 1
            now = time.ticks_ms()

        if time.ticks_diff(now, self.next_tick) >= 0:
            self.next_tick = time.ticks_add(now, self.sample_interval_ms)

        if (time.ticks_diff(now, self._next_tx_pump_ms) >= 0) or (len(self.tx_queue) >= self.tx_force_watermark):
            self._pump_tx()
            self._next_tx_pump_ms = time.ticks_add(now, self.tx_pump_interval_ms)

    def _on_cmd(self, topic, msg):
        """收到命令先入队,不在回调中publish"""
        try:
            payload = json.loads(msg)
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        self._pending_cmds.append(payload)
        print("[CMD] queue type=%s action=%s" % (
            payload.get("type"), payload.get("action")))

    def _process_pending_cmds(self):
        """在主循环中处理待回复的命令"""
        while self._pending_cmds:
            payload = self._pending_cmds.pop(0)
            cmd_id = payload.get("cmdId") or payload.get("cmd_id")
            req_type = payload.get("type")
            action = payload.get("action")
            if req_type == "request" and action == "status":
                bat = 0
                try:
                    from sensor.battery import get_battery_soc
                    bat = get_battery_soc() or 0
                except Exception:
                    pass
                ts = int(time.time() * 1000)
                if ts < 1000000000000:
                    ts += 946684800000
                status_msg = {
                    "deviceId": self.device_id,
                    "cmdId": cmd_id,
                    "online": True,
                    "status": "ok",
                    "message": "helmet online",
                    "battery": bat,
                    "low_power": self._low_power_mode,
                    "ts": ts,
                }
                self._publish_obj(self.TOPIC_STATUS, status_msg)
            elif req_type == "power" and action == "set":
                value = payload.get("value", {})
                target_lp = bool(value.get("low_power", False)) if isinstance(value, dict) else bool(value)
                self._web_power_pending = (target_lp, cmd_id)

    def _send_power_ack(self, cmd_id, target_lp):
        """发送省电模式命令的确认"""
        bat = 0
        try:
            from sensor.battery import get_battery_soc
            bat = get_battery_soc() or 0
        except Exception:
            pass
        ts = int(time.time() * 1000)
        if ts < 1000000000000:
            ts += 946684800000
        ack = {
            "deviceId": self.device_id,
            "cmdId": cmd_id,
            "ok": True,
            "message": "power mode updated",
            "battery": bat,
            "low_power": target_lp,
            "ts": ts,
        }
        self._publish_obj(self.TOPIC_ACK, ack)



    def run_forever(self):
        """阻塞主循环,适合独立运行。外部设置is_running=False即可退出"""
        self.start()
        next_hk = time.ticks_ms()

        while self.is_running:
            self.run_step()

            now = time.ticks_ms()
            if time.ticks_diff(now, next_hk) >= 500:
                next_hk = time.ticks_add(now, 500)
                if self.mqtt_connected and self.mqtt:
                    if not self._subscribed:
                        self._subscribed = self._subscribe_cmd()
                    if at_lock.acquire(50):
                        try:
                            self.mqtt.check_msg()
                        except Exception:
                            pass
                        finally:
                            at_lock.release()
                    self._process_pending_cmds()
                    if self._web_power_ack:
                        cmd_id, target_lp = self._web_power_ack
                        self._web_power_ack = None
                        self._send_power_ack(cmd_id, target_lp)
                    if time.ticks_diff(now, self._next_keepalive_ms) >= 0:
                        if at_lock.acquire(5000):
                            try:
                                self.mqtt.ping()
                            except Exception as e:
                                print("[MQTT] ping failed:", e)
                                self._close_mqtt()
                            finally:
                                at_lock.release()
                        self._next_keepalive_ms = time.ticks_add(now, 40000)
                        at_lock.try_gc()

            time.sleep_ms(2)

        self.stop()
