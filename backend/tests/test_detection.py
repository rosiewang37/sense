"""Phase 3 tests: Knowledge extraction pipeline (TDD-critical).

Tests:
- Pre-filter catches decision, approval, change language
- Pre-filter rejects casual chat
- Classification response parsing (valid + malformed JSON)
- Extraction response parsing (decision, follow-ups, missing fields)
- Full pipeline: event in → KO out, noise filtered
"""
import json
import pytest
from app.sense.detection import (
    pre_filter,
    parse_classification_response,
    parse_extraction_response,
    run_extraction_pipeline,
)


# --- Pre-filter ---

def test_prefilter_catches_decision_language():
    """'We've decided to...' should pass the pre-filter."""
    assert pre_filter("We've decided to go with MotorCo as our primary supplier") is True
    assert pre_filter("Going forward with the new thermal design") is True
    assert pre_filter("Final decision: we're switching to MotorCo") is True
    assert pre_filter("Let's go with option B") is True


def test_prefilter_rejects_casual_chat():
    """Casual messages should be filtered out."""
    assert pre_filter("Hey want to grab lunch?") is False
    assert pre_filter("Good morning everyone!") is False
    assert pre_filter("Thanks!") is False
    assert pre_filter("lol nice") is False


def test_prefilter_catches_approval_language():
    """Approval language should pass."""
    assert pre_filter("Approved for production release") is True
    assert pre_filter("LGTM, ship it") is True
    assert pre_filter("Signed off on the thermal spec") is True
    assert pre_filter("Green light on procurement") is True


def test_prefilter_catches_change_language():
    """Change language should pass."""
    assert pre_filter("Updated the BOM with new motor specs") is True
    assert pre_filter("Changed the supplier to MotorCo") is True
    assert pre_filter("New version of the thermal report uploaded") is True


# --- Classification Parsing ---

VALID_CLASSIFICATION = json.dumps({
    "is_significant": True,
    "confidence": 0.85,
    "type": "decision",
    "brief_reason": "Team decided to switch motor supplier",
})

MALFORMED_CLASSIFICATION = "This is not valid JSON at all"

CLASSIFICATION_WITH_EXTRA = """```json
{
    "is_significant": true,
    "confidence": 0.72,
    "type": "change",
    "brief_reason": "BOM was updated"
}
```"""


def test_classification_parses_valid_json():
    """Valid classification JSON response → structured result."""
    result = parse_classification_response(VALID_CLASSIFICATION)
    assert result["is_significant"] is True
    assert result["confidence"] == 0.85
    assert result["type"] == "decision"


def test_classification_handles_malformed_json():
    """Malformed JSON → graceful failure (not significant)."""
    result = parse_classification_response(MALFORMED_CLASSIFICATION)
    assert result["is_significant"] is False
    assert result["confidence"] == 0.0


def test_classification_strips_markdown_fences():
    """JSON wrapped in markdown code fences is parsed correctly."""
    result = parse_classification_response(CLASSIFICATION_WITH_EXTRA)
    assert result["is_significant"] is True
    assert result["type"] == "change"


# --- Extraction Parsing ---

VALID_EXTRACTION = json.dumps({
    "title": "Switch primary motor supplier to MotorCo",
    "summary": "Team decided to switch from SupplierA to MotorCo.",
    "type": "decision",
    "detail": {
        "statement": "We will use MotorCo as primary motor supplier starting Q2.",
        "rationale": "30% cost reduction and better lead times.",
        "alternatives_considered": ["Stay with SupplierA"],
        "expected_follow_ups": ["Update BOM in GitHub", "Create procurement ticket"],
    },
    "tags": ["supply-chain", "motors"],
})

EXTRACTION_MISSING_FIELDS = json.dumps({
    "title": "Quick BOM update",
    "summary": "Updated the bill of materials.",
    "type": "change",
    "detail": {
        "statement": "BOM updated with new motor part numbers.",
    },
    "tags": [],
})


def test_extraction_parses_decision():
    """Valid extraction response → KO fields."""
    result = parse_extraction_response(VALID_EXTRACTION)
    assert result["title"] == "Switch primary motor supplier to MotorCo"
    assert result["type"] == "decision"
    assert "MotorCo" in result["summary"]


def test_extraction_includes_expected_follow_ups():
    """Follow-ups should be extracted for the verification agent."""
    result = parse_extraction_response(VALID_EXTRACTION)
    follow_ups = result["detail"]["expected_follow_ups"]
    assert len(follow_ups) == 2
    assert "BOM" in follow_ups[0]


def test_extraction_handles_missing_fields():
    """Missing optional fields → None, not crash."""
    result = parse_extraction_response(EXTRACTION_MISSING_FIELDS)
    assert result["title"] == "Quick BOM update"
    detail = result["detail"]
    assert detail.get("rationale") is None
    assert detail.get("alternatives_considered") is None or detail.get("alternatives_considered") == []
    assert detail.get("expected_follow_ups") is None or detail.get("expected_follow_ups") == []


# --- Full Pipeline ---

@pytest.mark.asyncio
async def test_pipeline_end_to_end():
    """Significant event → KO extracted (with mocked LLM)."""
    mock_classification = {
        "is_significant": True,
        "confidence": 0.85,
        "type": "decision",
        "brief_reason": "Decision made",
    }
    mock_extraction = {
        "title": "Switch to MotorCo",
        "summary": "Team decided to switch.",
        "type": "decision",
        "detail": {
            "statement": "We will use MotorCo.",
            "rationale": "Cost savings.",
            "alternatives_considered": [],
            "expected_follow_ups": ["Update BOM"],
        },
        "tags": ["motors"],
    }

    event = {
        "source": "slack",
        "content": "We've decided to switch to MotorCo as our primary supplier",
        "event_type": "message",
        "actor_name": "Alice",
    }

    result = await run_extraction_pipeline(
        event,
        mock_classify_response=json.dumps(mock_classification),
        mock_extract_response=json.dumps(mock_extraction),
    )
    assert result is not None
    assert result["title"] == "Switch to MotorCo"
    assert result["type"] == "decision"


@pytest.mark.asyncio
async def test_pipeline_filters_noise():
    """Casual message → no KO created (filtered by pre-filter)."""
    event = {
        "source": "slack",
        "content": "Hey, want to grab lunch?",
        "event_type": "message",
        "actor_name": "Bob",
    }

    result = await run_extraction_pipeline(event)
    assert result is None
