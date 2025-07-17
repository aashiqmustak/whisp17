import threading
import logging
from typing import Dict, Tuple, Optional, Callable

logger = logging.getLogger(__name__)


class TimerManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._timers: Dict[Tuple[str, Optional[str]], threading.Timer] = {}
        self._callbacks: Dict[Tuple[str, Optional[str]], Callable] = {}
        self._running = True

    def start_timer(self, channel_id: str, thread_ts: Optional[str], 
                   timeout_seconds: int, callback: Callable) -> None:
        with self._lock:
            if not self._running:
                return
            
            key = (channel_id, thread_ts)
            self._cancel_timer_internal(key)
            
            timer = threading.Timer(timeout_seconds, self._timer_callback, args=[key])
            timer.daemon = True
            
            self._timers[key] = timer
            self._callbacks[key] = callback
            timer.start()

    def reset_timer(self, channel_id: str, thread_ts: Optional[str], 
                   timeout_seconds: int) -> None:
        with self._lock:
            key = (channel_id, thread_ts)
            if key in self._callbacks:
                callback = self._callbacks[key]
                self.start_timer(channel_id, thread_ts, timeout_seconds, callback)

    def cancel_timer(self, channel_id: str, thread_ts: Optional[str]) -> bool:
        with self._lock:
            key = (channel_id, thread_ts)
            return self._cancel_timer_internal(key)

    def _cancel_timer_internal(self, key: Tuple[str, Optional[str]]) -> bool:
        if key in self._timers:
            timer = self._timers[key]
            timer.cancel()
            del self._timers[key]
            del self._callbacks[key]
            return True
        return False

    def _timer_callback(self, key: Tuple[str, Optional[str]]) -> None:
        with self._lock:
            if key not in self._callbacks:
                return
            callback = self._callbacks[key]
            del self._timers[key]
            del self._callbacks[key]
        
        try:
            callback(key[0], key[1])
        except Exception as e:
            logger.error(f"Error in timer callback: {e}")

    def has_timer(self, channel_id: str, thread_ts: Optional[str]) -> bool:
        with self._lock:
            key = (channel_id, thread_ts)
            return key in self._timers

    def get_active_timers(self) -> set:
        with self._lock:
            return set(self._timers.keys())

    def get_timer_count(self) -> int:
        with self._lock:
            return len(self._timers)

    def stop_all(self) -> None:
        with self._lock:
            self._running = False
            for key in list(self._timers.keys()):
                self._cancel_timer_internal(key) 