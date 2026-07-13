from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import run_migrations
from .routers.auth import router as auth_router
from .routers.categories import router as categories_router
from .routers.contacts import router as contacts_router

run_migrations()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="연락처 관리 웹 서비스", version="1.0.0")
# /docs, /redoc, /openapi.json은 기본값 그대로 노출 (학습용이므로 비공개 처리 안 함)

app.include_router(auth_router)
app.include_router(contacts_router)
app.include_router(categories_router)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

VALIDATION_ERROR_MESSAGES = {
    "string_too_short": "입력값이 너무 짧습니다.",
    "string_too_long": "입력값이 너무 깁니다.",
    "string_pattern_mismatch": "입력 형식이 올바르지 않습니다.",
    "missing": "필수 입력값이 누락되었습니다.",
    "int_parsing": "숫자 형식이 올바르지 않습니다.",
    "int_type": "숫자 형식이 올바르지 않습니다.",
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    if not errors:
        return JSONResponse(status_code=422, content={"detail": "입력값이 올바르지 않습니다."})

    first = errors[0]
    if first["type"] == "value_error":
        message = first["msg"].removeprefix("Value error, ")
    else:
        message = VALIDATION_ERROR_MESSAGES.get(first["type"], "입력값이 올바르지 않습니다.")

    if len(errors) > 1:
        message += f" (그 외 {len(errors) - 1}건의 오류가 더 있습니다.)"

    return JSONResponse(status_code=422, content={"detail": message})


@app.get("/")
def serve_index():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))
