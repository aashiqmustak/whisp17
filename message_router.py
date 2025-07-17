import logging
from typing import Dict, Any, List
from edit_state_manager import is_user_in_edit_mode, get_user_original_message
from edit_rag_processor import edit_rag, validate_edit_instructions

logger = logging.getLogger(__name__)


def route_user_message(user_id: str, username: str, channel_id: str, 
                      user_messages: List[str], slack_handler=None) -> Dict[str, Any]:
    """
    Route user message to either edit_rag or normal rag pipeline based on edit mode status.
    
    Args:
        user_id: User ID
        username: User's display name
        channel_id: Slack channel ID
        user_messages: List of user messages to process
        slack_handler: Slack handler instance
        
    Returns:
        Dictionary with routing result and processing information
    """
    try:
        logger.info(f"Routing message for user {user_id}")
        
        # Check if user is in edit mode
        if is_user_in_edit_mode(user_id):
            logger.info(f"User {user_id} is in edit mode, routing to edit_rag")
            return route_to_edit_rag(user_id, username, channel_id, user_messages, slack_handler)
        else:
            logger.info(f"User {user_id} is in normal mode, routing to rag")
            return route_to_normal_rag(user_id, username, channel_id, user_messages, slack_handler)
            
    except Exception as e:
        logger.error(f"Error routing message for user {user_id}: {e}")
        return {
            "status": "error",
            "message": f"Error routing message: {str(e)}",
            "route": "error"
        }


def route_to_edit_rag(user_id: str, username: str, channel_id: str, 
                     user_messages: List[str], slack_handler=None) -> Dict[str, Any]:
    """
    Route message to edit_rag pipeline.
    
    Args:
        user_id: User ID
        username: User's display name
        channel_id: Slack channel ID
        user_messages: List of edit instructions
        slack_handler: Slack handler instance
        
    Returns:
        Dictionary with edit processing result
    """
    try:
        # Get original message from edit state
        original_message = get_user_original_message(user_id)
        if not original_message:
            logger.error(f"No original message found for user {user_id} in edit mode")
            return {
                "status": "error",
                "message": "No original message found for editing",
                "route": "edit_rag"
            }
        
        # Combine user messages into edit instructions
        edit_instructions = " ".join(user_messages).strip()
        
        # Validate edit instructions
        if not validate_edit_instructions(edit_instructions):
            logger.warning(f"Invalid edit instructions from user {user_id}: {edit_instructions}")
            return {
                "status": "error",
                "message": "Please provide clear edit instructions",
                "route": "edit_rag"
            }
        
        # Process edit request
        result = edit_rag(
            user_id=user_id,
            username=username,
            channel_id=channel_id,
            edit_instructions=edit_instructions,
            original_message=original_message,
            slack_handler=slack_handler
        )
        
        result["route"] = "edit_rag"
        return result
        
    except Exception as e:
        logger.error(f"Error processing edit request for user {user_id}: {e}")
        return {
            "status": "error",
            "message": f"Error processing edit request: {str(e)}",
            "route": "edit_rag"
        }


def route_to_normal_rag(user_id: str, username: str, channel_id: str, 
                       user_messages: List[str], slack_handler=None) -> Dict[str, Any]:
    """
    Route message to normal rag pipeline.
    
    Args:
        user_id: User ID
        username: User's display name
        channel_id: Slack channel ID
        user_messages: List of user messages
        slack_handler: Slack handler instance
        
    Returns:
        Dictionary with normal rag processing result
    """
    try:
        logger.info(f"Processing normal rag request for user {user_id}")
        
        # Return success without recursive processing
        # The actual processing will be handled by the fallback logic in process_messages
        return {
            "status": "success",
            "message": "Routed to normal rag pipeline",
            "route": "normal_rag",
            "should_process": True,  # Flag to indicate processing should continue
            "user_messages": user_messages,
            "user_id": user_id,
            "username": username,
            "channel_id": channel_id
        }
        
    except Exception as e:
        logger.error(f"Error processing normal rag request for user {user_id}: {e}")
        return {
            "status": "error",
            "message": f"Error processing normal rag request: {str(e)}",
            "route": "normal_rag"
        }


def should_bypass_router(user_messages: List[str]) -> bool:
    """
    Check if messages should bypass the router for special handling.
    
    Args:
        user_messages: List of user messages
        
    Returns:
        True if should bypass router, False otherwise
    """
    # Check for specific job actions that should be handled separately
    combined_text = " ".join(user_messages).lower()
    
    # Past request indicators
    past_indicators = [
        "past", "previous", "history", "drafts", "show me my", 
        "what are my", "my jobs", "old jobs", "earlier", "before"
    ]
    
    # Specific job action patterns
    import re
    edit_pattern = r'edit[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
    delete_pattern = r'delete[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
    show_pattern = r'show[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
    
    # Check if it's a past request or specific job action
    is_past_request = any(indicator in combined_text for indicator in past_indicators)
    is_specific_action = bool(re.search(edit_pattern, combined_text) or 
                             re.search(delete_pattern, combined_text) or 
                             re.search(show_pattern, combined_text))
    
    return is_past_request or is_specific_action


def should_bypass_router_for_user(user_id: str, user_messages: List[str]) -> bool:
    """
    Check if messages should bypass the router for special handling, considering user edit mode.
    
    Args:
        user_id: User ID
        user_messages: List of user messages
        
    Returns:
        True if should bypass router, False otherwise
    """
    # If user is in edit mode, don't bypass the router - route to edit RAG
    if is_user_in_edit_mode(user_id):
        logger.info(f"User {user_id} is in edit mode, not bypassing router")
        return False
    
    # Otherwise, use the regular bypass logic
    return should_bypass_router(user_messages) 