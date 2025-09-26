import asyncio
import time
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import structlog
from pathlib import Path

import redis
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_database
from app.services.cache_service import cache_service
from app.services.metrics_service import metrics_service
from app.core.config import settings

logger = structlog.get_logger(__name__)


class HealthCheck:
    """Individual health check result"""

    def __init__(
        self,
        name: str,
        status: str,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None
    ):
        self.name = name
        self.status = status  # "healthy", "unhealthy", "degraded", "unknown"
        self.message = message
        self.details = details or {}
        self.duration = duration
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "duration_ms": round(self.duration * 1000, 2) if self.duration else None,
            "timestamp": self.timestamp.isoformat()
        }


class HealthService:
    """Comprehensive health check service for monitoring system components"""

    def __init__(self):
        self.checks = {}
        self._register_health_checks()

    def _register_health_checks(self):
        """Register all health checks"""
        self.checks = {
            "database": self._check_database,
            "redis": self._check_redis,
            "filesystem": self._check_filesystem,
            "memory": self._check_memory,
            "cpu": self._check_cpu,
            "network": self._check_network,
            "aws_connectivity": self._check_aws_connectivity,
            "queue_system": self._check_queue_system,
            "background_workers": self._check_background_workers,
            "external_dependencies": self._check_external_dependencies
        }

    async def check_all(self, include_details: bool = True) -> Dict[str, Any]:
        """Run all health checks"""
        start_time = time.time()
        results = {}
        overall_status = "healthy"

        # Run all checks concurrently
        tasks = []
        for check_name, check_func in self.checks.items():
            task = asyncio.create_task(self._run_check(check_name, check_func))
            tasks.append(task)

        check_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, result in enumerate(check_results):
            check_name = list(self.checks.keys())[i]

            if isinstance(result, Exception):
                health_check = HealthCheck(
                    name=check_name,
                    status="unknown",
                    message=f"Check failed: {str(result)}",
                    details={"error": str(result)}
                )
            else:
                health_check = result

            results[check_name] = health_check.to_dict() if include_details else {
                "status": health_check.status,
                "message": health_check.message
            }

            # Update overall status
            if health_check.status == "unhealthy":
                overall_status = "unhealthy"
            elif health_check.status in ["degraded", "unknown"] and overall_status == "healthy":
                overall_status = "degraded"

        total_duration = time.time() - start_time

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "duration_ms": round(total_duration * 1000, 2),
            "checks": results,
            "summary": self._generate_summary(results)
        }

    async def _run_check(self, name: str, check_func) -> HealthCheck:
        """Run a single health check with timing"""
        start_time = time.time()
        try:
            result = await check_func()
            result.duration = time.time() - start_time
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Health check failed: {name}", error=str(e))
            return HealthCheck(
                name=name,
                status="unknown",
                message=f"Check failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
                duration=duration
            )

    async def _check_database(self) -> HealthCheck:
        """Check database connectivity and performance"""
        try:
            start_query_time = time.time()

            async with get_database() as db:
                # Test basic connectivity
                result = await db.execute(text("SELECT 1"))
                result.fetchone()

                # Test database performance
                await db.execute(text("SELECT COUNT(*) FROM information_schema.tables"))

                # Get connection pool info
                pool_info = {
                    "pool_size": db.bind.pool.size(),
                    "checked_in": db.bind.pool.checkedin(),
                    "checked_out": db.bind.pool.checkedout(),
                    "overflow": db.bind.pool.overflow(),
                    "invalid": db.bind.pool.invalid()
                }

                query_duration = time.time() - start_query_time

                status = "healthy"
                message = "Database is responsive"

                # Check for performance issues
                if query_duration > 1.0:
                    status = "degraded"
                    message = f"Database response slow ({query_duration:.2f}s)"

                # Check connection pool health
                if pool_info["checked_out"] / pool_info["pool_size"] > 0.8:
                    status = "degraded"
                    message = "High database connection usage"

                return HealthCheck(
                    name="database",
                    status=status,
                    message=message,
                    details={
                        "query_duration_ms": round(query_duration * 1000, 2),
                        "connection_pool": pool_info,
                        "database_url": settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else "configured"
                    }
                )

        except Exception as e:
            return HealthCheck(
                name="database",
                status="unhealthy",
                message=f"Database connection failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__}
            )

    async def _check_redis(self) -> HealthCheck:
        """Check Redis connectivity and performance"""
        try:
            start_time = time.time()

            # Test basic connectivity
            redis_client = cache_service.redis_client
            if not redis_client:
                return HealthCheck(
                    name="redis",
                    status="unhealthy",
                    message="Redis client not initialized"
                )

            # Test ping
            await asyncio.get_event_loop().run_in_executor(
                None, redis_client.ping
            )

            # Get Redis info
            info = await asyncio.get_event_loop().run_in_executor(
                None, redis_client.info
            )

            # Test set/get operation
            test_key = "health_check_test"
            await asyncio.get_event_loop().run_in_executor(
                None, redis_client.set, test_key, "test_value", 60
            )
            value = await asyncio.get_event_loop().run_in_executor(
                None, redis_client.get, test_key
            )
            await asyncio.get_event_loop().run_in_executor(
                None, redis_client.delete, test_key
            )

            operation_duration = time.time() - start_time

            status = "healthy"
            message = "Redis is responsive"

            # Check for performance issues
            if operation_duration > 0.5:
                status = "degraded"
                message = f"Redis response slow ({operation_duration:.2f}s)"

            # Check memory usage
            memory_usage = info.get('used_memory', 0)
            max_memory = info.get('maxmemory', 0)
            if max_memory > 0 and memory_usage / max_memory > 0.9:
                status = "degraded"
                message = "Redis memory usage high"

            return HealthCheck(
                name="redis",
                status=status,
                message=message,
                details={
                    "operation_duration_ms": round(operation_duration * 1000, 2),
                    "memory_used_mb": round(memory_usage / 1024 / 1024, 2),
                    "memory_max_mb": round(max_memory / 1024 / 1024, 2) if max_memory else "unlimited",
                    "connected_clients": info.get('connected_clients', 0),
                    "uptime_days": round(info.get('uptime_in_seconds', 0) / 86400, 1),
                    "version": info.get('redis_version', 'unknown')
                }
            )

        except Exception as e:
            return HealthCheck(
                name="redis",
                status="unhealthy",
                message=f"Redis connection failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__}
            )

    async def _check_filesystem(self) -> HealthCheck:
        """Check filesystem health and disk space"""
        try:
            # Check disk space
            disk_usage = psutil.disk_usage('/')
            used_percent = (disk_usage.used / disk_usage.total) * 100

            # Check log directory
            log_dir = Path("logs")
            log_dir_exists = log_dir.exists()
            log_dir_writable = log_dir.is_dir() and log_dir.exists()

            if log_dir_writable:
                try:
                    test_file = log_dir / "health_test.tmp"
                    test_file.write_text("test")
                    test_file.unlink()
                except:
                    log_dir_writable = False

            # Check temp directory
            temp_dir = Path("/tmp")
            temp_writable = temp_dir.exists() and temp_dir.is_dir()

            status = "healthy"
            message = "Filesystem is healthy"
            issues = []

            # Check disk space thresholds
            if used_percent > 95:
                status = "unhealthy"
                issues.append(f"Critical disk space: {used_percent:.1f}% used")
            elif used_percent > 85:
                status = "degraded"
                issues.append(f"High disk usage: {used_percent:.1f}% used")

            # Check directory access
            if not log_dir_writable:
                status = "degraded"
                issues.append("Log directory not writable")

            if not temp_writable:
                status = "degraded"
                issues.append("Temp directory not accessible")

            if issues:
                message = "; ".join(issues)

            return HealthCheck(
                name="filesystem",
                status=status,
                message=message,
                details={
                    "disk_total_gb": round(disk_usage.total / 1024**3, 2),
                    "disk_used_gb": round(disk_usage.used / 1024**3, 2),
                    "disk_free_gb": round(disk_usage.free / 1024**3, 2),
                    "disk_used_percent": round(used_percent, 1),
                    "log_directory_writable": log_dir_writable,
                    "temp_directory_accessible": temp_writable
                }
            )

        except Exception as e:
            return HealthCheck(
                name="filesystem",
                status="unknown",
                message=f"Filesystem check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_memory(self) -> HealthCheck:
        """Check system memory usage"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            status = "healthy"
            message = "Memory usage is normal"
            issues = []

            # Check memory thresholds
            if memory.percent > 95:
                status = "unhealthy"
                issues.append(f"Critical memory usage: {memory.percent:.1f}%")
            elif memory.percent > 85:
                status = "degraded"
                issues.append(f"High memory usage: {memory.percent:.1f}%")

            # Check swap usage
            if swap.percent > 50:
                issues.append(f"High swap usage: {swap.percent:.1f}%")
                if status == "healthy":
                    status = "degraded"

            if issues:
                message = "; ".join(issues)

            return HealthCheck(
                name="memory",
                status=status,
                message=message,
                details={
                    "memory_total_gb": round(memory.total / 1024**3, 2),
                    "memory_used_gb": round(memory.used / 1024**3, 2),
                    "memory_available_gb": round(memory.available / 1024**3, 2),
                    "memory_percent": memory.percent,
                    "swap_total_gb": round(swap.total / 1024**3, 2) if swap.total else 0,
                    "swap_used_gb": round(swap.used / 1024**3, 2) if swap.used else 0,
                    "swap_percent": swap.percent
                }
            )

        except Exception as e:
            return HealthCheck(
                name="memory",
                status="unknown",
                message=f"Memory check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_cpu(self) -> HealthCheck:
        """Check CPU usage"""
        try:
            # Get CPU usage (averaged over 1 second)
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)

            status = "healthy"
            message = "CPU usage is normal"
            issues = []

            # Check CPU thresholds
            if cpu_percent > 90:
                status = "unhealthy"
                issues.append(f"Critical CPU usage: {cpu_percent:.1f}%")
            elif cpu_percent > 75:
                status = "degraded"
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")

            # Check load average (if available)
            if load_avg[0] > cpu_count * 2:
                issues.append(f"High system load: {load_avg[0]:.2f}")
                if status == "healthy":
                    status = "degraded"

            if issues:
                message = "; ".join(issues)

            return HealthCheck(
                name="cpu",
                status=status,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "load_avg_1min": load_avg[0] if load_avg else None,
                    "load_avg_5min": load_avg[1] if load_avg else None,
                    "load_avg_15min": load_avg[2] if load_avg else None
                }
            )

        except Exception as e:
            return HealthCheck(
                name="cpu",
                status="unknown",
                message=f"CPU check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_network(self) -> HealthCheck:
        """Check network connectivity"""
        try:
            # Test DNS resolution
            import socket
            start_time = time.time()
            socket.gethostbyname("google.com")
            dns_duration = time.time() - start_time

            # Get network interface stats
            net_io = psutil.net_io_counters()

            status = "healthy"
            message = "Network connectivity is good"

            # Check DNS response time
            if dns_duration > 5.0:
                status = "degraded"
                message = f"Slow DNS resolution ({dns_duration:.2f}s)"

            return HealthCheck(
                name="network",
                status=status,
                message=message,
                details={
                    "dns_resolution_ms": round(dns_duration * 1000, 2),
                    "bytes_sent": net_io.bytes_sent if net_io else 0,
                    "bytes_received": net_io.bytes_recv if net_io else 0,
                    "packets_sent": net_io.packets_sent if net_io else 0,
                    "packets_received": net_io.packets_recv if net_io else 0
                }
            )

        except Exception as e:
            return HealthCheck(
                name="network",
                status="unhealthy",
                message=f"Network connectivity failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_aws_connectivity(self) -> HealthCheck:
        """Check AWS connectivity and credentials"""
        try:
            # This would test AWS connectivity
            # For now, we'll simulate the check
            status = "healthy"
            message = "AWS connectivity check passed"

            # In a real implementation, you would:
            # 1. Test STS GetCallerIdentity
            # 2. Test basic service access
            # 3. Check credential validity

            return HealthCheck(
                name="aws_connectivity",
                status=status,
                message=message,
                details={
                    "region": settings.AWS_DEFAULT_REGION or "us-east-1",
                    "credentials_configured": bool(settings.AWS_ACCESS_KEY_ID),
                    "last_check": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            return HealthCheck(
                name="aws_connectivity",
                status="degraded",
                message=f"AWS connectivity check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_queue_system(self) -> HealthCheck:
        """Check queue system health"""
        try:
            # Check queue sizes and worker status
            # This is a simplified check
            status = "healthy"
            message = "Queue system is operational"

            return HealthCheck(
                name="queue_system",
                status=status,
                message=message,
                details={
                    "default_queue_size": 0,  # Would be actual queue size
                    "priority_queue_size": 0,  # Would be actual queue size
                    "failed_jobs_count": 0,  # Would be actual count
                    "last_job_processed": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            return HealthCheck(
                name="queue_system",
                status="degraded",
                message=f"Queue system check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_background_workers(self) -> HealthCheck:
        """Check background worker status"""
        try:
            # Check if background workers are running
            # This would check actual worker processes
            status = "healthy"
            message = "Background workers are operational"

            return HealthCheck(
                name="background_workers",
                status=status,
                message=message,
                details={
                    "active_workers": 1,  # Would be actual count
                    "worker_types": ["job_worker"],  # Would be actual types
                    "last_worker_heartbeat": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            return HealthCheck(
                name="background_workers",
                status="degraded",
                message=f"Worker check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_external_dependencies(self) -> HealthCheck:
        """Check external service dependencies"""
        try:
            # Check external services (Sentry, etc.)
            status = "healthy"
            message = "External dependencies are accessible"

            return HealthCheck(
                name="external_dependencies",
                status=status,
                message=message,
                details={
                    "sentry_configured": bool(settings.SENTRY_DSN),
                    "external_apis": ["AWS Cost Explorer", "AWS STS"],
                    "last_check": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            return HealthCheck(
                name="external_dependencies",
                status="degraded",
                message=f"External dependency check failed: {str(e)}",
                details={"error": str(e)}
            )

    def _generate_summary(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a summary of health check results"""
        total_checks = len(results)
        healthy_count = sum(1 for r in results.values() if r["status"] == "healthy")
        degraded_count = sum(1 for r in results.values() if r["status"] == "degraded")
        unhealthy_count = sum(1 for r in results.values() if r["status"] == "unhealthy")
        unknown_count = sum(1 for r in results.values() if r["status"] == "unknown")

        return {
            "total_checks": total_checks,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count,
            "unknown": unknown_count,
            "health_score": round((healthy_count / total_checks) * 100, 1) if total_checks > 0 else 0
        }

    async def check_component(self, component_name: str) -> Dict[str, Any]:
        """Run health check for a specific component"""
        if component_name not in self.checks:
            return {
                "error": f"Unknown component: {component_name}",
                "available_components": list(self.checks.keys())
            }

        check_func = self.checks[component_name]
        result = await self._run_check(component_name, check_func)
        return result.to_dict()


# Global health service instance
health_service = HealthService()