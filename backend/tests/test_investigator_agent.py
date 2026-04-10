"""Phase 6 tests: Investigative query agent (TDD-critical).

Tests:
- Agent searches knowledge base
- Agent falls back to raw events
- Agent includes verification status
- Agent stops at max 8 iterations
- Agent says unknown when no data found
"""
import pytest

from app.backboard.models import KnowledgeEvent
from app.backboard.store import store_event, store_knowledge_object
from app.sense.agents.investigator import (
    run_query_agent,
    _build_grounded_answer,
    QUERY_AGENT_TOOLS,
    MAX_TOOL_CALLS,
)


@pytest.mark.asyncio
async def test_agent_searches_knowledge_base():
    """First step is always KB search."""
    mock_calls = [
        {"name": "search_knowledge_base", "args": {"query": "motor supplier"}},
    ]
    mock_tool_results = {
        "search_knowledge_base": [
            {"id": "ko1", "title": "Switch to MotorCo", "summary": "Decision to switch.", "type": "decision"}
        ],
    }
    result = await run_query_agent(
        question="Why did we switch motor suppliers?",
        mock_llm_tool_calls=mock_calls,
        mock_tool_results=mock_tool_results,
        mock_final_answer="The team decided to switch to MotorCo for 30% cost savings.",
    )
    assert result["answer"] is not None
    assert "MotorCo" in result["answer"]
    assert len(result["steps"]) >= 1
    assert result["steps"][0]["tool"] == "search_knowledge_base"


@pytest.mark.asyncio
async def test_agent_digs_into_raw_events():
    """Falls back to raw events when KB incomplete."""
    mock_calls = [
        {"name": "search_knowledge_base", "args": {"query": "motor"}},
        {"name": "search_raw_events", "args": {"query": "motor supplier", "source": "slack"}},
    ]
    mock_tool_results = {
        "search_knowledge_base": [],
        "search_raw_events": [
            {"content": "We decided to use MotorCo", "source": "slack"},
        ],
    }
    result = await run_query_agent(
        question="What happened with the motor supplier?",
        mock_llm_tool_calls=mock_calls,
        mock_tool_results=mock_tool_results,
        mock_final_answer="Based on Slack messages, the team chose MotorCo.",
    )
    assert len(result["steps"]) == 2
    assert result["steps"][1]["tool"] == "search_raw_events"


@pytest.mark.asyncio
async def test_agent_includes_verification_status():
    """Reports implementation status in answer."""
    mock_calls = [
        {"name": "search_knowledge_base", "args": {"query": "MotorCo"}},
        {"name": "get_verification_status", "args": {"knowledge_id": "ko1"}},
    ]
    mock_tool_results = {
        "search_knowledge_base": [{"id": "ko1", "title": "Switch to MotorCo"}],
        "get_verification_status": [
            {"description": "BOM updated", "status": "verified"},
            {"description": "Procurement ticket", "status": "missing"},
        ],
    }
    result = await run_query_agent(
        question="Was the MotorCo decision implemented?",
        mock_llm_tool_calls=mock_calls,
        mock_tool_results=mock_tool_results,
        mock_final_answer="Partially implemented. BOM updated, but procurement ticket is missing.",
    )
    assert "missing" in result["answer"].lower() or "partial" in result["answer"].lower()


@pytest.mark.asyncio
async def test_agent_stops_at_max_iterations():
    """Doesn't exceed 8 tool calls."""
    assert MAX_TOOL_CALLS == 8

    many_calls = [
        {"name": "search_knowledge_base", "args": {"query": f"q{i}"}}
        for i in range(12)
    ]
    result = await run_query_agent(
        question="Tell me everything",
        mock_llm_tool_calls=many_calls,
        mock_tool_results={"search_knowledge_base": []},
        mock_final_answer="Here's what I found.",
    )
    assert len(result["steps"]) <= MAX_TOOL_CALLS


@pytest.mark.asyncio
async def test_agent_says_unknown_when_no_data():
    """No relevant data → 'I don't have information'."""
    result = await run_query_agent(
        question="What about the quantum flux capacitor?",
        mock_llm_tool_calls=[
            {"name": "search_knowledge_base", "args": {"query": "quantum flux capacitor"}},
        ],
        mock_tool_results={"search_knowledge_base": []},
        mock_final_answer="I don't have information about a quantum flux capacitor in your project history.",
    )
    assert "don't have" in result["answer"].lower() or "no information" in result["answer"].lower()


@pytest.mark.asyncio
async def test_grounded_answer_uses_rationale_and_sources(db_session, monkeypatch):
    """Direct answers should use KO rationale and return sources separately."""

    class SessionContext:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class SessionFactory:
        def __init__(self, session):
            self._session = session

        def __call__(self):
            return SessionContext(self._session)

    ko = await store_knowledge_object(
        db_session,
        {
            "type": "decision",
            "title": "Move the primary database to Supabase",
            "summary": "The team moved the primary database to Supabase.",
            "detail": {
                "statement": "We moved the primary database to Supabase.",
                "rationale": "it gives us built-in auth and reduces operational overhead",
                "alternatives_considered": ["Keep self-hosted Postgres"],
                "expected_follow_ups": ["Migrate auth flows"],
            },
            "participants": [{"email": "", "name": "Alice", "role": "author"}],
            "tags": ["database", "supabase"],
            "confidence": 0.91,
            "occurred_at": "2026-02-20T15:00:00Z",
            "project_id": None,
        },
    )
    event = await store_event(
        db_session,
        {
            "source": "slack",
            "source_id": "supabase_decision_ts",
            "event_type": "message",
            "actor_email": None,
            "actor_name": "Alice",
            "content": "Final decision: we're moving the primary database to Supabase for built-in auth and less ops overhead.",
            "metadata": {"channel": "C-DB"},
            "raw_payload": {},
            "occurred_at": "2026-02-20T15:00:00Z",
            "project_id": None,
        },
    )
    db_session.add(
        KnowledgeEvent(
            knowledge_id=str(ko.id),
            event_id=str(event.id),
            relevance=1.0,
            relationship_="source_event",
        )
    )
    await db_session.flush()

    monkeypatch.setattr("app.database.get_session_factory", lambda: SessionFactory(db_session))

    result = await _build_grounded_answer(
        question="Why did we change the database to Supabase?",
        project_id=None,
    )

    assert result is not None
    assert "because" in result["answer"].lower()
    assert "built-in auth" in result["answer"].lower()
    assert result["sources"][0]["type"] == "knowledge_object"
    assert any(source["type"] == "event" for source in result["sources"][1:])
