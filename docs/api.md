# API Reference

Base URL: `http://localhost:8000/api/v1`

## Costs Endpoints

### Get Cost Summary
```http
GET /costs/summary
```

**Response:**
```json
{
  "current_month": 45234.56,
  "last_month": 42123.45,
  "projected": 48500.00,
  "savings_potential": 8234.00,
  "trend_percentage": 7.3
}
```

### Get Daily Costs
```http
GET /costs/daily?start=2025-01-01&end=2025-01-31
```

**Parameters:**
- `start` (required): Start date in YYYY-MM-DD format
- `end` (required): End date in YYYY-MM-DD format

**Response:**
```json
[
  {
    "date": "2025-01-15",
    "total_cost": 1523.45,
    "services": {
      "EC2": 823.12,
      "RDS": 412.33,
      "S3": 288.00
    },
    "tags": {},
    "region": "us-east-1",
    "account_id": "123456789012"
  }
]
```

### Get Service Costs
```http
GET /costs/services
```

**Response:**
```json
[
  {
    "service": "EC2",
    "cost": 20355.42,
    "percentage": 45,
    "trend": 5.2
  }
]
```

## Waste Detection Endpoints

### Get Waste Items
```http
GET /waste
```

**Response:**
```json
[
  {
    "id": "vol-0123456789abcdef0",
    "resource_type": "EBS Volume",
    "resource_id": "vol-0123456789abcdef0",
    "monthly_cost": 89.50,
    "detected_at": "2025-01-20T10:00:00Z",
    "remediated": false,
    "action": "Delete unused volume",
    "description": "Unattached GP2 volume (100GB)"
  }
]
```

### Remediate Waste Item
```http
POST /waste/{waste_id}/remediate
```

**Response:**
```json
{
  "message": "Waste item vol-0123456789abcdef0 has been scheduled for remediation"
}
```

### Get Waste Summary
```http
GET /waste/summary
```

**Response:**
```json
{
  "total_items": 15,
  "total_monthly_savings": 450.50,
  "total_annual_savings": 5406.00,
  "by_resource_type": {
    "EBS Volume": {
      "count": 8,
      "monthly_cost": 320.50
    },
    "Elastic IP": {
      "count": 5,
      "monthly_cost": 18.00
    }
  }
}
```

## Recommendations Endpoints

### Get Recommendations
```http
GET /recommendations
```

**Response:**
```json
[
  {
    "id": "rec-12345",
    "type": "reserved_instance",
    "resource_id": "i-0123456789abcdef0",
    "title": "Buy Reserved Instances",
    "description": "Purchase 1-year Reserved Instances for consistent workloads",
    "monthly_savings": 2340.00,
    "complexity": 2,
    "risk_level": "low",
    "status": "pending",
    "created_at": "2025-01-20T08:00:00Z"
  }
]
```

### Apply Recommendation
```http
POST /recommendations/{recommendation_id}/apply
```

**Response:**
```json
{
  "message": "Recommendation rec-12345 has been applied successfully"
}
```

### Dismiss Recommendation
```http
POST /recommendations/{recommendation_id}/dismiss
```

**Response:**
```json
{
  "message": "Recommendation rec-12345 has been dismissed"
}
```

### Get Recommendations Summary
```http
GET /recommendations/summary
```

**Response:**
```json
{
  "total_recommendations": 12,
  "total_monthly_savings": 8234.00,
  "total_annual_savings": 98808.00,
  "by_type": {
    "reserved_instance": {
      "count": 3,
      "monthly_savings": 4230.00
    },
    "right_sizing": {
      "count": 4,
      "monthly_savings": 2340.00
    }
  },
  "by_risk_level": {
    "low": {
      "count": 8,
      "monthly_savings": 6230.00
    },
    "medium": {
      "count": 3,
      "monthly_savings": 1560.00
    },
    "high": {
      "count": 1,
      "monthly_savings": 444.00
    }
  }
}
```

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Invalid date format. Use YYYY-MM-DD"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Error fetching cost data: AWS credentials not configured"
}
```

## Rate Limits

- 100 requests per minute per IP address
- AWS API calls are cached for 4 hours to prevent rate limiting

## Authentication

Currently, the API does not require authentication. This will be added in future versions for production deployments.