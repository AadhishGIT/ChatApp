import os
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "data", "chroma")


def get_retriever():
    """
    Returns a LangChain retriever that pulls the most relevant chunks
    from the Chroma vector store.
    """
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vectordb = Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
    )

    retriever = vectordb.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 10},  # top 10 relevant chunks
    )
    return retriever
