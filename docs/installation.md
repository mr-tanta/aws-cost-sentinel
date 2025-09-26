# Installation Guide

## Prerequisites

- Docker and Docker Compose
- AWS Account with appropriate permissions
- Git

## Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/aws-cost-sentinel.git
cd aws-cost-sentinel
```

2. **Configure environment variables**
```bash
cp .env.example .env
```

Edit the `.env` file with your AWS credentials and settings:
```
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
```

3. **Start the application**
```bash
docker-compose up -d
```

4. **Access the dashboard**
Open http://localhost:3000 in your browser.

## AWS Permissions Required

Create an IAM user or role with the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ce:GetCostAndUsage",
                "ce:GetUsageReport",
                "ce:GetReservationCoverage",
                "ce:GetReservationPurchaseRecommendation",
                "ce:GetReservationUtilization",
                "ec2:DescribeInstances",
                "ec2:DescribeVolumes",
                "ec2:DescribeAddresses",
                "ec2:DescribeSnapshots",
                "rds:DescribeDBInstances",
                "s3:ListAllMyBuckets",
                "s3:GetBucketLocation",
                "s3:GetBucketTagging"
            ],
            "Resource": "*"
        }
    ]
}
```

## Manual Installation

If you prefer to run without Docker:

### Backend Setup

1. **Install Python dependencies**
```bash
cd backend
pip install -r requirements.txt
```

2. **Set up PostgreSQL database**
```bash
createdb cost_sentinel
```

3. **Start Redis**
```bash
redis-server
```

4. **Run the backend**
```bash
uvicorn app.main:app --reload
```

### Frontend Setup

1. **Install Node.js dependencies**
```bash
pnpm install
```

2. **Start the development server**
```bash
pnpm dev
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for API calls |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `SECRET_KEY` | - | JWT secret key |

## Troubleshooting

### Common Issues

1. **AWS Credentials Error**
   - Ensure your AWS credentials are correct
   - Check IAM permissions
   - Try using AWS CLI to test: `aws sts get-caller-identity`

2. **Database Connection Error**
   - Ensure PostgreSQL is running
   - Check connection string in `.env`
   - Verify database exists

3. **Port Already in Use**
   - Check if ports 3000 or 8000 are in use
   - Stop conflicting services or change ports in docker-compose.yml

### Getting Help

- Check GitHub Issues for common problems
- Join our community discussions
- Submit detailed bug reports with logs