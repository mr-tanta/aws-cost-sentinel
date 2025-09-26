from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    DISMISSED = "dismissed"


class CostData(BaseModel):
    date: str
    total_cost: float
    services: Dict[str, float]
    tags: Dict[str, str]
    region: Optional[str] = None
    account_id: Optional[str] = None


class CostSummary(BaseModel):
    current_month: float
    last_month: float
    projected: float
    savings_potential: float
    trend_percentage: float


class ServiceCost(BaseModel):
    service: str
    cost: float
    percentage: float
    trend: float


class WasteItem(BaseModel):
    id: str
    resource_type: str
    resource_id: str
    monthly_cost: float
    detected_at: datetime
    remediated: bool
    action: str
    description: Optional[str] = None


class Recommendation(BaseModel):
    id: str
    type: str
    resource_id: str
    title: str
    description: str
    monthly_savings: float
    complexity: int
    risk_level: RiskLevel
    status: RecommendationStatus
    created_at: datetime


class AnomalyAlert(BaseModel):
    id: str
    type: str
    service: str
    current_cost: float
    expected_cost: float
    deviation_percentage: float
    detected_at: datetime
    resolved: bool