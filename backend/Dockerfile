FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN addgroup --system --gid 1001 appgroup && adduser --system --uid 1001 --ingroup appgroup appuser

COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/backend-requirements.txt

COPY app ./app
COPY backend ./backend

RUN mkdir -p /app/backend/output && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os, sys, urllib.request; port = os.getenv('BACKEND_PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/api/filter/health', timeout=3); sys.exit(0)"

CMD ["sh", "-c", "uvicorn backend.src.server:app --host ${BACKEND_HOST:-0.0.0.0} --port ${BACKEND_PORT:-8000}"]
