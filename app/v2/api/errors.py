import uuid

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class V2APIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable


def error_body(error: V2APIError, request_id: str | None = None) -> dict:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
            "retryable": error.retryable,
            "request_id": request_id or str(uuid.uuid4()),
        }
    }


async def v2_error_handler(_request: Request, exc: V2APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/v2"):
        error = V2APIError(
            422,
            "VALIDATION_ERROR",
            "请求参数无效",
            {"errors": jsonable_encoder(exc.errors())},
        )
        return JSONResponse(status_code=422, content=error_body(error))
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
    )
