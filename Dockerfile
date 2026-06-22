FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORE_DB_PATH=/data/store.sqlite \
    WIKI_PATH=/app/wiki.md \
    PLAYBOOK_PATH=/app/playbook.md

WORKDIR /app

# Instala dependencias + paquete
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Contenido leído en runtime: Wiki (datos factuales) + Playbook (directrices)
COPY wiki.md ./
COPY playbook.md ./

# Volumen para la memoria corta (SQLite). En Coolify montar un volumen persistente en /data.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Healthcheck simple para Coolify
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "agente.app:app", "--host", "0.0.0.0", "--port", "8000"]
