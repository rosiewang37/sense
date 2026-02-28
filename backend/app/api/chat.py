"""Chat API: investigative agent with persistent history via Backboard threads."""
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.chat import ChatMessage
from app.models.user import User
from app.sense.agents.investigator import run_query_agent

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatQuery(BaseModel):
    question: str
    project_id: str | None = None


@router.post("")
async def chat_query(
    query: ChatQuery,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run investigative agent and stream the response via SSE.

    Uses the user's persistent Backboard thread so conversation history
    is maintained across page navigations and sessions.
    """

    async def generate():
        # Save user message to DB
        user_msg = ChatMessage(
            user_id=str(current_user.id),
            project_id=query.project_id,
            role="user",
            content=query.question,
        )
        db.add(user_msg)
        await db.commit()

        try:
            result = await run_query_agent(
                question=query.question,
                thread_id=current_user.chat_thread_id,
                project_id=query.project_id,
            )

            # Persist the Backboard thread_id on the user for future calls
            returned_thread_id = result.get("thread_id")
            if returned_thread_id and returned_thread_id != current_user.chat_thread_id:
                current_user.chat_thread_id = returned_thread_id
                await db.commit()

            # Stream agent steps
            steps = result.get("steps", [])
            for step in steps:
                yield json.dumps({
                    "type": "agent_step",
                    "tool": step["tool"],
                    "status": "complete",
                    "result_preview": str(step.get("result", ""))[:200],
                }) + "\n"

            # Stream final answer
            answer = result.get("answer", "")
            yield json.dumps({"type": "text", "content": answer}) + "\n"

            # Save assistant response to DB
            agent_msg = ChatMessage(
                user_id=str(current_user.id),
                project_id=query.project_id,
                role="assistant",
                content=answer,
                agent_reasoning=steps if steps else None,
            )
            db.add(agent_msg)
            await db.commit()

        except Exception as e:
            logger.error(f"Chat agent error: {e}", exc_info=True)
            # Surface a categorized error hint so the user knows what failed
            import httpx
            if isinstance(e, httpx.HTTPStatusError):
                hint = f"LLM service returned an error (HTTP {e.response.status_code}). The team has been notified."
            elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
                hint = "Could not reach the AI service. Please try again in a moment."
            elif isinstance(e, ValueError) and "Backboard" in str(e):
                hint = f"AI service configuration error: {e}"
            else:
                hint = f"An unexpected error occurred: {type(e).__name__}. Check backend logs for details."
            yield json.dumps({"type": "text", "content": f"Sorry, something went wrong while investigating. {hint}"}) + "\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/history")
async def chat_history(
    project_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent chat history for the current user."""
    q = (
        select(ChatMessage)
        .where(ChatMessage.user_id == str(current_user.id))
        .order_by(ChatMessage.created_at.desc())
        .limit(100)
    )
    if project_id:
        q = q.where(ChatMessage.project_id == project_id)

    result = await db.execute(q)
    messages = list(reversed(result.scalars().all()))

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "agent_reasoning": m.agent_reasoning,
            "sources": m.sources,
            "created_at": m.created_at,
        }
        for m in messages
    ]
