import asyncio
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from app.models.aws_account import AWSAccount
from app.models.waste import WasteItem, WasteCategory, WasteStatus
from app.services.aws_client import aws_resource_manager, aws_cost_explorer
from app.core.config import settings

logger = structlog.get_logger(__name__)


class WasteDetectionService:
    """Service for detecting AWS resource waste and inefficiencies"""

    def __init__(self):
        self.detection_algorithms = {
            WasteCategory.UNATTACHED_VOLUMES: self._detect_unattached_volumes,
            WasteCategory.UNUSED_ELASTIC_IPS: self._detect_unused_elastic_ips,
            WasteCategory.STOPPED_INSTANCES: self._detect_stopped_instances,
            WasteCategory.UNDERUTILIZED_INSTANCES: self._detect_underutilized_instances,
            WasteCategory.OVERSIZED_INSTANCES: self._detect_oversized_instances,
            WasteCategory.UNUSED_LOAD_BALANCERS: self._detect_unused_load_balancers,
            WasteCategory.EMPTY_S3_BUCKETS: self._detect_empty_s3_buckets,
            WasteCategory.OLD_SNAPSHOTS: self._detect_old_snapshots,
            WasteCategory.UNUSED_NAT_GATEWAYS: self._detect_unused_nat_gateways,
            WasteCategory.IDLE_RDS_INSTANCES: self._detect_idle_rds_instances,
        }

    async def scan_account_for_waste(
        self,
        account: AWSAccount,
        categories: Optional[List[WasteCategory]] = None,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """Scan an AWS account for waste across specified categories"""

        scan_start = datetime.utcnow()

        # If no categories specified, scan all
        if not categories:
            categories = list(WasteCategory)

        logger.info("Starting waste detection scan",
                   account_id=account.account_id,
                   categories=[cat.value for cat in categories])

        results = {
            "account_id": account.account_id,
            "account_name": account.name,
            "status": "success",
            "items_found": 0,
            "items_created": 0,
            "items_updated": 0,
            "categories_scanned": [cat.value for cat in categories],
            "scan_started_at": scan_start,
            "error_message": None
        }

        try:
            total_items_found = 0
            total_items_created = 0
            total_items_updated = 0

            # Run detection algorithms for each category
            for category in categories:
                try:
                    if category in self.detection_algorithms:
                        logger.info("Running detection algorithm",
                                   account_id=account.account_id,
                                   category=category.value)

                        category_results = await self.detection_algorithms[category](
                            account=account,
                            db=db
                        )

                        total_items_found += category_results.get("items_found", 0)
                        total_items_created += category_results.get("items_created", 0)
                        total_items_updated += category_results.get("items_updated", 0)

                        logger.info("Detection algorithm completed",
                                   account_id=account.account_id,
                                   category=category.value,
                                   items_found=category_results.get("items_found", 0))

                except Exception as e:
                    logger.error("Detection algorithm failed",
                               account_id=account.account_id,
                               category=category.value,
                               error=str(e))
                    # Continue with other categories

            results.update({
                "items_found": total_items_found,
                "items_created": total_items_created,
                "items_updated": total_items_updated,
                "scan_completed_at": datetime.utcnow(),
                "scan_duration_seconds": (datetime.utcnow() - scan_start).total_seconds()
            })

        except Exception as e:
            logger.error("Waste detection scan failed",
                        account_id=account.account_id,
                        error=str(e))
            results.update({
                "status": "error",
                "error_message": str(e),
                "scan_completed_at": datetime.utcnow()
            })

        return results

    async def bulk_scan_accounts(
        self,
        accounts: List[AWSAccount],
        categories: Optional[List[WasteCategory]] = None,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """Scan multiple accounts for waste"""

        logger.info("Starting bulk waste detection scan",
                   account_count=len(accounts))

        # Use semaphore to limit concurrent scans
        semaphore = asyncio.Semaphore(3)

        async def scan_with_semaphore(account):
            async with semaphore:
                return await self.scan_account_for_waste(
                    account=account,
                    categories=categories,
                    db=db
                )

        # Execute all scans concurrently
        results = await asyncio.gather(
            *[scan_with_semaphore(account) for account in accounts],
            return_exceptions=True
        )

        # Process results and handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "account_id": accounts[i].account_id,
                    "account_name": accounts[i].name,
                    "status": "error",
                    "error_message": str(result),
                    "items_found": 0,
                    "items_created": 0,
                    "items_updated": 0
                })
            else:
                processed_results.append(result)

        return processed_results

    async def _detect_unattached_volumes(
        self,
        account: AWSAccount,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Detect unattached EBS volumes"""

        try:
            volumes = await aws_resource_manager.get_unattached_volumes(account)

            items_created = 0
            items_updated = 0

            for volume in volumes:
                # Estimate monthly cost based on volume size and type
                monthly_cost = self._estimate_ebs_cost(
                    volume['Size'],
                    volume['VolumeType']
                )

                # Check if this waste item already exists
                existing_item = await self._find_existing_waste_item(
                    db, account.id, WasteCategory.UNATTACHED_VOLUMES, volume['VolumeId']
                )

                if existing_item:
                    # Update existing item
                    existing_item.estimated_monthly_savings = monthly_cost
                    existing_item.updated_at = datetime.utcnow()
                    existing_item.resource_details = volume
                    items_updated += 1
                else:
                    # Create new waste item
                    waste_item = WasteItem(
                        account_id=account.id,
                        resource_id=volume['VolumeId'],
                        resource_type='EBS Volume',
                        category=WasteCategory.UNATTACHED_VOLUMES,
                        description=f"Unattached {volume['VolumeType']} volume ({volume['Size']} GB) in {volume['AvailabilityZone']}",
                        estimated_monthly_savings=monthly_cost,
                        confidence_score=0.9,  # High confidence for unattached volumes
                        region=volume['AvailabilityZone'][:-1],  # Remove AZ suffix
                        service='Amazon Elastic Block Store',
                        status=WasteStatus.DETECTED,
                        resource_details=volume
                    )

                    db.add(waste_item)
                    items_created += 1

            if items_created > 0 or items_updated > 0:
                await db.commit()

            return {
                "items_found": len(volumes),
                "items_created": items_created,
                "items_updated": items_updated
            }

        except Exception as e:
            logger.error("Failed to detect unattached volumes",
                        account_id=account.account_id,
                        error=str(e))
            raise

    async def _detect_unused_elastic_ips(
        self,
        account: AWSAccount,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Detect unused Elastic IP addresses"""

        try:
            elastic_ips = await aws_resource_manager.get_unused_elastic_ips(account)

            items_created = 0
            items_updated = 0

            for eip in elastic_ips:
                # Standard EIP pricing: $0.005 per hour when not attached
                monthly_cost = 0.005 * 24 * 30  # ~$3.60/month

                existing_item = await self._find_existing_waste_item(
                    db, account.id, WasteCategory.UNUSED_ELASTIC_IPS, eip['PublicIp']
                )

                if existing_item:
                    existing_item.estimated_monthly_savings = monthly_cost
                    existing_item.updated_at = datetime.utcnow()
                    existing_item.resource_details = eip
                    items_updated += 1
                else:
                    waste_item = WasteItem(
                        account_id=account.id,
                        resource_id=eip['PublicIp'],
                        resource_type='Elastic IP',
                        category=WasteCategory.UNUSED_ELASTIC_IPS,
                        description=f"Unused Elastic IP address {eip['PublicIp']} in {eip['Domain']} domain",
                        estimated_monthly_savings=monthly_cost,
                        confidence_score=0.95,  # Very high confidence
                        region='us-east-1',  # EIPs are region-specific but exact region needs to be determined
                        service='Amazon Elastic Compute Cloud',
                        status=WasteStatus.DETECTED,
                        resource_details=eip
                    )

                    db.add(waste_item)
                    items_created += 1

            if items_created > 0 or items_updated > 0:
                await db.commit()

            return {
                "items_found": len(elastic_ips),
                "items_created": items_created,
                "items_updated": items_updated
            }

        except Exception as e:
            logger.error("Failed to detect unused elastic IPs",
                        account_id=account.account_id,
                        error=str(e))
            raise

    async def _detect_stopped_instances(
        self,
        account: AWSAccount,
        db: AsyncSession,
        days_stopped: int = 7
    ) -> Dict[str, Any]:
        """Detect EC2 instances that have been stopped for extended periods"""

        try:
            stopped_instances = await aws_resource_manager.get_stopped_instances(
                account=account,
                days_stopped=days_stopped
            )

            items_created = 0
            items_updated = 0

            for instance in stopped_instances:
                # Estimate cost based on instance type (this is simplified)
                monthly_cost = self._estimate_ec2_cost(instance['InstanceType'])

                existing_item = await self._find_existing_waste_item(
                    db, account.id, WasteCategory.STOPPED_INSTANCES, instance['InstanceId']
                )

                if existing_item:
                    existing_item.estimated_monthly_savings = monthly_cost
                    existing_item.updated_at = datetime.utcnow()
                    existing_item.resource_details = instance
                    items_updated += 1
                else:
                    # Determine confidence based on how long it's been stopped
                    # More confidence for longer stopped instances
                    confidence = min(0.7 + (days_stopped / 30 * 0.2), 0.9)

                    waste_item = WasteItem(
                        account_id=account.id,
                        resource_id=instance['InstanceId'],
                        resource_type='EC2 Instance',
                        category=WasteCategory.STOPPED_INSTANCES,
                        description=f"Stopped {instance['InstanceType']} instance for {days_stopped}+ days",
                        estimated_monthly_savings=monthly_cost,
                        confidence_score=confidence,
                        region=instance.get('Placement', {}).get('AvailabilityZone', 'unknown')[:-1],
                        service='Amazon Elastic Compute Cloud',
                        status=WasteStatus.DETECTED,
                        resource_details=instance
                    )

                    db.add(waste_item)
                    items_created += 1

            if items_created > 0 or items_updated > 0:
                await db.commit()

            return {
                "items_found": len(stopped_instances),
                "items_created": items_created,
                "items_updated": items_updated
            }

        except Exception as e:
            logger.error("Failed to detect stopped instances",
                        account_id=account.account_id,
                        error=str(e))
            raise

    async def _detect_underutilized_instances(
        self,
        account: AWSAccount,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Detect underutilized EC2 instances"""

        # This is a simplified implementation
        # In production, you'd integrate with CloudWatch metrics

        try:
            # For now, return empty results as this requires CloudWatch integration
            logger.info("Underutilized instances detection requires CloudWatch metrics integration",
                       account_id=account.account_id)

            return {
                "items_found": 0,
                "items_created": 0,
                "items_updated": 0
            }

        except Exception as e:
            logger.error("Failed to detect underutilized instances",
                        account_id=account.account_id,
                        error=str(e))
            raise

    async def _detect_oversized_instances(self, account: AWSAccount, db: AsyncSession):
        """Detect oversized EC2 instances"""
        # Placeholder - requires CloudWatch metrics
        return {"items_found": 0, "items_created": 0, "items_updated": 0}

    async def _detect_unused_load_balancers(self, account: AWSAccount, db: AsyncSession):
        """Detect unused load balancers"""
        # Placeholder - requires ELB API integration
        return {"items_found": 0, "items_created": 0, "items_updated": 0}

    async def _detect_empty_s3_buckets(self, account: AWSAccount, db: AsyncSession):
        """Detect empty S3 buckets"""
        # Placeholder - requires S3 API integration
        return {"items_found": 0, "items_created": 0, "items_updated": 0}

    async def _detect_old_snapshots(self, account: AWSAccount, db: AsyncSession):
        """Detect old EBS snapshots"""
        # Placeholder - requires EC2 snapshot API integration
        return {"items_found": 0, "items_created": 0, "items_updated": 0}

    async def _detect_unused_nat_gateways(self, account: AWSAccount, db: AsyncSession):
        """Detect unused NAT gateways"""
        # Placeholder - requires VPC API integration
        return {"items_found": 0, "items_created": 0, "items_updated": 0}

    async def _detect_idle_rds_instances(self, account: AWSAccount, db: AsyncSession):
        """Detect idle RDS instances"""
        # Placeholder - requires RDS and CloudWatch integration
        return {"items_found": 0, "items_created": 0, "items_updated": 0}

    async def _find_existing_waste_item(
        self,
        db: AsyncSession,
        account_id: str,
        category: WasteCategory,
        resource_id: str
    ) -> Optional[WasteItem]:
        """Find existing waste item for the same resource"""

        result = await db.execute(
            select(WasteItem).where(
                and_(
                    WasteItem.account_id == account_id,
                    WasteItem.category == category,
                    WasteItem.resource_id == resource_id,
                    WasteItem.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    def _estimate_ebs_cost(self, size_gb: int, volume_type: str) -> float:
        """Estimate monthly EBS cost based on size and type"""

        # Simplified pricing (actual pricing varies by region)
        pricing_per_gb = {
            'gp3': 0.08,
            'gp2': 0.10,
            'io1': 0.125,
            'io2': 0.125,
            'sc1': 0.025,
            'st1': 0.045,
            'standard': 0.05
        }

        price_per_gb = pricing_per_gb.get(volume_type, 0.10)
        return size_gb * price_per_gb

    def _estimate_ec2_cost(self, instance_type: str) -> float:
        """Estimate monthly EC2 cost based on instance type"""

        # Simplified hourly pricing for common instance types (us-east-1)
        hourly_pricing = {
            't3.nano': 0.0052,
            't3.micro': 0.0104,
            't3.small': 0.0208,
            't3.medium': 0.0416,
            't3.large': 0.0832,
            't3.xlarge': 0.1664,
            't3.2xlarge': 0.3328,
            'm5.large': 0.096,
            'm5.xlarge': 0.192,
            'm5.2xlarge': 0.384,
            'm5.4xlarge': 0.768,
            'm5.8xlarge': 1.536,
            'm5.12xlarge': 2.304,
            'm5.16xlarge': 3.072,
            'm5.24xlarge': 4.608,
            'c5.large': 0.085,
            'c5.xlarge': 0.17,
            'c5.2xlarge': 0.34,
            'c5.4xlarge': 0.68,
            'c5.9xlarge': 1.53,
            'c5.12xlarge': 2.04,
            'c5.18xlarge': 3.06,
            'c5.24xlarge': 4.08,
        }

        hourly_rate = hourly_pricing.get(instance_type, 0.1)  # Default rate
        return hourly_rate * 24 * 30  # Monthly cost

    def _estimate_savings_confidence(
        self,
        resource_type: str,
        utilization_data: Optional[Dict[str, Any]] = None
    ) -> float:
        """Estimate confidence score for potential savings"""

        # Base confidence by resource type
        base_confidence = {
            'unattached_volume': 0.9,
            'unused_eip': 0.95,
            'stopped_instance': 0.8,
            'underutilized_instance': 0.7,
            'empty_bucket': 0.85
        }

        confidence = base_confidence.get(resource_type, 0.7)

        # Adjust based on utilization data if available
        if utilization_data:
            avg_cpu = utilization_data.get('average_cpu', 0)
            if avg_cpu < 5:
                confidence = min(confidence + 0.1, 0.95)
            elif avg_cpu > 20:
                confidence = max(confidence - 0.2, 0.3)

        return confidence


# Global instance
waste_detection_service = WasteDetectionService()