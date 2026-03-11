"""Server configuration via Pydantic Settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Configuration for the Orchestra HTTP server."""

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    api_prefix: str = "/api/v1"
    sse_heartbeat_interval: int = 15
    sse_retry_ms: int = 5000
