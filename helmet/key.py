# 智能头盔按键库
import time
from machine import Pin


class ButtonService:
    def __init__(
        self,
        power_pin="PA3",
        sos_pin="PC0",
        long_press_ms=2000,
        short_press_ms=50,
        on_sos=None,
        on_sos_cancel=None,
        on_stop_alarm=None,
        on_enter_low_power=None,
        on_exit_low_power=None,
    ):
        self.key_power = Pin(power_pin, Pin.IN, Pin.PULL_UP)
        self.key_sos = Pin(sos_pin, Pin.IN, Pin.PULL_UP)

        self.long_press_ms = int(long_press_ms)
        self.short_press_ms = int(short_press_ms)

        self.on_sos = on_sos
        self.on_sos_cancel = on_sos_cancel
        self.on_stop_alarm = on_stop_alarm
        self.on_enter_low_power = on_enter_low_power
        self.on_exit_low_power = on_exit_low_power

        self._power_pressed = False
        self._sos_pressed = False
        self._power_press_time = 0
        self._sos_press_time = 0
        self._low_power_mode = False

    def is_low_power_mode(self):
        return self._low_power_mode

    def update(self):
        now = time.ticks_ms()

        # 电源键：短按取消报警，长按切换低功耗/正常模式
        if self.key_power.value() == 0:
            if not self._power_pressed:
                self._power_pressed = True
                self._power_press_time = now
        else:
            if self._power_pressed:
                press_duration = time.ticks_diff(now, self._power_press_time)
                self._power_pressed = False

                if press_duration >= self.long_press_ms:
                    self._fire_callback(self.on_stop_alarm)
                elif press_duration >= self.short_press_ms:
                    self._toggle_low_power()

        # SOS键：短按触发SOS，长按取消SOS报警
        if self.key_sos.value() == 0:
            if not self._sos_pressed:
                self._sos_pressed = True
                self._sos_press_time = now
        else:
            if self._sos_pressed:
                press_duration = time.ticks_diff(now, self._sos_press_time)
                self._sos_pressed = False

                if press_duration >= self.long_press_ms:
                    self._fire_callback(self.on_sos_cancel)
                elif press_duration >= self.short_press_ms:
                    self._fire_callback(self.on_sos)

    def _toggle_low_power(self):
        if not self._low_power_mode:
            self._low_power_mode = True
            self._fire_callback(self.on_enter_low_power)
        else:
            self._low_power_mode = False
            self._fire_callback(self.on_exit_low_power)

    def _fire_callback(self, cb):
        if cb:
            try:
                cb()
            except Exception:
                pass



