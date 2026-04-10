"""Helpers for canonicalizing legacy KO types."""


def canonicalize_knowledge_type(value: str | None) -> str:
    """Map legacy or overlapping KO types onto the canonical type set."""
    normalized = (value or "decision").strip().lower() or "decision"
    if normalized == "change":
        return "decision"
    return normalized


def equivalent_knowledge_types(value: str | None) -> list[str]:
    """Return all stored DB types that should be treated as the same logical type."""
    canonical = canonicalize_knowledge_type(value)
    if canonical == "decision":
        return ["decision", "change"]
    return [canonical]
