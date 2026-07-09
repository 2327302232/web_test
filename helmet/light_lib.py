from machine import ADC, Pin
import pyb
import time


# 内部状态
_adc = None
_pwm_channel = None
_config = {
    'adc_pin': 'C5',
    'pwm_pin': 'PD15',
    'timer_id': 4,
    'channel_id': 4,
    'freq': 300,
    'adc_min': 15000,
    'adc_max': 55000,
}
_initialized = False
_current_duty = 0


def init(adc_pin='C5', pwm_pin='PD15', timer_id=4, channel_id=4,
         freq=300, adc_min=15000, adc_max=55000):
    global _adc, _pwm_channel, _config, _initialized

    _config.update({
        'adc_pin': adc_pin,
        'pwm_pin': pwm_pin,
        'timer_id': timer_id,
        'channel_id': channel_id,
        'freq': freq,
        'adc_min': adc_min,
        'adc_max': adc_max,
    })

    _adc = ADC(Pin(adc_pin))

    pwm_pin_obj = pyb.Pin(pwm_pin)
    tim = pyb.Timer(timer_id, freq=freq)
    _pwm_channel = tim.channel(channel_id, pyb.Timer.PWM, pin=pwm_pin_obj)

    _initialized = True


def _check_init():
    if not _initialized:
        raise RuntimeError("light_lib not initialized. Call init() first.")


def get_adc():
    _check_init()
    return _adc.read_u16()


def get_adc_12bit():
    _check_init()
    value_16bit = _adc.read_u16()
    value_12bit = value_16bit >> 4
    return value_12bit & 0xFFF


def get_voltage():
    _check_init()
    value = get_adc_12bit()
    return (value * 3.3) / 4095.0


def set_brightness(percent):
    global _current_duty
    _check_init()
    percent = max(0, min(100, percent))
    _pwm_channel.pulse_width_percent(percent)
    _current_duty = percent




def update():
    _check_init()
    raw_u16 = get_adc()
    raw_12bit = get_adc_12bit()
    voltage = get_voltage()

    adc_min = _config['adc_min']
    adc_max = _config['adc_max']

    if raw_u16 <= adc_min:
        brightness = 0
    elif raw_u16 >= adc_max:
        brightness = 100
    else:
        brightness = int(100 * (raw_u16 - adc_min) / (adc_max - adc_min))

    set_brightness(brightness)

    return {
        'raw_u16': raw_u16,
        'raw_12bit': raw_12bit,
        'voltage': voltage,
        'brightness': brightness,
    }

