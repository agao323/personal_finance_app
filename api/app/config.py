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

    # Where the browser reaches this household's app. The app itself never serves the
    # browser — that is the Next.js origin's job — so this is not a URL anything here
    # requests. It is read only as the signal for `is_deployment` below, which is why
    # it survived ticket 047b when the WebAuthn settings beside it did not.
    web_origin: str = "http://localhost:3000"

    @property
    def is_deployment(self) -> bool:
        """True anywhere this is served over https — i.e. not a developer's laptop.

        Derived from the origin rather than configured separately: two settings that
        must agree are one setting and a bug waiting to happen. Ticket 034 already
        used this signal to refuse booting on the default session secret; ticket 047a
        reuses the same one rather than introducing a second notion of "production"
        that could disagree with the first.
        """
        return self.web_origin.startswith("https://")

    # Cloudflare Access (ticket 044; promoted by 047a). **This is the authentication.**
    # `current_user` resolves the email Access verified to a row in `users`; there is no
    # application credential behind it any more. See docs/adr/0007-drop-passkeys.md.
    #
    # Both must be set or the check is disabled: an audience with no issuer accepts a
    # token from any Access tenant, and an issuer with no audience accepts one minted
    # for a different application. Either alone is worse than nothing, because it looks
    # like a check. Disabled means **refused**, never "allowed without checking" — and
    # `main.lifespan` will not let a deployment boot in that state at all.
    cf_access_team_domain: str | None = None
    cf_access_aud: str | None = None

    # Who you are on a laptop, where there is no Access in front to say (ticket 047a).
    #
    # Inert unless Access is unconfigured *and* `is_deployment` is false, so setting it
    # on a deployed environment does nothing — the value cannot become a way in. It is
    # also how the test suite authenticates, which is deliberate: the mechanism that
    # runs in development is the one the tests exercise, rather than a fixture-only
    # path that could drift from it.
    dev_identity_email: str | None = None

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
