import time
import threading
import logging
from typing import Dict, Set, Any

logger = logging.getLogger(__name__)


class MessageRecovery:
    """Background service to recover messages dropped by Slack's real-time events"""
    
    def __init__(self, slack_handler):
        self.slack_handler = slack_handler
        self.client = slack_handler.client
        self.running = False
        self.recovery_thread = None
        self.check_interval = 30  # Check every 30 seconds instead of 10
        self.lookback_window = 15  # Look back only 15 seconds
        
        # Track last processed timestamps for each channel
        self.last_processed_ts = {}
        # Track which messages we've already processed to avoid duplicates
        self.processed_messages = set()
        
        # Rate limiting protection
        self.last_check_time = {}  # Track when we last checked each channel
        self.min_check_interval = 25  # Don't check same channel more than once per 25 seconds
        
    def start(self):
        """Start the background message recovery service"""
        if self.running:
            return
            
        self.running = True
        self.recovery_thread = threading.Thread(target=self._recovery_loop, daemon=True)
        self.recovery_thread.start()
        logger.info("Message recovery service started")
        
    def stop(self):
        """Stop the background message recovery service"""
        self.running = False
        if self.recovery_thread:
            self.recovery_thread.join(timeout=2)
        logger.info("Message recovery service stopped")
        
    def _recovery_loop(self):
        """Main recovery loop - DISABLED since we now do immediate recovery before batches"""
        logger.info("Background recovery loop disabled - using immediate recovery before batch processing")
        # Background recovery is disabled - we now do immediate recovery before each batch
        while self.running:
            try:
                # Just sleep, don't run recovery checks
                time.sleep(60)  # Sleep for 60 seconds and do nothing
            except Exception as e:
                logger.error(f"Error in recovery loop: {e}")
                time.sleep(60)
                
    def _check_for_missing_messages(self):
        """Check all active channels for missing messages"""
        # Get channels with recent activity (from message store or timer manager)
        active_channels = set()
        
        # Add channels from current message store (only if they have recent messages)
        for channel_id, threads in self.slack_handler.message_store._messages.items():
            if threads:  # Only if there are active threads
                active_channels.add(channel_id)
            
        # Add channels from active timers (only currently active ones)
        for (channel_id, thread_ts) in self.slack_handler.timer_manager.get_active_timers():
            active_channels.add(channel_id)
        
        # Only check if there are active channels
        if not active_channels:
            return
            
        logger.debug(f"Checking {len(active_channels)} active channels for missing messages")
            
        # Check each active channel
        for channel_id in active_channels:
            try:
                self._check_channel_for_missing_messages(channel_id)
            except Exception as e:
                if "ratelimited" in str(e).lower():
                    logger.debug(f"Rate limited while checking channel {channel_id}, will retry later")
                else:
                    logger.error(f"Error checking channel {channel_id} for missing messages: {e}")
                
    def _check_channel_for_missing_messages(self, channel_id: str):
        """Check a specific channel for missing messages"""
        try:
            # Rate limiting: Don't check same channel too frequently
            now = time.time()
            last_check = self.last_check_time.get(channel_id, 0)
            if now - last_check < self.min_check_interval:
                return  # Skip this channel check
            
            self.last_check_time[channel_id] = now
            
            # Calculate time window to check
            oldest_ts = now - self.lookback_window
            
            # Get last processed timestamp for this channel, or use lookback window
            last_ts = self.last_processed_ts.get(channel_id, oldest_ts)
            
            # Get recent messages from Slack
            response = self.client.conversations_history(
                channel=channel_id,
                oldest=str(last_ts),
                limit=100,
                inclusive=True
            )
            
            if not response['ok']:
                logger.warning(f"Failed to get history for channel {channel_id}: {response.get('error')}")
                return
                
            messages = response['messages']
            recovered_count = 0
            
            # Process messages in chronological order (oldest first)
            for message in reversed(messages):
                if self._should_recover_message(message, channel_id):
                    self._recover_message(message, channel_id)
                    recovered_count += 1
                    
            if recovered_count > 0:
                logger.info(f"Recovered {recovered_count} missing messages from channel {channel_id}")
                
            # Update last processed timestamp
            if messages:
                latest_ts = max(float(msg['ts']) for msg in messages)
                self.last_processed_ts[channel_id] = latest_ts
                
        except Exception as e:
            logger.error(f"Error checking channel {channel_id} history: {e}")
            
    def _check_channel_for_missing_messages_immediate(self, channel_id: str):
        """Immediate check for missing messages - called before batch processing"""
        try:
            logger.info(f"=== IMMEDIATE RECOVERY CHECK for channel {channel_id} ===")
            
            # Calculate time window to check (look back 30 seconds from now)
            now = time.time()
            oldest_ts = now - 30  # More aggressive lookback for immediate check
            
            logger.info(f"Checking last 30 seconds for missing messages in channel {channel_id}")
            
            # Get recent messages from Slack
            response = self.client.conversations_history(
                channel=channel_id,
                oldest=str(oldest_ts),
                limit=100,
                inclusive=True
            )
            
            if not response['ok']:
                logger.warning(f"Failed to get history for channel {channel_id}: {response.get('error')}")
                return
                
            messages = response['messages']
            logger.info(f"Found {len(messages)} messages in Slack history for channel {channel_id}")
            recovered_count = 0
            
            # Process messages in chronological order (oldest first)
            for message in reversed(messages):
                if self._should_recover_message(message, channel_id):
                    logger.info(f"Recovering missing message: {message.get('text', '')[:50]}...")
                    self._recover_message_to_existing_batch(message, channel_id)
                    recovered_count += 1
                    
            if recovered_count > 0:
                logger.info(f"RECOVERY COMPLETE: Added {recovered_count} missing messages to existing batch for channel {channel_id}")
                print(f"\nRECOVERY COMPLETE: Added {recovered_count} missing messages to batch")
            else:
                logger.info(f"NO MISSING MESSAGES: All messages already captured for channel {channel_id}")
                
        except Exception as e:
            logger.error(f"Error in immediate recovery check for channel {channel_id}: {e}")
    
    def _recover_message_to_existing_batch(self, message: dict, channel_id: str):
        """Add a recovered message directly to existing batch (no new timer)"""
        try:
            # Create message ID and mark as processed
            msg_id = f"{channel_id}_{message.get('ts', '')}"
            self.processed_messages.add(msg_id)
            
            # Get username
            user = message.get('user')
            username = self.slack_handler._get_username(user) if user else 'unknown'
            text = message.get('text', '')
            ts = message.get('ts', '')
            thread_ts = message.get('thread_ts')
            
            print("\n" + "="*60)
            print("ADDING RECOVERED MESSAGE TO EXISTING BATCH")
            print(f"   User: {username} ({user})")
            print(f"   Text: '{text}'")
            print(f"   Timestamp: {ts}")
            print(f"   Channel: {channel_id}")
            print(f"   Thread: {thread_ts or 'main'}")
            print("="*60)
            
            logger.info(f"ADDING TO EXISTING BATCH: user={user}, text='{text}', channel={channel_id}, ts={ts}")
            
            # Add directly to message store (DON'T start new timer - we're already in timer callback)
            self.slack_handler.message_store.add_message(
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user,
                username=username,
                text=text,
                app_id=None
            )
            
            logger.info(f"Successfully added recovered message to existing batch for {channel_id}")
            
        except Exception as e:
            logger.error(f"Error adding recovered message to batch: {e}")
        
    def _should_recover_message(self, message: dict, channel_id: str) -> bool:
        """Determine if a message should be recovered"""
        # Create unique message ID
        msg_id = f"{channel_id}_{message.get('ts', '')}"
        
        # Skip if already processed
        if msg_id in self.processed_messages:
            logger.debug(f"Skipping already processed message: {msg_id}")
            return False
            
        # Skip bot messages
        if message.get('bot_id') or message.get('subtype'):
            logger.debug(f"Skipping bot message: {msg_id}")
            return False
            
        # Skip messages without text
        if not message.get('text', '').strip():
            logger.debug(f"Skipping message without text: {msg_id}")
            return False
            
        # Skip our own bot messages
        if message.get('user') == self.slack_handler.bot_app_id:
            logger.debug(f"Skipping our own bot message: {msg_id}")
            return False
        
        # Check if message is already in the current message store
        current_messages = self.slack_handler.message_store.get_messages(channel_id, message.get('thread_ts'))
        for stored_msg in current_messages:
            if stored_msg.timestamp == float(message.get('ts', 0)):
                logger.debug(f"Message already in message store, marking as processed: {msg_id}")
                self.processed_messages.add(msg_id)
                return False
        
        logger.info(f"Message eligible for recovery: {msg_id} - {message.get('text', '')[:50]}")
        return True
        
    def _recover_message(self, message: dict, channel_id: str):
        """Process a recovered message"""
        try:
            # Create message ID and mark as processed
            msg_id = f"{channel_id}_{message.get('ts', '')}"
            self.processed_messages.add(msg_id)
            
            # Convert Slack message to our event format
            event = {
                'user': message.get('user'),
                'type': 'message',
                'ts': message.get('ts'),
                'text': message.get('text', ''),
                'channel': channel_id,
                'thread_ts': message.get('thread_ts'),
                'event_ts': message.get('ts'),
                'channel_type': 'channel'
            }
            
            # Enhanced recovery logging
            user = message.get('user', 'unknown')
            text = message.get('text', '')
            ts = message.get('ts', '')
            
            print("\n" + "="*50)
            print("RECOVERING DROPPED MESSAGE")
            print(f"   User: {user}")
            print(f"   Text: '{text}'")
            print(f"   Timestamp: {ts}")
            print("="*50)
            
            logger.info(f"RECOVERING MESSAGE: user={user}, text='{text}', ts={ts}")
            
            # Process through normal message handler
            self.slack_handler._process_message_event(event)
            
        except Exception as e:
            logger.error(f"Error recovering message: {e}")
            
    def mark_message_processed(self, channel_id: str, ts: str):
        """Mark a message as processed to avoid duplicate recovery"""
        msg_id = f"{channel_id}_{ts}"
        self.processed_messages.add(msg_id)
        
        # Clean up old processed messages to prevent memory growth
        if len(self.processed_messages) > 10000:
            # Keep only recent 5000 messages
            self.processed_messages = set(list(self.processed_messages)[-5000:]) 