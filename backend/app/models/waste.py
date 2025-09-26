from sqlalchemy import Column, String, Numeric, DateTime, Boolean, Enum, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum

from app.db.base import Base


class WasteResourceType(str, enum.Enum):
    EBS_VOLUME = "ebs_volume"
    ELASTIC_IP = "elastic_ip"
    EC2_INSTANCE = "ec2_instance"
    RDS_INSTANCE = "rds_instance"
    LOAD_BALANCER = "load_balancer"
    EBS_SNAPSHOT = "ebs_snapshot"
    S3_BUCKET = "s3_bucket"


class WasteSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WasteItem(Base):
    __tablename__ = "waste_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(String(12), nullable=False, index=True)
    region = Column(String(20), nullable=False, index=True)
    resource_type = Column(Enum(WasteResourceType), nullable=False, index=True)
    resource_id = Column(String(200), nullable=False, index=True)
    resource_arn = Column(String(500), nullable=True)

    # Cost information
    monthly_cost = Column(Numeric(10, 2), nullable=False)
    annual_cost = Column(Numeric(10, 2), nullable=False)

    # Waste details
    severity = Column(Enum(WasteSeverity), nullable=False, default=WasteSeverity.MEDIUM)
    action = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    # Status tracking
    is_remediated = Column(Boolean, default=False)
    remediated_at = Column(DateTime(timezone=True), nullable=True)
    is_dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissal_reason = Column(Text, nullable=True)

    # Scheduling
    is_scheduled = Column(Boolean, default=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    resource_metadata = Column(JSONB, nullable=True)  # Store AWS resource details
    tags = Column(JSONB, nullable=True)
    detection_metadata = Column(JSONB, nullable=True)  # How/when it was detected

    # Timestamps
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_checked = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_waste_account_resource_type', 'account_id', 'resource_type'),
        Index('ix_waste_severity_cost', 'severity', 'monthly_cost'),
        Index('ix_waste_status_active', 'is_remediated', 'is_dismissed'),
    )

    def __repr__(self):
        return f"<WasteItem {self.resource_type} {self.resource_id} ${self.monthly_cost}/mo>"