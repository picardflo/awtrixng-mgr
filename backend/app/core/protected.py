"""Displays this installation must never write to.

**Why this is in code and not in a note.** On the previous project, a second
instance pointed at a display in service deleted its apps — twice. The second
time happened *after* the risk had been written down in an architecture
decision record. A warning someone has to remember is not a guardrail.

So the rule executes. Both the device tests and the CLI ask here before they
touch anything, and the answer is a refusal before a single request leaves the
machine.

**The list is empty by default**, and that is the right default for anyone
but its author: a name that means something here means nothing on your
network, and a guard full of someone else's hostnames protects nobody while
looking like it protects something.

Fill it with yours. One per display you want these tools to refuse, comma
separated, as names or addresses:

    AWTRIXNG_PROTECTED_HOSTS=awtrix-lounge,awtrix-lounge.lan,192.168.1.40

It is worth doing the day you own two. The one you experiment on and the one
the household looks at are the same model, answer the same API, and differ by
one character in a hostname.
"""

import os

#: Empty: see above. The guard is opt-in because its content is personal.
DEFAULT_PROTECTED = ""


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
