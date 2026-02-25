"""Cross-tool correlation engine.

Implements weighted scoring from TECHNICAL_SPEC Section 6:
  - Semantic similarity (0.35)
  - Actor overlap (0.25)
  - Temporal proximity (0.20)
  - Explicit references (0.20)

Merge threshold: > 0.6
"""
import re
import numpy as np

# Correlation weights
W_SEMANTIC = 0.35
W_ACTOR = 0.25
W_TEMPORAL = 0.20
W_REFERENCE = 0.20

MERGE_THRESHOLD = 0.6
DEFAULT_WINDOW_HOURS = 24

# Reference patterns
URL_PATTERN = re.compile(r"https?://\S+")
FILENAME_PATTERN = re.compile(r"\b[\w\-]+\.\w{2,5}\b")  # e.g., BOM_v3.xlsx
TICKET_PATTERN = re.compile(r"\b[A-Z]+-\d+\b")  # e.g., PROJ-123


def semantic_similarity_score(embedding_a: list[float], embedding_b: list[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    a = np.array(embedding_a)
    b = np.array(embedding_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def actor_overlap_score(actors_a: set[str], actors_b: set[str]) -> float:
    """Jaccard similarity between two actor sets."""
    if not actors_a or not actors_b:
        return 0.0
    intersection = actors_a & actors_b
    union = actors_a | actors_b
    if not union:
        return 0.0
    return len(intersection) / len(union)


def temporal_proximity_score(time_diff_seconds: float, window_hours: int = DEFAULT_WINDOW_HOURS) -> float:
    """Score based on how close events are in time. 0 = at window edge, 1 = simultaneous."""
    max_seconds = window_hours * 3600
    if time_diff_seconds >= max_seconds:
        return 0.0
    return max(0.0, 1.0 - (time_diff_seconds / max_seconds))


def find_shared_references(content_a: str, content_b: str) -> list[str]:
    """Find shared references between two content strings (URLs, filenames, ticket IDs)."""
    shared = []

    urls_a = set(URL_PATTERN.findall(content_a))
    urls_b = set(URL_PATTERN.findall(content_b))
    shared.extend(urls_a & urls_b)

    files_a = set(FILENAME_PATTERN.findall(content_a))
    files_b = set(FILENAME_PATTERN.findall(content_b))
    shared.extend(files_a & files_b)

    tickets_a = set(TICKET_PATTERN.findall(content_a))
    tickets_b = set(TICKET_PATTERN.findall(content_b))
    shared.extend(tickets_a & tickets_b)

    return shared


def weighted_correlation_score(
    embedding_a: list[float],
    embedding_b: list[float],
    actors_a: set[str],
    actors_b: set[str],
    time_diff_seconds: float,
    content_a: str = "",
    content_b: str = "",
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> float:
    """Compute the weighted correlation score between two events/KOs."""
    score = 0.0

    # Semantic similarity (highest weight)
    sim = semantic_similarity_score(embedding_a, embedding_b)
    if sim > 0.75:
        score += W_SEMANTIC * sim

    # Actor overlap
    actor_sim = actor_overlap_score(actors_a, actors_b)
    if actor_sim > 0:
        score += W_ACTOR * actor_sim

    # Temporal proximity
    temporal = temporal_proximity_score(time_diff_seconds, window_hours)
    score += W_TEMPORAL * temporal

    # Explicit references
    shared_refs = find_shared_references(content_a, content_b)
    if shared_refs:
        score += W_REFERENCE * min(1.0, len(shared_refs) / 3)

    return score


def merge_knowledge_data(ko_a: dict, ko_b: dict) -> dict:
    """Merge two knowledge object data dicts.

    - Primary is the higher-confidence KO
    - Participants: union
    - Event IDs: union
    - Tags: union
    """
    # Determine primary (higher confidence)
    if ko_b.get("confidence", 0) > ko_a.get("confidence", 0):
        primary, secondary = ko_b, ko_a
    else:
        primary, secondary = ko_a, ko_b

    # Merge participants (union by email)
    all_participants = {}
    for p in (secondary.get("participants") or []) + (primary.get("participants") or []):
        email = p.get("email", "")
        if email:
            all_participants[email] = p

    # Merge event IDs
    event_ids_a = set(ko_a.get("event_ids", []))
    event_ids_b = set(ko_b.get("event_ids", []))
    merged_event_ids = list(event_ids_a | event_ids_b)

    # Merge tags
    tags_a = set(ko_a.get("tags") or [])
    tags_b = set(ko_b.get("tags") or [])
    merged_tags = list(tags_a | tags_b)

    return {
        "title": primary["title"],
        "summary": primary.get("summary"),
        "detail": primary.get("detail", {}),
        "confidence": primary.get("confidence", 0),
        "participants": list(all_participants.values()),
        "event_ids": merged_event_ids,
        "tags": merged_tags,
    }
