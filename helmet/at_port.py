import _thread
import time
import gc


class AtPortLock:
    def __init__(self):
        self._lock = _thread.allocate_lock()
        self._gc_pending = False
        self._gc_threshold = 64 * 1024

    def acquire(self, timeout_ms=10000):
        start = time.ticks_ms()
        while True:
            if self._lock.acquire(False):
                return True
            if time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
                return False
            time.sleep_ms(1)

    def release(self):
        self._lock.release()
        if self._gc_pending:
            self._gc_pending = False
            gc.collect()

    def is_busy(self):
        if self._lock.acquire(False):
            self._lock.release()
            return False
        return True

    def try_gc(self, force=False):
        if not force and self.is_busy():
            self._gc_pending = True
            return False

        if force:
            gc.collect()
            self._gc_pending = False
            return True

        try:
            free = gc.mem_free()
        except Exception:
            free = 0

        if free < self._gc_threshold:
            gc.collect()
            self._gc_pending = False
            return True

        self._gc_pending = False
        return False


at_lock = AtPortLock()
