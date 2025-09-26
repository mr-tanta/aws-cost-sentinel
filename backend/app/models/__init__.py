from app.db.base import Base
from app.models.user import User
from app.models.aws_account import AWSAccount
from app.models.cost_data import CostData, CostSummary
from app.models.waste import WasteItem
from app.models.recommendation import Recommendation, RecommendationHistory

# Import all models here so Alembic can discover them
__all__ = [
    "Base",
    "User",
    "AWSAccount",
    "CostData",
    "CostSummary",
    "WasteItem",
    "Recommendation",
    "RecommendationHistory",
]