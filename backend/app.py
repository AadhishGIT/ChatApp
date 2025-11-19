from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rag_pipeline import load_rag_pipeline

app = FastAPI()
qa_chain = load_rag_pipeline()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "RAG backend is running!"}

@app.post("/ask")
async def ask_question(payload: dict):
    question = payload.get("question")

    if not question:
        return {"error": "Question is required."}

    response = qa_chain(question)
    answer = response["result"]

    return {"answer": answer}
