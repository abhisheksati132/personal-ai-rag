# 🧠 Personal AI Brain — Local-First Grounded RAG

> A privacy-first, zero-cloud Retrieval-Augmented Generation (RAG) system running entirely on your local machine. Query your personal notes, course materials, PDFs, Word documents, and text files with strict evidence grounding, exact source citations, and verified zero-hallucination refusal guards.

---

## 🌟 What Makes This Different?

Most RAG implementations wrap a generic chatbot around a vector database, quietly hallucinating when relevant context is missing or hiding citations behind vague footnotes. **Personal AI Brain** is designed around **evidence-first retrieval**:

1. **Guaranteed Zero-Hallucination Refusal**: If your query falls outside your indexed documents (or below the cosine similarity threshold), the system strictly refuses to answer (`"I don't have information on that in your indexed files"`) rather than confabulating.
2. **First-Class Evidence Trail**: Every grounded response features a dedicated Retrieval Strip with source filenames, chunk indices, and visual cosine similarity confidence bars.
3. **Real-Time Delta Watcher**: Drop, update, rename, or delete files in your documents directory — the background watcher automatically recalculates SHA-256 hashes, cleans up stale vectors, and re-indexes in real time without downtime.
4. **100% Local Data Sovereignty**: All embeddings (`nomic-embed-text`), LLM inferences (`llama3.2`), vector search (`ChromaDB`), and metadata tracking (`SQLite`) run completely on-premise with zero cloud telemetry.

---

## 🏗️ System Architecture

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             DOCUMENT INGESTION & SYNC                            │
└──────────────────────────────────────────────────────────────────────────────────┘
  📁 Local Documents (.pdf, .docx, .txt, .md)
     │
     ├──▶ 👁️ File Watcher (src/watcher.py) ── Debounced Watchdog daemon
     │     │
     ▼     ▼
  ⚙️ Ingestion Pipeline (src/ingest.py)
     │
     ├──▶ 🔍 SQLite Hash Tracker (data/brain.db) ── SHA-256 deduplication & mtime check
     │     ├─► Skips unchanged files automatically
     │     └─► Prunes stale vectors on file deletion/rename
     │
     ├──▶ 📄 Extractor Factory (src/extractors/) ── PDF (pypdf), DOCX, Text/Markdown
     │
     ├──▶ ✂️ Recursive Chunker (src/chunker.py) ── 1,000 char windows + 150 overlap
     │
     ├──▶ 🧠 Ollama Embedder (src/embeddings.py) ── nomic-embed-text (768 dimensions)
     │
     └──▶ 💾 ChromaDB Store (src/vector_store.py) ── Cosine HNSW vector index

┌──────────────────────────────────────────────────────────────────────────────────┐
│                            QUERY & RETRIEVAL PIPELINE                            │
└──────────────────────────────────────────────────────────────────────────────────┘
  💬 User Query (Natural Language)
     │
     ▼
  🌐 Next.js Web UI (frontend/ — port 3000) ── Archive aesthetic, Fraunces / JetBrains Mono
     │
     ▼ HTTP POST /query
  ⚡ FastAPI Backend (src/api.py — port 8000)
     │
     ├──▶ 🎯 Retrieval Service (src/retrieval.py)
     │     ├─► Embeds query via nomic-embed-text
     │     ├─► Vector search top-k chunks from ChromaDB
     │     └─► Filters by similarity threshold (min_score >= 0.40)
     │
     ├──▶ 🛡️ Prompt Builder & Refusal Guard (src/prompt.py)
     │     └─► [NO CONTEXT] ──► Immediate Grounded Fallback (Zero Hallucination)
     │     └─► [HAS CONTEXT] ─► Structured System Prompt with Cited Blocks
     │
     └──▶ 🦙 Ollama Local LLM (src/llm.py) ── LLaMA 3.2 synthesis
           │
           ▼
     ✅ Grounded Answer + Evidence Cards (Filename, Chunk #, Confidence Score)
```

---

## 📸 Web Interface Tour

The web interface is built with Next.js and Tailwind CSS, featuring an **archive-inspired design system** (Paper `#F6F5F2`, Ink `#1C1B1A`, Moss `#5B6B5B`, Pine `#3D5A4C`, Stone `#8A8578`) with **Fraunces** serif display typography and **JetBrains Mono** data metadata.

### 1. Grounded Chat & Signature Retrieval Strip
Every response renders an **Evidence Trail** row displaying the exact cited document chunks and similarity confidence scores:

![Web UI Chat & Retrieval Evidence Strip](https://raw.githubusercontent.com/abhisheksati132/personal-ai-rag/main/docs/phase4_ui_fixed_chat_view.jpg)

### 2. Live Indexed Files View
Live visibility into tracked documents, chunk distributions, storage footprints, and SQLite sync status:

![Indexed Files View](https://raw.githubusercontent.com/abhisheksati132/personal-ai-rag/main/docs/phase4_files_view_demo.jpg)

---

## 🚀 Quickstart: Docker Compose (Recommended)

Run the entire multi-container stack with a single command.

### 1. Clone Repository & Start Containers
```bash
git clone https://github.com/abhisheksati132/personal-ai-rag.git
cd personal-ai-rag

# Start Ollama, FastAPI Backend, File Watcher, and Next.js Web UI
docker compose up -d
```

### 2. Pull Local AI Models (One-Time Setup)
```bash
# Pull the 768-dim embedding model
docker compose exec ollama ollama pull nomic-embed-text

# Pull the lightweight local reasoning model
docker compose exec ollama ollama pull llama3.2
```

### 3. Open Web UI
- 🌐 **Web UI**: [http://localhost:3000](http://localhost:3000)
- 🔌 **FastAPI Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 📂 **Add Documents**: Drop your `.pdf`, `.docx`, `.txt`, or `.md` files into `./data/documents/` — the containerized watcher indexes them automatically!

---

## 🛠️ Alternative: Manual Native Setup

For local bare-metal development without Docker:

### Prerequisites
- Python 3.10+ (tested on Python 3.11–3.14)
- Node.js 18+ and npm
- [Ollama](https://ollama.com/) installed and running locally (`ollama serve`)

### 1. Install Models
```bash
ollama pull nomic-embed-text
ollama pull llama3.2
```

### 2. Set Up Python Backend
```bash
# Create and activate virtual environment
python -m venv .venv
# On Windows: .\.venv\Scripts\Activate.ps1
# On Linux/macOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Copy environment template
cp .env.example .env
```

### 3. Launch Services
```bash
# Terminal 1: Start FastAPI Backend (Port 8000)
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Start Real-Time Document Watcher
python -m src.watcher

# Terminal 3: Start Next.js Frontend (Port 3000)
cd frontend
npm install
npm run dev
```

---

## 🧪 CLI Verification & Testing Suite

### Run Automated Tests
```bash
python -m unittest discover tests -v
```

### CLI Inspection Commands
```bash
# Index/sync documents directory
python -m src.ingest --dir data/documents

# View live database indexing statistics
python -m src.ingest --stats

# Peek at raw extracted text without indexing
python -m src.ingest --peek data/documents/attention_is_all_you_need_summary.md

# Inspect recursive chunk boundaries and character offsets
python -m src.ingest --peek-chunks data/documents/attention_is_all_you_need_summary.md

# Test semantic retrieval directly via CLI
python -m src.ingest --query "How does multi-head self-attention work?"
```

---

## ⚙️ Configuration Reference

All settings can be customized via `.env` or system environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BRAIN_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Endpoint for Ollama API |
| `BRAIN_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model for semantic search |
| `BRAIN_LLM_MODEL` | `llama3.2` | Local synthesis LLM |
| `BRAIN_SIMILARITY_THRESHOLD` | `0.40` | Minimum cosine similarity score required for grounding |
| `BRAIN_TOP_K` | `5` | Maximum context chunks retrieved per query |
| `BRAIN_CHUNK_SIZE` | `1000` | Target character size for semantic text chunking |
| `BRAIN_CHUNK_OVERLAP` | `150` | Overlap characters between adjacent chunks |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI endpoint consumed by Next.js UI |

---

## 🗺️ Project Scope & Deliberately Deferred Non-Goals

To maintain a disciplined architectural boundary, the following features were **intentionally deferred**:

- **Multi-Device Cloud Sync**: The system is strictly designed for local, offline-first execution with zero cloud telemetry. Cloud sync introduces remote key storage and privacy trade-offs outside this local-first scope.
- **Cloud LLM Fallback (OpenAI/Anthropic APIs)**: Using external APIs violates the zero-leakage guarantee. The pipeline is calibrated for local model execution (`llama3.2`, `mistral`, `phi3`).
- **User Authentication / Multi-Tenancy**: This is a single-user Personal AI Brain operating directly against the user's filesystem and SQLite instance.
- **Streaming Responses in UI**: Phase 2/4 backend responses are atomic and include verification checks across all retrieved chunks before emitting answers.

---

## 📄 License

MIT License. Free for personal and commercial exploration.
