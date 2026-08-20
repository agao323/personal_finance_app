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

    # The household's first user, seeded by the initial migration. The `users` table
    # is also the auth allowlist (ticket 034), so this is the one place an identity
    # is declared — there is no second list that could disagree with it.
    owner_email: str = "owner@example.invalid"
    owner_display_name: str = "Owner"

    # Rejects mutating verbs on the public demo deployment. Nothing reads this until
    # ticket 037; it is defined now so the demo deployment is a configuration change
    # rather than a code change. Defense in depth only — the real boundary is that
    # the demo's credentials cannot reach the real database.
    demo_mode: bool = False

    # WebAuthn (ticket 034).
    #
    # `rp_id` must be the **registrable parent domain**, not the app's hostname: a
    # passkey scoped to `app.example.com` stops working the moment anything moves to
    # the apex, and the failure only shows up in production. `localhost` in dev, which
    # browsers special-case as a secure origin.
    #
    # `web_origin` is what the browser reports as the origin of the ceremony, and it
    # includes the scheme and port. It is validated separately from `rp_id` because
    # they answer different questions: which domain owns the credential, and which
    # page asked for it.
    rp_id: str = "localhost"
    rp_name: str = "Personal finance"
    web_origin: str = "http://localhost:3000"
    session_ttl_hours: int = 24 * 14
    # Signs the session cookie. Overridden in every deployed environment; the default
    # exists so a clean clone runs, and `Settings.session_secret_is_default` is what
    # stops it reaching production unnoticed.
    session_secret: str = "dev-only-not-a-secret"

    @property
    def session_secret_is_default(self) -> bool:
        return self.session_secret == "dev-only-not-a-secret"

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies everywhere but plain-HTTP local dev.

        Derived from the origin rather than configured separately: two settings that
        must agree are one setting and a bug waiting to happen.
        """
        return self.web_origin.startswith("https://")

    # Cloudflare Access (ticket 044). Only the account-recovery route reads these —
    # everything else is authenticated by a session, and Access is enforced at the
    # edge and again at the web origin. Both must be set or recovery is refused: an
    # audience with no issuer accepts a token from any Access tenant, and an issuer
    # with no audience accepts one minted for a different application.
    cf_access_team_domain: str | None = None
    cf_access_aud: str | None = None

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
