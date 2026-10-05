"""Optional local authentication.

Off unless ``AWTRIXNG_PASSWORD`` is set, so an installation that was open
stays open until its owner decides otherwise (§19).

Deliberate choices, since this is security code:

- **One password, no user list.** A personal appliance has one owner. A user
  table would be more code and more to get wrong for no gain.
- **The password is compared, not hashed.** It sits in clear in the process
  environment either way, so hashing it in memory would protect nothing. The
  comparison is constant-time, which does matter.
- **The session is a Fernet token in a cookie.** Fernet is authenticated
  encryption with a built-in timestamp, so expiry is enforced by the primitive
  rather than by code of mine. It is signed with a key *derived* from the main
  one: one key, one job.
- **A failed attempt costs a second.** Enough to make guessing over a network
  pointless, little enough not to annoy a typo.
"""

import asyncio
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.crypto import derived_fernet

log = logging.getLogger(__name__)

COOKIE_NAME = "awtrixhub_session"

#: How long a session lasts. Long enough not to log in every day, short enough
#: that a forgotten browser does not stay open forever.
SESSION_SECONDS = 30 * 24 * 3600

#: Delay added to a failed attempt.
FAILED_ATTEMPT_DELAY = 1.0

_SESSION_PAYLOAD = b"awtrixng-mgr"


def is_required() -> bool:
    return bool(get_settings().password)


def _session() -> Fernet:
    return derived_fernet("session")


async def check_password(candidate: str) -> bool:
    """Constant-time comparison, with a delay on failure."""
    expected = get_settings().password or ""
    ok = hmac.compare_digest(candidate.encode(), expected.encode())
    if not ok:
        log.warning("failed login attempt")
        await asyncio.sleep(FAILED_ATTEMPT_DELAY)
    return ok


def reads_summary(authorization: str | None) -> bool:
    """Whether a bearer token may read the dashboard summary.

    A second key, far weaker than the password and deliberately so: it is meant
    to sit in a dashboard's configuration file, so it opens one read-only route
    and nothing else. Compared in constant time like the password, and an empty
    setting means no token is accepted at all.
    """
    expected = get_settings().api_token
    if not expected or not authorization:
        return False
    scheme, _, candidate = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(candidate.strip().encode(), expected.encode())


def issue_session() -> str:
    return _session().encrypt(_SESSION_PAYLOAD).decode()


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        return _session().decrypt(token.encode(), ttl=SESSION_SECONDS) == _SESSION_PAYLOAD
    except (InvalidToken, ValueError, TypeError):
        return False
