import json
import uuid
import datetime
import os
import sys
from dotenv import load_dotenv
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents.stuff import create_stuff_documents_chain
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.documents import Document
from .retrieval.vectorstore import get_vectorstore
import time
import re

# Dynamically add the root directory to sys.path
current_file = os.path.abspath(__file__)
project_root = os.path.abspath(os.path.join(current_file, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

class RAGProcessor:
    def __init__(self):
        self.llm = ChatNVIDIA(
            model="meta/llama3-70b-instruct",
            api_key=os.getenv("NVIDIA_API_KEY")
        )
        self.vectorstore = get_vectorstore()
        self.handlers = {}
        
        # Enhanced formatting prompt
        self.format_prompt = ChatPromptTemplate.from_template("""
You are a rewriting assistant. Your job is to intelligently combine multiple user messages into one clear, structured, and grammatically correct sentence reflecting the user's intent.

Rules:
- Combine job-related details: role, skills, experience, location, job type.
- Include *any numeric experience* (e.g. "5 yrs", "3+ years", etc.) even if phrased vaguely.
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

    def get_rag_chain(self, user_id: str):
        """Get RAG chain for a specific user"""
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
- Only use the information found in formatted_query and chat_context.
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

        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5, "filter": {"user_id": user_id}})
        history_aware_retriever = create_history_aware_retriever(self.llm, retriever, contextualize_q_prompt)
        qa_chain = create_stuff_documents_chain(self.llm, qa_prompt)
        rag_chain = create_retrieval_chain(history_aware_retriever, qa_chain)

        def process_user_input(formatted_query: str, job_id: str | None = None) -> dict:
            """Process user input through RAG chain"""
            # Create filter based on whether job_id is provided
            filter_dict = {"user_id": user_id}
            if job_id:
                filter_dict["job_id"] = job_id
            
            try:
                similar_docs = self.vectorstore.similarity_search_with_score(
                    query=formatted_query,
                    k=5,
                    filter=filter_dict
                )
            except Exception as e:
                print(f"⚠ Error in similarity search: {e}")
                similar_docs = []

            # Get chat context - all previous user conversations
            try:
                collection = self.vectorstore._collection
                user_docs = collection.get(where={"user_id": user_id})
                documents = user_docs.get("documents", []) if user_docs else []
                chat_context = "\n".join([getattr(doc, 'page_content', str(doc)) for doc in documents]) if documents else ""
                print(f"🔍 Retrieved past data from RAG for user {user_id}")
                print(f"📄 Chat context: {chat_context[:200]}...")
            except Exception as e:
                print(f"⚠ Error retrieving chat context: {e}")
                chat_context = ""

            # Check if it's a past request query
            past_request_indicators = ["past", "previous", "history", "drafts", "show me my", "what are my"]
            is_past_request = any(indicator in formatted_query.lower() for indicator in past_request_indicators)
            
            # Only store the document if it's not a past request query
            if not is_past_request:
                metadata = {
                    "user_id": user_id,
                    "chat_id": str(uuid.uuid4()),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                if job_id:
                    metadata["job_id"] = job_id
                
                try:
                    self.vectorstore.add_documents([
                        Document(
                            page_content=formatted_query,
                            metadata=metadata
                        )
                    ])
                    print(f"✅ Stored new job requirement: {formatted_query}")
                except Exception as e:
                    print(f"⚠ Error storing document: {e}")
            else:
                print(f"🔍 Past request detected, not storing: {formatted_query}")

            # Generate final RAG response
            try:
                rag_result = rag_chain.invoke({
                    "input": formatted_query,
                    "chat_history": chat_context
                })
            except Exception as e:
                print(f"⚠ Error in RAG chain: {e}")
                rag_result = {"answer": "Error processing request", "context": []}

            # Final formatting
            try:
                final_output = self.llm.invoke(
                    response_format_prompt.format(
                        formatted_query=formatted_query,
                        chat_context=chat_context
                    )
                ).content
            except Exception as e:
                print(f"⚠ Error in final formatting: {e}")
                final_output = formatted_query

            return {
                "formatted_query": formatted_query,
                "chat_context": chat_context,
                "response": final_output,
                "is_past_request": is_past_request,
                "rag_answer": rag_result.get("answer", ""),
                "source_documents": rag_result.get("context", [])
            }

        return process_user_input

    def is_past_request_query(self, text: str) -> bool:
        """Check if the user text indicates a past request query"""
        text_lower = text.lower()
        past_indicators = [
            "past", "previous", "history", "drafts", "show me my", 
            "what are my", "my jobs", "old jobs", "earlier", "before"
        ]
        return any(indicator in text_lower for indicator in past_indicators)

    def is_specific_job_action(self, text: str) -> bool:
        """Check if the user text indicates a specific job action (show/edit/delete job_id)"""
        text_lower = text.lower()
        # Patterns that match both job_xxx and xxx formats, with optional space or underscore
        edit_pattern = r'edit[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
        delete_pattern = r'delete[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
        show_pattern = r'show[\s_]+(job_)?([a-zA-Z0-9_]{4,})'
        
        return bool(re.search(edit_pattern, text_lower) or 
                   re.search(delete_pattern, text_lower) or 
                   re.search(show_pattern, text_lower))

    def process_user_text(self, user_id: str, text: str, job_id: str | None = None) -> dict:
        """
        Process user text through RAG pipeline
        
        Args:
            user_id: User ID
            text: User's text input
            job_id: Optional job ID for job-specific context
            
        Returns:
            Dict containing processed response and metadata
        """
        try:
            print(f"🚀 Processing text for user {user_id}: {text}")
            
            # Check if this is a specific job action - if so, bypass formatter LLM
            is_specific_action = self.is_specific_job_action(text)
            print(f"🔍 Is specific job action: {is_specific_action}")
            
            if is_specific_action:
                # For specific job actions, use the original text directly
                print(f"🚫 Bypassing formatter LLM for specific job action")
                return {
                    "user_id": user_id,
                    "text": text,
                    "response": text,
                    "is_past_request": False,
                    "is_specific_job_action": True,
                    "formatted_query": text,
                    "job_id": job_id
                }
            else:
                # Check if this is a past request before processing
                is_past_req = self.is_past_request_query(text)
                print(f"🔍 Is past request: {is_past_req}")
                
                # Format the query using LLM
                try:
                    formatted_query = self.llm.invoke(
                        self.format_prompt.format(messages=text)
                    ).content
                except Exception as e:
                    print(f"⚠ Error formatting query: {e}")
                    formatted_query = text

                print(f"📝 Formatted query: {formatted_query}")

                # Get or create RAG handler for this user
                if user_id not in self.handlers:
                    self.handlers[user_id] = self.get_rag_chain(user_id)

                # Process through RAG
                response_data = self.handlers[user_id](formatted_query, job_id)
                
                return {
                    "user_id": user_id,
                    "text": text,
                    "response": response_data.get("response", ""),
                    "is_past_request": response_data.get("is_past_request", False),
                    "is_specific_job_action": False,
                    "formatted_query": formatted_query,
                    "chat_context": response_data.get("chat_context", ""),
                    "rag_answer": response_data.get("rag_answer", ""),
                    "source_documents": response_data.get("source_documents", []),
                    "job_id": job_id
                }

        except Exception as e:
            print(f"❌ Error processing user {user_id}: {e}")
            return {
                "user_id": user_id,
                "text": text,
                "response": f"Error: {str(e)}",
                "is_past_request": False,
                "is_specific_job_action": False,
                "formatted_query": text,
                "error": str(e),
                "job_id": job_id
            }

    def process_multiple_users(self, user_data: dict) -> list:
        """
        Process multiple users' text inputs
        
        Args:
            user_data: Dict with user_id as key and text as value
            Example: {"user1": "frontend developer", "user2": "backend engineer"}
            
        Returns:
            List of processed results
        """
        results = []
        for user_id, text in user_data.items():
            result = self.process_user_text(user_id, text)
            results.append(result)
        
        print(f"🚀 Processed {len(results)} users")
        return results


# Usage functions
def process_single_user(user_id: str, text: str, job_id: str | None = None, slack_handler=None) -> dict:
    """
    Process a single user's text through RAG
    
    Args:
        user_id: User ID
        text: User's text input
        job_id: Optional job ID for job-specific context
        slack_handler: Optional slack handler for responses
        
    Returns:
        Dict containing processed response and metadata
    """
    try:
        # Remove the 30-second sleep that was causing issues
        # time.sleep(30)  # Commented out
        
        processor = RAGProcessor()
        result = processor.process_user_text(user_id, text, job_id)
        
        # Only import and call intent_entity_processor if available
        try:
            from intent_entity_extractor.extractor import intent_entity_processor
            print(f"🚀 Sending result to intent_entity_processor")
            intent_entity_processor([result], slack_handler)
        except ImportError as e:
            print(f"⚠ Intent entity extractor not available: {e}")
        except Exception as e:
            print(f"⚠ Error calling intent_entity_processor: {e}")
        
        return result
    except Exception as e:
        print(f"❌ Error in process_single_user: {e}")
        return {
            "user_id": user_id,
            "text": text,
            "response": f"Error: {str(e)}",
            "error": str(e)
        }


def process_multiple_users(user_data: dict, slack_handler=None) -> list:
    """
    Process multiple users' text inputs
    
    Args:
        user_data: Dict with user_id as key and text as value
        slack_handler: Optional slack handler for responses
        
    Returns:
        List of processed results
    """
    try:
        processor = RAGProcessor()
        results = processor.process_multiple_users(user_data)
        
        # Only import and call intent_entity_processor if available
        try:
            from intent_entity_extractor.extractor import intent_entity_processor
            if slack_handler:
                print(f" Sending {len(results)} results to intent_entity_processor")
                intent_entity_processor(results, slack_handler)
        except ImportError as e:
            print(f"⚠ Intent entity extractor not available: {e}")
        except Exception as e:
            print(f"⚠ Error calling intent_entity_processor: {e}")
        
        return results
    except Exception as e:
        print(f"❌ Error in process_multiple_users: {e}")
        return []


# CLI usage
if __name__ == "__main__":
    # Example usage
    print("🧪 Testing RAG Processor")
    print("=" * 50)
    
    try:
        # Single user test - without calling the problematic dependencies
        processor = RAGProcessor()
        result = processor.process_user_text("user123", "I need a frontend developer with 5 years experience in skills of react and job type is full time")
        print(f"📋 Single user result: {result['response']}")
        
       
            
    except Exception as e:
        print(f"❌ Error in main: {e}")
        print("This might be due to missing dependencies or configuration issues.")
        print("Please ensure all required environment variables are set and dependencies are installed.")