FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Non-root user for security
RUN useradd -m -u 1001 neurodrug && chown -R neurodrug:neurodrug /app
USER neurodrug

# Create runtime directories
RUN mkdir -p checkpoints model_registry mlruns

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health/ || exit 1

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
