# 🚀 RAG ChatApp (FastAPI + React + LangChain + Groq)

A full-stack **Retrieval Augmented Generation (RAG)** chatbot application built with:

- **FastAPI** backend
- **LangChain** for RAG
- **Groq LLMs**
- **ChromaDB** vector store
- **React + Vite + TypeScript** frontend
- **TailwindCSS** for styling

Features include **PDF upload**, **document ingestion**, and **chat answering using your documents**.

---

# 📦 Installation & Setup

## 1️⃣ Backend Setup (FastAPI)

### Step 1 — Create & activate virtual environment

```sh
cd backend
python3.10 -m venv venv
source venv/bin/activate
```

### Step 2 — Install backend dependencies

```sh
pip install -r requirements.txt
```

If needed:

```sh
pip install python-multipart chromadb groq langchain langchain-community langchain-core
```

### Step 3 — Add your API key

Create a `.env` file in the project root from `.env.example`:

```
GROQ_API_KEY=your_key_here
```

(Do NOT commit this file.) Set `CORS_ORIGINS` to the exact URL of your deployed frontend; it is a comma-separated list.

### Step 4 — Add PDFs for ingestion

Place PDFs here:

```
backend/data/pdfs/
```

Then run ingestion:

```sh
python ingest.py
```

### Step 5 — Start FastAPI backend

```sh
uvicorn app:app --reload --port 8000
```

Backend will start at:

```
http://localhost:8000
```

Swagger docs:

```
http://localhost:8000/docs
```

---

## 2️⃣ Frontend Setup (React + Vite + TS)

### Step 1 — Install dependencies

```sh
cd frontend-react
npm install
```

### Step 2 — Start the development server

```sh
npm run dev
```

Frontend runs at:

```
http://localhost:5173
```

---

# ▶️ How to Use the App

1. Start **backend** (`uvicorn app:app --reload`)
2. Start **frontend** (`npm run dev`)
3. Open browser → `http://localhost:5173`
4. Upload PDFs via the upload button
5. Ask questions in chat — responses use RAG from your documents

---

# 🎉 You're all set!

The backend handles:

- PDF uploads
- Document ingestion
- Vector search
- Groq LLM generation

The frontend provides:

- Chat UI
- PDF upload UI
- Real-time responses

Enjoy building with RAG!

## Production notes

- Build the frontend with `npm run build`, then serve `frontend-react/dist` from a static web server or CDN.
- Set `VITE_API_BASE_URL` at build time to the public API URL (or `/api` behind a reverse proxy).
- Run the API without reload, for example: `uvicorn app:app --host 0.0.0.0 --port 8000` from `backend/`.
- The reset route is intended for the local single-user app. Add authentication before exposing it publicly.
- Uploaded documents are shared by every client of this simple deployment. Add tenant isolation and authentication before using it for multiple users.
