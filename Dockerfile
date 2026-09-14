FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod +x /docker-entrypoint.sh \
    && mkdir -p /data \
    && chown appuser:appuser /data

ENV SQLITE_PATH=/data/analytics.db \
    HOST=0.0.0.0 \
    PORT=8091

EXPOSE 8091

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "rpc_analytics.main:app", "--host", "0.0.0.0", "--port", "8091"]
