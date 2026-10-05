"""A configured instance of a connector type."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.base import HealthStatus, utcnow


class ConnectorInstance(SQLModel, table=True):
    __tablename__ = "connector"

    id: int | None = Field(default=None, primary_key=True)
    #: Registered connector id, e.g. "weather".
    type: str = Field(index=True)
    name: str = Field(index=True)

    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    #: {field name: Fernet token}. Per field, so the API can report which ones
    #: hold a value without ever decrypting them (ADR-005).
    secrets: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    enabled: bool = True

    status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    last_success: datetime | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
