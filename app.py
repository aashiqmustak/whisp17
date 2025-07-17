import json
import logging
import time
from threading import Thread
from flask import Flask, jsonify

from config import Config
from slack_handler import SlackHandler

logger = logging.getLogger(__name__)

# Global variables
app = Flask(__name__)
slack_handler = None
slack_connection_failed = False


def create_app():
    global slack_handler, slack_connection_failed
    
    app.config['DEBUG'] = Config.DEBUG
    
    try:
        # Just create the SlackHandler, don't start it yet
        slack_handler = SlackHandler(Config.get_slack_config())
        logger.info("Slack handler created (not started yet)")
    except Exception as e:
        slack_connection_failed = True
        logger.error(f"Slack handler creation failed: {e}")
    
    return app


@app.route('/health', methods=['GET'])
def health_check():
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': time.time(),
            'components': {
                'flask': 'healthy',
                'slack_handler': 'unknown',
                'ml_integration': 'enabled'
            }
        }
        
        if slack_connection_failed:
            health_status['components']['slack_handler'] = 'disconnected'
            health_status['status'] = 'degraded'
        elif slack_handler:
            try:
                stats = slack_handler.get_stats()
                health_status['components']['slack_handler'] = 'healthy'
                health_status['slack_stats'] = stats
            except Exception as e:
                health_status['components']['slack_handler'] = 'unhealthy'
        
        return jsonify(health_status), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }), 500


@app.route('/stats', methods=['GET'])
def get_stats():
    try:
        if slack_connection_failed:
            return jsonify({
                'status': 'slack_disconnected',
                'timestamp': time.time()
            }), 503
            
        if not slack_handler:
            return jsonify({'error': 'Slack handler not initialized'}), 503
        
        stats = slack_handler.get_stats()
        return jsonify(stats), 200
        
    except Exception as e:
        logger.error(f"Stats endpoint failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/ready', methods=['GET'])
def readiness_check():
    try:
        if slack_connection_failed:
            return jsonify({
                'ready': True, 
                'status': 'flask_only'
            }), 200
            
        if not slack_handler:
            return jsonify({'ready': False}), 503
        
        return jsonify({'ready': True}), 200
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'ready': False, 'error': str(e)}), 500


@app.route('/outcomes/<channel_id>', methods=['GET'])
@app.route('/outcomes/<channel_id>/<thread_ts>', methods=['GET'])
def get_final_outcomes(channel_id, thread_ts=None):
    try:
        if slack_connection_failed or not slack_handler:
            return jsonify({'error': 'Slack handler not available'}), 503
        
        outcomes_json = slack_handler.get_final_outcomes_json(channel_id, thread_ts)
        
        return jsonify({
            'channel_id': channel_id,
            'thread_ts': thread_ts,
            'outcomes': json.loads(outcomes_json)
        }), 200
        
    except Exception as e:
        logger.error(f"Final outcomes endpoint failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/status', methods=['GET'])
def app_status():
    try:
        status = {
            'app': 'Flask + Slack Bot',
            'version': '1.0.0',
            'timestamp': time.time(),
            'flask_server': 'running',
            'slack_integration': 'disconnected' if slack_connection_failed else ('connected' if slack_handler else 'not_initialized'),
            'ml_integration': 'enabled',
            'batch_timeout': f"{Config.BATCH_TIMEOUT_SECONDS}s",
            'max_batch_size': Config.MAX_BATCH_SIZE
        }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Status endpoint failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/debug', methods=['GET'])
def debug_state():
    try:
        if slack_connection_failed or not slack_handler:
            return jsonify({'error': 'Slack handler not available'}), 503
        
        debug_info = {
            'message_store_stats': slack_handler.message_store.get_stats(),
            'active_timers': list(slack_handler.timer_manager.get_active_timers()),
            'timer_count': slack_handler.timer_manager.get_timer_count(),
            'timestamp': time.time()
        }
        
        # Get detailed message store contents
        all_messages = {}
        for channel_id, threads in slack_handler.message_store._messages.items():
            all_messages[channel_id] = {}
            for thread_key, messages in threads.items():
                all_messages[channel_id][thread_key] = [
                    {
                        'user_id': msg.user_id,
                        'username': msg.username,
                        'text': msg.text,
                        'timestamp': msg.timestamp
                    } for msg in messages
                ]
        
        debug_info['current_messages'] = all_messages
        
        return jsonify(debug_info), 200
        
    except Exception as e:
        logger.error(f"Debug endpoint failed: {e}")
        return jsonify({'error': str(e)}), 500


# Initialize the app
create_app()