# The control panel is a Vite/React app; it is compiled here and copied into
# the Python image, so the whole thing still ships as one container.
FROM node:22-slim AS panel
WORKDIR /app/panel-ui
COPY panel-ui/package.json panel-ui/package-lock.json ./
RUN npm ci
COPY panel-ui ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
COPY --from=panel /app/src/agente/web/static/panel ./src/agente/web/static/panel
COPY content ./content
RUN pip install --no-cache-dir .
RUN useradd --create-home appuser && mkdir -p /data && chown appuser:appuser /data
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "agente.app:app", "--host", "0.0.0.0", "--port", "8000"]
