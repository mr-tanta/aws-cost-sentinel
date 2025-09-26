from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal


class ServiceCostItem(BaseModel):
    """Individual service cost item"""
    service: str
    cost: float
    percentage: Optional[float] = None
    record_count: Optional[int] = None


class CostTrendItem(BaseModel):
    """Individual cost trend data point"""
    date: str
    cost: float


class CostForecastItem(BaseModel):
    """Individual forecast data point"""
    date: str
    projected_cost: float
    confidence: float = Field(ge=0.0, le=1.0)


class CostSummaryResponse(BaseModel):
    """Cost summary response schema"""
    total_cost: float
    previous_period_cost: float
    change_percent: float
    period_start: str
    period_end: str
    top_services: List[ServiceCostItem]

    class Config:
        json_encoders = {
            Decimal: float
        }


class CostTrendResponse(BaseModel):
    """Cost trends response schema"""
    trends: List[CostTrendItem]
    granularity: str
    period_start: str
    period_end: str

    class Config:
        json_encoders = {
            Decimal: float
        }


class CostBreakdownResponse(BaseModel):
    """Cost breakdown response schema"""
    services: List[ServiceCostItem]
    total_cost: float
    period_start: str
    period_end: str

    class Config:
        json_encoders = {
            Decimal: float
        }


class ServiceCostResponse(BaseModel):
    """Service-specific cost response"""
    service: str
    total_cost: float
    daily_breakdown: List[CostTrendItem]
    percentage_of_total: float

    class Config:
        json_encoders = {
            Decimal: float
        }


class CostForecastResponse(BaseModel):
    """Cost forecast response schema"""
    forecast: List[CostForecastItem]
    total_projected_cost: float
    forecast_period_days: int
    based_on_days: int
    trend_factor: float

    class Config:
        json_encoders = {
            Decimal: float
        }


class CostSyncRequest(BaseModel):
    """Request schema for cost data sync"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    force_refresh: bool = False


class CostSyncResponse(BaseModel):
    """Response schema for cost data sync"""
    records_processed: int
    start_date: str
    end_date: str
    processing_time_seconds: Optional[float] = None


class CostComparisonRequest(BaseModel):
    """Request schema for cost comparison"""
    account_ids: List[str] = Field(min_items=1, max_items=10)
    start_date: date
    end_date: date
    granularity: str = Field(default="DAILY", regex="^(DAILY|WEEKLY|MONTHLY)$")


class AccountCostComparison(BaseModel):
    """Cost comparison for a single account"""
    account_id: str
    account_name: str
    total_cost: float
    daily_average: float
    top_services: List[ServiceCostItem]


class CostComparisonResponse(BaseModel):
    """Cost comparison response schema"""
    accounts: List[AccountCostComparison]
    period_start: str
    period_end: str
    total_cost_all_accounts: float

    class Config:
        json_encoders = {
            Decimal: float
        }


class CostAlertThreshold(BaseModel):
    """Cost alert threshold configuration"""
    threshold_type: str = Field(regex="^(DAILY|WEEKLY|MONTHLY|TOTAL)$")
    amount: float = Field(gt=0)
    comparison: str = Field(default="GREATER_THAN", regex="^(GREATER_THAN|PERCENTAGE_INCREASE)$")
    enabled: bool = True


class CostAlertRequest(BaseModel):
    """Request schema for setting up cost alerts"""
    name: str = Field(max_length=100)
    description: Optional[str] = Field(max_length=500)
    account_id: Optional[str] = None  # None means all accounts
    service: Optional[str] = None     # None means all services
    thresholds: List[CostAlertThreshold] = Field(min_items=1)


class CostAlertResponse(BaseModel):
    """Cost alert configuration response"""
    id: str
    name: str
    description: Optional[str]
    account_id: Optional[str]
    service: Optional[str]
    thresholds: List[CostAlertThreshold]
    is_active: bool
    created_at: str
    updated_at: str


class CostOptimizationSuggestion(BaseModel):
    """Cost optimization suggestion"""
    category: str = Field(regex="^(RIGHTSIZING|RESERVED_INSTANCES|STORAGE|NETWORKING|SCHEDULING)$")
    service: str
    resource_id: Optional[str]
    current_cost: float
    potential_savings: float
    confidence: float = Field(ge=0.0, le=1.0)
    effort_level: str = Field(regex="^(LOW|MEDIUM|HIGH)$")
    description: str
    action_required: str


class CostOptimizationResponse(BaseModel):
    """Cost optimization recommendations response"""
    suggestions: List[CostOptimizationSuggestion]
    total_potential_savings: float
    analyzed_period_days: int
    account_id: Optional[str]

    class Config:
        json_encoders = {
            Decimal: float
        }