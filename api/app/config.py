"""Application settings, read from the environment.

Required values have no default: a missing ``DATABASE_URL`` raises at startup rather
than surfacing later as a confusing connection error.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the API service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required. No default on purpose — see module docstring.
    database_url: str

    # Rejects mutating verbs on the public demo deployment. Nothing reads this until
    # ticket 037; it is defined now so the demo deployment is a configuration change
    # rather than a code change. Defense in depth only — the real boundary is that
    # the demo's credentials cannot reach the real database.
    demo_mode: bool = False

    # Observability (ticket 007). Sentry stays disabled while the DSN is unset.
    sentry_dsn: str | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, constructed once.

    Cached so importing modules don't each re-read and re-validate the environment.
    Tests that need different values call ``get_settings.cache_clear()``.
    """
    return Settings()
