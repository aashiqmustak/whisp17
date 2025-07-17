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
# from .workflow_manager import resume_workflow # MOVED

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
    from .workflow_manager import resume_workflow # MOVED HERE

    # 🔍 Decode block_id JSON to extract job_id and user_name
    try:
        block_metadata = json.loads(action.get("block_id", "{}"))
        job_id = block_metadata.get("job_id")
        user_name = block_metadata.get("user_name", "user")
        user_id = block_metadata.get("user_id", "123")
        is_edit_workflow = block_metadata.get("is_edit_workflow", False)  # New flag for edit workflow
    except Exception as e:
        print("⚠ Failed to parse block_id metadata:", e)
        return

    clicked_action = action["action_id"]
    message_ts = body["message"]["ts"]
    channel_id = body["channel"]["id"]

    print(f"🖱 Button clicked: {clicked_action} for job_id: {job_id} by @{user_name}")

    user_data = {
        "user_id": user_id,
        "user_name": user_name,
        "channel_id": channel_id,
    }

    # Run the workflow in a separate thread to avoid blocking
    workflow_thread = Thread(target=resume_workflow, args=(job_id, clicked_action, user_data))
    workflow_thread.start()

    # Update the message to give immediate feedback
    if clicked_action == "approve_click":
        result_text = f"✅ Thanks for the confirmation, <@{user_id}>. I'm now posting the job to LinkedIn. This may take a moment."
    elif clicked_action == "reject_click":
        result_text = f"❌ No worries <@{user_id}>, I’ve canceled the posting."
    elif clicked_action == "edit_click":
        result_text = f"✏️ Okay, <@{user_id}>! I'm ready for your edits. What would you like to change?"
    elif clicked_action == "draft_click":
        result_text = f"📋 Got it, <@{user_id}>. I've moved this to your drafts."
    else:
        result_text = "❓ Action recorded."

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
    
    # 👉 Encode user info into block_id as JSON (removed job_desc to fix character limit)
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

    print(f"✅ Message with buttons sent for job_id: {job_id}. Not waiting for response.")
    # No longer waiting, so we return immediately
    return "pending"

@app.action("approve_click")
def handle_approve(ack, body, client, action):
    ack()
    block_metadata = json.loads(action.get("block_id", "{}"))
    user_id = block_metadata.get("user_id", "user")
    result_text = f"✅ Perfect! I'm posting your job to LinkedIn now..."
    _update_slack_message(client, body, result_text)
    # ... set response_values ...
    job_id = block_metadata.get("job_id")
    response_values[job_id] = "approve"

@app.action("reject_click")
def handle_reject(ack, body, client, action):
    ack()
    block_metadata = json.loads(action.get("block_id", "{}"))
    user_id = block_metadata.get("user_id", "user")
    result_text = f"❌ No problem! I've discarded this job posting."
    _update_slack_message(client, body, result_text)
    job_id = block_metadata.get("job_id")
    response_values[job_id] = "reject"

@app.action("edit_click")
def handle_edit(ack, body, client, action):
    ack()
    block_metadata = json.loads(action.get("block_id", "{}"))
    user_id = block_metadata.get("user_id", "user")
    result_text = f"✏️ Sure! Please provide your edits."
    _update_slack_message(client, body, result_text)
    job_id = block_metadata.get("job_id")
    response_values[job_id] = "edit"

@app.action("draft_click")
def handle_draft(ack, body, client, action):
    ack()
    block_metadata = json.loads(action.get("block_id", "{}"))
    user_id = block_metadata.get("user_id", "user")
    result_text = f"📄 Got it! I've moved this job to your drafts folder."
    _update_slack_message(client, body, result_text)
    job_id = block_metadata.get("job_id")
    response_values[job_id] = "draft"

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