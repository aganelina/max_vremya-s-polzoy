from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger("api")

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
}

class ApiError(Exception):

    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(code)

class NotFound(ApiError):
    def __init__(self, code: str = "not_found") -> None:
        super().__init__(404, code)

class Forbidden(ApiError):
    def __init__(self, code: str = "forbidden") -> None:
        super().__init__(403, code)

class Conflict(ApiError):
    def __init__(self, code: str) -> None:
        super().__init__(409, code)

class Unprocessable(ApiError):
    def __init__(self, code: str) -> None:
        super().__init__(422, code)

def _body(code: str) -> dict[str, str]:
    return {"code": code}

async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(_body(exc.code), status_code=exc.status)

async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else ""
    code = detail if detail and detail.replace("_", "").isalnum() and detail.islower() else ""
    code = code or _STATUS_CODES.get(exc.status_code, "http_error")
    return JSONResponse(_body(code), status_code=exc.status_code, headers=exc.headers)

async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [".".join(str(p) for p in err.get("loc", ())) for err in exc.errors()]
    log.info("request_validation_failed", fields=fields)
    return JSONResponse(_body("validation_error"), status_code=422)

async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", error_type=type(exc).__name__)
    return JSONResponse(_body("internal_error"), status_code=500)

def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
