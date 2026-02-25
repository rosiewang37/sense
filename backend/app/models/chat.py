import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, JSON, String, Text

from app.database import Base

UUID_TYPE = String(36)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID_TYPE, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID_TYPE, ForeignKey("users.id"), nullable=True)
    project_id = Column(UUID_TYPE, ForeignKey("projects.id"), nullable=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    agent_reasoning = Column(JSON)
    sources = Column(JSON)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
