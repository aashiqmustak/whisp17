import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional

from models import SlackMessage


class MessageStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._messages: Dict[str, Dict[str, List[SlackMessage]]] = defaultdict(lambda: defaultdict(list))
        self._last_activity: Dict[str, Dict[str, float]] = defaultdict(dict)

    def add_message(self, channel_id: str, thread_ts: Optional[str], 
                   user_id: str, username: str, text: str, app_id: Optional[str] = None) -> None:
        with self._lock:
            thread_key = thread_ts or 'main'
            message = SlackMessage(
                user_id=user_id,
                username=username,
                text=text,
                timestamp=time.time(),
                channel_id=channel_id,
                thread_ts=thread_ts,
                app_id=app_id
            )
            self._messages[channel_id][thread_key].append(message)
            self._last_activity[channel_id][thread_key] = time.time()

    def get_messages(self, channel_id: str, thread_ts: Optional[str]) -> List[SlackMessage]:
        with self._lock:
            thread_key = thread_ts or 'main'
            return self._messages[channel_id][thread_key].copy()

    def get_last_activity(self, channel_id: str, thread_ts: Optional[str]) -> Optional[float]:
        with self._lock:
            thread_key = thread_ts or 'main'
            return self._last_activity[channel_id].get(thread_key)

    def update_ml_output(self, channel_id: str, thread_ts: Optional[str], ml_output: str) -> None:
        with self._lock:
            thread_key = thread_ts or 'main'
            messages = self._messages[channel_id][thread_key]
            for message in messages:
                message.ml_output = ml_output

    def remove_messages(self, channel_id: str, thread_ts: Optional[str]) -> List[SlackMessage]:
        with self._lock:
            thread_key = thread_ts or 'main'
            messages = self._messages[channel_id].pop(thread_key, [])
            self._last_activity[channel_id].pop(thread_key, None)
            return messages

    def get_message_count(self, channel_id: str, thread_ts: Optional[str]) -> int:
        with self._lock:
            thread_key = thread_ts or 'main'
            return len(self._messages[channel_id][thread_key])

    def clear_all(self) -> None:
        with self._lock:
            self._messages.clear()
            self._last_activity.clear()

    def get_stats(self) -> dict:
        with self._lock:
            total_channels = len(self._messages)
            total_threads = sum(len(threads) for threads in self._messages.values())
            total_messages = sum(
                len(messages) 
                for threads in self._messages.values() 
                for messages in threads.values()
            )
            return {
                'total_channels': total_channels,
                'total_threads': total_threads,
                'total_messages': total_messages
            } 