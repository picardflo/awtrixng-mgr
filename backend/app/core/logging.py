"""Readable logging, with no secret leaking out.

Three shapes of leak are possible in this project:

- an upstream API key travelling in a **query string**;
- a display credential in an **Authorization header** — NG can be put behind
  `authEnabled`, and the transport then sends Basic auth on every call;
- a credential inside a **JSON fragment** logged while debugging.

Each gets its own rule. Scrubbing happens in the formatter, so it also covers
messages emitted by third-party libraries.
"""

import logging
import re
import sys

#: The whole query string goes, without asking what is in it.
_QUERY = re.compile(r"(\?)([^\s\"']*)")

#: Authorization header: keep the scheme, mask the value. Without this rule,
#: "Authorization: Bearer <token>" would lose only the word "Bearer" and leave
#: the token in clear.
_AUTH_HEADER = re.compile(r"(?i)\b(authorization\s*[:=]\s*)(\w+\s+)?(\S+)")

#: Authentication scheme met outside a header.
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+(?!\*\*\*)(\S+)")

#: Sensitive key followed by its value, bare (token=x) or JSON ("token": "x").
_SECRETISH = re.compile(
    r"(?i)\b(apikey|api_key|token|password|passwd|secret|auth)"
    r"[\"']?\s*[=:]\s*[\"']?([^\s\"'&,}]+)"
)


def scrub(text: str) -> str:
    """Mask anything that looks like a secret. Apply before writing."""
    text = _AUTH_HEADER.sub(lambda m: f"{m.group(1)}{m.group(2) or ''}***", text)
    text = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)} ***", text)
    text = _QUERY.sub(lambda m: m.group(1) + "***", text)
    return _SECRETISH.sub(lambda m: f"{m.group(1)}=***", text)


class ScrubbingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return scrub(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        ScrubbingFormatter(
            fmt="%(asctime)s %(levelname)-5s %(name)-28s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn would otherwise duplicate every line, bypassing the scrubbing.
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).propagate = True
        logging.getLogger(noisy).handlers = []
    logging.getLogger("httpx").setLevel(logging.WARNING)
