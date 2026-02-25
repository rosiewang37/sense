"""Phase 2 tests: Webhook parsing and signature verification.

Tests:
- Slack message parsing → Event object
- Slack reaction parsing → Event object
- GitHub push parsing → Event object
- GitHub PR parsing → Event object
- Slack signature verification
- GitHub secret verification
"""
import hashlib
import hmac
import json
import time

import pytest
from app.sense.integrations.slack import parse_slack_event, verify_slack_signature
from app.sense.integrations.github import parse_github_event, verify_github_signature


# --- Slack Event Parsing ---

SLACK_MESSAGE_PAYLOAD = {
    "type": "event_callback",
    "event": {
        "type": "message",
        "user": "U12345",
        "text": "We've decided to switch to MotorCo as our primary supplier",
        "channel": "C98765",
        "ts": "1708444320.000100",
        "thread_ts": None,
    },
    "team_id": "T11111",
}

SLACK_REACTION_PAYLOAD = {
    "type": "event_callback",
    "event": {
        "type": "reaction_added",
        "user": "U12345",
        "reaction": "white_check_mark",
        "item": {
            "type": "message",
            "channel": "C98765",
            "ts": "1708444320.000100",
        },
    },
    "team_id": "T11111",
}


def test_slack_message_parsing():
    """Raw Slack message payload → normalized Event dict."""
    event = parse_slack_event(SLACK_MESSAGE_PAYLOAD)
    assert event["source"] == "slack"
    assert event["source_id"] == "1708444320.000100"
    assert event["event_type"] == "message"
    assert "MotorCo" in event["content"]
    assert event["metadata"]["channel"] == "C98765"


def test_slack_reaction_parsing():
    """Reaction payload → normalized Event dict."""
    event = parse_slack_event(SLACK_REACTION_PAYLOAD)
    assert event["source"] == "slack"
    assert event["event_type"] == "reaction_added"
    assert "white_check_mark" in event["content"]


# --- GitHub Event Parsing ---

GITHUB_PUSH_PAYLOAD = {
    "ref": "refs/heads/main",
    "commits": [
        {
            "id": "abc123def456",
            "message": "Update BOM with MotorCo parts",
            "author": {"email": "alice@company.com", "name": "Alice"},
            "timestamp": "2026-02-20T15:00:00Z",
            "url": "https://github.com/org/repo/commit/abc123def456",
        }
    ],
    "repository": {"full_name": "org/repo"},
    "sender": {"login": "alice"},
}

GITHUB_PR_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 42,
        "title": "Switch motor supplier to MotorCo",
        "body": "Updates BOM and procurement docs for the MotorCo transition.",
        "html_url": "https://github.com/org/repo/pull/42",
        "user": {"login": "bob"},
        "created_at": "2026-02-20T16:00:00Z",
        "merged": False,
    },
    "repository": {"full_name": "org/repo"},
    "sender": {"login": "bob"},
}


def test_github_push_parsing():
    """Push payload → list of normalized Event dicts (one per commit)."""
    events = parse_github_event("push", GITHUB_PUSH_PAYLOAD)
    assert len(events) == 1
    event = events[0]
    assert event["source"] == "github"
    assert event["source_id"] == "abc123def456"
    assert event["event_type"] == "push"
    assert "MotorCo" in event["content"]
    assert event["actor_email"] == "alice@company.com"


def test_github_pr_parsing():
    """PR payload → normalized Event dict."""
    events = parse_github_event("pull_request", GITHUB_PR_PAYLOAD)
    assert len(events) == 1
    event = events[0]
    assert event["source"] == "github"
    assert event["event_type"] == "pull_request"
    assert "MotorCo" in event["content"]
    assert event["metadata"]["action"] == "opened"
    assert event["metadata"]["pr_number"] == 42


# --- Signature Verification ---

def test_slack_signature_verification():
    """Valid Slack signature passes; invalid is rejected."""
    signing_secret = "test_signing_secret"
    timestamp = str(int(time.time()))
    body = json.dumps(SLACK_MESSAGE_PAYLOAD).encode()
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    expected_sig = "v0=" + hmac.new(
        signing_secret.encode(), sig_basestring, hashlib.sha256
    ).hexdigest()

    # Valid
    assert verify_slack_signature(body, timestamp, expected_sig, signing_secret) is True

    # Invalid
    assert verify_slack_signature(body, timestamp, "v0=invalid", signing_secret) is False


def test_github_secret_verification():
    """Valid GitHub webhook secret passes; invalid is rejected."""
    secret = "test_webhook_secret"
    body = json.dumps(GITHUB_PUSH_PAYLOAD).encode()
    expected_sig = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()

    # Valid
    assert verify_github_signature(body, expected_sig, secret) is True

    # Invalid
    assert verify_github_signature(body, "sha256=invalid", secret) is False
