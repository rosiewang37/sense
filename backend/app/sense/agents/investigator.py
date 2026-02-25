"""Investigative query agent: multi-step reasoning for chat queries.

Uses Gemini 2.5 Pro via Backboard API with function calling.
Max 8 tool calls per query (hard cap).
"""
import json

MAX_TOOL_CALLS = 8

QUERY_AGENT_SYSTEM_PROMPT = """You are Sense, an investigative engineering memory assistant.

When a user asks a question about their project history, you have tools to investigate:
1. Search the structured knowledge base (decisions, changes, approvals)
2. Search raw events (Slack messages, GitHub commits, file uploads)
3. Get full details and verification status of specific knowledge objects

Investigation approach:
- Start with the knowledge base. If the answer is clear, respond.
- If the knowledge base is incomplete, search raw events for more context.
- If you find a relevant knowledge object, check its verification status to report
  on implementation follow-through.
- Always cite your sources with [KO:id] for knowledge objects and [Event:id] for raw events.
- If you can't find the answer, say so clearly.
- Never fabricate information. Only report what the evidence shows."""

QUERY_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the structured knowledge base for decisions, changes, and approvals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "type_filter": {"type": "string", "enum": ["decision", "change", "approval", "blocker", "any"]},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_raw_events",
            "description": "Search raw ingested events (Slack messages, GitHub commits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source": {"type": "string", "enum": ["slack", "github", "any"]},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_knowledge_detail",
            "description": "Get full details of a specific knowledge object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "knowledge_id": {"type": "string"},
                },
                "required": ["knowledge_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_verification_status",
            "description": "Get verification status of a knowledge object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "knowledge_id": {"type": "string"},
                },
                "required": ["knowledge_id"],
            },
        },
    },
]


async def run_query_agent(
    question: str,
    project_id: str | None = None,
    mock_llm_tool_calls: list[dict] | None = None,
    mock_tool_results: dict | None = None,
    mock_final_answer: str | None = None,
) -> dict:
    """Run the investigative query agent.

    In test mode (mocks provided), simulates the agent loop.
    In production, uses the Backboard API for LLM function calling.

    Returns dict with 'answer' and 'steps'.
    """
    steps = []
    tool_call_count = 0

    if mock_llm_tool_calls is not None:
        # Test mode: simulate agent tool calls
        for call in mock_llm_tool_calls:
            if tool_call_count >= MAX_TOOL_CALLS:
                break
            tool_call_count += 1

            name = call["name"]
            args = call.get("args", {})
            result_data = (mock_tool_results or {}).get(name, [])

            steps.append({
                "tool": name,
                "args": args,
                "result": result_data,
            })

        return {
            "answer": mock_final_answer or "No answer available.",
            "steps": steps,
        }
    else:
        # Production mode: Backboard API
        from app.backboard.llm import backboard_llm

        messages = [{"role": "user", "content": question}]

        for _ in range(MAX_TOOL_CALLS):
            result = await backboard_llm.chat(
                messages=messages,
                model_role="chat",
                system=QUERY_AGENT_SYSTEM_PROMPT,
                tools=QUERY_AGENT_TOOLS,
            )

            if result["status"] == "REQUIRES_ACTION" and result["tool_calls"]:
                tool_outputs = []
                for tc in result["tool_calls"]:
                    tool_call_count += 1
                    if tool_call_count > MAX_TOOL_CALLS:
                        break

                    func_name = tc.get("function", {}).get("name", "")
                    steps.append({
                        "tool": func_name,
                        "args": tc.get("function", {}).get("parsed_arguments", {}),
                        "result": [],
                    })
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
                return {
                    "answer": result.get("content", "No answer available."),
                    "steps": steps,
                }

        return {
            "answer": result.get("content", "No answer available.") if result else "Max iterations reached.",
            "steps": steps,
        }
