from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime, timedelta

from app.models.schemas import CostSummary, ServiceCost, CostData
from app.services.aws_service import aws_service

router = APIRouter()


@router.get("/summary", response_model=CostSummary)
async def get_cost_summary():
    """Get cost summary including current month, last month, projected costs."""
    try:
        summary = await aws_service.get_monthly_costs()
        return CostSummary(**summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cost summary: {str(e)}")


@router.get("/daily", response_model=List[CostData])
async def get_daily_costs(start: str, end: str):
    """Get daily cost data for a date range."""
    try:
        # Validate date format
        start_date = datetime.strptime(start, '%Y-%m-%d')
        end_date = datetime.strptime(end, '%Y-%m-%d')

        if (end_date - start_date).days > 365:
            raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

        cost_data = await aws_service.get_cost_and_usage(start, end)

        # Transform AWS response to our format
        daily_costs = []
        for result in cost_data.get('ResultsByTime', []):
            date = result.get('TimePeriod', {}).get('Start')
            total_cost = float(result.get('Total', {}).get('BlendedCost', {}).get('Amount', 0))

            services = {}
            for group in result.get('Groups', []):
                service = group.get('Keys', ['Unknown'])[0]
                amount = float(group.get('Metrics', {}).get('BlendedCost', {}).get('Amount', 0))
                services[service] = amount

            daily_costs.append(CostData(
                date=date,
                total_cost=total_cost,
                services=services,
                tags={}
            ))

        return daily_costs
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching daily costs: {str(e)}")


@router.get("/services", response_model=List[ServiceCost])
async def get_service_costs():
    """Get cost breakdown by AWS service."""
    try:
        services = await aws_service.get_service_costs()
        return [ServiceCost(**service) for service in services]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching service costs: {str(e)}")