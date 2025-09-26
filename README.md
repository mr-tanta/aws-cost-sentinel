# AWS Cost Sentinel

Open-source cloud cost optimization platform for AWS environments. Automatically detects waste, provides intelligent recommendations, and helps reduce cloud spending by 20-40% through advanced analytics and ML-powered insights.

## Features

### Cost Analysis & Monitoring
- Real-time cost tracking across multiple AWS accounts
- Service-level cost breakdown and trend analysis
- Cost forecasting based on historical patterns
- Cross-account cost comparison and benchmarking
- Automated cost anomaly detection

### Intelligent Waste Detection
- Unattached EBS volumes identification
- Unused Elastic IP addresses detection
- Long-stopped EC2 instances analysis
- Underutilized resource identification
- Storage optimization opportunities

### ML-Powered Recommendations
- Rightsizing recommendations for EC2 instances
- Reserved Instance purchase suggestions
- Storage class optimization for S3 and EBS
- Cost optimization prioritized by ROI
- Implementation effort and risk assessment

### Multi-Account Management
- Centralized management of multiple AWS accounts
- Role-based access control and security
- Cross-account role assumption support
- Consolidated reporting and analytics

## Architecture

### Backend (Python FastAPI)
- **FastAPI** - Modern async web framework
- **SQLAlchemy** - Database ORM with async support
- **PostgreSQL** - Primary database
- **Redis** - Caching and task queue
- **Celery** - Background job processing
- **AWS SDK (boto3)** - AWS service integration

### Frontend (Next.js)
- **Next.js 15** - React framework with App Router
- **TypeScript** - Type-safe development
- **Material-UI** - Modern React UI framework
- **TailwindCSS** - Utility-first styling

### Infrastructure
- **Docker** - Containerized deployment
- **PostgreSQL** - Persistent data storage
- **Redis** - Session management and caching
- **nginx** - Reverse proxy and load balancing

## Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for local development)
- AWS credentials with appropriate permissions

## Quick Start

### Using Docker Compose

1. Clone the repository:
```bash
git clone https://github.com/mr-tanta/aws-cost-sentinel.git
cd aws-cost-sentinel
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Start the services:
```bash
docker-compose up -d
```

4. Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### Local Development

#### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup
```bash
cd frontend
pnpm install
pnpm dev
```

## Configuration

### Environment Variables

#### Backend (.env)
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/aws_cost_sentinel

# Redis
REDIS_URL=redis://localhost:6379/0

# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# API Settings
API_V1_STR=/api/v1
PROJECT_NAME=AWS Cost Sentinel
CORS_ORIGINS=["http://localhost:3000"]
```

#### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_SECRET=your-nextauth-secret
NEXTAUTH_URL=http://localhost:3000
```

## AWS Permissions

The application requires the following AWS permissions:

### Cost Explorer & Billing
- `ce:GetCostAndUsage`
- `ce:GetUsageReport`
- `ce:GetReservationPurchaseRecommendation`
- `ce:GetRightsizingRecommendation`

### EC2 Permissions
- `ec2:DescribeInstances`
- `ec2:DescribeVolumes`
- `ec2:DescribeSnapshots`
- `ec2:DescribeAddresses`
- `ec2:DescribeImages`

### Additional Services
- `s3:ListAllMyBuckets`
- `s3:GetBucketLocation`
- `rds:DescribeDBInstances`
- `elasticloadbalancing:DescribeLoadBalancers`

## API Documentation

The API documentation is automatically generated and available at `/docs` when running the backend server. Key endpoints include:

### Authentication
- `POST /api/v1/auth/login` - User authentication
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/refresh` - Token refresh

### Cost Analysis
- `GET /api/v1/costs/summary` - Cost summary and trends
- `GET /api/v1/costs/breakdown/services` - Service cost breakdown
- `POST /api/v1/costs/sync` - Manual cost data synchronization

### Waste Detection
- `POST /api/v1/waste/scan/{account_id}` - Scan account for waste
- `GET /api/v1/waste/items` - List detected waste items
- `GET /api/v1/waste/summary` - Waste detection summary

### Recommendations
- `GET /api/v1/recommendations` - Get optimization recommendations
- `PUT /api/v1/recommendations/{id}/status` - Update recommendation status

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 for Python code
- Use TypeScript for all new frontend code
- Write tests for new features
- Update documentation for API changes
- Use conventional commit messages

## Testing

### Backend Tests
```bash
cd backend
pytest tests/ -v
```

### Frontend Tests
```bash
cd frontend
pnpm test
```

## Deployment

### Production Deployment

1. Set production environment variables
2. Build and deploy using Docker Compose:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Kubernetes Deployment

Kubernetes manifests are available in the `k8s/` directory:
```bash
kubectl apply -f k8s/
```

## Monitoring & Observability

The application includes built-in monitoring capabilities:

- **Structured Logging** - JSON-formatted logs with correlation IDs
- **Health Checks** - Application and dependency health endpoints
- **Metrics** - Prometheus-compatible metrics endpoint
- **Error Tracking** - Integration with Sentry (optional)

## Security

- JWT-based authentication with refresh tokens
- Role-based access control (RBAC)
- Rate limiting on API endpoints
- Input validation and sanitization
- Secure AWS credential handling
- HTTPS/TLS encryption in production

## License

MIT License - see LICENSE file for details.

## Support

- Documentation: [Wiki](https://github.com/mr-tanta/aws-cost-sentinel/wiki)
- Issues: [GitHub Issues](https://github.com/mr-tanta/aws-cost-sentinel/issues)
- Discussions: [GitHub Discussions](https://github.com/mr-tanta/aws-cost-sentinel/discussions)

## Roadmap

- [ ] Advanced ML models for cost prediction
- [ ] Multi-cloud support (Azure, GCP)
- [ ] Cost allocation and chargeback features
- [ ] Advanced visualization and dashboards
- [ ] Automated remediation capabilities
- [ ] Integration with popular DevOps tools
