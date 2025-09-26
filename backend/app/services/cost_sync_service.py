import asyncio
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.base import get_database
from app.models.aws_account import AWSAccount, AWSAccountStatus
from app.models.cost_data import CostData
from app.services.aws_client import aws_cost_explorer
from app.core.config import settings

logger = structlog.get_logger(__name__)


class CostSyncService:
    """Service for syncing cost data from AWS automatically"""

    def __init__(self):
        self.sync_in_progress = set()  # Track accounts currently being synced

    async def sync_account_costs(
        self,
        account: AWSAccount,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        db: AsyncSession = None
    ) -> dict:
        """Sync cost data for a single account"""

        if str(account.id) in self.sync_in_progress:
            logger.warning("Sync already in progress for account", account_id=account.account_id)
            return {"status": "already_syncing", "account_id": account.account_id}

        self.sync_in_progress.add(str(account.id))

        try:
            # Set default date range (last 7 days)
            if not end_date:
                end_date = date.today()
            if not start_date:
                start_date = end_date - timedelta(days=7)

            logger.info("Starting cost sync",
                       account_id=account.account_id,
                       start_date=start_date.isoformat(),
                       end_date=end_date.isoformat())

            # Update account status to syncing
            account.status = AWSAccountStatus.SYNCING
            if db:
                await db.commit()

            # Fetch cost data from AWS
            try:
                cost_data = await aws_cost_explorer.get_cost_and_usage(
                    start_date=start_date.isoformat(),
                    end_date=(end_date + timedelta(days=1)).isoformat(),
                    granularity='DAILY',
                    metrics=['BlendedCost', 'UnblendedCost'],
                    group_by=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
                    account=account
                )

                records_processed = 0
                records_created = 0
                records_updated = 0

                # Process cost data
                for result_by_time in cost_data.get('ResultsByTime', []):
                    result_date = datetime.fromisoformat(result_by_time['TimePeriod']['Start']).date()

                    for group in result_by_time.get('Groups', []):
                        service_name = group['Keys'][0] if group['Keys'] else 'Other'
                        blended_amount = float(group['Metrics'].get('BlendedCost', {}).get('Amount', 0))
                        unblended_amount = float(group['Metrics'].get('UnblendedCost', {}).get('Amount', 0))

                        # Use blended cost as primary amount
                        amount = blended_amount if blended_amount > 0 else unblended_amount

                        if amount > 0.01:  # Only store costs > $0.01
                            records_processed += 1

                            # Check if record already exists
                            if db:
                                existing_query = await db.execute(
                                    select(CostData).where(
                                        and_(
                                            CostData.account_id == account.id,
                                            CostData.date == result_date,
                                            CostData.service == service_name
                                        )
                                    )
                                )
                                existing_record = existing_query.scalar_one_or_none()

                                if existing_record:
                                    # Update existing record if amount changed
                                    if abs(existing_record.amount - amount) > 0.01:
                                        existing_record.amount = amount
                                        existing_record.currency = 'USD'
                                        existing_record.updated_at = datetime.utcnow()
                                        records_updated += 1
                                else:
                                    # Create new record
                                    cost_record = CostData(
                                        account_id=account.id,
                                        date=result_date,
                                        service=service_name,
                                        amount=amount,
                                        currency='USD'
                                    )
                                    db.add(cost_record)
                                    records_created += 1

                # Commit all changes
                if db:
                    await db.commit()

                # Update account status back to connected
                account.status = AWSAccountStatus.CONNECTED
                account.last_sync_at = datetime.utcnow()
                account.error_message = None

                if db:
                    await db.commit()

                result = {
                    "status": "success",
                    "account_id": account.account_id,
                    "records_processed": records_processed,
                    "records_created": records_created,
                    "records_updated": records_updated,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }

                logger.info("Cost sync completed successfully", **result)
                return result

            except Exception as e:
                # Update account with error status
                account.status = AWSAccountStatus.ERROR
                account.error_message = str(e)

                if db:
                    await db.commit()

                logger.error("Cost sync failed",
                           account_id=account.account_id,
                           error=str(e))

                return {
                    "status": "error",
                    "account_id": account.account_id,
                    "error": str(e)
                }

        finally:
            self.sync_in_progress.discard(str(account.id))

    async def sync_all_connected_accounts(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        """Sync cost data for all connected accounts"""

        results = []

        # Get database session
        async with get_database() as db:
            # Get all connected accounts
            query = select(AWSAccount).where(
                and_(
                    AWSAccount.is_active == True,
                    AWSAccount.status == AWSAccountStatus.CONNECTED
                )
            )
            result = await db.execute(query)
            accounts = result.scalars().all()

            logger.info("Starting bulk cost sync", account_count=len(accounts))

            # Process accounts concurrently (but with limited concurrency)
            semaphore = asyncio.Semaphore(3)  # Max 3 concurrent syncs

            async def sync_with_semaphore(account):
                async with semaphore:
                    return await self.sync_account_costs(
                        account=account,
                        start_date=start_date,
                        end_date=end_date,
                        db=db
                    )

            # Execute all syncs concurrently
            sync_tasks = [sync_with_semaphore(account) for account in accounts]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            # Process results
            successful_syncs = 0
            failed_syncs = 0

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error("Account sync failed with exception",
                               account_id=accounts[i].account_id,
                               error=str(result))
                    failed_syncs += 1
                    results[i] = {
                        "status": "error",
                        "account_id": accounts[i].account_id,
                        "error": str(result)
                    }
                elif result.get("status") == "success":
                    successful_syncs += 1
                else:
                    failed_syncs += 1

            logger.info("Bulk cost sync completed",
                       total_accounts=len(accounts),
                       successful=successful_syncs,
                       failed=failed_syncs)

        return results

    async def get_sync_status(self, account_id: str) -> dict:
        """Get sync status for an account"""
        return {
            "account_id": account_id,
            "is_syncing": account_id in self.sync_in_progress
        }

    async def cleanup_old_cost_data(self, days_to_keep: int = 400) -> dict:
        """Clean up cost data older than specified days"""

        cutoff_date = date.today() - timedelta(days=days_to_keep)

        async with get_database() as db:
            # Count records to be deleted
            count_query = select(func.count(CostData.id)).where(
                CostData.date < cutoff_date
            )
            count_result = await db.execute(count_query)
            records_to_delete = count_result.scalar()

            if records_to_delete > 0:
                # Delete old records
                delete_query = select(CostData).where(CostData.date < cutoff_date)
                result = await db.execute(delete_query)
                old_records = result.scalars().all()

                for record in old_records:
                    await db.delete(record)

                await db.commit()

                logger.info("Cleaned up old cost data",
                           records_deleted=records_to_delete,
                           cutoff_date=cutoff_date.isoformat())

            return {
                "records_deleted": records_to_delete,
                "cutoff_date": cutoff_date.isoformat()
            }

    async def validate_cost_data_integrity(self) -> dict:
        """Validate cost data integrity and find anomalies"""

        issues = []

        async with get_database() as db:
            # Check for negative costs
            negative_costs_query = select(CostData).where(CostData.amount < 0)
            negative_result = await db.execute(negative_costs_query)
            negative_costs = negative_result.scalars().all()

            if negative_costs:
                issues.append({
                    "type": "negative_costs",
                    "count": len(negative_costs),
                    "description": "Found negative cost values"
                })

            # Check for unusually high costs (potential data quality issues)
            # Define "high" as more than 10x the median cost for the service
            high_cost_query = select(
                CostData.service,
                func.percentile_cont(0.5).within_group(CostData.amount).label('median_cost'),
                func.max(CostData.amount).label('max_cost')
            ).where(
                CostData.date >= date.today() - timedelta(days=30)
            ).group_by(CostData.service)

            high_cost_result = await db.execute(high_cost_query)
            service_stats = high_cost_result.all()

            anomalous_services = []
            for stat in service_stats:
                if stat.max_cost > stat.median_cost * 10 and stat.median_cost > 1:
                    anomalous_services.append({
                        "service": stat.service,
                        "median_cost": float(stat.median_cost),
                        "max_cost": float(stat.max_cost),
                        "ratio": float(stat.max_cost / stat.median_cost)
                    })

            if anomalous_services:
                issues.append({
                    "type": "cost_anomalies",
                    "services": anomalous_services,
                    "description": "Found services with unusually high cost spikes"
                })

            # Check for data gaps
            # TODO: Implement gap detection logic

        return {
            "validation_date": datetime.utcnow().isoformat(),
            "issues_found": len(issues),
            "issues": issues
        }


# Global instance
cost_sync_service = CostSyncService()