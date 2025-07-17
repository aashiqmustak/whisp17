import json
import time
import logging
import requests
from typing import List, Dict

from config import Config
from models import SlackMessage, MLProcessorError
from rag_it1.rag_func import formator_llm

logger = logging.getLogger(__name__)



class MLProcessor:
    def __init__(self, config: Dict[str, str]):
        # Get ML-specific config or use defaults
        ml_config = Config.get_ml_config()
        self.config = ml_config
        self.session = requests.Session()
        
        from requests.adapters import HTTPAdapter
        retry_adapter = HTTPAdapter(
            max_retries=int(self.config['retries']),
            pool_connections=10,
            pool_maxsize=20
        )
        self.session.mount('http://', retry_adapter)
        self.session.mount('https://', retry_adapter)

    def process_messages(self, messages: List[SlackMessage], slack_handler=None) -> str:
        if not messages:
            raise MLProcessorError("No messages to process")
        
        try:
            payload = self._prepare_payload(messages)
            
            # Try to send to external ML endpoint first
            try:
                self._send_request(payload)
                return f"Sent {len(messages)} message{'s' if len(messages) != 1 else ''} to ML endpoint"
            except Exception as endpoint_error:
                logger.warning(f"External ML endpoint failed: {endpoint_error}, falling back to local RAG processing")
                
                # Fall back to local RAG processing
                return self._process_locally(payload, slack_handler)
                
        except Exception as e:
            raise MLProcessorError(f"Failed to process messages: {e}")
    
    def _process_locally(self, payload: Dict, slack_handler=None) -> str:
        """Process messages using local RAG pipeline"""
        try:
            print("\n" + "="*80)
            print("PROCESSING WITH LOCAL RAG PIPELINE")
            print("="*80)
            print(f"Batch Size: {payload['batch_size']} messages")
            print("-"*80)
            print(json.dumps(payload, indent=2))
            print("="*80)
            
            # Call the RAG processing function
            result = formator_llm(payload, slack_handler)
            
            print("RAG processing completed successfully")
            logger.info(f"Local RAG processing completed for {payload['batch_size']} messages")
            
            return f"Processed {payload['batch_size']} message{'s' if payload['batch_size'] != 1 else ''} through RAG pipeline"
            
        except Exception as e:
            logger.error(f"Local RAG processing failed: {e}")
            raise MLProcessorError(f"Local RAG processing failed: {e}")

    def _prepare_payload(self, messages: List[SlackMessage]) -> Dict:
        message_outcomes = []
        for msg in messages:
            outcome = {
                "user_id": msg.user_id,
                "username": msg.username,
                "text": msg.text,
                "app_id": msg.app_id,
                "channel_id": msg.channel_id,
                "session_id": msg.session_id
            }
            message_outcomes.append(outcome)
        
        return {
            'messages': message_outcomes,
            'batch_size': len(messages),
            'timestamp': time.time()
        }

    def _send_request(self, payload: Dict) -> None:
        try:
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Flask-Slack-ML-App/1.0'
            }
            
            # Enhanced JSON payload display
            print("\n" + "="*80)
            print("SENDING JSON PAYLOAD TO ML ENDPOINT")
            print("="*80)
            print(f"Endpoint: {self.config['endpoint']}")
            print(f"Batch Size: {payload['batch_size']} messages")
            print("-"*80)
            print(json.dumps(payload, indent=2))
            print("="*80)
            
            response = self.session.post(
                self.config['endpoint'],
                json=payload,
                headers=headers,
                timeout=int(self.config['timeout'])
            )
            
            # Just check if request was successful, don't process response
            response.raise_for_status()
            print(f"Successfully sent to ML endpoint. Status: {response.status_code}")
            logger.info(f"Successfully sent data to ML endpoint. Status: {response.status_code}")
            
        except requests.exceptions.Timeout:
            raise MLProcessorError("ML model request timed out")
        except requests.exceptions.ConnectionError:
            raise MLProcessorError("Failed to connect to ML model")
        except requests.exceptions.HTTPError as e:
            raise MLProcessorError(f"ML model returned HTTP error: {e}")
        except Exception as e:
            raise MLProcessorError(f"Unexpected error: {e}")

    def health_check(self) -> bool:
        try:
            response = requests.get(f"{self.config['endpoint']}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

    def close(self) -> None:
        self.session.close()
        
    def start(self) -> None:
        """Start the ML processor (no-op for HTTP-based processor)"""
        logger.info("ML Processor started")
        
    def stop(self) -> None:
        """Stop the ML processor"""
        self.close()
        logger.info("ML Processor stopped")


class MockMLProcessor:
    """Mock ML processor for testing when real ML service is unavailable"""
    
    def __init__(self):
        pass
    
    def process_messages(self, messages: List[SlackMessage], slack_handler=None) -> str:
        """Process messages using local RAG pipeline"""
        
        # Create payload structure like real processor
        message_outcomes = []
        for msg in messages:
            outcome = {
                "user_id": msg.user_id,
                "username": msg.username,
                "text": msg.text,
                "app_id": msg.app_id,
                "channel_id": msg.channel_id,
                "session_id": msg.session_id
            }
            message_outcomes.append(outcome)
        
        payload = {
            'messages': message_outcomes,
            'batch_size': len(messages),
            'timestamp': time.time()
        }
        
        try:
            # Process through local RAG pipeline
            print("\n" + "="*80)
            print("PROCESSING WITH LOCAL RAG PIPELINE")
            print("="*80)
            print(f"Batch Size: {payload['batch_size']} messages")
            print("-"*80)
            print(json.dumps(payload, indent=2))
            print("="*80)
            
            # Call the RAG processing function
            from rag_it1.rag_func import formator_llm
            result = formator_llm(payload, slack_handler)
            
            print("RAG processing completed successfully")
            logger.info(f"Local RAG processing completed for {len(messages)} messages")
            
            return f"Processed {len(messages)} message{'s' if len(messages) != 1 else ''} through RAG pipeline"
            
        except Exception as e:
            logger.error(f"RAG processing failed: {e}")
            # Fall back to mock behavior
            print("Falling back to mock processing")
            logger.info(f"Mock ML processor simulated sending {len(messages)} messages")
            return f"Processed {len(messages)} message{'s' if len(messages) != 1 else ''} (mock mode)"

    def health_check(self) -> bool:
        return True

    def close(self) -> None:
        """No-op for mock processor"""
        pass
        
    def start(self) -> None:
        """Start the mock ML processor"""
        logger.info("Mock ML Processor started")
        
    def stop(self) -> None:
        """Stop the mock ML processor"""
        self.close()
        logger.info("Mock ML Processor stopped")


def send_to_ml(messages):
    """
    Direct function to call RAG processing (now integrated into ML processors above).
    Args:
        messages: Input data for RAG processing.
    Returns:
        dict: Result of processing.
    """
    print("Direct RAG call:")
    print(messages)
    print("###")
    return formator_llm(messages)