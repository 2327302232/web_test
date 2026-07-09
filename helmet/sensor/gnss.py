import quectel
import time
from at_port import at_lock

_AT_TIMEOUT = 100  # GNSS 获取 AT 锁的最长等待（毫秒），超时则跳过本次查询

class SimpleGNSS:
    def __init__(self):
        """初始化GNSS模块"""
        self.gnss = None
        self._last_location = None
        self._last_query_ms = 0
        self._query_interval_ms = 2000
        self.skip_hardware = False
        self._gnss_restart_count = 0
        self._gnss_last_restart_ms = 0
        self.start()
    
    def start(self):
        """启动GNSS(需要先获取AT锁，超时则跳过)"""
        if not at_lock.acquire(_AT_TIMEOUT):
            return False
        try:
            self.gnss = quectel.GNSS()
            if self.gnss.start():
                print("GNSS启动成功")
                return True
        except Exception as e:
            print(f"GNSS启动失败: {e}")
            return False
        finally:
            at_lock.release()
        return False
    
    def get_basic_location(self, timeout=30):
        """
        获取基本位置信息(AT锁保护,超时或AT口忙则返回None)
        
        参数:
            timeout: 超时时间（秒）,默认30秒
        
        返回:
            dict: 包含经纬度、海拔、速度的字典,如果获取失败返回None
        """
        if not self.gnss:
            if not self.start():
                return None

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            loc = self._get_location_locked()
            if loc:
                return self._extract_location(loc)
            time.sleep(1)

        return None

    def _extract_location(self, loc):
        # 只提取需要的字段
        return {
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "altitude": loc.get("altitude"),
            "speed_kmh": loc.get("speed_kmh"),
            "source": "gnss",
        }

    def get_cached_location(self, timeout=0):
        """
        返回缓存的位置信息(不发AT指令)

        参数:
            timeout: 超时时间（秒），仅>0时才会查询硬件
        """
        if timeout > 0:
            return self._query_location(timeout)
        return self._last_location

    def _restart_gnss(self):
        """重启GNSS模块(带频率限制,最多每30秒一次)"""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._gnss_last_restart_ms) < 30000:
            return False
        if self._gnss_restart_count >= 3:
            return False  # 超过3次不再重试
        self._gnss_restart_count += 1
        self._gnss_last_restart_ms = now
        print(f"[GNSS] 自动重启 (第{self._gnss_restart_count}次)")
        self.stop()
        time.sleep(1)
        return self.start()

    def _get_location_locked(self):
        """在AT锁保护下调用 gnss.get_location()，超时或失败返回 None"""
        if not at_lock.acquire(_AT_TIMEOUT):
            return None
        try:
            return self.gnss.get_location()
        except Exception:
            return None
        finally:
            at_lock.release()

    def refresh_location(self):
        """
        主动查询一次GNSS硬件，更新缓存（会发AT+QGPSLOC=2）
        返回最新的位置数据
        skip_hardware=True 时跳过查询，只返回缓存
        AT口忙时也跳过，用缓存数据
        """
        if self.skip_hardware:
            return self._last_location
        if not self.gnss:
            if not self.start():
                return self._last_location
        self._last_query_ms = time.ticks_ms()
        loc = None
        try:
            loc = self._get_location_locked()
        except Exception as e:
            err = str(e)
            # 505=未启动, 549=GPS芯片异常 → 自动重启（516=无信号，不重启，引擎后台继续搜星）
            if any(code in err for code in ("505", "549")):
                print(f"[GNSS] 错误 {err}，尝试重启")
                if self._restart_gnss():
                    time.sleep(2)
                    loc = self._get_location_locked()
            else:
                print(f"[GNSS] 查询异常: {err}")
        if loc:
            self._last_location = self._extract_location(loc)
        return self._last_location

    def _query_location(self, timeout):
        """
        带超时的硬件查询（内部方法，用于timeout>0的场景）
        """
        if not self.gnss:
            if not self.start():
                return self._last_location

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            now_ms = time.ticks_ms()
            if time.ticks_diff(now_ms, self._last_query_ms) < self._query_interval_ms:
                time.sleep(1)
                continue
            self._last_query_ms = now_ms
            loc = self._get_location_locked()
            if loc:
                self._last_location = self._extract_location(loc)
                break
            time.sleep(1)

        return self._last_location
    
    def stop(self):
        """停止GNSS(获取AT锁,超时则跳过)"""
        if not self.gnss:
            return
        if at_lock.acquire(_AT_TIMEOUT):
            try:
                self.gnss.stop()
            except Exception:
                pass
            finally:
                at_lock.release()
        self.gnss = None

try:
    gnss_module = SimpleGNSS()
except Exception:
    gnss_module = None

def get_basic_location(timeout=30):
    if not gnss_module:
        return None
    return gnss_module.get_basic_location(timeout)


def get_cached_location(timeout=0):
    if not gnss_module:
        return None
    return gnss_module.get_cached_location(timeout)


def refresh_location():
    """主动查询一次GNSS硬件,更新缓存"""
    if not gnss_module:
        return None
    return gnss_module.refresh_location()


