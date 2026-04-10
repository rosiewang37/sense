"""Tests for Gmail integration: parsing, dedup, and pipeline processing."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backboard.models import Event
from app.backboard.store import store_event
from app.sense.integrations.gmail import parse_gmail_event, _extract_sender, _strip_html


def test_parse_gmail_event_basic():
    """A well-formed Gmail message should produce a valid event dict."""
    message = {
        "id": "msg-001",
        "threadId": "thread-001",
        "from": "Alice Smith <alice@example.com>",
        "to": "bob@example.com, carol@example.com",
        "cc": "dave@example.com",
        "subject": "We've decided to use PostgreSQL 16",
        "body": "After evaluating MySQL and PostgreSQL, we're going with PG 16.",
        "date": "2026-04-10T10:00:00Z",
    }

    result = parse_gmail_event(message)

    assert result is not None
    assert result["source"] == "gmail"
    assert result["source_id"] == "msg-001"
    assert result["event_type"] == "email"
    assert result["actor_email"] == "alice@example.com"
    assert result["actor_name"] == "Alice Smith"
    assert "PostgreSQL 16" in result["content"]
    assert result["metadata"]["thread_id"] == "thread-001"
    assert result["metadata"]["subject"] == "We've decided to use PostgreSQL 16"
    assert "bob@example.com" in result["metadata"]["to"]
    assert "dave@example.com" in result["metadata"]["cc"]


def test_parse_gmail_event_with_headers():
    """Messages with nested headers dict should still parse correctly."""
    message = {
        "id": "msg-002",
        "threadId": "thread-002",
        "headers": [
            {"name": "From", "value": "Bob <bob@example.com>"},
            {"name": "Subject", "value": "Re: Architecture review"},
            {"name": "To", "value": "team@example.com"},
        ],
        "snippet": "I approve the proposed microservices split.",
        "internalDate": "1712750400000",  # epoch milliseconds
    }

    result = parse_gmail_event(message)

    assert result is not None
    assert result["actor_email"] == "bob@example.com"
    assert result["actor_name"] == "Bob"
    assert "Architecture review" in result["content"]
    assert "microservices split" in result["content"]


def test_parse_gmail_event_html_body():
    """HTML bodies should be stripped to plain text."""
    message = {
        "id": "msg-003",
        "subject": "Decision",
        "body": "<div><p>We've <b>decided</b> to use <a href='#'>Redis</a> for caching.</p></div>",
    }

    result = parse_gmail_event(message)

    assert result is not None
    assert "<div>" not in result["content"]
    assert "<b>" not in result["content"]
    assert "decided" in result["content"]
    assert "Redis" in result["content"]


def test_parse_gmail_event_empty_content():
    """Messages with no subject or body should return None."""
    message = {"id": "msg-empty", "subject": "", "body": ""}
    assert parse_gmail_event(message) is None


def test_parse_gmail_event_no_id():
    """Messages without an ID should return None."""
    message = {"subject": "Something", "body": "content"}
    assert parse_gmail_event(message) is None


def test_extract_sender_full():
    """Parse 'Name <email>' format."""
    name, email = _extract_sender("Alice Smith <alice@example.com>")
    assert name == "Alice Smith"
    assert email == "alice@example.com"


def test_extract_sender_bare_email():
    """Parse bare email address."""
    name, email = _extract_sender("alice@example.com")
    assert name == ""
    assert email == "alice@example.com"


def test_extract_sender_name_only():
    """Parse name without email."""
    name, email = _extract_sender("Alice")
    assert name == "Alice"
    assert email == ""


def test_strip_html():
    """HTML tags should be removed, whitespace collapsed."""
    html = "<p>Hello <b>world</b>!</p>  <br/>  Goodbye."
    assert _strip_html(html) == "Hello world ! Goodbye."


@pytest.mark.asyncio
async def test_gmail_event_dedup(db_session: AsyncSession):
    """Gmail events should dedup by source+source_id like all other sources."""
    event_data = {
        "source": "gmail",
        "source_id": "msg-dedup-001",
        "event_type": "email",
        "actor_email": "alice@example.com",
        "actor_name": "Alice",
        "content": "Test email content",
        "metadata": {"thread_id": "t-001", "subject": "Test"},
        "raw_payload": {},
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "project_id": None,
    }

    event1 = await store_event(db_session, event_data)
    event2 = await store_event(db_session, event_data)

    # Should return the same event (dedup)
    assert str(event1.id) == str(event2.id)

    # Should only have one event in DB
    result = await db_session.execute(
        select(Event).where(Event.source == "gmail", Event.source_id == "msg-dedup-001")
    )
    events = result.scalars().all()
    assert len(events) == 1
