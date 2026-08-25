# 🚀 RAG ChatApp (FastAPI + React + LangChain + Gemini)

A full-stack **Retrieval Augmented Generation (RAG)** chatbot application built with:

- **FastAPI** backend
- **LangChain** for RAG
- **Google Gemini LLMs**
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
pip install python-multipart chromadb google-genai langchain langchain-community langchain-core
```

### Step 3 — Add your API key

Create a `.env` file in the project root from `.env.example`:

```
GEMINI_API_KEY=your_key_here
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
- Gemini LLM generation

The frontend provides:

- Chat UI
- PDF upload UI
- Real-time responses

Enjoy building with RAG!

## Production notes

- Build the frontend with `npm run build`, then serve `frontend-react/dist` from a static web server or CDN.
- Set `VITE_API_BASE_URL` at build time to the public API URL (or `/api` behind a reverse proxy).
- Run the API without reload, for example: `uvicorn app:app --host 0.0.0.0 --port 8000` from `backend/`.
- Keep the frontend on Vercel and deploy `backend/` to Railway. Railway provides HTTPS and supports FastAPI directly.
- Railway's free plan provides limited monthly usage credit. It is free only within that allowance; when credits run out, the service stops. Do not add a payment method if you want to prevent charges.
- Railway's filesystem is ephemeral on redeploys and restarts. Uploaded PDFs and Chroma data are suitable for a demo but should move to persistent storage for production.
- The reset route is intended for the local single-user app. Add authentication before exposing it publicly.
- Uploaded documents are shared by every client of this simple deployment. Add tenant isolation and authentication before using it for multiple users.

### Railway deployment

1. Create an account at https://railway.com/ and start the Free Trial. Railway currently advertises a one-time $5 trial credit without requiring a card.
2. Create a new project and choose **Deploy from GitHub repo**.
3. Select this repository and create a service from it.
4. Open the service **Settings**, set **Root Directory** to `/backend`, and redeploy.
5. Open **Variables** and add:

```text
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash-lite
CORS_ORIGINS=https://frontend-react-blond-six.vercel.app
```

6. Open **Settings → Networking**, click **Generate Domain**, and copy the Railway URL.
7. Verify the backend by opening `https://<railway-domain>/health`; it should return `llmConfigured: true`.
8. Configure and redeploy the Vercel frontend:

```sh
cd frontend-react
npx vercel env add VITE_API_BASE_URL production
npx vercel --prod --yes
```
