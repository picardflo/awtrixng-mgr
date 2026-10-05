"""Installation settings, reachable from the interface.

Only the display language today. It lived in `.env` alone, which meant someone
switching the interface to French had no way to learn that the clocks keep
speaking English — and no way to change it without opening a file, which the
README promises nobody has to do.
"""

from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from sqlmodel import select

from app.api.deps import SessionDep
from app.core import language
from app.models import LANGUAGE, Setting, utcnow
from app.services.scheduler.loop import scheduler

router = APIRouter(tags=["settings"])


class Settings(BaseModel):
    """What an installation decides for itself."""

    #: The language of the words pushed to the matrix. Not the interface
    #: language: that one lives in each browser, because two people may read
    #: the same installation in two languages, while a clock has no reader to
    #: ask at three in the morning.
    language: str

    @field_validator("language")
    @classmethod
    def _supported(cls, value: str) -> str:
        if value not in language.SUPPORTED:
            raise ValueError(f"language must be one of {', '.join(language.SUPPORTED)}")
        return value


def load_into_memory(session) -> None:
    """Read the stored language once, at startup.

    Projection code runs far from a session — inside a connector, during a
    push — so it reads a module-level value rather than opening one per widget.
    """
    row = session.exec(select(Setting).where(Setting.key == LANGUAGE)).first()
    language.remember(row.value if row else None)


@router.get("/settings", response_model=Settings)
def read_settings() -> Settings:
    return Settings(language=language.current())


@router.put("/settings", response_model=Settings)
def write_settings(payload: Settings, session: SessionDep) -> Settings:
    """Change them. Takes effect on the next push, not at the next restart."""
    row = session.exec(select(Setting).where(Setting.key == LANGUAGE)).first()
    if row is None:
        row = Setting(key=LANGUAGE)
    row.value = payload.language
    row.updated_at = utcnow()
    session.add(row)
    session.commit()

    language.remember(payload.language)

    # The words change, so every widget has to say them again. Otherwise the
    # air quality widget keeps its English for half an hour and the setting
    # looks broken.
    scheduler.refresh_all()
    return Settings(language=language.current())
