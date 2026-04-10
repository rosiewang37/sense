"""Knowledge Object API: CRUD, filtering, verification status."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.backboard.models import Event, KnowledgeEvent, KnowledgeObject, VerificationCheck
from app.models.user import User
from app.sense.knowledge_types import canonicalize_knowledge_type, equivalent_knowledge_types

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeResponse(BaseModel):
    id: str
    type: str
    title: str
    summary: str | None
    detail: dict | None
    participants: list | None
    tags: list | None
    confidence: float
    status: str
    detected_at: str | None
    occurred_at: str | None
    verification_summary: dict | None = None
    source_events: list | None = None


class KnowledgeUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    tags: list[str] | None = None


@router.get("")
async def list_knowledge(
    type: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge objects with pagination and filters."""
    query = select(KnowledgeObject)

    if type:
        query = query.where(KnowledgeObject.type.in_(equivalent_knowledge_types(type)))
    if status:
        query = query.where(KnowledgeObject.status == status)
    if project_id:
        query = query.where(KnowledgeObject.project_id == project_id)

    query = query.order_by(KnowledgeObject.detected_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    kos = result.scalars().all()

    items = []
    for ko in kos:
        # Get verification summary
        v_result = await db.execute(
            select(VerificationCheck).where(VerificationCheck.knowledge_id == str(ko.id))
        )
        checks = v_result.scalars().all()
        v_summary = None
        if checks:
            v_summary = {
                "total": len(checks),
                "verified": sum(1 for c in checks if c.status == "verified"),
                "missing": sum(1 for c in checks if c.status == "missing"),
                "unknown": sum(1 for c in checks if c.status == "unknown"),
            }

        items.append({
            "id": str(ko.id),
            "type": canonicalize_knowledge_type(ko.type),
            "title": ko.title,
            "summary": ko.summary,
            "detail": ko.detail,
            "participants": ko.participants,
            "tags": ko.tags,
            "confidence": ko.confidence,
            "status": ko.status,
            "detected_at": ko.detected_at,
            "occurred_at": ko.occurred_at,
            "verification_summary": v_summary,
        })

    return {"items": items, "total": len(items), "offset": offset, "limit": limit}


@router.get("/{ko_id}")
async def get_knowledge(
    ko_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single knowledge object with verification checks."""
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == ko_id)
    )
    ko = result.scalar_one_or_none()
    if not ko:
        raise HTTPException(status_code=404, detail="Knowledge object not found")

    # Get verification checks
    v_result = await db.execute(
        select(VerificationCheck).where(VerificationCheck.knowledge_id == ko_id)
    )
    checks = v_result.scalars().all()

    linked_event_result = await db.execute(
        select(Event, KnowledgeEvent)
        .join(KnowledgeEvent, KnowledgeEvent.event_id == Event.id)
        .where(KnowledgeEvent.knowledge_id == ko_id)
        .order_by(Event.occurred_at.asc())
    )
    source_events = []
    for event, link in linked_event_result.all():
        source_events.append(
            {
                "id": str(event.id),
                "source": event.source,
                "source_id": event.source_id,
                "event_type": event.event_type,
                "actor_name": event.actor_name,
                "content": event.content,
                "occurred_at": event.occurred_at,
                "relationship": link.relationship_,
                "relevance": link.relevance,
                "metadata": event.metadata_ or {},
            }
        )

    return {
        "id": str(ko.id),
        "type": canonicalize_knowledge_type(ko.type),
        "title": ko.title,
        "summary": ko.summary,
        "detail": ko.detail,
        "participants": ko.participants,
        "tags": ko.tags,
        "confidence": ko.confidence,
        "status": ko.status,
        "detected_at": ko.detected_at,
        "occurred_at": ko.occurred_at,
        "source_events": source_events,
        "verification_checks": [
            {
                "id": str(c.id),
                "description": c.description,
                "status": c.status,
                "evidence": c.evidence,
                "suggestion": c.suggestion,
                "checked_at": c.checked_at,
            }
            for c in checks
        ],
    }


@router.patch("/{ko_id}")
async def update_knowledge(
    ko_id: str,
    update: KnowledgeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge object (title, status, tags)."""
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == ko_id)
    )
    ko = result.scalar_one_or_none()
    if not ko:
        raise HTTPException(status_code=404, detail="Knowledge object not found")

    if update.title is not None:
        ko.title = update.title
    if update.status is not None:
        ko.status = update.status
    if update.tags is not None:
        ko.tags = update.tags

    return {"ok": True}


@router.delete("/{ko_id}")
async def delete_knowledge(
    ko_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge object."""
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == ko_id)
    )
    ko = result.scalar_one_or_none()
    if not ko:
        raise HTTPException(status_code=404, detail="Knowledge object not found")

    await db.delete(ko)
    return {"ok": True}


@router.post("/{ko_id}/confirm")
async def confirm_knowledge(
    ko_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Human confirms accuracy of a knowledge object."""
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == ko_id)
    )
    ko = result.scalar_one_or_none()
    if not ko:
        raise HTTPException(status_code=404, detail="Knowledge object not found")

    ko.reviewed = True
    ko.reviewed_by = current_user.email
    return {"ok": True}


@router.post("/{ko_id}/dismiss")
async def dismiss_knowledge(
    ko_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Human dismisses a false positive knowledge object."""
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == ko_id)
    )
    ko = result.scalar_one_or_none()
    if not ko:
        raise HTTPException(status_code=404, detail="Knowledge object not found")

    ko.status = "dismissed"
    ko.reviewed = True
    ko.reviewed_by = current_user.email
    return {"ok": True}


@router.get("/{ko_id}/verification")
async def get_verification_checks(
    ko_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get verification checks for a knowledge object."""
    result = await db.execute(
        select(VerificationCheck).where(VerificationCheck.knowledge_id == ko_id)
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
