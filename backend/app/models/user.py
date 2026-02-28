import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.database import Base

UUID_TYPE = String(36)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID_TYPE, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    hashed_password = Column(String(255), nullable=False)
    team_id = Column(UUID_TYPE, ForeignKey("teams.id"), nullable=True)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    chat_thread_id = Column(String(255), nullable=True)  # Backboard thread for persistent chat

    team = relationship("Team", back_populates="users")
