"""Huge OCR 서비스 — PaddleOCR (한국어 PP-OCRv5, CPU).

- POST /ocr : 이미지(PNG·JPG 바이트) → 읽는 순서대로 정렬한 줄 목록과 평균 신뢰도.
GPU 는 llm-rt·stt 가 쓰므로 CPU 로 돈다 (TRD 6-2). 한 번에 한 장씩 처리한다.
"""

import io
import os
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from paddleocr import PaddleOCR
from PIL import Image

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_SIDE = int(os.environ.get("OCR_MAX_SIDE", "2400"))

app = FastAPI(title="huge-ocr")


def localModels() -> dict:
    """받아 둔 모델 경로. PaddleX 는 이름만 주면 캐시가 있어도 접속부터 시도하므로, 망이 끊긴 실행에서는 경로를 직접 준다."""
    root = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", "/hf/paddlex")) / "official_models"
    det, rec = "PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec"
    if not ((root / det).is_dir() and (root / rec).is_dir()):
        return {}
    return {"text_detection_model_name": det, "text_detection_model_dir": str(root / det),
            "text_recognition_model_name": rec, "text_recognition_model_dir": str(root / rec)}


engine = PaddleOCR(lang="korean", device="cpu", use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_textline_orientation=False, **localModels())
lock = threading.Lock()


def loadImage(data: bytes) -> np.ndarray:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    scale = MAX_SIDE / max(image.size)
    if scale < 1:
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return np.asarray(image)[:, :, ::-1]  # RGB → BGR (PaddleOCR 입력)


def toLines(texts: list[str], scores: list[float], boxes) -> list[dict]:
    """글자 상자를 위→아래, 같은 줄이면 왼→오른쪽 순서로 묶는다."""
    items = []
    for text, score, box in zip(texts, scores, boxes, strict=False):
        x0, y0, x1, y1 = (float(v) for v in box[:4])
        if text.strip():
            items.append({"text": text.strip(), "conf": float(score), "x": x0, "y": (y0 + y1) / 2, "h": max(y1 - y0, 1.0)})
    items.sort(key=lambda it: (it["y"], it["x"]))
    lines: list[list[dict]] = []
    for it in items:
        if lines and abs(lines[-1][0]["y"] - it["y"]) < lines[-1][0]["h"] * 0.6:
            lines[-1].append(it)
        else:
            lines.append([it])
    result = []
    for line in lines:
        line.sort(key=lambda it: it["x"])
        result.append({"text": " ".join(it["text"] for it in line), "conf": round(sum(it["conf"] for it in line) / len(line), 4)})
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(request: Request):
    data = await request.body()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "image required (max 15MB)")
    try:
        image = loadImage(data)
    except Exception as exc:  # noqa: BLE001 — 깨진 이미지
        raise HTTPException(400, "unreadable image") from exc
    started = time.monotonic()
    with lock:
        results = engine.predict(image)
    texts, scores, boxes = [], [], []
    for res in results:
        texts += list(res["rec_texts"])
        scores += [float(s) for s in res["rec_scores"]]
        boxes += [list(b) for b in res["rec_boxes"]]
    lines = toLines(texts, scores, boxes)
    confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
    return {"lines": lines, "text": "\n".join(line["text"] for line in lines), "confidence": confidence,
            "seconds": round(time.monotonic() - started, 2)}
