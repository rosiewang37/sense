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


def parse_slack_event(payload: dict) -> dict:
    """Parse a Slack event callback into a normalized event dict."""
    event = payload.get("event", {})
    event_type = event.get("type", "unknown")

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
        source_id = event.get("ts", "")
        content = event.get("text", "")
        files = event.get("files") or []
        try:
            ts_float = float(event.get("ts", 0))
            occurred_at = datetime.fromtimestamp(ts_float, tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            occurred_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "channel": event.get("channel"),
            "thread_ts": event.get("thread_ts"),
            "file_ids": [str(file_data.get("id") or "") for file_data in files if file_data.get("id")],
        }

    return {
        "source": "slack",
        "source_id": source_id,
        "event_type": event_type,
        "actor_email": None,  # Resolved via Slack API in production
        "actor_name": event.get("user"),
        "content": content,
        "metadata": metadata,
        "raw_payload": payload,
        "occurred_at": occurred_at,
    }
