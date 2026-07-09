"""特征提取"""

import time
import math
from collections import deque

class FeatureExtractor:
    """实时特征提取"""

    def __init__(self,config):
        self.config=config

        #数据缓冲区
        self.accel_buffer=deque([],config.WINDOW_SIZE)
        self.gyro_buffer=deque([],config.WINDOW_SIZE)
        self.svm_buffer=deque([],config.WINDOW_SIZE)
        self.gyro_mag_buffer=deque([],config.WINDOW_SIZE)
        self.roll_buffer=deque([],config.WINDOW_SIZE)
        self.pitch_buffer=deque([],config.WINDOW_SIZE)
        self.time_buffer=deque([],config.WINDOW_SIZE)
        self.health_flag_buffer=deque([],config.WINDOW_SIZE)

        #特征窗口
        self.window_size=config.WINDOW_SIZE
        self.feature_window=config.FEATURE_WINDOW

        #增加统计变量
        self.svm_sum=0.0
        self.svm_sq_sum=0.0
        self.gyro_mag_sum=0.0
        self.gyro_mag_sq_sum=0.0

    def update_buffer(self,processed_data):
        """更新数据缓冲区"""
        #提取数据
        new_svm=processed_data.get('accel_svm',0.0)
        new_gyro_mag=processed_data.get('gyro_mag',0.0)

        #检查缓冲区是否满了
        if len(self.svm_buffer)==self.window_size:
            #移除旧数据
            old_svm=self.svm_buffer[0]
            old_gyro_mag=self.gyro_mag_buffer[0]

            #更新统计变量
            self.svm_sum-=old_svm
            self.svm_sq_sum-=old_svm**2
            self.gyro_mag_sum-=old_gyro_mag
            self.gyro_mag_sq_sum-=old_gyro_mag**2

        #添加新数据
        self.svm_sum+=new_svm
        self.svm_sq_sum+=new_svm**2
        self.gyro_mag_sum+=new_gyro_mag
        self.gyro_mag_sq_sum+=new_gyro_mag**2

        #更新缓冲区
        self.accel_buffer.append(processed_data['accel_motion'])
        self.gyro_buffer.append(processed_data['gyro_filtered'])
        self.svm_buffer.append(new_svm)
        self.gyro_mag_buffer.append(new_gyro_mag)
        self.roll_buffer.append(processed_data['euler'][0])
        self.pitch_buffer.append(processed_data['euler'][1])
        self.time_buffer.append(processed_data['timestamp'])
        self.health_flag_buffer.append(processed_data['health_flag'])
    def calculate_features(self):
        """计算特征向量"""
        if len(self.accel_buffer)<self.feature_window:
            return None  
        
        features={}
        
        #1.统计特征
        features['svm_peak'],features['svm_mean'],features['svm_var']=self._calc_stats(self.svm_buffer)
        features['gyro_mag_peak'],features['gyro_mag_mean'],features['gyro_mag_var']=self._calc_stats(self.gyro_mag_buffer)

        #2.运动学特征
        features['jerk_peak']=self._calc_jerk_peak()

        #3.时域特征
        features['pulse_width']=self._calc_pulse_width()
        features['zero_crossing']=self._calc_zero_crossing(0)  #x轴        

        #4.姿态特征
        features['pitch_rate'],features['roll_rate']=self._calc_attitude_rates()

        #5.方向特征
        features['main_direction'],features['direction_strength']=self._calc_main_direction()

        #6.相关性特征
        features['correlation']=self._calc_correlation()

        #7.数据质量特征
        features['health_flag']=self._get_latest_health_flag()

        #8时间戳
        features['timestamp']=self.time_buffer[-1] if self.time_buffer else 0

        return features
    
    def _calc_stats(self,data):
        """计算峰值、均值、方差"""
        if not data:
            return 0.0,0.0,0.0
        
        n=len(data)

        #使用增量统计进行计算
        if data is self.svm_buffer:
            mean=self.svm_sum/n
            var=(self.svm_sq_sum/n-mean**2) if n>1 else 0.0
            peak=max(data) if data else 0.0
        elif data is self.gyro_mag_buffer:
            mean=self.gyro_mag_sum/n
            var=(self.gyro_mag_sq_sum/n-mean**2) if n>1 else 0.0
            peak=max(data) if data else 0.0
        else:
            data_sum=sum(data)
            mean=data_sum/n
            var=sum((x-mean)**2 for x in data)/(n-1) if n>1 else 0.0
            peak=max(data) if data else 0.0

        return peak,mean,var
    
    
    def _calc_jerk_peak(self):
        """计算加速度冲击特征 """
        if len(self.accel_buffer) < 3:  # 至少需要3个点
            return 0.0
        
        jerk_peak = 0.0
        dt = 1.0 / self.config.SAMPLE_RATE
        
        # 将deque转换为list
        accel_list = list(self.accel_buffer)
        
        # 使用简单差分，避免中心差分在边界的问题
        for i in range(1, len(accel_list)):
            # 计算时间间隔（单位：秒）
            time_interval = dt  # 假设固定采样率
            
            # 计算jerk (m/s³) = Δa / Δt
            jerk_x = (accel_list[i][0] - accel_list[i-1][0]) / time_interval
            jerk_y = (accel_list[i][1] - accel_list[i-1][1]) / time_interval
            jerk_z = (accel_list[i][2] - accel_list[i-1][2]) / time_interval
            
            # 计算Jerk幅度
            jerk_mag = math.sqrt(jerk_x**2 + jerk_y**2 + jerk_z**2)
            
            # 过滤异常值
            if jerk_mag > 1000:  # 1000 m/s³ 是合理的上限
                continue
            
            if jerk_mag > jerk_peak:
                jerk_peak = jerk_mag
        
        return jerk_peak

    
    def _calc_pulse_width(self,threshold_ratio=0.5):
        """计算脉冲宽度"""
        if not self.svm_buffer:
            return 0.0
        
        #将deque转换为list以提高索引访问速度
        svm_list=list(self.svm_buffer)
        svm_mean=sum(svm_list)/len(svm_list)
        svm_max=max(svm_list)
        threshold=svm_mean+threshold_ratio*(svm_max-svm_mean)

        in_pulse=False
        pulse_start=0
        max_width=0

        for i,svm in enumerate(svm_list):
            if svm>threshold:
                if not in_pulse:
                    in_pulse=True
                    pulse_start=i
                width=i-pulse_start+1
                max_width=max(max_width,width)
            else:
                in_pulse=False

        return max_width*(1000/self.config.SAMPLE_RATE)  #转换为毫秒
    
    
    def _calc_zero_crossing(self,axis=0,deadzone=0.1):
        """带死区的过零率计算"""
        if len(self.accel_buffer)<2:
            return 0
        
        crossings=0
        accel_list=list(self.accel_buffer)

        for i in range(1,len(accel_list)):
            prev=accel_list[i-1][axis]
            curr=accel_list[i][axis]

            if (abs(prev)>deadzone and abs(curr)>deadzone):
                if (prev<0 and curr>0) or (prev>0 and curr<0):
                    crossings+=1
        
        return crossings/(len(accel_list)-1) if len(accel_list)>1 else 0.0
    
    def _calc_attitude_rates(self):
        """计算姿态变化率"""
        if len(self.roll_buffer)<2 or len(self.pitch_buffer)<2:
            return 0.0,0.0
        
        if len(self.time_buffer)>=2:
            dt=(self.time_buffer[-1]-self.time_buffer[0])/1000.0  #转换为秒
        else:
            dt=len(self.pitch_buffer)/self.config.SAMPLE_RATE  

        if dt<=0:
            return 0.0,0.0
        
        roll_rate=(self.roll_buffer[-1]-self.roll_buffer[0])/dt
        pitch_rate=(self.pitch_buffer[-1]-self.pitch_buffer[0])/dt

        return abs(roll_rate),abs(pitch_rate)
    
    def _calc_main_direction(self):
        """计算主方向特征"""
        if not self.accel_buffer:
            return 0,0.0
        
        contributions=[0.0,0.0,0.0]
        accel_list=list(self.accel_buffer)

        for accel in accel_list:
            for i in range(3):
                contributions[i]+=abs(accel[i])

        total=sum(contributions)
        if total>0:
            contributions=[c/total for c in contributions]

        #找到贡献最大的方向
        max_contribution=max(contributions)
        main_dir=contributions.index(max_contribution)
        strength=contributions[main_dir]

        return main_dir,strength
    
    def _calc_correlation(self):
        """计算加速度-姿态相关性特征"""
        if len(self.accel_buffer)<2 or len(self.gyro_buffer)<2:
            return 0.0
        
        accel_list=list(self.accel_buffer)
        pitch_list=list(self.pitch_buffer)

        accel_x=[accel[0] for accel in accel_list]

        #均值
        mean_accel_x=sum(accel_x)/len(accel_x)
        mean_pitch=sum(pitch_list)/len(pitch_list)

        #计算协方差和标准差
        cov=sum((a-mean_accel_x)*(p-mean_pitch) for a,p in zip(accel_x,pitch_list))
        std_accel=math.sqrt(sum((a-mean_accel_x)**2 for a in accel_x))
        std_pitch=math.sqrt(sum((p-mean_pitch)**2 for p in pitch_list))

        if std_accel>0 and std_pitch>0:
            return cov/(std_accel*std_pitch)
        
        return 0.0
    
    def _get_latest_health_flag(self):
        """获取最新的健康状态标志"""
        if not self.health_flag_buffer:
            return 0
        
        return self.health_flag_buffer[-1]
    
    def reset_buffers(self):
        """重置所有缓冲区和统计变量"""
        self.accel_buffer.clear()
        self.gyro_buffer.clear()
        self.svm_buffer.clear()
        self.gyro_mag_buffer.clear()
        self.roll_buffer.clear()
        self.pitch_buffer.clear()
        self.time_buffer.clear()
        self.health_flag_buffer.clear()

        self.svm_sum=0.0
        self.svm_sq_sum=0.0
        self.gyro_mag_sum=0.0
        self.gyro_mag_sq_sum=0.0