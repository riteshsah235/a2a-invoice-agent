import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    JSON,
    UniqueConstraint,
    Index,
)
from app.database import Base


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(String(128), primary_key=True, index=True)
    principal_id = Column(String(128), nullable=False, index=True)
    context_id = Column(String(128), nullable=False, index=True)
    state = Column(String(64), nullable=False, default="TASK_STATE_INPUT_REQUIRED")
    batch_id = Column(String(128), nullable=True)
    policy_revision = Column(String(64), nullable=True)
    
    # Stored lists of message dicts and artifact dicts
    history_json = Column(JSON, nullable=False, default=list)
    artifacts_json = Column(JSON, nullable=False, default=list)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_tasks_principal_task", "principal_id", "id"),
    )


class IdempotencyModel(Base):
    __tablename__ = "idempotency_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    principal_id = Column(String(128), nullable=False)
    message_id = Column(String(128), nullable=False)
    fingerprint = Column(String(64), nullable=False)  # SHA-256 hex
    task_id = Column(String(128), nullable=False)
    response_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("principal_id", "message_id", name="uq_principal_message_id"),
        Index("ix_idempotency_lookup", "principal_id", "message_id"),
    )


class PackageDecisionCacheModel(Base):
    __tablename__ = "package_decision_cache"

    package_hash = Column(String(64), primary_key=True)  # Canonical SHA-256 of package
    action = Column(String(64), nullable=False)
    facts_json = Column(JSON, nullable=False)
    evidence_refs_json = Column(JSON, nullable=False)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProposalModel(Base):
    __tablename__ = "task_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    principal_id = Column(String(128), nullable=False, index=True)
    task_id = Column(String(128), nullable=False, index=True)
    context_id = Column(String(128), nullable=False)
    batch_id = Column(String(128), nullable=False)
    package_id = Column(String(128), nullable=False)
    action_id = Column(String(128), nullable=False)
    action = Column(String(64), nullable=False)
    facts_json = Column(JSON, nullable=False)
    evidence_refs_json = Column(JSON, nullable=False)
    rationale = Column(Text, nullable=False)
    
    # Continuation outcome when processed
    outcome = Column(String(32), nullable=True)  # ACCEPTED / REJECTED
    receipt_nonce = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_proposal_lookup", "task_id", "package_id", "action_id"),
    )
