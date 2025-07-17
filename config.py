import os
from typing import Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    # Flask Configuration
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Slack Configuration
    SLACK_BOT_TOKEN: str = os.getenv('SLACK_BOT_TOKEN', '')
    SLACK_APP_TOKEN: str = os.getenv('SLACK_APP_TOKEN', '')
    SLACK_SIGNING_SECRET: str = os.getenv('SLACK_SIGNING_SECRET', '')
    
    # ML Model Configuration
    ML_MODEL_ENDPOINT: str = os.getenv('ML_MODEL_ENDPOINT', '')
    ML_MODEL_TIMEOUT: int = int(os.getenv('ML_MODEL_TIMEOUT', '10'))
    ML_MODEL_RETRIES: int = int(os.getenv('ML_MODEL_RETRIES', '3'))
    
    # Message Batching Configuration
    BATCH_TIMEOUT_SECONDS: int = int(os.getenv('BATCH_TIMEOUT_SECONDS', '20'))
    MAX_BATCH_SIZE: int = int(os.getenv('MAX_BATCH_SIZE', '50'))
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    @classmethod
    def validate(cls) -> None:
        required_vars = ['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN']
        missing = [var for var in required_vars if not getattr(cls, var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    @classmethod
    def get_slack_config(cls) -> Dict[str, str]:
        return {
            'bot_token': cls.SLACK_BOT_TOKEN,
            'app_token': cls.SLACK_APP_TOKEN,
            'signing_secret': cls.SLACK_SIGNING_SECRET,
            'batch_timeout': str(cls.BATCH_TIMEOUT_SECONDS)
        }

    @classmethod
    def get_ml_config(cls) -> Dict[str, str]:
        return {
            'endpoint': cls.ML_MODEL_ENDPOINT,
            'timeout': cls.ML_MODEL_TIMEOUT,
            'retries': cls.ML_MODEL_RETRIES
        } 