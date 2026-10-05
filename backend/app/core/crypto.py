"""Encryption of the credentials stored in the database (ADR-005).

This is not a defence against root access to the volume: it is a defence
against leaking through a backup, a copy of the .db file, or someone opening it
in a SQLite client.
"""

import base64
import hashlib
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def key_bytes() -> bytes:
    """The raw Fernet key. Other purposes derive from it rather than reuse it."""
    settings = get_settings()

    if settings.secret_key:
        return settings.secret_key.encode()

    path = settings.secret_key_file
    if path.exists():
        return path.read_bytes().strip()

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    # Created 0600 straight away, with no window where it is world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    log.info("generated new encryption key at %s", path)
    return key


@lru_cache
def _fernet() -> Fernet:
    return Fernet(key_bytes())


@lru_cache
def derived_fernet(purpose: str) -> Fernet:
    """A key for another purpose, derived from the main one.

    Sessions must not be signed with the very key that encrypts credentials:
    one key, one job. Deriving keeps a single secret on disk while giving each
    use its own key.
    """
    material = hashlib.sha256(f"awtrixng-mgr:{purpose}:".encode() + key_bytes()).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Rotated key, or a database from another deployment: never bring the
        # application down, the connector will simply go into error.
        log.error("could not decrypt a stored secret (wrong or rotated key)")
        raise


def preview(value: str) -> str:
    """Masked preview returned by the API. A secret never leaves in clear."""
    tail = value[-4:] if len(value) >= 8 else ""
    return "••••" + tail
