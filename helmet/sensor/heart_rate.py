import qwiic_max3010x
import time


def millis():
    # 纳秒转毫秒
    return time.time_ns() // 1000000


class TempleHeartRate:
    def __init__(self):
        self.sensor = None

    def _init_sensor(self):
        self.sensor = qwiic_max3010x.QwiicMax3010x()
        if not self.sensor.begin():
            self.sensor = None
            return False

        # 太阳穴专用配置 - 高灵敏度
        self.sensor.setup(
            powerLevel=0x1F,      # LED驱动功率，太阳穴皮肤薄用低功率就够
            sampleAverage=1,      # 不做采样平均，保留原始波形
            ledMode=2,            # Red+IR双通道
            sampleRate=400,       # 400Hz高采样率
            pulseWidth=411,       # 脉冲宽度411us，提高ADC分辨率
            adcRange=8192
        )
        self.sensor.setPulseAmplitudeIR(0x1F)
        self.sensor.setPulseAmplitudeRed(0x1F)
        return True


class TaiyangStepper:
    def __init__(self, emit_interval_ms=3000):
        self.monitor = TempleHeartRate()
        self.emit_interval_ms = emit_interval_ms
        self._ok = self.monitor._init_sensor()
        self.raw_signal = []
        self.buffer_size = 50
        self.baseline = 0
        self.baseline_alpha = 0.05
        self.last_beat_time = 0
        self.bpm_values = []
        self.max_bpm_values = 6
        self.peak_threshold = 15
        self.min_beat_interval = 600
        self.max_beat_interval = 1500
        self.last_emit_time = millis()

    def ok(self):
        return self._ok

    def step(self):
        # 返回None=还没到输出时间，0=没数据，float=BPM
        if not self._ok:
            return None

        ir_value = self.monitor.sensor.getIR()
        red_value = self.monitor.sensor.getRed()

        combined_value = ir_value + red_value
        # 信号丢失，重置状态
        if combined_value < 10000:
            self.bpm_values.clear()
            self.last_beat_time = 0
            self.baseline = 0
            return 0

        if self.baseline == 0:
            self.baseline = combined_value
        else:
            self.baseline = self.baseline_alpha * combined_value + (1 - self.baseline_alpha) * self.baseline

        ac_value = combined_value - self.baseline

        self.raw_signal.append(ac_value)
        if len(self.raw_signal) > self.buffer_size:
            self.raw_signal.pop(0)

        if len(self.raw_signal) >= 4:
            diff1 = self.raw_signal[-1] - self.raw_signal[-2]
            diff2 = self.raw_signal[-2] - self.raw_signal[-3]

            if diff2 > 0 and diff1 < 0:
                if len(self.raw_signal) >= 7:
                    baseline_val = (
                        self.raw_signal[-7] + self.raw_signal[-6] + self.raw_signal[-5] +
                        self.raw_signal[-4] + self.raw_signal[-3]
                    ) / 5
                    peak_height = self.raw_signal[-2] - baseline_val
                else:
                    peak_height = diff2

                if peak_height > self.peak_threshold:
                    now = millis()
                    delta = now - self.last_beat_time

                    if self.last_beat_time > 0 and self.min_beat_interval < delta < self.max_beat_interval:
                        bpm = 60000.0 / delta
                        bpm = round(bpm, 1)

                        if 40 < bpm < 100:
                            self.last_beat_time = now
                            self.bpm_values.append(bpm)
                            if len(self.bpm_values) > self.max_bpm_values:
                                self.bpm_values.pop(0)
                    elif self.last_beat_time == 0:
                        self.last_beat_time = now

        # 到输出时间了就返回平均BPM
        now_time = millis()
        if now_time - self.last_emit_time >= self.emit_interval_ms:
            self.last_emit_time = now_time
            if self.bpm_values:
                avg_bpm = sum(self.bpm_values) / len(self.bpm_values)
                return round(avg_bpm, 1)
            return 0

        return None  # 还没到时间8