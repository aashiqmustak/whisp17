import os
import json
import uuid
from typing import Dict, Any
import logging
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain.prompts import ChatPromptTemplate

# Import the state manager
from edit_state_manager import clear_user_edit_mode

load_dotenv()
logger = logging.getLogger(__name__)


def edit_rag(user_id: str, username: str, channel_id: str, edit_instructions: str, 
             original_message: str, slack_handler=None) -> Dict[str, Any]:
    """
    Process edit instructions and generate updated job description.
    
    Args:
        user_id: User ID
        username: User's display name
        channel_id: Slack channel ID
        edit_instructions: User's edit instructions
        original_message: Original job description message
        slack_handler: Slack handler instance for posting messages
        
    Returns:
        Dictionary with success status and updated job description
    """
    try:
        logger.info(f"Processing edit request for user {user_id}")
        
        # Initialize LLM
        llm = ChatNVIDIA(
            model="meta/llama3-70b-instruct",
            api_key=os.getenv("NVIDIA_API_KEY")
        )
        
        # Create prompt for job description editing
        edit_prompt = ChatPromptTemplate.from_template("""
You are a smart job description editor. Your task is to update the given job description based on the user's specific edit instructions.

Instructions:
- ONLY update the fields or aspects mentioned in the edit instructions
- DO NOT add fictional or speculative information
- MAINTAIN the original job description's formatting, professionalism, and clarity
- If the edit instructions are unclear, make reasonable interpretations but stay conservative
- Your output should be the complete updated job description
- Do NOT include any introductory text or explanations

Original Job Description:
{original_job_description}

Edit Instructions:
{edit_instructions}

Updated Job Description:
""")
        
        # Extract job description from the original message
        job_description = extract_job_description(original_message)
        
        # Generate updated job description
        updated_description = llm.invoke(
            edit_prompt.format(
                original_job_description=job_description,
                edit_instructions=edit_instructions
            )
        ).content
        
        # Send updated job description to Slack
        success = send_updated_job_to_slack(
            channel_id, updated_description, user_id, username, slack_handler
        )
        
        if success:
            # Clear edit mode for the user
            clear_user_edit_mode(user_id)
            logger.info(f"Successfully processed edit request for user {user_id}")
            
            return {
                "status": "success",
                "updated_description": updated_description,
                "message": "Job description updated successfully"
            }
        else:
            logger.error(f"Failed to send updated job description to Slack for user {user_id}")
            return {
                "status": "error",
                "message": "Failed to send updated job description to Slack"
            }
            
    except Exception as e:
        logger.error(f"Error processing edit request for user {user_id}: {e}")
        return {
            "status": "error",
            "message": f"Error processing edit request: {str(e)}"
        }


def extract_job_description(original_message: str) -> str:
    """
    Extract job description from the original Slack message.
    
    Args:
        original_message: Full Slack message with user mentions and text
        
    Returns:
        Clean job description text
    """
    # Remove user mentions and extra text
    lines = original_message.split('\n')
    job_desc_lines = []
    
    # Skip the first line if it contains user mention
    start_idx = 0
    if lines and lines[0].startswith('Hey @'):
        start_idx = 1
    
    # Find the actual job description content
    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        if line and not line.startswith('Does this look okay?'):
            job_desc_lines.append(line)
        elif line.startswith('Does this look okay?'):
            break
    
    return '\n'.join(job_desc_lines).strip()


def send_updated_job_to_slack(channel_id: str, updated_description: str, 
                             user_id: str, username: str, slack_handler=None) -> bool:
    """
    Send updated job description to Slack with approval buttons.
    
    Args:
        channel_id: Slack channel ID
        updated_description: Updated job description
        user_id: User ID
        username: User's display name
        slack_handler: Slack handler instance
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        from maya_agent.slack_button_n import send_job_desc
        
        # Generate new job ID for the updated description
        job_id = str(uuid.uuid4())[:8]
        
        logger.info(f"Sending updated job description to Slack for user {user_id}")
        
        # Send the updated job description with approval buttons
        action = send_job_desc(channel_id, updated_description, job_id, username, user_id)
        
        logger.info(f"Updated job description sent successfully for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending updated job description to Slack: {e}")
        return False


def validate_edit_instructions(edit_instructions: str) -> bool:
    """
    Validate edit instructions to ensure they're not empty or invalid.
    
    Args:
        edit_instructions: User's edit instructions
        
    Returns:
        True if valid, False otherwise
    """
    if not edit_instructions or not edit_instructions.strip():
        return False
    
    # Check if it's just whitespace or very short
    if len(edit_instructions.strip()) < 3:
        return False
    
    return True 