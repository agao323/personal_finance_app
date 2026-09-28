"""The advisor's tables: what cascades, what survives, what is refused, what is exported.

The migration's round trip is covered by `test_schema.test_upgrade_downgrade_upgrade_is_clean`,
which walks every revision including 0007.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Numeric, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models.advisor import (
    AdvisorConversation,
    AdvisorMessage,
    AdvisorToolCall,
    AdvisorTurn,
    AdvisorUsage,
)

ADVISOR_TABLES = {
    "advisor_conversations",
    "advisor_turns",
    "advisor_messages",
    "advisor_tool_calls",
    "advisor_usage",
}
NOW = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def conversation(db_session: Session, owner_id: int) -> AdvisorConversation:
    conv = AdvisorConversation(
        user_id=owner_id,
        view="household",
        title_text="What's our net worth?",
        expires_at=NOW + dt.timedelta(days=30),
    )
    db_session.add(conv)
    db_session.flush()
    turn = AdvisorTurn(conversation_id=conv.id, seq=1, status="complete", grounding="verified")
    db_session.add(turn)
    db_session.flush()
    db_session.add_all(
        [
            AdvisorMessage(
                turn_id=turn.id, seq=1, role="user", content=[{"type": "text", "text": "q"}]
            ),
            AdvisorMessage(
                turn_id=turn.id, seq=2, role="assistant", content=[{"type": "text", "text": "a"}]
            ),
            AdvisorToolCall(
                conversation_id=conv.id,
                turn_id=turn.id,
                tool_name="networth_get",
                tool_call_id="c1",
                args={"view": "household"},
                status="ok",
                latency_ms=12,
                row_count=0,
                result_bytes=400,
                withheld_count=0,
            ),
            AdvisorUsage(
                turn_id=turn.id,
                provider="scripted",
                model="scripted",
                input_tokens=1000,
                output_tokens=200,
                latency_ms=50,
            ),
        ]
    )
    db_session.flush()
    return conv


def test_no_money_column_in_any_advisor_table() -> None:
    """Cost is derived from token counts; a 2dp column would round a call's cost to zero."""
    for name in ADVISOR_TABLES:
        for column in Base.metadata.tables[name].columns:
            assert not isinstance(column.type, Numeric), f"{name}.{column.name}"


def test_deleting_a_conversation_keeps_the_audit_trail(
    db_session: Session, conversation: AdvisorConversation
) -> None:
    conv_id = conversation.id
    db_session.delete(conversation)
    db_session.flush()
    db_session.expire_all()

    assert db_session.execute(select(func.count()).select_from(AdvisorTurn)).scalar_one() == 0
    assert db_session.execute(select(func.count()).select_from(AdvisorMessage)).scalar_one() == 0
    call = db_session.execute(select(AdvisorToolCall)).scalar_one()
    assert (call.conversation_id, call.turn_id) == (None, None)
    assert call.args == {"view": "household"}
    usage = db_session.execute(select(AdvisorUsage)).scalar_one()
    assert usage.turn_id is None
    assert db_session.get(AdvisorConversation, conv_id) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "exploded"), ("grounding", "maybe"), ("feedback", "meh")],
)
def test_value_sets_are_enforced(
    db_session: Session, conversation: AdvisorConversation, field: str, value: str
) -> None:
    turn = AdvisorTurn(conversation_id=conversation.id, seq=2, status="complete", grounding="none")
    setattr(turn, field, value)
    db_session.add(turn)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_turn_number_is_unique_in_its_conversation(
    db_session: Session, conversation: AdvisorConversation
) -> None:
    db_session.add(
        AdvisorTurn(conversation_id=conversation.id, seq=1, status="complete", grounding="none")
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_export_carries_the_advisor(
    client: TestClient, conversation: AdvisorConversation
) -> None:
    body = client.get("/export").json()

    assert body["advisor_conversations"][0]["id"] == str(conversation.id)
    assert uuid.UUID(body["advisor_turns"][0]["conversation_id"]) == conversation.id
    assert [m["role"] for m in body["advisor_messages"]] == ["user", "assistant"]
    assert body["advisor_tool_calls"][0]["tool_name"] == "networth_get"
    assert body["advisor_usage"][0]["output_tokens"] == 200
