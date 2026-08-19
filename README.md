# 🧠 Personal AI Brain (Local-First RAG Pipeline)

A privacy-focused, zero-cloud Retrieval-Augmented Generation (RAG) system running entirely on your local machine.

---

## 🏗️ Architecture (Phase 1: Ingestion Engine)

```text
📁 Local Files (.pdf, .docx, .txt, .md)
   │
   ▼
📂 Ingestion Pipeline (src/ingest.py)
   │
   ├──▶ 🔍 SHA-256 & Timestamp Check (SQLite: data/brain.db)
   │     └─► Skips unchanged files automatically
   │
   ├──▶ 📄 Extractor Factory (src/extractors/)
   │     ├─► PDFExtractor (pypdf)
   │     ├─► DocxExtractor (python-docx)
   │     └─► TextExtractor (.txt, .md with UTF-8 / fallback decoding)
   │
   ├──▶ ✂️ Recursive Chunker (src/chunker.py)
   │     └─► Sentence & paragraph semantic splitting + overlap
   │
   ├──▶ 🧠 Ollama Embedder (src/embeddings.py)
   │     └─► nomic-embed-text (768-dim local embeddings)
   │
   └──▶ 💾 ChromaDB (src/vector_store.py)
         └─► Persistent vector storage (data/chroma_db)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.14)
- (Optional for live embeddings) [Ollama](https://ollama.com/) with `nomic-embed-text`:
  ```bash
  ollama pull nomic-embed-text
  ```

### 2. Environment Setup
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

---

## 🛠️ Usage

### Ingest Documents
Point the ingestion script at your documents folder:
```powershell
# Ingest data/documents directory using local Ollama nomic-embed-text
python -m src.ingest --dir data/documents

# Or run with mock embeddings for offline testing / development
python -m src.ingest --dir data/documents --mock-embeddings
```

### Ingestion CLI Options
```text
options:
  --dir DIR             Directory to scan and index (default: ./data/documents)
  --file FILE           Index a specific single file
  --peek FILE           Peek at raw extracted text and metadata without indexing
  --peek-chunks FILE    Inspect generated chunks and boundary splits for a file
  --query TEXT          Run a test query against indexed chunks in ChromaDB
  --force               Force re-indexing even if file is unchanged
  --mock-embeddings     Use deterministic mock embedder (no Ollama required)
  --stats               Display indexing statistics table
  --clear               Clear all vectors and SQLite records
```

### Inspect Raw Text & Chunks (Verification Tools)
```powershell
# Peek at raw extracted text from a PDF, Word doc, or Markdown file
python -m src.ingest --peek data/documents/local_rag_overview.pdf

# Inspect how a document is chunked (boundaries, character ranges, IDs)
python -m src.ingest --peek-chunks data/documents/attention_is_all_you_need_summary.md

# Test semantic retrieval directly from ChromaDB
python -m src.ingest --query "How does self-attention work?" --mock-embeddings
```

### Check Database Statistics
```powershell
python -m src.ingest --stats
```

---

## 🧪 Running Tests

Run the full automated test suite:
```powershell
.\.venv\Scripts\python.exe -m unittest discover tests -v
```

---

## 📁 Project Structure

```text
rag/
├── data/
│   ├── documents/          # Place your PDFs, DOCX, TXT, MD files here
│   ├── chroma_db/          # Persistent ChromaDB vector storage
│   └── brain.db            # SQLite state tracking & file metadata
├── src/
│   ├── config.py           # App settings & directory paths
│   ├── db.py               # SQLite metadata manager (hash & mtime tracker)
│   ├── chunker.py          # Recursive semantic text chunker
│   ├── embeddings.py       # Ollama nomic-embed-text & mock embedder
│   ├── vector_store.py     # ChromaDB client wrapper
│   ├── ingest.py           # Ingestion pipeline & CLI
│   └── extractors/         # File format extractors (.pdf, .docx, .txt, .md)
│       ├── base.py
│       ├── pdf_extractor.py
│       ├── docx_extractor.py
│       ├── text_extractor.py
│       └── factory.py
├── tests/                  # Automated unit & integration test suite
│   ├── test_extractors.py
│   ├── test_chunker.py
│   ├── test_db.py
│   ├── test_vector_store.py
│   └── test_ingest.py
├── requirements.txt
└── README.md
```
