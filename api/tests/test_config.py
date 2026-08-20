"""Unit tests for app.config."""

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_reads_database_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://u:p@h:5432/d"


def test_missing_required_var_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing DATABASE_URL must raise at construction, not at first query."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    assert "database_url" in str(excinfo.value)


def test_demo_mode_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing reads this until 037, but the safe default matters now."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    assert Settings(_env_file=None).demo_mode is False


def test_demo_mode_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert Settings(_env_file=None).demo_mode is True


def test_sentry_disabled_when_dsn_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert Settings(_env_file=None).sentry_dsn is None


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


def test_a_deployed_app_refuses_the_default_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A known signing key lets anyone mint a cookie for any user id.

    Nothing about the running app would look wrong, which is exactly why this is a
    failed boot rather than a warning in a log nobody reads.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        with TestClient(app):
            pass

    get_settings.cache_clear()


def test_a_deployed_app_starts_once_the_secret_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    monkeypatch.setenv("SESSION_SECRET", "a-real-secret-from-fly")
    # Access is the authentication as of 047a, and a deployment without it does not
    # boot — so "the secret is set" is no longer sufficient on its own.
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "allofmymoney.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud-123")
    get_settings.cache_clear()

    with TestClient(app):
        pass

    get_settings.cache_clear()


def test_a_deployment_without_access_refuses_to_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing would authenticate it, so it must not accept a first request.

    `deps.current_user` refuses every request in this state, which is correct and one
    request too late to be reassuring. An operator should learn about it from a failed
    release rather than from a support conversation.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("WEB_ORIGIN", "https://allofmymoney.com")
    monkeypatch.setenv("SESSION_SECRET", "a-real-secret-from-fly")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="Cloudflare Access is not configured"):
        with TestClient(app):
            pass

    get_settings.cache_clear()


def test_the_demo_is_the_deliberate_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """The demo is public by design and has no Access in front of it.

    It boots without one. Asserted rather than assumed, because this is the single
    branch that lets a deployment run unauthenticated and it must not be reachable by
    accident — `DEMO_MODE` is false by default and set on exactly one deployment.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("WEB_ORIGIN", "https://demo.allofmymoney.com")
    monkeypatch.setenv("SESSION_SECRET", "a-real-secret-from-fly")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
    get_settings.cache_clear()

    with TestClient(app):
        pass

    get_settings.cache_clear()


def test_local_development_is_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """http://localhost is not a deployment, and a clean clone must just run."""
    monkeypatch.setenv("WEB_ORIGIN", "http://localhost:3000")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.session_secret_is_default is True
    assert settings.cookie_secure is False

    get_settings.cache_clear()
