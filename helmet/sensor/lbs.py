import _thread
import time
from quectel import LBS
from at_port import at_lock


class SimpleLBS:
    def __init__(self):
        self._lbs = None
        self._last_location = None
        self._lock = _thread.allocate_lock()
        self._busy = False

    def request_location(self):
        """按需请求一次LBS定位(非阻塞，后台线程查一次就停）"""
        if self._busy:
            return
        self._busy = True
        try:
            _thread.start_new_thread(self._run, ())
        except Exception as e:
            self._busy = False
            print("[LBS] 线程启动失败:", e)

    def clear(self):
        """清除缓存的位置(GNSS恢复后调用)"""
        with self._lock:
            self._last_location = None

    def _run(self):
        if not at_lock.acquire(20000):
            self._busy = False
            return
        lbs = None
        try:
            lbs = LBS()
            loc = lbs.get_location(15000)
            if loc and loc.get("latitude") is not None:
                with self._lock:
                    self._last_location = {
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                        "altitude": loc.get("altitude"),
                        "speed_kmh": None,
                        "source": "lbs",
                    }
        except Exception:
            pass
        finally:
            if lbs:
                try:
                    lbs.deinit()
                except Exception:
                    pass
            at_lock.release()
            self._busy = False

    def get_cached_location(self):
        """获取缓存的LBS位置(不触发查询)"""
        with self._lock:
            if self._last_location:
                return dict(self._last_location)
            return None

    @property
    def is_busy(self):
        return self._busy


lbs_module = SimpleLBS()


def get_cached_location():
    return lbs_module.get_cached_location()


def request_location():
    lbs_module.request_location()


def clear():
    lbs_module.clear()
