import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base

UUID_TYPE = String(36)


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID_TYPE, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    team_id = Column(UUID_TYPE, ForeignKey("teams.id"), nullable=True)

    team = relationship("Team", back_populates="projects")
