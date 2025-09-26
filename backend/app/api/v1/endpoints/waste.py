from fastapi import APIRouter, HTTPException
from typing import List

from app.models.schemas import WasteItem
from app.services.aws_service import aws_service

router = APIRouter()


@router.get("", response_model=List[WasteItem])
async def get_waste_items():
    """Get all detected waste items."""
    try:
        waste_items = []

        # Find unattached volumes
        volumes = await aws_service.find_unattached_volumes()
        waste_items.extend(volumes)

        # Find unused Elastic IPs
        elastic_ips = await aws_service.find_unused_elastic_ips()
        waste_items.extend(elastic_ips)

        # Find stopped instances
        stopped_instances = await aws_service.find_stopped_instances()
        waste_items.extend(stopped_instances)

        # Convert to WasteItem models
        return [WasteItem(**item) for item in waste_items]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching waste items: {str(e)}")


@router.post("/{waste_id}/remediate")
async def remediate_waste_item(waste_id: str):
    """Remediate a specific waste item."""
    try:
        # In production, this would actually delete/remediate the resource
        # For now, just return success
        return {"message": f"Waste item {waste_id} has been scheduled for remediation"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error remediating waste item: {str(e)}")


@router.get("/summary")
async def get_waste_summary():
    """Get summary of waste detection results."""
    try:
        waste_items = []

        # Get all waste items
        volumes = await aws_service.find_unattached_volumes()
        waste_items.extend(volumes)

        elastic_ips = await aws_service.find_unused_elastic_ips()
        waste_items.extend(elastic_ips)

        stopped_instances = await aws_service.find_stopped_instances()
        waste_items.extend(stopped_instances)

        total_items = len(waste_items)
        total_monthly_savings = sum(item.get('monthly_cost', 0) for item in waste_items)

        # Group by resource type
        by_type = {}
        for item in waste_items:
            resource_type = item.get('resource_type', 'Unknown')
            if resource_type not in by_type:
                by_type[resource_type] = {'count': 0, 'monthly_cost': 0}
            by_type[resource_type]['count'] += 1
            by_type[resource_type]['monthly_cost'] += item.get('monthly_cost', 0)

        return {
            "total_items": total_items,
            "total_monthly_savings": total_monthly_savings,
            "total_annual_savings": total_monthly_savings * 12,
            "by_resource_type": by_type
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching waste summary: {str(e)}")