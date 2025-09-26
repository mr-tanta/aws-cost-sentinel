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
from app.models.waste import WasteItem, WasteStatus, WasteCategory
from app.services.aws_client import aws_resource_manager
from app.services.waste_detection_service import waste_detection_service
from app.schemas.waste_detection import (
    WasteItemResponse,
    WasteDetectionResponse,
    WasteSummaryResponse,
    WasteItemCreate,
    WasteItemUpdate
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/scan/{account_id}", response_model=dict)
async def scan_account_for_waste(
    account_id: UUID,
    categories: Optional[str] = Query(None, description="Comma-separated waste categories to scan"),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Scan an AWS account for waste and inefficiencies"""
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

        # Parse categories
        scan_categories = None
        if categories:
            category_list = [cat.strip().upper() for cat in categories.split(',')]
            try:
                scan_categories = [WasteCategory(cat) for cat in category_list]
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid waste category: {str(e)}"
                )

        logger.info("Starting waste detection scan",
                   account_id=account.account_id,
                   categories=scan_categories)

        # Run waste detection
        scan_results = await waste_detection_service.scan_account_for_waste(
            account=account,
            categories=scan_categories,
            db=db
        )

        return create_api_response(
            success=True,
            data=scan_results,
            message="Waste detection scan completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to scan for waste", account_id=str(account_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to scan for waste"
        )


@router.get("/items", response_model=dict)
async def get_waste_items(
    account_id: Optional[UUID] = Query(None),
    category: Optional[WasteCategory] = Query(None),
    status: Optional[WasteStatus] = Query(None),
    min_monthly_cost: Optional[float] = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get waste items with filtering and pagination"""
    try:
        # Build base query
        query = select(WasteItem).where(WasteItem.is_active == True)

        # Apply filters
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
            query = query.where(WasteItem.account_id == account_id)

        if category:
            query = query.where(WasteItem.category == category)

        if status:
            query = query.where(WasteItem.status == status)

        if min_monthly_cost:
            query = query.where(WasteItem.estimated_monthly_savings >= min_monthly_cost)

        # Get total count
        count_query = select(func.count(WasteItem.id)).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(WasteItem.estimated_monthly_savings.desc())
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        waste_items = result.scalars().all()

        # Convert to response format
        items_data = [WasteItemResponse.from_orm(item) for item in waste_items]

        return create_api_response(
            success=True,
            data={
                "items": items_data,
                "total_count": total_count,
                "page": skip // limit + 1,
                "pages": (total_count + limit - 1) // limit,
                "filters_applied": {
                    "account_id": str(account_id) if account_id else None,
                    "category": category.value if category else None,
                    "status": status.value if status else None,
                    "min_monthly_cost": min_monthly_cost
                }
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get waste items", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve waste items"
        )


@router.get("/summary", response_model=dict)
async def get_waste_summary(
    account_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Get waste detection summary and statistics"""
    try:
        # Build base query
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = select(WasteItem).where(
            and_(
                WasteItem.is_active == True,
                WasteItem.detected_at >= cutoff_date
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
            query = query.where(WasteItem.account_id == account_id)

        result = await db.execute(query)
        waste_items = result.scalars().all()

        # Calculate summary statistics
        total_items = len(waste_items)
        total_potential_savings = sum(item.estimated_monthly_savings for item in waste_items)

        # Group by category
        category_breakdown = {}
        for item in waste_items:
            if item.category not in category_breakdown:
                category_breakdown[item.category] = {
                    "count": 0,
                    "potential_savings": 0,
                    "avg_confidence": 0
                }
            category_breakdown[item.category]["count"] += 1
            category_breakdown[item.category]["potential_savings"] += item.estimated_monthly_savings
            category_breakdown[item.category]["avg_confidence"] += item.confidence_score

        # Calculate averages
        for category, data in category_breakdown.items():
            if data["count"] > 0:
                data["avg_confidence"] = data["avg_confidence"] / data["count"]
                data["potential_savings"] = round(data["potential_savings"], 2)
                data["avg_confidence"] = round(data["avg_confidence"], 3)

        # Group by status
        status_breakdown = {}
        for item in waste_items:
            if item.status not in status_breakdown:
                status_breakdown[item.status] = 0
            status_breakdown[item.status] += 1

        # Top waste items by savings
        top_items = sorted(waste_items, key=lambda x: x.estimated_monthly_savings, reverse=True)[:10]

        summary = {
            "total_waste_items": total_items,
            "total_potential_monthly_savings": round(total_potential_savings, 2),
            "analysis_period_days": days,
            "category_breakdown": {
                cat.value: data for cat, data in category_breakdown.items()
            },
            "status_breakdown": {
                status.value: count for status, count in status_breakdown.items()
            },
            "top_waste_items": [
                {
                    "id": str(item.id),
                    "category": item.category.value,
                    "resource_id": item.resource_id,
                    "description": item.description,
                    "potential_savings": round(item.estimated_monthly_savings, 2),
                    "confidence": round(item.confidence_score, 3)
                }
                for item in top_items
            ]
        }

        return create_api_response(
            success=True,
            data=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get waste summary", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve waste summary"
        )


@router.put("/items/{item_id}/status", response_model=dict)
async def update_waste_item_status(
    item_id: UUID,
    new_status: WasteStatus,
    notes: Optional[str] = None,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Update the status of a waste item"""
    try:
        # Find the waste item
        result = await db.execute(
            select(WasteItem).where(
                and_(
                    WasteItem.id == item_id,
                    WasteItem.is_active == True
                )
            )
        )
        waste_item = result.scalar_one_or_none()

        if not waste_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Waste item not found"
            )

        # Update status
        old_status = waste_item.status
        waste_item.status = new_status
        waste_item.updated_at = datetime.utcnow()

        # Add notes if provided
        if notes:
            current_notes = waste_item.notes or ""
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            new_note = f"[{timestamp}] Status changed from {old_status.value} to {new_status.value}: {notes}"
            waste_item.notes = f"{current_notes}\n{new_note}".strip()

        # If marked as resolved, update resolved date
        if new_status == WasteStatus.RESOLVED:
            waste_item.resolved_at = datetime.utcnow()

        await db.commit()
        await db.refresh(waste_item)

        logger.info("Waste item status updated",
                   item_id=str(item_id),
                   old_status=old_status.value,
                   new_status=new_status.value,
                   user_id=current_user_id)

        return create_api_response(
            success=True,
            data=WasteItemResponse.from_orm(waste_item),
            message="Waste item status updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update waste item status", item_id=str(item_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update waste item status"
        )


@router.post("/bulk-scan", response_model=dict)
async def bulk_scan_accounts(
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs, or null for all"),
    categories: Optional[str] = Query(None, description="Comma-separated waste categories"),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Trigger waste detection scan for multiple accounts"""
    try:
        # Parse account IDs
        target_accounts = []
        if account_ids:
            account_id_list = [UUID(id.strip()) for id in account_ids.split(',')]
            # Verify all accounts exist and are accessible
            accounts_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.id.in_(account_id_list),
                        AWSAccount.is_active == True,
                        AWSAccount.status == AWSAccountStatus.CONNECTED
                    )
                )
            )
            target_accounts = accounts_query.scalars().all()
        else:
            # Get all connected accounts
            accounts_query = await db.execute(
                select(AWSAccount).where(
                    and_(
                        AWSAccount.is_active == True,
                        AWSAccount.status == AWSAccountStatus.CONNECTED
                    )
                )
            )
            target_accounts = accounts_query.scalars().all()

        if not target_accounts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No connected accounts found for scanning"
            )

        # Parse categories
        scan_categories = None
        if categories:
            category_list = [cat.strip().upper() for cat in categories.split(',')]
            try:
                scan_categories = [WasteCategory(cat) for cat in category_list]
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid waste category: {str(e)}"
                )

        logger.info("Starting bulk waste detection scan",
                   account_count=len(target_accounts),
                   categories=scan_categories,
                   user_id=current_user_id)

        # Run bulk scan
        scan_results = await waste_detection_service.bulk_scan_accounts(
            accounts=target_accounts,
            categories=scan_categories,
            db=db
        )

        # Calculate summary
        total_items_found = sum(result.get("items_found", 0) for result in scan_results)
        successful_scans = sum(1 for result in scan_results if result.get("status") == "success")

        return create_api_response(
            success=True,
            data={
                "accounts_scanned": len(target_accounts),
                "successful_scans": successful_scans,
                "failed_scans": len(target_accounts) - successful_scans,
                "total_waste_items_found": total_items_found,
                "scan_results": scan_results
            },
            message="Bulk waste detection scan completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to perform bulk waste scan", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform bulk waste scan"
        )


@router.delete("/items/{item_id}", response_model=dict)
async def dismiss_waste_item(
    item_id: UUID,
    reason: Optional[str] = None,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_database)
):
    """Dismiss (soft delete) a waste item"""
    try:
        # Find the waste item
        result = await db.execute(
            select(WasteItem).where(
                and_(
                    WasteItem.id == item_id,
                    WasteItem.is_active == True
                )
            )
        )
        waste_item = result.scalar_one_or_none()

        if not waste_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Waste item not found"
            )

        # Soft delete
        waste_item.is_active = False
        waste_item.status = WasteStatus.DISMISSED
        waste_item.updated_at = datetime.utcnow()

        # Add dismissal reason to notes
        if reason:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            dismissal_note = f"[{timestamp}] Dismissed by user: {reason}"
            current_notes = waste_item.notes or ""
            waste_item.notes = f"{current_notes}\n{dismissal_note}".strip()

        await db.commit()

        logger.info("Waste item dismissed",
                   item_id=str(item_id),
                   reason=reason,
                   user_id=current_user_id)

        return create_api_response(
            success=True,
            message="Waste item dismissed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to dismiss waste item", item_id=str(item_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dismiss waste item"
        )


@router.get("/categories", response_model=dict)
async def get_waste_categories():
    """Get all available waste detection categories"""
    categories = [
        {
            "value": category.value,
            "name": category.value.replace('_', ' ').title(),
            "description": _get_category_description(category)
        }
        for category in WasteCategory
    ]

    return create_api_response(
        success=True,
        data={"categories": categories}
    )


def _get_category_description(category: WasteCategory) -> str:
    """Get human-readable description for waste categories"""
    descriptions = {
        WasteCategory.UNATTACHED_VOLUMES: "EBS volumes that are not attached to any EC2 instance",
        WasteCategory.UNUSED_ELASTIC_IPS: "Elastic IP addresses that are not associated with any resource",
        WasteCategory.STOPPED_INSTANCES: "EC2 instances that have been stopped for an extended period",
        WasteCategory.UNDERUTILIZED_INSTANCES: "EC2 instances with consistently low CPU or memory utilization",
        WasteCategory.OVERSIZED_INSTANCES: "EC2 instances that are larger than necessary for their workload",
        WasteCategory.UNUSED_LOAD_BALANCERS: "Load balancers with no active targets",
        WasteCategory.EMPTY_S3_BUCKETS: "S3 buckets that contain no objects but incur storage costs",
        WasteCategory.OLD_SNAPSHOTS: "EBS snapshots that are older than retention policy",
        WasteCategory.UNUSED_NAT_GATEWAYS: "NAT gateways with minimal or no traffic",
        WasteCategory.IDLE_RDS_INSTANCES: "RDS instances with low connection count or CPU usage"
    }
    return descriptions.get(category, "No description available")