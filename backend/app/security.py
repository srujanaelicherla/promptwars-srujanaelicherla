"""Response headers for every application-generated response."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

CallNext = Callable[[Request], Awaitable[Response]]


def apply_security_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"


async def guard_requests(request: Request, call_next: CallNext) -> Response:
    response = await call_next(request)
    apply_security_headers(response)
    return response
