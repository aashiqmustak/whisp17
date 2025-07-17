import os
import json
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain.prompts import ChatPromptTemplate
from rag_it1.retrieval.vectorstore import get_vectorstore
from edit_rag.slack_button import send_job_desc
import requests
from slack_bolt.adapter.socket_mode import SocketModeHandler
from threading import Thread
from edit_rag.slack_button import app as slack_app, SLACK_APP_TOKEN 

Thread(target=lambda: SocketModeHandler(slack_app, SLACK_APP_TOKEN).start(), daemon=True).start()
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
from maya_agent.database import insert_draft
# Import normalization logic
try:
    from intent_entity_extractor.extractor import normalize_job_title
except ImportError:
    def normalize_job_title(changes_dict, original_job_data=None):
        # Dummy fallback
        return None

# Step 2: load the .env file
load_dotenv(dotenv_path=env_path)
CHANNEL_ID= None
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
PERSON_URN = os.getenv("PERSON_URN")
SLACK_BOT = os.getenv("SLACK_BOT_TOKEN")

def send_slack_message(text):#Add Channel_id as a paramater
    headers = {
        "Authorization": f"Bearer {SLACK_BOT}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    data = {
        "channel": CHANNEL_ID,
        "text": text,
    }
    print(CHANNEL_ID)
    response = requests.post("https://slack.com/api/chat.postMessage", json=data, headers=headers)#Add username and user_id
 
    return response.json()





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

def load_job_store(file_path="job_store.json"):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_job_store(data, file_path="job_store.json"):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def store_job_description(job_json_path="job_descp.json"):
    if not os.path.exists(job_json_path):
        return {"error": f"{job_json_path} not found"}

    with open(job_json_path, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    user_id = job_data.get("user_id")
    job_desc = job_data.get("job_desc", "").strip()

    if not user_id or not job_desc:
        return {"error": "Missing user_id or job_desc"}

    job_store = load_job_store()
    job_store[user_id] = job_desc
    save_job_store(job_store)
    return {"status": "stored", "user_id": user_id}


def alter_job_description(reply, job_desc, original_job_data=None):
    # Extract what user wants to change
    llm = ChatNVIDIA(
        model="meta/llama3-70b-instruct",
        api_key=os.getenv("NVIDIA_API_KEY")
    )
    change_extractor_prompt = ChatPromptTemplate.from_template("""
    Analyze the user's edit request and extract specific changes:
    
    User's Edit Request: {reply}
    
    Extract:
    - skills_change: new skills mentioned or null
    - experience_change: new experience level or null  
    - title_change: explicit title change or null
    - location_change: new location or null
    - job_type_change: new job type or null
    
    Return JSON:
    {{"skills_change": "...", "experience_change": "...", "title_change": "...", "location_change": "...", "job_type_change": "..."}}
    """)
    # Get extracted changes
    changes = llm.invoke(change_extractor_prompt.format(reply=reply)).content
    changes_dict = json.loads(changes)
    # Apply job title normalization if skills or experience changed
    normalization_explanation = ""
    if changes_dict.get("skills_change") or changes_dict.get("experience_change"):
        normalized_title = normalize_job_title(changes_dict, original_job_data)
        if normalized_title:
            changes_dict["title_change"] = normalized_title
            normalization_explanation = f"\n\n_Note: The job title was normalized to '{normalized_title}' based on the new skills/experience provided._"
    # Update job description with normalized changes
    update_prompt = ChatPromptTemplate.from_template("""
    Apply these specific changes to the job description:
    Changes: {changes}
    Original: {job_desc}
    
    Rules:
    - Only update fields mentioned in changes
    - Maintain professional formatting
    - If title changed due to skills/experience, explain the normalization
    
    Updated Job Description:
    """)
    updated_desc = llm.invoke(update_prompt.format(changes=json.dumps(changes_dict), job_desc=job_desc)).content
    if normalization_explanation:
        updated_desc += normalization_explanation
    return {"new_job_description": updated_desc}


# ========================
# MAIN EXECUTION
# ========================
def post_job_to_linkedin(user_id,user_name,result):
    print("🚀 [post_job_to_linkedin]")


    post_text = (
        f"🚀 New Job Opportunity!\n\n"
        # f"📌 Title: {job_title}\n"
        # f"🧠 Experience: {experience}\n"
        # f"📍 Location: {location}\n"
        # f"🛠 Skills: {skills}\n\n"
        f"{result}\n\n"
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
           
            print("jobposting url:")
            print(post_url)
            print("####")
            # ✅ Send to Slack
            slack_message = f"✅ Job posted successfully! <@{user_id}>, here’s your LinkedIn link:\nhttps://www.linkedin.com/feed/update/{post_id}"

            send_slack_message(slack_message)

        else:
            print( f"❌ Failed: {res.status_code} - {res.text}")

    except Exception as e:
        print( f"❌ Exception: {e}")

  
def run_job_rewrite_pipeline(user_id, reply,job_desc,user_name,channel_id):
    

    result = alter_job_description(reply,job_desc)
    CHANNEL_ID=channel_id
    result=result["new_job_description"]
    print("\n Altered job description processed")
    import uuid
    job_id = str(uuid.uuid4())[:8] 
   
    # Fix file path to access edit_mode.json from root directory
    edit_mode_path = os.path.join(os.path.dirname(__file__), '..', 'edit_mode.json')
    
    try:
        with open(edit_mode_path, 'r') as f:
            content = f.read().strip()
            if not content:
                edit_mode = {}
            else:
                edit_mode = json.loads(content)

    except FileNotFoundError:
        edit_mode = {}
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in edit_mode.json: {e}")
        edit_mode = {}
    


    job=edit_mode[user_id]["job_data"]



    # use this channelid if there is an error in edge case

    # CHANNEL_ID= edit_mode[user_id]["channel_id"]



    # Reset user's edit mode
    if user_id in edit_mode:
        edit_mode[user_id]["status"] = False
        edit_mode[user_id]["message"] = "null"
        edit_mode[user_id]["job_id"]="null"
        edit_mode[user_id]["channel_id"]="null"
        edit_mode[user_id]["user_name"]="null"
        edit_mode[user_id]["job_data"]="null"
    
    # Write back to file
    with open(edit_mode_path, 'w') as f:
        json.dump(edit_mode, f, indent=2)
    action = send_job_desc(channel_id, result, job_id, user_name, user_id)
    print(action)
    print(f"📤 Sending updated job description to Slack | job_id: {job_id}")
    
    if action == "approve":
        print("✅ Approved by user. Proceeding...")
        if user_id:
            delete_user_data(user_id)
        post_job_to_linkedin(user_id,user_name,result)
        
    elif action == "reject":
        print("🧹 User rejected. Resetting memory and halting job.")
        if user_id:
            delete_user_data(user_id)
        print(f"User selected: {action}")

    elif action =="edit":
        print("User clicked edit, initiating edit workflow")
     
        print( "EDIT Started")


    elif action =="draft":
        print("User selected draft, sent to draft function")
        insert_draft(
            job_id=job_id,  # ← you already generated it before calling send_job_desc
            user_id=user_id,
            username=user_name,
            channel_id=CHANNEL_ID,
            job_data=job,
            description=result
        )
        if user_id:
            delete_user_data(user_id)
        
        # # Send confirmation message to Slack
        # draft_confirmation = f"✅ <@{user_id}>, your job posting has been saved as a draft!\n\n" \
        #                     f"📋 **Draft Details:**\n" \
        #                     f"• Job Title: {job.get('job_title', 'N/A')}\n" \
        #                     f"• Company: {job.get('company', 'N/A')}\n" \
        #                     f"• Job ID: `{job_id}`\n\n" \
                        #    f"💡 **To manage your drafts:**\n" \
                        #    f"• Say \"show my posts\" to view all your drafts\n" \
                        #    f"• Say \"edit {job_id}\" to modify this draft\n" \
                        #    f"• Say \"delete {job_id}\" to remove this draft"
        
        # send_slack_message(draft_confirmation)
        # # Set error to stop workflow from proceeding to LinkedIn posting
        # state["error"] = f"User selected: {action}"
        # state["job_result"] = f"Draft saved successfully: {job_id}"
        print("Edit clicked")


# # Run only if script is executed directly
# if __name__ == "__main__":
#     user_id='12122'
#     user_name='manoj'
#     reply='change year of experience to 3 years'
#     job_desc="Hey <@U09359UUX8X>, here's your job description:\n\n**Senior Backend Developer**\nWe are looking for a skilled Backend Developer with 5 years of experience in Python.\n**Requirements:**\n- Python programming\n- Database management\n- API development\n\n**Job Type:** Full-time\n\nDoes this look okay?"
#     output = run_job_rewrite_pipeline(user_id, reply,job_desc,user_name)
#     if output:
#         print("\n Final Output:\n")
#         print(output)