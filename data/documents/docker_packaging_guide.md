# Docker Packaging Guide for Personal AI Brain

The Personal AI Brain uses Docker Compose to orchestrate 4 core services:
1. `ollama`: Local LLM and embedding server with persistent model storage.
2. `backend`: FastAPI server providing `/query`, `/files`, `/health`, and `/stats` endpoints.
3. `watcher`: Real-time watchdog file watcher that auto-indexes newly dropped documents.
4. `frontend`: Next.js web application with the signature evidence trail strip.

All four containers share a dedicated bridge network with persistent volume storage for vectors and SQLite state.
