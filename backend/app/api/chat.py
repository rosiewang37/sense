"""Chat API: streaming investigative agent responses."""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.sense.agents.investigator import run_query_agent

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatQuery(BaseModel):
    question: str
    project_id: str | None = None


@router.post("")
async def chat_query(
    query: ChatQuery,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream agent investigation + answer via SSE."""

    async def generate():
        # Run the query agent
        result = await run_query_agent(
            question=query.question,
            project_id=query.project_id,
        )

        # Stream agent steps
        for step in result.get("steps", []):
            yield json.dumps({
                "type": "agent_step",
                "tool": step["tool"],
                "status": "complete",
                "result_preview": str(step.get("result", ""))[:200],
            }) + "\n"

        # Stream final answer
        answer = result.get("answer", "")
        yield json.dumps({
            "type": "text",
            "content": answer,
        }) + "\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/history")
async def chat_history(
    project_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for current project."""
    from sqlalchemy import select
    from app.models.chat import ChatMessage

    query = select(ChatMessage).where(ChatMessage.user_id == str(current_user.id))
    if project_id:
        query = query.where(ChatMessage.project_id == project_id)
    query = query.order_by(ChatMessage.created_at.desc()).limit(50)

    result = await db.execute(query)
    messages = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "agent_reasoning": m.agent_reasoning,
            "sources": m.sources,
            "created_at": m.created_at,
        }
        for m in reversed(messages)
    ]
