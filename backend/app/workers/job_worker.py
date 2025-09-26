import asyncio
import signal
import sys
from typing import Dict, Any
from datetime import datetime
import structlog

from app.services.queue_service import queue_service, JobStatus
from app.services.cost_sync_service import cost_sync_service
from app.services.waste_detection_service import waste_detection_service
from app.services.recommendations_engine import recommendations_engine
from app.services.event_dispatcher import event_dispatcher
from app.db.base import get_database
from app.models.aws_account import AWSAccount
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger(__name__)


class JobWorker:
    """Background job worker for processing queued tasks"""

    def __init__(self, queue_name: str = "default", worker_id: str = None):
        self.queue_name = queue_name
        self.worker_id = worker_id or f"worker-{id(self)}"
        self.running = False
        self.current_job_id = None
        self._register_job_handlers()

    def _register_job_handlers(self):
        """Register all job handlers with the queue service"""
        queue_service.register_handler("cost_sync", self._handle_cost_sync)
        queue_service.register_handler("waste_scan", self._handle_waste_scan)
        queue_service.register_handler("generate_recommendations", self._handle_generate_recommendations)
        queue_service.register_handler("bulk_cost_sync", self._handle_bulk_cost_sync)
        queue_service.register_handler("account_health_check", self._handle_account_health_check)
        queue_service.register_handler("cleanup_old_data", self._handle_cleanup_old_data)
        queue_service.register_handler("generate_scheduled_report", self._handle_generate_scheduled_report)
        logger.info("Job handlers registered", worker_id=self.worker_id)

    async def _handle_cost_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle cost synchronization job"""
        account_id = payload.get("account_id")
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")

        if not account_id:
            raise ValueError("account_id is required for cost sync job")

        logger.info("Processing cost sync job", account_id=account_id)

        async with get_database() as db:
            # Get account details
            result = await db.execute(
                select(AWSAccount).where(AWSAccount.id == account_id)
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account not found: {account_id}")

            # Perform cost sync
            sync_result = await cost_sync_service.sync_account_costs(
                account=account,
                start_date=start_date,
                end_date=end_date,
                db=db
            )

            # Dispatch real-time event
            await event_dispatcher.notify_cost_sync_completed(
                user_id="system",  # In production, get actual user_id
                account_id=account_id,
                cost_summary={
                    "records_processed": sync_result.get("records_processed", 0),
                    "total_cost": sync_result.get("total_cost", 0),
                    "sync_completed_at": datetime.utcnow().isoformat()
                }
            )

            return {
                "account_id": account_id,
                "records_processed": sync_result.get("records_processed", 0),
                "records_created": sync_result.get("records_created", 0),
                "records_updated": sync_result.get("records_updated", 0),
                "status": sync_result.get("status", "completed")
            }

    async def _handle_waste_scan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle waste detection scan job"""
        account_id = payload.get("account_id")
        categories = payload.get("categories")

        if not account_id:
            raise ValueError("account_id is required for waste scan job")

        logger.info("Processing waste scan job", account_id=account_id)

        async with get_database() as db:
            # Get account details
            result = await db.execute(
                select(AWSAccount).where(AWSAccount.id == account_id)
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account not found: {account_id}")

            # Perform waste scan
            scan_result = await waste_detection_service.scan_account_for_waste(
                account=account,
                categories=categories,
                db=db
            )

            # Dispatch real-time event (simplified - would include actual waste items)
            await event_dispatcher.notify_waste_scan_completed(
                user_id="system",  # In production, get actual user_id
                account_id=account_id,
                waste_items=[]  # Would include actual waste items found
            )

            return {
                "account_id": account_id,
                "items_found": scan_result.get("items_found", 0),
                "items_created": scan_result.get("items_created", 0),
                "items_updated": scan_result.get("items_updated", 0),
                "status": scan_result.get("status", "completed")
            }

    async def _handle_generate_recommendations(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle recommendations generation job"""
        account_id = payload.get("account_id")
        recommendation_types = payload.get("recommendation_types")

        logger.info("Processing recommendations job", account_id=account_id)

        async with get_database() as db:
            account = None
            if account_id:
                result = await db.execute(
                    select(AWSAccount).where(AWSAccount.id == account_id)
                )
                account = result.scalar_one_or_none()

            # Generate recommendations
            recommendations = await recommendations_engine.generate_recommendations(
                account=account,
                recommendation_types=recommendation_types,
                db=db
            )

            return {
                "account_id": account_id,
                "recommendations_generated": len(recommendations),
                "status": "completed"
            }

    async def _handle_bulk_cost_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle bulk cost synchronization job"""
        account_ids = payload.get("account_ids")
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")

        logger.info("Processing bulk cost sync job", account_count=len(account_ids) if account_ids else 0)

        async with get_database() as db:
            accounts = []
            if account_ids:
                result = await db.execute(
                    select(AWSAccount).where(AWSAccount.id.in_(account_ids))
                )
                accounts = result.scalars().all()
            else:
                # Sync all connected accounts
                result = await db.execute(
                    select(AWSAccount).where(AWSAccount.is_active == True)
                )
                accounts = result.scalars().all()

            # Perform bulk sync
            results = []
            for account in accounts:
                try:
                    sync_result = await cost_sync_service.sync_account_costs(
                        account=account,
                        start_date=start_date,
                        end_date=end_date,
                        db=db
                    )
                    results.append(sync_result)
                except Exception as e:
                    logger.error("Account sync failed", account_id=str(account.id), error=str(e))
                    results.append({
                        "account_id": str(account.id),
                        "status": "error",
                        "error_message": str(e)
                    })

            successful = sum(1 for r in results if r.get("status") == "success")

            return {
                "accounts_processed": len(results),
                "successful_syncs": successful,
                "failed_syncs": len(results) - successful,
                "status": "completed"
            }

    async def _handle_account_health_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle account health check job"""
        account_id = payload.get("account_id")

        if not account_id:
            raise ValueError("account_id is required for health check job")

        logger.info("Processing account health check", account_id=account_id)

        async with get_database() as db:
            result = await db.execute(
                select(AWSAccount).where(AWSAccount.id == account_id)
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account not found: {account_id}")

            # Perform health check using AWS client
            from app.services.aws_client import aws_client_manager
            health_result = await aws_client_manager.test_connection(account)

            # Update account status based on health check
            if health_result.get("status") == "success":
                account.status = "connected"
                account.error_message = None
            else:
                account.status = "error"
                account.error_message = health_result.get("error_message")

            await db.commit()

            return {
                "account_id": account_id,
                "health_status": health_result.get("status"),
                "error_message": health_result.get("error_message"),
                "status": "completed"
            }

    async def _handle_cleanup_old_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle cleanup of old data"""
        days_to_keep = payload.get("days_to_keep", 365)
        data_types = payload.get("data_types", ["cost_data", "waste_items", "recommendations"])

        logger.info("Processing data cleanup job", days_to_keep=days_to_keep)

        cleanup_results = {}

        if "cost_data" in data_types:
            cost_cleanup = await cost_sync_service.cleanup_old_cost_data(days_to_keep)
            cleanup_results["cost_data"] = cost_cleanup

        # Add cleanup for other data types as needed

        return {
            "cleanup_results": cleanup_results,
            "status": "completed"
        }

    async def _handle_generate_scheduled_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle scheduled report generation job"""
        account_id = payload.get("account_id")
        start_date_str = payload.get("start_date")
        end_date_str = payload.get("end_date")
        format_types = payload.get("format_types", ["pdf"])
        schedule_type = payload.get("schedule_type", "monthly")
        user_id = payload.get("user_id")

        logger.info("Processing scheduled report generation",
                   account_id=account_id,
                   schedule_type=schedule_type)

        try:
            from datetime import datetime
            from app.services.report_service import report_service

            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)

            generated_reports = []

            # Generate report in each requested format
            for format_type in format_types:
                try:
                    report_result = await report_service.generate_comprehensive_report(
                        account_id=account_id,
                        start_date=start_date,
                        end_date=end_date,
                        format_type=format_type,
                        user_id=user_id
                    )
                    generated_reports.append(report_result)

                    # Notify user about report completion
                    if user_id:
                        await event_dispatcher.notify_job_progress(
                            user_id=user_id,
                            job_id=f"scheduled_report_{account_id}",
                            status="completed",
                            progress={
                                "message": f"Scheduled {format_type.upper()} report generated",
                                "format": format_type,
                                "report_id": report_result["report_id"]
                            }
                        )

                except Exception as e:
                    logger.error("Failed to generate report format",
                               format_type=format_type,
                               error=str(e))
                    if user_id:
                        await event_dispatcher.notify_error(
                            user_id=user_id,
                            error_type="report_generation_failed",
                            error_message=f"Failed to generate {format_type} report: {str(e)}"
                        )

            # Schedule next report generation
            if generated_reports:
                next_schedule = await report_service.schedule_periodic_reports(
                    account_id=account_id,
                    schedule_type=schedule_type,
                    format_types=format_types,
                    user_id=user_id
                )

            return {
                "account_id": account_id,
                "reports_generated": len(generated_reports),
                "formats": format_types,
                "schedule_type": schedule_type,
                "next_scheduled": next_schedule.get("next_run") if generated_reports else None,
                "status": "completed"
            }

        except Exception as e:
            logger.error("Scheduled report generation failed",
                        account_id=account_id,
                        error=str(e))

            if user_id:
                await event_dispatcher.notify_error(
                    user_id=user_id,
                    error_type="scheduled_report_failed",
                    error_message=f"Scheduled report generation failed: {str(e)}"
                )

            raise

    async def start(self):
        """Start the worker"""
        self.running = True
        logger.info("Worker starting", worker_id=self.worker_id, queue=self.queue_name)

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        while self.running:
            try:
                # Dequeue next job
                job_id = queue_service.dequeue_job(self.queue_name, timeout=5)

                if job_id:
                    self.current_job_id = job_id
                    logger.info("Processing job", job_id=job_id, worker_id=self.worker_id)

                    # Process the job
                    success = await queue_service.process_job(job_id)

                    if success:
                        logger.info("Job completed", job_id=job_id)
                    else:
                        logger.error("Job failed", job_id=job_id)

                    self.current_job_id = None

                else:
                    # No job available, short sleep
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error("Worker error", error=str(e), worker_id=self.worker_id)
                # Continue processing other jobs
                await asyncio.sleep(5)

        logger.info("Worker stopped", worker_id=self.worker_id)

    def stop(self):
        """Stop the worker gracefully"""
        logger.info("Worker stopping", worker_id=self.worker_id)
        self.running = False

        # If currently processing a job, let it complete
        if self.current_job_id:
            logger.info("Waiting for current job to complete", job_id=self.current_job_id)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal", signal=signum, worker_id=self.worker_id)
        self.stop()


# Job scheduling utilities

class JobScheduler:
    """Utility class for scheduling common background jobs"""

    @staticmethod
    def schedule_cost_sync(
        account_id: str,
        start_date: str = None,
        end_date: str = None,
        delay: int = 0
    ) -> str:
        """Schedule a cost sync job"""
        return queue_service.enqueue_job(
            job_type="cost_sync",
            payload={
                "account_id": account_id,
                "start_date": start_date,
                "end_date": end_date
            },
            delay=delay
        )

    @staticmethod
    def schedule_waste_scan(
        account_id: str,
        categories: list = None,
        delay: int = 0
    ) -> str:
        """Schedule a waste detection scan"""
        return queue_service.enqueue_job(
            job_type="waste_scan",
            payload={
                "account_id": account_id,
                "categories": categories
            },
            delay=delay
        )

    @staticmethod
    def schedule_bulk_cost_sync(
        account_ids: list = None,
        start_date: str = None,
        end_date: str = None,
        delay: int = 0
    ) -> str:
        """Schedule bulk cost sync job"""
        return queue_service.enqueue_job(
            job_type="bulk_cost_sync",
            payload={
                "account_ids": account_ids,
                "start_date": start_date,
                "end_date": end_date
            },
            delay=delay
        )

    @staticmethod
    def schedule_recommendations_generation(
        account_id: str = None,
        recommendation_types: list = None,
        delay: int = 0
    ) -> str:
        """Schedule recommendations generation"""
        return queue_service.enqueue_job(
            job_type="generate_recommendations",
            payload={
                "account_id": account_id,
                "recommendation_types": recommendation_types
            },
            delay=delay
        )


if __name__ == "__main__":
    """Run worker as standalone process"""
    import argparse

    parser = argparse.ArgumentParser(description="AWS Cost Sentinel Job Worker")
    parser.add_argument("--queue", default="default", help="Queue name to process")
    parser.add_argument("--worker-id", help="Worker identifier")
    args = parser.parse_args()

    worker = JobWorker(queue_name=args.queue, worker_id=args.worker_id)

    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        sys.exit(0)