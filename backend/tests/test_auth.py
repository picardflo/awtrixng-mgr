"""Authentication.

Security code, so the tests state the guarantees rather than the mechanics:
what is refused, what is accepted, and what stays open whatever happens.
"""

import re
import time

import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import get_settings
from app.core.crypto import _fernet, derived_fernet
from app.main import OPEN_PATHS

PASSWORD = "correct horse battery staple"


@pytest.fixture
def secured(monkeypatch):
    """An installation with a password, and no delay on failure."""
    monkeypatch.setenv("AWTRIXNG_PASSWORD", PASSWORD)
    monkeypatch.setattr(auth, "FAILED_ATTEMPT_DELAY", 0.0)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anonymous(client, secured):
    """A client against a secured installation, not signed in."""
    return client


def sign_in(test_client: TestClient) -> None:
    response = test_client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.json()["ok"] is True


# -- No password: nothing changes for an existing installation ----------------


def test_without_password_everything_stays_open(client):
    assert client.get("/api/devices").status_code == 200
    assert client.get("/api/auth/status").json() == {
        "required": False,
        "authenticated": False,
    }


def test_login_without_password_configured_is_a_no_op(client):
    response = client.post("/api/auth/login", json={"password": "anything"})
    assert response.json()["code"] == "auth.not_required"
    assert auth.COOKIE_NAME not in response.cookies


# -- With a password ----------------------------------------------------------


def test_protected_route_refuses_without_a_session(anonymous):
    response = anonymous.get("/api/devices")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.required"


def test_wrong_password_grants_nothing(anonymous):
    response = anonymous.post("/api/auth/login", json={"password": "wrong"})
    assert response.json()["ok"] is False
    assert response.json()["code"] == "auth.wrong_password"
    assert auth.COOKIE_NAME not in response.cookies
    assert anonymous.get("/api/devices").status_code == 401


def test_right_password_opens_the_application(anonymous):
    sign_in(anonymous)
    assert anonymous.get("/api/devices").status_code == 200
    assert anonymous.get("/api/auth/status").json() == {
        "required": True,
        "authenticated": True,
    }


def test_logout_closes_it_again(anonymous):
    sign_in(anonymous)
    anonymous.post("/api/auth/logout")
    assert anonymous.get("/api/devices").status_code == 401


def test_health_is_always_reachable(anonymous):
    """The container healthcheck has no cookie, and must not need one."""
    assert anonymous.get("/api/health").status_code == 200


def test_an_empty_password_is_refused_before_it_reaches_the_comparison(anonymous):
    assert anonymous.post("/api/auth/login", json={"password": ""}).status_code == 422


# -- The session token --------------------------------------------------------


def test_a_forged_cookie_is_refused(anonymous):
    anonymous.cookies.set(auth.COOKIE_NAME, "not-a-token")
    assert anonymous.get("/api/devices").status_code == 401


def test_a_token_signed_with_the_credential_key_is_refused():
    """The whole point of deriving: a value encrypted with the key that
    protects the stored secrets is not a session."""
    forged = _fernet().encrypt(b"awtrixng-mgr").decode()
    assert auth.is_valid_session(forged) is False


def test_a_token_from_another_purpose_is_refused():
    forged = derived_fernet("backup").encrypt(b"awtrixng-mgr").decode()
    assert auth.is_valid_session(forged) is False


def test_a_session_expires(monkeypatch):
    token = auth.issue_session()
    assert auth.is_valid_session(token) is True
    # Fernet stamps its own timestamp, so age is judged by the primitive; move
    # the clock past the TTL rather than trusting our own bookkeeping.
    monkeypatch.setattr(auth, "SESSION_SECONDS", 1)
    # Captured before patching, or the replacement calls itself.
    now = time.time
    monkeypatch.setattr(time, "time", lambda: now() + 10)
    assert auth.is_valid_session(token) is False


def test_no_cookie_at_all_is_refused():
    assert auth.is_valid_session(None) is False
    assert auth.is_valid_session("") is False


# -- The cookie itself --------------------------------------------------------


def test_the_cookie_is_not_readable_by_scripts(anonymous):
    response = anonymous.post("/api/auth/login", json={"password": PASSWORD})
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    # No TLS in development, so no Secure flag: the browser would drop the
    # cookie and no one could sign in.
    assert "Secure" not in header


def test_behind_tls_the_cookie_is_marked_secure(client, secured, monkeypatch):
    monkeypatch.setenv("AWTRIXNG_SECURE_COOKIE", "true")
    get_settings.cache_clear()
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert "Secure" in response.headers["set-cookie"]


# -- The whole surface --------------------------------------------------------


def every_route(router) -> list:
    """Every endpoint declared anywhere in the application.

    Walked rather than listed: FastAPI nests the routers it includes instead
    of flattening them, so a walk that stopped at the first level would
    quietly check four routes and pass.
    """
    found = []
    for route in getattr(router, "routes", []):
        if getattr(route, "methods", None) and hasattr(route, "path"):
            found.append(route)
        found.extend(every_route(route))
    # Included routers keep their own table, and their paths there are missing
    # the prefix — which is why the requests below come from the schema.
    nested = getattr(router, "original_router", None)
    if nested is not None:
        found.extend(every_route(nested))
    return found


def our_routes(app) -> list:
    """The routes awtrixng-mgr declares, as opposed to the documentation pages
    FastAPI mounts on its own."""
    return [
        route
        for included in getattr(app, "routes", [])
        if getattr(included, "original_router", None) is not None
        for route in every_route(included.original_router)
    ]


def builtin_paths(app) -> list[str]:
    """FastAPI's own pages — /redoc and friends. They carry resolved paths and
    are excluded from the schema by construction, so they are listed here
    instead."""
    from starlette.routing import Route

    return [route.path for route in app.routes if isinstance(route, Route)]


def test_none_of_our_routes_escapes_the_schema(anonymous):
    """The inventory below is read from the OpenAPI schema, because that is
    where paths appear with their prefix. That only proves something if none
    of our routes hides from the schema — so none may."""
    hidden = [
        route.path
        for route in our_routes(anonymous.app)
        if getattr(route, "include_in_schema", True) is False
    ]
    assert hidden == [], f"hidden from the schema, so untested: {hidden}"


def test_the_built_in_documentation_pages_refuse_too(anonymous):
    """/redoc exists whether or not anyone remembers it does."""
    paths = builtin_paths(anonymous.app)
    assert "/redoc" in paths, "FastAPI stopped mounting /redoc; drop this test"
    for path in paths:
        assert anonymous.get(path).status_code == 401, f"{path} answered anonymously"


def test_every_route_refuses_an_anonymous_caller(anonymous):
    """Walks the whole surface rather than trusting a spot check.

    Deny-by-default is only worth something if it is checked against the real
    route table: a router added later is covered the day it is mounted,
    without anyone remembering to extend a list here.
    """
    schema = anonymous.app.openapi()

    checked = 0
    for path, operations in schema["paths"].items():
        if path in OPEN_PATHS:
            continue
        for method in operations:
            if method.upper() in {"HEAD", "OPTIONS"}:
                continue
            # Path parameters are irrelevant: the refusal happens before any
            # handler runs, so any value forming a valid URL will do.
            url = re.sub(r"\{[^}]+\}", "1", path)
            response = anonymous.request(method.upper(), url)
            assert response.status_code == 401, f"{method.upper()} {path} answered anonymously"
            assert response.json()["code"] == "auth.required"
            checked += 1

    # A guard against the walk silently matching nothing — it already caught
    # one version of this test that only ever reached four routes.
    assert checked > 30, f"only {checked} operations were exercised"
    assert checked == sum(
        len([m for m in ops if m.upper() not in {"HEAD", "OPTIONS"}])
        for path, ops in schema["paths"].items()
        if path not in OPEN_PATHS
    )


def test_the_open_paths_are_the_ones_we_meant(anonymous):
    """OPEN_PATHS is a security boundary; it is spelled out here so that
    widening it has to be a deliberate edit in two places."""
    assert OPEN_PATHS == {
        "/api/health",
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/logout",
    }
    for path in OPEN_PATHS:
        assert anonymous.get(path).status_code != 401
