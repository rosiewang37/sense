"""Phase 4 tests: Cross-tool correlation engine (TDD-critical).

Tests:
- Semantic similarity scoring
- Actor overlap scoring
- Temporal proximity scoring
- Explicit reference detection
- Weighted score above/below merge threshold
- Merge logic: combines participants, events, keeps higher confidence
"""
import pytest
import numpy as np
from app.sense.correlation import (
    semantic_similarity_score,
    actor_overlap_score,
    temporal_proximity_score,
    find_shared_references,
    weighted_correlation_score,
    merge_knowledge_data,
)


# --- Individual Scoring Functions ---

def test_semantic_similarity_high_for_related():
    """Same-topic embeddings should score high (> 0.75)."""
    # Nearly identical vectors
    vec_a = np.random.rand(768).tolist()
    vec_b = [v + np.random.normal(0, 0.01) for v in vec_a]
    score = semantic_similarity_score(vec_a, vec_b)
    assert score > 0.75


def test_semantic_similarity_low_for_unrelated():
    """Random different vectors should score low (< 0.5)."""
    # Use orthogonal vectors to guarantee low similarity
    vec_a = [0.0] * 768
    vec_b = [0.0] * 768
    vec_a[0] = 1.0  # Unit vector along dim 0
    vec_b[1] = 1.0  # Unit vector along dim 1
    score = semantic_similarity_score(vec_a, vec_b)
    assert score < 0.1  # Orthogonal vectors have ~0 cosine similarity


def test_actor_overlap_scoring():
    """Same actors → high score; no overlap → 0."""
    actors_a = {"alice@co.com", "bob@co.com"}
    actors_b = {"alice@co.com", "charlie@co.com"}
    score = actor_overlap_score(actors_a, actors_b)
    # Jaccard: 1/3 = 0.333
    assert 0.3 < score < 0.4

    # No overlap
    actors_c = {"dave@co.com"}
    score_none = actor_overlap_score(actors_a, actors_c)
    assert score_none == 0.0


def test_temporal_proximity_scoring():
    """Events close in time → high score; far apart → low."""
    # 1 hour apart in a 24-hour window
    score_close = temporal_proximity_score(3600, window_hours=24)
    assert score_close > 0.9

    # 20 hours apart
    score_far = temporal_proximity_score(20 * 3600, window_hours=24)
    assert score_far < 0.2


def test_reference_detection_finds_urls():
    """Shared GitHub URL detected across KOs."""
    content_a = "Check out https://github.com/org/repo/pull/42 for the BOM changes"
    content_b = "PR merged: https://github.com/org/repo/pull/42"
    refs = find_shared_references(content_a, content_b)
    assert len(refs) >= 1
    assert any("github.com" in ref for ref in refs)


def test_reference_detection_finds_filenames():
    """Shared filenames detected."""
    content_a = "Updated the BOM_v3.xlsx with MotorCo parts"
    content_b = "Uploaded BOM_v3.xlsx to the shared drive"
    refs = find_shared_references(content_a, content_b)
    assert len(refs) >= 1
    assert any("BOM_v3" in ref for ref in refs)


# --- Weighted Correlation Score ---

def test_weighted_score_merges_above_threshold():
    """Combined score > 0.6 → should merge."""
    # Create scenario with high semantic + actor + temporal
    vec_a = np.random.rand(768).tolist()
    vec_b = [v + np.random.normal(0, 0.01) for v in vec_a]
    actors_a = {"alice@co.com", "bob@co.com"}
    actors_b = {"alice@co.com", "bob@co.com"}
    time_diff_seconds = 1800  # 30 minutes
    content_a = "Decided to use MotorCo https://github.com/org/repo/pull/42"
    content_b = "BOM updated for MotorCo https://github.com/org/repo/pull/42"

    score = weighted_correlation_score(
        embedding_a=vec_a, embedding_b=vec_b,
        actors_a=actors_a, actors_b=actors_b,
        time_diff_seconds=time_diff_seconds,
        content_a=content_a, content_b=content_b,
    )
    assert score > 0.6


def test_weighted_score_no_merge_below_threshold():
    """Unrelated events score < 0.6 → no merge."""
    vec_a = np.random.rand(768).tolist()
    vec_b = np.random.rand(768).tolist()
    actors_a = {"alice@co.com"}
    actors_b = {"dave@co.com"}
    time_diff_seconds = 20 * 3600  # 20 hours
    content_a = "Going to lunch"
    content_b = "Deploy to production"

    score = weighted_correlation_score(
        embedding_a=vec_a, embedding_b=vec_b,
        actors_a=actors_a, actors_b=actors_b,
        time_diff_seconds=time_diff_seconds,
        content_a=content_a, content_b=content_b,
    )
    assert score < 0.6


# --- Merge Logic ---

def test_merge_combines_participants():
    """Merged KO has union of participants."""
    ko_a = {
        "participants": [{"email": "alice@co.com"}, {"email": "bob@co.com"}],
        "confidence": 0.9,
        "title": "Switch to MotorCo",
        "summary": "Decision to switch suppliers.",
        "tags": ["motors"],
        "detail": {"statement": "Switch to MotorCo"},
    }
    ko_b = {
        "participants": [{"email": "alice@co.com"}, {"email": "charlie@co.com"}],
        "confidence": 0.7,
        "title": "BOM update for MotorCo",
        "summary": "Updated BOM.",
        "tags": ["bom"],
        "detail": {"statement": "BOM updated"},
    }
    merged = merge_knowledge_data(ko_a, ko_b)
    emails = {p["email"] for p in merged["participants"]}
    assert emails == {"alice@co.com", "bob@co.com", "charlie@co.com"}


def test_merge_combines_events():
    """Merged KO has union of linked event IDs."""
    ko_a = {"event_ids": ["ev1", "ev2"]}
    ko_b = {"event_ids": ["ev2", "ev3"]}
    merged = merge_knowledge_data(
        {**ko_a, "participants": [], "confidence": 0.8, "tags": [], "title": "A", "summary": "A", "detail": {}},
        {**ko_b, "participants": [], "confidence": 0.7, "tags": [], "title": "B", "summary": "B", "detail": {}},
    )
    assert set(merged["event_ids"]) == {"ev1", "ev2", "ev3"}


def test_merge_keeps_higher_confidence():
    """Primary is the higher-confidence KO."""
    ko_a = {
        "confidence": 0.6, "title": "Lower", "summary": "Lower",
        "participants": [], "tags": [], "detail": {}, "event_ids": [],
    }
    ko_b = {
        "confidence": 0.9, "title": "Higher", "summary": "Higher",
        "participants": [], "tags": [], "detail": {}, "event_ids": [],
    }
    merged = merge_knowledge_data(ko_a, ko_b)
    assert merged["title"] == "Higher"
    assert merged["confidence"] == 0.9
