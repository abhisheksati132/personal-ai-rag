# Deployment Guide: Personal AI Brain on Render

This guide outlines the exact, sequential manual deployment procedure for the Personal AI Brain RAG application on Render using the Blueprint specification in `render.yaml`.

---

## 1. Pre-Deployment Checklist

Before creating or deploying services on Render:
1. **Rotate Groq API Key**: In your Groq console, generate a fresh API key and revoke previous keys.
2. **Choose a Strong `APP_PASSWORD`**: Pick a password with at least 16 characters (the rate limiter enforces escalating lockouts: 60s after 5 failures, then 5 min, then 15 min).
3. **Generate `AUTH_SECRET_KEY`**: Run the following in your terminal and store the output in your password manager:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
4. **Cloud Database & Vector Store Credentials**:
   - Supabase PostgreSQL URL (`DATABASE_URL`, e.g., `postgresql://postgres.[ref]:[pass]@aws-0-[region].pooler.supabase.com:6543/postgres`).
   - Qdrant Cloud Cluster URL (`QDRANT_URL`, e.g., `https://[cluster].us-east4-0.gcp.cloud.qdrant.io:6333`).
   - Qdrant Cloud API Key (`QDRANT_API_KEY`).

---

## 2. Render Blueprint Initialization

1. Log into your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Blueprint**.
3. Select the `personal-ai-rag` repository on branch `main`.
4. Render will parse `render.yaml` and discover two services:
   - **`personal-ai-brain-api`** (FastAPI Web Service - Python 3.11, Singapore region `singapore` to minimize latency to Mumbai database)
   - **`personal-ai-brain-ui`** (Next.js Static Site - global CDN)

> **Important**: `render.yaml` deliberately marks `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` with `sync: false`. Render's internal `fromService` discovery returns private mesh hostnames (e.g. `personal-ai-brain-api:10000`), which client web browsers cannot reach. Public HTTPS URLs must be manually entered in the exact order below.

---

## 3. Step-by-Step Deployment Order

### Step 1: Deploy Backend Service (`personal-ai-brain-api`)

1. In the Blueprint setup (or under the `personal-ai-brain-api` service settings), provide the secret environment variables:
   - `APP_PASSWORD`: Your 16+ character master password.
   - `AUTH_SECRET_KEY`: Your generated 64-character hex secret.
   - `DATABASE_URL`: Your Supabase connection string.
   - `QDRANT_URL`: Your Qdrant Cloud URL.
   - `QDRANT_API_KEY`: Your Qdrant API key.
   - `GROQ_API_KEY`: Your rotated Groq API key.
   - `CORS_ORIGINS`: Leave empty for now (will be set in Step 3).
2. Click **Apply** or **Deploy** to start building the backend.
3. The backend build runs:
   ```bash
   pip install -r requirements.txt && python -c "from src.config import settings; from fastembed import TextEmbedding; TextEmbedding(model_name=settings.FASTEMBED_MODEL, cache_dir=str(settings.FASTEMBED_CACHE_DIR))"
   ```
   This pre-downloads and bakes the quantized ONNX embedding model (~300 MB) into the build cache.
4. When deployment completes, note your public backend URL from the top of the Render page:
   ```text
   https://personal-ai-brain-api.onrender.com
   ```
5. Verify health check by navigating to:
   ```text
   https://personal-ai-brain-api.onrender.com/health
   ```
   Confirm status code `200` and JSON response.

---

### Step 2: Configure & Rebuild Frontend (`personal-ai-brain-ui`)

1. In the Render Dashboard, navigate to the `personal-ai-brain-ui` Static Site service.
2. Go to **Environment** settings and set:
   - `NEXT_PUBLIC_API_URL`: `https://personal-ai-brain-api.onrender.com`
     - **CRITICAL**: The URL **must explicitly start with `https://`**. Do not omit the scheme (e.g., entering `personal-ai-brain-api.onrender.com` will be rejected by the frontend with a visible configuration error).
3. **CRITICAL REBUILD REQUIREMENT**:
   - Because Next.js static site generation (`npm run build` producing static HTML/JS bundles) bakes environment variables starting with `NEXT_PUBLIC_*` into client JavaScript bundles **at build time**, setting or updating `NEXT_PUBLIC_API_URL` requires a rebuild.
   - Click **Manual Deploy** -> **Clear build cache & deploy** (or **Deploy latest commit**).
   - Wait for the build and export to finish.
4. When deployment completes, note your public frontend URL:
   ```text
   https://personal-ai-brain-ui.onrender.com
   ```

---

### Step 3: Wire Frontend URL into Backend CORS

1. Return to the `personal-ai-brain-api` Web Service settings in Render.
2. Under **Environment**, update `CORS_ORIGINS`:
   - `CORS_ORIGINS`: `https://personal-ai-brain-ui.onrender.com`
3. Click **Save Changes**. Render will automatically trigger a rolling redeploy of the backend service with the updated CORS policy.

---

## 4. Verification & Smoke Test

1. Open your frontend in a private browser window: `https://personal-ai-brain-ui.onrender.com`.
2. Confirm the **AuthGate** prompt appears.
3. Test incorrect password: confirm 401 error message.
4. Enter your correct `APP_PASSWORD`: confirm immediate login.
5. In the Ask view, ask a question against your indexed files (e.g. *"Explain CAT-1 compiler phases"*).
6. Verify the answer is generated via Groq (`openai/gpt-oss-120b`) with source citations.
7. Reload the page: verify the session remains active without prompting for credentials again.
8. Click Logout in the sidebar: verify immediate return to the AuthGate login screen.
