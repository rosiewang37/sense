"""Gmail message parsing for the Sense pipeline.

Normalizes Gmail messages into the standard event dict format.
Messages are fetched via MCP polling (not webhooks).
"""
import re
from datetime import datetime, timezone

# Simple HTML tag stripper — good enough for email body extraction
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = _HTML_TAG_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_sender(from_header: str) -> tuple[str, str]:
    """Extract (name, email) from a 'From' header like 'Alice <alice@example.com>'."""
    match = re.match(r"^(.+?)\s*<([^>]+)>$", from_header.strip())
    if match:
        name = match.group(1).strip().strip('"').strip("'")
        email = match.group(2).strip()
        return name, email
    # Bare email address
    if "@" in from_header:
        return "", from_header.strip()
    return from_header.strip(), ""


def _parse_date(date_str: str | None) -> str:
    """Best-effort parse of email date to ISO-8601."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    # Try epoch milliseconds (some APIs return this)
    try:
        ts = int(date_str) / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        pass
    # Return as-is if already ISO-ish, or fallback to now
    try:
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return date_str
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def parse_gmail_event(message: dict) -> dict | None:
    """Parse a Gmail message dict into a normalized event dict.

    Expects a dict with at least:
    - id: Gmail message ID
    - subject or headers with Subject
    - body or snippet: message content
    - from or headers with From: sender info
    - date or internalDate: timestamp

    Returns None if the message can't be parsed into a usable event.
    """
    msg_id = str(message.get("id") or "").strip()
    if not msg_id:
        return None

    # Extract headers (some APIs flatten them, some nest them)
    headers = {}
    for h in message.get("headers") or []:
        if isinstance(h, dict):
            headers[h.get("name", "").lower()] = h.get("value", "")

    # Subject
    subject = (
        message.get("subject")
        or headers.get("subject")
        or ""
    ).strip()

    # Body / content
    body = message.get("body") or message.get("snippet") or ""
    if isinstance(body, dict):
        # Gmail API nests body content
        body = body.get("data") or body.get("text") or ""
    if "<" in body and ">" in body:
        body = _strip_html(body)
    body = body.strip()

    # Build content: subject + body
    content_parts = []
    if subject:
        content_parts.append(subject)
    if body and body != subject:
        content_parts.append(body)
    content = "\n\n".join(content_parts)

    if not content:
        return None

    # Sender
    from_header = message.get("from") or headers.get("from") or ""
    sender_name, sender_email = _extract_sender(from_header)

    # Recipients
    to_header = message.get("to") or headers.get("to") or ""
    cc_header = message.get("cc") or headers.get("cc") or ""
    to_list = [addr.strip() for addr in to_header.split(",") if addr.strip()] if to_header else []
    cc_list = [addr.strip() for addr in cc_header.split(",") if addr.strip()] if cc_header else []

    # Thread and labels
    thread_id = message.get("threadId") or message.get("thread_id") or ""
    labels = message.get("labelIds") or message.get("labels") or []

    # Date
    date_str = (
        message.get("date")
        or message.get("internalDate")
        or headers.get("date")
        or ""
    )
    occurred_at = _parse_date(date_str)

    return {
        "source": "gmail",
        "source_id": msg_id,
        "event_type": "email",
        "actor_email": sender_email,
        "actor_name": sender_name or sender_email,
        "content": content,
        "metadata": {
            "thread_id": str(thread_id),
            "subject": subject,
            "to": to_list,
            "cc": cc_list,
            "labels": labels if isinstance(labels, list) else [],
            "sender_email": sender_email,
            "sender_name": sender_name,
        },
        "raw_payload": message,
        "occurred_at": occurred_at,
    }
