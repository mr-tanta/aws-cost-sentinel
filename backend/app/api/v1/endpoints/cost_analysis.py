from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.core.security import get_current_user_id, create_api_response
from app.db.base import get_database
from app.models.aws_account import AWSAccount, AWSAccountStatus
from app.models.cost_data import CostData
from app.services.aws_client import aws_cost_explorer
from app.schemas.cost_analysis import (
    CostSummaryResponse,
    CostTrendResponse,
    CostBreakdownResponse,
    ServiceCostResponse,
    CostForecastResponse
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/summary", response_model=dict)
async def get_cost_summary(
    account_id: Optional[UUID] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get cost summary for the specified period"""
    try:
        # Set default date range (last 30 days)
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Build base query
        query = select(CostData).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        )

        # Filter by account if specified
        if account_id:
            # Verify account access
            account_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.id == account_id,
                        AWSAccount.is_active == True
                    )
                )
            )
            account = account_query.scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AWS account not found"
                )
            query = query.where(CostData.account_id == account_id)

        # Execute query
        result = await db.execute(query)
        cost_records = result.scalars().all()

        # Calculate summary metrics
        total_cost = sum(record.amount for record in cost_records)

        # Calculate previous period for comparison
        prev_start = start_date - (end_date - start_date)
        prev_end = start_date - timedelta(days=1)

        prev_query = select(CostData).where(
            and_(
                CostData.date >= prev_start,
                CostData.date <= prev_end
            )
        )
        if account_id:
            prev_query = prev_query.where(CostData.account_id == account_id)

        prev_result = await db.execute(prev_query)
        prev_records = prev_result.scalars().all()
        prev_total = sum(record.amount for record in prev_records)

        # Calculate percentage change
        change_percent = 0.0
        if prev_total > 0:
            change_percent = ((total_cost - prev_total) / prev_total) * 100

        # Group by service
        service_breakdown = {}
        for record in cost_records:
            if record.service not in service_breakdown:
                service_breakdown[record.service] = 0
            service_breakdown[record.service] += record.amount

        # Top services
        top_services = sorted(
            service_breakdown.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        summary = {
            "total_cost": round(total_cost, 2),
            "previous_period_cost": round(prev_total, 2),
            "change_percent": round(change_percent, 2),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "top_services": [
                {"service": service, "cost": round(cost, 2)}
                for service, cost in top_services
            ]
        }

        return create_api_response(
            success=True,
            data=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get cost summary", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cost summary"
        )


@router.get("/trends", response_model=dict)
async def get_cost_trends(
    account_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=7, le=365),
    granularity: str = Query("DAILY", regex="^(DAILY|WEEKLY|MONTHLY)$"),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get cost trends over time"""
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Verify account access if specified
        if account_id:
            account_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.id == account_id,
                        AWSAccount.is_active == True
                    )
                )
            )
            account = account_query.scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AWS account not found"
                )

        # Build query based on granularity
        if granularity == "DAILY":
            date_column = CostData.date
        elif granularity == "WEEKLY":
            # Group by week
            date_column = func.date_trunc('week', CostData.date)
        else:  # MONTHLY
            date_column = func.date_trunc('month', CostData.date)

        query = select(
            date_column.label('period'),
            func.sum(CostData.amount).label('total_cost')
        ).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        ).group_by('period').order_by('period')

        if account_id:
            query = query.where(CostData.account_id == account_id)

        result = await db.execute(query)
        trends = result.all()

        trend_data = [
            {
                "date": trend.period.isoformat() if isinstance(trend.period, date) else str(trend.period),
                "cost": round(float(trend.total_cost), 2)
            }
            for trend in trends
        ]

        return create_api_response(
            success=True,
            data={
                "trends": trend_data,
                "granularity": granularity,
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat()
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get cost trends", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cost trends"
        )


@router.get("/breakdown/services", response_model=dict)
async def get_service_breakdown(
    account_id: Optional[UUID] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get cost breakdown by AWS service"""
    try:
        # Set default date range
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Verify account access if specified
        if account_id:
            account_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.id == account_id,
                        AWSAccount.is_active == True
                    )
                )
            )
            account = account_query.scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AWS account not found"
                )

        # Query for service breakdown
        query = select(
            CostData.service,
            func.sum(CostData.amount).label('total_cost'),
            func.count(CostData.id).label('record_count')
        ).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        ).group_by(CostData.service).order_by(func.sum(CostData.amount).desc())

        if account_id:
            query = query.where(CostData.account_id == account_id)

        result = await db.execute(query)
        services = result.all()

        total_cost = sum(float(service.total_cost) for service in services)

        service_breakdown = [
            {
                "service": service.service,
                "cost": round(float(service.total_cost), 2),
                "percentage": round((float(service.total_cost) / total_cost * 100), 2) if total_cost > 0 else 0,
                "record_count": service.record_count
            }
            for service in services
        ]

        return create_api_response(
            success=True,
            data={
                "services": service_breakdown,
                "total_cost": round(total_cost, 2),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat()
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get service breakdown", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve service breakdown"
        )


@router.post("/sync", response_model=dict)
async def sync_cost_data(
    account_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Manually trigger cost data sync from AWS"""
    try:
        # Verify account access
        account_query = await db.execute(
            select(AWSAccount).where(
                and_(
                    AWSAccount.id == account_id,
                    AWSAccount.is_active == True,
                    AWSAccount.status == AWSAccountStatus.CONNECTED
                )
            )
        )
        account = account_query.scalar_one_or_none()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connected AWS account not found"
            )

        # Set default date range (last 7 days)
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        # Fetch cost data from AWS
        cost_data = await aws_cost_explorer.get_cost_and_usage(
            start_date=start_date.isoformat(),
            end_date=(end_date + timedelta(days=1)).isoformat(),  # AWS API is exclusive of end date
            granularity='DAILY',
            metrics=['BlendedCost'],
            group_by=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            account=account
        )

        # Process and store cost data
        records_created = 0
        for result_by_time in cost_data.get('ResultsByTime', []):
            result_date = datetime.fromisoformat(result_by_time['TimePeriod']['Start']).date()

            for group in result_by_time.get('Groups', []):
                service_name = group['Keys'][0] if group['Keys'] else 'Other'
                amount = float(group['Metrics']['BlendedCost']['Amount'])

                if amount > 0:  # Only store non-zero costs
                    # Check if record already exists
                    existing_query = await db.execute(
                        select(CostData).where(
                            and_(
                                CostData.account_id == account_id,
                                CostData.date == result_date,
                                CostData.service == service_name
                            )
                        )
                    )
                    existing_record = existing_query.scalar_one_or_none()

                    if existing_record:
                        # Update existing record
                        existing_record.amount = amount
                        existing_record.currency = 'USD'
                        existing_record.updated_at = datetime.utcnow()
                    else:
                        # Create new record
                        cost_record = CostData(
                            account_id=account_id,
                            date=result_date,
                            service=service_name,
                            amount=amount,
                            currency='USD'
                        )
                        db.add(cost_record)
                        records_created += 1

        await db.commit()

        logger.info("Cost data synced successfully",
                   account_id=str(account_id),
                   records_created=records_created,
                   start_date=start_date.isoformat(),
                   end_date=end_date.isoformat())

        return create_api_response(
            success=True,
            data={
                "records_processed": records_created,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            message="Cost data synchronized successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to sync cost data",
                    account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to synchronize cost data"
        )


@router.get("/forecast", response_model=dict)
async def get_cost_forecast(
    account_id: Optional[UUID] = Query(None),
    days_ahead: int = Query(30, ge=1, le=365),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get cost forecast based on historical data"""
    try:
        # This is a simplified forecast - in production you'd use more sophisticated ML
        end_date = date.today()
        start_date = end_date - timedelta(days=90)  # Use 90 days of history

        # Build query for historical data
        query = select(CostData).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        )

        if account_id:
            # Verify account access
            account_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.id == account_id,
                        AWSAccount.is_active == True
                    )
                )
            )
            account = account_query.scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AWS account not found"
                )
            query = query.where(CostData.account_id == account_id)

        result = await db.execute(query)
        historical_records = result.scalars().all()

        # Simple linear trend calculation
        daily_costs = {}
        for record in historical_records:
            if record.date not in daily_costs:
                daily_costs[record.date] = 0
            daily_costs[record.date] += record.amount

        # Calculate average daily cost and trend
        if len(daily_costs) < 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient historical data for forecast"
            )

        sorted_dates = sorted(daily_costs.keys())
        daily_amounts = [daily_costs[date] for date in sorted_dates]

        # Simple moving average for trend
        recent_avg = sum(daily_amounts[-30:]) / min(30, len(daily_amounts))
        older_avg = sum(daily_amounts[-60:-30]) / min(30, len(daily_amounts))

        # Calculate trend factor
        trend_factor = 1.0
        if older_avg > 0:
            trend_factor = recent_avg / older_avg

        # Generate forecast
        forecast_data = []
        base_cost = recent_avg

        for i in range(1, days_ahead + 1):
            forecast_date = end_date + timedelta(days=i)
            # Apply trend with some dampening
            dampened_trend = 1 + (trend_factor - 1) * 0.5
            projected_cost = base_cost * (dampened_trend ** (i / 30))

            forecast_data.append({
                "date": forecast_date.isoformat(),
                "projected_cost": round(projected_cost, 2),
                "confidence": max(0.5, 1.0 - (i / days_ahead * 0.5))  # Decreasing confidence
            })

        total_forecast = sum(item["projected_cost"] for item in forecast_data)

        return create_api_response(
            success=True,
            data={
                "forecast": forecast_data,
                "total_projected_cost": round(total_forecast, 2),
                "forecast_period_days": days_ahead,
                "based_on_days": len(daily_costs),
                "trend_factor": round(trend_factor, 3)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate cost forecast", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate cost forecast"
        )


@router.get("/comparison", response_model=dict)
async def compare_accounts(
    account_ids: str = Query(..., description="Comma-separated list of account IDs"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Compare costs across multiple AWS accounts"""
    try:
        # Parse account IDs
        account_id_list = [UUID(id.strip()) for id in account_ids.split(',')]

        if len(account_id_list) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 10 accounts can be compared at once"
            )

        # Set default date range
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Verify all accounts exist and are accessible
        accounts_query = await db.execute(
            select(AWSAccount).where(
                and_(
                    AWSAccount.id.in_(account_id_list),
                    AWSAccount.is_active == True
                )
            )
        )
        accounts = accounts_query.scalars().all()

        if len(accounts) != len(account_id_list):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more accounts not found or inaccessible"
            )

        comparison_data = []
        total_cost_all_accounts = 0

        for account in accounts:
            # Get cost data for this account
            cost_query = await db.execute(
                select(CostData).where(
                    and_(
                        CostData.account_id == account.id,
                        CostData.date >= start_date,
                        CostData.date <= end_date
                    )
                )
            )
            cost_records = cost_query.scalars().all()

            account_total = sum(record.amount for record in cost_records)
            total_cost_all_accounts += account_total

            # Calculate daily average
            days_in_period = (end_date - start_date).days + 1
            daily_average = account_total / days_in_period if days_in_period > 0 else 0

            # Top services for this account
            service_breakdown = {}
            for record in cost_records:
                if record.service not in service_breakdown:
                    service_breakdown[record.service] = 0
                service_breakdown[record.service] += record.amount

            top_services = sorted(
                service_breakdown.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            comparison_data.append({
                "account_id": str(account.id),
                "account_name": account.name,
                "total_cost": round(account_total, 2),
                "daily_average": round(daily_average, 2),
                "percentage_of_total": 0,  # Will calculate below
                "top_services": [
                    {"service": service, "cost": round(cost, 2)}
                    for service, cost in top_services
                ]
            })

        # Calculate percentages
        for account_data in comparison_data:
            if total_cost_all_accounts > 0:
                account_data["percentage_of_total"] = round(
                    (account_data["total_cost"] / total_cost_all_accounts) * 100, 2
                )

        return create_api_response(
            success=True,
            data={
                "accounts": comparison_data,
                "total_cost_all_accounts": round(total_cost_all_accounts, 2),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "accounts_compared": len(accounts)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to compare accounts", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare accounts"
        )


@router.get("/optimization-suggestions", response_model=dict)
async def get_optimization_suggestions(
    account_id: Optional[UUID] = Query(None),
    service: Optional[str] = Query(None),
    min_savings: float = Query(10.0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get cost optimization suggestions"""
    try:
        # This is a simplified version - in production you'd use ML models
        suggestions = []

        # Build base query for cost analysis
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        query = select(CostData).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        )

        if account_id:
            # Verify account access
            account_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.id == account_id,
                        AWSAccount.is_active == True
                    )
                )
            )
            account = account_query.scalar_one_or_none()
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="AWS account not found"
                )
            query = query.where(CostData.account_id == account_id)

        if service:
            query = query.where(CostData.service == service)

        result = await db.execute(query)
        cost_records = result.scalars().all()

        # Analyze cost patterns and generate suggestions
        service_costs = {}
        for record in cost_records:
            if record.service not in service_costs:
                service_costs[record.service] = []
            service_costs[record.service].append(record.amount)

        for service_name, costs in service_costs.items():
            total_cost = sum(costs)
            avg_daily_cost = total_cost / 30

            if total_cost >= min_savings:
                # Example suggestions based on service patterns
                if service_name == 'Amazon Elastic Compute Cloud - Compute':
                    if avg_daily_cost > 50:  # Arbitrary threshold
                        suggestions.append({
                            "category": "RIGHTSIZING",
                            "service": service_name,
                            "resource_id": None,
                            "current_cost": round(total_cost, 2),
                            "potential_savings": round(total_cost * 0.2, 2),  # 20% potential savings
                            "confidence": 0.7,
                            "effort_level": "MEDIUM",
                            "description": f"Consider rightsizing EC2 instances. Monthly cost: ${total_cost:.2f}",
                            "action_required": "Review instance utilization and consider smaller instance types"
                        })

                elif service_name == 'Amazon Simple Storage Service':
                    if avg_daily_cost > 20:
                        suggestions.append({
                            "category": "STORAGE",
                            "service": service_name,
                            "resource_id": None,
                            "current_cost": round(total_cost, 2),
                            "potential_savings": round(total_cost * 0.3, 2),
                            "confidence": 0.8,
                            "effort_level": "LOW",
                            "description": f"Optimize S3 storage classes. Monthly cost: ${total_cost:.2f}",
                            "action_required": "Move infrequently accessed data to cheaper storage classes"
                        })

                elif service_name == 'Amazon Relational Database Service':
                    if avg_daily_cost > 30:
                        suggestions.append({
                            "category": "RESERVED_INSTANCES",
                            "service": service_name,
                            "resource_id": None,
                            "current_cost": round(total_cost, 2),
                            "potential_savings": round(total_cost * 0.4, 2),
                            "confidence": 0.9,
                            "effort_level": "LOW",
                            "description": f"Consider RDS Reserved Instances. Monthly cost: ${total_cost:.2f}",
                            "action_required": "Purchase 1-year Reserved Instances for consistent workloads"
                        })

        # Filter suggestions by minimum savings
        suggestions = [s for s in suggestions if s["potential_savings"] >= min_savings]

        # Sort by potential savings
        suggestions.sort(key=lambda x: x["potential_savings"], reverse=True)

        total_potential_savings = sum(s["potential_savings"] for s in suggestions)

        return create_api_response(
            success=True,
            data={
                "suggestions": suggestions,
                "total_potential_savings": round(total_potential_savings, 2),
                "analyzed_period_days": 30,
                "account_id": str(account_id) if account_id else None,
                "suggestions_count": len(suggestions)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get optimization suggestions", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get optimization suggestions"
        )


@router.post("/sync-all", response_model=dict)
async def sync_all_accounts(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Trigger cost data sync for all connected accounts"""
    try:
        from app.services.cost_sync_service import cost_sync_service

        # Set default date range
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        logger.info("Triggering bulk cost sync",
                   start_date=start_date.isoformat(),
                   end_date=end_date.isoformat(),
                   user_id=current_user_id)

        # Start the sync process (this will run in background)
        results = await cost_sync_service.sync_all_connected_accounts(
            start_date=start_date,
            end_date=end_date
        )

        # Count successful vs failed syncs
        successful = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - successful

        return create_api_response(
            success=True,
            data={
                "total_accounts": len(results),
                "successful_syncs": successful,
                "failed_syncs": failed,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "results": results
            },
            message="Bulk cost sync completed"
        )

    except Exception as e:
        logger.error("Failed to sync all accounts", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync all accounts"
        )