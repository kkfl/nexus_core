import datetime
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


class CarrierTarget(Base):
    """
    Configured connection to a provider boundary.
    Contains aliases for secret credentials to fetch from secrets_agent.
    """

    __tablename__ = "carrier_targets"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(100), nullable=False, index=True)
    env = Column(String(20), nullable=False, default="prod", index=True)

    name = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)  # twilio, mock
    enabled = Column(Boolean, nullable=False, default=True)

    credential_aliases = Column(JSON, nullable=False, default=dict)
    default_region = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "env", "name", name="uq_carrier_target_name_tenant"),
    )


class CarrierDidInventory(Base):
    """
    DIDs currently or historically provisioned on a carrier target.
    """

    __tablename__ = "carrier_did_inventory"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(100), nullable=False, index=True)
    env = Column(String(20), nullable=False, default="prod")
    carrier_target_id = Column(
        String(36), ForeignKey("carrier_targets.id", ondelete="CASCADE"), nullable=False
    )

    number = Column(String(50), nullable=False, index=True)  # E.164
    provider_sid = Column(String(100), nullable=True)  # Provider's internal ID

    capabilities = Column(
        JSON, nullable=False, default=dict
    )  # {"voice": True, "sms": False, "mms": False}
    status = Column(String(50), nullable=False, default="active")  # active, released

    purchased_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    released_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("carrier_target_id", "number", name="uq_carrier_did_number_target"),
    )


class CarrierTrunkRecord(Base):
    """
    SIP Trunk configurations.
    """

    __tablename__ = "carrier_trunk_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(100), nullable=False, index=True)
    env = Column(String(20), nullable=False, default="prod")
    carrier_target_id = Column(
        String(36), ForeignKey("carrier_targets.id", ondelete="CASCADE"), nullable=False
    )

    trunk_id = Column(String(100), nullable=False)  # Provider's internal ID
    friendly_name = Column(String(255), nullable=False)
    termination_sip_domain = Column(String(255), nullable=True)

    status = Column(String(50), nullable=False, default="active")
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("carrier_target_id", "trunk_id", name="uq_carrier_trunk_id_target"),
    )


class CarrierJob(Base):
    """
    Enqueued mutation jobs for background runner.
    """

    __tablename__ = "carrier_jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(100), nullable=False, index=True)
    env = Column(String(20), nullable=False, default="prod")
    carrier_target_id = Column(
        String(36), ForeignKey("carrier_targets.id", ondelete="CASCADE"), nullable=False
    )

    action = Column(String(100), nullable=False)  # purchase_did, release_did, update_trunk
    payload_redacted = Column(JSON, nullable=False, default=dict)

    status = Column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, running, succeeded, failed
    error_redacted = Column(Text, nullable=True)

    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True, index=True)

    correlation_id = Column(String(100), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class CarrierJobResult(Base):
    """
    Output summary of a completed CarrierJob.
    """

    __tablename__ = "carrier_job_results"

    job_id = Column(String(36), ForeignKey("carrier_jobs.id", ondelete="CASCADE"), primary_key=True)
    output_summary_safe = Column(JSON, nullable=False, default=dict)
    completed_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)


class CarrierAuditEvent(Base):
    """
    Immutable audit log for all state lifecycle transitions.
    """

    __tablename__ = "carrier_audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    env = Column(String(20), nullable=False, default="prod", index=True)

    correlation_id = Column(String(100), nullable=True, index=True)
    service_id = Column(String(100), nullable=False)  # Calling service
    action = Column(String(100), nullable=False)
    result = Column(String(50), nullable=False)  # success, denied, failed
    reason = Column(Text, nullable=True)
    target_id = Column(String(36), nullable=True)

    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
