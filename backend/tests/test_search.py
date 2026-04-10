"""Phase 6 tests: Search and context formatting.

Tests:
- Vector search returns relevant results
- Search respects project scope
- Context formatting for KOs
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import KnowledgeObject
from app.backboard.store import search_knowledge_objects, store_knowledge_object
from app.backboard.tools import search_knowledge_base


@pytest.mark.asyncio
async def test_vector_search_returns_relevant(db_session: AsyncSession):
    """Query about motors → motor decision."""
    await store_knowledge_object(db_session, {
        "type": "decision",
        "title": "Switch primary motor supplier to MotorCo",
        "summary": "Team decided to switch from SupplierA to MotorCo.",
        "confidence": 0.85,
        "tags": ["motors", "supply-chain"],
    })
    await db_session.flush()

    results = await search_knowledge_base(db_session, query="motor supplier")
    assert len(results) >= 1
    assert any("motor" in r["title"].lower() for r in results)


@pytest.mark.asyncio
async def test_vector_search_respects_project(db_session: AsyncSession):
    """Only returns results from the same project."""
    await store_knowledge_object(db_session, {
        "type": "decision",
        "title": "Use React for Project Alpha",
        "summary": "Frontend framework choice.",
        "confidence": 0.8,
        "project_id": "proj_alpha",
    })
    await store_knowledge_object(db_session, {
        "type": "decision",
        "title": "Use Vue for Project Beta",
        "summary": "Frontend framework choice.",
        "confidence": 0.8,
        "project_id": "proj_beta",
    })
    await db_session.flush()

    results = await search_knowledge_base(db_session, query="frontend framework", project_id="proj_alpha")
    titles = [r["title"] for r in results]
    assert any("Alpha" in t for t in titles)
    assert not any("Beta" in t for t in titles)


@pytest.mark.asyncio
async def test_context_formatting(db_session: AsyncSession):
    """KOs formatted into clean context dicts."""
    await store_knowledge_object(db_session, {
        "type": "approval",
        "title": "Approved thermal design v2",
        "summary": "Thermal design approved by the review board.",
        "confidence": 0.92,
        "tags": ["thermal"],
    })
    await db_session.flush()

    results = await search_knowledge_base(db_session, query="thermal design")
    assert len(results) >= 1
    result = next(r for r in results if "thermal" in r["title"].lower())
    assert "id" in result
    assert "type" in result
    assert "title" in result
    assert "summary" in result
    assert result["type"] == "approval"


@pytest.mark.asyncio
async def test_change_filter_maps_to_decision(db_session: AsyncSession):
    """Legacy 'change' filters should still return canonical decision records."""
    await store_knowledge_object(db_session, {
        "type": "change",
        "title": "Move database to Supabase",
        "summary": "Replaced the old database stack with Supabase.",
        "confidence": 0.9,
        "tags": ["database", "supabase"],
    })
    await db_session.flush()

    results = await search_knowledge_objects(
        db_session,
        query="supabase database",
        type_filter="change",
        limit=5,
    )

    assert len(results) == 1
    assert results[0]["type"] == "decision"
