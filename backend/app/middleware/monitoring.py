import time
import uuid
from typing import Callable, Any, Dict
import structlog
from fastapi import Request, Response
from fastapi.routing import Match
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.services.metrics_service import metrics_service

logger = structlog.get_logger(__name__)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting performance and usage metrics"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.sensitive_endpoints = {
            '/auth/login',
            '/auth/refresh',
            '/auth/register',
            '/aws/accounts'
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics"""

        # Generate unique request ID for tracing
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Start timing
        start_time = time.time()

        # Get endpoint information
        endpoint = self._get_endpoint_name(request)
        method = request.method

        # Add structured logging context
        log_context = {
            "request_id": request_id,
            "method": method,
            "endpoint": endpoint,
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent", "")
        }

        # Add user context if available
        if hasattr(request.state, 'current_user') and request.state.current_user:
            log_context["user_id"] = str(request.state.current_user.id)
            log_context["user_email"] = request.state.current_user.email

        logger.info("Request started", **log_context)

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Record metrics
            metrics_service.record_http_request(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration=duration
            )

            # Log completion
            log_context.update({
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "response_size": len(response.body) if hasattr(response, 'body') else 0
            })

            # Don't log sensitive data
            if endpoint not in self.sensitive_endpoints:
                logger.info("Request completed", **log_context)
            else:
                logger.info("Sensitive request completed",
                           request_id=request_id,
                           method=method,
                           endpoint="[SENSITIVE]",
                           status_code=response.status_code,
                           duration_ms=round(duration * 1000, 2))

            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}s"

            return response

        except Exception as e:
            # Calculate duration for failed requests
            duration = time.time() - start_time

            # Record error metrics
            metrics_service.record_http_request(
                method=method,
                endpoint=endpoint,
                status_code=500,
                duration=duration
            )

            metrics_service.record_error(
                error_type=type(e).__name__,
                component="api"
            )

            # Log error
            log_context.update({
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_ms": round(duration * 1000, 2)
            })

            logger.error("Request failed", **log_context)
            raise

    def _get_endpoint_name(self, request: Request) -> str:
        """Extract endpoint name from request"""
        try:
            for route in request.app.routes:
                match, _ = route.matches({"type": "http", "path": request.url.path, "method": request.method})
                if match == Match.FULL:
                    return route.path
            return request.url.path
        except:
            return request.url.path

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware for detailed performance monitoring"""

    def __init__(self, app: ASGIApp, slow_request_threshold: float = 1.0):
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Monitor request performance"""

        start_time = time.time()

        # Set performance tracking on request state
        request.state.performance_start = start_time

        try:
            response = await call_next(request)

            duration = time.time() - start_time

            # Log slow requests
            if duration > self.slow_request_threshold:
                logger.warning("Slow request detected",
                             request_id=getattr(request.state, 'request_id', 'unknown'),
                             method=request.method,
                             endpoint=request.url.path,
                             duration_ms=round(duration * 1000, 2),
                             threshold_ms=round(self.slow_request_threshold * 1000, 2))

            # Add performance headers
            response.headers["X-Performance-Duration"] = f"{duration:.3f}"

            # Mark as slow if above threshold
            if duration > self.slow_request_threshold:
                response.headers["X-Performance-Slow"] = "true"

            return response

        except Exception:
            # Still track performance for failed requests
            duration = time.time() - start_time
            if duration > self.slow_request_threshold:
                logger.warning("Slow failed request",
                             request_id=getattr(request.state, 'request_id', 'unknown'),
                             method=request.method,
                             endpoint=request.url.path,
                             duration_ms=round(duration * 1000, 2))
            raise


class UserActivityMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking user activity"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.tracked_endpoints = {
            '/dashboard',
            '/aws/accounts',
            '/costs',
            '/waste',
            '/recommendations',
            '/reports'
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track user activity"""

        response = await call_next(request)

        # Only track activity for authenticated users
        if hasattr(request.state, 'current_user') and request.state.current_user:
            user_id = str(request.state.current_user.id)

            # Determine action type
            action = self._determine_action(request)

            if action:
                metrics_service.record_user_action(
                    action=action,
                    user_id=user_id
                )

        return response

    def _determine_action(self, request: Request) -> str:
        """Determine the action type from the request"""
        method = request.method
        path = request.url.path

        # Map endpoints to actions
        if path.startswith('/api/v1/dashboard'):
            return 'view_dashboard'
        elif path.startswith('/api/v1/aws/accounts'):
            if method == 'POST':
                return 'connect_aws_account'
            elif method == 'GET':
                return 'view_aws_accounts'
            elif method == 'DELETE':
                return 'disconnect_aws_account'
        elif path.startswith('/api/v1/costs'):
            if method == 'POST':
                return 'sync_cost_data'
            elif method == 'GET':
                return 'view_cost_analysis'
        elif path.startswith('/api/v1/waste'):
            if method == 'POST':
                return 'run_waste_scan'
            elif method == 'GET':
                return 'view_waste_analysis'
        elif path.startswith('/api/v1/recommendations'):
            if method == 'POST':
                return 'generate_recommendations'
            elif method == 'GET':
                return 'view_recommendations'
        elif path.startswith('/api/v1/reports'):
            if method == 'POST' and 'generate' in path:
                return 'generate_report'
            elif method == 'POST' and 'schedule' in path:
                return 'schedule_report'
            elif method == 'GET':
                return 'view_reports'

        return None


class DatabaseMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking database performance"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track database metrics during request processing"""

        # Initialize DB tracking
        request.state.db_queries = []
        request.state.db_query_count = 0
        request.state.db_query_time = 0.0

        try:
            response = await call_next(request)

            # Log database usage if significant
            if request.state.db_query_count > 10:
                logger.info("High DB query count",
                           request_id=getattr(request.state, 'request_id', 'unknown'),
                           query_count=request.state.db_query_count,
                           total_time_ms=round(request.state.db_query_time * 1000, 2))

            # Record database connection metrics
            metrics_service.record_db_connection(
                active_count=request.state.db_query_count
            )

            return response

        except Exception:
            raise


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security monitoring"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.rate_limit_headers = {
            'X-RateLimit-Limit',
            'X-RateLimit-Remaining',
            'X-RateLimit-Reset'
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Monitor security-related events"""

        # Check for suspicious patterns
        self._check_suspicious_patterns(request)

        response = await call_next(request)

        # Monitor authentication failures
        if response.status_code == 401:
            self._log_auth_failure(request)
        elif response.status_code == 403:
            self._log_authorization_failure(request)

        # Check for rate limiting
        self._check_rate_limiting(request, response)

        return response

    def _check_suspicious_patterns(self, request: Request):
        """Check for suspicious request patterns"""

        # Check for SQL injection patterns
        query_string = str(request.query_params)
        if any(pattern in query_string.lower() for pattern in ['union select', 'drop table', '1=1']):
            logger.warning("Potential SQL injection attempt",
                         request_id=getattr(request.state, 'request_id', 'unknown'),
                         client_ip=self._get_client_ip(request),
                         query_string=query_string)

            metrics_service.record_error(
                error_type="security_threat",
                component="sql_injection_attempt"
            )

    def _log_auth_failure(self, request: Request):
        """Log authentication failure"""
        logger.warning("Authentication failure",
                      request_id=getattr(request.state, 'request_id', 'unknown'),
                      client_ip=self._get_client_ip(request),
                      endpoint=request.url.path,
                      user_agent=request.headers.get("user-agent", ""))

        metrics_service.record_error(
            error_type="authentication_failure",
            component="auth"
        )

    def _log_authorization_failure(self, request: Request):
        """Log authorization failure"""
        user_id = "unknown"
        if hasattr(request.state, 'current_user') and request.state.current_user:
            user_id = str(request.state.current_user.id)

        logger.warning("Authorization failure",
                      request_id=getattr(request.state, 'request_id', 'unknown'),
                      user_id=user_id,
                      client_ip=self._get_client_ip(request),
                      endpoint=request.url.path)

        metrics_service.record_error(
            error_type="authorization_failure",
            component="auth"
        )

    def _check_rate_limiting(self, request: Request, response: Response):
        """Check if request hit rate limits"""
        if response.status_code == 429:
            logger.warning("Rate limit exceeded",
                          request_id=getattr(request.state, 'request_id', 'unknown'),
                          client_ip=self._get_client_ip(request),
                          endpoint=request.url.path)

            metrics_service.record_error(
                error_type="rate_limit_exceeded",
                component="rate_limiter"
            )

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"