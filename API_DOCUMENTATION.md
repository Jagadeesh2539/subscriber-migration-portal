# Subscriber Migration Portal - API Documentation

**Version:** 2.2.0-production-complete  
**Last Updated:** October 29, 2025  
**Base URL:** `https://your-api-gateway-id.execute-api.us-east-1.amazonaws.com/prod`

## Overview

Complete production-ready API for the Subscriber Migration Portal with comprehensive features for all GUI components:

- ✅ **Authentication & Authorization**
- ✅ **Dashboard Statistics** 
- ✅ **Subscriber Management (CRUD)**
- ✅ **Bulk Operations**
- ✅ **Migration Jobs**
- ✅ **File Upload Processing**
- ✅ **Analytics & Reporting**
- ✅ **Provisioning Management**
- ✅ **Data Export**
- ✅ **Audit Logging**

## Authentication

### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "Admin@123"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Login successful",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "username": "admin",
      "role": "admin",
      "permissions": ["read", "write", "delete", "admin"]
    },
    "expires_in": 86400
  }
}
```

### Default Users
- **admin** / Admin@123 (full access)
- **operator** / Operator@123 (read/write)
- **guest** / Guest@123 (read-only)

### Logout
```http
POST /api/auth/logout
Authorization: Bearer {token}
```

## System Health

### Health Check
```http
GET /api/health
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "status": "healthy",
    "version": "2.2.0-production-complete",
    "services": {
      "app": true,
      "dynamodb": true,
      "s3": true,
      "secrets_manager": true,
      "cloudwatch": true,
      "legacy_db": false
    },
    "current_mode": "dual_prov",
    "features_enabled": [
      "authentication",
      "subscriber_management",
      "bulk_operations",
      "migration_jobs",
      "analytics",
      "provisioning",
      "audit_logging",
      "data_export",
      "file_upload"
    ]
  }
}
```

## Dashboard

### Get Dashboard Statistics
```http
GET /api/dashboard/stats
Authorization: Bearer {token}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "totalSubscribers": 1250,
    "cloudSubscribers": 800,
    "legacySubscribers": 450,
    "systemHealth": "healthy",
    "provisioningMode": "dual_prov",
    "lastUpdated": "2025-10-29T11:45:30.123Z",
    "migrationJobs": {
      "active": 2,
      "completed": 15,
      "failed": 1,
      "pending": 3
    },
    "recentActivity": [
      {
        "id": "job-123",
        "type": "migration",
        "status": "completed",
        "timestamp": "2025-10-29T11:30:00.000Z",
        "description": "Migration job csv_upload"
      }
    ],
    "performanceMetrics": {
      "avgResponseTime": 120,
      "successRate": 98.5,
      "throughput": 450
    }
  }
}
```

## Subscriber Management

### Get Subscribers
```http
GET /api/subscribers?limit=50&search=&source=all&status=all
Authorization: Bearer {token}
```

**Parameters:**
- `limit` (optional): Number of results (max 100, default 50)
- `search` (optional): Search term for UID/IMSI/MSISDN
- `source` (optional): all/cloud/legacy (default: all)
- `status` (optional): all/ACTIVE/INACTIVE/DELETED (default: all)

**Response:**
```json
{
  "status": "success",
  "data": {
    "subscribers": [
      {
        "subscriberId": "USER001",
        "uid": "USER001",
        "imsi": "123456789012345",
        "msisdn": "+1234567890",
        "status": "ACTIVE",
        "source": "cloud",
        "created_at": "2025-10-29T10:00:00.000Z",
        "created_by": "admin"
      }
    ],
    "count": 1,
    "total_count": 1250,
    "search": "",
    "source": "all",
    "status": "all"
  }
}
```

### Create Subscriber
```http
POST /api/subscribers
Authorization: Bearer {token}
Content-Type: application/json

{
  "uid": "USER002",
  "imsi": "123456789012346",
  "msisdn": "+1234567891",
  "status": "ACTIVE",
  "mode": "dual_prov",
  "apn": "internet",
  "roaming_allowed": true
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Subscriber created",
  "data": {
    "uid": "USER002",
    "mode": "dual_prov",
    "results": {
      "cloud": "success",
      "legacy": "success"
    }
  }
}
```

## Bulk Operations

### Bulk Delete
```http
POST /api/operations/bulk-delete
Authorization: Bearer {token}
Content-Type: application/json

{
  "identifiers": ["USER001", "USER002", "USER003"],
  "mode": "dual_prov",
  "soft_delete": true
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Bulk delete completed: 2 successful, 1 failed",
  "data": {
    "processed": 3,
    "successful": 2,
    "failed": 1,
    "errors": [
      {
        "identifier": "USER003",
        "error": "Subscriber not found"
      }
    ]
  }
}
```

### Bulk Audit (Compare Systems)
```http
POST /api/audit/compare
Authorization: Bearer {token}
Content-Type: application/json

{
  "systems": ["legacy", "cloud"],
  "sample_size": 100
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Audit comparison completed",
  "data": {
    "comparison_timestamp": "2025-10-29T11:45:30.123Z",
    "systems_compared": ["legacy", "cloud"],
    "sample_size": 100,
    "stats": {
      "total_compared": 95,
      "matches": 85,
      "discrepancies": 5,
      "cloud_only": 3,
      "legacy_only": 2
    },
    "discrepancies": [
      {
        "uid": "USER001",
        "type": "field_mismatch",
        "differences": [
          {
            "field": "status",
            "cloud_value": "ACTIVE",
            "legacy_value": "INACTIVE"
          }
        ]
      }
    ]
  }
}
```

## Migration Jobs

### Get Migration Jobs
```http
GET /api/migration/jobs?limit=20&status=all
Authorization: Bearer {token}
```

**Parameters:**
- `limit` (optional): Number of results (max 100, default 20)
- `status` (optional): all/PENDING/RUNNING/COMPLETED/FAILED

**Response:**
```json
{
  "status": "success",
  "data": {
    "jobs": [
      {
        "id": "job-123",
        "type": "csv_upload",
        "status": "COMPLETED",
        "source": "legacy",
        "target": "cloud",
        "progress": 100,
        "total_records": 500,
        "processed_records": 500,
        "successful_records": 495,
        "failed_records": 5,
        "created_at": "2025-10-29T10:00:00.000Z",
        "created_by": "admin",
        "updated_at": "2025-10-29T10:30:00.000Z"
      }
    ],
    "count": 1,
    "status_filter": "all"
  }
}
```

### Create Migration Job
```http
POST /api/migration/jobs
Authorization: Bearer {token}
Content-Type: application/json

{
  "type": "csv_upload",
  "source": "legacy",
  "target": "cloud",
  "criteria": {
    "status": "ACTIVE"
  },
  "metadata": {
    "description": "Migrate active subscribers"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Migration job created",
  "data": {
    "job_id": "job-456",
    "status": "PENDING",
    "created_at": "2025-10-29T11:45:30.123Z"
  }
}
```

### Upload Migration File
```http
POST /api/migration/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

file: [CSV/JSON/XML file]
target: cloud
```

**Response:**
```json
{
  "status": "success",
  "message": "File uploaded successfully",
  "data": {
    "job_id": "job-789",
    "filename": "subscribers.csv",
    "status": "uploaded"
  }
}
```

## Analytics

### Get Analytics Data
```http
GET /api/analytics?range=30d
Authorization: Bearer {token}
```

**Parameters:**
- `range` (optional): 24h/7d/30d/90d (default: 30d)

**Response:**
```json
{
  "status": "success",
  "data": {
    "time_range": "30d",
    "start_time": "2025-09-29T11:45:30.123Z",
    "end_time": "2025-10-29T11:45:30.123Z",
    "subscriber_metrics": {
      "total_subscribers": 1250,
      "active_subscribers": 1100,
      "inactive_subscribers": 100,
      "new_subscribers": 150,
      "deleted_subscribers": 50
    },
    "migration_metrics": {
      "total_jobs": 21,
      "completed_jobs": 15,
      "failed_jobs": 1,
      "success_rate": 95.24,
      "avg_processing_time": 1800
    },
    "system_metrics": {
      "api_calls": 5420,
      "error_rate": 2.1,
      "avg_response_time": 125
    }
  }
}
```

## Provisioning Management

### Get Provisioning Mode
```http
GET /api/config/provisioning-mode
Authorization: Bearer {token}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "mode": "dual_prov",
    "available_modes": ["legacy", "cloud", "dual_prov"],
    "description": {
      "legacy": "All operations target legacy database only",
      "cloud": "All operations target cloud database only",
      "dual_prov": "Operations target both legacy and cloud databases"
    }
  }
}
```

### Set Provisioning Mode (Admin Only)
```http
POST /api/config/provisioning-mode
Authorization: Bearer {admin-token}
Content-Type: application/json

{
  "mode": "cloud"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Provisioning mode updated",
  "data": {
    "mode": "cloud"
  }
}
```

### Get Provisioning Dashboard
```http
GET /api/provision/dashboard
Authorization: Bearer {token}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "current_mode": "dual_prov",
    "system_status": {
      "legacy_system": {
        "status": "healthy",
        "subscribers": 450,
        "last_sync": "2025-10-29T11:45:30.123Z"
      },
      "cloud_system": {
        "status": "healthy",
        "subscribers": 800,
        "last_sync": "2025-10-29T11:45:30.123Z"
      }
    },
    "sync_status": {
      "in_sync": true,
      "discrepancies": 0,
      "last_audit": "2025-10-29T11:45:30.123Z"
    },
    "recent_operations": []
  }
}
```

## Data Export

### Export Data
```http
GET /api/export/{system}?format=csv&limit=1000
Authorization: Bearer {token}
```

**Parameters:**
- `system`: cloud/legacy/all
- `format` (optional): csv/json (default: csv)
- `limit` (optional): max records (max 10000, default 1000)

**Response:** File download with appropriate headers

**CSV Example:**
```
subscriberId,uid,imsi,msisdn,status,source,created_at
USER001,USER001,123456789012345,+1234567890,ACTIVE,cloud,2025-10-29T10:00:00.000Z
```

## Audit Logging

### Get Audit Logs
```http
GET /api/audit/logs?limit=50&action=&user=&start_date=
Authorization: Bearer {token}
```

**Parameters:**
- `limit` (optional): Number of results (max 1000, default 50)
- `action` (optional): Filter by action type
- `user` (optional): Filter by username
- `start_date` (optional): ISO date string

**Response:**
```json
{
  "status": "success",
  "data": {
    "logs": [
      {
        "id": "20251029_114530_abc12345_login_success",
        "timestamp": "2025-10-29T11:45:30.123Z",
        "action": "login_success",
        "resource": "auth",
        "user": "admin",
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0...",
        "details": {}
      }
    ],
    "count": 1,
    "filters": {
      "action": null,
      "user": null,
      "start_date": null
    }
  }
}
```

## Error Handling

All API endpoints return consistent error responses:

```json
{
  "status": "error",
  "message": "Authentication required",
  "timestamp": "2025-10-29T11:45:30.123Z",
  "version": "2.2.0-production-complete",
  "error": "Detailed error information"
}
```

### Common HTTP Status Codes
- `200` - Success
- `201` - Created
- `400` - Bad Request (invalid input)
- `401` - Unauthorized (invalid/missing token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error
- `503` - Service Unavailable

## Rate Limiting

- **Default:** 1000 requests per day, 200 per hour
- **Login endpoint:** 10 requests per minute
- **Admin users:** May have overrides

## Authentication Headers

For all protected endpoints, include:
```
Authorization: Bearer {your-jwt-token}
Content-Type: application/json
```

## Database Support

### Provisioning Modes
1. **Legacy Mode:** All operations target legacy MySQL database only
2. **Cloud Mode:** All operations target DynamoDB only  
3. **Dual Provisioning:** Operations target both systems simultaneously

### Supported Operations by Mode

| Operation | Legacy | Cloud | Dual Prov |
|-----------|--------|-------|----------|
| Create Subscriber | ✅ | ✅ | ✅ Both |
| Read Subscribers | ✅ | ✅ | ✅ Both |
| Update Subscriber | ✅ | ✅ | ✅ Both |
| Delete Subscriber | ✅ | ✅ | ✅ Both |
| Bulk Operations | ✅ | ✅ | ✅ Both |
| Audit Compare | ✅ | ✅ | ✅ Cross-system |
| Data Export | ✅ | ✅ | ✅ Combined |

## Environment Variables

```bash
# JWT Configuration
JWT_SECRET=your-secret-key

# DynamoDB Tables
SUBSCRIBER_TABLE_NAME=subscriber-table
AUDIT_LOG_TABLE_NAME=audit-log-table
MIGRATION_JOBS_TABLE_NAME=migration-jobs-table
TOKEN_BLACKLIST_TABLE_NAME=token-blacklist-table

# S3 Configuration
MIGRATION_UPLOAD_BUCKET_NAME=migration-uploads

# Legacy Database
LEGACY_DB_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:name
LEGACY_DB_HOST=your-mysql-host
LEGACY_DB_PORT=3306
LEGACY_DB_NAME=legacydb

# Users
USERS_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:users

# System Configuration
PROV_MODE=dual_prov
FRONTEND_ORIGIN=*
```

## Deployment

### Quick Deployment
```powershell
# Run the complete deployment script
.\deploy-complete-backend.ps1
```

### Manual Deployment
```bash
# 1. Package the application
cd backend
pip install -r requirements.txt -t lambda-package/
cp app.py lambda-package/

# 2. Create deployment package
cd lambda-package
zip -r ../lambda-package.zip .
cd ..

# 3. Update Lambda function
aws lambda update-function-code \
  --function-name your-function-name \
  --zip-file fileb://lambda-package.zip

# 4. Update configuration
aws lambda update-function-configuration \
  --function-name your-function-name \
  --handler app.lambda_handler \
  --runtime python3.11 \
  --timeout 30 \
  --memory-size 512
```

## Testing

### Health Check Test
```bash
# Direct Lambda invocation
aws lambda invoke \
  --function-name your-function-name \
  --payload '{}' \
  response.json

# API Gateway test
curl https://your-api-gateway-url/prod/api/health
```

### Authentication Test
```bash
curl -X POST https://your-api-gateway-url/prod/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}'
```

## Troubleshooting

### Common Issues

1. **KeyError: 'headers'** - Fixed in v2.2.0
2. **401 Unauthorized** - Check JWT token and permissions
3. **503 Service Unavailable** - Check DynamoDB table availability
4. **Database connection issues** - Verify Secrets Manager configuration

### Debug Mode

For local development:
```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

## Support

For issues or questions:
1. Check CloudWatch logs for the Lambda function
2. Verify AWS service permissions
3. Test individual endpoints using the provided examples
4. Check environment variable configuration

---

**🎯 All GUI features now have complete backend API support!**