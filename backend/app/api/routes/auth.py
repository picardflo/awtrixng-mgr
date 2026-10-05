"""Logging in and out.

These three routes are the only ones reachable without a session, together
with /api/health — which the container's own healthcheck calls and which
returns nothing but a status and a version.
"""

import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.core import auth
from app.core.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class AuthStatus(BaseModel):
    #: False when no password is configured: everything is open.
    required: bool
    authenticated: bool


class LoginResult(BaseModel):
    ok: bool
    message: str
    code: str


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=get_settings().secure_cookie,
        path="/",
    )


@router.get("/status", response_model=AuthStatus)
def status(request: Request) -> AuthStatus:
    """Whether a password is configured, and whether this browser is signed in.

    The frontend asks before showing anything, so an installation with no
    password never sees a login screen.
    """
    return AuthStatus(
        required=auth.is_required(),
        authenticated=auth.is_valid_session(request.cookies.get(auth.COOKIE_NAME)),
    )


@router.post("/login", response_model=LoginResult)
async def login(payload: LoginRequest, response: Response) -> LoginResult:
    if not auth.is_required():
        return LoginResult(
            ok=True, message="No password is configured.", code="auth.not_required"
        )

    if not await auth.check_password(payload.password):
        return LoginResult(ok=False, message="Wrong password.", code="auth.wrong_password")

    _set_cookie(response, auth.issue_session())
    log.info("signed in")
    return LoginResult(ok=True, message="Signed in.", code="auth.signed_in")


@router.post("/logout", response_model=LoginResult)
def logout(response: Response) -> LoginResult:
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return LoginResult(ok=True, message="Signed out.", code="auth.signed_out")
