import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import structlog
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pythonjsonlogger import jsonlogger

from app.core.config import settings


class LoggingService:
    """Enhanced logging service with structured logging, audit trails, and log management"""

    def __init__(self):
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self._setup_loggers()
        self._configure_structlog()

    def _setup_loggers(self):
        """Set up various loggers for different purposes"""

        # Main application logger
        self.app_logger = self._create_logger(
            name="aws_cost_sentinel",
            filename="application.log",
            level=getattr(logging, settings.LOG_LEVEL.upper())
        )

        # API access logger
        self.access_logger = self._create_logger(
            name="aws_cost_sentinel.access",
            filename="access.log",
            level=logging.INFO,
            formatter_type="access"
        )

        # Security audit logger
        self.security_logger = self._create_logger(
            name="aws_cost_sentinel.security",
            filename="security.log",
            level=logging.WARNING,
            formatter_type="security"
        )

        # Database operations logger
        self.db_logger = self._create_logger(
            name="aws_cost_sentinel.database",
            filename="database.log",
            level=logging.INFO
        )

        # AWS API logger
        self.aws_logger = self._create_logger(
            name="aws_cost_sentinel.aws",
            filename="aws_api.log",
            level=logging.INFO
        )

        # Job/Task logger
        self.job_logger = self._create_logger(
            name="aws_cost_sentinel.jobs",
            filename="jobs.log",
            level=logging.INFO
        )

        # Error logger (high priority errors)
        self.error_logger = self._create_logger(
            name="aws_cost_sentinel.errors",
            filename="errors.log",
            level=logging.ERROR,
            max_bytes=50 * 1024 * 1024,  # 50MB
            backup_count=10
        )

    def _create_logger(
        self,
        name: str,
        filename: str,
        level: int = logging.INFO,
        formatter_type: str = "json",
        max_bytes: int = 20 * 1024 * 1024,  # 20MB default
        backup_count: int = 5
    ) -> logging.Logger:
        """Create a configured logger"""

        logger = logging.getLogger(name)
        logger.setLevel(level)

        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # File handler with rotation
        file_path = self.log_dir / filename
        file_handler = RotatingFileHandler(
            filename=file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)

        # Console handler for development
        if settings.DEBUG:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            logger.addHandler(console_handler)

        # Set formatter
        if formatter_type == "json":
            formatter = jsonlogger.JsonFormatter(
                fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        elif formatter_type == "access":
            formatter = logging.Formatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        elif formatter_type == "security":
            formatter = jsonlogger.JsonFormatter(
                fmt='%(asctime)s %(name)s %(levelname)s %(funcName)s %(lineno)d %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            formatter = jsonlogger.JsonFormatter()

        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def _configure_structlog(self):
        """Configure structlog for structured logging"""

        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        # Add JSON renderer for production, console for development
        if settings.ENVIRONMENT == "development":
            processors.append(structlog.dev.ConsoleRenderer())
        else:
            processors.append(structlog.processors.JSONRenderer())

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

    # Specialized logging methods

    def log_api_access(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """Log API access"""
        self.access_logger.info(
            "API Access",
            extra={
                "method": method,
                "endpoint": endpoint,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2),
                "user_id": user_id,
                "client_ip": client_ip,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    def log_security_event(
        self,
        event_type: str,
        description: str,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Log security-related events"""
        log_data = {
            "event_type": event_type,
            "description": description,
            "user_id": user_id,
            "client_ip": client_ip,
            "timestamp": datetime.utcnow().isoformat()
        }

        if additional_data:
            log_data.update(additional_data)

        self.security_logger.warning(
            "Security Event",
            extra=log_data
        )

    def log_auth_event(
        self,
        event: str,
        user_email: str,
        success: bool,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None
    ):
        """Log authentication events"""
        log_data = {
            "event": event,
            "user_email": user_email,
            "success": success,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow().isoformat()
        }

        if not success and failure_reason:
            log_data["failure_reason"] = failure_reason

        level = logging.INFO if success else logging.WARNING
        self.security_logger.log(
            level,
            "Authentication Event",
            extra=log_data
        )

    def log_aws_api_call(
        self,
        service: str,
        operation: str,
        duration: float,
        success: bool,
        account_id: Optional[str] = None,
        error_message: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """Log AWS API calls"""
        log_data = {
            "service": service,
            "operation": operation,
            "duration_ms": round(duration * 1000, 2),
            "success": success,
            "account_id": account_id,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        if not success and error_message:
            log_data["error_message"] = error_message

        level = logging.INFO if success else logging.ERROR
        self.aws_logger.log(
            level,
            "AWS API Call",
            extra=log_data
        )

    def log_database_operation(
        self,
        operation: str,
        table: str,
        duration: float,
        rows_affected: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """Log database operations"""
        log_data = {
            "operation": operation,
            "table": table,
            "duration_ms": round(duration * 1000, 2),
            "rows_affected": rows_affected,
            "timestamp": datetime.utcnow().isoformat()
        }

        if error_message:
            log_data["error_message"] = error_message
            level = logging.ERROR
        else:
            level = logging.INFO

        self.db_logger.log(
            level,
            "Database Operation",
            extra=log_data
        )

    def log_job_event(
        self,
        job_id: str,
        job_type: str,
        event: str,
        duration: Optional[float] = None,
        status: str = "running",
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log background job events"""
        log_data = {
            "job_id": job_id,
            "job_type": job_type,
            "event": event,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }

        if duration is not None:
            log_data["duration_ms"] = round(duration * 1000, 2)

        if error_message:
            log_data["error_message"] = error_message

        if metadata:
            log_data.update(metadata)

        level = logging.ERROR if status == "failed" else logging.INFO
        self.job_logger.log(
            level,
            "Job Event",
            extra=log_data
        )

    def log_business_event(
        self,
        event_type: str,
        description: str,
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        amount: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log business-related events"""
        log_data = {
            "event_type": event_type,
            "description": description,
            "user_id": user_id,
            "account_id": account_id,
            "amount": amount,
            "timestamp": datetime.utcnow().isoformat()
        }

        if metadata:
            log_data.update(metadata)

        self.app_logger.info(
            "Business Event",
            extra=log_data
        )

    def log_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """Log application errors"""
        log_data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "user_id": user_id,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        if context:
            log_data.update(context)

        self.error_logger.error(
            "Application Error",
            extra=log_data,
            exc_info=True
        )

    # Log management methods

    def get_recent_logs(
        self,
        logger_name: str = "aws_cost_sentinel",
        lines: int = 100,
        level: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent log entries"""
        log_entries = []

        try:
            logger_mapping = {
                "app": "application.log",
                "access": "access.log",
                "security": "security.log",
                "database": "database.log",
                "aws": "aws_api.log",
                "jobs": "jobs.log",
                "errors": "errors.log"
            }

            filename = logger_mapping.get(logger_name, "application.log")
            log_file = self.log_dir / filename

            if not log_file.exists():
                return log_entries

            # Read last N lines
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

            for line in recent_lines:
                try:
                    log_entry = json.loads(line.strip())

                    # Filter by level if specified
                    if level and log_entry.get('levelname', '').lower() != level.lower():
                        continue

                    log_entries.append(log_entry)
                except json.JSONDecodeError:
                    # Handle non-JSON log lines
                    log_entries.append({
                        'message': line.strip(),
                        'timestamp': datetime.utcnow().isoformat(),
                        'levelname': 'INFO'
                    })

        except Exception as e:
            self.log_error(e, context={"operation": "get_recent_logs"})

        return log_entries

    def search_logs(
        self,
        query: str,
        logger_name: str = "app",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search logs with filters"""
        results = []

        try:
            logs = self.get_recent_logs(logger_name, lines=10000)  # Get more for searching

            for log_entry in logs:
                # Time filter
                if start_time or end_time:
                    log_time_str = log_entry.get('timestamp', log_entry.get('asctime', ''))
                    try:
                        log_time = datetime.fromisoformat(log_time_str.replace('Z', '+00:00'))

                        if start_time and log_time < start_time:
                            continue
                        if end_time and log_time > end_time:
                            continue
                    except (ValueError, TypeError):
                        continue

                # Text search
                log_text = json.dumps(log_entry).lower()
                if query.lower() in log_text:
                    results.append(log_entry)

                if len(results) >= limit:
                    break

        except Exception as e:
            self.log_error(e, context={"operation": "search_logs"})

        return results

    def get_log_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get logging statistics"""
        stats = {
            "total_entries": 0,
            "by_level": {"INFO": 0, "WARNING": 0, "ERROR": 0, "DEBUG": 0},
            "by_logger": {},
            "error_rate": 0.0,
            "top_errors": []
        }

        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            # Aggregate stats from all log files
            for logger_type in ["app", "access", "security", "database", "aws", "jobs", "errors"]:
                logs = self.get_recent_logs(logger_type, lines=10000)

                logger_stats = {"total": 0, "errors": 0}

                for log_entry in logs:
                    # Time filter
                    log_time_str = log_entry.get('timestamp', log_entry.get('asctime', ''))
                    try:
                        log_time = datetime.fromisoformat(log_time_str.replace('Z', '+00:00'))
                        if log_time < cutoff_time:
                            continue
                    except (ValueError, TypeError):
                        continue

                    stats["total_entries"] += 1
                    logger_stats["total"] += 1

                    level = log_entry.get('levelname', 'INFO')
                    stats["by_level"][level] = stats["by_level"].get(level, 0) + 1

                    if level == "ERROR":
                        logger_stats["errors"] += 1

                stats["by_logger"][logger_type] = logger_stats

            # Calculate error rate
            total_entries = stats["total_entries"]
            if total_entries > 0:
                stats["error_rate"] = (stats["by_level"]["ERROR"] / total_entries) * 100

        except Exception as e:
            self.log_error(e, context={"operation": "get_log_stats"})

        return stats

    def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """Clean up old log files"""
        cleaned_count = 0

        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)

            for log_file in self.log_dir.glob("*.log.*"):  # Rotated log files
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    cleaned_count += 1

            self.app_logger.info(
                "Log cleanup completed",
                extra={
                    "files_removed": cleaned_count,
                    "days_kept": days_to_keep,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            self.log_error(e, context={"operation": "cleanup_old_logs"})

        return cleaned_count

    def export_logs(
        self,
        logger_name: str = "app",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        format_type: str = "json"
    ) -> str:
        """Export logs to file"""
        try:
            logs = self.get_recent_logs(logger_name, lines=50000)

            # Filter by time if specified
            if start_time or end_time:
                filtered_logs = []
                for log_entry in logs:
                    log_time_str = log_entry.get('timestamp', log_entry.get('asctime', ''))
                    try:
                        log_time = datetime.fromisoformat(log_time_str.replace('Z', '+00:00'))

                        if start_time and log_time < start_time:
                            continue
                        if end_time and log_time > end_time:
                            continue

                        filtered_logs.append(log_entry)
                    except (ValueError, TypeError):
                        continue

                logs = filtered_logs

            # Create export file
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            export_filename = f"logs_export_{logger_name}_{timestamp}.{format_type}"
            export_path = self.log_dir / export_filename

            with open(export_path, 'w', encoding='utf-8') as f:
                if format_type == "json":
                    json.dump(logs, f, indent=2, default=str)
                else:  # CSV or plain text
                    for log_entry in logs:
                        f.write(f"{log_entry}\n")

            return str(export_path)

        except Exception as e:
            self.log_error(e, context={"operation": "export_logs"})
            return ""


# Global logging service instance
logging_service = LoggingService()