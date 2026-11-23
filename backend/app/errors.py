"""Error handlers that return a stable JSON shape and no internal detail."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.bookings import BookingError
from app.schemas import ErrorCode, ErrorResponse
from app.security import apply_security_headers

logger = logging.getLogger("lablink")

_IGNORED_LOC = {"body", "query", "path", "header", "cookie"}
_MAX_FIELDS = 20


def error_response(
    status_code: int,
    error: ErrorCode,
    message: str,
    fields: list[str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=error, message=message, fields=fields)
    response = JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))
    apply_security_headers(response)
    return response


def validation_fields(exc: RequestValidationError) -> list[str]:
    """Collect field locations only. Submitted values are discarded."""

    names: set[str] = set()
    for error in exc.errors():
        loc = error.get("loc")
        if not isinstance(loc, (tuple, list)):
            continue
        parts: list[str] = []
        for part in loc:
            if isinstance(part, str) and part in _IGNORED_LOC:
                continue
            if isinstance(part, (str, int)):
                parts.append(str(part)[:80])
        if parts:
            names.add(".".join(parts)[:120])
        if len(names) >= _MAX_FIELDS:
            break
    return sorted(names)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(BookingError, booking_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if exc.status_code == 404:
        error: ErrorCode = "not_found"
        message = "The requested resource does not exist."
    elif exc.status_code == 405:
        error = "method_not_allowed"
        message = "This method is not allowed for the requested resource."
    else:
        error = "request_failed"
        message = "The request could not be completed."

    response = error_response(exc.status_code, error, message)
    headers = exc.headers or {}
    allow = headers.get("Allow")
    if allow:
        response.headers["Allow"] = allow
    return response


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return error_response(
        422,
        "invalid_request",
        "The request is invalid.",
        validation_fields(exc),
    )


async def booking_error_handler(_request: Request, exc: BookingError) -> JSONResponse:
    return error_response(exc.status_code, exc.error, exc.message)


async def unhandled_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("Unhandled application error: %s", type(exc).__name__)
    return error_response(500, "internal_error", "The request could not be completed.")
