import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional, Dict, Any, List
import structlog
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools

from app.core.config import settings
from app.models.aws_account import AWSAccount

logger = structlog.get_logger(__name__)


class AWSClientManager:
    """Manages AWS client instances with support for multiple accounts and role assumption"""

    def __init__(self):
        self._clients: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, boto3.Session] = {}
        self._executor = ThreadPoolExecutor(max_workers=10)

    def _get_base_session(self) -> boto3.Session:
        """Get the base AWS session using configured credentials"""
        return boto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )

    def _assume_role(self, role_arn: str, external_id: Optional[str] = None) -> boto3.Session:
        """Assume an AWS role and return a new session"""
        try:
            base_session = self._get_base_session()
            sts_client = base_session.client('sts')

            assume_role_kwargs = {
                'RoleArn': role_arn,
                'RoleSessionName': f'cost-sentinel-{int(datetime.now().timestamp())}',
                'DurationSeconds': 3600  # 1 hour
            }

            if external_id:
                assume_role_kwargs['ExternalId'] = external_id

            response = sts_client.assume_role(**assume_role_kwargs)

            credentials = response['Credentials']

            return boto3.Session(
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name=settings.AWS_REGION
            )
        except ClientError as e:
            logger.error("Failed to assume role", role_arn=role_arn, error=str(e))
            raise

    def get_session(self, account: Optional[AWSAccount] = None) -> boto3.Session:
        """Get AWS session for the given account or default credentials"""
        if not account or not account.role_arn:
            return self._get_base_session()

        cache_key = f"{account.account_id}:{account.role_arn}"

        # Check if we have a cached session
        if cache_key in self._sessions:
            return self._sessions[cache_key]

        # Assume role and cache the session
        session = self._assume_role(account.role_arn, account.external_id)
        self._sessions[cache_key] = session

        logger.info("Created new AWS session", account_id=account.account_id, role_arn=account.role_arn)
        return session

    def get_client(self, service: str, account: Optional[AWSAccount] = None) -> Any:
        """Get AWS client for the given service and account"""
        session = self.get_session(account)
        return session.client(service)

    async def test_connection(self, account: Optional[AWSAccount] = None) -> Dict[str, Any]:
        """Test AWS connection and return account information"""
        def _test_sync():
            try:
                session = self.get_session(account)
                sts_client = session.client('sts')

                # Get caller identity
                identity = sts_client.get_caller_identity()

                # Test Cost Explorer access
                ce_client = session.client('ce')
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=1)

                ce_client.get_cost_and_usage(
                    TimePeriod={
                        'Start': start_date.isoformat(),
                        'End': end_date.isoformat()
                    },
                    Granularity='DAILY',
                    Metrics=['BlendedCost']
                )

                return {
                    'status': 'success',
                    'account_id': identity.get('Account'),
                    'arn': identity.get('Arn'),
                    'user_id': identity.get('UserId'),
                    'cost_explorer_access': True
                }

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))

                logger.error("AWS connection test failed",
                           account_id=account.account_id if account else None,
                           error_code=error_code,
                           error_message=error_message)

                return {
                    'status': 'error',
                    'error_code': error_code,
                    'error_message': error_message,
                    'cost_explorer_access': False
                }
            except Exception as e:
                logger.error("Unexpected error during connection test", error=str(e))
                return {
                    'status': 'error',
                    'error_code': 'UnexpectedError',
                    'error_message': str(e),
                    'cost_explorer_access': False
                }

        # Run the synchronous test in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _test_sync)

    def clear_cache(self, account_id: Optional[str] = None):
        """Clear cached sessions for specific account or all accounts"""
        if account_id:
            # Clear sessions for specific account
            keys_to_remove = [k for k in self._sessions.keys() if k.startswith(f"{account_id}:")]
            for key in keys_to_remove:
                del self._sessions[key]
        else:
            # Clear all cached sessions
            self._sessions.clear()

        logger.info("Cleared AWS session cache", account_id=account_id or "all")


class AWSCostExplorer:
    """AWS Cost Explorer service wrapper"""

    def __init__(self, client_manager: AWSClientManager):
        self.client_manager = client_manager
        self.executor = ThreadPoolExecutor(max_workers=5)

    async def get_cost_and_usage(
        self,
        start_date: str,
        end_date: str,
        granularity: str = 'DAILY',
        metrics: List[str] = None,
        group_by: List[Dict[str, str]] = None,
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get cost and usage data from AWS Cost Explorer"""

        def _get_cost_sync():
            try:
                client = self.client_manager.get_client('ce', account)

                params = {
                    'TimePeriod': {
                        'Start': start_date,
                        'End': end_date
                    },
                    'Granularity': granularity,
                    'Metrics': metrics or ['BlendedCost']
                }

                if group_by:
                    params['GroupBy'] = group_by

                return client.get_cost_and_usage(**params)

            except ClientError as e:
                logger.error("Failed to get cost and usage",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_cost_sync)

    async def get_rightsizing_recommendation(
        self,
        service: str = 'AmazonEC2',
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get right-sizing recommendations"""

        def _get_recommendations_sync():
            try:
                client = self.client_manager.get_client('ce', account)

                return client.get_rightsizing_recommendation(
                    Filter={
                        'Dimensions': {
                            'Key': 'SERVICE',
                            'Values': [service]
                        }
                    },
                    Configuration={
                        'BenefitsConsidered': True,
                        'RecommendationTarget': 'SAME_INSTANCE_FAMILY'
                    }
                )

            except ClientError as e:
                logger.error("Failed to get rightsizing recommendations",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_recommendations_sync)

    async def get_reservation_recommendations(
        self,
        service: str = 'AmazonEC2',
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get Reserved Instance recommendations"""

        def _get_ri_recommendations_sync():
            try:
                client = self.client_manager.get_client('ce', account)

                return client.get_reservation_purchase_recommendation(
                    Service=service,
                    AccountScope='LINKED',
                    LookbackPeriodInDays='SIXTY_DAYS',
                    TermInYears='ONE_YEAR',
                    PaymentOption='PARTIAL_UPFRONT'
                )

            except ClientError as e:
                logger.error("Failed to get RI recommendations",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_ri_recommendations_sync)

    async def get_cost_categories(
        self,
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get available cost categories"""

        def _get_cost_categories_sync():
            try:
                client = self.client_manager.get_client('ce', account)
                return client.list_cost_category_definitions()
            except ClientError as e:
                logger.error("Failed to get cost categories",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_cost_categories_sync)

    async def get_dimension_values(
        self,
        dimension: str,
        start_date: str,
        end_date: str,
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get dimension values (e.g., services, instance types)"""

        def _get_dimension_values_sync():
            try:
                client = self.client_manager.get_client('ce', account)

                return client.get_dimension_values(
                    TimePeriod={
                        'Start': start_date,
                        'End': end_date
                    },
                    Dimension=dimension,
                    Context='COST_AND_USAGE'
                )
            except ClientError as e:
                logger.error("Failed to get dimension values",
                           dimension=dimension,
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_dimension_values_sync)

    async def get_usage_forecast(
        self,
        start_date: str,
        end_date: str,
        metric: str = 'BLENDED_COST',
        granularity: str = 'MONTHLY',
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get usage forecast"""

        def _get_usage_forecast_sync():
            try:
                client = self.client_manager.get_client('ce', account)

                return client.get_usage_forecast(
                    TimePeriod={
                        'Start': start_date,
                        'End': end_date
                    },
                    Metric=metric,
                    Granularity=granularity
                )
            except ClientError as e:
                logger.error("Failed to get usage forecast",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_usage_forecast_sync)

    async def get_cost_and_usage_with_resources(
        self,
        start_date: str,
        end_date: str,
        granularity: str = 'DAILY',
        group_by: List[Dict[str, str]] = None,
        filter_expression: Optional[Dict[str, Any]] = None,
        account: Optional[AWSAccount] = None
    ) -> Dict[str, Any]:
        """Get cost and usage data with resource-level details"""

        def _get_cost_with_resources_sync():
            try:
                client = self.client_manager.get_client('ce', account)

                params = {
                    'TimePeriod': {
                        'Start': start_date,
                        'End': end_date
                    },
                    'Granularity': granularity,
                    'Metrics': ['BlendedCost', 'UnblendedCost', 'UsageQuantity']
                }

                if group_by:
                    params['GroupBy'] = group_by

                if filter_expression:
                    params['Filter'] = filter_expression

                return client.get_cost_and_usage(**params)

            except ClientError as e:
                logger.error("Failed to get cost and usage with resources",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_cost_with_resources_sync)


class AWSResourceManager:
    """AWS resource management for waste detection"""

    def __init__(self, client_manager: AWSClientManager):
        self.client_manager = client_manager
        self.executor = ThreadPoolExecutor(max_workers=10)

    async def get_unattached_volumes(self, account: Optional[AWSAccount] = None) -> List[Dict[str, Any]]:
        """Find unattached EBS volumes"""

        def _get_volumes_sync():
            try:
                client = self.client_manager.get_client('ec2', account)

                # Get all available (unattached) volumes
                response = client.describe_volumes(
                    Filters=[
                        {'Name': 'status', 'Values': ['available']}
                    ]
                )

                volumes = []
                for volume in response.get('Volumes', []):
                    volumes.append({
                        'VolumeId': volume['VolumeId'],
                        'Size': volume['Size'],
                        'VolumeType': volume['VolumeType'],
                        'CreateTime': volume['CreateTime'],
                        'AvailabilityZone': volume['AvailabilityZone'],
                        'Encrypted': volume.get('Encrypted', False),
                        'Tags': {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
                    })

                return volumes

            except ClientError as e:
                logger.error("Failed to get unattached volumes",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_volumes_sync)

    async def get_unused_elastic_ips(self, account: Optional[AWSAccount] = None) -> List[Dict[str, Any]]:
        """Find unused Elastic IPs"""

        def _get_eips_sync():
            try:
                client = self.client_manager.get_client('ec2', account)

                response = client.describe_addresses()

                unused_ips = []
                for address in response.get('Addresses', []):
                    # Check if EIP is not associated with any instance
                    if 'InstanceId' not in address and 'NetworkInterfaceId' not in address:
                        unused_ips.append({
                            'PublicIp': address['PublicIp'],
                            'AllocationId': address.get('AllocationId'),
                            'Domain': address['Domain'],
                            'Tags': {tag['Key']: tag['Value'] for tag in address.get('Tags', [])}
                        })

                return unused_ips

            except ClientError as e:
                logger.error("Failed to get unused elastic IPs",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_eips_sync)

    async def get_stopped_instances(
        self,
        days_stopped: int = 7,
        account: Optional[AWSAccount] = None
    ) -> List[Dict[str, Any]]:
        """Find EC2 instances that have been stopped for a specified number of days"""

        def _get_stopped_instances_sync():
            try:
                client = self.client_manager.get_client('ec2', account)

                response = client.describe_instances(
                    Filters=[
                        {'Name': 'instance-state-name', 'Values': ['stopped']}
                    ]
                )

                cutoff_time = datetime.now() - timedelta(days=days_stopped)
                stopped_instances = []

                for reservation in response.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        # Check if instance has been stopped for the specified period
                        state_transition_reason = instance.get('StateTransitionReason', '')

                        # Try to extract stop time from the state transition reason
                        # This is a simplified approach - in production you might want to track this differently
                        if instance.get('LaunchTime') and instance['LaunchTime'] < cutoff_time:
                            stopped_instances.append({
                                'InstanceId': instance['InstanceId'],
                                'InstanceType': instance['InstanceType'],
                                'LaunchTime': instance['LaunchTime'],
                                'State': instance['State']['Name'],
                                'StateTransitionReason': state_transition_reason,
                                'Platform': instance.get('Platform', 'Linux/UNIX'),
                                'Tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                            })

                return stopped_instances

            except ClientError as e:
                logger.error("Failed to get stopped instances",
                           account_id=account.account_id if account else None,
                           error=str(e))
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_stopped_instances_sync)


# Global instances
aws_client_manager = AWSClientManager()
aws_cost_explorer = AWSCostExplorer(aws_client_manager)
aws_resource_manager = AWSResourceManager(aws_client_manager)