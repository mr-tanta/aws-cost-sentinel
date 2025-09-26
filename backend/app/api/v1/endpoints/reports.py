from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime, date, timedelta
from uuid import UUID
import structlog

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.report_service import report_service
from app.services.queue_service import queue_service
from app.services.event_dispatcher import event_dispatcher
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()


class ReportRequest(BaseModel):
    account_id: UUID
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    format_type: str = "pdf"  # pdf, excel, html


class ScheduledReportRequest(BaseModel):
    account_id: UUID
    schedule_type: str  # daily, weekly, monthly
    format_types: List[str] = ["pdf"]
    enabled: bool = True


class ReportResponse(BaseModel):
    report_id: str
    file_path: str
    format: str
    size_bytes: int
    generated_at: str
    summary: dict


@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Generate a comprehensive cost optimization report"""

    try:
        # Set default date range if not provided (last 30 days)
        end_date = request.end_date or date.today()
        start_date = request.start_date or (end_date - timedelta(days=30))

        # Validate date range
        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        if (end_date - start_date).days > 365:
            raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

        # Validate format
        if request.format_type not in ["pdf", "excel", "html"]:
            raise HTTPException(status_code=400, detail="Format must be pdf, excel, or html")

        logger.info("Generating report",
                   account_id=str(request.account_id),
                   format_type=request.format_type,
                   user_id=str(current_user.id))

        # Generate report
        report_result = await report_service.generate_comprehensive_report(
            account_id=str(request.account_id),
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.max.time()),
            format_type=request.format_type,
            user_id=str(current_user.id)
        )

        # Notify user via WebSocket about report completion
        background_tasks.add_task(
            event_dispatcher.notify_job_progress,
            user_id=str(current_user.id),
            job_id=f"report_{report_result['report_id']}",
            status="completed",
            progress={"message": f"Report generated successfully in {request.format_type.upper()} format"}
        )

        return ReportResponse(
            report_id=report_result["report_id"],
            file_path=report_result["file_path"],
            format=report_result["format"],
            size_bytes=report_result["size_bytes"],
            generated_at=report_result["generated_at"],
            summary=report_result["summary"]
        )

    except ValueError as e:
        logger.error("Report generation validation error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Report generation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.get("/download/{report_id}")
async def download_report(
    report_id: str,
    current_user: User = Depends(get_current_user)
):
    """Download a generated report file"""

    try:
        # In a production environment, you'd validate user access to this report
        # and fetch the actual file path from database/cache

        # For now, we'll use a simple cache lookup
        from app.services.cache_service import cache_service

        # Try to get report info from cache
        # This is simplified - in production you'd have proper report tracking
        report_info = None

        if not report_info:
            raise HTTPException(status_code=404, detail="Report not found or expired")

        file_path = report_info.get("file_path")
        if not file_path:
            raise HTTPException(status_code=404, detail="Report file not found")

        # Determine media type based on format
        format_type = report_info.get("format", "pdf").lower()
        media_types = {
            "pdf": "application/pdf",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "html": "text/html"
        }

        filename = f"aws_cost_report_{report_id}.{format_type}"

        return FileResponse(
            path=file_path,
            media_type=media_types.get(format_type, "application/octet-stream"),
            filename=filename
        )

    except Exception as e:
        logger.error("Report download failed", error=str(e), report_id=report_id)
        raise HTTPException(status_code=500, detail="Failed to download report")


@router.post("/schedule")
async def schedule_periodic_reports(
    request: ScheduledReportRequest,
    current_user: User = Depends(get_current_user)
):
    """Schedule periodic report generation"""

    try:
        # Validate schedule type
        if request.schedule_type not in ["daily", "weekly", "monthly"]:
            raise HTTPException(status_code=400, detail="Schedule type must be daily, weekly, or monthly")

        # Validate format types
        for format_type in request.format_types:
            if format_type not in ["pdf", "excel", "html"]:
                raise HTTPException(status_code=400, detail=f"Invalid format type: {format_type}")

        logger.info("Scheduling periodic reports",
                   account_id=str(request.account_id),
                   schedule_type=request.schedule_type,
                   user_id=str(current_user.id))

        # Schedule the reports
        schedule_result = await report_service.schedule_periodic_reports(
            account_id=str(request.account_id),
            schedule_type=request.schedule_type,
            format_types=request.format_types,
            user_id=str(current_user.id)
        )

        return {
            "message": "Periodic reports scheduled successfully",
            "job_id": schedule_result["job_id"],
            "schedule_type": schedule_result["schedule_type"],
            "next_run": schedule_result["next_run"],
            "format_types": schedule_result["format_types"]
        }

    except ValueError as e:
        logger.error("Report scheduling validation error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Report scheduling failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to schedule periodic reports")


@router.get("/history")
async def get_report_history(
    account_id: Optional[UUID] = Query(None),
    limit: int = Query(default=50, le=100),
    current_user: User = Depends(get_current_user)
):
    """Get user's report generation history"""

    try:
        # In a production environment, you'd query a proper reports database table
        # For now, return a mock response

        history = []

        # This is where you'd implement actual database query
        # SELECT * FROM reports WHERE user_id = current_user.id
        # AND (account_id = account_id OR account_id IS NULL)
        # ORDER BY created_at DESC LIMIT limit

        return {
            "reports": history,
            "total_count": len(history),
            "user_id": str(current_user.id)
        }

    except Exception as e:
        logger.error("Failed to get report history", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve report history")


@router.delete("/cleanup")
async def cleanup_old_reports(
    days_to_keep: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user)
):
    """Clean up old report files (admin only)"""

    try:
        # Check if user has admin permissions
        if not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Admin access required")

        logger.info("Starting report cleanup", days_to_keep=days_to_keep)

        # Clean up old files
        cleaned_count = await report_service.cleanup_old_reports(days_to_keep)

        return {
            "message": f"Successfully cleaned up {cleaned_count} old report files",
            "files_removed": cleaned_count,
            "days_kept": days_to_keep
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Report cleanup failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to clean up old reports")


@router.get("/templates")
async def get_report_templates(
    current_user: User = Depends(get_current_user)
):
    """Get available report templates and formats"""

    templates = [
        {
            "id": "comprehensive",
            "name": "Comprehensive Cost Analysis",
            "description": "Complete cost breakdown with waste analysis and recommendations",
            "formats": ["pdf", "excel", "html"],
            "sections": [
                "Executive Summary",
                "Cost Breakdown by Service",
                "Waste Detection Results",
                "Priority Recommendations",
                "Historical Trends"
            ]
        },
        {
            "id": "executive",
            "name": "Executive Summary",
            "description": "High-level overview for executives and decision makers",
            "formats": ["pdf", "html"],
            "sections": [
                "Key Metrics",
                "Cost Trends",
                "Top Recommendations",
                "ROI Projections"
            ]
        },
        {
            "id": "technical",
            "name": "Technical Analysis",
            "description": "Detailed technical analysis for engineering teams",
            "formats": ["excel", "html"],
            "sections": [
                "Resource Utilization",
                "Performance Metrics",
                "Configuration Issues",
                "Optimization Opportunities"
            ]
        }
    ]

    return {
        "templates": templates,
        "supported_formats": ["pdf", "excel", "html"],
        "max_date_range_days": 365
    }


@router.post("/preview")
async def preview_report_data(
    request: ReportRequest,
    current_user: User = Depends(get_current_user)
):
    """Preview report data before generating the full report"""

    try:
        # Set default date range
        end_date = request.end_date or date.today()
        start_date = request.start_date or (end_date - timedelta(days=30))

        # Validate date range
        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        # Get a simplified version of the report data for preview
        from app.services.report_service import report_service

        preview_data = await report_service._collect_report_data(
            account_id=str(request.account_id),
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.max.time())
        )

        # Return a simplified preview
        return {
            "account": preview_data["account"],
            "period": preview_data["period"],
            "summary": preview_data["summary"],
            "top_services": preview_data["cost_breakdown"][:5],
            "top_waste_categories": preview_data["waste_categories"][:3],
            "top_recommendations": preview_data["recommendations"][:3]
        }

    except ValueError as e:
        logger.error("Report preview validation error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Report preview failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to preview report data")