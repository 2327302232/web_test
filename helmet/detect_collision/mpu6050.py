import machine
import time
import ustruct
import math
from machine import I2C, Pin

class MPU6050:
    """MPU6050六轴IMU驱动"""
    
    #寄存器地址
    SAMPLE_DIV=0x19          #采样率分配器
    CONFIG=0x1A              #配置寄存器
    GYRO_CONFIG=0x1B         #陀螺仪配置寄存器
    GYRO_XOUT_H=0x43         #陀螺仪数据起始位置
    ACCEL_CONFIG=0x1C        #加速度计配置寄存器
    ACCEL_XOUT_H=0x3B        #加速度计数据起始位置
    PWR_MGMT_1=0x6B          #电源管理寄存器1
    TEMP_OUT_H=0x41          #温度数据起始位置

    def __init__(self,i2c,addr=0x68):
        """初始化MPU6050对象
        参数：
            i2c: I2C对象
            addr: MPU6050的I2C地址
        """
        self.i2c=i2c
        self.addr=addr

        #校准数据
        self.accel_bias=[0.0,0.0,0.0]
        self.gyro_bias=[0.0,0.0,0.0]

        #初始化MPU6050
        self._initialize()

    def _write_reg(self,reg,value):
        buf=bytearray([value])
        self.i2c.writeto_mem(self.addr, reg, buf)

    def _read_reg(self,reg,nbytes):
        return self.i2c.readfrom_mem(self.addr, reg, nbytes)
    
    def _initialize(self):
        #唤醒MPU6050
        try:
            self._write_reg(self.PWR_MGMT_1, 0x00)
            time.sleep(0.1)

            #设置采样率为(200Hz)
            self._write_reg(self.SAMPLE_DIV, 0x04)

            #设置陀螺仪量程为±1000°/s
            self._write_reg(self.GYRO_CONFIG, 0x18)

            #设置加速度计量程为±8g
            self._write_reg(self.ACCEL_CONFIG, 0x10) 

            #配置低通滤波器
            self._write_reg(self.CONFIG, 0x03)   

            print("MPU6050初始化完成")
        except Exception as e:
            print("MPU6050初始化失败:", e)
            
    def calibrate(self,samples=1000):
        """校准MPU6050，计算加速度计和陀螺仪的偏置
        参数：
            samples: 校准时采集的样本数量
        """
        accel_sum=[0.0,0.0,0.0]
        gyro_sum=[0.0,0.0,0.0]

        for i in range(samples):
            #读取原始数据
            accel_raw,gyro_raw,temp=self.read_raw()

            #累加数据
            for j in range(3):
                accel_sum[j]+=accel_raw[j]
                gyro_sum[j]+=gyro_raw[j]

            time.sleep_ms(5)  #适当延时，避免过快采集

        #计算零偏
        for j in range(3):
            self.accel_bias[j]=accel_sum[j]/samples
            self.gyro_bias[j]=gyro_sum[j]/samples

        #调整z轴加速度计零偏（1g=4096LSB）
        self.accel_bias[2]-=4096.0

        print("MPU6050校准完成")

    def read_raw(self):
        """读取原始传感器数据"""
        #读取14字节：加速度（6）+温度（2）+陀螺仪（6）
        data=self._read_reg(self.ACCEL_XOUT_H, 14)

        #解析加速度计数据
        ax=ustruct.unpack(">h", data[0:2])[0]
        ay=ustruct.unpack(">h", data[2:4])[0]
        az=ustruct.unpack(">h", data[4:6])[0]

        #解析温度数据
        temp=ustruct.unpack(">h", data[6:8])[0]

        #解析陀螺仪数据
        gx=ustruct.unpack(">h", data[8:10])[0]
        gy=ustruct.unpack(">h", data[10:12])[0]
        gz=ustruct.unpack(">h", data[12:14])[0]

        return [ax,ay,az],[gx,gy,gz],temp
    
    def get_data(self,calibrated=True):
        """获取处理后的传感器数据
        参数：
            calibrated: 是否进行校准
        返回：
            accel:三轴加速度 (单位:m/s²)
            gyro:三轴角速度 (单位:rad/s)
            temp:温度 (单位:°C)
        """
        #读取原始数据
        accel_raw,gyro_raw,temp_raw=self.read_raw()

        #应用校准
        if calibrated:
            for i in range(3):
                accel_raw[i]-=self.accel_bias[i]
                gyro_raw[i]-=self.gyro_bias[i]
        
        #单位转换
        accel=[x*9.80665/4096.0 for x in accel_raw]  #加速度转换为m/s²
        #gyro=[x*(1000.0/32.8)*(math.pi/180.0) for x in gyro_raw]  #角速度转换为rad/s
        gyro = [x / 32.8 * (math.pi / 180.0) for x in gyro_raw]
        temp=temp_raw/340.0+36.53  #温度转换为°C       

        return accel,gyro,temp