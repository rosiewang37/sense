"""Agent tool implementations (Backboard layer).

These functions provide the search capabilities used by both the
verification agent and the investigative query agent.
"""
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event, KnowledgeObject, VerificationCheck


async def search_events_by_content(
    db: AsyncSession,
    query: str,
    source: str = "any",
    since_hours: int = 72,
    project_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search events by content (keyword matching; vector search in production)."""
    stmt = select(Event)

    if source != "any":
        stmt = stmt.where(Event.source == source)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)

    # Keyword-based search (vector search requires pgvector in production)
    keywords = query.lower().split()
    if keywords:
        conditions = [Event.content.ilike(f"%{kw}%") for kw in keywords]
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "source": e.source,
            "source_id": e.source_id,
            "event_type": e.event_type,
            "actor_email": e.actor_email,
            "content": e.content,
            "occurred_at": e.occurred_at,
        }
        for e in events
    ]


async def search_events_by_actor(
    db: AsyncSession,
    actor_email: str,
    source: str = "any",
    since_hours: int = 72,
    project_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search events by actor email."""
    stmt = select(Event).where(Event.actor_email == actor_email)

    if source != "any":
        stmt = stmt.where(Event.source == source)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "source": e.source,
            "source_id": e.source_id,
            "event_type": e.event_type,
            "actor_email": e.actor_email,
            "content": e.content,
            "occurred_at": e.occurred_at,
        }
        for e in events
    ]


async def search_knowledge_base(
    db: AsyncSession,
    query: str,
    type_filter: str = "any",
    project_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Search knowledge objects by content (keyword; vector in production)."""
    stmt = select(KnowledgeObject).where(KnowledgeObject.status == "active")

    if type_filter != "any":
        stmt = stmt.where(KnowledgeObject.type == type_filter)
    if project_id:
        stmt = stmt.where(KnowledgeObject.project_id == project_id)

    keywords = query.lower().split()
    if keywords:
        conditions = []
        for kw in keywords:
            conditions.append(KnowledgeObject.title.ilike(f"%{kw}%"))
            conditions.append(KnowledgeObject.summary.ilike(f"%{kw}%"))
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    kos = result.scalars().all()

    return [
        {
            "id": str(ko.id),
            "type": ko.type,
            "title": ko.title,
            "summary": ko.summary,
            "confidence": ko.confidence,
            "status": ko.status,
            "occurred_at": ko.occurred_at,
        }
        for ko in kos
    ]


async def get_knowledge_detail(db: AsyncSession, knowledge_id: str) -> dict | None:
    """Get full details of a knowledge object."""
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == knowledge_id)
    )
    ko = result.scalar_one_or_none()
    if not ko:
        return None

    return {
        "id": str(ko.id),
        "type": ko.type,
        "title": ko.title,
        "summary": ko.summary,
        "detail": ko.detail,
        "participants": ko.participants,
        "tags": ko.tags,
        "confidence": ko.confidence,
        "status": ko.status,
        "occurred_at": ko.occurred_at,
    }


async def get_verification_status(db: AsyncSession, knowledge_id: str) -> list[dict]:
    """Get verification checks for a knowledge object."""
    result = await db.execute(
        select(VerificationCheck).where(VerificationCheck.knowledge_id == knowledge_id)
    )
    checks = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "description": c.description,
            "status": c.status,
            "evidence": c.evidence,
            "suggestion": c.suggestion,
            "checked_at": c.checked_at,
        }
        for c in checks
    ]
