import json
import logging
import time
from typing import Dict, Any, Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import Config
from message_store import MessageStore
from timer_manager import TimerManager
from ml_processor import MLProcessor, MockMLProcessor
from message_recovery import MessageRecovery
from intent_entity_extractor.extractor import handle_specific_job_action

logger = logging.getLogger(__name__)


class SlackHandler:
    def __init__(self, config: Dict[str, str]):
        self.config = config
        self.app = App(token=config['bot_token'])
        self.client = self.app.client
        
        # Set batch configuration
        self.batch_timeout = int(config.get('batch_timeout', '20'))
        
        # Initialize core components
        self.message_store = MessageStore()
        self.timer_manager = TimerManager()
        self.ml_processor = MLProcessor(config)
        
        # Set up event handlers
        self._setup_event_handlers()
        self._get_bot_app_id()
        
        # Initialize Message Recovery System
        self.message_recovery = MessageRecovery(self)
        
        # Initialize Socket Mode handler (but don't start yet)
        self.socket_handler = SocketModeHandler(
            app=self.app, 
            app_token=config['app_token']
        )
        
        # Add global message counter for debugging
        self.message_counter = 0
        
        # Initialize ML processor with fallback to mock
        try:
            # Test ML processor health
            if not self.ml_processor.health_check():
                logger.warning("ML processor health check failed, using mock processor")
                self.ml_processor = MockMLProcessor()
        except Exception as e:
            logger.warning(f"ML processor initialization failed: {e}, using mock processor")
            self.ml_processor = MockMLProcessor()
            
        self.bot_app_id = None

    def _setup_event_handlers(self) -> None:
        # Track message timestamps to detect missing messages
        self.message_timestamps = {}
        
        @self.app.middleware
        def log_all_requests(req, resp, next):
            """Middleware to log all incoming Slack requests for debugging"""
            try:
                if hasattr(req, 'body') and req.body:
                    body = req.body
                    if isinstance(body, dict):
                        event = body.get('event', {})
                        if event.get('type') == 'message' and not event.get('subtype'):
                            user = event.get('user', 'unknown')
                            text = event.get('text', '')
                            ts = event.get('ts', '')
                            logger.debug(f"MIDDLEWARE - Slack sent message: user={user}, text='{text}', ts={ts}")
            except Exception as e:
                logger.debug(f"Middleware logging error: {e}")
            
            # Continue processing
            next()

        # Add session event handlers
        @self.app.event(".*")
        def handle_session_events(event, client):
            """Handle all events to detect session establishment"""
            event_type = event.get('type', 'unknown')
            if event_type == 'hello':
                print("\n" + "="*80)
                print("SLACK SESSION ESTABLISHED SUCCESSFULLY")
                print("="*80)
                logger.info("Slack WebSocket session established")
            elif event_type not in ['message', 'app_mention']:
                logger.debug(f"Session event: {event_type}")

        @self.app.event("message")
        def handle_message(event: Dict[str, Any], say, client) -> None:
            logger.debug(f"PRIMARY HANDLER - Received message event: {event}")
            self._process_message_event(event)

        @self.app.event("app_mention")
        def handle_app_mention(event: Dict[str, Any], say, client) -> None:
            logger.debug(f"APP MENTION - Received app mention: {event}")
            self._process_message_event(event)

    def _process_message_event(self, event: dict) -> None:
        """Process a message event and handle batching"""
        try:
            channel_id = event.get('channel')
            thread_ts = event.get('thread_ts')
            text = event.get('text', '').strip()
            user = event.get('user')
            ts = event.get('ts')
            
            # Check for duplicate messages by timestamp - Slack sometimes sends same message multiple times
            msg_id = f"{channel_id}_{ts}"
            if hasattr(self, 'message_recovery') and self.message_recovery:
                if msg_id in self.message_recovery.processed_messages:
                    logger.debug(f"Skipping duplicate message: {msg_id} - '{text[:50]}'")
                    return
                # Mark as processed immediately to prevent future duplicates
                self.message_recovery.mark_message_processed(channel_id, ts)
            
            # Skip if no text
            if not text:
                return
                
            # Skip bot messages
            if event.get('bot_id') or event.get('subtype'):
                return
                
            # Skip our own messages
            if user == self.bot_app_id:
                return
            
            # Get username
            username = self._get_username(user)
            
            # Enhanced message logging
            print("\n" + "─"*60)
            print(f"INCOMING MESSAGE")
            print(f"   User: {username} ({user})")
            print(f"   Text: '{text}'")
            print(f"   Channel: {channel_id}")
            print(f"   Thread: {thread_ts or 'main'}")
            print(f"   Timestamp: {ts}")
            print("─"*60)
            
            # Add to message store (using the correct method signature)
            self.message_store.add_message(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user,
                username=username,
                text=text,
                app_id=None  # Not a bot message
            )
            
            # Log the message
            counter = self.message_store.get_message_count(channel_id, thread_ts)
            logger.info(f"NEW MESSAGE #{counter}: user={user}, text='{text}', channel={channel_id}, thread={thread_ts}")
            
            # Start/restart timer for this batch
            self.timer_manager.start_timer(
                channel_id=channel_id,
                thread_ts=thread_ts,
                timeout_seconds=self.batch_timeout,
                callback=lambda ch, th: self._on_timer_expired(ch, th)
            )
            
        except Exception as e:
            logger.error(f"Error processing message event: {e}")
            logger.exception(e)

    def _get_bot_app_id(self) -> None:
        """Get the bot's app ID for filtering out own messages"""
        try:
            auth_response = self.client.auth_test()
            if auth_response['ok']:
                app_id = auth_response.get('app_id')
                user_id = auth_response.get('user_id')
                team_id = auth_response.get('team_id')
                logger.info(f"Bot identification: app_id={app_id}, user_id={user_id}, team_id={team_id}")
                
                # Use team_id if app_id is not available
                self.bot_app_id = app_id or team_id
                logger.info(f"Using bot_app_id: {self.bot_app_id}")
            else:
                logger.error("Failed to get bot app ID from auth_test")
        except Exception as e:
            logger.error(f"Error getting bot app ID: {e}")

    def _get_username(self, user_id: str) -> str:
        try:
            response = self.client.users_info(user=user_id)
            return response['user']['name'] if response['ok'] else user_id
        except:
            return user_id

    def _manage_timer(self, channel_id: str, thread_ts: Optional[str]) -> None:
        """Start or restart the timer for a channel/thread"""
        try:
            if self.timer_manager.has_timer(channel_id, thread_ts):
                self.timer_manager.reset_timer(channel_id, thread_ts, self.batch_timeout)
            else:
                self.timer_manager.start_timer(
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    timeout_seconds=self.batch_timeout,
                    callback=lambda ch, th: self._on_timer_expired(ch, th)
                )
        except Exception as e:
            logger.error(f"Error managing timer for {channel_id}/{thread_ts}: {e}")

    def _on_timer_expired(self, channel_id: str, thread_ts: Optional[str]) -> None:
        """Handle timer expiration - create batch, check for missing messages, and process complete batch"""
        try:
            thread_display = thread_ts or 'main'
            
            print("\n" + "="*50)
            print(f"BATCH TIMER EXPIRED for {channel_id}/{thread_display}")
            print("="*50)
            
            logger.info(f"TIMER EXPIRED for {channel_id}/{thread_display}")
            
            # STEP 1: First create the initial batch from messages we've already collected
            initial_messages = self.message_store.get_messages(channel_id, thread_ts)
            
            if not initial_messages:
                logger.warning(f"No messages found for expired timer: {channel_id}/{thread_display}")
                return
                
            print(f"Initial batch contains {len(initial_messages)} messages:")
            for i, msg in enumerate(initial_messages, 1):
                print(f"   {i}. {msg.username}: '{msg.text}'")
            print("─"*60)
            
            logger.info(f"Created initial batch of {len(initial_messages)} messages for {channel_id}/{thread_display}")
            
            # STEP 2: Check for missing messages and add them to the existing batch
            if self.message_recovery:
                logger.info(f"Checking for missing messages to add to batch for {channel_id}")
                try:
                    # This will add any missing messages directly to the message store
                    self.message_recovery._check_channel_for_missing_messages_immediate(channel_id)
                    
                    # Get the updated batch (original + any recovered messages)
                    final_messages = self.message_store.get_messages(channel_id, thread_ts)
                    
                    if len(final_messages) > len(initial_messages):
                        added_count = len(final_messages) - len(initial_messages)
                        logger.info(f"Added {added_count} missing messages to batch for {channel_id}")
                        
                        print(f"Final batch now contains {len(final_messages)} messages:")
                        for i, msg in enumerate(final_messages, 1):
                            print(f"   {i}. {msg.username}: '{msg.text}'")
                        print("─"*60)
                    else:
                        logger.info(f"No missing messages found - final batch remains {len(final_messages)} messages")
                        final_messages = initial_messages
                        
                except Exception as e:
                    logger.warning(f"Error checking for missing messages: {e}")
                    final_messages = initial_messages
            else:
                logger.info("Message recovery disabled - using initial batch only")
                final_messages = initial_messages
            
            # STEP 3: Process the complete batch (original + recovered messages)
            logger.info(f"Processing complete batch of {len(final_messages)} messages for {channel_id}/{thread_display}")
            self._process_messages(channel_id, thread_ts, final_messages)
            
        except Exception as e:
            logger.error(f"Error in timer callback for {channel_id}/{thread_ts}: {e}")

    def _process_messages(self, channel_id: str, thread_ts: Optional[str], 
                        messages: list) -> None:
        """Process a batch of messages through ML and post response"""
        try:
            thread_display = thread_ts or 'main'
            logger.info(f"Starting ML processing for {len(messages)} messages in {channel_id}/{thread_display}")

            # === NEW: Check for specific job actions before ML processing ===
            if messages and len(messages) == 1:
                msg = messages[0]
                user_data = {
                    'user_id': getattr(msg, 'user_id', None) or msg.get('user_id'),
                    'username': getattr(msg, 'username', None) or msg.get('username'),
                    'channel_id': channel_id,
                    'thread_ts': thread_ts,
                }
                original_text = getattr(msg, 'text', None) or msg.get('text', '')
                if handle_specific_job_action(original_text, user_data, self):
                    logger.info(f"Handled specific job action for message: {original_text}")
                    return  # Do not proceed to ML processing
            # === END NEW ===

            # Send to ML processor
            try:
                ml_response = self.ml_processor.process_messages(messages, slack_handler=self)
                logger.info(f"ML processing successful for {channel_id}/{thread_display}, response: {ml_response}")
                
                # Update message store with ML output
                self.message_store.update_ml_output(channel_id, thread_ts, ml_response)
                
                # Post response to Slack
                self._post_response(channel_id, thread_ts, ml_response)
                
            except Exception as e:
                logger.error(f"ML processing failed for {channel_id}/{thread_display}: {e}")
                error_msg = f"Processed {len(messages)} message{'s' if len(messages) != 1 else ''} (ML processing failed)"
                self._post_response(channel_id, thread_ts, error_msg)
            
            # Remove processed messages from store
            removed_messages = self.message_store.remove_messages(channel_id, thread_ts)
            logger.info(f"Removed {len(removed_messages)} messages from store after processing")
            
        except Exception as e:
            logger.error(f"Error processing messages for {channel_id}/{thread_ts}: {e}")

    def _post_response(self, channel_id: str, thread_ts: Optional[str], 
                      text: str) -> None:
        """Post a response message to Slack"""
        try:
            thread_display = thread_ts or 'main'
            logger.info(f"About to post response to Slack for {channel_id}/{thread_display}: '{text}'")
            
            response = self.client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts
            )
            
            if response['ok']:
                logger.info(f"Successfully posted response to Slack for {channel_id}/{thread_display}")
            else:
                logger.error(f"Failed to post response to Slack: {response.get('error')}")
                
        except Exception as e:
            logger.error(f"Error posting response to Slack: {e}")

    def run(self):
        """Start the Slack bot using Socket Mode"""
        try:
            # Start background systems
            self.ml_processor.start()
            self.message_recovery.start()  # Re-enabled with better duplicate detection
            
            print("\n" + "="*80)
            print("STARTING SLACK BOT SESSION")
            print("="*80)
            logger.info("Starting Slack bot with Socket Mode...")
            
            self.socket_handler.start()
        except Exception as e:
            logger.error(f"Failed to start Slack bot: {e}")
            self.shutdown()
            raise
            
    def shutdown(self):
        """Gracefully shut down all services"""
        logger.info("Shutting down Slack bot...")
        
        # Stop message recovery first
        if self.message_recovery:
            self.message_recovery.stop()
        
        # Stop ML processor
        if self.ml_processor:
            self.ml_processor.stop()
            
        # Stop timer manager
        if self.timer_manager:
            self.timer_manager.stop_all()
            
        # Stop socket connection
        if self.socket_handler:
            self.socket_handler.close()
            
        logger.info("Slack bot shutdown complete")

    def get_final_outcomes_json(self, channel_id: str, thread_ts: Optional[str] = None) -> str:
        messages = self.message_store.get_messages(channel_id, thread_ts)
        outcomes = [msg.to_final_outcome_dict() for msg in messages]
        return json.dumps(outcomes, indent=2)

    def get_stats(self) -> Dict[str, Any]:
        try:
            store_stats = self.message_store.get_stats() if self.message_store else {}
            timer_stats = {
                'active_timers': self.timer_manager.get_timer_count() if self.timer_manager else 0
            }
            
            return {
                'status': 'healthy',
                'timestamp': time.time(),
                'message_store': store_stats,
                'timers': timer_stats,
                'components': {
                    'message_store': 'healthy' if self.message_store else 'unhealthy',
                    'timer_manager': 'healthy' if self.timer_manager else 'unhealthy',
                    'ml_processor': 'healthy' if self.ml_processor else 'unhealthy',
                    'message_recovery': 'healthy' if self.message_recovery else 'unhealthy'
                }
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': time.time()
            } 