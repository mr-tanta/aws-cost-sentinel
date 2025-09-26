from sqlalchemy import Column, String, Numeric, Date, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class CostData(Base):
    __tablename__ = "cost_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(String(12), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    service = Column(String(100), nullable=False, index=True)
    region = Column(String(20), nullable=False, index=True)
    usage_type = Column(String(200), nullable=True)
    operation = Column(String(200), nullable=True)
    cost = Column(Numeric(12, 4), nullable=False)
    usage_amount = Column(Numeric(15, 6), nullable=True)
    usage_unit = Column(String(50), nullable=True)

    # Store additional metadata like tags, dimensions
    dimensions = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Composite indexes for better query performance
    __table_args__ = (
        Index('ix_cost_data_account_date', 'account_id', 'date'),
        Index('ix_cost_data_service_date', 'service', 'date'),
        Index('ix_cost_data_account_service_date', 'account_id', 'service', 'date'),
        Index('ix_cost_data_region_date', 'region', 'date'),
    )

    def __repr__(self):
        return f"<CostData {self.account_id} {self.service} {self.date} ${self.cost}>"


class CostSummary(Base):
    __tablename__ = "cost_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(String(12), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    period_type = Column(String(20), nullable=False)  # daily, monthly, yearly
    total_cost = Column(Numeric(12, 4), nullable=False)

    # Service breakdown
    services_breakdown = Column(JSONB, nullable=True)
    regions_breakdown = Column(JSONB, nullable=True)

    # Trends and comparisons
    previous_period_cost = Column(Numeric(12, 4), nullable=True)
    cost_change_percentage = Column(Numeric(5, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_cost_summary_account_date_period', 'account_id', 'date', 'period_type'),
    )

    def __repr__(self):
        return f"<CostSummary {self.account_id} {self.date} {self.period_type} ${self.total_cost}>"