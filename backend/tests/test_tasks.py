"""Task-pipeline tests for context linking and local fallback matching."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event, KnowledgeEvent, KnowledgeObject
from app.backboard.store import store_event, store_knowledge_object
from app.sense.tasks import (
    _find_and_link_to_existing_decision,
    _try_update_related_ko,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed_slack_decision(
    db_session: AsyncSession,
    *,
    channel: str,
    source_id: str,
    title: str,
    summary: str,
    statement: str,
    source_content: str,
    context_messages: list[dict],
) -> tuple[Event, KnowledgeObject]:
    source_event = await store_event(
        db_session,
        {
            "source": "slack",
            "source_id": source_id,
            "event_type": "message",
            "actor_email": None,
            "actor_name": "Alice",
            "content": source_content,
            "metadata": {
                "channel": channel,
                "context_messages": context_messages,
            },
            "raw_payload": {},
            "occurred_at": _now_iso(),
            "project_id": None,
        },
    )

    ko = await store_knowledge_object(
        db_session,
        {
            "type": "decision",
            "title": title,
            "summary": summary,
            "detail": {
                "statement": statement,
                "rationale": None,
                "alternatives_considered": [],
                "expected_follow_ups": [],
            },
            "participants": [{"email": "", "name": "Alice", "role": "author"}],
            "tags": [],
            "confidence": 0.9,
            "occurred_at": _now_iso(),
            "project_id": None,
        },
    )

    db_session.add(
        KnowledgeEvent(
            knowledge_id=str(ko.id),
            event_id=str(source_event.id),
            relevance=1.0,
            relationship_="source_event",
        )
    )
    await db_session.flush()
    return source_event, ko


@pytest.mark.asyncio
async def test_follow_up_context_is_linked_only_when_relevant(db_session: AsyncSession):
    """Follow-up actions should extend the existing KO, but unrelated chatter should not."""
    context_messages = [
        {
            "user_name": "Alice",
            "text": "Docker Desktop licensing is getting expensive now that we have 60 engineers.",
            "ts": "99.0",
        },
        {
            "user_name": "Bob",
            "text": "Podman is drop-in compatible and doesn't need a daemon or a paid license.",
            "ts": "99.5",
        },
        {
            "user_name": "Alice",
            "text": "We've decided to standardize on Podman instead of Docker Desktop for local development.",
            "ts": "100.0",
        },
    ]
    source_event, ko = await _seed_slack_decision(
        db_session,
        channel="C-PODMAN",
        source_id="100.0",
        title="Standardize on Podman for local development",
        summary="The team chose Podman over Docker Desktop for local development.",
        statement="Use Podman instead of Docker Desktop for local development.",
        source_content=context_messages[-1]["text"],
        context_messages=context_messages,
    )

    follow_up_event_data = {
        "source": "slack",
        "source_id": "101.0",
        "event_type": "message",
        "actor_email": None,
        "actor_name": "Bob",
        "content": "I'll update the onboarding docs and dev setup scripts by end of week.",
        "metadata": {
            "channel": "C-PODMAN",
            "context_messages": context_messages
            + [
                {
                    "user_name": "Bob",
                    "text": "I'll update the onboarding docs and dev setup scripts by end of week.",
                    "ts": "101.0",
                }
            ],
        },
        "raw_payload": {},
        "occurred_at": _now_iso(),
        "project_id": None,
    }
    follow_up_event = await store_event(db_session, follow_up_event_data)

    linked_ko_id = await _try_update_related_ko(
        db_session,
        str(follow_up_event.id),
        follow_up_event_data,
    )

    assert linked_ko_id == str(ko.id)

    refreshed_source_event = await db_session.get(Event, source_event.id)
    context_timestamps = {
        msg["ts"] for msg in (refreshed_source_event.metadata_ or {}).get("context_messages", [])
    }
    assert "101.0" in context_timestamps

    refreshed_ko = await db_session.get(KnowledgeObject, ko.id)
    related_context = (refreshed_ko.detail or {}).get("related_context") or []
    assert any(item.get("relationship") == "context" for item in related_context)

    context_link = await db_session.execute(
        select(KnowledgeEvent).where(
            KnowledgeEvent.knowledge_id == str(ko.id),
            KnowledgeEvent.event_id == str(follow_up_event.id),
            KnowledgeEvent.relationship_ == "context",
        )
    )
    assert context_link.scalar_one_or_none() is not None

    unrelated_event_data = {
        "source": "slack",
        "source_id": "102.0",
        "event_type": "message",
        "actor_email": None,
        "actor_name": "Carol",
        "content": "Thanks everyone.",
        "metadata": {
            "channel": "C-PODMAN",
            "context_messages": context_messages
            + [
                {
                    "user_name": "Carol",
                    "text": "Thanks everyone.",
                    "ts": "102.0",
                }
            ],
        },
        "raw_payload": {},
        "occurred_at": _now_iso(),
        "project_id": None,
    }
    unrelated_event = await store_event(db_session, unrelated_event_data)

    assert (
        await _try_update_related_ko(db_session, str(unrelated_event.id), unrelated_event_data)
        is None
    )


@pytest.mark.asyncio
async def test_file_upload_context_merges_into_existing_decision(db_session: AsyncSession):
    """A later file upload should be linked and its attachment metadata should surface on the KO."""
    source_event, ko = await _seed_slack_decision(
        db_session,
        channel="C-RUNBOOK",
        source_id="200.0",
        title="Adopt the incident runbook template",
        summary="The team adopted a standard runbook template for production incidents.",
        statement="Use the attached runbook template for production incidents.",
        source_content="We've decided to adopt the attached runbook template for all production incident responses.",
        context_messages=[
            {
                "user_name": "Alice",
                "text": "We've decided to adopt the attached runbook template for all production incident responses.",
                "ts": "200.0",
            }
        ],
    )

    file_event_data = {
        "source": "slack",
        "source_id": "201.0",
        "event_type": "file_shared",
        "actor_email": None,
        "actor_name": "Alice",
        "content": "",
        "metadata": {
            "channel": "C-RUNBOOK",
            "attachments": [
                {
                    "id": "F123",
                    "name": "incident_runbook_template.pdf",
                    "filetype": "pdf",
                }
            ],
        },
        "raw_payload": {},
        "occurred_at": _now_iso(),
        "project_id": None,
    }
    file_event = await store_event(db_session, file_event_data)

    linked_ko_id = await _try_update_related_ko(
        db_session,
        str(file_event.id),
        file_event_data,
    )

    assert linked_ko_id == str(ko.id)

    refreshed_source_event = await db_session.get(Event, source_event.id)
    attachments = (refreshed_source_event.metadata_ or {}).get("attachments") or []
    assert any(attachment.get("name") == "incident_runbook_template.pdf" for attachment in attachments)

    context_messages = (refreshed_source_event.metadata_ or {}).get("context_messages") or []
    assert any(message.get("ts") == "201.0" for message in context_messages)


@pytest.mark.asyncio
async def test_github_commit_links_without_embeddings(db_session: AsyncSession, monkeypatch):
    """Local lexical matching should still link a commit even when embeddings are unavailable."""
    ko = await store_knowledge_object(
        db_session,
        {
            "type": "decision",
            "title": "Replace NGINX with Caddy reverse proxy",
            "summary": "The team chose Caddy over NGINX to get automatic TLS.",
            "detail": {
                "statement": "Replace NGINX with Caddy as the reverse proxy.",
                "rationale": "Automatic TLS and simpler operations.",
                "alternatives_considered": ["Keep NGINX"],
                "expected_follow_ups": ["Update deployment manifests"],
            },
            "participants": [{"email": "alice@example.com", "name": "Alice", "role": "author"}],
            "tags": ["reverse-proxy", "tls"],
            "confidence": 0.88,
            "occurred_at": _now_iso(),
            "project_id": None,
        },
    )
    await db_session.flush()

    async def fake_generate_embedding(_: str):
        return None

    monkeypatch.setattr("app.backboard.embeddings.generate_embedding", fake_generate_embedding)

    event_data = {
        "source": "github",
        "source_id": "commit-caddy-1",
        "event_type": "push",
        "actor_email": "alice@example.com",
        "actor_name": "Alice",
        "content": "Replace NGINX with Caddy reverse proxy for automatic TLS",
        "metadata": {
            "repo": "org/repo",
            "ref": "refs/heads/main",
        },
        "raw_payload": {},
        "occurred_at": _now_iso(),
        "project_id": None,
    }
    event = await store_event(db_session, event_data)

    linked_ko_id = await _find_and_link_to_existing_decision(
        db_session,
        str(event.id),
        event_data,
    )

    assert linked_ko_id == str(ko.id)

    evidence_link = await db_session.execute(
        select(KnowledgeEvent).where(
            KnowledgeEvent.knowledge_id == str(ko.id),
            KnowledgeEvent.event_id == str(event.id),
            KnowledgeEvent.relationship_ == "github_evidence",
        )
    )
    assert evidence_link.scalar_one_or_none() is not None

    refreshed_ko = await db_session.get(KnowledgeObject, ko.id)
    related_context = (refreshed_ko.detail or {}).get("related_context") or []
    assert any(item.get("relationship") == "github_evidence" for item in related_context)


@pytest.mark.asyncio
async def test_github_commit_links_by_actor_name(db_session: AsyncSession, monkeypatch):
    """Actor name matching (not just email) should allow GitHub events to link to Slack decisions."""
    # Use a unique project_id so we don't match KOs from other tests
    project_id = "proj-actor-name-test"
    ko = await store_knowledge_object(
        db_session,
        {
            "type": "decision",
            "title": "Switch logging framework to structlog",
            "summary": "Team decided to adopt structlog for structured logging.",
            "detail": {
                "statement": "Use structlog instead of stdlib logging.",
                "rationale": "Better JSON output for observability.",
                "alternatives_considered": ["loguru"],
                "expected_follow_ups": ["Update logger config"],
            },
            # Slack-sourced participant: name only, no email
            "participants": [{"email": "", "name": "Alice", "role": "author"}],
            "tags": ["logging", "structlog"],
            "confidence": 0.85,
            "occurred_at": _now_iso(),
            "project_id": project_id,
        },
    )
    await db_session.flush()

    async def fake_generate_embedding(_: str):
        return None

    monkeypatch.setattr("app.backboard.embeddings.generate_embedding", fake_generate_embedding)

    event_data = {
        "source": "github",
        "source_id": "commit-structlog-1",
        "event_type": "push",
        # GitHub actor: name matches Slack participant name (case-insensitive)
        "actor_email": "",
        "actor_name": "alice",
        "content": "Switch logging framework to structlog for structured logging",
        "metadata": {"repo": "org/repo", "ref": "refs/heads/main"},
        "raw_payload": {},
        "occurred_at": _now_iso(),
        "project_id": project_id,
    }
    event = await store_event(db_session, event_data)

    linked_ko_id = await _find_and_link_to_existing_decision(
        db_session, str(event.id), event_data,
    )

    assert linked_ko_id == str(ko.id)


@pytest.mark.asyncio
async def test_proximity_keeps_short_agreement_messages(db_session: AsyncSession):
    """Short agreement messages near the trigger should be kept even with zero keyword overlap."""
    from app.sense.tasks import _filter_context_messages_for_knowledge

    # Create a KO about a technical decision
    ko = await store_knowledge_object(
        db_session,
        {
            "type": "decision",
            "title": "Migrate database to PostgreSQL 16",
            "summary": "Team chose PostgreSQL 16 for the new backend.",
            "detail": {"statement": "Use PostgreSQL 16."},
            "participants": [],
            "tags": ["postgresql", "database"],
            "confidence": 0.9,
            "occurred_at": _now_iso(),
            "project_id": None,
        },
    )
    await db_session.flush()

    context_messages = [
        {"user_name": "Bob", "text": "What about MySQL?", "ts": "98.0"},
        {"user_name": "Alice", "text": "We've decided to migrate to PostgreSQL 16", "ts": "100.0"},
        {"user_name": "Carol", "text": "Sounds good, let's do it", "ts": "101.0"},
        {"user_name": "Dave", "text": "+1", "ts": "102.0"},
        {"user_name": "Eve", "text": "Anyone want lunch?", "ts": "200.0"},
    ]

    filtered = _filter_context_messages_for_knowledge(
        context_messages, ko, trigger_ts="100.0",
    )

    kept_ts = {msg["ts"] for msg in filtered}
    # Trigger always kept
    assert "100.0" in kept_ts
    # Short agreements within 2 positions of trigger should be kept (proximity)
    assert "101.0" in kept_ts
    assert "102.0" in kept_ts
    # Preceding message within 2 positions should also be kept
    assert "98.0" in kept_ts
    # Distant unrelated message should be filtered out
    assert "200.0" not in kept_ts


@pytest.mark.asyncio
async def test_context_merge_preserves_existing_messages(db_session: AsyncSession):
    """Re-enrichment of source events should merge context, not replace it."""
    source_event, ko = await _seed_slack_decision(
        db_session,
        channel="C-MERGE",
        source_id="300.0",
        title="Use Redis for caching",
        summary="Team decided to use Redis for application caching.",
        statement="Use Redis for caching.",
        source_content="We've decided to use Redis for caching.",
        context_messages=[
            {"user_name": "Alice", "text": "We've decided to use Redis for caching.", "ts": "300.0"},
            {"user_name": "Bob", "text": "I'll set up the Redis cluster.", "ts": "301.0"},
        ],
    )

    # Simulate a follow-up that triggers re-enrichment
    follow_up_data = {
        "source": "slack",
        "source_id": "302.0",
        "event_type": "message",
        "actor_email": None,
        "actor_name": "Carol",
        "content": "I'll update the caching layer documentation.",
        "metadata": {
            "channel": "C-MERGE",
            "context_messages": [
                {"user_name": "Alice", "text": "We've decided to use Redis for caching.", "ts": "300.0"},
                {"user_name": "Carol", "text": "I'll update the caching layer documentation.", "ts": "302.0"},
            ],
        },
        "raw_payload": {},
        "occurred_at": _now_iso(),
        "project_id": None,
    }
    follow_up_event = await store_event(db_session, follow_up_data)

    linked_ko_id = await _try_update_related_ko(
        db_session, str(follow_up_event.id), follow_up_data,
    )

    assert linked_ko_id == str(ko.id)

    # Verify the source event's context_messages were MERGED, not replaced
    refreshed_source = await db_session.get(Event, source_event.id)
    context_ts = {
        msg["ts"] for msg in (refreshed_source.metadata_ or {}).get("context_messages", [])
    }
    # Original message should still be there
    assert "300.0" in context_ts
    # Bob's original follow-up should be preserved (not lost by re-fetch)
    assert "301.0" in context_ts
    # New follow-up should be added
    assert "302.0" in context_ts
