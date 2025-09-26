from fastapi import APIRouter, HTTPException
from typing import List

from app.models.schemas import Recommendation
from app.services.recommendations_service import recommendations_service

router = APIRouter()


@router.get("", response_model=List[Recommendation])
async def get_recommendations():
    """Get all cost optimization recommendations."""
    try:
        recommendations = await recommendations_service.generate_recommendations()
        return [Recommendation(**rec) for rec in recommendations]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recommendations: {str(e)}")


@router.post("/{recommendation_id}/apply")
async def apply_recommendation(recommendation_id: str):
    """Apply a specific recommendation."""
    try:
        success = await recommendations_service.apply_recommendation(recommendation_id)
        if success:
            return {"message": f"Recommendation {recommendation_id} has been applied successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to apply recommendation")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying recommendation: {str(e)}")


@router.post("/{recommendation_id}/dismiss")
async def dismiss_recommendation(recommendation_id: str):
    """Dismiss a specific recommendation."""
    try:
        success = await recommendations_service.dismiss_recommendation(recommendation_id)
        if success:
            return {"message": f"Recommendation {recommendation_id} has been dismissed"}
        else:
            raise HTTPException(status_code=400, detail="Failed to dismiss recommendation")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error dismissing recommendation: {str(e)}")


@router.get("/summary")
async def get_recommendations_summary():
    """Get summary of recommendations including potential savings."""
    try:
        recommendations = await recommendations_service.generate_recommendations()

        total_recommendations = len(recommendations)
        total_monthly_savings = sum(rec.get('monthly_savings', 0) for rec in recommendations)
        total_annual_savings = total_monthly_savings * 12

        # Group by type
        by_type = {}
        for rec in recommendations:
            rec_type = rec.get('type', 'unknown')
            if rec_type not in by_type:
                by_type[rec_type] = {'count': 0, 'monthly_savings': 0}
            by_type[rec_type]['count'] += 1
            by_type[rec_type]['monthly_savings'] += rec.get('monthly_savings', 0)

        # Group by risk level
        by_risk = {}
        for rec in recommendations:
            risk_level = rec.get('risk_level', 'unknown')
            if risk_level not in by_risk:
                by_risk[risk_level] = {'count': 0, 'monthly_savings': 0}
            by_risk[risk_level]['count'] += 1
            by_risk[risk_level]['monthly_savings'] += rec.get('monthly_savings', 0)

        return {
            "total_recommendations": total_recommendations,
            "total_monthly_savings": total_monthly_savings,
            "total_annual_savings": total_annual_savings,
            "by_type": by_type,
            "by_risk_level": by_risk,
            "top_opportunities": sorted(recommendations, key=lambda x: x.get('monthly_savings', 0), reverse=True)[:5]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recommendations summary: {str(e)}")