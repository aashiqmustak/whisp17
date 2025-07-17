import json
import uuid

import datetime
from dotenv import load_dotenv
from collections import defaultdict
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents.stuff import create_stuff_documents_chain
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.documents import Document
from .logic_editor import RoundRobinQueueManager

# Removed incorrect sqlalchemy import

import sys
import os

# Dynamically add the root directory to sys.path
current_file = os.path.abspath(__file__)
project_root = os.path.abspath(os.path.join(current_file, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from .retrieval.vectorstore import get_vectorstore
from intent_entity_extractor.extractor import intent_entity_processor
from edit_rag.edit_formatter import run_job_rewrite_pipeline
from .format_llm_1 import extract_jobs_from_input
# Shared LLM for formatting
formatter_llm = ChatNVIDIA(
    model="meta/llama3-70b-instruct",
    api_key=os.getenv("NVIDIA_API_KEY")
)

# Enhanced formatting prompt for batching with past request detection
format_prompt = ChatPromptTemplate.from_template("""
You are a rewriting assistant. Your job is to intelligently combine multiple user messages into one clear, structured, and grammatically correct sentence reflecting the user's intent.

Rules:
- Combine job-related details: role, skills, experience, location, job type.
- Include **any numeric experience** (e.g. "5 yrs", "3+ years", etc.) even if phrased vaguely.
- Do NOT skip or assume information — only use what's mentioned.
- Ignore greetings or casual words like "hi", "hello", "need job".
- PRESERVE past request keywords like "past", "previous", "history", "drafts", "show me my jobs"
- Output should be a single clear sentence.

📘 Examples:

Messages:
- "frontend"
- "5 yrs"
- "remote job"

Combined Output:
"I am looking for a remote frontend developer role with 5 years of experience."

Messages:
- "backend"
- "node"
- "3+ yrs exp"
- "hybrid"

Combined Output:
"I want a hybrid backend developer role with over 3 years of experience in Node.js."

Messages:
- "show me"
- "my past jobs"

Combined Output:
"Show me my past jobs."

Messages:
- "what are my drafts"

Combined Output:
"What are my drafts."

Messages:
- "job history"
- "previous postings"

Combined Output:
"Show me my job history and previous postings."

Messages:
{messages}

Combined Output:
""")


def get_rag_chain(user_id: str):
    llm = ChatNVIDIA(
        model="meta/llama3-70b-instruct",
        api_key=os.getenv("NVIDIA_API_KEY")
    )
    vectorstore = get_vectorstore()

    contextualize_q_prompt = ChatPromptTemplate.from_template("""
Given a clumsy chat history and a vague or informal user message, rephrase it into a clear, standalone, and grammatically correct question.

Rules:
- Assume the user is casually expressing their needs or intentions.
- Correct grammar, spelling, and structure.
- Preserve all information, especially skills, experience, and job type.
- PRESERVE past request indicators like "past", "previous", "history", "drafts", "show me my"
- Do NOT hallucinate or add new info.

Chat History:
{chat_history}

Latest Input:
{input}

Standalone Question:
""")

    qa_prompt = ChatPromptTemplate.from_template("""
You are a helpful assistant. Use the provided context to accurately answer the user's intent or question.

Rules:
- Expect informal, shorthand, or clumsy user input.
- Extract meaning and match relevant context.
- If context lacks required info, respond with: "Sorry, I don't have enough information."
- If user is asking about past jobs, drafts, or history, acknowledge the request clearly.

Context:
{context}

User Input:
{input}

Answer:
""")

    response_format_prompt = ChatPromptTemplate.from_template("""
You are a sentence optimizer. Your job is to synthesize a single, clear, grammatically correct sentence summarizing the user's intent.

Strict Rules:
- Input may be clumsy, broken, or shorthand — fix grammar, spelling, structure.
- Only use the information found in `formatted_query` and `chat_context`.
- Do NOT invent or guess anything.
- Combine related data (skills, experience, job type) logically.
- PRESERVE past request keywords like "past", "previous", "history", "drafts", "show me my"
- Output only one sentence.

Formatted Query:
{formatted_query}

Chat Context:
{chat_context}

Final Intent:
""")

    retriever = vectorstore.as_retriever(search_kwargs={"k": 5, "filter": {"user_id": user_id}})
    history_aware_retriever = create_history_aware_retriever(llm, retriever, contextualize_q_prompt)
    qa_chain = create_stuff_documents_chain(llm, qa_prompt)
    rag_chain = create_retrieval_chain(history_aware_retriever, qa_chain)

    def process_user_input(formatted_query: str) -> dict:
        similar_docs = vectorstore.similarity_search_with_score(
            query=formatted_query,
            k=5,
            filter={"user_id": user_id}
        )

        # Get chat context - all previous user conversations
        try:
            collection = vectorstore._collection
            user_docs = collection.get(where={"user_id": user_id})
            documents = user_docs.get("documents", []) if user_docs else []
            chat_context = "\n".join([getattr(doc, 'page_content', str(doc)) for doc in documents]) if documents else ""
            print("retrieving past data from rag")
            print(chat_context)
            print("#####")
        except Exception:
            chat_context = ""

        # Only store the document if it's not a past request query
        # (we don't want to store "show me my drafts" as a job requirement)
        past_request_indicators = ["past", "previous", "history", "drafts", "show me my", "what are my"]
        is_past_request = any(indicator in formatted_query.lower() for indicator in past_request_indicators)
        
        if not is_past_request:
            vectorstore.add_documents([
                Document(
                    page_content=formatted_query,
                    metadata={
                        "user_id": user_id,
                        "chat_id": str(uuid.uuid4()),
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                )
            ])
            print(f"✅ Stored new job requirement: {formatted_query}")
        else:
            print(f"🔍 Past request detected, not storing: {formatted_query}")

        # Generate final RAG response
        rag_result = rag_chain.invoke({
            "input": formatted_query,
            "chat_history": chat_context
        })

        # Final formatting
        final_output = llm.invoke(
            response_format_prompt.format(
                formatted_query=formatted_query,
                chat_context=chat_context
            )
        ).content

        return {
            "formatted_query": formatted_query,
            "chat_context": chat_context,
            "response": final_output,
            "is_past_request": is_past_request
        }

    return process_user_input


def is_past_request_query(messages: list) -> bool:
    """
    Check if the user messages indicate a past request query
    """
    combined_text = " ".join(messages).lower()
    past_indicators = [
        "past", "previous", "history", "drafts", "show me my", 
        "what are my", "my jobs", "old jobs", "earlier", "before"
    ]
    return any(indicator in combined_text for indicator in past_indicators)


def is_specific_job_action(messages: list) -> bool:
    """
    Check if the user messages indicate a specific job action (show/edit/delete job_id)
    """
    combined_text = " ".join(messages).lower()
    # Patterns that match both job_xxx and xxx formats, with optional space or underscore
    edit_pattern = r'edit[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
    delete_pattern = r'delete[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
    show_pattern = r'show[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
    
    import re
    return bool(re.search(edit_pattern, combined_text) or 
               re.search(delete_pattern, combined_text) or 
               re.search(show_pattern, combined_text))


def process_messages(json_data: dict, slack_handler=None) -> list:
    messages = json_data.get("messages", [])
    user_messages = defaultdict(list)
    user_meta = {}
    results = []
    handlers = {}

    for msg in messages:
        uid = msg.get("user_id")
        if not uid:
            continue

        text = msg.get("text", "").strip()
        if text:
            user_messages[uid].append(text)

        # Store metadata only once per user
        if uid not in user_meta:
            user_meta[uid] = {
                "user_id": uid,
                "username": msg.get("username", ""),
                "app_id": msg.get("app_id", ""),
                "channel_id": msg.get("channel_id", ""),
                "session_id": msg.get("session_id", "")
            }
    # Check edit mode before processing
    try:
        with open("edit_mode.json","r") as f:
            edit_dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        edit_dict = {}
    
    for user_id, message_list in user_messages.items():
        #add formetter llm code to process use message list
        user_reply = " ".join(message_list)
        if user_id in edit_dict and edit_dict[user_id].get("status") == True:
            # Call pipeline to edit the job description
            job_desc = edit_dict[user_id]["message"]
            user_name = user_meta[user_id]["username"]
            channel_id = user_meta[user_id]["channel_id"]
            
            # Join message list into a single string for the edit request
            
            
            print(f"🔄 Processing edit request for user {user_id}: {user_reply}")
            
            # Process the edit
            run_job_rewrite_pipeline(user_id=user_id, reply=user_reply, job_desc=job_desc, user_name=user_name,channel_id=channel_id)
            
            # Clear edit mode after processing
            edit_dict[user_id]["status"] = False
            with open("edit_mode.json","w") as f:
                json.dump(edit_dict, f, indent=2)
            
            print(f"✅ Edit mode cleared for user {user_id}")
            continue
        else:
            if user_id not in edit_dict:
               edit_dict[user_id]={}
               edit_dict[user_id]["status"]=False
               edit_dict[user_id]["free"]=True
               edit_dict[user_id]["message"]=None
               with open("edit_mode.json","w") as f:
                json.dump(edit_dict, f, indent=2)
           
            extracted=extract_jobs_from_input(user_reply)
            if(isinstance(extracted,dict)):
                current_processor={user_id:user_reply}
            else:
                message_list=extracted
                message_list= [i[0] for i in message_list]
                tracker=RoundRobinQueueManager()
                tracker_dict={user_id:message_list}
                current_processor=tracker.process_user_requests(tracker_dict)
                print(current_processor)
                if edit_dict[user_id].get("free")==False:
                  continue
                elif edit_dict[user_id].get("free")==True:
                  tracker.mark_user_busy(user_id)
        try:
            # Check if this is a specific job action - if so, bypass formatter LLM
            is_specific_action = is_specific_job_action(message_list)
            print(f"🔍 Is specific job action for user {user_id}: {is_specific_action}")
            
            if is_specific_action:
                # For specific job actions, use the original message directly
                print(f"🚫 Bypassing formatter LLM for specific job action: {message_list}")
                user_meta[user_id]["response"] = current_processor[user_id]  # Use original message
                user_meta[user_id]["is_past_request"] = False
                user_meta[user_id]["text"] = current_processor[user_id]
                user_meta[user_id]["is_specific_job_action"] = True
                
                print(f"📝 User {user_id} processed (specific job action):")
                print(f"   - Original messages: {message_list}")
                print(f"   - Response: {user_meta[user_id]['response']}")
            else:
                # Check if this is a past request before processing
                is_past_req = is_past_request_query(message_list)
                print(f"🔍 Is past request for user {user_id}: {is_past_req}")
                
                combined_text = current_processor[user_id]
                formatted_query = formatter_llm.invoke(
                    format_prompt.format(messages=combined_text)
                ).content

                if user_id not in handlers:
                    handlers[user_id] = get_rag_chain(user_id)

                response_data = handlers[user_id](formatted_query)
                user_meta[user_id]["response"] = response_data.get("response", "")
                user_meta[user_id]["is_past_request"] = response_data.get("is_past_request", False)
                # Store original message text for pattern matching
                user_meta[user_id]["text"] = current_processor[user_id]
                user_meta[user_id]["is_specific_job_action"] = False

                print(f"📝 User {user_id} processed:")
                print(f"   - Original messages: {current_processor[user_id]}")
                print(f"   - Formatted query: {formatted_query}")
                print(f"   - Is past request: {response_data.get('is_past_request', False)}")
                print(f"   - Response: {response_data.get('response', '')[:100]}...")

        except Exception as e:
            user_meta[user_id]["response"] = f"Error: {str(e)}"
            user_meta[user_id]["is_past_request"] = False
            user_meta[user_id]["is_specific_job_action"] = False
            print(f"❌ Error processing user {user_id}: {e}")

        results.append(user_meta[user_id])

    print(f"🚀 Sending {len(results)} results to intent_entity_processor")
    intent_entity_processor(results, slack_handler)
    return results


# CLI usage
def formator_llm(input_data, slack_handler=None):
    output = process_messages(input_data, slack_handler)
    print(json.dumps(output, indent=2))
    return output



if __name__ =="__main__":
    input={
    "messages": [
        {
            "user_id": "U0911MZLHGW",
            "username": "vishwa.fury",
            "text": "i need a frontend dev",
            "app_id": "T091X4YCNAU",
            "channel_id": "C094YC3F6T1",
            "session_id": "C094YC3F6T1_main"
        },
       
    ],
    "batch_size": 5,
    "timestamp": 1751120769.072652
}
    process_messages(input)