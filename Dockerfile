# ============================================================
# Stage 1 — Builder
# ============================================================
FROM python:3.9-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir \
    --prefix=/install \
    -r requirements.txt


# ============================================================
# Stage 2 — Runtime
# ============================================================
FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

RUN mkdir -p /app/static/uploads /app/templates && \
    chmod +x /app/start.sh

RUN useradd \
        --create-home \
        --shell /usr/sbin/nologin \
        appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=30s \
    --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=5)"

CMD ["./start.sh"]
