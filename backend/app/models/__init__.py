"""Persistence models.

Every model must be imported here: Alembic discovers tables through
SQLModel.metadata, which is only populated on import.
"""

from app.models.base import HealthStatus, utcnow
from app.models.connector import ConnectorInstance
from app.models.device import Device
from app.models.reminder import Reminder, ReminderTarget
from app.models.setting import LANGUAGE, Setting
from app.models.widget import Widget, WidgetTarget

__all__ = [
    "LANGUAGE",
    "Setting",
    "ConnectorInstance",
    "Device",
    "HealthStatus",
    "Reminder",
    "ReminderTarget",
    "Widget",
    "WidgetTarget",
    "utcnow",
]
