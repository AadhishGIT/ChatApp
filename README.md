# 🚀 DocuMind — Production RAG Chatbot (100% Free Tier Architecture)

A full-stack, production-grade **Retrieval-Augmented Generation (RAG)** chatbot engineered to operate **completely free of cost forever** using generous free-tier cloud infrastructure:

- **Frontend**: React 19 + TypeScript + Vite + TailwindCSS 4 (Hosted on **Vercel** — 100% Free Forever)
- **Backend**: FastAPI with async Server-Sent Events (SSE) streaming (Hosted on **Render** — 100% Free Tier)
- **Vector Database**: **Supabase PostgreSQL** with `pgvector` + HNSW indexing (500 MB DB Free Forever)
- **LLM & Embeddings**: **Google Gemini API** (`gemini-2.5-flash-lite` + `text-embedding-004`) (15 RPM / 1,500 RPD Free Forever)
- **Keep-Alive**: Free HTTP pinger (Cron-job.org / UptimeRobot) to prevent cold starts

---

## 🏗 System Architecture

```text
┌──────────────────────┐         HTTP / SSE (Streaming)         ┌──────────────────────┐
│                      │ ──────────────────────────────────────> │                      │
│     React + Vite     │                                         │   FastAPI Backend    │
│  (Hosted on Vercel)  │ <────────────────────────────────────── │  (Hosted on Render)  │
└──────────────────────┘           Real-time Token Stream        └──────────┬───────────┘
                                                                            │
                                                     ┌──────────────────────┴──────────────────────┐
                                                     ▼                                             ▼
                                          ┌──────────────────────┐                      ┌──────────────────────┐
                                          │  Google Gemini API   │                      │  Supabase Database   │
                                          │  · Flash Generation  │                      │  · pgvector Store    │
                                          │  · Remote Embeddings │                      │  · HNSW Indexing     │
                                          └──────────────────────┘                      └──────────────────────┘
```

---

## ⚡ Why This Stack is 100% Free & Production-Grade

1. **No Trial Expirations**: Unlike Railway's 7-day trial, Vercel, Render, Supabase, and Gemini API have permanent free tiers.
2. **Lightweight & High Performance**: By replacing local PyTorch/`sentence-transformers` with Gemini's remote embedding API, backend memory usage dropped from **1.2 GB to ~60 MB**, allowing it to run smoothly on any 512 MB free container.
3. **True Cloud Persistence**: Vector embeddings and document metadata are stored in Supabase cloud PostgreSQL with `pgvector`, so server redeploys never wipe your documents.
4. **Sub-second Perceived Latency**: Responses stream in real-time word-by-word using Server-Sent Events (SSE).
5. **Session Isolation**: Each chat session has isolated document indexing and conversation history.

---

## 🛠 Step 1: Set Up Supabase (Free Vector DB)

1. Sign up for free at [supabase.com](https://supabase.com) and create a new project.
2. Open the **SQL Editor** in your Supabase project dashboard.
3. Copy the entire contents of [`supabase/schema.sql`](file:///Users/aadhishd/Documents/CodingStuff/ChatApp/supabase/schema.sql) and click **Run**.
4. Go to **Project Settings → API** and copy:
   - **Project URL** (`https://<project-ref>.supabase.co`)
   - **anon / public key** (or service role key)

---

## 🔑 Step 2: Get a Free Google Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Generate an API Key (Free tier includes 15 requests per minute, 1,500 requests per day at \$0 cost).

---

## 💻 Step 3: Local Development

### Backend Setup:

```sh
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
CORS_ORIGINS=http://localhost:5173
```

Start the backend:

```sh
uvicorn app:app --reload --port 8000
```

### Frontend Setup:

```sh
cd frontend-react
npm install
npm run dev
```

Open your browser at `http://localhost:5173`.

---

## 🚀 Step 4: Deploy Backend for Free (Render)

1. Push your code to GitHub.
2. Go to [render.com](https://render.com) and sign in.
3. Click **New + → Web Service**.
4. Connect your GitHub repository.
5. Configure the service:
   - **Name**: `documind-backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install --no-cache-dir -r backend/requirements.txt`
   - **Start Command**: `cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
6. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: `<your_gemini_api_key>`
   - `SUPABASE_URL`: `<your_supabase_url>`
   - `SUPABASE_KEY`: `<your_supabase_anon_key>`
   - `CORS_ORIGINS`: `*` (or your Vercel URL)
7. Click **Deploy Web Service** and copy your backend URL (e.g., `https://documind-backend.onrender.com`).

---

## 🌐 Step 5: Deploy Frontend for Free (Vercel)

1. Go to [vercel.com](https://vercel.com) and sign in with GitHub.
2. Click **Add New... → Project** and select your repository.
3. In **Root Directory**, click edit and select `frontend-react`.
4. In **Environment Variables**, add:
   - `VITE_API_BASE_URL`: `https://documind-backend.onrender.com` (your Render backend URL)
5. Click **Deploy**. Vercel will build and deploy your React app globally with free SSL and CDN!

---

## 🕒 Step 6: Keep Backend Awake for Free (Optional)

Free instances on Render sleep after 15 minutes of inactivity. To keep your app warm 24/7 at \$0 cost:
1. Go to [cron-job.org](https://cron-job.org) or [uptimerobot.com](https://uptimerobot.com) (100% free).
2. Create an HTTP monitor that pings your backend health endpoint every 14 minutes:
   `https://documind-backend.onrender.com/health`

Even if the server does sleep, DocuMind includes an automatic **Cold-Start Indicator** in the UI that alerts the user and retries automatically until the server wakes up!
