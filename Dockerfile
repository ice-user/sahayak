FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SAHAYAK_SEARCH=bm25

WORKDIR /app

# Install only what the API needs: the Streamlit UI, MCP server and pytest are skipped.
# Hybrid search: build with --build-arg INSTALL_HYBRID=1 and run with SAHAYAK_SEARCH=hybrid (needs ~1 GB RAM).
ARG INSTALL_HYBRID=0
COPY requirements.txt /tmp/requirements.txt
COPY server/requirements.txt /tmp/server-requirements.txt
RUN grep -vEi '^(streamlit|mcp|pytest|fastembed|langgraph|beautifulsoup4|pypdf|rapidfuzz|rich)' /tmp/requirements.txt > /tmp/core.txt \
    && pip install -r /tmp/core.txt -r /tmp/server-requirements.txt \
    && if [ "$INSTALL_HYBRID" = "1" ]; then pip install "fastembed>=0.4"; fi

# Non-root user; --chown avoids a second layer that duplicates the files. Traces are off unless SAHAYAK_TRACES=1.
RUN useradd --create-home --uid 10001 sahayak
COPY --chown=sahayak sahayak ./sahayak
COPY --chown=sahayak server ./server
COPY --chown=sahayak data ./data
USER sahayak

# Render injects PORT (10000 by default); locally it falls back to 8000.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'), timeout=3)"
CMD ["sh", "-c", "exec uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 100 --timeout-keep-alive 5"]
