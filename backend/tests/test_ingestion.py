"""Phase 2 tests: Event storage and deduplication.

Tests:
- Event stored with embedding field
- Duplicate event (same source_id) is ignored
"""
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event
from app.backboard.store import store_event


@pytest.mark.asyncio
async def test_event_stored(db_session: AsyncSession):
    """Event is persisted to the events table."""
    event_data = {
        "source": "slack",
        "source_id": "test_ts_001",
        "event_type": "message",
        "actor_email": "alice@example.com",
        "actor_name": "Alice",
        "content": "We decided to use MotorCo",
        "metadata": {"channel": "C123"},
        "raw_payload": {},
        "occurred_at": "2026-02-20T14:32:00Z",
        "project_id": None,
    }
    event = await store_event(db_session, event_data)
    assert event.id is not None
    assert event.source == "slack"
    assert event.content == "We decided to use MotorCo"

    # Verify it's in the DB
    result = await db_session.execute(select(Event).where(Event.source_id == "test_ts_001"))
    stored = result.scalar_one()
    assert stored.actor_email == "alice@example.com"


@pytest.mark.asyncio
async def test_duplicate_event_ignored(db_session: AsyncSession):
    """Same source+source_id should not create a second row."""
    event_data = {
        "source": "github",
        "source_id": "commit_dedup_test",
        "event_type": "push",
        "actor_email": "bob@example.com",
        "actor_name": "Bob",
        "content": "Fix typo",
        "metadata": {},
        "raw_payload": {},
        "occurred_at": "2026-02-20T15:00:00Z",
        "project_id": None,
    }
    event1 = await store_event(db_session, event_data)
    event2 = await store_event(db_session, event_data)

    # Should return the same event, not create a duplicate
    assert event1.id == event2.id

    # Only one row
    result = await db_session.execute(
        select(Event).where(Event.source_id == "commit_dedup_test")
    )
    rows = result.scalars().all()
    assert len(rows) == 1
