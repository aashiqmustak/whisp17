import os
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

load_dotenv()

def get_vectorstore():
    embeddings = NVIDIAEmbeddings(
        model="nvidia/embed-qa-4",
        api_key="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"
    )
    persist_directory = os.getenv("CHROMA_DIR", "./chroma_store")

    vectorstore = Chroma(
        collection_name="rag_chroma",
        persist_directory=persist_directory,
        embedding_function=embeddings
    )

    print(f"INFO: Chroma initialized with {len(vectorstore.get()['ids'])} documents")
    return vectorstore
