"""Middleware for the Orchestra server."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from orchestra.server.config import ServerConfig


def add_cors_middleware(app: "FastAPI", config: "ServerConfig") -> None:
    """Configure CORS middleware on the FastAPI app."""
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def add_request_id_middleware(app: "FastAPI") -> None:
    """Add middleware that generates a UUID request ID for each request.

    The ID is returned in the ``X-Request-ID`` response header.
    """
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response

    class RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self, request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    app.add_middleware(RequestIDMiddleware)
