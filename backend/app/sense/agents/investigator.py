"""Investigative query agent: multi-step reasoning for chat queries.

Uses the Backboard API with a persistent thread per user.
Max 8 tool calls per query (hard cap).
"""
import json
import logging

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 8

QUERY_AGENT_SYSTEM_PROMPT = """You are Sense, an investigative engineering memory assistant.

When a user asks a question about their project history, you have tools to investigate:
1. Search the structured knowledge base (decisions, approvals; implementation changes are stored as decisions)
2. Search raw events (Slack messages, GitHub commits)
3. Get full details of a specific knowledge object
4. Get verification status of a knowledge object

Investigation approach:
- Start with search_knowledge_base. If the answer is clear, respond directly.
- If the user asks "why", "how", or asks for rationale, you must call get_knowledge_detail on the best match before answering.
- If incomplete, search raw events for more context.
- If you find a relevant knowledge object, check its verification status.
- Answer the user's question directly. Do not just summarize search results or say what tools you used.
- Always cite your sources with [KO:id] for knowledge objects and [Event:id] for raw events.
- If you cannot find the answer, say so clearly.
- Never fabricate information. Only report what the evidence shows."""

QUERY_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the structured knowledge base for decisions and approvals (changes are stored as decisions).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "type_filter": {
                        "type": "string",
                        "enum": ["decision", "change", "approval", "blocker", "any"],
                    },
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
                    "source": {
                        "type": "string",
                        "enum": ["slack", "github", "any"],
                    },
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
            "description": "Get verification status and checks for a knowledge object.",
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


async def _execute_tool(name: str, args: dict, project_id: str | None = None) -> str:
    """Execute a tool call and return the result as a JSON string.

    Each tool is wrapped in try/except so a single tool failure doesn't
    kill the entire agent loop — the error is returned to the LLM so it
    can try another approach.
    """
    try:
        from app.database import get_session_factory
        from app.backboard.store import (
            search_knowledge_objects,
            search_events,
            get_knowledge_object,
            get_verification_checks_for_ko,
        )

        async with get_session_factory()() as db:
            if name == "search_knowledge_base":
                results = await search_knowledge_objects(
                    db,
                    query=args.get("query", ""),
                    type_filter=args.get("type_filter"),
                    project_id=project_id,
                    limit=args.get("limit", 5),
                )
                return json.dumps({"results": results})

            elif name == "search_raw_events":
                results = await search_events(
                    db,
                    query=args.get("query", ""),
                    source=args.get("source"),
                    project_id=project_id,
                    limit=args.get("limit", 5),
                )
                return json.dumps({"results": results})

            elif name == "get_knowledge_detail":
                ko = await get_knowledge_object(db, args["knowledge_id"])
                if not ko:
                    return json.dumps({"error": "Knowledge object not found"})
                detected_at = ko.detected_at
                if hasattr(detected_at, "isoformat"):
                    detected_at = detected_at.isoformat()
                return json.dumps({
                    "id": str(ko.id),
                    "type": ko.type,
                    "title": ko.title,
                    "summary": ko.summary,
                    "detail": ko.detail,
                    "participants": ko.participants,
                    "tags": ko.tags,
                    "confidence": ko.confidence,
                    "status": ko.status,
                    "detected_at": str(detected_at or ""),
                })

            elif name == "get_verification_status":
                checks = await get_verification_checks_for_ko(db, args["knowledge_id"])
                return json.dumps({"checks": checks, "total": len(checks)})

            else:
                return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        logger.error(f"Tool execution error ({name}): {e}", exc_info=True)
        return json.dumps({"error": f"Tool '{name}' failed: {str(e)}"})


def _pick_preferred_knowledge_id(steps: list[dict]) -> str | None:
    """Extract the most likely KO ID from prior tool steps."""
    for step in reversed(steps):
        tool_name = step.get("tool")
        if tool_name == "get_knowledge_detail":
            result = step.get("result") or {}
            if isinstance(result, dict) and result.get("id"):
                return str(result["id"])
            args = step.get("args") or {}
            if isinstance(args, dict) and args.get("knowledge_id"):
                return str(args["knowledge_id"])

        if tool_name == "search_knowledge_base":
            result = step.get("result") or {}
            results = result.get("results") if isinstance(result, dict) else None
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict) and first.get("id"):
                    return str(first["id"])

    return None


def _ensure_sentence(text: str | None) -> str:
    """Normalize short text into a complete sentence."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


async def _build_grounded_answer(
    question: str,
    project_id: str | None,
    preferred_knowledge_id: str | None = None,
) -> dict | None:
    """Build a direct answer from stored KO detail plus linked sources."""
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.backboard.models import Event, KnowledgeEvent
    from app.backboard.store import get_knowledge_object, search_knowledge_objects
    from app.sense.knowledge_types import canonicalize_knowledge_type

    question_lower = question.lower()

    async with get_session_factory()() as db:
        candidate = None

        if preferred_knowledge_id:
            candidate = await get_knowledge_object(db, preferred_knowledge_id)

        if candidate is None:
            search_results = await search_knowledge_objects(
                db,
                query=question,
                project_id=project_id,
                limit=3,
            )
            if not search_results:
                return None

            top = search_results[0]
            runner_up_score = search_results[1].get("match_score", 0.0) if len(search_results) > 1 else 0.0
            top_score = top.get("match_score", 0.0)
            if top_score < 1.25 or (len(search_results) > 1 and top_score <= runner_up_score):
                return None

            candidate = await get_knowledge_object(db, top["id"])

        if not candidate:
            return None

        detail = candidate.detail or {}
        statement = ""
        rationale = ""
        if isinstance(detail, dict):
            statement = str(detail.get("statement") or "").strip()
            rationale = str(detail.get("rationale") or "").strip()

        primary_statement = _ensure_sentence(statement or candidate.summary or candidate.title)

        linked_event_result = await db.execute(
            select(Event, KnowledgeEvent)
            .join(KnowledgeEvent, KnowledgeEvent.event_id == Event.id)
            .where(KnowledgeEvent.knowledge_id == str(candidate.id))
            .order_by(Event.occurred_at.asc())
        )
        linked_events = linked_event_result.all()

        sources = [
            {
                "type": "knowledge_object",
                "id": str(candidate.id),
                "label": f"[{canonicalize_knowledge_type(candidate.type)}] {candidate.title}",
                "detail": candidate.summary or statement or "",
            }
        ]
        for event, link in linked_events[:4]:
            sources.append(
                {
                    "type": "event",
                    "id": str(event.id),
                    "label": f"[{link.relationship_ or event.source}] {event.actor_name or event.source}",
                    "detail": (event.content or "")[:300],
                }
            )

        if "why" in question_lower:
            if rationale:
                answer = f"{primary_statement} Because {rationale.rstrip('.')}."
            else:
                answer = (
                    f"{primary_statement} I found the decision, but the stored record does not include "
                    "an explicit rationale."
                )
        else:
            answer = primary_statement
            if rationale and ("what did we decide" in question_lower or "what change" in question_lower):
                answer += f" Reason noted: {rationale.rstrip('.')}."

        return {"answer": answer, "sources": sources}


async def run_query_agent(
    question: str,
    thread_id: str | None = None,
    project_id: str | None = None,
    mock_llm_tool_calls: list[dict] | None = None,
    mock_tool_results: dict | None = None,
    mock_final_answer: str | None = None,
) -> dict:
    """Run the investigative query agent.

    Uses a persistent Backboard thread so conversation history is maintained
    across messages. Returns dict with keys: answer, steps, thread_id.
    """
    steps = []
    tool_call_count = 0

    if mock_llm_tool_calls is not None:
        # Test mode
        for call in mock_llm_tool_calls:
            if tool_call_count >= MAX_TOOL_CALLS:
                break
            tool_call_count += 1
            name = call["name"]
            args = call.get("args", {})
            result_data = (mock_tool_results or {}).get(name, [])
            steps.append({"tool": name, "args": args, "result": result_data})

        return {
            "answer": mock_final_answer or "No answer available.",
            "steps": steps,
            "thread_id": thread_id,
        }

    import httpx

    try:
        from app.backboard.llm import backboard_llm

        # Ensure the chat assistant exists (cached after first call)
        logger.info("Creating/getting chat assistant...")
        assistant_id = await backboard_llm._get_or_create_assistant(
            "chat", system=QUERY_AGENT_SYSTEM_PROMPT, tools=QUERY_AGENT_TOOLS
        )

        # Use the caller-supplied thread or create a fresh one
        if not thread_id:
            logger.info("Creating new chat thread...")
            thread_id = await backboard_llm.create_thread(assistant_id)

        model_config = backboard_llm.MODELS["chat"]
        result = None
        current_content = question

        for iteration in range(MAX_TOOL_CALLS + 1):
            logger.info(f"Chat agent iteration {iteration}, sending to Backboard...")
            async with httpx.AsyncClient(timeout=120.0) as client:
                msg_resp = await client.post(
                    f"{backboard_llm.BACKBOARD_BASE}/threads/{thread_id}/messages",
                    headers=backboard_llm._headers(),
                    data={
                        "content": current_content,
                        "llm_provider": model_config["provider"],
                        "model_name": model_config["model"],
                        "stream": "false",
                    },
                )
                msg_resp.raise_for_status()
                result = msg_resp.json()

            status = result.get("status", "COMPLETED")
            tool_calls = result.get("tool_calls") or []

            if status == "REQUIRES_ACTION" and tool_calls:
                tool_outputs = []
                for tc in tool_calls:
                    if tool_call_count >= MAX_TOOL_CALLS:
                        break
                    tool_call_count += 1

                    func = tc.get("function", {})
                    func_name = func.get("name", "")
                    raw_args = func.get("parsed_arguments") or func.get("arguments") or {}
                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            raw_args = {}

                    logger.info(f"Chat agent tool: {func_name}({raw_args})")
                    tool_result = await _execute_tool(func_name, raw_args, project_id=project_id)

                    steps.append({
                        "tool": func_name,
                        "args": raw_args,
                        "result": json.loads(tool_result),
                    })
                    tool_outputs.append({
                        "tool_call_id": tc.get("id", ""),
                        "output": tool_result,
                    })

                run_id = result.get("run_id")
                if run_id and tool_outputs:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        submit_resp = await client.post(
                            f"{backboard_llm.BACKBOARD_BASE}/threads/{thread_id}/runs/{run_id}/submit-tool-outputs",
                            headers=backboard_llm._headers(),
                            json={"tool_outputs": tool_outputs},
                        )
                        submit_resp.raise_for_status()
                        result = submit_resp.json()

                # Subsequent iterations: thread already has the message
                current_content = ""
            else:
                break

        answer = (result or {}).get("content") or "I could not find relevant information to answer that question."
        grounded = await _build_grounded_answer(
            question=question,
            project_id=project_id,
            preferred_knowledge_id=_pick_preferred_knowledge_id(steps),
        )
        if grounded:
            answer = grounded["answer"]
            return {
                "answer": answer,
                "steps": steps,
                "thread_id": thread_id,
                "sources": grounded["sources"],
            }

        return {"answer": answer, "steps": steps, "thread_id": thread_id}

    except httpx.HTTPStatusError as e:
        logger.error(f"Backboard API HTTP error: {e.response.status_code} — {e.response.text}", exc_info=True)
        return await _fallback_db_search(question, thread_id, steps, "llm_http_error", project_id)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error(f"Backboard API connection error: {e}", exc_info=True)
        return await _fallback_db_search(question, thread_id, steps, "llm_unavailable", project_id)
    except Exception as e:
        logger.error(f"Chat agent unexpected error: {e}", exc_info=True)
        return await _fallback_db_search(question, thread_id, steps, "unexpected_error", project_id)


async def _fallback_db_search(
    question: str,
    thread_id: str | None,
    steps: list,
    error_type: str,
    project_id: str | None,
) -> dict:
    """Fallback: search the DB directly without LLM reasoning.

    Returns whatever KOs match the query so the user gets some data
    even when the LLM gateway is down. Produces a personable answer
    with detailed sources sent separately via the ``sources`` key.
    """
    logger.info(f"Running fallback DB search (reason: {error_type})")
    try:
        grounded = await _build_grounded_answer(
            question=question,
            project_id=project_id,
            preferred_knowledge_id=_pick_preferred_knowledge_id(steps),
        )
        if grounded:
            steps.append(
                {
                    "tool": "fallback_grounded_answer",
                    "args": {"query": question},
                    "result": {"sources": len(grounded["sources"])},
                }
            )
            return {
                "answer": grounded["answer"],
                "steps": steps,
                "thread_id": thread_id,
                "sources": grounded["sources"],
            }

        ko_result = await _execute_tool(
            "search_knowledge_base",
            {"query": question, "limit": 5},
            project_id=project_id,
        )
        event_result = await _execute_tool(
            "search_raw_events",
            {"query": question, "limit": 5},
            project_id=project_id,
        )

        ko_data = json.loads(ko_result).get("results", [])
        event_data = json.loads(event_result).get("results", [])

        steps.append({"tool": "fallback_search", "args": {"query": question}, "result": {"kos": len(ko_data), "events": len(event_data)}})

        # Build a personable answer (visible text)
        if ko_data:
            # Summarize the top results conversationally
            ko_summaries = []
            for ko in ko_data[:3]:
                ko_type = ko.get("type", "item")
                title = ko.get("title", "Untitled")
                summary = ko.get("summary", "")
                if summary:
                    ko_summaries.append(f"**{title}** — {summary}")
                else:
                    ko_summaries.append(f"**{title}** ({ko_type})")

            if len(ko_data) == 1:
                answer = f"I found one relevant {ko_data[0].get('type', 'item')} in the knowledge base:\n\n" + ko_summaries[0]
            else:
                answer = f"I found {len(ko_data)} relevant items in the knowledge base:\n\n" + "\n\n".join(ko_summaries)
                if len(ko_data) > 3:
                    answer += f"\n\n...and {len(ko_data) - 3} more. Check the sources below for details."
        elif event_data:
            answer = "I didn't find any structured decisions matching your query, but I found some related raw events that might help. See the sources below."
        else:
            answer = "I wasn't able to find anything matching your query in the knowledge base or raw events. Try rephrasing or check back after more data has been ingested."

        # Build sources list (hidden behind toggle on frontend)
        sources = []
        for ko in ko_data:
            sources.append({
                "type": "knowledge_object",
                "id": ko.get("id", ""),
                "label": f"[{ko.get('type', 'unknown')}] {ko.get('title', 'Untitled')}",
                "detail": ko.get("summary", ""),
            })
        for ev in event_data:
            sources.append({
                "type": "event",
                "id": ev.get("id", ""),
                "label": f"[{ev.get('source', 'unknown')}] {ev.get('actor_name') or 'Unknown'}",
                "detail": (ev.get("content") or "")[:300],
            })

    except Exception as fallback_err:
        logger.error(f"Fallback DB search also failed: {fallback_err}", exc_info=True)
        answer = "The AI assistant is temporarily unavailable. Please try again in a moment."
        sources = []

    return {"answer": answer, "steps": steps, "thread_id": thread_id, "sources": sources}
