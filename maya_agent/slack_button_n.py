#gives warning

import os
import time
import uuid
import sys
from threading import Thread
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from threading import Event
import json
from dotenv import load_dotenv

# Import database functions and other necessary logic
from maya_agent.database import get_draft_by_job_id, delete_user_draft, update_draft
from edit_rag.edit_formatter import run_job_rewrite_pipeline


# Step 1: go up one directory level from this script's location
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Step 2: load the .env file
load_dotenv(dotenv_path=env_path)
# ====== Slack Tokens ======
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")


# ====== Init Slack App ======
app = App(token=SLACK_BOT_TOKEN)
 # job_id → "approve"/"reject"/"edit"


response_events = {}   # job_id → Event object
response_values = {}   # job_id → "approve" / "reject" / "edit"
job_storage = {}       # job_id → job_description storage

# ====== Button Click Handler ======
@app.action("approve_click")
@app.action("reject_click")
@app.action("edit_click")
@app.action("draft_click")
def handle_button_click(ack, body, client, action):
    ack()

    # 🔍 Decode block_id JSON to extract job_id and user_name
    try:
        block_metadata = json.loads(action.get("block_id", "{}"))
        job_id = block_metadata.get("job_id")
        user_name = block_metadata.get("user_name", "user")
        user_id= block_metadata.get("user_id","123")
        is_edit_workflow = block_metadata.get("is_edit_workflow", False)  # New flag for edit workflow
    except Exception as e:
        print("⚠ Failed to parse block_id metadata:", e)
        job_id = "unknown"
        user_name = "user"
        is_edit_workflow = False

    clicked_action = action["action_id"]
    message_ts = body["message"]["ts"]
    channel_id = body["channel"]["id"]

    print(f"🖱 Button clicked: {clicked_action} for job_id: {job_id} by @{user_name}")

    # Retrieve the job from the database
    job_data = get_draft_by_job_id(job_id)
    if not job_data:
        result_text = f"❌ Sorry <@{user_id}>, I couldn't find the original job data. It might have expired or been deleted."
        _update_slack_message(client, body, result_text)
        return

    if clicked_action == "approve_click":
        result_text = f"✅ Thanks for the confirmation, <@{user_id}>. I'm now posting the job on LinkedIn."
        # In a real scenario, you would trigger the LinkedIn posting logic here.
        # For now, we'll just confirm to the user.
        delete_user_draft(job_id, user_id) # Clean up the draft
    elif clicked_action == "reject_click":
        result_text = f"❌ No worries <@{user_id}>, I’ve canceled the posting."
        delete_user_draft(job_id, user_id) # Clean up the draft
    elif clicked_action == "edit_click":
        # The user wants to edit. We'll set the edit mode state.
        edit_mode_path = os.path.join(os.path.dirname(__file__), '..', 'edit_mode.json')
        try:
            with open(edit_mode_path, 'r') as f:
                edit_mode = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            edit_mode = {}
        
        edit_mode[user_id] = {
            "status": True,
            "message": job_data.get("description", ""),
            "job_id": job_id,
            "channel_id": channel_id,
            "user_name": user_name,
            "job_data": job_data
        }
        
        with open(edit_mode_path, 'w') as f:
            json.dump(edit_mode, f)
            
        result_text = f"✏ Got it <@{user_id}>, I've marked this for editing. Please provide the necessary changes."
        
    elif clicked_action == "draft_click":
        result_text = f"📋 Got it <@{user_id}>, I've saved this job to your drafts."
        # The job is already in the drafts, so we just confirm.
        # Optionally, you could update a status field here.
    else:
        result_text = f"❓ Unknown action clicked."

    # Update the message in Slack to show the result
    _update_slack_message(client, body, result_text)


def _update_slack_message(client, body, result_text):
    message_ts = body["message"]["ts"]
    channel_id = body["channel"]["id"]
    client.chat_update(
        channel=channel_id,
        ts=message_ts,
        text="Response recorded.",
        blocks=[{
            "type": "section",
            "text": {"type": "mrkdwn", "text": result_text}
        }]
    )


# ====== Send Job Description to Slack ======
def send_job_desc(CHANNEL_ID, JOB_DESC, job_id, user_name, user_id):
    client = app.client

    # 👉 Encode user info into block_id as JSON
    block_metadata = json.dumps({
        "job_id": job_id, 
        "user_name": user_name,
        "user_id": user_id
    })

    print(f"📤 Posting to Slack | job_id: {job_id}")
    client.chat_postMessage(
        channel=CHANNEL_ID,
        text="Choose an action:",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Hey @{user_name}, here's your job description:\n\n{JOB_DESC}\n\nWhat would you like to do?"}
            },
            {
                "type": "actions",
                "block_id": block_metadata,  # embedded job_id + user_name
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ Yes, Post it"}, "action_id": "approve_click", "style": "primary"},
                    {"type": "button", "text": {"type": "plain_text", "text": "❌ No, Discard it"}, "action_id": "reject_click", "style": "danger"},
                    {"type": "button", "text": {"type": "plain_text", "text": "✏️ Edit"}, "action_id": "edit_click"},
                    {"type": "button", "text": {"type": "plain_text", "text": "📄 Move to Draft"}, "action_id": "draft_click"}
                ]
            }
        ]
    )

    # NO MORE WAITING! The function returns immediately.
    print(f"✅ Message sent for job_id: {job_id}. Not waiting for response.")

@app.action("approve_click")
def handle_approve(ack, body, client, action):
    # This function is now handled by the generic handle_button_click
    pass

@app.action("reject_click")
def handle_reject(ack, body, client, action):
    # This function is now handled by the generic handle_button_click
    pass

@app.action("edit_click")
def handle_edit(ack, body, client, action):
    # This function is now handled by the generic handle_button_click
    pass

@app.action("draft_click")
def handle_draft(ack, body, client, action):
    # This function is now handled by the generic handle_button_click
    pass