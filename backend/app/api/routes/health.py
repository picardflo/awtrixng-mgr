from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core import language

router = APIRouter(tags=["system"])


class Health(BaseModel):
    status: str
    version: str
    #: The language the clocks speak. Here because this is the only route that
    #: answers without a password, and because "the interface says French but
    #: the matrix says MODERATE" is otherwise undiagnosable from outside: one
    #: has to trust what a form shows about a value held in another process.
    #:
    #: Nothing private: it is a two-letter code, and the version beside it is
    #: already public.
    clock_language: str


@router.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", version=__version__, clock_language=language.current())
