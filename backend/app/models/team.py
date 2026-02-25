import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.database import Base

UUID_TYPE = String(36)


class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID_TYPE, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())

    projects = relationship("Project", back_populates="team")
    users = relationship("User", back_populates="team")
    integrations = relationship("Integration", back_populates="team")
