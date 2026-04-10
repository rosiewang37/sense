"""CRUD operations for events and knowledge objects (Backboard layer)."""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event, KnowledgeObject, VerificationCheck
from app.sense.knowledge_types import canonicalize_knowledge_type, equivalent_knowledge_types

_SEARCH_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "did", "do", "for", "from",
    "have", "how", "i", "if", "in", "into", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "that", "the", "their", "them", "there", "to",
    "us", "was", "we", "what", "when", "where", "which", "who", "why", "with",
}


def _normalize_search_tokens(*parts: str | None) -> set[str]:
    """Normalize free text into keyword tokens for lightweight ranking."""
    tokens: set[str] = set()
    for part in parts:
        if not part:
            continue
        for token in _SEARCH_TOKEN_PATTERN.findall(part.lower()):
            if len(token) < 2 or token in _SEARCH_STOPWORDS:
                continue
            tokens.add(token)
    return tokens


def _knowledge_search_parts(ko: KnowledgeObject) -> list[str]:
    """Build a searchable text bundle for a KO."""
    parts = [ko.title or "", ko.summary or ""]
    detail = ko.detail or {}
    if isinstance(detail, dict):
        for key in ("statement", "rationale"):
            value = detail.get(key)
            if isinstance(value, str):
                parts.append(value)
        for key in ("alternatives_considered", "expected_follow_ups"):
            for value in detail.get(key) or []:
                if isinstance(value, str):
                    parts.append(value)
        for entry in detail.get("related_context") or []:
            if isinstance(entry, dict):
                content = entry.get("content")
                if isinstance(content, str):
                    parts.append(content)
    for tag in ko.tags or []:
        if isinstance(tag, str):
            parts.append(tag)
    return parts


def _event_search_parts(event: Event) -> list[str]:
    """Build a searchable text bundle for a raw event."""
    metadata = event.metadata_ or {}
    parts = [event.content or "", event.actor_name or ""]
    for key in ("repo", "ref", "url"):
        value = metadata.get(key)
        if isinstance(value, str):
            parts.append(value)
    for attachment in metadata.get("attachments") or []:
        if isinstance(attachment, dict):
            for key in ("name", "filetype", "mimetype"):
                value = attachment.get(key)
                if isinstance(value, str):
                    parts.append(value)
    return parts


def _match_score(query: str, candidate_parts: list[str]) -> float:
    """Return a simple relevance score based on keyword overlap."""
    query_tokens = _normalize_search_tokens(query)
    if not query_tokens:
        return 0.0

    candidate_tokens = _normalize_search_tokens(*candidate_parts)
    if not candidate_tokens:
        return 0.0

    shared = query_tokens & candidate_tokens
    if not shared:
        return 0.0

    exact_phrase_bonus = 0.0
    joined = " ".join(candidate_parts).lower()
    ordered_query_tokens = [
        token
        for token in _SEARCH_TOKEN_PATTERN.findall(query.lower())
        if len(token) >= 2 and token not in _SEARCH_STOPWORDS
    ]
    query_text = " ".join(ordered_query_tokens)
    if query_text and query_text in joined:
        exact_phrase_bonus = 0.5

    return len(shared) + (len(shared) / len(query_tokens)) + exact_phrase_bonus


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
        type=canonicalize_knowledge_type(ko_data["type"]),
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


async def search_knowledge_objects(
    db: AsyncSession,
    query: str,
    type_filter: str | None = None,
    project_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Full-text search over knowledge objects by title + summary.

    Used by the investigative chat agent to answer user questions.
    """
    stmt = select(KnowledgeObject).where(KnowledgeObject.status != "merged")
    if type_filter and type_filter != "any":
        matched_types = equivalent_knowledge_types(type_filter)
        stmt = stmt.where(KnowledgeObject.type.in_(matched_types))
    if project_id:
        stmt = stmt.where(KnowledgeObject.project_id == project_id)
    stmt = stmt.order_by(KnowledgeObject.detected_at.desc()).limit(limit * 6)

    result = await db.execute(stmt)
    kos = result.scalars().all()

    scored = []
    for ko in kos:
        match_score = _match_score(query, _knowledge_search_parts(ko))
        if match_score > 0:
            scored.append((match_score, ko))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1].detected_at or "",
        ),
        reverse=True,
    )
    scored = scored[:limit]
    return [
        {
            "id": str(ko.id),
            "type": canonicalize_knowledge_type(ko.type),
            "title": ko.title,
            "summary": ko.summary,
            "confidence": ko.confidence,
            "status": ko.status,
            "detected_at": ko.detected_at.isoformat() if hasattr(ko.detected_at, "isoformat") else str(ko.detected_at or ""),
            "match_score": score,
        }
        for score, ko in scored
    ]


async def search_events(
    db: AsyncSession,
    query: str,
    source: str | None = None,
    project_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Full-text search over raw ingested events.

    Used by the investigative chat agent.
    """
    stmt = select(Event)
    if source and source != "any":
        stmt = stmt.where(Event.source == source)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)
    stmt = stmt.order_by(Event.ingested_at.desc()).limit(limit * 6)

    result = await db.execute(stmt)
    events = result.scalars().all()

    scored = []
    for ev in events:
        match_score = _match_score(query, _event_search_parts(ev))
        if match_score > 0:
            scored.append((match_score, ev))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1].ingested_at or "",
        ),
        reverse=True,
    )
    scored = scored[:limit]
    return [
        {
            "id": str(ev.id),
            "source": ev.source,
            "event_type": ev.event_type,
            "actor_name": ev.actor_name,
            "content": (ev.content or "")[:500],
            "occurred_at": ev.occurred_at.isoformat() if hasattr(ev.occurred_at, "isoformat") else str(ev.occurred_at or ""),
            "match_score": score,
        }
        for score, ev in scored
    ]


async def get_verification_checks_for_ko(
    db: AsyncSession, knowledge_id: str
) -> list[dict]:
    """Get all verification checks for a KO."""
    result = await db.execute(
        select(VerificationCheck).where(VerificationCheck.knowledge_id == knowledge_id)
    )
    checks = result.scalars().all()
    return [
        {
            "description": c.description,
            "status": c.status,
            "evidence": c.evidence,
            "suggestion": c.suggestion,
        }
        for c in checks
    ]
