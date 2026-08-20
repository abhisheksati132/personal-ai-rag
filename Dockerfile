# ==============================================================================
# Personal AI Brain - FastAPI Backend & Ingestion Engine
# ==============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install system utilities (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY pyrightconfig.json .

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    BRAIN_OLLAMA_BASE_URL=http://ollama:11434 \
    BRAIN_DATA_DIR=/app/data

# Ensure data directory exists
RUN mkdir -p /app/data/documents /app/data/chroma_db

EXPOSE 8000

# Default command: start FastAPI backend
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
