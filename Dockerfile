FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first so code changes don't invalidate this layer
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
# Strip CRLF in case the repo was checked out on Windows
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Celery warns loudly when run as root
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/api/health/', timeout=4)"

CMD ["./start.sh"]
