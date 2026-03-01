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

    source = event_data.get("source", "unknown")
    content_preview = (event_data.get("content") or "")[:80]
    logger.info(f"[task] ===== PROCESSING EVENT from {source}: \"{content_preview}\" =====")

    async with get_session_factory()() as db:
        # Step 1: Store event (dedup handled inside store_event)
        event = await store_event(db, event_data)
        event_id = str(event.id)
        logger.info(f"[task] Step 1/5 STORE: event {event_id} stored")

        if event_data.get("source") == "slack":
            logger.info(f"[task] Step 1b ENRICH: fetching Slack context...")
            event_data = await _enrich_slack_event_context(event, event_data)
            ctx = (event_data.get("metadata") or {}).get("context_messages")
            logger.info(f"[task] Step 1b ENRICH: done ({len(ctx) if ctx else 0} context messages)")
            # Ensure SQLAlchemy detects the JSON column change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(event, "metadata_")

        # Step 2: Generate embedding for the event content
        content = event_data.get("content", "")
        if content:
            logger.info(f"[task] Step 2/5 EMBED: generating embedding...")
            embedding_bytes = await generate_embedding(content)
            if embedding_bytes:
                event.embedding = embedding_bytes
                logger.info(f"[task] Step 2/5 EMBED: success")
            else:
                logger.warning(f"[task] Step 2/5 EMBED: returned None (API issue?)")

        await db.commit()

        # Step 3: Run extraction pipeline
        from app.sense.detection import run_extraction_pipeline

        logger.info(f"[task] Step 3/5 EXTRACT: running extraction pipeline...")
        try:
            ko_data = await run_extraction_pipeline(event_data)
        except Exception as e:
            logger.error(f"[task] Step 3/5 EXTRACT FAILED: {e}", exc_info=True)
            return {"event_id": event_id, "ko_created": False, "error": str(e)}

        if ko_data is None:
            logger.info(f"[task] Step 3/5 EXTRACT: no KO produced (filtered or not significant)")

            # Even without a new KO, try to link this event to an existing one.
            # GitHub events → link as evidence; Slack events → link as context
            # and re-enrich the source event with updated surrounding messages.
            if source == "github":
                linked_ko_id = await _find_and_link_to_existing_decision(
                    db, event_id, event_data
                )
                if linked_ko_id:
                    logger.info(
                        f"[task] GitHub event {event_id} linked as evidence to KO {linked_ko_id}"
                    )
                    return {"event_id": event_id, "ko_created": False, "linked_ko_id": linked_ko_id}
            elif source == "slack":
                linked_ko_id = await _try_update_related_ko(db, event_id, event_data)
                if linked_ko_id:
                    logger.info(
                        f"[task] ===== EVENT {event_id} DONE (linked as context to KO {linked_ko_id}) ====="
                    )
                    return {"event_id": event_id, "ko_created": False, "linked_ko_id": linked_ko_id}

            logger.info(f"[task] ===== EVENT {event_id} DONE (no KO) =====")
            return {"event_id": event_id, "ko_created": False}

        # Step 4: For GitHub events that DID produce a KO, check if it should
        # link to an existing decision KO instead of creating a duplicate.
        if event_data.get("source") == "github":
            linked_ko_id = await _find_and_link_to_existing_decision(
                db, event_id, event_data
            )
            if linked_ko_id:
                logger.info(
                    f"GitHub event {event_id} linked as evidence to decision KO {linked_ko_id}"
                )
                return {"event_id": event_id, "ko_created": False, "linked_ko_id": linked_ko_id}

        # Step 4b: Store as a new Knowledge Object
        logger.info(f"[task] Step 4/5 STORE KO: \"{ko_data.get('title')}\" (type={ko_data.get('type')})")
        ko_data["occurred_at"] = event_data.get("occurred_at")
        ko_data["project_id"] = event_data.get("project_id")
        ko_data["participants"] = _merge_participants(
            ko_data.get("participants"),
            _extract_participants(event_data),
        )

        ko = await store_knowledge_object(db, ko_data)
        ko_id = str(ko.id)
        logger.info(f"[task] Step 4/5 STORE KO: created KO {ko_id}")

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
        logger.info(f"[task] Step 4/5 STORE KO: committed to DB and linked to event {event_id}")

        # Step 5: Run verification inline (same background task)
        # NOTE: Verification is skipped when SKIP_VERIFICATION=true (for testing).
        # In production this should always run. Remove the flag once testing is done.
        from app.config import get_settings
        _settings = get_settings()
        if getattr(_settings, "skip_verification", False):
            logger.info(f"[task] Step 5/5 VERIFY: skipped (SKIP_VERIFICATION=true)")
        else:
            logger.info(f"[task] Step 5/5 VERIFY: running verification agent...")
            await run_verification_async(ko_id)
            logger.info(f"[task] Step 5/5 VERIFY: done")

        logger.info(f"[task] ===== EVENT {event_id} DONE → KO {ko_id} created =====")
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


def _merge_participants(*participant_groups: list[dict] | None) -> list[dict]:
    """Merge participant lists, deduplicating by email when available, else by name."""
    merged: dict[str, dict] = {}

    for group in participant_groups:
        for participant in group or []:
            if not isinstance(participant, dict):
                continue

            email = (participant.get("email") or "").strip()
            name = (participant.get("name") or "").strip()
            if not email and not name:
                continue

            key = email.lower() if email else f"name:{name.lower()}"
            existing = merged.get(key, {"email": "", "name": "", "role": "participant"})
            role = "author" if "author" in {existing.get("role"), participant.get("role")} else (
                participant.get("role") or existing.get("role") or "participant"
            )
            merged[key] = {
                "email": email or existing.get("email", ""),
                "name": name or existing.get("name", ""),
                "role": role,
            }

    return list(merged.values())


async def _enrich_slack_event_context(event, event_data: dict) -> dict:
    """Best-effort Slack enrichment for surrounding messages, names, and attachments."""
    from app.config import get_settings
    from app.sense.integrations.slack_api import (
        fetch_surrounding_messages,
        get_file_metadata,
        resolve_user_name,
    )

    settings = get_settings()
    if not settings.slack_bot_token:
        return event_data

    metadata = dict(event.metadata_ or event_data.get("metadata") or {})
    channel = metadata.get("channel")
    message_ts = event_data.get("source_id")

    if channel and message_ts:
        context_messages = await fetch_surrounding_messages(
            channel=channel,
            message_ts=message_ts,
            bot_token=settings.slack_bot_token,
        )
        if context_messages:
            metadata["context_messages"] = context_messages

    actor_id = event_data.get("actor_name") or ""
    if actor_id:
        actor_display_name = await resolve_user_name(actor_id, settings.slack_bot_token)
        if actor_display_name:
            metadata["actor_display_name"] = actor_display_name
            event.actor_name = actor_display_name
            event_data["actor_name"] = actor_display_name

    attachments = []
    for file_id in metadata.get("file_ids") or []:
        file_metadata = await get_file_metadata(file_id, settings.slack_bot_token)
        if file_metadata:
            attachments.append(file_metadata)
    if attachments:
        metadata["attachments"] = attachments

    event.metadata_ = metadata
    event_data["metadata"] = metadata
    return event_data


async def _try_update_related_ko(db, event_id: str, event_data: dict) -> str | None:
    """Link a non-decision Slack event to a recent KO from the same channel.

    When a Slack message that doesn't produce its own KO arrives in the same
    channel as a recent decision, this function:
    1. Links the new event to the existing KO as a 'context' relationship
    2. Re-fetches surrounding messages for the KO's source event (capturing
       follow-ups that weren't available during initial processing)
    3. Merges new participant names into the KO
    """
    if event_data.get("source") != "slack":
        return None

    channel = (event_data.get("metadata") or {}).get("channel")
    if not channel:
        return None

    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified
    from app.backboard.models import Event as EventModel, KnowledgeEvent, KnowledgeObject

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Find the most recent active KO whose source event is from the same channel
    result = await db.execute(
        select(KnowledgeObject, EventModel)
        .join(KnowledgeEvent, KnowledgeEvent.knowledge_id == KnowledgeObject.id)
        .join(EventModel, KnowledgeEvent.event_id == EventModel.id)
        .where(
            KnowledgeObject.status == "active",
            KnowledgeObject.detected_at >= since,
            EventModel.source == "slack",
            KnowledgeEvent.relationship_ == "source_event",
        )
        .order_by(KnowledgeObject.detected_at.desc())
    )

    matched_ko = None
    source_event = None
    for ko, evt in result.all():
        evt_channel = (evt.metadata_ or {}).get("channel")
        if evt_channel == channel:
            matched_ko = ko
            source_event = evt
            break

    if not matched_ko or not source_event:
        return None

    ko_id = str(matched_ko.id)

    # 1. Link this event to the KO as context (skip if already linked)
    existing_link = await db.execute(
        select(KnowledgeEvent).where(
            KnowledgeEvent.knowledge_id == ko_id,
            KnowledgeEvent.event_id == event_id,
        )
    )
    if not existing_link.scalar_one_or_none():
        link = KnowledgeEvent(
            knowledge_id=ko_id,
            event_id=event_id,
            relevance=0.5,
            relationship_="context",
        )
        db.add(link)

    # 2. Re-enrich the source event's surrounding messages so the
    #    ContextPanel picks up follow-up messages that arrived after
    #    the decision was first processed.
    from app.config import get_settings
    from app.sense.integrations.slack_api import fetch_surrounding_messages

    settings = get_settings()
    if settings.slack_bot_token:
        source_ts = source_event.source_id
        if source_ts:
            context_messages = await fetch_surrounding_messages(
                channel=channel,
                message_ts=source_ts,
                bot_token=settings.slack_bot_token,
            )
            if context_messages:
                updated_metadata = dict(source_event.metadata_ or {})
                updated_metadata["context_messages"] = context_messages
                source_event.metadata_ = updated_metadata
                flag_modified(source_event, "metadata_")

    # 3. Update KO participants with the new actor name
    actor_name = event_data.get("actor_name", "")
    if actor_name:
        current_participants = list(matched_ko.participants or [])
        existing_names = {(p.get("name") or "").lower() for p in current_participants}
        if actor_name.lower() not in existing_names:
            current_participants.append({
                "email": "",
                "name": actor_name,
                "role": "participant",
            })
            matched_ko.participants = current_participants
            flag_modified(matched_ko, "participants")

    await db.commit()
    logger.info(
        f"[task] Linked event {event_id} as context to KO {ko_id} and re-enriched source event"
    )
    return ko_id


async def _find_and_link_to_existing_decision(
    db, event_id: str, event_data: dict
) -> str | None:
    """Check if a GitHub event's content correlates with a recent decision KO.

    If a match is found above the threshold, links the event as evidence to
    the existing decision and returns its ID. Returns None if no match found.
    """
    from app.backboard.store import get_recent_knowledge
    from app.backboard.embeddings import generate_embedding, bytes_to_vector
    from app.backboard.models import KnowledgeEvent
    from app.sense.correlation import weighted_correlation_score, MERGE_THRESHOLD

    # Only look at decision KOs from the past 7 days
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_kos = await get_recent_knowledge(db, project_id=event_data.get("project_id"), since=since)
    decision_kos = [ko for ko in recent_kos if ko.type == "decision"]

    if not decision_kos:
        return None

    # Generate embedding for the GitHub event content
    content = event_data.get("content", "")
    event_embedding_bytes = await generate_embedding(content) if content else None
    event_vector = bytes_to_vector(event_embedding_bytes) if event_embedding_bytes else []

    # Get actors from the event
    actors_event = set()
    if event_data.get("actor_email"):
        actors_event.add(event_data["actor_email"])

    best_score = 0.0
    best_ko = None

    for ko in decision_kos:
        ko_vector = bytes_to_vector(ko.embedding) if ko.embedding else []
        actors_ko = {p.get("email", "") for p in (ko.participants or []) if p.get("email")}

        # Use a generous time window (7 days) — GitHub commits can happen days after a decision
        score = weighted_correlation_score(
            event_vector, ko_vector,
            actors_event, actors_ko,
            time_diff_seconds=0,  # Don't penalise time; decisions precede implementation
            content_a=content,
            content_b=f"{ko.title or ''} {ko.summary or ''}",
            window_hours=168,  # 7 days
        )

        if score > best_score:
            best_score = score
            best_ko = ko

    # Link threshold — slightly lower than merge threshold so we catch related commits
    LINK_THRESHOLD = MERGE_THRESHOLD * 0.75  # ~0.45

    if best_ko and best_score >= LINK_THRESHOLD:
        # Link this event as evidence to the existing decision KO
        from sqlalchemy import select
        existing_link = await db.execute(
            select(KnowledgeEvent).where(
                KnowledgeEvent.knowledge_id == str(best_ko.id),
                KnowledgeEvent.event_id == event_id,
            )
        )
        if not existing_link.scalar_one_or_none():
            link = KnowledgeEvent(
                knowledge_id=str(best_ko.id),
                event_id=event_id,
                relevance=best_score,
                relationship_="github_evidence",
            )
            db.add(link)
            await db.commit()

        return str(best_ko.id)

    return None


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

                # Get embeddings (may be empty — correlation still works
                # via actor, temporal, and reference scoring)
                emb_a = bytes_to_vector(ko_a.embedding) if ko_a.embedding else []
                emb_b = bytes_to_vector(ko_b.embedding) if ko_b.embedding else []

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
