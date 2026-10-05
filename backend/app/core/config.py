"""Application settings, read from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AWTRIXNG_", extra="ignore")

    #: Persistent directory: SQLite database and encryption key.
    data_dir: Path = Path("/data")
    log_level: str = "INFO"

    #: Fernet key for credentials. Generated in data_dir when absent.
    secret_key: str | None = None

    #: Outbound HTTP guardrails.
    http_connect_timeout: float = 5.0
    http_read_timeout: float = 10.0
    http_max_response_bytes: int = 2 * 1024 * 1024

    #: Smallest refresh interval a widget may be given.
    min_refresh_seconds: int = 5

    #: Language of the words pushed to the displays — weather conditions, moon
    #: phases. Not the interface language, which each browser chooses for
    #: itself. "en" or "fr"; anything else falls back to English.
    language: str = "en"

    #: Read-only token for a dashboard. Empty means no token works.
    api_token: str = ""

    #: Local password. Empty means no authentication at all.
    password: str = ""

    #: Whether the session cookie carries the Secure flag. True whenever the
    #: browser reaches the app over HTTPS. False in development, where Vite
    #: serves over plain HTTP.
    secure_cookie: bool = False

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'awtrixng.db'}"

    @property
    def secret_key_file(self) -> Path:
        return self.data_dir / "secret.key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
