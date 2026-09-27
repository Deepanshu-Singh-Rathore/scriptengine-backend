FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for compiling and running
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port (default 8000, overridden by PORT env in Render/Railway/Koyeb)
EXPOSE 8000

# Start FastAPI application
CMD ["python", "run.py"]
