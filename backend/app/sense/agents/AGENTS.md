# Agents — Intent

## Purpose
AI agents that use Gemini function calling to verify decisions and answer investigative queries.

## Scope
`app/sense/agents/` — verification and investigative agents.

## Entry Points
- `verification.py:run_verification_agent()` — checks if expected follow-ups happened
- `investigator.py:run_query_agent()` — answers questions about project history

## Contracts / Invariants
- **Safety caps are non-negotiable:**
  - Verification agent: max **10** tool calls per run
  - Investigative agent: max **8** tool calls per query
  - After cap: return whatever has been found, never loop further
- Tool-use loop pattern:
  1. Define function declarations (name, description, parameters JSON schema)
  2. Send messages + tool declarations to Gemini via `backboard_llm.chat()`
  3. If response contains `tool_calls`: execute each, append results, loop
  4. If response contains text (no tool_calls): done, return answer
  5. If cap reached: force return with partial results
- Verification checks recorded with status: `"verified"` | `"missing"` | `"unknown"`
- Only mark `"verified"` when evidence is unambiguous

## Available Tools

### Verification Agent
- `search_events_by_content` — keyword search in events
- `search_events_by_actor` — find events by actor name/email
- `record_verification_check` — record a check result

### Investigative Agent
- `search_knowledge_base` — search KOs by query
- `search_raw_events` — search raw events by keyword
- `get_knowledge_detail` — get full KO by ID
- `get_verification_status` — get verification checks for a KO

## Testing
Mock tool calls via `mock_llm_tool_calls` parameter — list of dicts with `tool`, `args`, `result` (or `response` for final text). No real LLM needed.

## Anti-Patterns
- Exceeding safety caps under any circumstances
- Fabricating tool results (agents must use actual data)
- Skipping verification in production (controlled by `SKIP_VERIFICATION` flag, should be `false` in prod)
- Making LLM calls outside the `backboard_llm` gateway
