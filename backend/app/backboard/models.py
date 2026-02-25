"""Backboard layer models: events, knowledge objects, verification checks, merges."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Float, ForeignKey, Index, LargeBinary, String, Text, JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base

# Use String(36) for UUIDs — portable across SQLite and PostgreSQL.
# In production PostgreSQL, Alembic migration uses native UUID type.
UUID_TYPE = String(36)


def new_uuid():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID_TYPE, primary_key=True, default=new_uuid)
    source = Column(String(50), nullable=False)
    source_id = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    actor_email = Column(String(255))
    actor_name = Column(String(255))
    content = Column(Text)
    metadata_ = Column("metadata", JSON)
    raw_payload = Column(JSON)
    embedding = Column(LargeBinary, nullable=True)  # Stored as bytes; pgvector in production
    occurred_at = Column(String, nullable=False)
    ingested_at = Column(String, default=now_iso)
    project_id = Column(UUID_TYPE, ForeignKey("projects.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_events_source_source_id"),
    )

    knowledge_links = relationship("KnowledgeEvent", back_populates="event")


class KnowledgeObject(Base):
    __tablename__ = "knowledge_objects"

    id = Column(UUID_TYPE, primary_key=True, default=new_uuid)
    type = Column(String(50), nullable=False, default="decision")
    title = Column(String(500), nullable=False)
    summary = Column(Text)
    detail = Column(JSON)
    participants = Column(JSON)
    tags = Column(JSON)  # Stored as JSON array; ARRAY(Text) in production PG
    confidence = Column(Float, nullable=False, default=0.0)
    status = Column(String(50), default="active")
    embedding = Column(LargeBinary, nullable=True)
    detected_at = Column(String, default=now_iso)
    occurred_at = Column(String)
    project_id = Column(UUID_TYPE, ForeignKey("projects.id"), nullable=True)
    reviewed = Column(Boolean, default=False)
    reviewed_by = Column(String(255))
    reviewed_at = Column(String)

    event_links = relationship("KnowledgeEvent", back_populates="knowledge_object")
    verification_checks = relationship("VerificationCheck", back_populates="knowledge_object")


class KnowledgeEvent(Base):
    __tablename__ = "knowledge_events"

    knowledge_id = Column(
        UUID_TYPE, ForeignKey("knowledge_objects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id = Column(
        UUID_TYPE, ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relevance = Column(Float, default=1.0)
    relationship_ = Column("relationship", String(100))

    knowledge_object = relationship("KnowledgeObject", back_populates="event_links")
    event = relationship("Event", back_populates="knowledge_links")


class VerificationCheck(Base):
    __tablename__ = "verification_checks"

    id = Column(UUID_TYPE, primary_key=True, default=new_uuid)
    knowledge_id = Column(
        UUID_TYPE, ForeignKey("knowledge_objects.id", ondelete="CASCADE"),
    )
    description = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    evidence = Column(Text)
    suggestion = Column(Text)
    event_id = Column(UUID_TYPE, ForeignKey("events.id"), nullable=True)
    checked_at = Column(String, default=now_iso)

    knowledge_object = relationship("KnowledgeObject", back_populates="verification_checks")


class KnowledgeMerge(Base):
    __tablename__ = "knowledge_merges"

    id = Column(UUID_TYPE, primary_key=True, default=new_uuid)
    primary_id = Column(UUID_TYPE, ForeignKey("knowledge_objects.id"))
    merged_id = Column(UUID_TYPE)
    merge_score = Column(Float)
    merged_at = Column(String, default=now_iso)
