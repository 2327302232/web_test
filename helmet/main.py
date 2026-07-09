"""智能头盔主程序
"""
import time
import gc
import _thread

from at_port import at_lock

# ── 全局状态 ──
low_power = False       # 低功耗模式标志
running = True          # 全局运行标志
uploader = None         # MQTT上传器
voice_svc = None        # 语音服务
gnss_mod = None         # GNSS模块引用
buttons = None          # 按键服务
light_voice_off = False # 语音关灯标志（True=用户语音关了灯）


def enter_low_power():
    """进入低功耗模式:关闭传感器和GNSS,保留碰撞检测和语音识别"""
    global low_power
    if low_power:
        return
    low_power = True
    uploader.set_low_power_mode(True)
    voice_svc.set_low_power(True)
    try:
        voice_svc.cmd_processor._low_power_mode = True
    except Exception:
        pass
    # 关闭传感器电源（心率MAX3010x、温湿度AHT20、电池MAX17049）
    try:
        packager.power_down_sensors()
    except Exception:
        pass
    if gnss_mod:
        gnss_mod.stop()
    # 关灯（低功耗模式不亮灯）
    try:
        light_lib.set_brightness(0)
    except Exception:
        pass
    gc.collect()
    try:
        voice_svc.voice_sys.speak("已进入低功耗模式", interrupt=False, wait_for_complete=False)
    except Exception:
        pass


def exit_low_power():
    """退出低功耗模式:恢复所有传感器和GNSS"""
    global low_power
    if not low_power:
        return
    low_power = False
    uploader.set_low_power_mode(False)
    voice_svc.set_low_power(False)
    try:
        voice_svc.cmd_processor._low_power_mode = False
    except Exception:
        pass
    # 重新上电传感器（心率、温湿度、电池）
    try:
        packager.power_up_sensors()
    except Exception:
        pass
    if gnss_mod:
        gnss_mod.start()
    # 恢复灯（如果用户没有语音关掉灯）
    if not light_voice_off:
        try:
            light_lib.update()
        except Exception:
            pass
    gc.collect()
    try:
        voice_svc.voice_sys.speak("已切换至正常模式", interrupt=False, wait_for_complete=False)
    except Exception:
        pass


def on_voice_light_on():
    """语音开灯回调"""
    global light_voice_off
    light_voice_off = False
    light_lib.update()


def on_voice_light_off():
    """语音关灯回调"""
    global light_voice_off
    light_voice_off = True
    light_lib.set_brightness(0)


def on_collision(evt):
    """碰撞/SOS事件回调：启动GNSS并标记报警模式"""
    # 低功耗下需要临时启动GNSS
    if low_power:
        if gnss_mod:
            gnss_mod.start()
    # 标记报警活跃（低功耗下恢复发送，正常模式下也标记事件）
    uploader._low_power_alert_active = True
    uploader._last_event = evt.get("event", "collision") if evt else "collision"


def on_sos():
    """SOS一键报警:仅上传报警信息+位置，不触发本地报警音"""
    if voice_svc.system_state.trigger_collision():
        on_collision({"event": "sos"})


def on_sos_cancel():
    """SOS键长按3秒取消SOS报警"""
    uploader.clear_alert()
    if low_power and gnss_mod:
        gnss_mod.stop()
        gc.collect()


def on_stop_alarm():
    """电源键长按3秒停止报警(碰撞/跌倒报警）"""
    uploader.clear_alert()
    voice_svc.system_state.stop_alert_thread()
    if low_power and gnss_mod:
        gnss_mod.stop()
        gc.collect()


# ── 后台线程函数 ──

def upload_loop():
    """MQTT上传线程:直接开始连接,不再等待"""
    gc.collect()
    try:
        uploader.run_forever()
    except Exception:
        pass
    # run_forever退出后清理
    try:
        uploader._close_mqtt()
    except Exception:
        pass


def voice_loop():
    """语音服务线程：处理语音识别和播报"""
    time.sleep(2)
    gc.collect()
    while running:
        try:
            voice_svc._running = True
            voice_svc._voice_main_loop()
        except Exception:
            pass
        gc.collect()
        if running:
            time.sleep(2)


# ═══════════════════════════════════════
# 初始化流程（按内存消耗从小到大）
# ═══════════════════════════════════════

# 第1步：传感器（心率、温湿度、GNSS位置、IMU）
gc.collect()
from sensor.data_packager import DataPackager
packager = DataPackager()
gc.collect()
time.sleep(2)

# 第2步：碰撞检测器（MPU6050校准+算法初始化，趁内存最多时做）
gc.collect()
packager.event_detector._init_runtime_if_needed()
collision_ready = packager.event_detector.is_ready()
gc.collect()
time.sleep(1)

# 第3步：MQTT上传器（只创建对象，不立即连接）
gc.collect()
from mqtt_uploader import MqttUploader
uploader = MqttUploader(debug=False, mqtt_port=8883, packager=packager)
gc.collect()
time.sleep(1)

# 第3.5步：灯光模块
gc.collect()
import light_lib
light_lib.init()
light_lib.update()  # 开机自动启动灯（自动调节，白天不亮晚上亮）
gc.collect()

# 第4步：语音系统（音频+语音识别+指令处理）
gc.collect()
from voice.voice_service import VoiceService
voice_svc = VoiceService(
    packager=packager,
    low_power_callback=enter_low_power,
    normal_mode_callback=exit_low_power,
    on_collision=on_collision,
    light_on_callback=on_voice_light_on,
    light_off_callback=on_voice_light_off,
)
gc.collect()
time.sleep(2)

# 第5步：按键（PA3=电源键，PC0=SOS键）
gc.collect()
from key import ButtonService
buttons = ButtonService(
    on_enter_low_power=enter_low_power,
    on_exit_low_power=exit_low_power,
    on_stop_alarm=on_stop_alarm,
    on_sos=on_sos,
    on_sos_cancel=on_sos_cancel,
)
gc.collect()
time.sleep(1)

# 第6步：GNSS引用（data_packager导入时已自动启动）
gnss_mod = None
try:
    from sensor.gnss import gnss_module as _gnss
    gnss_mod = _gnss
except Exception:
    pass
gc.collect()

# 第7步：先播报"头盔已启动"（此时AT口完全空闲，MQTT还没启动）
gc.collect()
try:
    voice_svc.voice_sys.speak("头盔已启动", wait_for_complete=True)
except Exception:
    pass
gc.collect()

# 第8步：播报完成后再启动MQTT上传线程（MQTT连接会占用AT口）
old_stack = _thread.stack_size()
_thread.stack_size(8192)
_thread.start_new_thread(upload_loop, ())
gc.collect()

# 等MQTT连接后再启动语音服务线程
time.sleep(20)
gc.collect()
_thread.start_new_thread(voice_loop, ())
gc.collect()
_thread.stack_size(old_stack)

# ═══════════════════════════════════════
# 主循环：按键轮询 + 碰撞检测（50ms间隔）
# ═══════════════════════════════════════
gc_counter = 0
lbs_check_counter = 0  # 每3秒轮询位置源（manage_location_source内部控制实际间隔）
try:
    while True:
        # 轮询按键状态（短按切换低功耗，长按停止报警）
        buttons.update()

        # 非阻塞碰撞检测
        if collision_ready:
            evt = packager.event_detector.check_once()
            if evt and evt.get("event") in ("collision", "fall"):
                if voice_svc.system_state.trigger_collision():
                    on_collision(evt)
                    voice_svc.cmd_processor.start_collision_alert()

        # 自动调光（非低功耗且用户没有语音关灯时）
        if not low_power and not light_voice_off:
            try:
                light_lib.update()
            except Exception:
                pass

        # 网站下发的省电命令（通过MQTT power/set）
        wp = uploader.pop_web_power_pending()
        if wp is not None:
            target_lp, cmd_id = wp
            if target_lp:
                enter_low_power()
            else:
                exit_low_power()
            uploader.set_web_power_ack(cmd_id, target_lp)

        # 每10秒检查一次GNSS→LBS位置源（不放在热路径中）
        lbs_check_counter += 1
        if lbs_check_counter >= 60:  # 60 * 50ms = 3s
            lbs_check_counter = 0
            try:
                packager.manage_location_source()
            except Exception:
                pass

        # 智能GC：只在AT口空闲时执行，不会打断正在进行中的AT指令
        gc_counter += 1
        if gc_counter >= 40:
            gc_counter = 0
            at_lock.try_gc()

        time.sleep(0.05)

except KeyboardInterrupt:
    running = False
    uploader.is_running = False  # 让run_forever退出
    time.sleep(1)  # 等线程退出
    try:
        uploader._close_mqtt()
    except Exception:
        pass
    try:
        voice_svc._running = False
    except Exception:
        pass
    gc.collect()
    print("程序已停止")
except Exception as e:
    running = False
    uploader.is_running = False
    time.sleep(1)
    try:
        uploader._close_mqtt()
    except Exception:
        pass
    try:
        voice_svc._running = False
    except Exception:
        pass
    gc.collect()
    print("程序异常停止:", e)	