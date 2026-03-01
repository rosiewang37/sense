# Correlation Tuning Guide

This document lists the current correlation and detection knobs, what each one does, and when to change it.

## Tunable Parameters

| Parameter | Current Value | Location | What It Controls |
| --- | --- | --- | --- |
| `W_SEMANTIC` | `0.35` | `backend/app/sense/correlation.py` | Weight applied to semantic similarity when the similarity gate passes. |
| `W_ACTOR` | `0.25` | `backend/app/sense/correlation.py` | Weight applied to actor overlap (shared participants). |
| `W_TEMPORAL` | `0.20` | `backend/app/sense/correlation.py` | Weight applied to time proximity inside the configured window. |
| `W_REFERENCE` | `0.20` | `backend/app/sense/correlation.py` | Weight applied to shared URLs, filenames, and ticket IDs. |
| `MERGE_THRESHOLD` | `0.6` | `backend/app/sense/correlation.py` | Minimum score required for KO-to-KO merge during scheduled correlation. |
| Semantic similarity gate | `0.75` | `backend/app/sense/correlation.py`, `weighted_correlation_score()` | Semantic similarity contributes only when cosine similarity is greater than `0.75`. |
| Reference cap | `3` | `backend/app/sense/correlation.py`, `weighted_correlation_score()` | Shared-reference contribution is capped at `3` matches (`min(1.0, len(shared_refs) / 3)`). |
| `DEFAULT_WINDOW_HOURS` | `24` | `backend/app/sense/correlation.py` | Default time window for temporal scoring. |
| Classification confidence threshold | `0.5` | `backend/app/sense/detection.py`, `run_extraction_pipeline()` | Minimum classifier confidence before extraction runs. |
| GitHub link threshold | `0.45` | `backend/app/sense/tasks.py`, `_find_and_link_to_existing_decision()` | Minimum score to link a GitHub event to an existing decision KO (`MERGE_THRESHOLD * 0.75`). |
| GitHub linking window | `7 days` | `backend/app/sense/tasks.py`, `_find_and_link_to_existing_decision()` | How far back to look for recent decision KOs before linking a GitHub event. |
| GitHub temporal scoring window | `168 hours` | `backend/app/sense/tasks.py`, `_find_and_link_to_existing_decision()` | Time window passed into correlation for GitHub evidence linking. |
| Correlation task window | `24 hours` | `backend/app/sense/tasks.py`, `run_correlation_async()` | How far back the scheduled merge scan looks for active KOs. |
| Pre-filter regex patterns | See `SIGNIFICANCE_SIGNALS` | `backend/app/sense/detection.py` | Cheap keyword gate before any LLM classification call. |

## Scoring Formula

The weighted correlation score is built from four components:

```text
score =
  semantic_component +
  actor_component +
  temporal_component +
  reference_component
```

The current implementation expands to:

```text
semantic_component = W_SEMANTIC * cosine_similarity   if cosine_similarity > 0.75 else 0
actor_component    = W_ACTOR * actor_overlap
temporal_component = W_TEMPORAL * temporal_proximity
reference_component = W_REFERENCE * min(1.0, shared_reference_count / 3)
```

### Example: Likely Merge

If two KOs have:

- cosine similarity `0.82`
- actor overlap `0.50`
- temporal proximity `0.75`
- `2` shared references

The score is:

```text
(0.35 * 0.82) + (0.25 * 0.50) + (0.20 * 0.75) + (0.20 * (2/3))
= 0.287 + 0.125 + 0.150 + 0.133
= 0.695
```

`0.695` is above `MERGE_THRESHOLD (0.6)`, so the pair merges.

### Example: Similar Topic, But Not Enough Evidence

If two KOs have:

- cosine similarity `0.72`
- actor overlap `0.00`
- temporal proximity `0.50`
- `0` shared references

The score is:

```text
0 + 0 + (0.20 * 0.50) + 0 = 0.10
```

The semantic part contributes nothing because the `0.75` gate was not met.

## When To Change What

- Decisions merge too aggressively: raise `MERGE_THRESHOLD` first. If bad merges are driven by shared participants, lower `W_ACTOR`. If they are driven by timing, lower `W_TEMPORAL`.
- Decisions are not merging enough: lower `MERGE_THRESHOLD` first. If obviously related items are semantically close but still missing, consider lowering the semantic gate from `0.75` or raising `W_SEMANTIC`.
- GitHub commits fail to link to known decisions: lower the GitHub link threshold or widen the 7-day search window in `_find_and_link_to_existing_decision()`.
- Unrelated GitHub commits are linking: raise the GitHub link threshold or reduce the 7-day search window.
- Too many non-decisions reach the LLM: tighten `SIGNIFICANCE_SIGNALS` in `backend/app/sense/detection.py`.
- Real decisions are filtered out before classification: add more pre-filter patterns or reduce dependence on narrow phrasing.
- The classifier is too strict: reduce the `0.5` classification confidence threshold.
- The classifier is too noisy: increase the `0.5` threshold.

## Pre-Filter Patterns

The regex pre-filter lives in `SIGNIFICANCE_SIGNALS` inside `backend/app/sense/detection.py`.

To add a new pattern:

1. Add a new regex string to the `SIGNIFICANCE_SIGNALS` list.
2. Keep the pattern targeted to high-signal language, not general conversation.
3. Prefer simple, readable expressions that match common phrasing.
4. Remember the list is compiled with `re.IGNORECASE`, so you do not need inline case flags.
5. Re-test with both positive and negative examples to make sure the new pattern does not let too much noise through.

Example additions:

```python
r"approved for release"
r"we are standardizing on"
r"let's deprecate"
```

## Recommended Tuning Order

1. Start with thresholds (`MERGE_THRESHOLD`, classifier confidence, GitHub link threshold).
2. Adjust weights only after you know which component is over-contributing.
3. Change one knob at a time and re-run the manual scenarios in `docs/TESTING_PLAN.md`.
4. Record before/after examples when you tune so you can tell whether the change helped or just shifted failure modes.
