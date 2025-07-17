from langchain.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from dotenv import load_dotenv
import os
import json

# Load .env and API key
load_dotenv()
api_key = os.getenv("NVIDIA_API_KEY")

# Initialize NVIDIA LLM
formatter_llm = ChatNVIDIA(model="meta/llama3-70b-instruct", api_key=api_key)

# Define the job intent extraction prompt
job_split_prompt = ChatPromptTemplate.from_template("""
You are a job intent extraction assistant.

Your task is to analyze user input messages and extract complete job intent statements.

Rules:
1. Identify distinct job roles mentioned or implied in the message.
2. If only job-related details (like skills, experience, job type, or location) are provided and no job title is clearly mentioned, return:
   {{"rag_1_request": true}}
3. For each detected or inferred job role, rephrase it as a standalone sentence that includes:
   - Job title (standardized)
   - Skills (if mentioned)
   - Experience (if mentioned)
   - Location (if mentioned)
   - Job type (if mentioned)
4. If multiple job roles are found, generate one sentence for each.
5. If terms like “frontend”, “backend”, or “fullstack” appear without “developer” or “engineer”, infer and clean them into standard job titles.
6. If experience is mentioned as “2 years and 5 years for frontend and backend respectively”, assign accordingly.

Return the final result as a JSON list of standalone intent statements. Each item must be in its own list.

Examples:

Input: "looking for frontend and backend with 2 years and 5 years respectively"
Output:
[
  ["We are looking for a frontend developer with 2 years experience."],
  ["We are looking for a backend developer with 5 years experience."]
]

Input: "React, full-time, remote, 3 years"
Output:
{{"rag_1_request": true}}

Input: "need a frontend developer with React"]
Output:
[
  ["We need a frontend developer with React experience."]
]

User Input:
{user_input}

Return:
- If job titles are found, return JSON list of lists.
- If no job title is found, return: {{"rag_1_request": true}}

Return ONLY the raw JSON.
""")



def extract_jobs_from_input(raw_text: str):
    try:
        # Invoke the LLM with the prompt and user input
        response = formatter_llm.invoke(
            job_split_prompt.format(user_input=raw_text)
        ).content.strip()

        print("🧠 Raw LLM Output:\n", response)

        # Try parsing the JSON response
        parsed = json.loads(response)

        # Case 1: Special case - only job-related entities, no job title
        if isinstance(parsed, dict) and parsed.get("rag_1_request"):
            return parsed

        # Case 2: List of job role sentences
        if isinstance(parsed, list):
            return [(item[0].strip(), "") for item in parsed if isinstance(item, list) and item]

    except Exception as e:
        print(f"⚠ Error: {e}")
        return [(raw_text.strip(), "")]


if __name__ == "__main__":
    user_input = "skills java"
    result = extract_jobs_from_input(user_input)
    print("\n✅ Final Parsed Result:\n", result)