"""Slack webhook receiver and event parsing."""
import hashlib
import hmac
from datetime import datetime, timezone


def verify_slack_signature(
    body: bytes, timestamp: str, signature: str, signing_secret: str
) -> bool:
    """Verify Slack request signature."""
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    expected = "v0=" + hmac.new(
        signing_secret.encode(), sig_basestring, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_file_ids(event: dict) -> list[str]:
    """Collect Slack file IDs from both message and file_shared payload shapes."""
    file_ids = []

    for file_data in event.get("files") or []:
        file_id = str(file_data.get("id") or "").strip()
        if file_id:
            file_ids.append(file_id)

    inline_file = event.get("file") or {}
    inline_file_id = str(inline_file.get("id") or "").strip()
    if inline_file_id:
        file_ids.append(inline_file_id)

    top_level_file_id = str(event.get("file_id") or "").strip()
    if top_level_file_id:
        file_ids.append(top_level_file_id)

    deduped = []
    for file_id in file_ids:
        if file_id not in deduped:
            deduped.append(file_id)
    return deduped


def _parse_occurred_at(raw_ts) -> str:
    """Convert a Slack timestamp or event_time value into ISO-8601."""
    try:
        ts_float = float(raw_ts or 0)
        return datetime.fromtimestamp(ts_float, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return datetime.now(timezone.utc).isoformat()


def parse_slack_event(payload: dict) -> dict:
    """Parse a Slack event callback into a normalized event dict."""
    event = payload.get("event", {})
    event_type = event.get("type", "unknown")
    file_ids = _extract_file_ids(event)

    # Handle different event types
    if event_type == "reaction_added":
        reaction = event.get("reaction", "")
        item = event.get("item", {})
        source_id = f"{item.get('ts', '')}_{reaction}"
        content = f"Reaction :{reaction}: added"
        occurred_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "channel": item.get("channel"),
            "reaction": reaction,
            "item_ts": item.get("ts"),
        }
    else:
        # message, message_changed, file_shared, etc.
        raw_ts = event.get("ts") or event.get("event_ts") or payload.get("event_time")
        source_id = str(raw_ts or (f"file_shared_{file_ids[0]}" if file_ids else ""))
        content = event.get("text", "")
        if not content and event_type == "file_shared":
            content = f"Slack file shared: {file_ids[0] if file_ids else 'file'}"
        occurred_at = _parse_occurred_at(raw_ts)
        metadata = {
            "channel": event.get("channel") or event.get("channel_id"),
            "thread_ts": event.get("thread_ts"),
            "file_ids": file_ids,
        }

    result = {
        "source": "slack",
        "source_id": source_id,
        "event_type": event_type,
        "actor_email": None,  # Resolved via Slack API in production
        "actor_name": event.get("user") or event.get("user_id"),
        "content": content,
        "metadata": metadata,
        "raw_payload": payload,
        "occurred_at": occurred_at,
    }
    print(
        f"[SENSE] parse_slack_event: type={event_type}, "
        f"file_ids={file_ids}, "
        f"has_files_key={'files' in event}, "
        f"has_file_key={'file' in event}, "
        f"content_preview=\"{(content or '')[:60]}\"",
        flush=True,
    )
    return result
