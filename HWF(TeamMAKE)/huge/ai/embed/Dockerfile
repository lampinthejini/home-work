FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 HF_HOME=/hf
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# GPU 는 llm-rt·stt 가 쓰므로 CPU 전용 torch 만 깐다 (TRD 6-2: 임베딩은 CPU)
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
EXPOSE 9003
# 첫 실행은 BGE-M3(약 2.3GB)를 내려받느라 몇 분 걸린다
HEALTHCHECK --interval=15s --timeout=5s --retries=80 CMD curl -fs http://localhost:9003/health || exit 1
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9003"]
