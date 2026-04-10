"""Background tasks for the Sense application layer.

Pipeline: ingest event → generate embedding → detect/extract KO → verify.
Correlation runs on a periodic schedule via APScheduler.

All tasks are plain async functions invoked via FastAPI BackgroundTasks.
"""
import logging
import re
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_FOLLOW_UP_PATTERN = re.compile(
    r"\b(i('| wi)?ll|we('| wi)?ll|next|follow[- ]?up|start|update|document|implement|"
    r"migrat\w*|ship|roll\s*out|this sprint|by end of|by eow)\b",
    re.IGNORECASE,
)
_MATCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "for",
    "from", "had", "has", "have", "if", "in", "into", "is", "it", "its",
    "of", "on", "or", "our", "that", "the", "their", "them", "this", "to",
    "us", "was", "we", "were", "will", "with",
}


def _trim_suffix(token: str) -> str:
    """Apply lightweight stemming so singular/plural and tense variants still match."""
    for suffix, replacement in (
        ("ies", "y"),
        ("ied", "y"),
        ("ing", ""),
        ("ers", ""),
        ("er", ""),
        ("ed", ""),
        ("es", ""),
        ("s", ""),
    ):
        if len(token) <= len(suffix) + 2 or not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)] + replacement
        if len(stem) >= 3 and stem[-1:] == stem[-2:-1]:
            stem = stem[:-1]
        return stem
    return token


def _tokenize_for_match(*parts: str | None) -> set[str]:
    """Normalize text into comparable keyword tokens."""
    tokens: set[str] = set()
    for part in parts:
        if not part:
            continue
        for raw in _TOKEN_PATTERN.findall(part.lower()):
            if len(raw) < 2 or raw in _MATCH_STOPWORDS:
                continue
            token = _trim_suffix(raw)
            if len(token) >= 2 and token not in _MATCH_STOPWORDS:
                tokens.add(token)
    return tokens


def _extract_knowledge_parts(knowledge: object) -> list[str]:
    """Build the searchable text for a KO from title, detail, and tags."""
    if isinstance(knowledge, dict):
        title = knowledge.get("title")
        summary = knowledge.get("summary")
        detail = knowledge.get("detail") or {}
        tags = knowledge.get("tags") or []
    else:
        title = getattr(knowledge, "title", None)
        summary = getattr(knowledge, "summary", None)
        detail = getattr(knowledge, "detail", None) or {}
        tags = getattr(knowledge, "tags", None) or []

    parts = [title, summary]
    if isinstance(detail, dict):
        for key in ("statement", "rationale"):
            value = detail.get(key)
            if isinstance(value, str):
                parts.append(value)
        for key in ("alternatives_considered", "expected_follow_ups"):
            for value in detail.get(key) or []:
                if isinstance(value, str):
                    parts.append(value)

    for tag in tags:
        if isinstance(tag, str):
            parts.append(tag)

    return [part for part in parts if isinstance(part, str) and part.strip()]


def _extract_event_parts(event_data: dict) -> list[str]:
    """Build searchable text for an event from content and attachment metadata."""
    metadata = event_data.get("metadata") or {}
    parts = [event_data.get("content")]

    for attachment in metadata.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        attachment_text = " ".join(
            str(attachment.get(key) or "")
            for key in ("name", "filetype", "mimetype")
        ).strip()
        if attachment_text:
            parts.append(attachment_text)

    for key in ("repo", "ref", "url"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)

    return [part for part in parts if isinstance(part, str) and part.strip()]


def _text_overlap_score(left_parts: list[str], right_parts: list[str]) -> tuple[float, set[str]]:
    """Measure keyword overlap between two pieces of text."""
    left_tokens = _tokenize_for_match(*left_parts)
    right_tokens = _tokenize_for_match(*right_parts)
    if not left_tokens or not right_tokens:
        return 0.0, set()

    shared = left_tokens & right_tokens
    if not shared:
        return 0.0, set()

    precision = len(shared) / len(left_tokens)
    recall = len(shared) / len(right_tokens)
    return ((precision * 0.7) + (recall * 0.3), shared)


def _looks_like_follow_up_message(text: str | None) -> bool:
    """Detect action-oriented follow-up messages that rely on surrounding context."""
    if not text:
        return False
    return bool(_FOLLOW_UP_PATTERN.search(text))


def _score_event_against_knowledge(knowledge: object, event_data: dict) -> float:
    """Score whether an event is relevant to an existing KO using local heuristics."""
    knowledge_parts = _extract_knowledge_parts(knowledge)
    direct_score, _ = _text_overlap_score(_extract_event_parts(event_data), knowledge_parts)
    if direct_score > 0:
        print(f"[SENSE] _score_event_against_knowledge: direct overlap={direct_score:.3f}", flush=True)
        return direct_score

    is_follow_up = _looks_like_follow_up_message(event_data.get("content"))
    print(f"[SENSE] _score_event_against_knowledge: direct overlap=0, looks_like_follow_up={is_follow_up}", flush=True)
    if not is_follow_up:
        return 0.0

    metadata = event_data.get("metadata") or {}
    current_ts = str(event_data.get("source_id") or "")
    context_messages = metadata.get("context_messages") or []
    print(f"[SENSE] _score_event_against_knowledge: {len(context_messages)} context messages available", flush=True)
    nearby_scores = []
    for message in context_messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("ts") or "") == current_ts:
            continue
        score, _ = _text_overlap_score([str(message.get("text") or "")], knowledge_parts)
        if score > 0:
            nearby_scores.append(score)

    if not nearby_scores:
        print(f"[SENSE] _score_event_against_knowledge: no nearby context scores — returning 0", flush=True)
        return 0.0

    final = max(nearby_scores) * 0.75
    print(f"[SENSE] _score_event_against_knowledge: nearby_scores={[f'{s:.3f}' for s in nearby_scores]}, final={final:.3f}", flush=True)
    return final


def _message_preview_from_event(event_data: dict) -> str:
    """Build a human-readable preview for a linked event."""
    content = (event_data.get("content") or "").strip()
    if content:
        return content

    attachment_names = [
        str(attachment.get("name") or "").strip()
        for attachment in (event_data.get("metadata") or {}).get("attachments") or []
        if isinstance(attachment, dict) and str(attachment.get("name") or "").strip()
    ]
    if attachment_names:
        return f"Shared attachment: {', '.join(attachment_names)}"

    return ""


def _event_to_context_message(event_data: dict) -> dict | None:
    """Represent an event as a context message for the source Slack event."""
    preview = _message_preview_from_event(event_data)
    source_id = str(event_data.get("source_id") or "").strip()
    if not preview or not source_id:
        return None

    metadata = event_data.get("metadata") or {}
    actor_name = (
        metadata.get("actor_display_name")
        or event_data.get("actor_name")
        or "Unknown"
    )
    return {
        "user_name": str(actor_name or "Unknown"),
        "text": preview,
        "ts": source_id,
    }


def _merge_attachments(existing: list[dict] | None, new_items: list[dict] | None) -> list[dict]:
    """Merge attachment metadata, preferring the newest version of each file."""
    merged: dict[str, dict] = {}
    for attachment in (existing or []) + (new_items or []):
        if not isinstance(attachment, dict):
            continue
        key = str(attachment.get("id") or attachment.get("name") or "").strip()
        if not key:
            continue
        merged[key] = attachment
    return list(merged.values())


def _filter_context_messages_for_knowledge(
    context_messages: list[dict] | None,
    knowledge: object,
    trigger_ts: str,
    always_include_ts: set[str] | None = None,
) -> list[dict]:
    """Keep only the trigger and nearby messages that actually support the KO.

    Uses a combination of keyword overlap and proximity to the trigger message:
    - Messages within 2 positions of the trigger are always included (proximity)
    - Other messages need a keyword overlap score >= 0.04
    - Proximity bonus: messages closer to trigger get a 0.03 boost per position
    """
    input_count = len(context_messages) if context_messages else 0
    always_include_ts = always_include_ts or set()
    knowledge_parts = _extract_knowledge_parts(knowledge)
    deduped: dict[str, dict] = {}

    for message in context_messages or []:
        if not isinstance(message, dict):
            continue
        ts = str(message.get("ts") or "").strip()
        if not ts:
            continue
        deduped[ts] = {
            "user_name": str(message.get("user_name") or "Unknown"),
            "text": str(message.get("text") or ""),
            "ts": ts,
        }

    # Build an ordered list of timestamps to determine trigger position
    ordered_ts = sorted(deduped.keys(), key=lambda t: float(t) if t.replace(".", "").isdigit() else 0)
    trigger_index = None
    for i, ts in enumerate(ordered_ts):
        if ts == trigger_ts:
            trigger_index = i
            break

    _THRESHOLD = 0.04
    _PROXIMITY_WINDOW = 2  # messages within 2 positions always included
    _PROXIMITY_BONUS = 0.03  # bonus per position closer to trigger

    filtered: list[dict] = []
    for ts, message in deduped.items():
        if ts == trigger_ts or ts in always_include_ts:
            filtered.append(message)
            continue

        # Compute distance from trigger message
        distance = None
        if trigger_index is not None:
            msg_index = None
            for i, t in enumerate(ordered_ts):
                if t == ts:
                    msg_index = i
                    break
            if msg_index is not None:
                distance = abs(msg_index - trigger_index)

        # Always include messages within proximity window of trigger
        if distance is not None and distance <= _PROXIMITY_WINDOW:
            filtered.append(message)
            continue

        score, _ = _text_overlap_score([message.get("text", "")], knowledge_parts)

        # Apply proximity bonus for nearby messages
        if distance is not None and distance > 0:
            proximity_bonus = max(0, _PROXIMITY_BONUS * (_PROXIMITY_WINDOW + 2 - distance))
            score += proximity_bonus

        if score >= _THRESHOLD:
            filtered.append(message)

    if trigger_ts and trigger_ts in deduped and not any(msg["ts"] == trigger_ts for msg in filtered):
        filtered.append(deduped[trigger_ts])

    def sort_key(message: dict) -> tuple[int, float]:
        try:
            return (0, float(message.get("ts") or 0))
        except (TypeError, ValueError):
            return (1, 0.0)

    filtered.sort(key=sort_key)
    print(f"[SENSE] _filter_context_messages_for_knowledge: {input_count} input → {len(filtered)} kept", flush=True)
    return filtered


def _update_knowledge_detail_with_linked_event(knowledge_object, event_data: dict, relationship: str) -> bool:
    """Record a concise list of linked context/evidence snippets on the KO itself."""
    preview = _message_preview_from_event(event_data)
    if not preview:
        return False

    detail = dict(knowledge_object.detail or {})
    related_context = list(detail.get("related_context") or [])
    new_entry = {
        "source": event_data.get("source"),
        "relationship": relationship,
        "content": preview[:300],
        "occurred_at": event_data.get("occurred_at"),
    }

    if new_entry in related_context:
        return False

    related_context.append(new_entry)
    detail["related_context"] = related_context[-10:]
    knowledge_object.detail = detail

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(knowledge_object, "detail")
    return True


def _refresh_source_event_context(source_event, knowledge: object, event_data: dict) -> bool:
    """Merge a linked Slack event into the KO's source-event context snapshot."""
    if getattr(source_event, "source", None) != "slack":
        return False

    from sqlalchemy.orm.attributes import flag_modified

    metadata = dict(source_event.metadata_ or {})
    existing_messages = list(metadata.get("context_messages") or [])
    additional_message = _event_to_context_message(event_data)
    if additional_message:
        existing_messages.append(additional_message)

    metadata["context_messages"] = _filter_context_messages_for_knowledge(
        existing_messages,
        knowledge,
        trigger_ts=str(getattr(source_event, "source_id", "") or ""),
        always_include_ts={additional_message["ts"]} if additional_message else None,
    )

    merged_attachments = _merge_attachments(
        metadata.get("attachments"),
        (event_data.get("metadata") or {}).get("attachments"),
    )
    if merged_attachments:
        metadata["attachments"] = merged_attachments

    if metadata == dict(source_event.metadata_ or {}):
        return False

    source_event.metadata_ = metadata
    flag_modified(source_event, "metadata_")
    return True


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
            meta = event_data.get("metadata") or {}
            ctx = meta.get("context_messages")
            attachments = meta.get("attachments")
            file_ids = meta.get("file_ids") or []
            print(
                f"[SENSE] Step 1b SUMMARY: "
                f"context_msgs={len(ctx) if ctx else 0}, "
                f"attachments={len(attachments) if attachments else 0}, "
                f"file_ids={file_ids}, "
                f"actor={event_data.get('actor_name')}",
                flush=True,
            )
            logger.info(f"[task] Step 1b ENRICH: done ({len(ctx) if ctx else 0} context messages)")
            # Ensure SQLAlchemy detects the JSON column change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(event, "metadata_")

        elif event_data.get("source") == "gmail":
            logger.info(f"[task] Step 1b ENRICH: fetching Gmail thread context...")
            event_data = await _enrich_gmail_event_context(event, event_data)
            ctx = (event_data.get("metadata") or {}).get("context_messages")
            logger.info(f"[task] Step 1b ENRICH: done ({len(ctx) if ctx else 0} thread messages)")

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
        _refresh_source_event_context(event, ko, event_data)
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
    metadata = dict(event.metadata_ or event_data.get("metadata") or {})
    channel = metadata.get("channel")
    message_ts = event_data.get("source_id")

    has_token = bool(settings.slack_bot_token)
    print(f"[SENSE] _enrich_slack_event_context: SLACK_BOT_TOKEN={'set' if has_token else 'NOT SET'}, channel={channel}, ts={message_ts}", flush=True)

    if settings.slack_bot_token and channel and message_ts:
        context_messages = await fetch_surrounding_messages(
            channel=channel,
            message_ts=message_ts,
            bot_token=settings.slack_bot_token,
        )
        print(f"[SENSE] _enrich_slack_event_context: fetch_surrounding_messages returned {len(context_messages)} messages", flush=True)
        if context_messages:
            metadata["context_messages"] = context_messages
    else:
        if not settings.slack_bot_token:
            print(f"[SENSE] _enrich_slack_event_context: skipping context fetch — no bot token", flush=True)
        elif not channel or not message_ts:
            print(f"[SENSE] _enrich_slack_event_context: skipping context fetch — missing channel or ts", flush=True)

    actor_id = event_data.get("actor_name") or ""
    if settings.slack_bot_token and actor_id:
        actor_display_name = await resolve_user_name(actor_id, settings.slack_bot_token)
        print(f"[SENSE] _enrich_slack_event_context: actor '{actor_id}' → '{actor_display_name}'", flush=True)
        if actor_display_name:
            metadata["actor_display_name"] = actor_display_name
            event.actor_name = actor_display_name
            event_data["actor_name"] = actor_display_name

    attachments = list(metadata.get("attachments") or [])
    file_ids = metadata.get("file_ids") or []
    print(f"[SENSE] _enrich_slack_event_context: file_ids={file_ids}", flush=True)
    if settings.slack_bot_token:
        for file_id in file_ids:
            print(f"[SENSE] _enrich_slack_event_context: fetching file metadata for {file_id}...", flush=True)
            file_metadata = await get_file_metadata(file_id, settings.slack_bot_token)
            if file_metadata:
                print(f"[SENSE] _enrich_slack_event_context: file '{file_metadata.get('name')}' ({file_metadata.get('filetype')})", flush=True)
                attachments.append(file_metadata)
            else:
                print(f"[SENSE] _enrich_slack_event_context: file metadata fetch failed for {file_id}", flush=True)
    elif file_ids:
        print(f"[SENSE] _enrich_slack_event_context: skipping file fetch — no bot token", flush=True)
    if attachments:
        metadata["attachments"] = _merge_attachments(metadata.get("attachments"), attachments)

    if not (event_data.get("content") or "").strip():
        synthetic_content = _message_preview_from_event({"metadata": metadata})
        if synthetic_content:
            event.content = synthetic_content
            event_data["content"] = synthetic_content

    if not metadata.get("context_messages"):
        fallback_message = _event_to_context_message({
            "source_id": message_ts,
            "actor_name": event_data.get("actor_name"),
            "content": event_data.get("content"),
            "metadata": metadata,
        })
        if fallback_message:
            metadata["context_messages"] = [fallback_message]

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
    best_score = 0.0
    candidates = result.all()
    print(f"[SENSE] _try_update_related_ko: {len(candidates)} candidate KO+event pairs from DB", flush=True)
    for ko, evt in candidates:
        evt_channel = (evt.metadata_ or {}).get("channel")
        if evt_channel == channel:
            score = _score_event_against_knowledge(ko, event_data)
            ko_title = getattr(ko, "title", "?")
            print(f"[SENSE] _try_update_related_ko: KO '{ko_title}' score={score:.3f} (threshold=0.08)", flush=True)
            if score > best_score:
                matched_ko = ko
                source_event = evt
                best_score = score

    # Temporal proximity fallback: when normal scoring fails because context
    # messages are missing, use time-based proximity for follow-up messages.
    if best_score < 0.08 and _looks_like_follow_up_message(event_data.get("content")):
        print(f"[SENSE] _try_update_related_ko: normal scoring failed, trying temporal fallback...", flush=True)
        for ko, evt in candidates:
            evt_channel = (evt.metadata_ or {}).get("channel")
            if evt_channel != channel:
                continue
            # Check if KO was created within the last 15 minutes
            try:
                ko_detected = datetime.fromisoformat(ko.detected_at) if isinstance(ko.detected_at, str) else ko.detected_at
                if ko_detected.tzinfo is None:
                    ko_detected = ko_detected.replace(tzinfo=timezone.utc)
                diff_seconds = (datetime.now(timezone.utc) - ko_detected).total_seconds()
            except (ValueError, TypeError, AttributeError):
                continue
            if diff_seconds > 900:  # 15 minutes
                continue
            fallback_score = 0.15 * (1.0 - diff_seconds / 900)
            ko_title = getattr(ko, "title", "?")
            print(f"[SENSE] _try_update_related_ko: temporal fallback KO '{ko_title}' age={diff_seconds:.0f}s score={fallback_score:.3f}", flush=True)
            if fallback_score > best_score:
                matched_ko = ko
                source_event = evt
                best_score = fallback_score

    if not matched_ko or not source_event or best_score < 0.08:
        print(f"[SENSE] _try_update_related_ko: no match (best_score={best_score:.3f})", flush=True)
        return None

    print(f"[SENSE] _try_update_related_ko: matched KO '{getattr(matched_ko, 'title', '?')}' with score={best_score:.3f}", flush=True)

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
            relevance=best_score,
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
            new_context_messages = await fetch_surrounding_messages(
                channel=channel,
                message_ts=source_ts,
                bot_token=settings.slack_bot_token,
            )
            if new_context_messages:
                current_metadata = dict(source_event.metadata_ or {})
                # Merge new messages with existing ones instead of replacing,
                # so previously captured context is preserved even if the
                # Slack API window has shifted.
                existing_context = list(current_metadata.get("context_messages") or [])
                existing_ts = {str(m.get("ts")) for m in existing_context}
                for msg in new_context_messages:
                    if str(msg.get("ts")) not in existing_ts:
                        existing_context.append(msg)
                existing_context.sort(key=lambda m: float(m.get("ts", 0)))
                current_metadata["context_messages"] = existing_context
                source_event.metadata_ = current_metadata
                flag_modified(source_event, "metadata_")

    _refresh_source_event_context(source_event, matched_ko, event_data)

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

    _update_knowledge_detail_with_linked_event(matched_ko, event_data, "context")

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
    from app.sense.knowledge_types import canonicalize_knowledge_type

    # Only look at decision KOs from the past 7 days
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_kos = await get_recent_knowledge(db, project_id=event_data.get("project_id"), since=since)
    decision_kos = [ko for ko in recent_kos if canonicalize_knowledge_type(ko.type) == "decision"]

    if not decision_kos:
        return None

    # Generate embedding for the GitHub event content
    content = event_data.get("content", "")
    event_embedding_bytes = await generate_embedding(content) if content else None
    event_vector = bytes_to_vector(event_embedding_bytes) if event_embedding_bytes else []

    # Get actors from the event — use BOTH email and name for cross-platform matching.
    # Slack captures display names (not emails), GitHub captures login names.
    # Using both ensures the actor overlap score is nonzero when the same person
    # appears as "alice" (GitHub) and "Alice" (Slack display name).
    actors_event = set()
    if event_data.get("actor_email"):
        actors_event.add(event_data["actor_email"].lower())
    if event_data.get("actor_name"):
        actors_event.add(event_data["actor_name"].lower())

    best_score = 0.0
    best_ko = None

    for ko in decision_kos:
        ko_vector = bytes_to_vector(ko.embedding) if ko.embedding else []
        actors_ko = set()
        for p in (ko.participants or []):
            if p.get("email"):
                actors_ko.add(p["email"].lower())
            if p.get("name"):
                actors_ko.add(p["name"].lower())
        lexical_score = _score_event_against_knowledge(ko, event_data)

        # Use a generous time window (7 days) — GitHub commits can happen days after a decision
        score = weighted_correlation_score(
            event_vector, ko_vector,
            actors_event, actors_ko,
            time_diff_seconds=0,  # Don't penalise time; decisions precede implementation
            content_a=content,
            content_b=f"{ko.title or ''} {ko.summary or ''}",
            window_hours=168,  # 7 days
        )
        score = max(score, lexical_score)

        if score > best_score:
            best_score = score
            best_ko = ko

    # Link threshold — lower than merge threshold to catch related commits.
    # Lowered from 0.75 to 0.55 multiplier because GitHub evidence should
    # link more easily than KO merges.
    LINK_THRESHOLD = MERGE_THRESHOLD * 0.55  # ~0.33

    if best_ko and best_score >= LINK_THRESHOLD:
        # Link this event as evidence to the existing decision KO
        from sqlalchemy import select
        link_added = False
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
            link_added = True

        detail_updated = _update_knowledge_detail_with_linked_event(
            best_ko,
            event_data,
            "github_evidence",
        )
        if link_added or detail_updated:
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

                # Get actors — use both emails and names for cross-platform matching
                actors_a = set()
                for p in (ko_a.participants or []):
                    if p.get("email"):
                        actors_a.add(p["email"].lower())
                    if p.get("name"):
                        actors_a.add(p["name"].lower())
                actors_b = set()
                for p in (ko_b.participants or []):
                    if p.get("email"):
                        actors_b.add(p["email"].lower())
                    if p.get("name"):
                        actors_b.add(p["name"].lower())

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


# ---------------------------------------------------------------------------
# Gmail polling
# ---------------------------------------------------------------------------

# Track the last poll time so we only fetch new messages
_gmail_last_poll_iso: str | None = None


async def poll_gmail_messages() -> dict:
    """Poll Gmail for recent messages and process them through the pipeline.

    Uses the Gmail MCP server to search for and read messages. This function
    is called periodically by APScheduler when gmail_poll_enabled is True.
    """
    global _gmail_last_poll_iso

    from app.config import get_settings
    settings = get_settings()

    if not settings.gmail_poll_enabled:
        return {"polled": 0, "processed": 0, "skipped": "disabled"}

    # Import here to avoid circular imports
    from app.sense.integrations.gmail import parse_gmail_event

    # Determine search window
    if _gmail_last_poll_iso is None:
        # First poll: look back 1 hour
        since = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        since = datetime.fromisoformat(_gmail_last_poll_iso)

    # Update last poll time
    _gmail_last_poll_iso = datetime.now(timezone.utc).isoformat()

    # Search for recent messages
    # Note: This function is designed to be called by an MCP-aware controller.
    # In production, the Gmail MCP tools are called from outside and results
    # are passed to process_gmail_batch(). This function provides the interface.
    logger.info(f"[gmail] Polling for messages since {since.isoformat()}")

    return {"polled": 0, "processed": 0, "since": since.isoformat()}


async def process_gmail_batch(messages: list[dict], project_id: str | None = None) -> dict:
    """Process a batch of Gmail messages through the pipeline.

    Called with pre-fetched message data (from MCP or API). Each message
    is parsed, stored as an event, and run through the extraction pipeline.
    """
    from app.sense.integrations.gmail import parse_gmail_event

    processed = 0
    skipped = 0

    for message in messages:
        event_data = parse_gmail_event(message)
        if event_data is None:
            skipped += 1
            continue

        if project_id:
            event_data["project_id"] = project_id

        try:
            result = await process_event_async(event_data)
            if result:
                processed += 1
                logger.info(
                    f"[gmail] Processed message {event_data['source_id']}: "
                    f"ko_created={result.get('ko_created', False)}"
                )
        except Exception as e:
            logger.error(f"[gmail] Failed to process message {event_data.get('source_id')}: {e}")
            skipped += 1

    logger.info(f"[gmail] Batch complete: {processed} processed, {skipped} skipped")
    return {"processed": processed, "skipped": skipped}


async def _enrich_gmail_event_context(event, event_data: dict) -> dict:
    """Best-effort Gmail enrichment: fetch the full email thread as context.

    Populates event.metadata_ with context_messages from the email thread,
    using the same format as Slack context messages.
    """
    metadata = dict(event.metadata_ or event_data.get("metadata") or {})
    thread_id = metadata.get("thread_id")

    if not thread_id:
        logger.info("[gmail] No thread_id — skipping context enrichment")
        return event_data

    # Thread messages are expected to be pre-fetched and passed in metadata
    # by the MCP controller, since we can't call MCP tools from within
    # the backend process directly.
    thread_messages = metadata.get("thread_messages") or []
    if not thread_messages:
        logger.info(f"[gmail] No thread_messages for thread {thread_id}")
        return event_data

    # Convert thread messages to context_messages format
    context_messages = []
    for msg in thread_messages:
        sender = msg.get("from") or msg.get("sender_name") or "Unknown"
        # Extract just the name if it's a full "Name <email>" format
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')
        text = msg.get("snippet") or msg.get("body") or msg.get("subject") or ""
        ts = msg.get("id") or msg.get("internalDate") or ""
        context_messages.append({
            "user_name": sender,
            "text": text.strip(),
            "ts": str(ts),
        })

    metadata["context_messages"] = context_messages
    event.metadata_ = metadata
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(event, "metadata_")

    logger.info(f"[gmail] Enriched with {len(context_messages)} thread messages")
    return event_data
