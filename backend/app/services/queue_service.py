import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import redis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class QueueService:
    """Redis-based queue service for background job processing"""

    def __init__(self):
        self.redis_client = None
        self.job_handlers = {}
        self._connect()

    def _connect(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self.redis_client.ping()
            logger.info("Queue service Redis connection established")
        except redis.RedisError as e:
            logger.error("Failed to connect to Redis for queue service", error=str(e))
            self.redis_client = None

    def register_handler(self, job_type: str, handler: Callable):
        """Register a job handler function"""
        self.job_handlers[job_type] = handler
        logger.info("Registered job handler", job_type=job_type)

    def enqueue_job(
        self,
        job_type: str,
        payload: Dict[str, Any],
        priority: JobPriority = JobPriority.NORMAL,
        delay: Optional[int] = None,
        max_retries: int = 3,
        queue_name: str = "default"
    ) -> Optional[str]:
        """Enqueue a background job"""
        if not self.redis_client:
            logger.error("Redis not available, cannot enqueue job")
            return None

        job_id = str(uuid.uuid4())
        now = datetime.utcnow()

        job_data = {
            "id": job_id,
            "type": job_type,
            "payload": payload,
            "status": JobStatus.PENDING.value,
            "priority": priority.value,
            "created_at": now.isoformat(),
            "scheduled_at": (now + timedelta(seconds=delay)).isoformat() if delay else now.isoformat(),
            "max_retries": max_retries,
            "retry_count": 0,
            "queue": queue_name,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "result": None
        }

        try:
            # Store job details
            job_key = f"job:{job_id}"
            self.redis_client.hset(job_key, mapping={
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in job_data.items()
            })

            # Set job expiration (7 days)
            self.redis_client.expire(job_key, 604800)

            if delay:
                # Schedule for later execution
                score = (now + timedelta(seconds=delay)).timestamp()
                self.redis_client.zadd(f"scheduled:{queue_name}", {job_id: score})
            else:
                # Add to priority queue immediately
                queue_key = f"queue:{queue_name}:priority:{priority.value}"
                self.redis_client.lpush(queue_key, job_id)

            logger.info("Job enqueued", job_id=job_id, job_type=job_type, queue=queue_name)
            return job_id

        except redis.RedisError as e:
            logger.error("Failed to enqueue job", error=str(e))
            return None

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID"""
        if not self.redis_client:
            return None

        try:
            job_key = f"job:{job_id}"
            job_data = self.redis_client.hgetall(job_key)

            if not job_data:
                return None

            # Parse JSON fields
            for key in ["payload", "result"]:
                if job_data.get(key):
                    try:
                        job_data[key] = json.loads(job_data[key])
                    except json.JSONDecodeError:
                        pass

            # Convert numeric fields
            for key in ["priority", "max_retries", "retry_count"]:
                if job_data.get(key):
                    job_data[key] = int(job_data[key])

            return job_data

        except redis.RedisError as e:
            logger.error("Failed to get job", job_id=job_id, error=str(e))
            return None

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update job status and metadata"""
        if not self.redis_client:
            return False

        try:
            job_key = f"job:{job_id}"
            updates = {
                "status": status.value,
                "updated_at": datetime.utcnow().isoformat()
            }

            if status == JobStatus.PROCESSING:
                updates["started_at"] = datetime.utcnow().isoformat()
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                updates["completed_at"] = datetime.utcnow().isoformat()

            if error_message:
                updates["error_message"] = error_message

            if result:
                updates["result"] = json.dumps(result)

            self.redis_client.hset(job_key, mapping=updates)
            return True

        except redis.RedisError as e:
            logger.error("Failed to update job status", job_id=job_id, error=str(e))
            return False

    def dequeue_job(self, queue_name: str = "default", timeout: int = 5) -> Optional[str]:
        """Dequeue next job from priority queue"""
        if not self.redis_client:
            return None

        try:
            # Check scheduled jobs first
            self._move_scheduled_jobs(queue_name)

            # Try to get job from highest priority queue first
            for priority in sorted(JobPriority, key=lambda x: x.value, reverse=True):
                queue_key = f"queue:{queue_name}:priority:{priority.value}"
                result = self.redis_client.brpop(queue_key, timeout=1)
                if result:
                    return result[1]

            return None

        except redis.RedisError as e:
            logger.error("Failed to dequeue job", error=str(e))
            return None

    def _move_scheduled_jobs(self, queue_name: str):
        """Move scheduled jobs that are ready to execute to the main queue"""
        if not self.redis_client:
            return

        try:
            scheduled_key = f"scheduled:{queue_name}"
            now = datetime.utcnow().timestamp()

            # Get jobs ready for execution
            ready_jobs = self.redis_client.zrangebyscore(
                scheduled_key, 0, now, withscores=True
            )

            for job_id, score in ready_jobs:
                # Get job details to determine priority
                job_data = self.get_job(job_id)
                if job_data:
                    priority = job_data.get("priority", JobPriority.NORMAL.value)
                    queue_key = f"queue:{queue_name}:priority:{priority}"

                    # Move to priority queue
                    self.redis_client.lpush(queue_key, job_id)
                    self.redis_client.zrem(scheduled_key, job_id)

        except redis.RedisError as e:
            logger.error("Failed to move scheduled jobs", error=str(e))

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        if not self.redis_client:
            return False

        job_data = self.get_job(job_id)
        if not job_data:
            return False

        if job_data["status"] not in [JobStatus.PENDING.value, JobStatus.RETRY.value]:
            return False

        try:
            # Update status
            self.update_job_status(job_id, JobStatus.CANCELLED)

            # Remove from queues
            queue_name = job_data["queue"]
            priority = job_data["priority"]

            # Remove from regular queue
            queue_key = f"queue:{queue_name}:priority:{priority}"
            self.redis_client.lrem(queue_key, 0, job_id)

            # Remove from scheduled queue
            scheduled_key = f"scheduled:{queue_name}"
            self.redis_client.zrem(scheduled_key, job_id)

            return True

        except redis.RedisError as e:
            logger.error("Failed to cancel job", job_id=job_id, error=str(e))
            return False

    def retry_job(self, job_id: str) -> bool:
        """Retry a failed job"""
        if not self.redis_client:
            return False

        job_data = self.get_job(job_id)
        if not job_data:
            return False

        if job_data["retry_count"] >= job_data["max_retries"]:
            return False

        try:
            # Increment retry count
            job_key = f"job:{job_id}"
            self.redis_client.hincrby(job_key, "retry_count", 1)

            # Update status
            self.update_job_status(job_id, JobStatus.RETRY)

            # Re-queue with exponential backoff delay
            retry_count = job_data["retry_count"] + 1
            delay = min(2 ** retry_count * 60, 3600)  # Max 1 hour delay

            queue_name = job_data["queue"]
            scheduled_key = f"scheduled:{queue_name}"
            score = (datetime.utcnow() + timedelta(seconds=delay)).timestamp()
            self.redis_client.zadd(scheduled_key, {job_id: score})

            logger.info("Job scheduled for retry",
                       job_id=job_id,
                       retry_count=retry_count,
                       delay_seconds=delay)
            return True

        except redis.RedisError as e:
            logger.error("Failed to retry job", job_id=job_id, error=str(e))
            return False

    def get_queue_stats(self, queue_name: str = "default") -> Dict[str, int]:
        """Get queue statistics"""
        if not self.redis_client:
            return {}

        try:
            stats = {
                "pending": 0,
                "scheduled": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0
            }

            # Count jobs in priority queues
            for priority in JobPriority:
                queue_key = f"queue:{queue_name}:priority:{priority.value}"
                stats["pending"] += self.redis_client.llen(queue_key)

            # Count scheduled jobs
            scheduled_key = f"scheduled:{queue_name}"
            stats["scheduled"] = self.redis_client.zcard(scheduled_key)

            # Count jobs by status (this is approximate)
            # In a production system, you might want to maintain separate counters

            return stats

        except redis.RedisError as e:
            logger.error("Failed to get queue stats", error=str(e))
            return {}

    def clear_completed_jobs(self, older_than_days: int = 7) -> int:
        """Clear completed jobs older than specified days"""
        if not self.redis_client:
            return 0

        try:
            cutoff_time = datetime.utcnow() - timedelta(days=older_than_days)
            pattern = "job:*"
            deleted_count = 0

            for key in self.redis_client.scan_iter(match=pattern):
                job_data = self.redis_client.hgetall(key)
                if job_data.get("status") in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
                    completed_at = job_data.get("completed_at")
                    if completed_at:
                        completed_time = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                        if completed_time < cutoff_time:
                            self.redis_client.delete(key)
                            deleted_count += 1

            logger.info("Cleared completed jobs", count=deleted_count)
            return deleted_count

        except redis.RedisError as e:
            logger.error("Failed to clear completed jobs", error=str(e))
            return 0

    # Job execution context

    async def process_job(self, job_id: str) -> bool:
        """Process a single job"""
        job_data = self.get_job(job_id)
        if not job_data:
            logger.error("Job not found", job_id=job_id)
            return False

        job_type = job_data["type"]
        handler = self.job_handlers.get(job_type)

        if not handler:
            error_msg = f"No handler registered for job type: {job_type}"
            logger.error(error_msg, job_id=job_id)
            self.update_job_status(job_id, JobStatus.FAILED, error_message=error_msg)
            return False

        try:
            # Update status to processing
            self.update_job_status(job_id, JobStatus.PROCESSING)

            # Execute job
            result = await handler(job_data["payload"])

            # Mark as completed
            self.update_job_status(job_id, JobStatus.COMPLETED, result=result)

            logger.info("Job completed successfully", job_id=job_id, job_type=job_type)
            return True

        except Exception as e:
            error_msg = str(e)
            logger.error("Job execution failed", job_id=job_id, error=error_msg)
            self.update_job_status(job_id, JobStatus.FAILED, error_message=error_msg)

            # Attempt retry if retries available
            if job_data["retry_count"] < job_data["max_retries"]:
                self.retry_job(job_id)

            return False


# Global queue service instance
queue_service = QueueService()