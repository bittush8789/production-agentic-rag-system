# ==============================================================================
# Enterprise Production Dockerfile for IT Support Agentic RAG Copilot
# Features: Keycloak RBAC, NeMo & Presidio Guardrails, Hybrid RAG, Non-Root User
# ==============================================================================

FROM python:3.11-slim

# Set environment variables for production performance and security
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRANSFORMERS_NO_TF=1 \
    USE_TF=0 \
    PORT=8080 \
    WORKERS=2 \
    PYTHONPATH=/app

WORKDIR /app

# Install security certificates, curl for healthcheck, and build utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create secure, unprivileged system user (CIS Benchmark compliance)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -m appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm

# Copy application source code
COPY . .

# Set up volume directories and assign ownership to appuser
RUN mkdir -p /app/data /app/uploads && \
    chown -R appuser:appgroup /app

# Run as non-root user
USER appuser

# Container Healthcheck (Cloud native readiness)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || exit 1

EXPOSE 8080

# Production ASGI server with proxy headers and configurable workers
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WORKERS:-2} --proxy-headers --forwarded-allow-ips '*'"]
