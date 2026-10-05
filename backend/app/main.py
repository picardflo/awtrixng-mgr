"""FastAPI entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import __version__
from app.api.routes import (
    auth as auth_routes,
)
from app.api.routes import (
    backup,
    connectors,
    devices,
    health,
    icons,
    places,
    reminders,
    summary,
    widgets,
)
from app.api.routes import (
    settings as settings_routes,
)
from app.connectors.registry import load_all as load_connectors
from app.core import auth
from app.core.config import get_settings
from app.core.errors import AwtrixNgError
from app.core.logging import configure_logging
from app.db.session import init_db
from app.services.ng.icons import catalogue as icon_catalogue
from app.services.scheduler.loop import scheduler

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("awtrixng-mgr %s starting", __version__)
    load_connectors()
    try:
        init_db()
    except AwtrixNgError as exc:
        # An environment problem deserves one readable line, not a 200-line
        # traceback repeated on every container restart.
        log.error("cannot start: %s", exc.message)
        raise SystemExit(1) from None

    await scheduler.start()
    # Warm the icon catalogue in the background: the first search would
    # otherwise pay several seconds of paging. A failure here is harmless, the
    # next search simply retries.
    warm = asyncio.create_task(_warm_icon_catalogue())
    yield
    warm.cancel()
    await scheduler.stop()
    log.info("awtrixng-mgr stopping")


async def _warm_icon_catalogue() -> None:
    try:
        await icon_catalogue.load()
    except (AwtrixNgError, asyncio.CancelledError):
        log.info("icon catalogue not preloaded; it will load on first search")


#: The only paths reachable without a session. Everything else is denied by
#: default — including /api/docs and the OpenAPI schema — so a route added
#: later is protected without anyone having to remember to say so.
OPEN_PATHS = frozenset(
    {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}
)


def create_app() -> FastAPI:
    application = FastAPI(
        title="awtrixng-mgr",
        version=__version__,
        summary="Connect your services. Build your widgets. Light up AWTRIX.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    application.include_router(health.router, prefix="/api")
    application.include_router(auth_routes.router, prefix="/api")
    application.include_router(devices.router, prefix="/api")
    application.include_router(connectors.router, prefix="/api")
    application.include_router(widgets.router, prefix="/api")
    application.include_router(icons.router, prefix="/api")
    application.include_router(places.router, prefix="/api")
    application.include_router(reminders.router, prefix="/api")
    application.include_router(settings_routes.router, prefix="/api")
    application.include_router(summary.router, prefix="/api")
    application.include_router(backup.router, prefix="/api")

    @application.middleware("http")
    async def require_authentication(request: Request, call_next):
        if not auth.is_required() or request.url.path in OPEN_PATHS:
            return await call_next(request)
        if auth.is_valid_session(request.cookies.get(auth.COOKIE_NAME)):
            return await call_next(request)
        # A dashboard reads the summary with a token of its own. It opens that
        # one route: listed here rather than in OPEN_PATHS, because without a
        # token it stays as closed as the rest.
        bearer = request.headers.get("authorization")
        if request.url.path == "/api/summary" and auth.reads_summary(bearer):
            return await call_next(request)

        from fastapi.responses import JSONResponse

        # Saying *which* refusal it is, when the caller already knows it sent a
        # token. A dashboard that gets "authentication required" while sending
        # one has no way to tell a wrong token from a route this version does
        # not have yet — both were the same message, and both happened.
        if bearer and bearer.lower().startswith("bearer "):
            detail, code = (
                ("This token does not open that path.", "auth.token_refused")
                if request.url.path == "/api/summary"
                else ("A token only opens /api/summary.", "auth.token_scope")
            )
        else:
            detail, code = "Authentication required.", "auth.required"

        return JSONResponse(status_code=401, content={"detail": detail, "code": code})

    @application.exception_handler(AwtrixNgError)
    async def _domain_error(_request, exc: AwtrixNgError):
        from fastapi.responses import JSONResponse

        # detail stays English and readable; code is what the UI translates.
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "code": exc.code, "params": exc.params},
        )

    return application


app = create_app()
