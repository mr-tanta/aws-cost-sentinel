from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.models.waste import WasteCategory, WasteStatus


class WasteItemBase(BaseModel):
    """Base waste item schema"""
    resource_id: str = Field(max_length=255)
    resource_type: str = Field(max_length=100)
    category: WasteCategory
    description: str = Field(max_length=1000)
    estimated_monthly_savings: float = Field(ge=0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    region: str = Field(max_length=50)
    service: str = Field(max_length=100)
    resource_details: Optional[Dict[str, Any]] = None


class WasteItemCreate(WasteItemBase):
    """Waste item creation schema"""
    account_id: UUID
    status: WasteStatus = WasteStatus.DETECTED


class WasteItemUpdate(BaseModel):
    """Waste item update schema"""
    status: Optional[WasteStatus] = None
    notes: Optional[str] = None
    estimated_monthly_savings: Optional[float] = Field(None, ge=0)
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)

    class Config:
        orm_mode = True


class WasteItemResponse(WasteItemBase):
    """Waste item response schema"""
    id: UUID
    account_id: UUID
    status: WasteStatus
    detected_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None
    is_active: bool

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {
            Decimal: float
        }


class WasteCategoryInfo(BaseModel):
    """Waste category information"""
    value: str
    name: str
    description: str


class WasteCategoriesResponse(BaseModel):
    """Available waste categories response"""
    categories: List[WasteCategoryInfo]


class WasteScanRequest(BaseModel):
    """Waste scan request schema"""
    account_id: UUID
    categories: Optional[List[WasteCategory]] = None
    force_rescan: bool = False


class WasteScanResult(BaseModel):
    """Individual account waste scan result"""
    account_id: str
    account_name: str
    status: str  # "success", "error", "partial"
    items_found: int = 0
    items_created: int = 0
    items_updated: int = 0
    categories_scanned: List[str] = []
    scan_duration_seconds: Optional[float] = None
    error_message: Optional[str] = None


class WasteDetectionResponse(BaseModel):
    """Waste detection scan response"""
    scan_id: str
    account_id: str
    status: str
    items_found: int
    categories_scanned: List[str]
    scan_started_at: datetime
    scan_completed_at: Optional[datetime]
    error_message: Optional[str] = None


class WasteBulkScanResponse(BaseModel):
    """Bulk waste scan response"""
    accounts_scanned: int
    successful_scans: int
    failed_scans: int
    total_waste_items_found: int
    scan_results: List[WasteScanResult]


class WasteCategoryBreakdown(BaseModel):
    """Waste breakdown by category"""
    count: int
    potential_savings: float
    avg_confidence: float


class WasteStatusBreakdown(BaseModel):
    """Waste breakdown by status"""
    detected: int = 0
    acknowledged: int = 0
    in_progress: int = 0
    resolved: int = 0
    dismissed: int = 0
    false_positive: int = 0


class TopWasteItem(BaseModel):
    """Top waste item summary"""
    id: str
    category: str
    resource_id: str
    description: str
    potential_savings: float
    confidence: float


class WasteSummaryResponse(BaseModel):
    """Waste summary response schema"""
    total_waste_items: int
    total_potential_monthly_savings: float
    analysis_period_days: int
    category_breakdown: Dict[str, WasteCategoryBreakdown]
    status_breakdown: Dict[str, int]
    top_waste_items: List[TopWasteItem]

    class Config:
        json_encoders = {
            Decimal: float
        }


class ResourceUtilizationMetric(BaseModel):
    """Resource utilization metrics"""
    metric_name: str
    current_value: float
    threshold_value: float
    unit: str
    period_days: int
    is_underutilized: bool


class WasteItemDetail(BaseModel):
    """Detailed waste item information"""
    id: UUID
    resource_id: str
    resource_type: str
    category: WasteCategory
    status: WasteStatus
    description: str
    estimated_monthly_savings: float
    confidence_score: float
    detected_at: datetime
    region: str
    service: str
    account_name: str
    resource_details: Optional[Dict[str, Any]]
    utilization_metrics: Optional[List[ResourceUtilizationMetric]]
    remediation_steps: Optional[List[str]]
    notes: Optional[str]
    tags: Optional[Dict[str, str]]

    class Config:
        orm_mode = True
        from_attributes = True


class WasteFilterOptions(BaseModel):
    """Available filter options for waste items"""
    categories: List[WasteCategoryInfo]
    statuses: List[str]
    services: List[str]
    regions: List[str]
    accounts: List[Dict[str, str]]  # id, name pairs


class WasteItemsListResponse(BaseModel):
    """Paginated waste items list response"""
    items: List[WasteItemResponse]
    total_count: int
    page: int
    pages: int
    filters_applied: Dict[str, Any]

    class Config:
        json_encoders = {
            Decimal: float
        }


class WasteRemediationAction(BaseModel):
    """Waste remediation action"""
    action_type: str = Field(regex="^(DELETE|STOP|RESIZE|MODIFY|SCHEDULE)$")
    description: str
    estimated_time_minutes: int
    risk_level: str = Field(regex="^(LOW|MEDIUM|HIGH)$")
    requires_approval: bool = False
    automation_available: bool = False


class WasteRemediationPlan(BaseModel):
    """Waste remediation plan"""
    waste_item_id: UUID
    actions: List[WasteRemediationAction]
    total_estimated_savings: float
    total_estimated_time_minutes: int
    overall_risk_level: str
    prerequisites: Optional[List[str]] = None
    warnings: Optional[List[str]] = None


class WasteRemediationRequest(BaseModel):
    """Waste remediation execution request"""
    waste_item_ids: List[UUID] = Field(min_items=1, max_items=50)
    approve_high_risk: bool = False
    execution_mode: str = Field(default="DRY_RUN", regex="^(DRY_RUN|EXECUTE)$")
    notification_email: Optional[str] = None


class WasteRemediationResult(BaseModel):
    """Waste remediation execution result"""
    waste_item_id: UUID
    status: str  # "success", "failed", "skipped"
    actions_completed: List[str]
    actual_savings: Optional[float] = None
    execution_time_minutes: Optional[float] = None
    error_message: Optional[str] = None


class WasteRemediationSummary(BaseModel):
    """Waste remediation execution summary"""
    execution_id: str
    total_items: int
    successful_remediations: int
    failed_remediations: int
    skipped_remediations: int
    total_savings_realized: float
    execution_started_at: datetime
    execution_completed_at: Optional[datetime]
    results: List[WasteRemediationResult]


class WasteTrendData(BaseModel):
    """Waste trend data point"""
    date: str
    items_detected: int
    items_resolved: int
    potential_savings: float
    actual_savings: Optional[float] = None


class WasteTrendsResponse(BaseModel):
    """Waste trends analysis response"""
    trends: List[WasteTrendData]
    period_start: str
    period_end: str
    total_items_period: int
    total_potential_savings_period: float
    resolution_rate_percent: float

    class Config:
        json_encoders = {
            Decimal: float
        }