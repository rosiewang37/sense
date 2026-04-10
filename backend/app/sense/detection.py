"""Knowledge extraction pipeline: pre-filter → classification → extraction.

Uses the pre-filter regex patterns from the TECHNICAL_SPEC Section 5.2,
classification prompt from 5.3, and extraction prompt from 5.4.
"""
import json
import logging
import re

from app.sense.knowledge_types import canonicalize_knowledge_type

logger = logging.getLogger(__name__)

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
a significant engineering moment (decision, approval, blocker).

Respond with JSON:
{{
  "is_significant": true/false,
  "confidence": 0.0-1.0,
  "type": "decision|approval|blocker|context|none",
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
            "type": canonicalize_knowledge_type(data.get("type", "none")),
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
  "type": "decision|approval|blocker",
  "detail": {{
    "statement": "the specific decision or approved action",
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
        "type": canonicalize_knowledge_type(data.get("type", "context")),
        "detail": detail,
        "tags": data.get("tags", []),
    }


# --- Full Pipeline ---

def _format_context_for_extraction(event: dict) -> tuple[str, list[dict]]:
    """Build a readable context block for extraction and collect named participants."""
    metadata = event.get("metadata") or {}
    context_messages = metadata.get("context_messages") or []
    attachments = metadata.get("attachments") or []
    trigger_ts = str(event.get("source_id") or "")
    trigger_index = next(
        (idx for idx, msg in enumerate(context_messages) if str(msg.get("ts") or "") == trigger_ts),
        None,
    )

    lines: list[str] = []
    participants: list[dict] = []
    seen_participants: set[str] = set()

    def add_participant(name: str) -> None:
        cleaned = (name or "").strip()
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen_participants:
            return
        seen_participants.add(key)
        participants.append({"email": "", "name": cleaned, "role": "participant"})

    def format_message(message: dict) -> str:
        name = (message.get("user_name") or "Unknown").strip() or "Unknown"
        text = (message.get("text") or "").strip()
        add_participant(name)
        return f"- {name}: {text}"

    if context_messages:
        if trigger_index is None:
            trigger_index = max(0, len(context_messages) - 1)

        preceding = context_messages[:trigger_index]
        trigger_message = context_messages[trigger_index]
        following = context_messages[trigger_index + 1:]

        if preceding:
            lines.append("Preceding messages:")
            lines.extend(format_message(message) for message in preceding if message.get("text"))

        lines.append("Trigger message:")
        lines.append(format_message(trigger_message))

        if following:
            lines.append("Following messages:")
            lines.extend(format_message(message) for message in following if message.get("text"))

    if attachments:
        lines.append("Shared attachments:")
        for attachment in attachments:
            name = attachment.get("name", "unnamed file") or "unnamed file"
            filetype = attachment.get("filetype") or attachment.get("mimetype") or "unknown"
            permalink = attachment.get("permalink") or attachment.get("url_private") or ""
            suffix = f" ({filetype})"
            if permalink:
                suffix += f" {permalink}"
            lines.append(f"- {name}{suffix}")

    return "\n".join(lines).strip(), participants


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
    source = event.get("source", "unknown")
    preview = (content or "")[:80]

    # Step 1: Pre-filter
    if not pre_filter(content):
        logger.info(f"[pipeline] PRE-FILTER rejected ({source}): \"{preview}\"")
        return None
    logger.info(f"[pipeline] PRE-FILTER passed ({source}): \"{preview}\"")

    # Step 2: Classification
    if mock_classify_response:
        classify_text = mock_classify_response
    else:
        # Production path: call LLM via Backboard API
        logger.info(f"[pipeline] CLASSIFY: calling LLM for classification...")
        from app.backboard.llm import backboard_llm
        classify_result = await backboard_llm.chat(
            messages=[{
                "role": "user",
                "content": CLASSIFICATION_PROMPT.format(
                    source=source,
                    event_type=event.get("event_type", "unknown"),
                    actor_name=event.get("actor_name", "unknown"),
                    content=content,
                ),
            }],
            model_role="detection",
        )
        classify_text = classify_result["content"]
        logger.info(f"[pipeline] CLASSIFY: LLM responded")

    classification = parse_classification_response(classify_text)
    logger.info(
        f"[pipeline] CLASSIFY result: significant={classification['is_significant']}, "
        f"confidence={classification['confidence']:.2f}, type={classification['type']}"
    )

    if not classification["is_significant"] or classification["confidence"] < 0.5:
        logger.info(f"[pipeline] CLASSIFY rejected (not significant or low confidence)")
        return None

    context_text, context_participants = _format_context_for_extraction(event)
    if context_text:
        logger.info(f"[pipeline] CONTEXT: {len(context_participants)} participants, {len(context_text)} chars of context")
        print(f"[SENSE] _format_context_for_extraction: {len((event.get('metadata') or {}).get('context_messages') or [])} context messages, {len(context_participants)} participants", flush=True)
    else:
        context_text = "No surrounding conversation context was available. Extract based on the message content alone."
        logger.info("[pipeline] CONTEXT: empty — using no-context fallback prompt")

    # Step 3: Extraction
    if mock_extract_response:
        extract_text = mock_extract_response
    else:
        logger.info(f"[pipeline] EXTRACT: calling LLM for extraction...")
        from app.backboard.llm import backboard_llm
        extract_result = await backboard_llm.chat(
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.format(
                    source=source,
                    content=content,
                    context=context_text,
                ),
            }],
            model_role="extraction",
        )
        extract_text = extract_result["content"]
        logger.info(f"[pipeline] EXTRACT: LLM responded")

    extraction = parse_extraction_response(extract_text)
    if extraction is None:
        logger.warning(f"[pipeline] EXTRACT: failed to parse extraction response")
        return None

    logger.info(
        f"[pipeline] EXTRACT success: title=\"{extraction.get('title', '')}\", "
        f"type={extraction.get('type', '')}"
    )

    # Add classification confidence
    extraction["confidence"] = classification["confidence"]
    extraction["participants"] = context_participants
    return extraction
