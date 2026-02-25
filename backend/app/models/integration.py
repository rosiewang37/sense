import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.database import Base

UUID_TYPE = String(36)


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(UUID_TYPE, primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(UUID_TYPE, ForeignKey("teams.id"), nullable=True)
    source = Column(String(50), nullable=False)
    credentials = Column(JSON)
    config = Column(JSON)
    status = Column(String(50), default="active")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())

    team = relationship("Team", back_populates="integrations")
