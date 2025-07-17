# manoj_updated/maya_agent/workflow_manager.py

import json
from .database import get_draft_by_job_id, update_draft_status, delete_user_draft
# from .naveens_agent import post_job_to_linkedin, send_slack_message # MOVED
import os

def resume_workflow(job_id: str, clicked_action: str, user_data: dict):
    """
    Resumes the job posting workflow based on user's button click.
    """
    from .naveens_agent import post_job_to_linkedin, send_slack_message # MOVED HERE

    user_id = user_data.get("user_id")
    user_name = user_data.get("user_name")
    channel_id = user_data.get("channel_id")

    job_draft = get_draft_by_job_id(job_id)

    if not job_draft:
        print(f"❌ Error: Could not find job draft with job_id: {job_id}")
        send_slack_message(channel_id, "Sorry, I couldn't find that job request. It might have expired or been completed already.")
        return

    if clicked_action == "approve_click":
        print(f"✅ Resuming 'approve' workflow for job_id: {job_id}")
        
        # Reconstruct the state needed for the posting function
        # The job_draft from the DB contains all the columns as dict keys
        agent_state = {
            "user_id": user_id,
            "user_name": user_name,
            "channel_id": channel_id,
            "job_data": job_draft,  # Pass the whole draft dict
            "error": None,
            "job_result": "",
            "edit_workflow_active": None
        }
        
        # Update status to prevent re-processing
        update_draft_status(job_id, "processing")
        
        # Call the LinkedIn posting function
        post_job_to_linkedin(agent_state)
        
        # Once posted, we can consider deleting the draft or marking as completed
        update_draft_status(job_id, "completed")

    elif clicked_action == "reject_click":
        print(f"❌ Resuming 'reject' workflow for job_id: {job_id}")
        delete_user_draft(job_id, user_id)
        print(f"🗑️ Job draft {job_id} has been deleted.")

    elif clicked_action == "draft_click":
        print(f"📄 Resuming 'draft' workflow for job_id: {job_id}")
        # The job is already a draft, but we'll move it from 'pending_approval' to 'active'
        update_draft_status(job_id, "active")
        print(f"✅ Job draft {job_id} marked as active.")

    elif clicked_action == "edit_click":
        print(f"✏️ Resuming 'edit' workflow for job_id: {job_id}")
        
        # Set user's state to edit mode using the JSON file
        edit_mode_path = os.path.join(os.path.dirname(__file__), '..', 'edit_mode.json')
        try:
            with open(edit_mode_path, 'r') as f:
                edit_mode_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            edit_mode_data = {}

        edit_mode_data[user_id] = {
            "status": True,
            "message": job_draft.get("description"),
            "job_id": job_id,
            "channel_id": channel_id,
            "user_name": user_name,
            "job_data": job_draft
        }

        with open(edit_mode_path, 'w') as f:
            json.dump(edit_mode_data, f)
            
        # Send message to user asking for edits
        message = f"✏️ Okay, <@{user_id}>! What would you like to change in the job description for *{job_draft.get('job_title')}*?"
        send_slack_message(channel_id, message)

    else:
        print(f"❓ Unknown action '{clicked_action}' for job_id: {job_id}") 