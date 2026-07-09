from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import engine
from .models import Base
from .routers.auth import router as auth_router
from .routers.categories import router as categories_router
from .routers.contacts import router as contacts_router

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="연락처 관리 웹 서비스", version="1.0.0")
# /docs, /redoc, /openapi.json은 기본값 그대로 노출 (학습용이므로 비공개 처리 안 함)

app.include_router(auth_router)
app.include_router(contacts_router)
app.include_router(categories_router)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def serve_index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))
