import time
import asyncio
from typing import Dict, Any, Optional, List
from functools import wraps
import psutil
import structlog
from datetime import datetime, timedelta
from collections import defaultdict

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    CollectorRegistry,
    multiprocess,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)
from fastapi import Response

logger = structlog.get_logger(__name__)


class MetricsService:
    """Comprehensive metrics collection service using Prometheus"""

    def __init__(self):
        self.registry = REGISTRY
        self._setup_metrics()
        self._setup_system_metrics()
        self._business_metrics = defaultdict(float)

    def _setup_metrics(self):
        """Initialize Prometheus metrics"""

        # API Metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total number of HTTP requests',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )

        self.http_request_duration_seconds = Histogram(
            'http_request_duration_seconds',
            'HTTP request latency',
            ['method', 'endpoint'],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0],
            registry=self.registry
        )

        # Database Metrics
        self.db_query_duration_seconds = Histogram(
            'db_query_duration_seconds',
            'Database query execution time',
            ['query_type', 'table'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
            registry=self.registry
        )

        self.db_connections_active = Gauge(
            'db_connections_active',
            'Number of active database connections',
            registry=self.registry
        )

        self.db_connections_total = Counter(
            'db_connections_total',
            'Total number of database connections created',
            registry=self.registry
        )

        # Cache Metrics
        self.cache_operations_total = Counter(
            'cache_operations_total',
            'Total cache operations',
            ['operation', 'status'],
            registry=self.registry
        )

        self.cache_hit_ratio = Gauge(
            'cache_hit_ratio',
            'Cache hit ratio',
            registry=self.registry
        )

        self.cache_size_bytes = Gauge(
            'cache_size_bytes',
            'Cache size in bytes',
            registry=self.registry
        )

        # Queue Metrics
        self.queue_jobs_total = Counter(
            'queue_jobs_total',
            'Total number of jobs processed',
            ['queue_name', 'job_type', 'status'],
            registry=self.registry
        )

        self.queue_job_duration_seconds = Histogram(
            'queue_job_duration_seconds',
            'Job processing duration',
            ['queue_name', 'job_type'],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0],
            registry=self.registry
        )

        self.queue_size = Gauge(
            'queue_size',
            'Number of jobs in queue',
            ['queue_name', 'status'],
            registry=self.registry
        )

        # AWS API Metrics
        self.aws_api_calls_total = Counter(
            'aws_api_calls_total',
            'Total AWS API calls',
            ['service', 'operation', 'status'],
            registry=self.registry
        )

        self.aws_api_duration_seconds = Histogram(
            'aws_api_duration_seconds',
            'AWS API call duration',
            ['service', 'operation'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry
        )

        self.aws_api_rate_limit_hits = Counter(
            'aws_api_rate_limit_hits_total',
            'AWS API rate limit hits',
            ['service'],
            registry=self.registry
        )

        # Business Metrics
        self.cost_data_processed_total = Counter(
            'cost_data_processed_total',
            'Total cost data records processed',
            ['account_id'],
            registry=self.registry
        )

        self.waste_items_detected_total = Counter(
            'waste_items_detected_total',
            'Total waste items detected',
            ['category', 'account_id'],
            registry=self.registry
        )

        self.recommendations_generated_total = Counter(
            'recommendations_generated_total',
            'Total recommendations generated',
            ['type', 'account_id'],
            registry=self.registry
        )

        self.potential_savings_total = Gauge(
            'potential_savings_total',
            'Total potential savings identified',
            ['account_id'],
            registry=self.registry
        )

        self.total_cost_monitored = Gauge(
            'total_cost_monitored',
            'Total AWS costs being monitored',
            ['account_id'],
            registry=self.registry
        )

        # User Metrics
        self.active_users = Gauge(
            'active_users',
            'Number of active users',
            registry=self.registry
        )

        self.user_actions_total = Counter(
            'user_actions_total',
            'Total user actions',
            ['action', 'user_id'],
            registry=self.registry
        )

        # WebSocket Metrics
        self.websocket_connections_active = Gauge(
            'websocket_connections_active',
            'Active WebSocket connections',
            registry=self.registry
        )

        self.websocket_messages_total = Counter(
            'websocket_messages_total',
            'Total WebSocket messages',
            ['direction', 'message_type'],
            registry=self.registry
        )

        # Report Metrics
        self.reports_generated_total = Counter(
            'reports_generated_total',
            'Total reports generated',
            ['format', 'account_id'],
            registry=self.registry
        )

        self.report_generation_duration_seconds = Histogram(
            'report_generation_duration_seconds',
            'Report generation duration',
            ['format'],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
            registry=self.registry
        )

        # Error Metrics
        self.errors_total = Counter(
            'errors_total',
            'Total errors',
            ['error_type', 'component'],
            registry=self.registry
        )

    def _setup_system_metrics(self):
        """Initialize system-level metrics"""

        self.system_cpu_percent = Gauge(
            'system_cpu_percent',
            'System CPU usage percentage',
            registry=self.registry
        )

        self.system_memory_bytes = Gauge(
            'system_memory_bytes',
            'System memory usage',
            ['type'],  # total, available, used
            registry=self.registry
        )

        self.system_disk_bytes = Gauge(
            'system_disk_bytes',
            'System disk usage',
            ['type'],  # total, free, used
            registry=self.registry
        )

        self.application_info = Info(
            'application_info',
            'Application information',
            registry=self.registry
        )

    async def update_system_metrics(self):
        """Update system-level metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_percent.set(cpu_percent)

            # Memory metrics
            memory = psutil.virtual_memory()
            self.system_memory_bytes.labels(type='total').set(memory.total)
            self.system_memory_bytes.labels(type='available').set(memory.available)
            self.system_memory_bytes.labels(type='used').set(memory.used)

            # Disk metrics
            disk = psutil.disk_usage('/')
            self.system_disk_bytes.labels(type='total').set(disk.total)
            self.system_disk_bytes.labels(type='free').set(disk.free)
            self.system_disk_bytes.labels(type='used').set(disk.used)

            # Application info
            from app.core.config import settings
            self.application_info.info({
                'version': settings.VERSION,
                'environment': settings.ENVIRONMENT,
                'python_version': '3.11',  # You can get this dynamically
            })

        except Exception as e:
            logger.error("Failed to update system metrics", error=str(e))

    # Metric recording methods

    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics"""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()

        self.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def record_db_query(self, query_type: str, table: str, duration: float):
        """Record database query metrics"""
        self.db_query_duration_seconds.labels(
            query_type=query_type,
            table=table
        ).observe(duration)

    def record_cache_operation(self, operation: str, status: str):
        """Record cache operation metrics"""
        self.cache_operations_total.labels(
            operation=operation,
            status=status
        ).inc()

    def update_cache_metrics(self, hit_ratio: float, size_bytes: int):
        """Update cache metrics"""
        self.cache_hit_ratio.set(hit_ratio)
        self.cache_size_bytes.set(size_bytes)

    def record_queue_job(self, queue_name: str, job_type: str, status: str, duration: float = None):
        """Record queue job metrics"""
        self.queue_jobs_total.labels(
            queue_name=queue_name,
            job_type=job_type,
            status=status
        ).inc()

        if duration is not None:
            self.queue_job_duration_seconds.labels(
                queue_name=queue_name,
                job_type=job_type
            ).observe(duration)

    def update_queue_size(self, queue_name: str, pending: int, running: int):
        """Update queue size metrics"""
        self.queue_size.labels(queue_name=queue_name, status='pending').set(pending)
        self.queue_size.labels(queue_name=queue_name, status='running').set(running)

    def record_aws_api_call(self, service: str, operation: str, status: str, duration: float):
        """Record AWS API call metrics"""
        self.aws_api_calls_total.labels(
            service=service,
            operation=operation,
            status=status
        ).inc()

        self.aws_api_duration_seconds.labels(
            service=service,
            operation=operation
        ).observe(duration)

    def record_aws_rate_limit_hit(self, service: str):
        """Record AWS API rate limit hit"""
        self.aws_api_rate_limit_hits.labels(service=service).inc()

    def record_cost_data_processed(self, account_id: str, record_count: int):
        """Record cost data processing metrics"""
        self.cost_data_processed_total.labels(account_id=account_id).inc(record_count)

    def record_waste_item_detected(self, category: str, account_id: str):
        """Record waste item detection"""
        self.waste_items_detected_total.labels(
            category=category,
            account_id=account_id
        ).inc()

    def record_recommendation_generated(self, recommendation_type: str, account_id: str):
        """Record recommendation generation"""
        self.recommendations_generated_total.labels(
            type=recommendation_type,
            account_id=account_id
        ).inc()

    def update_potential_savings(self, account_id: str, amount: float):
        """Update potential savings metric"""
        self.potential_savings_total.labels(account_id=account_id).set(amount)

    def update_total_cost_monitored(self, account_id: str, amount: float):
        """Update total cost monitored metric"""
        self.total_cost_monitored.labels(account_id=account_id).set(amount)

    def update_active_users(self, count: int):
        """Update active users count"""
        self.active_users.set(count)

    def record_user_action(self, action: str, user_id: str):
        """Record user action"""
        self.user_actions_total.labels(action=action, user_id=user_id).inc()

    def update_websocket_connections(self, count: int):
        """Update WebSocket connections count"""
        self.websocket_connections_active.set(count)

    def record_websocket_message(self, direction: str, message_type: str):
        """Record WebSocket message"""
        self.websocket_messages_total.labels(
            direction=direction,
            message_type=message_type
        ).inc()

    def record_report_generated(self, format_type: str, account_id: str, duration: float):
        """Record report generation"""
        self.reports_generated_total.labels(
            format=format_type,
            account_id=account_id
        ).inc()

        self.report_generation_duration_seconds.labels(
            format=format_type
        ).observe(duration)

    def record_error(self, error_type: str, component: str):
        """Record error occurrence"""
        self.errors_total.labels(
            error_type=error_type,
            component=component
        ).inc()

    def record_db_connection(self, active_count: int):
        """Record database connection metrics"""
        self.db_connections_active.set(active_count)
        self.db_connections_total.inc()

    # Decorators for automatic metrics collection

    def track_time(self, metric_name: str, labels: Dict[str, str] = None):
        """Decorator to track function execution time"""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    duration = time.time() - start_time
                    if hasattr(self, metric_name):
                        metric = getattr(self, metric_name)
                        if labels:
                            metric.labels(**labels).observe(duration)
                        else:
                            metric.observe(duration)

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration = time.time() - start_time
                    if hasattr(self, metric_name):
                        metric = getattr(self, metric_name)
                        if labels:
                            metric.labels(**labels).observe(duration)
                        else:
                            metric.observe(duration)

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator

    def count_calls(self, metric_name: str, labels: Dict[str, str] = None):
        """Decorator to count function calls"""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    result = await func(*args, **kwargs)
                    if hasattr(self, metric_name):
                        metric = getattr(self, metric_name)
                        if labels:
                            metric.labels(**labels).inc()
                        else:
                            metric.inc()
                    return result
                except Exception as e:
                    if hasattr(self, metric_name):
                        error_labels = labels.copy() if labels else {}
                        error_labels['status'] = 'error'
                        metric = getattr(self, metric_name)
                        metric.labels(**error_labels).inc()
                    raise

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    result = func(*args, **kwargs)
                    if hasattr(self, metric_name):
                        metric = getattr(self, metric_name)
                        if labels:
                            metric.labels(**labels).inc()
                        else:
                            metric.inc()
                    return result
                except Exception as e:
                    if hasattr(self, metric_name):
                        error_labels = labels.copy() if labels else {}
                        error_labels['status'] = 'error'
                        metric = getattr(self, metric_name)
                        metric.labels(**error_labels).inc()
                    raise

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of current metrics"""
        await self.update_system_metrics()

        # Get sample values (in a real implementation, you'd query the actual metrics)
        return {
            "system": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent
            },
            "application": {
                "active_connections": 0,  # Would be actual value
                "cache_hit_ratio": 0.85,  # Would be actual value
                "queue_size": 0,  # Would be actual value
            },
            "business": {
                "total_accounts": 0,  # Would be actual value
                "total_cost_monitored": 0.0,  # Would be actual value
                "potential_savings": 0.0,  # Would be actual value
            }
        }

    def export_metrics(self) -> Response:
        """Export metrics in Prometheus format"""
        try:
            data = generate_latest(self.registry)
            return Response(content=data, media_type=CONTENT_TYPE_LATEST)
        except Exception as e:
            logger.error("Failed to export metrics", error=str(e))
            return Response(content="", media_type=CONTENT_TYPE_LATEST)


# Global metrics service instance
metrics_service = MetricsService()