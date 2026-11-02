FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PADDLE_PDX_CACHE_HOME=/hf/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
# opencv(PaddleOCR 의존) 가 쓰는 시스템 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends curl libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
EXPOSE 9002
HEALTHCHECK --interval=15s --timeout=5s --retries=40 CMD curl -fs http://localhost:9002/health || exit 1
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9002"]
