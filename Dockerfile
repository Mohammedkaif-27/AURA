# Use Python 3.11 slim image for optimal size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Create data directories if they don't exist
RUN mkdir -p backend/data backend/chroma_db

# Expose port 8080 (Cloud Run requirement)
EXPOSE 8080

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Run the application with uvicorn
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
