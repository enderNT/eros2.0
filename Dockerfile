FROM python:3.13-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src ./src
COPY content ./content
RUN pip install --no-cache-dir .
RUN useradd --create-home appuser && mkdir -p /data && chown appuser:appuser /data
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "agente.app:app", "--host", "0.0.0.0", "--port", "8000"]
