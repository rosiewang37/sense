"""Knowledge extraction pipeline: pre-filter → classification → extraction.

Uses the pre-filter regex patterns from the TECHNICAL_SPEC Section 5.2,
classification prompt from 5.3, and extraction prompt from 5.4.
"""
import json
import re

# --- Pre-filter (Rule-Based, No LLM Cost) ---

SIGNIFICANCE_SIGNALS = [
    # Decision language
    r"we('ve| have)? decided", r"going (with|forward with)",
    r"final (call|decision|answer)", r"let's go with",
    r"we('re| are) (switching|moving|changing) to",

    # Approval language
    r"approved", r"sign(ed)? off", r"lgtm", r"green.?light",

    # Rejection language
    r"ruling out", r"we('re| are) not going (with|to)", r"rejected",

    # Change language
    r"updated", r"changed .+ to", r"new version", r"replaced",

    # Evaluation language
    r"after (comparing|evaluating|testing|reviewing)",
    r"pros and cons", r"trade.?off",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SIGNIFICANCE_SIGNALS]


def pre_filter(text: str) -> bool:
    """Fast regex filter — returns True if the text contains significance signals."""
    if not text:
        return False
    return any(p.search(text) for p in _COMPILED_PATTERNS)


# --- Classification Response Parsing ---

CLASSIFICATION_PROMPT = """You classify engineering team events by significance.
Given an event from a collaboration tool, determine if it represents
a significant engineering moment (decision, change, approval, blocker).

Respond with JSON:
{{
  "is_significant": true/false,
  "confidence": 0.0-1.0,
  "type": "decision|change|approval|blocker|context|none",
  "brief_reason": "why"
}}

Event source: {source}
Event type: {event_type}
Author: {actor_name}
Content: {content}"""


def parse_classification_response(response_text: str) -> dict:
    """Parse LLM classification response into structured result.

    Handles JSON wrapped in markdown fences or plain JSON.
    Returns a safe default if parsing fails.
    """
    text = response_text.strip()

    # Strip markdown code fences
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)

    try:
        data = json.loads(text)
        return {
            "is_significant": bool(data.get("is_significant", False)),
            "confidence": float(data.get("confidence", 0.0)),
            "type": data.get("type", "none"),
            "brief_reason": data.get("brief_reason", ""),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {
            "is_significant": False,
            "confidence": 0.0,
            "type": "none",
            "brief_reason": "Failed to parse classification response",
        }


# --- Extraction Response Parsing ---

EXTRACTION_PROMPT = """Extract structured knowledge from this engineering team event.
Be precise — only include information explicitly stated or strongly implied.

Event source: {source}
Content: {content}
Context: {context}

Extract as JSON:
{{
  "title": "short descriptive title",
  "summary": "1-2 sentence summary",
  "type": "decision|change|approval|blocker",
  "detail": {{
    "statement": "the specific decision/change/approval",
    "rationale": "why (if stated)",
    "alternatives_considered": ["if any mentioned"],
    "expected_follow_ups": ["what actions should follow from this"]
  }},
  "tags": ["relevant topic tags"]
}}"""


def parse_extraction_response(response_text: str) -> dict | None:
    """Parse LLM extraction response into KO fields.

    Returns None if parsing fails entirely.
    """
    text = response_text.strip()

    # Strip markdown code fences
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    # Normalize the detail field
    detail = data.get("detail", {})
    if not isinstance(detail, dict):
        detail = {}

    # Ensure all detail sub-fields exist (may be None)
    detail.setdefault("statement", None)
    detail.setdefault("rationale", None)
    detail.setdefault("alternatives_considered", [])
    detail.setdefault("expected_follow_ups", [])

    return {
        "title": data.get("title", "Untitled"),
        "summary": data.get("summary"),
        "type": data.get("type", "context"),
        "detail": detail,
        "tags": data.get("tags", []),
    }


# --- Full Pipeline ---

async def run_extraction_pipeline(
    event: dict,
    mock_classify_response: str | None = None,
    mock_extract_response: str | None = None,
) -> dict | None:
    """Run the full extraction pipeline: pre-filter → classify → extract.

    Accepts mock LLM responses for testing. In production, calls the Backboard API.
    Returns extracted KO data dict or None if filtered/not significant.
    """
    content = event.get("content", "")

    # Step 1: Pre-filter
    if not pre_filter(content):
        return None

    # Step 2: Classification
    if mock_classify_response:
        classify_text = mock_classify_response
    else:
        # Production path: call LLM via Backboard API
        from app.backboard.llm import backboard_llm
        classify_result = await backboard_llm.chat(
            messages=[{
                "role": "user",
                "content": CLASSIFICATION_PROMPT.format(
                    source=event.get("source", "unknown"),
                    event_type=event.get("event_type", "unknown"),
                    actor_name=event.get("actor_name", "unknown"),
                    content=content,
                ),
            }],
            model_role="detection",
        )
        classify_text = classify_result["content"]

    classification = parse_classification_response(classify_text)

    if not classification["is_significant"] or classification["confidence"] < 0.5:
        return None

    # Step 3: Extraction
    if mock_extract_response:
        extract_text = mock_extract_response
    else:
        from app.backboard.llm import backboard_llm
        extract_result = await backboard_llm.chat(
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.format(
                    source=event.get("source", "unknown"),
                    content=content,
                    context="",
                ),
            }],
            model_role="extraction",
        )
        extract_text = extract_result["content"]

    extraction = parse_extraction_response(extract_text)
    if extraction is None:
        return None

    # Add classification confidence
    extraction["confidence"] = classification["confidence"]
    return extraction
