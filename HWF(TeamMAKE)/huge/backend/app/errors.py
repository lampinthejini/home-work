"""오류 응답은 {"code", "message"} 한 가지 모양 (TRD 4-3, API 명세서 2장)."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def notFound() -> ApiError:
    return ApiError(404, "NOT_FOUND", "찾을 수 없습니다.")


async def apiErrorHandler(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"code": exc.code, "message": exc.message})


async def unexpectedErrorHandler(_request: Request, _exc: Exception):
    # 원인은 응답에 넣지 않는다. 예외는 이 뒤에 서버 로그로 남는다 (Starlette 가 다시 던짐)
    return JSONResponse(status_code=500, content={"code": "SERVER_ERROR", "message": "잠시 후 다시 시도해 주세요."})


async def validationErrorHandler(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:])
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": f"{field}: {first.get('msg', '형식 오류')}"})
