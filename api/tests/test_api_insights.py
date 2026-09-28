"""`GET /insights` against the synthetic seed, through HTTP.

The seed is generated relative to today, so which findings appear depends on the calendar
— a perk is only urgent late in its period. These assert what holds on any day: the shape,
the ranking, and that spend-based findings do not change with the view.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scripts.seed_synthetic import seed

ORDER = {"urgent": 0, "warning": 1, "notice": 2, "info": 3}
SPEND_KINDS = {"spend_spike", "spend_increase", "uncategorised_spend", "recurring_summary"}


def _insights(client: TestClient, view: str) -> dict[str, Any]:
    response = client.get("/insights", params={"view": view})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_insights_over_the_seed(client: TestClient, db_session: Session) -> None:
    seed(db_session)

    mine = _insights(client, "mine")
    household = _insights(client, "household")

    assert mine["view"] == "mine" and household["view"] == "household"
    assert mine["findings"], "the seed is built to exercise findings"
    for body in (mine, household):
        ranks = [ORDER[f["severity"]] for f in body["findings"]]
        assert ranks == sorted(ranks)
        for finding in body["findings"]:
            assert finding["evidence"], finding["id"]
            assert finding["title"] and finding["detail"]

    def spend(body: dict[str, Any]) -> list[dict[str, Any]]:
        return [f for f in body["findings"] if f["kind"] in SPEND_KINDS]

    assert spend(mine) == spend(household)


def test_insights_are_readable_on_the_demo(
    client: TestClient, db_session: Session, monkeypatch: Any
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        assert client.get("/insights").status_code == 200
    finally:
        get_settings.cache_clear()
