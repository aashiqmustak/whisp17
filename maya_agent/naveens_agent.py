import os
import requests
from typing import TypedDict, Optional, Any
import json
from dotenv import load_dotenv
from rag_it1.logic_editor import RoundRobinQueueManager
from rag_it1.rag_processor import process_single_user
import threading
# from redis_manager import RedisManager # No longer needed
# Step 1: go up one directory level from this script's location
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
queue_manager = RoundRobinQueueManager()
# Step 2: load the .env file
load_dotenv(dotenv_path=env_path)

SLACK_BOT = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = None

import requests
from langgraph.graph import StateGraph, START, END
import uuid
from threading import Thread
# from maya_agent.slack_button_n import app as slack_app, SLACK_APP_TOKEN # MOVED
from slack_bolt.adapter.socket_mode import SocketModeHandler
# from maya_agent.slack_button_n import send_job_desc # MOVED
from rag_it1.retrieval.vectorstore import get_vectorstore
from maya_agent.database import insert_draft, update_draft_status

# The Slack App needs to be initialized here for the SocketModeHandler to work
from maya_agent.slack_button_n import app as slack_app, SLACK_APP_TOKEN
Thread(target=lambda: SocketModeHandler(slack_app, SLACK_APP_TOKEN).start(), daemon=True).start()

# ========== Config ==========
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
PERSON_URN = os.getenv("PERSON_URN")

OLLAMA_URL = os.getenv("OLLAMA_URL")

def send_slack_message(channel_id, text):#Add Channel_id as a paramater
    headers = {
        "Authorization": f"Bearer {SLACK_BOT}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    data = {
        "channel": channel_id,
        "text": text,
    }
    print(channel_id)
    response = requests.post("https://slack.com/api/chat.postMessage", json=data, headers=headers)#Add username and user_id
 
    return response.json()



user_id = None
user_name = None

# ========== State Schema ==========
class AgentState(TypedDict):
    user_id: str
    user_name: str
    channel_id: str
    job_data: dict[str, Any]
    error: Optional[str]
    job_result: str
    edit_workflow_active: Optional[bool]

# ========== Node: Job Requirement Validation ==========
REQUIRED_FIELDS = [
    "job_title", "company", "job_type",
    "experience",  "skills"
   
]

def delete_user_data(user_id: str):
    """
    Delete all documents from the vectorstore associated with a given user_id.
    """
    try:
        vectorstore = get_vectorstore()
        collection = vectorstore._collection  # Low-level access to Chroma collection

        # Perform deletion based on metadata filter
        deleted = collection.delete(where={"user_id": user_id})

        print(f"✅ Successfully deleted data for user_id: {user_id}")
        return {"status": "success", "user_id": user_id, "deleted": deleted}
    except Exception as e:
        print(f"❌ Failed to delete data for user_id: {user_id} - {str(e)}")
        return {"status": "error", "user_id": user_id, "error": str(e)}

def job_req(state: AgentState) -> AgentState:
    print("🛡 [job_req] Checking required fields...")

    user_id = state["user_id"]
    user_name = state["user_name"]
    channel_id = state["channel_id"]

    job = state.get("job_data", {})
    missing = []

    for field in REQUIRED_FIELDS:
        if field not in job:
            missing.append(field)
        else:
            val = job[field]
            if (
                val is None or
                (isinstance(val, str) and (not val.strip() or val.strip().lower() == "null")) or
                (isinstance(val, list) and not val)
            ):
                missing.append(field)

    if missing:
        message = f"Hey <@{user_id}>, I’m almost ready to generate the job description — just need these missing details: {', '.join(missing)}. Mind sending them over?"
        print(channel_id)
        try:
            send_slack_message(channel_id, message)
        except Exception as e:
            print(f"Error sending slack message: {e}")
        print("###")
        print("warning msg to slack")
        print(message,user_id)
        state["error"] = f"❌{user_name} can you give  Missing required fields: {', '.join(missing)}"
        state["job_result"] = state["error"]
        print(state["error"])
    else:
        state["error"] = None
        print("✅ All required fields are present.")

    return state




# ========== Node: Job Description ==========
def job_description_llm(state: AgentState) -> AgentState:#add Channel id as a parameter
    print("🧠 [job_description_llm]")
    from maya_agent.slack_button_n import send_job_desc # MOVED HERE

    user_id = state["user_id"]
    user_name = state["user_name"]
    channel_id = state["channel_id"]

    job = state.get("job_data", {})
    job_title = job.get("job_title", "Job")
    experience = job.get("experience", "N/A")
    location = job.get("location", "Remote")
    skills = job.get("skills", "null")

    prompt = (
        f"Write a professional LinkedIn job description for the following role:\n"
        f"Title: {job_title}\n"
        f"Experience: {experience}\n"
        f"Location: {location}\n"
        f"Skills: {skills}\n"
        "Write the output below 2500 characters"
    )

    try:
        if not OLLAMA_URL:
            raise ValueError("OLLAMA_URL environment variable is not set")
        res = requests.post(OLLAMA_URL, json={
            "model": "llama3.2:1b",
            "prompt": prompt,
            "stream": False
        }, timeout=60)
        res.raise_for_status()
        description = res.json()["response"]

        state["job_data"]["llm_description"] = description
        # 🔁 Slack interactive part
        job_id = str(uuid.uuid4())[:8]
 
        # First, save the generated job description as a draft
        insert_draft(
            job_id=job_id,
            user_id=user_id,
            username=user_name,
            channel_id=channel_id,
            job_data=job,
            description=description,
            status="pending_approval"  # New status
        )
 
        if user_id:
            delete_user_data(user_id)
         
        # Now, send the message with buttons, but don't wait
        action = send_job_desc(channel_id, description, job_id, user_name, user_id)
         
        # The 'action' will now be 'pending', so we halt the workflow here.
        # The workflow will be resumed by the workflow_manager when a button is clicked.
        if action == "pending":
            print(f"⌛ Job {job_id} is pending user approval. Halting workflow.")
            state["error"] = "WORKFLOW_PENDING" # Special state to stop the graph
    except Exception as e:
        state["error"] = f"❌ LLM Error: {e}"
        state["job_data"]["llm_description"] = "⚠ Failed to generate description."
        print(state["error"])
         
    return state

# ========== Node: Post Job ==========
def post_job_to_linkedin(state: AgentState) -> AgentState:
    print("🚀 [post_job]")

    user_id = state["user_id"]
    user_name = state["user_name"]
    channel_id = state["channel_id"]

    job = state.get("job_data", {})
    job_title = job.get("job_title", "Job Opening")
    experience = job.get("experience", "N/A")
    location = job.get("location", "Remote")
    skills = job.get("skills", "null")
    description = job.get("llm_description", "")

    post_text = (
        f"🚀 New Job Opportunity!\n\n"
        f"📌 Title: {job_title}\n"
        f"🧠 Experience: {experience}\n"
        f"📍 Location: {location}\n"
        f"🛠 Skills: {skills}\n\n"
        f"{description}\n\n"
        "#Hiring #JobOpening #Careers"
    )

    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    payload = {
        "author": PERSON_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    try:
        res = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload)

        if res.status_code == 201:
            post_id = res.headers.get("x-restli-id", "unknown")
            post_url = f"@{user_name} -> https://www.linkedin.com/feed/update/{post_id}"
            state["job_result"] = f"✅ Posted: {post_url}"
            print("jobposting url:")
            print(post_url)
            print("####")
            # ✅ Send to Slack
            slack_message = f"✅ Job posted successfully! <@{user_id}>, here’s your LinkedIn link:\nhttps://www.linkedin.com/feed/update/{post_id}"

            send_slack_message(channel_id, slack_message)

        else:
            state["job_result"] = f"❌ Failed: {res.status_code} - {res.text}"

    except Exception as e:
        state["job_result"] = f"❌ Exception: {e}"

    return state

# ========== Node: Finalize ==========
def finalize(state: AgentState) -> AgentState:
    print("✅ [finalize]")
    print(f"📤 {state.get('job_result')}")
    return state

# ========== Build Graph ==========
graph = StateGraph(AgentState)
graph.add_node("job_req", job_req)
graph.add_node("job_description_llm", job_description_llm)
graph.add_node("post_job", post_job_to_linkedin)
graph.add_node("finalize", finalize)

# Set entry point to validation
graph.set_entry_point("job_req")

# Conditional branching from job_req
graph.add_conditional_edges(
    "job_req",
    lambda state: "error" if state.get("error") else "success",
    {
        "success": "job_description_llm",
        "error": END
    }
)

# Conditional branching from job_description_llm
graph.add_conditional_edges(
    "job_description_llm",
    lambda state: "error" if state.get("error") else "success",
    {
        "success": "post_job",
        "error": END
    }
)

graph.add_edge("post_job", "finalize")
graph.add_edge("finalize", END)

app = graph.compile()

def naveen(input_json):#Add Channel_id as a parameter
    print("[naveen] Starting LinkedIn job posting workflow...")
    print(f"Raw input: {input_json}")
    
    # Get user info from the input
    user_id = input_json["user_id"]
    user_name = input_json["username"]
    channel_id = input_json["channel_id"]
    entities = input_json.get("entities", {})
    
    # Pass user info to the state
    input_state: AgentState = {
        "user_id": user_id,
        "user_name": user_name,
        "channel_id": channel_id,
        "job_data": entities,
        "error": None,
        "job_result": "",
        "edit_workflow_active": None
    }
    
    print(f"Parsed entities: {entities}")

    print("Input to LangGraph:", input_state)

    # Invoke LangGraph app
    result = app.invoke(input_state)
    print(f"LangGraph result: {result}")
    return result