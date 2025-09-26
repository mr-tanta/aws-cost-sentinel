import json
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
import structlog
import numpy as np
from dataclasses import dataclass

from app.models.aws_account import AWSAccount
from app.models.cost_data import CostData
from app.models.waste import WasteItem, WasteCategory, WasteStatus
from app.models.recommendation import Recommendation, RecommendationType, RecommendationStatus
from app.services.aws_client import aws_cost_explorer

logger = structlog.get_logger(__name__)


@dataclass
class CostPattern:
    """Cost pattern analysis result"""
    service: str
    account_id: str
    trend: str  # 'increasing', 'decreasing', 'stable', 'volatile'
    avg_daily_cost: float
    cost_variance: float
    growth_rate: float
    seasonality_detected: bool


@dataclass
class RecommendationScore:
    """ML-based recommendation scoring"""
    base_score: float
    impact_factor: float
    confidence_factor: float
    effort_factor: float
    risk_factor: float
    final_score: float


class RecommendationsEngine:
    """Intelligent recommendations engine with ML-based scoring"""

    def __init__(self):
        self.recommendation_generators = {
            RecommendationType.COST_OPTIMIZATION: self._generate_cost_optimization_recommendations,
            RecommendationType.RIGHTSIZING: self._generate_rightsizing_recommendations,
            RecommendationType.RESERVED_INSTANCES: self._generate_reserved_instance_recommendations,
            RecommendationType.STORAGE_OPTIMIZATION: self._generate_storage_optimization_recommendations,
            RecommendationType.WASTE_ELIMINATION: self._generate_waste_elimination_recommendations,
            RecommendationType.SCHEDULING: self._generate_scheduling_recommendations,
            RecommendationType.SECURITY_OPTIMIZATION: self._generate_security_optimization_recommendations,
        }

    async def generate_recommendations(
        self,
        account: Optional[AWSAccount] = None,
        recommendation_types: Optional[List[RecommendationType]] = None,
        min_score: float = 0.5,
        limit: int = 50,
        db: AsyncSession = None
    ) -> List[Dict[str, Any]]:
        """Generate intelligent recommendations based on cost patterns and waste analysis"""

        logger.info("Generating recommendations",
                   account_id=account.account_id if account else "all",
                   types=recommendation_types,
                   min_score=min_score)

        if not recommendation_types:
            recommendation_types = list(RecommendationType)

        all_recommendations = []

        # Generate recommendations for each type
        for rec_type in recommendation_types:
            if rec_type in self.recommendation_generators:
                try:
                    recommendations = await self.recommendation_generators[rec_type](
                        account=account,
                        db=db
                    )
                    all_recommendations.extend(recommendations)
                except Exception as e:
                    logger.error("Failed to generate recommendations",
                               type=rec_type.value,
                               error=str(e))

        # Score and rank recommendations
        scored_recommendations = []
        for rec in all_recommendations:
            score = self._calculate_ml_score(rec)
            if score.final_score >= min_score:
                rec['ml_score'] = score.final_score
                rec['score_breakdown'] = {
                    'base_score': score.base_score,
                    'impact_factor': score.impact_factor,
                    'confidence_factor': score.confidence_factor,
                    'effort_factor': score.effort_factor,
                    'risk_factor': score.risk_factor
                }
                scored_recommendations.append(rec)

        # Sort by ML score (descending)
        scored_recommendations.sort(key=lambda x: x['ml_score'], reverse=True)

        # Store top recommendations in database
        if db and scored_recommendations:
            await self._store_recommendations(scored_recommendations[:limit], db)

        return scored_recommendations[:limit]

    async def _generate_cost_optimization_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate general cost optimization recommendations"""

        recommendations = []

        # Analyze cost patterns
        cost_patterns = await self._analyze_cost_patterns(account, db)

        for pattern in cost_patterns:
            if pattern.trend == 'increasing' and pattern.growth_rate > 0.1:  # 10% growth
                recommendations.append({
                    'type': RecommendationType.COST_OPTIMIZATION,
                    'title': f'High Cost Growth Alert - {pattern.service}',
                    'description': f'{pattern.service} costs are increasing rapidly ({pattern.growth_rate:.1%} growth rate)',
                    'estimated_savings': pattern.avg_daily_cost * 30 * 0.2,  # Assume 20% potential savings
                    'effort_level': 'medium',
                    'implementation_time_days': 14,
                    'risk_level': 'low',
                    'category': 'cost_monitoring',
                    'service': pattern.service,
                    'account_id': pattern.account_id,
                    'confidence': 0.8,
                    'impact': 'high' if pattern.avg_daily_cost > 100 else 'medium',
                    'actions': [
                        'Review recent resource provisioning',
                        'Analyze usage patterns',
                        'Consider cost allocation tags',
                        'Set up cost alerts'
                    ]
                })

            if pattern.cost_variance > pattern.avg_daily_cost * 0.5:  # High volatility
                recommendations.append({
                    'type': RecommendationType.COST_OPTIMIZATION,
                    'title': f'Cost Volatility Alert - {pattern.service}',
                    'description': f'{pattern.service} shows high cost volatility, indicating potential inefficient usage',
                    'estimated_savings': pattern.avg_daily_cost * 30 * 0.15,
                    'effort_level': 'medium',
                    'implementation_time_days': 7,
                    'risk_level': 'low',
                    'category': 'usage_optimization',
                    'service': pattern.service,
                    'account_id': pattern.account_id,
                    'confidence': 0.7,
                    'impact': 'medium',
                    'actions': [
                        'Analyze usage patterns',
                        'Consider auto-scaling policies',
                        'Review peak usage requirements',
                        'Implement cost monitoring'
                    ]
                })

        return recommendations

    async def _generate_rightsizing_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate rightsizing recommendations based on usage patterns"""

        recommendations = []

        # Get EC2 cost data
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        query = select(CostData).where(
            and_(
                CostData.service == 'Amazon Elastic Compute Cloud - Compute',
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        )

        if account:
            query = query.where(CostData.account_id == account.id)

        result = await db.execute(query)
        ec2_costs = result.scalars().all()

        # Group by account
        account_costs = {}
        for cost in ec2_costs:
            if cost.account_id not in account_costs:
                account_costs[cost.account_id] = []
            account_costs[cost.account_id].append(cost.amount)

        for account_id, costs in account_costs.items():
            total_monthly_cost = sum(costs)
            if total_monthly_cost > 500:  # Only for accounts with significant EC2 costs

                # Simplified rightsizing logic
                potential_savings = total_monthly_cost * 0.25  # Assume 25% potential savings

                recommendations.append({
                    'type': RecommendationType.RIGHTSIZING,
                    'title': 'EC2 Instance Rightsizing Opportunity',
                    'description': f'Analysis suggests potential rightsizing savings for EC2 instances (Monthly cost: ${total_monthly_cost:.2f})',
                    'estimated_savings': potential_savings,
                    'effort_level': 'high',
                    'implementation_time_days': 21,
                    'risk_level': 'medium',
                    'category': 'compute_optimization',
                    'service': 'Amazon EC2',
                    'account_id': str(account_id),
                    'confidence': 0.6,  # Lower confidence without actual utilization data
                    'impact': 'high' if potential_savings > 200 else 'medium',
                    'actions': [
                        'Analyze CloudWatch metrics for CPU and memory utilization',
                        'Use AWS Compute Optimizer recommendations',
                        'Test performance with smaller instance types',
                        'Implement gradual rightsizing with monitoring'
                    ]
                })

        return recommendations

    async def _generate_reserved_instance_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate Reserved Instance recommendations"""

        recommendations = []

        # Analyze consistent compute workloads
        end_date = date.today()
        start_date = end_date - timedelta(days=90)  # 3 months of data

        query = select(
            CostData.account_id,
            CostData.service,
            func.avg(CostData.amount).label('avg_daily_cost'),
            func.stddev(CostData.amount).label('cost_stddev'),
            func.count(CostData.id).label('data_points')
        ).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date,
                CostData.service.in_([
                    'Amazon Elastic Compute Cloud - Compute',
                    'Amazon Relational Database Service'
                ])
            )
        ).group_by(CostData.account_id, CostData.service)

        if account:
            query = query.where(CostData.account_id == account.id)

        result = await db.execute(query)
        service_stats = result.all()

        for stat in service_stats:
            avg_monthly_cost = float(stat.avg_daily_cost) * 30
            cost_stability = 1.0 - (float(stat.cost_stddev or 0) / float(stat.avg_daily_cost))

            # Recommend RI for stable, high-cost services
            if avg_monthly_cost > 100 and cost_stability > 0.7 and stat.data_points > 60:
                # Conservative RI savings estimate (30-40%)
                estimated_savings = avg_monthly_cost * 0.35

                service_name = stat.service
                if 'Compute Cloud' in service_name:
                    service_display = 'EC2'
                    ri_type = 'EC2 Reserved Instances'
                elif 'Database' in service_name:
                    service_display = 'RDS'
                    ri_type = 'RDS Reserved Instances'
                else:
                    service_display = service_name
                    ri_type = 'Reserved Instances'

                recommendations.append({
                    'type': RecommendationType.RESERVED_INSTANCES,
                    'title': f'{ri_type} Opportunity',
                    'description': f'Stable {service_display} usage pattern detected. Monthly cost: ${avg_monthly_cost:.2f}',
                    'estimated_savings': estimated_savings,
                    'effort_level': 'low',
                    'implementation_time_days': 1,
                    'risk_level': 'low',
                    'category': 'reserved_capacity',
                    'service': service_name,
                    'account_id': str(stat.account_id),
                    'confidence': min(0.9, cost_stability),
                    'impact': 'high' if estimated_savings > 100 else 'medium',
                    'actions': [
                        f'Purchase 1-year {ri_type}',
                        'Consider partial upfront payment',
                        'Monitor usage patterns post-purchase',
                        'Plan for renewal 30 days before expiration'
                    ],
                    'metadata': {
                        'monthly_cost': avg_monthly_cost,
                        'cost_stability': cost_stability,
                        'data_points': stat.data_points
                    }
                })

        return recommendations

    async def _generate_storage_optimization_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate storage optimization recommendations"""

        recommendations = []

        # Analyze S3 costs
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        query = select(
            CostData.account_id,
            func.sum(CostData.amount).label('total_cost')
        ).where(
            and_(
                CostData.service == 'Amazon Simple Storage Service',
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        ).group_by(CostData.account_id)

        if account:
            query = query.where(CostData.account_id == account.id)

        result = await db.execute(query)
        s3_costs = result.all()

        for cost_data in s3_costs:
            monthly_cost = float(cost_data.total_cost)
            if monthly_cost > 50:  # Only for significant S3 costs

                # Estimate potential savings from storage class optimization
                estimated_savings = monthly_cost * 0.3  # 30% potential savings

                recommendations.append({
                    'type': RecommendationType.STORAGE_OPTIMIZATION,
                    'title': 'S3 Storage Class Optimization',
                    'description': f'S3 storage costs can be reduced through intelligent tiering and lifecycle policies (Monthly cost: ${monthly_cost:.2f})',
                    'estimated_savings': estimated_savings,
                    'effort_level': 'medium',
                    'implementation_time_days': 7,
                    'risk_level': 'low',
                    'category': 'storage_optimization',
                    'service': 'Amazon S3',
                    'account_id': str(cost_data.account_id),
                    'confidence': 0.8,
                    'impact': 'high' if estimated_savings > 50 else 'medium',
                    'actions': [
                        'Analyze object access patterns',
                        'Implement S3 Intelligent Tiering',
                        'Create lifecycle policies for old data',
                        'Consider moving to Glacier for archival data'
                    ]
                })

        return recommendations

    async def _generate_waste_elimination_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate recommendations based on detected waste"""

        recommendations = []

        # Get high-value waste items
        query = select(WasteItem).where(
            and_(
                WasteItem.is_active == True,
                WasteItem.status == WasteStatus.DETECTED,
                WasteItem.estimated_monthly_savings > 10
            )
        ).order_by(desc(WasteItem.estimated_monthly_savings))

        if account:
            query = query.where(WasteItem.account_id == account.id)

        result = await db.execute(query)
        waste_items = result.scalars().all()

        # Group waste by category for better recommendations
        waste_by_category = {}
        for item in waste_items:
            if item.category not in waste_by_category:
                waste_by_category[item.category] = []
            waste_by_category[item.category].append(item)

        for category, items in waste_by_category.items():
            total_savings = sum(item.estimated_monthly_savings for item in items)
            avg_confidence = sum(item.confidence_score for item in items) / len(items)

            if total_savings > 20:  # Only for significant savings
                category_name = category.value.replace('_', ' ').title()

                recommendations.append({
                    'type': RecommendationType.WASTE_ELIMINATION,
                    'title': f'Eliminate {category_name}',
                    'description': f'Remove {len(items)} {category_name.lower()} items to save ${total_savings:.2f}/month',
                    'estimated_savings': total_savings,
                    'effort_level': 'low' if category in [WasteCategory.UNUSED_ELASTIC_IPS, WasteCategory.UNATTACHED_VOLUMES] else 'medium',
                    'implementation_time_days': 3 if len(items) < 10 else 7,
                    'risk_level': 'low',
                    'category': 'waste_removal',
                    'service': items[0].service,
                    'account_id': str(items[0].account_id),
                    'confidence': avg_confidence,
                    'impact': 'high' if total_savings > 100 else 'medium',
                    'actions': self._get_waste_elimination_actions(category),
                    'metadata': {
                        'waste_items_count': len(items),
                        'waste_category': category.value,
                        'top_waste_items': [
                            {
                                'id': str(item.id),
                                'resource_id': item.resource_id,
                                'savings': item.estimated_monthly_savings
                            }
                            for item in items[:5]
                        ]
                    }
                })

        return recommendations

    async def _generate_scheduling_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate scheduling recommendations for non-production workloads"""

        # Placeholder for scheduling recommendations
        # This would analyze cost patterns to identify workloads that could benefit from scheduling

        return []

    async def _generate_security_optimization_recommendations(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate security-related cost optimization recommendations"""

        # Placeholder for security recommendations
        # This would analyze security-related costs and suggest optimizations

        return []

    async def _analyze_cost_patterns(
        self,
        account: Optional[AWSAccount],
        db: AsyncSession
    ) -> List[CostPattern]:
        """Analyze cost patterns using simple statistical methods"""

        patterns = []
        end_date = date.today()
        start_date = end_date - timedelta(days=60)  # 2 months of data

        # Query for cost trends by service
        query = select(
            CostData.account_id,
            CostData.service,
            CostData.date,
            CostData.amount
        ).where(
            and_(
                CostData.date >= start_date,
                CostData.date <= end_date
            )
        ).order_by(CostData.account_id, CostData.service, CostData.date)

        if account:
            query = query.where(CostData.account_id == account.id)

        result = await db.execute(query)
        cost_data = result.all()

        # Group by account and service
        service_data = {}
        for row in cost_data:
            key = (str(row.account_id), row.service)
            if key not in service_data:
                service_data[key] = []
            service_data[key].append((row.date, row.amount))

        # Analyze each service's cost pattern
        for (account_id, service), data in service_data.items():
            if len(data) >= 14:  # Need at least 2 weeks of data
                costs = [amount for _, amount in data]
                avg_cost = np.mean(costs)
                cost_variance = np.var(costs)

                # Simple trend analysis
                x = np.arange(len(costs))
                y = np.array(costs)
                trend_slope = np.polyfit(x, y, 1)[0] if len(costs) > 1 else 0

                # Determine trend direction
                growth_rate = trend_slope / avg_cost if avg_cost > 0 else 0

                if growth_rate > 0.02:  # 2% growth per data point
                    trend = 'increasing'
                elif growth_rate < -0.02:
                    trend = 'decreasing'
                elif cost_variance > avg_cost * 0.25:  # High variance
                    trend = 'volatile'
                else:
                    trend = 'stable'

                pattern = CostPattern(
                    service=service,
                    account_id=account_id,
                    trend=trend,
                    avg_daily_cost=avg_cost,
                    cost_variance=cost_variance,
                    growth_rate=growth_rate,
                    seasonality_detected=False  # Simple implementation doesn't detect seasonality
                )

                patterns.append(pattern)

        return patterns

    def _calculate_ml_score(self, recommendation: Dict[str, Any]) -> RecommendationScore:
        """Calculate ML-based score for recommendation prioritization"""

        # Base score from estimated savings
        estimated_savings = recommendation.get('estimated_savings', 0)
        base_score = min(estimated_savings / 1000, 1.0)  # Normalize to 0-1 scale

        # Impact factor (based on savings potential)
        if estimated_savings > 500:
            impact_factor = 1.0
        elif estimated_savings > 100:
            impact_factor = 0.8
        elif estimated_savings > 50:
            impact_factor = 0.6
        else:
            impact_factor = 0.4

        # Confidence factor
        confidence = recommendation.get('confidence', 0.5)
        confidence_factor = confidence

        # Effort factor (lower effort = higher score)
        effort_level = recommendation.get('effort_level', 'medium')
        effort_factors = {'low': 1.0, 'medium': 0.7, 'high': 0.4}
        effort_factor = effort_factors.get(effort_level, 0.7)

        # Risk factor (lower risk = higher score)
        risk_level = recommendation.get('risk_level', 'medium')
        risk_factors = {'low': 1.0, 'medium': 0.8, 'high': 0.5}
        risk_factor = risk_factors.get(risk_level, 0.8)

        # Calculate final weighted score
        weights = {
            'base': 0.3,
            'impact': 0.25,
            'confidence': 0.2,
            'effort': 0.15,
            'risk': 0.1
        }

        final_score = (
            base_score * weights['base'] +
            impact_factor * weights['impact'] +
            confidence_factor * weights['confidence'] +
            effort_factor * weights['effort'] +
            risk_factor * weights['risk']
        )

        return RecommendationScore(
            base_score=base_score,
            impact_factor=impact_factor,
            confidence_factor=confidence_factor,
            effort_factor=effort_factor,
            risk_factor=risk_factor,
            final_score=min(final_score, 1.0)
        )

    def _get_waste_elimination_actions(self, category: WasteCategory) -> List[str]:
        """Get specific actions for waste elimination by category"""

        actions_map = {
            WasteCategory.UNATTACHED_VOLUMES: [
                'Review unattached EBS volumes',
                'Create snapshots of important volumes',
                'Delete unnecessary volumes',
                'Set up monitoring for future unattached volumes'
            ],
            WasteCategory.UNUSED_ELASTIC_IPS: [
                'Identify unused Elastic IP addresses',
                'Release unused EIPs',
                'Associate necessary EIPs with resources',
                'Review EIP allocation policies'
            ],
            WasteCategory.STOPPED_INSTANCES: [
                'Review stopped instances',
                'Terminate unnecessary instances',
                'Create AMIs for important instances',
                'Consider spot instances for development'
            ]
        }

        return actions_map.get(category, [
            'Review identified resources',
            'Assess business impact',
            'Remove or optimize resources',
            'Implement monitoring'
        ])

    async def _store_recommendations(
        self,
        recommendations: List[Dict[str, Any]],
        db: AsyncSession
    ) -> None:
        """Store generated recommendations in the database"""

        for rec_data in recommendations[:20]:  # Store top 20 recommendations
            try:
                recommendation = Recommendation(
                    account_id=rec_data.get('account_id'),
                    type=rec_data['type'],
                    title=rec_data['title'],
                    description=rec_data['description'],
                    estimated_savings=rec_data['estimated_savings'],
                    confidence_score=rec_data['confidence'],
                    effort_level=rec_data['effort_level'],
                    risk_level=rec_data['risk_level'],
                    implementation_time_days=rec_data.get('implementation_time_days', 7),
                    status=RecommendationStatus.PENDING,
                    category=rec_data.get('category', 'general'),
                    service=rec_data.get('service', 'Multiple'),
                    actions=rec_data.get('actions', []),
                    metadata=rec_data.get('metadata', {})
                )

                db.add(recommendation)

            except Exception as e:
                logger.error("Failed to store recommendation", error=str(e))

        await db.commit()


# Global instance
recommendations_engine = RecommendationsEngine()