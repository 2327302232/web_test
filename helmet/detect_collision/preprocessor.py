"""
数据预处理模块
"""

import math
import time

class DataPreprocessor:
    """数据预处理类"""

    def __init__(self, config):
        self.config = config
        self.dt=1.0/self.config.SAMPLE_RATE

        #滤波器状态
        self.accel_filter_state=[[0.0,0.0] for _ in range(3)]  #每轴的滤波器状态
        self.gyro_filter_state=[[0.0,0.0] for _ in range(3)]

        #互补滤波器的状态
        self.q0,self.q1,self.q2,self.q3=1.0,0.0,0.0,0.0  #初始姿态为水平

        #重力常数
        self.g=9.80665

        # 用于存储最近的重力估计值
        self.gravity_history = []
   
    def _iir_filter(self, x, state, cutoff_freq):
        """
        二阶Butterworth低通滤波器 (直接II型)
        使用双线性变换设计，更稳定
        """
        # 如果截止频率高于采样率的一半，强制设置为尼奎斯特频率
        if cutoff_freq <= 0 or cutoff_freq >= self.config.SAMPLE_RATE / 2:
            # 直接返回输入，不滤波
            return x, state
        
        # 计算滤波器系数 (使用双线性变换的预畸变)
        T = self.dt
        w0 = 2.0 * math.pi * cutoff_freq
        warped = 2.0 / T * math.tan(w0 * T / 2.0)  # 频率预畸变
        
        # 二阶Butterworth低通滤波器系数
        alpha = 1.0 / (1.0 + math.sqrt(2) * T * warped / 2.0 + (T * warped / 2.0) ** 2)
        
        b0 = alpha
        b1 = 2.0 * alpha
        b2 = alpha
        
        a1 = 2.0 * alpha * (1.0 - (T * warped / 2.0) ** 2)
        a2 = alpha * (1.0 - math.sqrt(2) * T * warped / 2.0 + (T * warped / 2.0) ** 2)
        
        # 确保状态存在且长度为2
        if len(state) < 2:
            state = [0.0, 0.0]
        
        w1, w2 = state[0], state[1]
        
        # 计算滤波器输出
        w_new = x - a1 * w1 - a2 * w2
        y = b0 * w_new + b1 * w1 + b2 * w2
        
        # 更新状态
        new_state = [w_new, w1]
        
        return y, new_state
    
    def complementary_filter(self,accel,gyro):
        """
        互补滤波器融合加速度计和陀螺仪数据

        参数：
            accel:加速度计数据 [ax,ay,az] 单位:m/s^2
            gyro:陀螺仪数据 [gx,gy,gz] 单位:rad/s
        """
        
        q0,q1,q2,q3=self.q0,self.q1,self.q2,self.q3
        gx,gy,gz=gyro[0],gyro[1],gyro[2]

        #运动状态检测
        accel_norm=math.sqrt(accel[0]**2+accel[1]**2+accel[2]**2)
        gyro_norm=math.sqrt(gx**2+gy**2+gz**2)

        is_high_dynamic=(abs(accel_norm-9.80665)>self.config.MOTION_HIGH_DYNAMIC_ACCEL_THRESHOLD) or (gyro_norm>self.config.MOTION_HIGH_DYNAMIC_GYRO_THRESHOLD  )
        #自适应选择融合参数
        current_alpha=self.config.ALPHA_HIGH_DYNAMIC if is_high_dynamic else self.config.ALPHA_NORMAL

        #陀螺仪积分预测
        q0_pred=q0+(-q1*gx-q2*gy-q3*gz)*self.dt/2.0
        q1_pred=q1+(q0*gx-q3*gy+q2*gz)*self.dt/2.0
        q2_pred=q2+(q3*gx+q0*gy-q1*gz)*self.dt/2.0
        q3_pred=q3+(-q2*gx+q1*gy+q0*gz)*self.dt/2.0

        #加速度计修正
        norm=math.sqrt(accel[0]**2+accel[1]**2+accel[2]**2)
        if norm>0.1:
            ax,ay,az=accel[0]/norm,accel[1]/norm,accel[2]/norm

            #估计重力方向
            gx_pred=2.0*(q1_pred*q3_pred-q0_pred*q2_pred)
            gy_pred=2.0*(q0_pred*q1_pred+q2_pred*q3_pred)
            gz_pred=q0_pred**2-q1_pred**2-q2_pred**2+q3_pred**2

            #计算误差
            ex=(ay*gz_pred-az*gy_pred)
            ey=(az*gx_pred-ax*gz_pred)
            ez=(ax*gy_pred-ay*gx_pred)

            #修正陀螺仪读数
            gx += ex*current_alpha
            gy += ey*current_alpha
            gz += ez*current_alpha

            #重新积分
            self.q0=q0+(-q1*gx-q2*gy-q3*gz)*self.dt/2.0
            self.q1=q1+(q0*gx-q3*gy+q2*gz)*self.dt/2.0
            self.q2=q2+(q3*gx+q0*gy-q1*gz)*self.dt/2.0
            self.q3=q3+(-q2*gx+q1*gy+q0*gz)*self.dt/2.0
        else:
            self.q0,self.q1,self.q2,self.q3=q0_pred,q1_pred,q2_pred,q3_pred

            #归一化四元数
        norm_q=math.sqrt(self.q0**2+self.q1**2+self.q2**2+self.q3**2)
        if norm_q>0.0:
            self.q0/=norm_q
            self.q1/=norm_q 
            self.q2/=norm_q
            self.q3/=norm_q

        #计算欧拉角
        roll,pitch,yaw=self._quaternion_to_euler(self.q0,self.q1,self.q2,self.q3)
        return [self.q0,self.q1,self.q2,self.q3,roll,pitch,yaw]
    
    def _quaternion_to_euler(self,q0,q1,q2,q3):
        """
        将四元数转换为欧拉角

        参数：
            q0,q1,q2,q3:四元数
        返回：
            roll,pitch,yaw:欧拉角
        """
        #横滚角
        sinr_cosp=2.0*(q0*q1+q2*q3)
        cosr_cosp=1.0-2.0*(q1*q1+q2*q2)
        roll=math.atan2(sinr_cosp,cosr_cosp)

        #俯仰角
        sinp=2.0*(q0*q2-q3*q1)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)  # 正负90度
        else:
            pitch = math.asin(sinp)

        #偏航角
        siny_cosp=2.0*(q0*q3+q1*q2)
        cosy_cosp=1.0-2.0*(q2*q2+q3*q3)
        yaw=math.atan2(siny_cosp,cosy_cosp)
        return roll,pitch,yaw
    
    def remove_gravity(self,accel,quaternion,is_high_dynamic,quat_confidence=1.0):
        """
        去除重力分量

        参数：
            accel:加速度计数据 [ax,ay,az] 单位:m/s^2
            quaternion:当前姿态四元数 [q0,q1,q2,q3]
            is_high_dynamic:是否处于高动态运动状态
            quat_confidence:四元数的置信度(0.0-1.0)，用于高动态时的加权融合
        返回：
            (accel_motion,health_flag)
            accel_motion:去除重力的加速度 
            health_flag:数据健康标志(0:优秀,1:良好,2:警告,3:不可用)
        """
        q0,q1,q2,q3=quaternion

        #---1.输入有效性检查---
        #如果quat_confidence为0，表示姿态完全不可信
        if quat_confidence<=0.0:
            return accel,3
        
        #检查四元数是否近似为单位四元数
        norm_q_sq=q0**2+q1**2+q2**2+q3**2
        if abs(norm_q_sq-1.0)>0.1:
            if quat_confidence<0.3:
                return accel,3  #四元数异常且置信度低，数据不可用
            else:
                #尝试归一化
                norm_q=math.sqrt(norm_q_sq)
                q0,q1,q2,q3=q0/norm_q,q1/norm_q,q2/norm_q,q3/norm_q

        #---2.计算重力分量---
        gx=2.0*(q1*q3-q0*q2)*self.g
        gy=2.0*(q0*q1+q2*q3)*self.g
        gz=(q0**2-q1**2-q2**2+q3**2)*self.g

        self.gravity_history.append([gx,gy,gz])
        if len(self.gravity_history)>=5:
            self.gravity_history.pop(0)

        #如果姿态置信度低，对重力分量进行平滑
        if quat_confidence<0.5 and len(self.gravity_history)>0:

                #计算历史平均值
            gx_avg=sum(g[0] for g in self.gravity_history)/len(self.gravity_history)
            gy_avg=sum(g[1] for g in self.gravity_history)/len(self.gravity_history)
            gz_avg=sum(g[2] for g in self.gravity_history)/len(self.gravity_history)
                
            #根据置信度混合当前值和历史值
            alpha=quat_confidence  #置信度越高，当前值权重越大
            gx=alpha*gx+(1.0-alpha)*gx_avg
            gy=alpha*gy+(1.0-alpha)*gy_avg
            gz=alpha*gz+(1.0-alpha)*gz_avg
        
        #---3.鲁棒性重力扣除策略---
        #计算合加速度，用于判断运动强度
        accel_norm=math.sqrt(accel[0]**2+accel[1]**2+accel[2]**2)
        motion_intensity=abs(accel_norm-self.g)  #偏离重力的程度

        #策略A：理想情况（静态/低速，姿态高可信）
        if not is_high_dynamic and quat_confidence>0.8 and motion_intensity<1.0:
            ax_motion=accel[0]-gx
            ay_motion=accel[1]-gy
            az_motion=accel[2]-gz
            health_flag=0  #优秀
        
        #策略B：高动态或低置信度，但任有必要处理
        elif is_high_dynamic or quat_confidence<0.5:
            ax_raw=accel[0]-gx
            ay_raw=accel[1]-gy
            az_raw=accel[2]-gz

            #根据置信度和运动强度调整限幅阈值
            #置信度越低，限幅越严格，避免异常值
            base_limit=20.0  #基础限幅阈值 20m/s^2
            confidence_factor=0.5+quat_confidence  #0.5~1.5
            dynamic_factor=1.0 if not is_high_dynamic else 1.5
            limit=base_limit*confidence_factor*dynamic_factor

            #应用软限幅
            ax_motion=max(-limit,min(limit,ax_raw))
            ay_motion=max(-limit,min(limit,ay_raw))
            az_motion=max(-limit,min(limit,az_raw))

            #如果运动强度很大且置信度很低，标记为警告
            if motion_intensity>5.0 and quat_confidence<0.3:
                health_flag=2  #警告
            else:
                health_flag=1  #良好
        
        #策略C：默认情况
        else:
            ax_motion=accel[0]-gx
            ay_motion=accel[1]-gy
            az_motion=accel[2]-gz

            #根据可信度决定健康程度
            if quat_confidence>0.6:
                health_flag=1  #良好
            else:
                health_flag=2  #警告
        
        #---4.后处理验证---
        motion_norm=math.sqrt(ax_motion**2+ay_motion**2+az_motion**2)

        #如果结果看起来不合理，调整健康度
        if motion_norm>30.0:   #超过3g的运动加速度，通常不合理
            health_flag=max(health_flag,2)  #至少标记为警告
        
        #如果四元数置信度极低，但结果看起来合理，可能置信度估计有误
        if quat_confidence<0.2 and motion_norm<5.0 and not is_high_dynamic:
            pass  #保持当前健康度，不做过度惩罚

        return [ax_motion,ay_motion,az_motion],health_flag
    
    def estimate_quaternion_confidence(self,accel,gyro,quaternion,dt):
        q0,q1,q2,q3=quaternion

        #1.重力匹配度（权重40%）
        #计算估计的重力向量
        gx=2.0*(q1*q3-q0*q2)*self.g
        gy=2.0*(q0*q1+q2*q3)*self.g
        gz=(q0**2-q1**2-q2**2+q3**2)*self.g

        #计算测量值与估计值的差异
        gravity_error=math.sqrt((accel[0]-gx)**2+(accel[1]-gy)**2+(accel[2]-gz)**2)
        #归一化误差：理想情况应为0
        #误差在0~5 m/s^2之间映射到1-0
        gravity_match=max(0.0,1.0-gravity_error/5.0)

        #2.陀螺仪稳定性（权重30%）
        gyro_norm=math.sqrt(gyro[0]**2+gyro[1]**2+gyro[2]**2)
        #角速度越小，置信度越高
        gyro_stability=max(0.0,1.0-gyro_norm/5.0) #5 rad/s为阈值

        #3.姿态变化连续性（权重30%）
        if not hasattr(self,'last_quaternion'):
            self.last_quaternion=quaternion
            self.last_time=time.ticks_ms()
            change_rate=0.0
        else:
            #计算四元数变化（用点积计算角度差）
            q_last=self.last_quaternion
            dot_product=q0*q_last[0]+q1*q_last[1]+q2*q_last[2]+q3*q_last[3]

            #确保在[-1,1]范围内
            dot_product=max(-1.0,min(1.0,dot_product))
            angle_change=2.0*math.acos(abs(dot_product))  #角度变化，单位：弧度

            #计算时间差
            current_time=time.ticks_ms()
            time_diff=(current_time-self.last_time)/1000.0  #秒

            if time_diff>0.0:  #避免除零错误
                change_rate=angle_change/time_diff  #角速度，单位：弧度/秒
            else:
                change_rate=0.0
            #更新状态
            self.last_quaternion=quaternion
            self.last_time=current_time
        
        #变化率越小，置信度越高
        #假设正常运动下角度变化率不超过2 rad/s
        continuity=max(0.0,1.0-change_rate/2.0)

        #4.综合置信度
        confidence=(0.4*gravity_match+0.3*gyro_stability+0.3*continuity)
        #限制在0.0-1.0范围内
        confidence=max(0.0,min(1.0,confidence))
        return confidence
    
    def preprocess_data(self,accel_raw,gyro_raw):
        """
        预处理加速度计和陀螺仪数据

        参数：
            accel_raw:原始加速度计数据 [ax,ay,az] 单位：m/s^2
            gyro_raw:原始陀螺仪数据 [gx,gy,gz] 单位：rad/s
        返回：
            processed_data:字典，包含所有处理结果
        """
        #1.应用低通滤波
        accel_filtered=[0.0,0.0,0.0]
        gyro_filtered=[0.0,0.0,0.0]

        for i in range(3):
            #加速度计滤波
            accel_filtered[i],self.accel_filter_state[i]=self._iir_filter(accel_raw[i]
                                                                          ,self.accel_filter_state[i]
                                                                          ,self.config.ACCEL_LPF_CUTOFF)
            
            #陀螺仪滤波
            gyro_filtered[i],self.gyro_filter_state[i]=self._iir_filter(gyro_raw[i]
                                                                        ,self.gyro_filter_state[i]
                                                                        ,self.config.GYRO_LPF_CUTOFF)
            
        #2.计算运动状态检测
        accel_norm=math.sqrt(accel_filtered[0]**2+accel_filtered[1]**2+accel_filtered[2]**2)
        gyro_norm=math.sqrt(gyro_filtered[0]**2+gyro_filtered[1]**2+gyro_filtered[2]**2)

        is_high_dynamic=(abs(accel_norm-9.80665)>self.config.MOTION_HIGH_DYNAMIC_ACCEL_THRESHOLD) or (gyro_norm>self.config.MOTION_HIGH_DYNAMIC_GYRO_THRESHOLD  )

        #3.姿态解算(使用互补滤波器)
        attitude_result=self.complementary_filter(accel_filtered,gyro_filtered)

        #complementary_filter返回值：[q0,q1,q2,q3,roll,pitch,yaw]
        quaternion=attitude_result[0:4]
        euler_angles=attitude_result[4:7]

        #4.估计姿态置信度
        quat_confidence=self.estimate_quaternion_confidence(accel_filtered,gyro_filtered,quaternion,self.dt)

        #5.去除重力分量
        accel_motion,health_flag=self.remove_gravity(accel_filtered,quaternion,is_high_dynamic,quat_confidence)

        #6.计算合加速度和合角速度
        svm=math.sqrt(accel_motion[0]**2+accel_motion[1]**2+accel_motion[2]**2)
        gyro_mag=math.sqrt(gyro_filtered[0]**2+gyro_filtered[1]**2+gyro_filtered[2]**2)

        #7.构建处理结果字典
        processed_data={
            #原始数据
            'accel_raw':accel_raw,
            'gyro_raw':gyro_raw,

            #滤波后数据
            'accel_filtered':accel_filtered,
            'gyro_filtered':gyro_filtered,

            #姿态信息
            'quaternion':quaternion,
            'euler':euler_angles,

            #去除重力后的运动加速度
            'accel_motion':accel_motion,

            #状态和置信度
            'is_high_dynamic':is_high_dynamic,
            'quat_confidence':quat_confidence,
            'health_flag':health_flag,

            #特征值
            'accel_svm':svm,
            'gyro_mag':gyro_mag,

            #时间信息
            'timestamp':time.ticks_ms(),
            'dt':self.dt

        }
        return processed_data


