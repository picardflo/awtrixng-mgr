"""Displays this installation must never write to.

**Why this is in code and not in a note.** On the previous project, a second
instance pointed at a display in service deleted its apps — twice. The second
time happened *after* the risk had been written down in an architecture
decision record. A warning someone has to remember is not a guardrail.

So the rule executes. Both the device tests and the CLI ask here before they
touch anything, and the answer is a refusal before a single request leaves the
machine.

The default names the lounge clock, which runs AWTRIX 3 and is the one the
family looks at. Override with `AWTRIXNG_PROTECTED_HOSTS`, comma separated;
set it empty to disable the guard entirely, which is what a published copy of
this project would do.
"""

import os

DEFAULT_PROTECTED = "awtrix-cl1,awtrix-cl1.home.lan"


class ProtectedHostError(Exception):
    """Raised instead of writing to a display that is in service."""


def protected_hosts() -> set[str]:
    raw = os.environ.get("AWTRIXNG_PROTECTED_HOSTS", DEFAULT_PROTECTED)
    return {name.strip().lower() for name in raw.split(",") if name.strip()}


def is_protected(host: str) -> bool:
    return host.strip().lower() in protected_hosts()


def assert_writable(host: str) -> None:
    """Refuse a protected display, before anything reaches the network."""
    if is_protected(host):
        raise ProtectedHostError(
            f"{host} is a display in service: refusing to write to it. "
            f"Set AWTRIXNG_PROTECTED_HOSTS to change this list."
        )
