"""One error envelope for every failure (AD-6, NFR3)."""

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DEFAULT_MESSAGES, DomainError, ErrorCode

logger = logging.getLogger(__name__)

STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.DATABASE_UNAVAILABLE: 503,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.ORDER_NOT_FOUND: 404,
    ErrorCode.ORDER_NOT_DELIVERED: 422,
    ErrorCode.RETURN_WINDOW_EXPIRED: 422,
    ErrorCode.INVALID_QUANTITY: 422,
    ErrorCode.LINE_NOT_ON_ORDER: 422,
}

CODE_BY_HTTP_STATUS: dict[int, ErrorCode] = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
}


def error_response(
    status_code: int, code: ErrorCode, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code.value, "message": message}},
        headers=headers,
    )


async def handle_domain_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return error_response(STATUS_BY_CODE.get(exc.code, 500), exc.code, exc.message)


async def handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    problems = "; ".join(
        f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
        for err in exc.errors()
    )
    message = DEFAULT_MESSAGES[ErrorCode.VALIDATION_ERROR]
    if problems:
        message = f"{message} {problems}"
    return error_response(422, ErrorCode.VALIDATION_ERROR, message)


async def handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = CODE_BY_HTTP_STATUS.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return error_response(
        exc.status_code, code, DEFAULT_MESSAGES[code], headers=getattr(exc, "headers", None)
    )


async def handle_database_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Database error: %s", exc)
    code = ErrorCode.DATABASE_UNAVAILABLE
    return error_response(STATUS_BY_CODE[code], code, DEFAULT_MESSAGES[code])


async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    code = ErrorCode.INTERNAL_ERROR
    return error_response(STATUS_BY_CODE[code], code, DEFAULT_MESSAGES[code])


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(sqlite3.OperationalError, handle_database_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
