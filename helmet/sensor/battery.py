"""
MAX17049 电池电量计驱动 - 仅读取电量
I2C地址: 0x36 (7-bit)
SOC寄存器: 0x04, 高字节=整数%, 低字节=小数部分(1/256%)
"""

import time
from machine import SoftI2C, Pin

_MAX17049_ADDR = 0x36
_REG_SOC = 0x04


class BatteryLevel:
    def __init__(self):
        self._i2c = None
        self._ok = False
        self._last_soc = None
        self._last_soc_ms = 0
        self._cache_ms = 10000  # 缓存10秒，避免频繁I2C超时
        self._fail_count = 0
        self._max_fail_before_disable = 3  # 连续失败3次后停止尝试
        self._init_sensor()

    def _init_sensor(self):
        try:
            self._i2c = SoftI2C(sda=Pin("PF15"), scl=Pin("PE13"), freq=400000)
            devices = self._i2c.scan()
            if _MAX17049_ADDR in devices:
                self._ok = True
                print("MAX17049 初始化成功")
            else:
                print("MAX17049 未找到, 地址: 0x%02X" % _MAX17049_ADDR)
        except Exception as e:
            print("MAX17049 初始化失败:", e)

    def ok(self):
        return self._ok

    def get_soc(self):
        """
        获取电池电量百分比（带缓存）

        返回:
            int: 电量百分比 (0~100),失败返回None
        """
        if not self._ok:
            return self._last_soc  # 返回缓存值，可能是None

        # 缓存未过期直接返回
        now = time.ticks_ms()
        if self._last_soc is not None:
            if time.ticks_diff(now, self._last_soc_ms) < self._cache_ms:
                return self._last_soc

        try:
            data = self._i2c.readfrom_mem(_MAX17049_ADDR, _REG_SOC, 2)
            soc = data[0]
            if soc < 0:
                soc = 0
            elif soc > 100:
                soc = 100
            self._last_soc = soc
            self._last_soc_ms = now
            self._fail_count = 0
            return soc
        except Exception as e:
            self._fail_count += 1
            print("MAX17049 读取电量失败: %s" % e)
            # 连续失败多次后停止尝试，避免持续阻塞
            if self._fail_count >= self._max_fail_before_disable:
                self._ok = False
            return self._last_soc  # 返回缓存值


# ==================== 简单接口 ====================

_battery = None


def _get_battery():
    global _battery
    if _battery is None:
        _battery = BatteryLevel()
    return _battery


def get_battery_soc():
    """
    获取电池电量百分比

    返回:
        int: 电量 (0~100)，失败返回None
    """
    return _get_battery().get_soc()



