from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import asyncio
import structlog
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import settings
from app.api.v1.api import api_router


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# Initialize Sentry for error tracking
if settings.SENTRY_DSN and not settings.DEBUG:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting AWS Cost Sentinel API", version=settings.VERSION)

    # Initialize database connections, cache, etc.
    # await init_database()
    # await init_cache()

    # Start WebSocket cleanup task
    from app.services.websocket_service import websocket_manager
    cleanup_task = asyncio.create_task(websocket_cleanup_worker())

    yield

    # Shutdown
    logger.info("Shutting down AWS Cost Sentinel API")

    # Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Cleanup resources
    # await cleanup_database()
    # await cleanup_cache()


async def websocket_cleanup_worker():
    """Background task to clean up stale WebSocket connections"""
    from app.services.websocket_service import websocket_manager

    while True:
        try:
            await websocket_manager.cleanup_stale_connections()
            await asyncio.sleep(300)  # Run every 5 minutes
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("WebSocket cleanup error", error=str(e))
            await asyncio.sleep(60)  # Wait 1 minute on error


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Open-source AWS cost optimization platform API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Security middleware
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure this properly in production
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monitoring middleware
from app.middleware.monitoring import (
    MonitoringMiddleware,
    PerformanceMiddleware,
    UserActivityMiddleware,
    DatabaseMiddleware,
    SecurityMiddleware
)

app.add_middleware(SecurityMiddleware)
app.add_middleware(UserActivityMiddleware)
app.add_middleware(DatabaseMiddleware)
app.add_middleware(PerformanceMiddleware, slow_request_threshold=2.0)
app.add_middleware(MonitoringMiddleware)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "message": "AWS Cost Sentinel API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring"""
    try:
        from app.services.health_service import health_service

        # Run comprehensive health checks
        health_result = await health_service.check_all(include_details=False)

        # Return 503 if any critical components are unhealthy
        status_code = 200
        if health_result["status"] == "unhealthy":
            status_code = 503
        elif health_result["status"] == "degraded":
            status_code = 200  # Still accepting traffic but with warnings

        # Format response for load balancers
        response = {
            "status": health_result["status"],
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "timestamp": health_result["timestamp"],
            "summary": health_result["summary"]
        }

        if status_code == 503:
            raise HTTPException(status_code=503, detail=response)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with full component status"""
    try:
        from app.services.health_service import health_service
        return await health_service.check_all(include_details=True)
    except Exception as e:
        logger.error("Detailed health check failed", error=str(e))
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/health/{component}")
async def component_health_check(component: str):
    """Health check for a specific component"""
    try:
        from app.services.health_service import health_service
        return await health_service.check_component(component)
    except Exception as e:
        logger.error("Component health check failed", error=str(e), component=component)
        raise HTTPException(status_code=500, detail=f"Component health check failed: {component}")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from app.services.metrics_service import metrics_service
    return metrics_service.export_metrics()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=settings.DEBUG,
    )