#queue_rag.py
import json, uuid, datetime, os
from collections import deque, defaultdict
from dotenv import load_dotenv
from old_rag import get_rag_chain as get_old_rag_handler

from langchain.prompts import ChatPromptTemplate
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents.stuff import create_stuff_documents_chain
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.documents import Document
# ⛳ import formatter only
from format_llm_1 import extract_jobs_from_input

from retrieval.vectorstore import get_vectorstore

# Load environment variables
load_dotenv()
api_key = os.getenv("NVIDIA_API_KEY")

# Initialize LLMs
formatter_llm = ChatNVIDIA(model="meta/llama3-70b-instruct", api_key=api_key)
llm = ChatNVIDIA(model="meta/llama3-70b-instruct", api_key=api_key)

# Per-user queues
user_queues = defaultdict(deque)

# Prompt templates
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
- Do NOT combine different job roles (e.g., frontend + backend) into one.
- Only use the information found in formatted_query and chat_context.
- Do NOT invent or guess missing skills or experience.
- Output only one sentence.
- Be precise, direct, and aligned with the user's original structure.

Formatted Query:
{formatted_query}

Chat Context:
{chat_context}

Final Intent:
""")

def get_rag_chain(user_id):
    vectorstore = get_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5, "filter": {"user_id": user_id}})
    history_retriever = create_history_aware_retriever(llm, retriever, contextualize_q_prompt)
    qa_chain = create_stuff_documents_chain(llm, qa_prompt)
    return create_retrieval_chain(history_retriever, qa_chain), vectorstore

# Enqueue jobs or fallback to general RAG
def enqueue_jobs(user_id, user_text):
    parsed = extract_jobs_from_input(user_text)

    if isinstance(parsed, dict) and parsed.get("rag_1_request"):
        handler = get_old_rag_handler(user_id)
        result = handler(user_text)  # ✅ Now this will work

        user_queues[user_id].append(result["response"])
        return

    for job in parsed:
        cleaned = job[0].strip()
        if cleaned:
            user_queues[user_id].append(cleaned)

# Per-user processor
def process_next_job(user_id):
    if not user_queues[user_id]:
        return {"status": "done", "message": "No jobs in queue"}

    job_text = user_queues[user_id].popleft()
    rag_chain, vectorstore = get_rag_chain(user_id)

    # Duplication check
    similar_docs = vectorstore.similarity_search_with_score(job_text, k=5, filter={"user_id": user_id})
    is_duplicate = any(score > 0.88 for _, score in similar_docs)

    chat_context = ""
    if is_duplicate:
        matches = vectorstore.similarity_search(similar_docs[0][0].page_content, k=10, filter={"user_id": user_id})
        chat_context = "\n".join([d.page_content for d in matches])
    else:
        try:
            user_docs = vectorstore._collection.get(where={"user_id": user_id})
            chat_context = "\n".join(user_docs.get("documents", [])) if user_docs else ""
        except Exception:
            chat_context = ""

    # Save
    vectorstore.add_documents([Document(
        page_content=job_text,
        metadata={
            "user_id": user_id,
            "chat_id": str(uuid.uuid4()),
            "timestamp": datetime.datetime.now().isoformat()
        }
    )])

    # Refine output
    final_sentence = llm.invoke(response_format_prompt.format(
        formatted_query=job_text,
        chat_context=chat_context
    )).content.strip()

    return {
        "user_id": user_id,
        "formatted_query": job_text,
        "chat_context": chat_context,
        "response": final_sentence
    }