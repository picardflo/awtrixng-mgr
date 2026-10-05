"""Connector DTOs. Secrets go in, they never come back out (§5.2)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import HealthStatus


class ConnectorCreate(BaseModel):
    type: str
    name: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    #: Plaintext on the way in only; encrypted before it touches the database.
    secrets: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class ConnectorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    config: dict[str, Any] | None = None
    #: Only the keys present are changed; "" clears one.
    secrets: dict[str, str] | None = None
    enabled: bool | None = None


class ConnectorRead(BaseModel):
    id: int
    type: str
    name: str
    config: dict[str, Any]
    #: Which secret fields hold a value. Never the values themselves.
    secrets_set: list[str]
    enabled: bool
    status: HealthStatus
    last_success: datetime | None
    last_error: str | None
    last_error_code: str | None
    consecutive_failures: int
