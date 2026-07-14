# Use Python 3.11 slim image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (tesseract-ocr for scanned PDF text extraction)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# NOTE: In HF API mode (HF_TOKEN set), models are NOT loaded locally.
# The heavy sentence-transformers + torch are only needed for local mode.
# To keep the Docker image small for Render/cloud, we skip model pre-download.
# If you need local mode, uncomment the lines below:
# RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
# RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy the entire project
COPY . .

# Create data directories (must exist before startup auto-ingestion)
RUN mkdir -p backend/data/manuals backend/data/policies backend/chroma_db

EXPOSE 8080

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
