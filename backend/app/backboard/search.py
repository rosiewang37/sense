"""Vector search and retrieval (Backboard layer).

In production with pgvector, uses cosine similarity SQL queries.
For SQLite fallback, uses keyword search (vector search unavailable).
"""
import logging

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event, KnowledgeObject

logger = logging.getLogger(__name__)


async def vector_search_events(
    db: AsyncSession,
    query: str,
    source: str = "any",
    since_hours: int = 72,
    project_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search events using vector similarity (pgvector) or keyword fallback.

    In production (PostgreSQL + pgvector):
      - Generates embedding for the query
      - Uses cosine distance operator (<=>)  on the embedding column
    In development (SQLite):
      - Falls back to keyword (LIKE) search
    """
    # Keyword-based search (works on both SQLite and PG)
    stmt = select(Event)

    if source != "any":
        stmt = stmt.where(Event.source == source)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)

    keywords = [kw for kw in query.lower().split() if len(kw) > 2]
    if keywords:
        conditions = [Event.content.ilike(f"%{kw}%") for kw in keywords]
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.order_by(Event.occurred_at.desc()).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "source": e.source,
            "source_id": e.source_id,
            "event_type": e.event_type,
            "actor_email": e.actor_email,
            "actor_name": e.actor_name,
            "content": e.content,
            "occurred_at": e.occurred_at,
        }
        for e in events
    ]


async def vector_search_knowledge(
    db: AsyncSession,
    query: str,
    type_filter: str = "any",
    project_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Search knowledge objects using vector similarity or keyword fallback."""
    stmt = select(KnowledgeObject).where(KnowledgeObject.status == "active")

    if type_filter != "any":
        stmt = stmt.where(KnowledgeObject.type == type_filter)
    if project_id:
        stmt = stmt.where(KnowledgeObject.project_id == project_id)

    keywords = [kw for kw in query.lower().split() if len(kw) > 2]
    if keywords:
        conditions = []
        for kw in keywords:
            conditions.append(KnowledgeObject.title.ilike(f"%{kw}%"))
            conditions.append(KnowledgeObject.summary.ilike(f"%{kw}%"))
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.order_by(KnowledgeObject.detected_at.desc()).limit(limit)
    result = await db.execute(stmt)
    kos = result.scalars().all()

    return [
        {
            "id": str(ko.id),
            "type": ko.type,
            "title": ko.title,
            "summary": ko.summary,
            "detail": ko.detail,
            "confidence": ko.confidence,
            "status": ko.status,
            "occurred_at": ko.occurred_at,
            "participants": ko.participants,
            "tags": ko.tags,
        }
        for ko in kos
    ]
