FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run injects PORT env var — uvicorn reads it via backend/main.py
ENV PORT=8080
ENV PYTHONPATH=/app

# Single entrypoint — backend/main.py is the authoritative main
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]