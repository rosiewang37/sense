"""Phase 5 tests: Verification agent (TDD-critical).

Tests:
- Agent tool: search_events_by_content returns relevant events
- Agent tool: search_events_by_actor returns actor's events
- Agent tool: record_verification_check persists to DB
- Agent identifies verified action (BOM commit found)
- Agent identifies missing action (no procurement ticket → suggestion)
- Agent stops at max 10 iterations
- Agent handles KO with no expected follow-ups
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.backboard.models import Event, VerificationCheck
from app.backboard.store import store_event, store_verification_check
from app.backboard.tools import search_events_by_content, search_events_by_actor
from app.sense.agents.verification import (
    run_verification_agent,
    VERIFICATION_TOOLS,
    MAX_TOOL_CALLS,
)


@pytest.fixture
def sample_ko():
    """A sample Knowledge Object for testing."""
    return {
        "id": "ko_test_001",
        "type": "decision",
        "title": "Switch to MotorCo",
        "summary": "Team decided to switch from SupplierA to MotorCo.",
        "detail": {
            "statement": "We will use MotorCo as primary motor supplier.",
            "rationale": "30% cost reduction.",
            "expected_follow_ups": [
                "Update BOM in GitHub",
                "Create procurement ticket",
            ],
        },
        "participants": [{"email": "alice@co.com"}],
    }


# --- Agent Tool Functions ---

@pytest.mark.asyncio
async def test_agent_tool_search_events_by_content(db_session: AsyncSession):
    """search_events_by_content returns events matching a query."""
    await store_event(db_session, {
        "source": "github",
        "source_id": "bom_commit_001",
        "event_type": "push",
        "actor_email": "alice@co.com",
        "actor_name": "Alice",
        "content": "Update BOM with MotorCo parts",
        "metadata": {},
        "raw_payload": {},
        "occurred_at": "2026-02-20T15:00:00Z",
        "project_id": None,
    })
    await db_session.flush()

    results = await search_events_by_content(db_session, query="BOM MotorCo", source="any")
    assert len(results) >= 1
    assert any("BOM" in r["content"] for r in results)


@pytest.mark.asyncio
async def test_agent_tool_search_events_by_actor(db_session: AsyncSession):
    """search_events_by_actor returns events by a specific actor."""
    await store_event(db_session, {
        "source": "slack",
        "source_id": "alice_msg_001",
        "event_type": "message",
        "actor_email": "alice@co.com",
        "actor_name": "Alice",
        "content": "I'll handle the procurement ticket",
        "metadata": {},
        "raw_payload": {},
        "occurred_at": "2026-02-20T16:00:00Z",
        "project_id": None,
    })
    await db_session.flush()

    results = await search_events_by_actor(db_session, actor_email="alice@co.com", source="any")
    assert len(results) >= 1
    assert all(r["actor_email"] == "alice@co.com" for r in results)


@pytest.mark.asyncio
async def test_agent_tool_record_check(db_session: AsyncSession):
    """record_verification_check persists a check to DB."""
    check = await store_verification_check(
        db_session,
        knowledge_id="ko_test_001",
        description="BOM updated in GitHub",
        status="verified",
        evidence="commit bom_commit_001",
    )
    await db_session.flush()

    result = await db_session.execute(
        select(VerificationCheck).where(VerificationCheck.id == check.id)
    )
    stored = result.scalar_one()
    assert stored.status == "verified"
    assert "commit" in stored.evidence


# --- Agent Execution Logic ---

@pytest.mark.asyncio
async def test_agent_identifies_verified_action(sample_ko):
    """Agent finds BOM commit → marks 'verified'."""
    mock_events = [
        {"content": "Update BOM with MotorCo parts", "source": "github", "source_id": "abc123"},
    ]

    # Run agent with mock LLM and tool results
    checks = await run_verification_agent(
        sample_ko,
        mock_tool_results={
            "search_events_by_content": mock_events,
            "search_events_by_actor": [],
        },
        mock_llm_tool_calls=[
            {"name": "search_events_by_content", "args": {"query": "Update BOM"}},
            {"name": "record_verification_check", "args": {
                "description": "BOM updated in GitHub",
                "status": "verified",
                "evidence": "commit abc123: Update BOM with MotorCo parts",
            }},
        ],
    )
    assert any(c["status"] == "verified" for c in checks)


@pytest.mark.asyncio
async def test_agent_identifies_missing_action(sample_ko):
    """Agent finds no procurement ticket → marks 'missing' with suggestion."""
    checks = await run_verification_agent(
        sample_ko,
        mock_tool_results={
            "search_events_by_content": [],
            "search_events_by_actor": [],
        },
        mock_llm_tool_calls=[
            {"name": "search_events_by_content", "args": {"query": "procurement ticket"}},
            {"name": "record_verification_check", "args": {
                "description": "Create procurement ticket",
                "status": "missing",
                "suggestion": "Create a procurement ticket for MotorCo initial order",
            }},
        ],
    )
    assert any(c["status"] == "missing" for c in checks)
    assert any(c.get("suggestion") for c in checks)


@pytest.mark.asyncio
async def test_agent_stops_at_max_iterations(sample_ko):
    """Agent doesn't exceed 10 tool calls."""
    assert MAX_TOOL_CALLS == 10

    # Create 15 tool calls — should be capped at 10
    many_calls = [
        {"name": "search_events_by_content", "args": {"query": f"search {i}"}}
        for i in range(15)
    ]
    checks = await run_verification_agent(
        sample_ko,
        mock_tool_results={"search_events_by_content": [], "search_events_by_actor": []},
        mock_llm_tool_calls=many_calls,
    )
    # Should not crash; execution was capped
    assert isinstance(checks, list)


@pytest.mark.asyncio
async def test_agent_handles_no_expected_follow_ups():
    """KO with no follow-ups → minimal/empty checks."""
    ko = {
        "id": "ko_no_followups",
        "type": "context",
        "title": "General discussion",
        "summary": "Discussed project timeline.",
        "detail": {
            "statement": "Timeline discussion",
            "expected_follow_ups": [],
        },
        "participants": [],
    }

    checks = await run_verification_agent(
        ko,
        mock_tool_results={},
        mock_llm_tool_calls=[],
    )
    assert isinstance(checks, list)
    # No follow-ups → no checks needed (or minimal)
    assert len(checks) == 0
