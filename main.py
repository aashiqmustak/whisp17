#!/usr/bin/env python3
"""
Main entry point for the Slack ML Integration Bot
"""

import os
import sys
import signal
import logging

from config import Config
from app import app, slack_handler, slack_connection_failed

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more verbose output
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('app.log')  # File output
    ]
)

# Set specific loggers to appropriate levels
logging.getLogger('slack_bolt').setLevel(logging.INFO)
logging.getLogger('slack_sdk').setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down...")
    if slack_handler:
        slack_handler.shutdown()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    try:
        # Start Flask server in background thread
        from threading import Thread
        flask_thread = Thread(
            target=lambda: app.run(
                host='0.0.0.0',
                port=int(os.getenv('PORT', 3001)),
                debug=False,  # Debug mode doesn't work well in threads
                use_reloader=False,
                threaded=True
            ),
            daemon=True
        )
        flask_thread.start()
        logger.info("Flask server started in background thread...")
        
        # Start Slack handler in main thread (required for Socket Mode)
        if slack_handler and not slack_connection_failed:
            logger.info("Starting Slack handler in main thread...")
            slack_handler.run()  # This will block
        else:
            logger.warning("Slack handler not available, running Flask only...")
            # Keep main thread alive
            import time
            while True:
                time.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        sys.exit(1)
    finally:
        if slack_handler:
            slack_handler.shutdown()


if __name__ == '__main__':
    main() 