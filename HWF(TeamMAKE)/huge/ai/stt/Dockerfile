FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY server.py .
EXPOSE 9000
HEALTHCHECK --interval=15s --timeout=5s --retries=40 CMD curl -fs http://localhost:9000/health || exit 1
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9000"]
