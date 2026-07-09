import time
from machine import UART, Pin


class VoiceASR:
    """语音识别模块驱动,通过UART接收语音芯片发来的指令字节"""

    def __init__(self, uart_id=2, baudrate=9600, tx_pin_name="PD5", rx_pin_name="PD6", af=7):
        self.uart = None
        self.uart_id = uart_id
        self.baudrate = baudrate
        self.tx_pin_name = tx_pin_name
        self.rx_pin_name = rx_pin_name
        self.af = af
        self._init_uart()

    def _init_uart(self):
        try:
            Pin(self.tx_pin_name, Pin.AF_PP, af=self.af)
            Pin(self.rx_pin_name, Pin.AF_PP, af=self.af)
            self.uart = UART(self.uart_id, baudrate=self.baudrate)
        except Exception as e:
            pass
            self.uart = None

    def available(self):
        """串口有没有数据可读"""
        return self.uart is not None and self.uart.any()

    def read_command(self):
        """读1字节指令,语音芯片识别到关键词后会通过串口发一个字节过来"""
        if not self.available():
            return None
        try:
            data = self.uart.read(1)
            if data:
                return data
        except Exception:
            return None
        return None

