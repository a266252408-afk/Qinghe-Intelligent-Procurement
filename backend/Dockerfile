FROM python:3.11.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 非 root 运行；命名卷首次挂载时会继承这里的目录属主
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads /app/chroma \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 嵌入式 Chroma 与 SQLite 均不适合多进程写，默认单 worker
CMD ["sh", "-c", "mkdir -p data/uploads chroma && python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
