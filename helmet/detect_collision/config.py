class Config:
    """系统配置参数"""

    #============MPU6050配置=============
    #寄存器地址
    MPU6050_ADDR=0x68

    #采样率配置
    SAMPLE_RATE=200
    SAMPLE_DIV=4       #分配系数：1000/（1+4）

    #测量范围配置
    ACCEL_FS_SEL=0x10  #±8g
    GYRO_FS_SEL=0x18   #±1000°/s

    #数字低通滤波器
    DLPF_CFG=0x03     #加速度44Hz，陀螺仪42Hz

    #校准参数
    CALIBRATION_SAMPLES=1000  #校准时采集的样本数量

    #单位转换系数
    ACCEL_SCALE=9.80665/4096.0  #加速度计的单位转换系数，±8g对应的分辨率为4096 LSB/g
    GYRO_SCALE =(1000.0/32.8) *(3.14159/180.0   )  #陀螺仪的单位转换系数，±1000°/s对应的分辨率为32768 LSB/(°/s)

    #============数据处理参数=============
    #滤波参数
    ACCEL_LPF_CUTOFF=20.0  #Hz
    GYRO_LPF_CUTOFF=20.0   #Hz

    #运动状态检测阈值
    MOTION_HIGH_DYNAMIC_ACCEL_THRESHOLD=2.0    #单位：m/s^2 合加速度超过此值视为高动态
    MOTION_HIGH_DYNAMIC_GYRO_THRESHOLD=3.0     #单位：rad/s 角速度超过此值视为高动态

    #自适应滤波参数
    ALPHA_NORMAL=0.02         #正常运动时的融合系数
    ALPHA_HIGH_DYNAMIC=0.005  #高动态运动时的融合系数

    #============特征处理配置参数=============
     # 缓冲区与窗口配置
    WINDOW_SIZE = 50           # 数据缓冲区大小 
    FEATURE_WINDOW = 25       # 计算特征所需的最小窗口大小 

    #============决策引擎参数=============
    # 事件历史配置
    EVENT_HISTORY_SIZE = 20  # 事件历史记录最大长度

    # 第一级检测阈值
    ACCEL_SVM_THRESHOLD_LOW =3.5 #2.0  # 合加速度低阈值 (m/s²)

    # 第二级检测阈值
    CORRELATION_THRESHOLD =0.45# 0.6  # 相关系数阈值

    # 主动事件检测阈值
    PULSE_WIDTH_THRESHOLD = 100.0  # 刹车脉冲宽度阈值 (ms)

    # 被动事件检测阈值
    JERK_COLLISION_THRESHOLD =180.0 #100.0  # 碰撞Jerk阈值 (m/s³)
    PULSE_WIDTH_COLLISION_MAX =70.0 #100.0  # 碰撞最大脉冲宽度 (ms)
    PULSE_WIDTH_COLLISION_MIN =12.0 #10.0   # 碰撞最小脉冲宽度 (ms)

    # 跌倒检测阈值
    GYRO_FALL_THRESHOLD = 0.0872665                     # 约 5°/s -> 0.087 rad/s
    FALL_DETECTION_TIMEOUT = 2.0   # 跌倒检测超时 (s)
    ANGLE_FALL_THRESHOLD = 45.0    # 跌倒角度阈值 (°)
    STATIC_TIME_THRESHOLD = 3.0    # 静止时间阈值 (s)
    STATIC_ACCEL_THRESHOLD = 0.5   # 静止加速度阈值 (m/s²)
    STATIC_GYRO_THRESHOLD = 0.00872665                  # 约 0.5°/s -> 0.0087 rad/s
    SEVERE_GYRO_THRESHOLD = 0.1396263                   # 约 8°/s -> 0.140 rad/s
    SEVERE_FALL_SVM_THRESHOLD = 5.0 # 严重跌倒合加速度阈值 (m/s²)     
    SEVERITY_HIGH = 7.0           # 高严重度阈值
    # 报警冷却时间
    COLLISION_COOLDOWN_MS = 5000   # 碰撞报警冷却时间 (ms)
    FALL_COOLDOWN_MS = 10000       # 跌倒报警冷却时间 (ms)

    JERK_NOISE_FLOOR = 15.0  # Jerk零偏阈值，单位m/s³

    #============调试参数=============
    # ===== 频率解耦 =====
    SENSOR_RATE_HZ =100        # IMU读取频率
    ALGO_RATE_HZ =20           # 算法处理频率
    UPLOAD_RATE_HZ =8          # 常态上传频率

    # ===== 发送策略 =====
    TX_QUEUE_MAX =16
    TX_BUDGET_PER_LOOP =1
    TX_GUARD_MS = 10
    TX_FORCE_WATERMARK =8  
    MAX_CATCHUP_CYCLES =1

    # ===== 告警抑制（降低误报）=====
    ALERT_MIN_SEV = 4.2
    ALERT_MIN_CONF = 0.65
    ALERT_CONSEC_FRAMES = 2            # 连续2帧满足才出告警
    EVENT_UPLOAD_BURST_MS = 1500       # 事件后1.5秒内提高上传密度

    # ===== 预热 =====
    WARMUP_SECONDS = 8
    UPLOAD_PROCESSED_DEBUG = False

    
    MQTT_RETRY_INTERVAL_MS = 15000
    MQTT_MIN_FREE_MEM = 25000
    CONNECT_FIRST_WINDOW_MS =5000 
    MQTT_RESERVE_BYTES = 8192


    TIME_VALID_YEAR = 2024
    TIME_GATE_MS =180000

    MQTT_STARTUP_DELAY_MS =1000 
    MQTT_RETRY_MAX_MS = 120000
    


