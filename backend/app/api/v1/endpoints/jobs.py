from datetime import date, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user_id, create_api_response
from app.db.base import get_database
from app.services.queue_service import queue_service, JobStatus, JobPriority
from app.workers.job_worker import JobScheduler

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/", response_model=dict)
async def list_jobs(
    status_filter: Optional[str] = Query(None, regex="^(pending|processing|completed|failed|cancelled)$"),
    limit: int = Query(50, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id)
):
    """List background jobs with optional filtering"""
    try:
        # Get queue statistics
        stats = queue_service.get_queue_stats()

        # In a production system, you'd want to store job metadata
        # that includes user_id to filter jobs by user
        response_data = {
            "queue_stats": stats,
            "message": "Job listing functionality requires additional user-job mapping implementation"
        }

        return create_api_response(
            success=True,
            data=response_data
        )

    except Exception as e:
        logger.error("Failed to list jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job list"
        )


@router.get("/{job_id}", response_model=dict)
async def get_job_status(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get status and details of a specific job"""
    try:
        job_data = queue_service.get_job(job_id)

        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        return create_api_response(
            success=True,
            data=job_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get job status", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job status"
        )


@router.post("/cost-sync", response_model=dict)
async def schedule_cost_sync(
    account_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    delay_minutes: int = Query(0, ge=0, le=1440),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Schedule a cost synchronization job for an account"""
    try:
        # Verify account access
        from app.models.aws_account import AWSAccount
        from sqlalchemy import select, and_

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
                detail="AWS account not found or inaccessible"
            )

        # Set default dates if not provided
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Schedule the job
        job_id = JobScheduler.schedule_cost_sync(
            account_id=str(account_id),
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            delay=delay_minutes * 60
        )

        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to schedule cost sync job"
            )

        logger.info("Cost sync job scheduled",
                   job_id=job_id,
                   account_id=str(account_id),
                   user_id=current_user_id)

        return create_api_response(
            success=True,
            data={
                "job_id": job_id,
                "account_id": str(account_id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "scheduled_delay_minutes": delay_minutes
            },
            message="Cost synchronization job scheduled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to schedule cost sync", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule cost synchronization job"
        )


@router.post("/waste-scan", response_model=dict)
async def schedule_waste_scan(
    account_id: UUID,
    categories: Optional[str] = Query(None, description="Comma-separated waste categories"),
    delay_minutes: int = Query(0, ge=0, le=1440),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Schedule a waste detection scan for an account"""
    try:
        # Verify account access
        from app.models.aws_account import AWSAccount
        from sqlalchemy import select, and_

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
                detail="AWS account not found or inaccessible"
            )

        # Parse categories if provided
        category_list = None
        if categories:
            category_list = [cat.strip() for cat in categories.split(',')]

        # Schedule the job
        job_id = JobScheduler.schedule_waste_scan(
            account_id=str(account_id),
            categories=category_list,
            delay=delay_minutes * 60
        )

        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to schedule waste scan job"
            )

        logger.info("Waste scan job scheduled",
                   job_id=job_id,
                   account_id=str(account_id),
                   categories=category_list,
                   user_id=current_user_id)

        return create_api_response(
            success=True,
            data={
                "job_id": job_id,
                "account_id": str(account_id),
                "categories": category_list,
                "scheduled_delay_minutes": delay_minutes
            },
            message="Waste detection scan scheduled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to schedule waste scan", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule waste detection scan"
        )


@router.post("/bulk-cost-sync", response_model=dict)
async def schedule_bulk_cost_sync(
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs, null for all accounts"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    delay_minutes: int = Query(0, ge=0, le=1440),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Schedule bulk cost synchronization for multiple accounts"""
    try:
        # Parse account IDs if provided
        account_id_list = None
        if account_ids:
            account_id_list = [UUID(id.strip()) for id in account_ids.split(',')]

            # Verify all accounts are accessible
            from app.models.aws_account import AWSAccount
            from sqlalchemy import select, and_

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
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more accounts not found or inaccessible"
                )

            account_id_list = [str(acc.id) for acc in accounts]

        # Set default dates
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        # Schedule the job
        job_id = JobScheduler.schedule_bulk_cost_sync(
            account_ids=account_id_list,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            delay=delay_minutes * 60
        )

        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to schedule bulk cost sync job"
            )

        logger.info("Bulk cost sync job scheduled",
                   job_id=job_id,
                   account_count=len(account_id_list) if account_id_list else "all",
                   user_id=current_user_id)

        return create_api_response(
            success=True,
            data={
                "job_id": job_id,
                "account_ids": account_id_list,
                "account_count": len(account_id_list) if account_id_list else "all",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "scheduled_delay_minutes": delay_minutes
            },
            message="Bulk cost synchronization job scheduled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to schedule bulk cost sync", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule bulk cost synchronization job"
        )


@router.post("/generate-recommendations", response_model=dict)
async def schedule_recommendations_generation(
    account_id: Optional[UUID] = Query(None),
    recommendation_types: Optional[str] = Query(None, description="Comma-separated recommendation types"),
    delay_minutes: int = Query(0, ge=0, le=1440),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Schedule recommendations generation job"""
    try:
        # Verify account if specified
        if account_id:
            from app.models.aws_account import AWSAccount
            from sqlalchemy import select, and_

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
                    detail="AWS account not found or inaccessible"
                )

        # Parse recommendation types if provided
        types_list = None
        if recommendation_types:
            types_list = [rtype.strip() for rtype in recommendation_types.split(',')]

        # Schedule the job
        job_id = JobScheduler.schedule_recommendations_generation(
            account_id=str(account_id) if account_id else None,
            recommendation_types=types_list,
            delay=delay_minutes * 60
        )

        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to schedule recommendations generation job"
            )

        logger.info("Recommendations generation job scheduled",
                   job_id=job_id,
                   account_id=str(account_id) if account_id else None,
                   user_id=current_user_id)

        return create_api_response(
            success=True,
            data={
                "job_id": job_id,
                "account_id": str(account_id) if account_id else None,
                "recommendation_types": types_list,
                "scheduled_delay_minutes": delay_minutes
            },
            message="Recommendations generation job scheduled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to schedule recommendations generation", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule recommendations generation job"
        )


@router.post("/{job_id}/cancel", response_model=dict)
async def cancel_job(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Cancel a pending job"""
    try:
        # Get job details first
        job_data = queue_service.get_job(job_id)
        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        # Cancel the job
        success = queue_service.cancel_job(job_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job cannot be cancelled (may already be processing or completed)"
            )

        logger.info("Job cancelled", job_id=job_id, user_id=current_user_id)

        return create_api_response(
            success=True,
            message="Job cancelled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel job", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel job"
        )


@router.post("/{job_id}/retry", response_model=dict)
async def retry_job(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Retry a failed job"""
    try:
        # Get job details first
        job_data = queue_service.get_job(job_id)
        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )

        # Retry the job
        success = queue_service.retry_job(job_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job cannot be retried (may have exceeded max retries or not in failed state)"
            )

        logger.info("Job retry scheduled", job_id=job_id, user_id=current_user_id)

        return create_api_response(
            success=True,
            message="Job retry scheduled successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retry job", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry job"
        )


@router.get("/stats/queue", response_model=dict)
async def get_queue_stats(
    queue_name: str = Query("default"),
    current_user_id: str = Depends(get_current_user_id)
):
    """Get queue statistics and health information"""
    try:
        stats = queue_service.get_queue_stats(queue_name)

        return create_api_response(
            success=True,
            data={
                "queue_name": queue_name,
                "stats": stats
            }
        )

    except Exception as e:
        logger.error("Failed to get queue stats", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve queue statistics"
        )