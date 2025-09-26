from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum

from app.db.base import Base


class AWSAccountStatus(str, enum.Enum):
    CONNECTED = "connected"
    ERROR = "error"
    PENDING = "pending"
    SYNCING = "syncing"


class AWSAccount(Base):
    __tablename__ = "aws_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    account_id = Column(String(12), nullable=False, unique=True, index=True)
    region = Column(String(20), nullable=False)
    role_arn = Column(String, nullable=True)
    external_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    status = Column(Enum(AWSAccountStatus), default=AWSAccountStatus.PENDING)
    error_message = Column(Text, nullable=True)
    last_sync = Column(DateTime(timezone=True), nullable=True)
    sync_metadata = Column(JSONB, nullable=True)  # Store sync progress, stats, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<AWSAccount {self.account_id} ({self.name})>"