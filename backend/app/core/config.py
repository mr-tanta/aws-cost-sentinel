from typing import List, Optional, Any, Dict
from pydantic import Field, validator
from pydantic_settings import BaseSettings
import secrets
import json


class Settings(BaseSettings):
    # API Settings
    PROJECT_NAME: str = "AWS Cost Sentinel"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")

    # Security
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/cost_sentinel"
    )
    DATABASE_SYNC_URL: str = Field(
        default="postgresql://postgres:password@localhost:5432/cost_sentinel"
    )

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")

    # AWS Configuration
    AWS_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_ROLE_ARN: Optional[str] = None
    AWS_EXTERNAL_ID: Optional[str] = None

    # CORS Settings
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "https://localhost:3000", "http://localhost"]
    )

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            if isinstance(v, str):
                v = json.loads(v)
            return v
        raise ValueError("Invalid CORS origins format")

    # Email Configuration
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: str = "noreply@cost-sentinel.com"

    # Report Storage
    REPORTS_BUCKET: Optional[str] = None
    REPORTS_BASE_URL: Optional[str] = None

    # Monitoring
    SENTRY_DSN: Optional[str] = None

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Data Retention
    COST_DATA_RETENTION_DAYS: int = 395  # ~13 months
    LOG_RETENTION_DAYS: int = 90

    # Background Jobs
    SYNC_FREQUENCY_HOURS: int = 4
    CLEANUP_FREQUENCY_HOURS: int = 24

    # Feature Flags
    FEATURES: Dict[str, bool] = {
        "waste_detection": True,
        "recommendations": True,
        "reports": True,
        "alerts": True,
        "multi_account": True,
        "real_time_sync": False,
    }

    # Pagination
    DEFAULT_PAGE_SIZE: int = 25
    MAX_PAGE_SIZE: int = 100

    # Cache Settings
    CACHE_TTL_SECONDS: int = 300  # 5 minutes
    CACHE_TTL_LONG_SECONDS: int = 3600  # 1 hour

    # Cost Analysis Settings
    COST_ANOMALY_THRESHOLD: float = 20.0  # 20% increase
    MINIMUM_WASTE_COST: float = 1.0  # $1 minimum to consider waste

    # Recommendations Settings
    MIN_RECOMMENDATION_SAVINGS: float = 10.0  # $10 minimum savings
    CONFIDENCE_THRESHOLD: float = 70.0  # 70% minimum confidence

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT.lower() == "testing"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()