from sqlalchemy import Column, String, Numeric, DateTime, Boolean, Enum, Text, Integer, Index, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum

from app.db.base import Base


class RecommendationType(str, enum.Enum):
    RESERVED_INSTANCES = "reserved_instances"
    SAVINGS_PLANS = "savings_plans"
    RIGHT_SIZING = "right_sizing"
    STORAGE_OPTIMIZATION = "storage_optimization"
    COMPUTE_OPTIMIZATION = "compute_optimization"
    CLEANUP = "cleanup"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(str, enum.Enum):
    PENDING = "pending"
    APPLIED = "applied"
    DISMISSED = "dismissed"
    SCHEDULED = "scheduled"


class Impact(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(String(12), nullable=False, index=True)
    region = Column(String(20), nullable=False, index=True)

    # Recommendation details
    type = Column(Enum(RecommendationType), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)

    # Resource information
    resource_id = Column(String(200), nullable=True)
    resource_arn = Column(String(500), nullable=True)
    resource_type = Column(String(100), nullable=True)

    # Financial impact
    monthly_savings = Column(Numeric(10, 2), nullable=False)
    annual_savings = Column(Numeric(10, 2), nullable=False)
    implementation_cost = Column(Numeric(10, 2), nullable=True)

    # Risk and complexity assessment
    complexity = Column(Integer, nullable=False)  # 1-5 scale
    risk_level = Column(Enum(RiskLevel), nullable=False)
    confidence = Column(Integer, nullable=False)  # 0-100
    impact = Column(Enum(Impact), nullable=False)

    # Status tracking
    status = Column(Enum(RecommendationStatus), nullable=False, default=RecommendationStatus.PENDING)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissal_reason = Column(Text, nullable=True)

    # Scheduling
    scheduled_for = Column(DateTime(timezone=True), nullable=True)

    # Metadata and tags
    tags = Column(ARRAY(String), nullable=True)
    metadata = Column(JSONB, nullable=True)  # Store implementation details, AWS API calls needed
    prerequisites = Column(JSONB, nullable=True)  # What needs to be done first

    # Analysis data
    analysis_data = Column(JSONB, nullable=True)  # Store the data used to generate recommendation
    baseline_metrics = Column(JSONB, nullable=True)  # Current state metrics

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # When recommendation becomes stale

    __table_args__ = (
        Index('ix_recommendation_account_type', 'account_id', 'type'),
        Index('ix_recommendation_status_savings', 'status', 'monthly_savings'),
        Index('ix_recommendation_risk_complexity', 'risk_level', 'complexity'),
        Index('ix_recommendation_active', 'status', 'expires_at'),
    )

    def __repr__(self):
        return f"<Recommendation {self.type} ${self.monthly_savings}/mo {self.status}>"


class RecommendationHistory(Base):
    __tablename__ = "recommendation_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # applied, dismissed, updated
    user_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<RecommendationHistory {self.action} {self.created_at}>"