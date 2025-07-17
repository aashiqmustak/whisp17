from dataclasses import dataclass
from typing import Optional


class MLProcessorError(Exception):
    """Custom exception for ML processor errors"""
    pass


@dataclass
class SlackMessage:
    user_id: str
    username: str
    text: str
    timestamp: float
    channel_id: str
    thread_ts: Optional[str] = None
    app_id: Optional[str] = None
    ml_output: Optional[str] = None
    
    @property
    def session_id(self) -> str:
        return f"{self.channel_id}_{self.thread_ts or 'main'}"
    
    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'text': self.text,
            'ml_output': self.ml_output,
            'app_id': self.app_id,
            'channel_id': self.channel_id,
            'session_id': self.session_id,
            'timestamp': self.timestamp,
            'thread_ts': self.thread_ts
        }
    
    def to_final_outcome_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'text': self.text,
            'ml_output': self.ml_output,
            'app_id': self.app_id,
            'channel_id': self.channel_id,
            'session_id': self.session_id
        } 