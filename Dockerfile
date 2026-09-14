FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

USER appuser

ENV SQLITE_PATH=/data/analytics.db \
    HOST=0.0.0.0 \
    PORT=8091

EXPOSE 8091

CMD ["uvicorn", "rpc_analytics.main:app", "--host", "0.0.0.0", "--port", "8091"]
