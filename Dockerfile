# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# System dependencies:
#  - libmagic1: MIME sniffing for upload validation
#  - libjpeg/zlib: Pillow image codecs
#  - curl: container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libjpeg62-turbo \
    zlib1g \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY scripts ./scripts
COPY test_assets ./test_assets

RUN mkdir -p /app/uploads /app/output_reports

EXPOSE 8000

EXPOSE 8000

ENV PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
