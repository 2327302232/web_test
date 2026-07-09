"""决策引擎模块"""

import math
import time
from collections import deque

class DecisionEngine:
    """事件检测与分类引擎"""

    #事件类型常量
    EVENT_NORMAL=0                   #正常骑行
    EVENT_ACCELERATION=1             #加速
    EVENT_BRAKING=2                  #刹车
    EVENT_TURNING=3                   #转弯
    EVENT_BUMP=4                      #颠簸
    EVENT_COLLISION_FRONT=5           #前碰撞
    EVENT_COLLISION_SIDE=6            #侧碰撞
    EVENT_COLLISION_REAR=7            #后碰撞
    EVENT_FALL=8                      #摔倒
    EVENT_SEVERE_FALL=9                #严重摔倒

    #报警级别常量
    ALERT_NONE=0                     #无报警
    ALERT_INFO=1                     #信息级报警
    ALERT_WARNING=2                  #警告级报警
    ALERT_URGENT=3                    #紧急级报警
    ALERT_SOS=4                      #求救

    #事件映射表
    EVENT_NAMES={
        EVENT_NORMAL:"正常骑行",
        EVENT_ACCELERATION:"加速",
        EVENT_BRAKING:"刹车",
        EVENT_TURNING:"转弯",
        EVENT_BUMP:"颠簸",
        EVENT_COLLISION_FRONT:"前碰撞",
        EVENT_COLLISION_SIDE:"侧碰撞",
        EVENT_COLLISION_REAR:"后碰撞",
        EVENT_FALL:"摔倒",
        EVENT_SEVERE_FALL:"严重摔倒"
    }

    #报警映射表
    ALERT_NAMES={
        ALERT_NONE:"无报警",
        ALERT_INFO:"信息提示",
        ALERT_WARNING:"警告",
        ALERT_URGENT:"紧急",
        ALERT_SOS:"求救"
    }

    def __init__(self,config):
        self.config=config
        self.jerk_noise_floor = getattr(config, 'JERK_NOISE_FLOOR', 15.0)

        # 防误报参数
        self.collision_confirm_frames = getattr(config, 'COLLISION_CONFIRM_FRAMES', 3)
        self.bump_to_collision_min_severity = getattr(config, 'BUMP_TO_COLLISION_MIN_SEVERITY', 4.2)
        self.low_confidence_suppress = getattr(config, 'LOW_CONFIDENCE_SUPPRESS', 0.68)
        self._collision_candidate_streak = 0

        #事件历史记录（用于连续事件检测和去抖动）
        self.event_history=deque([],config.EVENT_HISTORY_SIZE)

        #跌倒检测状态机
        self.fall_state={
            'start_time':None,       #跌倒开始时间
            'gyro_peak':0.0,         #跌倒过程中最大的角速度
            'svm_peak':0.0,          #跌倒过程中最大的合加速度
            'detection_phase':0,      #检测阶段：0=未检测，1=旋转阶段，2=冲击阶段，3=静止阶段
            'confirmed':False         #是否已确认跌倒事件
        }

        #事件状态机
        self.event_state={
            'current_event':self.EVENT_NORMAL,  #当前事件类型
            'start_time':0,             #当前事件开始时间
            'duration':0,               #当前事件持续时间
            'severity_history':deque([],5)#最近5次的严重度
        }

        #统计信息
        self.stats={
            'total_events':0,
            'collision_count':0,
            'fall_count':0,
            'last_alert_time':0,
        }

        #报警冷却时间（防止重复报警）
        self.alert_cooldown={
            'collision':0,
            'fall':0
        }


    def process(self,features,processed_data):
        """处理特征数据，进行事件检测和分类
        参数：
            features: 计算得到的特征向量
            processed_data: 预处理后的原始数据
        返回：
            事件结果字典、包含事件类型、严重度、置信度、报警级别等信息
        """
        #1.输入验证
        if features is None or processed_data is None:
            return self._create_result(self.EVENT_NORMAL,0.0,0.5,self.ALERT_NONE,'数据不足')
        
        #2.考量数据质量
        health_flag=features.get('health_flag',0)
        if health_flag>=2:  #警告或不可用
            #数据质量差，降低检测灵敏度
            return self._handle_low_quality_data(features)
        
        #3.多级事件检测流程
        event_result=self._cascade_detection(features,processed_data)

        #4.事件状态机更新
        self._update_event_state(event_result,features)

        #5.事件历史记录
        self._update_history(event_result)

        #6.统计信息更新
        self._update_statistics(event_result)

        return event_result
   
    def _cascade_detection(self,features,processed_data):
        """多级事件检测流程,五层决策树"""

        #第一层：冲击强度筛选
        if features['svm_peak']<self.config.ACCEL_SVM_THRESHOLD_LOW:
            self._collision_candidate_streak = 0
            return self._create_result(self.EVENT_NORMAL,0.0,0.9,self.ALERT_NONE,'冲击强度低于阈值')
        
        #第二层：主动/被动运动区分
        correlation=features.get('correlation',0.0)

        if correlation>self.config.CORRELATION_THRESHOLD:
            #高度相关，可能是主动运动
            self._collision_candidate_streak = 0
            event_type,severity,confidence=self._detect_active_event(features)
        else:
            #相关性低，可能是被动运动
            event_type,severity,confidence=self._detect_passive_event(features)

        # 对低置信/低严重度碰撞做降级，降低手持轻微动作误报
        if event_type in [self.EVENT_COLLISION_FRONT,self.EVENT_COLLISION_SIDE,self.EVENT_COLLISION_REAR]:
            if severity < self.bump_to_collision_min_severity or confidence < self.low_confidence_suppress:
                event_type = self.EVENT_BUMP
                confidence = min(confidence, 0.65)

        #第三层：跌倒检测（对碰撞事件进行跌倒检测）
        if event_type in [self.EVENT_COLLISION_FRONT,self.EVENT_COLLISION_SIDE,self.EVENT_COLLISION_REAR]:
            fall_result=self._detect_fall(features,processed_data)
            if fall_result['is_fall']:
                event_type=fall_result['fall_type']
                severity=fall_result['severity']
                confidence=fall_result['confidence']

        #第四层：警报级别确定
        alert_level=self._determine_alert_level(event_type,severity)

        #第五层：报警冷却检查
        if self._check_alert_cooldown(event_type,alert_level):
            alert_level=self.ALERT_NONE
            confidence *=0.7  #置信度降低，因为抑制了报警
        
        return self._create_result(event_type,severity,confidence,alert_level,self._get_event_description(event_type,severity))
    def _detect_active_event(self,features):
        """检测主动运动事件（加速、刹车、转弯）"""
        main_dir=features['main_direction']
        strength=features['direction_strength']

        #根据主方向和强度判断事件类型
        if main_dir ==0:  #前后方向
            if features['pulse_width']>self.config.PULSE_WIDTH_THRESHOLD:
                #较长脉冲：刹车
                event_type=self.EVENT_BRAKING
                confidence=0.8
            else:
                #短脉冲：加速
                event_type=self.EVENT_ACCELERATION
                confidence=0.7
        elif main_dir==1:  #左右方向
            #转弯
            event_type=self.EVENT_TURNING
            confidence=0.75
        else:  #Z轴主导或混合
            #可能是颠簸或其他非特定事件
            event_type=self.EVENT_BUMP
            confidence=0.6

        #计算严重度
        severity=self._calculate_severity(features,is_active=True)

        return event_type,severity,confidence
    

    def _detect_passive_event(self,features):
        """检测被动运动事件"""
        # 使用处理后的jerk值
        effective_jerk = self._get_effective_jerk(features)

        # 原始碰撞候选
        collision_candidate=(
            effective_jerk > self.config.JERK_COLLISION_THRESHOLD and
            features['pulse_width']<self.config.PULSE_WIDTH_COLLISION_MAX and
            features['pulse_width']>self.config.PULSE_WIDTH_COLLISION_MIN
        )

        # 连续帧确认（去抖）
        if collision_candidate:
            self._collision_candidate_streak += 1
        else:
            self._collision_candidate_streak = 0

        is_collision = self._collision_candidate_streak >= self.collision_confirm_frames
        
        if is_collision:
            #根据主方向判断碰撞类型
            main_dir=features['main_direction']
            if main_dir==0:
                event_type=self.EVENT_COLLISION_FRONT
            elif main_dir==1:
                event_type=self.EVENT_COLLISION_SIDE
            else:
                event_type=self.EVENT_COLLISION_REAR
            
            confidence=0.75
        else:
            #其他被动事件，暂时归为颠簸
            event_type=self.EVENT_BUMP
            confidence=0.6
            
        #计算严重度
        severity=self._calculate_severity(features,is_active=False)

        return event_type,severity,confidence
    def _detect_fall(self,features,processed_data):
        """检测跌倒事件，基于跌倒状态机"""
        current_time=time.ticks_ms()    
        fall_state=self.fall_state

        #第一阶段：旋转阶段
        if fall_state['detection_phase']==0:
            if features['gyro_mag_peak']>self.config.GYRO_FALL_THRESHOLD:
                fall_state['detection_phase']=1
                fall_state['start_time']=current_time
                fall_state['gyro_peak']=features['gyro_mag_peak']
                fall_state['svm_peak']=features['svm_peak']
                return{'is_fall':False,'fall_type':None,'severity':0.0,'confidence':0.0}
        
        #第二阶段：检测冲击和姿态异常
        elif fall_state['detection_phase']==1:
            time_since_start=(current_time-fall_state['start_time'])/1000.0  #转换为秒

            if time_since_start<self.config.FALL_DETECTION_TIMEOUT:
                #检查姿态角度
                roll_deg=abs(processed_data['euler'][0]*180.0/math.pi)
                pitch_deg=abs(processed_data['euler'][1]*180.0/math.pi)

                if roll_deg>self.config.ANGLE_FALL_THRESHOLD or pitch_deg>self.config.ANGLE_FALL_THRESHOLD:
                    fall_state['detection_phase']=2

            else:
                #超时未检测到姿态异常，重置状态机
                self._reset_fall_state()
                return {'is_fall': False, 'fall_type': None, 'severity': 0.0, 'confidence': 0.0}

        #第三阶段：检查持续静止
        elif fall_state['detection_phase']==2:
            time_since_start=(current_time-fall_state['start_time'])/1000.0  #转换为秒

            if time_since_start>self.config.STATIC_TIME_THRESHOLD:
                #检查是否持续静止
                if features['svm_peak']<self.config.STATIC_ACCEL_THRESHOLD and features['gyro_mag_peak']<self.config.STATIC_GYRO_THRESHOLD:
                    fall_state['detection_phase']=3
                    fall_state['confirmed']=True
                else:
                    #超时未确认跌倒，重置状态机
                    self._reset_fall_state()
                    return {'is_fall': False, 'fall_type': None, 'severity': 0.0, 'confidence': 0.0}

        #检查是否确认跌倒
        if fall_state['confirmed']:
            #根据碰撞类型判断跌倒类型
            if fall_state['gyro_peak']>self.config.SEVERE_GYRO_THRESHOLD and fall_state['svm_peak']>self.config.SEVERE_FALL_SVM_THRESHOLD:
                fall_type=self.EVENT_SEVERE_FALL
                severity=min(10.0,fall_state['svm_peak']+3.0)
            else:
                fall_type=self.EVENT_FALL
                severity=min(8.0,fall_state['svm_peak']+2.0)

            confidence=0.85
            result={'is_fall':True,'fall_type':fall_type,'severity':severity,'confidence':confidence}

            #重置状态
            self._reset_fall_state()

            return result
        
        return{'is_fall':False,'fall_type':None,'severity':0.0,'confidence':0.0}
    
    def _get_effective_jerk(self, features):
        """获取经过零偏处理的有效jerk值"""
        raw_jerk = features.get('jerk_peak', 0.0)
        return max(0.0, raw_jerk - self.jerk_noise_floor)
    
    def _calculate_severity(self,features,is_active=False):
        """计算事件严重度(0-10)"""
        severity=0.0

        # 使用处理后的jerk值
        effective_jerk = self._get_effective_jerk(features)

        
        if is_active:
            #主动事件严重度计算
            severity+=min(features['svm_peak']/5.0,2.0)   #加速度贡献分，最多2分
            severity+=min(features['gyro_mag_peak']/5.0,1.5)  #旋转贡献分，最多1.5分
            severity += min(effective_jerk / 100.0, 1.0)  #突然性贡献分，最多1分

            #方向集中度加分
            if features['direction_strength']>0.7:
                severity+=0.5

            #脉冲宽度判断
            if features['pulse_width']>200:    #长脉冲
                severity+=1.0
        else:
            #被动事件严重度计算
            severity+=min(features['svm_peak']/10.0,4.0)   #加速度贡献分，最多4分
            severity+=min(features['gyro_mag_peak']/25.0,3.0)  #旋转贡献分，最多3分
            severity += min(effective_jerk / 80.0, 2.0)  #突然性贡献分，最多2分

            #脉冲宽度判断
            if features['pulse_width']<50:    #很短脉冲，可能是碰撞
                severity+=1.5
            elif features['pulse_width']<100:  #短脉冲
                severity+=1.0

        #限制在0-10范围
        severity=max(0.0,min(10.0,severity))

        return round(severity,1)           
    

    def _determine_alert_level(self,event_type,severity):
        """根据事件类型和严重度确定报警级别"""
        if event_type ==self.EVENT_NORMAL:
            return self.ALERT_NONE
        
        elif event_type ==self.EVENT_BUMP:
            if severity>4.0:
                return self.ALERT_INFO
            return self.ALERT_NONE
        
        elif event_type in [self.EVENT_ACCELERATION,self.EVENT_BRAKING,self.EVENT_TURNING]:
            if severity>5.0:
                return self.ALERT_WARNING
            elif severity>3.0:
                return self.ALERT_INFO
            else:
                return self.ALERT_NONE
            
        elif event_type in [self.EVENT_COLLISION_FRONT,self.EVENT_COLLISION_SIDE,self.EVENT_COLLISION_REAR]:
            if severity>=8.0:
                return self.ALERT_SOS
            elif severity>=6.0:
                return self.ALERT_URGENT
            elif severity>=4.0:
                return self.ALERT_WARNING
            else:
                return self.ALERT_NONE
            
        elif event_type ==self.EVENT_FALL:
            return self.ALERT_SOS
        
        return self.ALERT_NONE
    def _check_alert_cooldown(self,event_type,alert_level):
        """检查报警冷却时间，防止重复报警"""
        current_time=time.ticks_ms()

        #只有较高等级的报警才需要冷却
        if alert_level < self.ALERT_WARNING:
            return False
        
        #碰撞报警冷却
        if event_type in [self.EVENT_COLLISION_FRONT,self.EVENT_COLLISION_SIDE,self.EVENT_COLLISION_REAR]:
            if current_time - self.alert_cooldown['collision']<self.config.COLLISION_COOLDOWN_MS:
                return True
            self.alert_cooldown['collision']=current_time
        
        #跌倒报警冷却
        elif event_type in [self.EVENT_FALL,self.EVENT_SEVERE_FALL]:
            if current_time - self.alert_cooldown['fall']<self.config.FALL_COOLDOWN_MS:
                return True
            self.alert_cooldown['fall']=current_time
            
        return False
    
    def _handle_low_quality_data(self,features):
        """处理数据质量差的情况，降低检测灵敏度"""
        #即使数据质量差，也检查是否有明显的危险
        if features['svm_peak']>15.0 or features['gyro_mag_peak']>8.0:
            #有很强的信号，即使数据质量差也报警
            return self._create_result(self.EVENT_COLLISION_FRONT,6.0,0.6,self.ALERT_WARNING,'数据质量差但检测到强烈冲击,方向不可靠')
        
        return self._create_result(self.EVENT_NORMAL,0.0,0.5,self.ALERT_NONE,'数据质量差，无法可靠检测')
    
    def _update_event_state(self,event_result,features):
        """更新事件状态机"""
        current_event=event_result['type']

        if current_event != self.event_state['current_event']:
            #事件变化
            self.event_state['current_event']=current_event
            self.event_state['start_time']=time.ticks_ms()
            self.event_state['duration']=0
        else:
            #事件持续
            self.event_state['duration']=(time.ticks_ms()-self.event_state['start_time'])/1000.0  #持续时间，单位秒

        #更新严重度历史
        self.event_state['severity_history'].append(event_result['severity'])

    def _update_history(self,event_result):
        """更新事件历史记录"""
        history_entry={
            'type':event_result['type'],
            'type_name':self.EVENT_NAMES.get(event_result['type'],'未知'),
            'severity':event_result['severity'],
            'confidence':event_result['confidence'],
            'alert_level':event_result['alert_level'],
            'alert_name':self.ALERT_NAMES.get(event_result['alert_level'],'未知'),
            'timestamp':event_result['timestamp'],
            'description':event_result.get('description','')
        }
        self.event_history.append(history_entry)

    def _update_statistics(self,event_result):
        """更新统计信息"""
        self.stats['total_events']+=1

        if event_result['type'] in [self.EVENT_COLLISION_FRONT,self.EVENT_COLLISION_SIDE,self.EVENT_COLLISION_REAR]:
            self.stats['collision_count']+=1
        
        if event_result['type'] in [self.EVENT_FALL,self.EVENT_SEVERE_FALL]:
            self.stats['fall_count']+=1
        
        if event_result['alert_level']>=self.ALERT_WARNING:
            self.stats['last_alert_time']=time.ticks_ms()
    
    def _reset_fall_state(self):
        """重置跌倒状态机"""
        self.fall_state={
            'start_time':None,
            'gyro_peak':0.0,
            'svm_peak':0.0,
            'detection_phase':0,
            'confirmed':False
        }
    
    def reset_all(self):
        """重置所有状态和统计信息"""
        self.reset_event_state()
        self.reset_statistics()
        self.reset_event_history()
        self._reset_fall_state()
        self._collision_candidate_streak = 0
        self.alert_cooldown={
            'collision':0,
            'fall':0
        }
        return {
            'status':'success',
            'message':'所有状态和统计信息已重置',
            'timestamp':time.ticks_ms()
        }

    def _create_result(self,event_type,severity,confidence,alert_level,description=''):
        """创建事件结果字典"""
        return {
            'type':event_type,
            'type_name':self.EVENT_NAMES.get(event_type,'未知'),
            'severity':severity,   #0-10
            'confidence':min(1.0,max(0.0,confidence)),  #0-1
            'alert_level':alert_level,
            'alert_name':self.ALERT_NAMES.get(alert_level,'未知'),
            'timestamp':time.ticks_ms(),
            'description':description
        }
    
    def _get_event_description(self,event_type,severity):
        """根据事件类型和严重度生成描述文本"""
        base_desc=self.EVENT_NAMES.get(event_type,'未知事件')

        if severity>=8.0:
            intensity='非常严重'
        elif severity>=6.0:
            intensity='严重'
        elif severity>=4.0:
            intensity='中等'
        elif severity>=2.0:
            intensity='轻微'
        else:
            intensity='极轻微'

        return f"{intensity}{base_desc}"
    
    def get_recent_history(self,count=5):
        """获取最近n条事件历史记录"""
        return list(self.event_history)[-count:]
    
    def get_statistics(self):
        """获取当前统计信息"""
        return self.stats.copy()
    
    def get_event_state(self):
        """获取当前事件状态"""
        return self.event_state.copy()
    
    def reset_statistics(self):
        """重置统计信息"""
        self.stats={
            'total_events':0,
            'collision_count':0,
            'fall_count':0,
            'last_alert_time':0,
        }
    
    def reset_event_history(self):
        """重置事件历史记录"""
        self.event_history.clear()

    def reset_event_state(self):
        """重置事件状态机"""
        self.event_state = {
            'current_event': self.EVENT_NORMAL,
            'start_time': 0,
            'duration': 0,
            'severity_history': deque([],5),
        }
    
    def reset_all(self):
        """重置所有状态和统计信息"""
        self.reset_event_state()
        self.reset_statistics()
        self.reset_event_history()
        self._reset_fall_state()
        self._collision_candidate_streak = 0
        self.alert_cooldown={
            'collision':0,
            'fall':0
        }
        return {
            'status':'success',
            'message':'所有状态和统计信息已重置',
            'timestamp':time.ticks_ms()
        }
