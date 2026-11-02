"""Huge 임베딩 서비스 — BGE-M3 (sentence-transformers, CPU).

- POST /embed : {"texts": [...]} → {"vectors": [[1024개 숫자], ...]} (길이 1로 맞춤 → 내적 = 코사인 유사도)
질문 DB 불러올 때·질문 만들 때 비슷한 질문 찾기(RAG)와 베낌·중복 확인에 쓴다 (TRD 7-4).
"""

import os
import threading

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
MAX_TEXTS = 64
MAX_CHARS = 2000

torch.set_num_threads(int(os.environ.get("EMBED_THREADS", "4")))
model = SentenceTransformer(MODEL_NAME, device="cpu")
model.max_seq_length = 512
lock = threading.Lock()
app = FastAPI(title="huge-embed")


class EmbedIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_TEXTS)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "dim": model.get_sentence_embedding_dimension()}


@app.post("/embed")
def embed(body: EmbedIn):
    texts = [t[:MAX_CHARS] for t in body.texts]
    if any(not t.strip() for t in texts):
        raise HTTPException(422, "빈 글은 넣을 수 없습니다")
    with lock:
        vectors = model.encode(texts, batch_size=16, normalize_embeddings=True, convert_to_numpy=True)
    return {"vectors": [[round(float(x), 6) for x in v] for v in vectors]}
