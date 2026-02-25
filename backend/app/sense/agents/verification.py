"""Verification agent: checks whether expected follow-up actions were implemented.

Uses Gemini 2.0 Flash via Backboard API with function calling.
Max 10 tool calls per run (hard cap).
"""
import json

MAX_TOOL_CALLS = 10

VERIFICATION_SYSTEM_PROMPT = """You are a verification agent for Sense, an engineering project memory system.

You have been given a Knowledge Object (a captured engineering decision, change, or approval).
Your job is to verify whether the expected follow-up actions have been implemented across
the team's connected tools (Slack, GitHub, Google Drive).

Instructions:
1. Read the knowledge object carefully. Identify what follow-up actions should have happened.
2. Use the search tools to look for evidence of each expected action.
3. For each expected action, record a verification check:
   - "verified" if you found clear evidence it was done
   - "missing" if you searched and couldn't find evidence
   - "unknown" if you can't determine (insufficient data)
4. For missing actions, suggest a specific follow-up action.
5. Be conservative — only mark "verified" if the evidence is clear.
6. Do NOT evaluate whether the decision was good or bad. Only check implementation."""

VERIFICATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_events_by_content",
            "description": "Search ingested events for content matching a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Semantic search query"},
                    "source": {"type": "string", "enum": ["slack", "github", "any"]},
                    "since_hours": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events_by_actor",
            "description": "Search events by a specific actor email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "actor_email": {"type": "string"},
                    "source": {"type": "string", "enum": ["slack", "github", "any"]},
                    "since_hours": {"type": "integer"},
                },
                "required": ["actor_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_verification_check",
            "description": "Record a verification check result for the knowledge object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "status": {"type": "string", "enum": ["verified", "missing", "unknown"]},
                    "evidence": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "event_id": {"type": "string"},
                },
                "required": ["description", "status"],
            },
        },
    },
]


async def run_verification_agent(
    ko: dict,
    mock_tool_results: dict | None = None,
    mock_llm_tool_calls: list[dict] | None = None,
) -> list[dict]:
    """Run the verification agent on a Knowledge Object.

    In test mode (mock_llm_tool_calls provided), simulates the agent loop.
    In production, uses the Backboard API for LLM function calling.

    Returns a list of verification check dicts.
    """
    detail = ko.get("detail", {})
    follow_ups = detail.get("expected_follow_ups", [])

    # If no follow-ups, nothing to verify
    if not follow_ups and not mock_llm_tool_calls:
        return []

    checks = []
    tool_call_count = 0

    if mock_llm_tool_calls is not None:
        # Test mode: execute mock tool calls
        for call in mock_llm_tool_calls:
            if tool_call_count >= MAX_TOOL_CALLS:
                break
            tool_call_count += 1

            name = call["name"]
            args = call.get("args", {})

            if name == "record_verification_check":
                checks.append({
                    "description": args.get("description", ""),
                    "status": args.get("status", "unknown"),
                    "evidence": args.get("evidence"),
                    "suggestion": args.get("suggestion"),
                    "event_id": args.get("event_id"),
                })
            elif mock_tool_results:
                # Execute search tools against mock data
                _result = mock_tool_results.get(name, [])
    else:
        # Production mode: use Backboard API
        from app.backboard.llm import backboard_llm

        ko_json = json.dumps(ko, indent=2)
        messages = [{
            "role": "user",
            "content": f"{VERIFICATION_SYSTEM_PROMPT}\n\nKnowledge Object:\n{ko_json}",
        }]

        for _ in range(MAX_TOOL_CALLS):
            result = await backboard_llm.chat(
                messages=messages,
                model_role="verification",
                system=VERIFICATION_SYSTEM_PROMPT,
                tools=VERIFICATION_TOOLS,
            )

            if result["status"] == "REQUIRES_ACTION" and result["tool_calls"]:
                tool_outputs = []
                for tc in result["tool_calls"]:
                    tool_call_count += 1
                    if tool_call_count > MAX_TOOL_CALLS:
                        break

                    func_name = tc.get("function", {}).get("name", "")
                    func_args = tc.get("function", {}).get("parsed_arguments", {})

                    if func_name == "record_verification_check":
                        checks.append({
                            "description": func_args.get("description", ""),
                            "status": func_args.get("status", "unknown"),
                            "evidence": func_args.get("evidence"),
                            "suggestion": func_args.get("suggestion"),
                        })
                        tool_outputs.append({
                            "tool_call_id": tc.get("id", ""),
                            "output": json.dumps({"ok": True}),
                        })
                    else:
                        tool_outputs.append({
                            "tool_call_id": tc.get("id", ""),
                            "output": json.dumps({"results": []}),
                        })

                if result.get("run_id") and result.get("thread_id"):
                    result = await backboard_llm.submit_tool_outputs(
                        thread_id=result["thread_id"],
                        run_id=result["run_id"],
                        tool_outputs=tool_outputs,
                    )
            else:
                break  # Agent is done

    return checks
