"""CRUD operations for events and knowledge objects (Backboard layer)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event, KnowledgeObject, VerificationCheck


async def store_event(db: AsyncSession, event_data: dict) -> Event:
    """Store an event, returning existing if duplicate (same source+source_id)."""
    result = await db.execute(
        select(Event).where(
            Event.source == event_data["source"],
            Event.source_id == event_data["source_id"],
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    event = Event(
        source=event_data["source"],
        source_id=event_data["source_id"],
        event_type=event_data["event_type"],
        actor_email=event_data.get("actor_email"),
        actor_name=event_data.get("actor_name"),
        content=event_data.get("content"),
        metadata_=event_data.get("metadata"),
        raw_payload=event_data.get("raw_payload"),
        occurred_at=event_data["occurred_at"],
        project_id=event_data.get("project_id"),
    )
    db.add(event)
    await db.flush()
    return event


async def store_knowledge_object(db: AsyncSession, ko_data: dict) -> KnowledgeObject:
    """Create a new Knowledge Object."""
    ko = KnowledgeObject(
        type=ko_data["type"],
        title=ko_data["title"],
        summary=ko_data.get("summary"),
        detail=ko_data.get("detail"),
        participants=ko_data.get("participants"),
        tags=ko_data.get("tags"),
        confidence=ko_data.get("confidence", 0.0),
        status=ko_data.get("status", "active"),
        occurred_at=ko_data.get("occurred_at"),
        project_id=ko_data.get("project_id"),
    )
    db.add(ko)
    await db.flush()
    return ko


async def get_knowledge_object(db: AsyncSession, ko_id: str) -> KnowledgeObject | None:
    """Fetch a Knowledge Object by ID."""
    result = await db.execute(select(KnowledgeObject).where(KnowledgeObject.id == ko_id))
    return result.scalar_one_or_none()


async def get_recent_knowledge(
    db: AsyncSession,
    project_id: str | None,
    since: str,
    exclude_id: str | None = None,
) -> list[KnowledgeObject]:
    """Get recent knowledge objects for correlation."""
    query = select(KnowledgeObject).where(
        KnowledgeObject.occurred_at >= since,
        KnowledgeObject.status == "active",
    )
    if project_id:
        query = query.where(KnowledgeObject.project_id == project_id)
    if exclude_id:
        query = query.where(KnowledgeObject.id != exclude_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def store_verification_check(
    db: AsyncSession, knowledge_id: str, **kwargs
) -> VerificationCheck:
    """Store a verification check result."""
    check = VerificationCheck(
        knowledge_id=knowledge_id,
        description=kwargs["description"],
        status=kwargs["status"],
        evidence=kwargs.get("evidence"),
        suggestion=kwargs.get("suggestion"),
        event_id=kwargs.get("event_id"),
    )
    db.add(check)
    await db.flush()
    return check
