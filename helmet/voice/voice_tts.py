import time
import quectel

try:
    import _thread
except Exception:
    _thread = None

from at_port import at_lock

class _NullLock:

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class VoiceSystem:
    """TTS语音播报系统"""

    def __init__(self, voice_lock=None):
        self.audio = None
        self.initialized = False
        self.is_speaking = False           # 当前是否在播报
        self.last_tts_complete_time = 0    # 上次播报完成的时间戳
        self.voice_lock = voice_lock or (_thread.allocate_lock() if _thread else _NullLock())
        self._init_audio()

    def _init_audio(self):
        """初始化quectel音频模块,注册TTS播报完成回调"""
        try:
            time.sleep(0.5)
            self.audio = quectel.Audio()

            def callback(event):
                # TTS播完后回调，更新状态，voice_service会用这个时间来续命唤醒态
                if event == quectel.Audio.TTS_END:
                    with self.voice_lock:
                        self.is_speaking = False
                    self.last_tts_complete_time = time.time()

            if self.audio.init(callback):
                self.audio.tts_set_volume(100)
                try:
                    self.audio.set_speaker_volume(5)
                except Exception:
                    pass
                self.initialized = True

        except Exception as e:
            self.initialized = False

    def speak(self, text, speed=1.0, interrupt=True, wait_for_complete=False):
        """
        播报语音文本
        - interrupt: 是否打断当前播报
        - wait_for_complete: 阻塞等播报结束（用于需要顺序播报的场景）
        """
        with self.voice_lock:
            if self.is_speaking and not interrupt:
                return False
            self.is_speaking = True

        # 音频没初始化成功就模拟等待，不影响逻辑流程
        if not self.initialized or not self.audio:
            time.sleep(len(text) * 0.08 * speed)
            with self.voice_lock:
                self.is_speaking = False
            self.last_tts_complete_time = time.time()
            return True

        # TTS占用AT口期间，让GNSS跳过硬件查询，避免AT口冲突
        _gnss = None
        try:
            from sensor.gnss import gnss_module as _gnss
            _gnss.skip_hardware = True
        except Exception:
            pass

        result = False
        try:
            for attempt in range(2):
                if attempt > 0:
                    print("[TTS] tts_play失败，重新初始化Audio并重试一次")
                    time.sleep(1)
                    try:
                        self.audio = quectel.Audio()
                        def _cb(ev):
                            if ev == quectel.Audio.TTS_END:
                                with self.voice_lock:
                                    self.is_speaking = False
                                self.last_tts_complete_time = time.time()
                        if self.audio.init(_cb):
                            self.audio.tts_set_volume(100)
                            try:
                                self.audio.set_speaker_volume(5)
                            except Exception:
                                pass
                            self.initialized = True
                            print("[TTS] Audio重新初始化成功")
                        else:
                            print("[TTS] Audio重新初始化失败")
                    except Exception as e:
                        print(f"[TTS] Audio重初始化异常: {e}")
                        break

                if not at_lock.acquire(30000):
                    with self.voice_lock:
                        self.is_speaking = False
                    result = False
                    break
                try:
                    result = self.audio.tts_play(text)
                except Exception as e:
                    print(f"[TTS] tts_play失败: {e}")
                finally:
                    at_lock.release()

                if result is not False:
                    break  # 成功
        finally:
            if _gnss is not None:
                try:
                    _gnss.skip_hardware = False
                except Exception:
                    pass

        if wait_for_complete:
            timeout = len(text) * 0.25 + 3.0
            start_time = time.time()
            while self.is_speaking and (time.time() - start_time < timeout):
                time.sleep(0.05)
            if self.is_speaking:
                with self.voice_lock:
                    self.is_speaking = False
        return result is not False

    def beep(self, duration=0.1, tone=440):
        """播放提示音（简单延时模拟，实际硬件可能有蜂鸣器驱动）"""
        time.sleep(duration)
        return True

    def wakeup_tone(self):
        """唤醒提示音"""
        self.beep(0.05, 660)

    def command_ack_tone(self):
        """指令确认音"""
        self.beep(0.05, 440)

    def error_tone(self):
        """错误提示音"""
        self.beep(0.1, 220)

    def sleep_tone(self):
        """休眠提示音"""
        self.beep(0.2, 330)

    def collision_alert_tone(self):
        """碰撞报警音：两组高低音交替，制造紧迫感"""
        for _ in range(2):
            self.beep(0.2, 880)
            time.sleep(0.1)
            self.beep(0.1, 440)
            time.sleep(0.1)