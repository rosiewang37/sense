"""Background tasks for the Sense application layer.

Pipeline: ingest event → generate embedding → detect/extract KO → verify.
Correlation runs on a periodic schedule via APScheduler.

All tasks are plain async functions invoked via FastAPI BackgroundTasks.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def ping() -> str:
    """Test task to verify background tasks work."""
    return "pong"


async def process_event_async(event_data: dict) -> dict:
    """Process an ingested event through the full pipeline.

    1. Store the event (with dedup)
    2. Generate and store embedding
    3. Run extraction pipeline (pre-filter → classify → extract)
    4. If a KO is extracted, store it and trigger verification
    """
    from app.database import get_session_factory
    from app.backboard.store import store_event, store_knowledge_object
    from app.backboard.embeddings import generate_embedding
    from app.backboard.models import KnowledgeEvent

    async with get_session_factory()() as db:
        # Step 1: Store event (dedup handled inside store_event)
        event = await store_event(db, event_data)
        event_id = str(event.id)
        logger.info(f"Stored event {event_id} from {event_data.get('source')}")

        # Step 2: Generate embedding for the event content
        content = event_data.get("content", "")
        if content:
            embedding_bytes = await generate_embedding(content)
            if embedding_bytes:
                event.embedding = embedding_bytes
                logger.info(f"Generated embedding for event {event_id}")

        await db.commit()

        # Step 3: Run extraction pipeline
        from app.sense.detection import run_extraction_pipeline

        ko_data = await run_extraction_pipeline(event_data)

        if ko_data is None:
            logger.info(f"Event {event_id} filtered out (not significant)")
            return {"event_id": event_id, "ko_created": False}

        # Step 4: Store Knowledge Object
        ko_data["occurred_at"] = event_data.get("occurred_at")
        ko_data["project_id"] = event_data.get("project_id")
        ko_data["participants"] = _extract_participants(event_data)

        ko = await store_knowledge_object(db, ko_data)
        ko_id = str(ko.id)
        logger.info(f"Created KO {ko_id}: {ko_data.get('title')}")

        # Generate KO embedding
        ko_text = f"{ko_data.get('title', '')} {ko_data.get('summary', '')}"
        ko_embedding = await generate_embedding(ko_text)
        if ko_embedding:
            ko.embedding = ko_embedding

        # Link event to KO
        link = KnowledgeEvent(
            knowledge_id=ko_id,
            event_id=event_id,
            relevance=1.0,
            relationship_="source_event",
        )
        db.add(link)
        await db.commit()

        # Step 5: Run verification inline (same background task)
        await run_verification_async(ko_id)

        return {"event_id": event_id, "ko_created": True, "ko_id": ko_id}


def _extract_participants(event_data: dict) -> list[dict]:
    """Extract participant info from event data."""
    participants = []
    actor_email = event_data.get("actor_email")
    actor_name = event_data.get("actor_name")
    if actor_email or actor_name:
        participants.append({
            "email": actor_email or "",
            "name": actor_name or "",
            "role": "author",
        })
    return participants


async def run_verification_async(ko_id: str) -> dict:
    """Run the verification agent on a Knowledge Object."""
    from app.database import get_session_factory
    from app.backboard.store import get_knowledge_object, store_verification_check
    from app.sense.agents.verification import run_verification_agent

    async with get_session_factory()() as db:
        ko = await get_knowledge_object(db, ko_id)
        if not ko:
            logger.warning(f"KO {ko_id} not found for verification")
            return {"ko_id": ko_id, "checks": 0}

        # Build KO dict for agent
        ko_dict = {
            "id": str(ko.id),
            "type": ko.type,
            "title": ko.title,
            "summary": ko.summary,
            "detail": ko.detail or {},
            "participants": ko.participants or [],
            "tags": ko.tags or [],
            "confidence": ko.confidence,
        }

        checks = await run_verification_agent(ko_dict)
        logger.info(f"Verification for KO {ko_id}: {len(checks)} checks")

        # Store checks
        for check in checks:
            await store_verification_check(db, ko_id, **check)

        await db.commit()
        return {"ko_id": ko_id, "checks": len(checks)}


async def run_correlation_async() -> dict:
    """Run cross-tool correlation on recent knowledge objects.

    Scheduled periodically (every 2 minutes via APScheduler). Compares recent KOs
    pairwise and merges those above the threshold.
    """
    from app.database import get_session_factory
    from app.backboard.store import get_recent_knowledge
    from app.backboard.embeddings import bytes_to_vector
    from app.backboard.models import KnowledgeMerge
    from app.sense.correlation import weighted_correlation_score, MERGE_THRESHOLD

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    async with get_session_factory()() as db:
        kos = await get_recent_knowledge(db, project_id=None, since=since)

        if len(kos) < 2:
            return {"merges": 0, "scanned": len(kos)}

        merges_performed = 0

        # Pairwise comparison
        for i in range(len(kos)):
            for j in range(i + 1, len(kos)):
                ko_a = kos[i]
                ko_b = kos[j]

                # Get embeddings
                emb_a = bytes_to_vector(ko_a.embedding) if ko_a.embedding else []
                emb_b = bytes_to_vector(ko_b.embedding) if ko_b.embedding else []

                if not emb_a or not emb_b:
                    continue

                # Get actors
                actors_a = {p.get("email", "") for p in (ko_a.participants or []) if p.get("email")}
                actors_b = {p.get("email", "") for p in (ko_b.participants or []) if p.get("email")}

                # Compute time difference
                try:
                    time_a = datetime.fromisoformat(ko_a.occurred_at) if ko_a.occurred_at else datetime.now(timezone.utc)
                    time_b = datetime.fromisoformat(ko_b.occurred_at) if ko_b.occurred_at else datetime.now(timezone.utc)
                    time_diff = abs((time_a - time_b).total_seconds())
                except (ValueError, TypeError):
                    time_diff = 86400  # Default to 24h if parsing fails

                # Get content for reference matching
                content_a = f"{ko_a.title or ''} {ko_a.summary or ''}"
                content_b = f"{ko_b.title or ''} {ko_b.summary or ''}"

                score = weighted_correlation_score(
                    emb_a, emb_b, actors_a, actors_b,
                    time_diff, content_a, content_b,
                )

                if score > MERGE_THRESHOLD:
                    # Record merge (primary = higher confidence)
                    if ko_b.confidence > ko_a.confidence:
                        primary, merged = ko_b, ko_a
                    else:
                        primary, merged = ko_a, ko_b

                    merge_record = KnowledgeMerge(
                        primary_id=str(primary.id),
                        merged_id=str(merged.id),
                        merge_score=score,
                    )
                    db.add(merge_record)

                    # Mark the lower-confidence KO as merged
                    merged.status = "merged"
                    merges_performed += 1
                    logger.info(
                        f"Merged KO {merged.id} into {primary.id} (score={score:.3f})"
                    )

        await db.commit()
        return {"merges": merges_performed, "scanned": len(kos)}
