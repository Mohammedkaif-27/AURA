# Use Python 3.11 slim image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding models at build time (avoids first-request latency)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy the entire project
COPY . .

# Create data directories
RUN mkdir -p backend/data backend/chroma_db

EXPOSE 8080

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
