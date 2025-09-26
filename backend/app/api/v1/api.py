from fastapi import APIRouter

from app.api.v1.endpoints import auth, aws_accounts, cost_analysis, waste_detection, recommendations, reports, dashboard

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(aws_accounts.router, prefix="/aws/accounts", tags=["aws-accounts"])
api_router.include_router(cost_analysis.router, prefix="/costs", tags=["cost-analysis"])
api_router.include_router(waste_detection.router, prefix="/waste", tags=["waste-detection"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])