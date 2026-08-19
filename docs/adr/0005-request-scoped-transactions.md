# ADR 0005 — The request is the transaction boundary

Status: accepted · 2026-08-18 · Backfilled by ticket 039

## Context

Every write endpoint answered `200` and persisted nothing.

`get_session` yielded a SQLAlchemy session and closed it. Endpoints called
`session.flush()` — to get generated ids, and so later statements in the same request
could see earlier ones — and nothing ever committed. Only `routers/rules.py` called
`session.commit()` explicitly, which is why the rules screen would have been the one
part of the app that worked.

This shipped across tickets 019, 020/021 and 023: creating accounts, recording balances,
adding stakes, committing a CSV import, and categorising a transaction. All of them had
green functional tests.

**The suite structurally could not see it.** `tests/conftest.py` overrides `get_session`
with a session joined to an outer transaction that is rolled back after each test. Within
a test, a flush is indistinguishable from a commit: later statements on the same session
see the data, assertions pass, and the rollback at the end is expected either way. Every
one of those endpoints' tests passed against a write that never landed.

It was found by clicking the category picker in a browser and reading the row back.

## Decision

`get_session` commits when the handler returns and rolls back when it raises:

```python
with get_sessionmaker()() as session:
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
```

Endpoints flush; the dependency commits, once. The explicit commits in `rules.py` were
removed — two ways of ending a transaction is how the next person gets it wrong.

`except Exception` deliberately includes `HTTPException`, so a handler that raises a 404
partway through a multi-step write leaves nothing behind.

## Alternatives considered

**Commit in each endpoint.** What `rules.py` was already doing. Rejected: it is a line
every future endpoint must remember, the failure is silent, and this incident is the
proof — six endpoints across three tickets forgot it, and nothing caught them.

**`autocommit`/`autoflush` at the sessionmaker.** Commits per statement rather than per
request, so a handler that writes two rows and fails between them leaves the first. The
whole point of a request-scoped transaction is that it does not.

**Change the test fixture to commit for real, and truncate between tests.** Would have
caught this, but it makes every test slower and each one responsible for its own cleanup.
Rejected in favour of keeping the fast rolled-back fixture and testing the dependency
itself directly — which is what `tests/test_db.py` does, using the real `get_session` and
verifying persistence from a *second* session.

## Consequences

**A whole class of bug is now impossible** rather than merely unlikely: no endpoint can
forget to commit, because no endpoint commits.

**The rolled-back test fixture stays**, and so does its blind spot. It cannot see commit
behaviour, by construction. `tests/test_db.py` is the only place that can, and the
integration tests in `tests/test_integration.py` cover the same ground from the outside
by reading a written value back through a separate request.

**The lesson generalises.** A fixture that makes tests fast by removing a production
behaviour will hide bugs in exactly that behaviour. It is worth writing down which
behaviour each such fixture removes, and testing that behaviour somewhere else on
purpose.
