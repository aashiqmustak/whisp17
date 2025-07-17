import json
import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Path to the edit state file
EDIT_STATE_FILE = "edit_mode.json"


def load_state() -> Dict[str, Any]:
    """
    Load the edit state from JSON file.
    
    Returns:
        Dict containing user edit states. Empty dict if file doesn't exist.
    """
    try:
        if not os.path.exists(EDIT_STATE_FILE):
            logger.info(f"Edit state file {EDIT_STATE_FILE} not found, returning empty state")
            return {}
        
        with open(EDIT_STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
            logger.debug(f"Loaded edit state for {len(state)} users")
            return state
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {EDIT_STATE_FILE}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading edit state: {e}")
        return {}


def save_state(state: Dict[str, Any]) -> bool:
    """
    Save the edit state to JSON file.
    
    Args:
        state: Dictionary containing user edit states
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open(EDIT_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved edit state for {len(state)} users")
        return True
    except Exception as e:
        logger.error(f"Error saving edit state: {e}")
        return False


def get_user_edit_status(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get edit status for a specific user.
    
    Args:
        user_id: User ID to check
        
    Returns:
        User's edit state dict if exists, None otherwise
    """
    state = load_state()
    return state.get(user_id)


def set_user_edit_mode(user_id: str, message: str) -> bool:
    """
    Set a user to edit mode with the original message.
    
    Args:
        user_id: User ID
        message: Original job description message
        
    Returns:
        True if set successfully, False otherwise
    """
    state = load_state()
    state[user_id] = {
        "status": True,
        "message": message
    }
    result = save_state(state)
    if result:
        logger.info(f"Set user {user_id} to edit mode")
    return result


def clear_user_edit_mode(user_id: str) -> bool:
    """
    Clear edit mode for a user.
    
    Args:
        user_id: User ID to clear
        
    Returns:
        True if cleared successfully, False otherwise
    """
    state = load_state()
    if user_id in state:
        state[user_id]["status"] = False
        result = save_state(state)
        if result:
            logger.info(f"Cleared edit mode for user {user_id}")
        return result
    return True  # User not in edit mode, nothing to clear


def is_user_in_edit_mode(user_id: str) -> bool:
    """
    Check if a user is currently in edit mode.
    
    Args:
        user_id: User ID to check
        
    Returns:
        True if user is in edit mode, False otherwise
    """
    user_state = get_user_edit_status(user_id)
    return user_state is not None and user_state.get("status", False) is True


def get_user_original_message(user_id: str) -> Optional[str]:
    """
    Get the original message for a user in edit mode.
    
    Args:
        user_id: User ID
        
    Returns:
        Original message if user is in edit mode, None otherwise
    """
    user_state = get_user_edit_status(user_id)
    if user_state and user_state.get("status", False):
        return user_state.get("message")
    return None 