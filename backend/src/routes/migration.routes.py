#!/usr/bin/env python3
"""
Migration Routes - RDS to DynamoDB Migration API Endpoints
Integrates with your existing portal architecture
"""

from flask import Blueprint, request
from middleware.auth import require_auth
from middleware.rate_limiter import rate_limit
from controllers.migration.controller import MigrationController

# Create blueprint
migration_bp = Blueprint('migration', __name__, url_prefix='/api/migration')

# RDS to DynamoDB Migration Routes
@migration_bp.route('/rds-to-dynamo', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def create_migration_job():
    """
    Create new RDS to DynamoDB migration job
    POST /api/migration/rds-to-dynamo
    
    Body:
    {
        "filters": {
            "status": "ACTIVE",           # Optional: filter by subscriber status
            "date_from": "2023-01-01",    # Optional: start date filter
            "date_to": "2025-10-29"       # Optional: end date filter
        },
        "batch_size": 500              # Records per batch (1-1000)
    }
    
    Response:
    {
        "job_id": "uuid-string",
        "status": "PENDING",
        "estimated_records": 15000,
        "batch_size": 500,
        "created_at": "2025-10-29T13:30:00Z"
    }
    """
    return MigrationController.create_migration_job()

@migration_bp.route('/rds-to-dynamo/jobs', methods=['GET'])
@require_auth(['read'])
@rate_limit("20 per minute")
def list_migration_jobs():
    """
    List all migration jobs with filtering
    GET /api/migration/rds-to-dynamo/jobs?status=RUNNING&limit=20&offset=0
    
    Query Parameters:
    - status: Filter by job status (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
    - limit: Number of results (max 100, default 20)
    - offset: Pagination offset (default 0)
    """
    return MigrationController.list_migration_jobs()

@migration_bp.route('/rds-to-dynamo/<job_id>/start', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def start_migration_job(job_id):
    """
    Start migration job execution using Step Functions
    POST /api/migration/rds-to-dynamo/{job_id}/start
    
    Triggers AWS Step Functions workflow for automated migration
    """
    return MigrationController.start_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/pause', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def pause_migration_job(job_id):
    """
    Pause running migration job
    POST /api/migration/rds-to-dynamo/{job_id}/pause
    
    Stops Step Functions execution and preserves cursor position
    """
    return MigrationController.pause_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/resume', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def resume_migration_job(job_id):
    """
    Resume paused migration job
    POST /api/migration/rds-to-dynamo/{job_id}/resume
    
    Restarts Step Functions execution from last cursor position
    """
    return MigrationController.resume_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/cancel', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def cancel_migration_job(job_id):
    """
    Cancel migration job
    POST /api/migration/rds-to-dynamo/{job_id}/cancel
    
    Stops execution and marks job as cancelled
    """
    return MigrationController.cancel_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/status', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_migration_status(job_id):
    """
    Get detailed migration job status and progress
    GET /api/migration/rds-to-dynamo/{job_id}/status
    
    Response:
    {
        "job_id": "uuid-string",
        "status": "RUNNING",
        "progress": {
            "total": 15000,
            "processed": 7500,
            "succeeded": 7450,
            "failed": 50,
            "percentage": 50.0
        },
        "timing": {
            "created_at": "2025-10-29T13:30:00Z",
            "updated_at": "2025-10-29T13:35:00Z",
            "estimated_completion": "2025-10-29T13:45:00Z"
        },
        "execution_status": "RUNNING",
        "error_summary": [],
        "cursor": {"last_id": 7500}
    }
    """
    return MigrationController.get_migration_status(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/audit', methods=['POST'])
@require_auth(['read'])
@rate_limit("5 per minute")
def run_migration_audit(job_id):
    """
    Run post-migration audit to verify data integrity
    POST /api/migration/rds-to-dynamo/{job_id}/audit
    
    Body:
    {
        "sample_size": 1000  # Number of records to compare (1-10000)
    }
    
    Response:
    {
        "audit_timestamp": "2025-10-29T13:40:00Z",
        "sample_size": 1000,
        "results": {
            "matches": 950,
            "discrepancies": 50,
            "missing_in_dynamo": 10,
            "accuracy_percentage": 95.0
        },
        "discrepancies": [
            {
                "type": "field_mismatch",
                "uid": "USER001",
                "differences": {"status": {"rds": "ACTIVE", "dynamo": "INACTIVE"}}
            }
        ]
    }
    """
    return MigrationController.run_migration_audit(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/export', methods=['GET'])
@require_auth(['read'])
@rate_limit("3 per minute")
def export_migration_results(job_id):
    """
    Export migration job results
    GET /api/migration/rds-to-dynamo/{job_id}/export?format=csv
    
    Query Parameters:
    - format: Export format (csv, json)
    
    Returns downloadable file with migration results
    """
    return MigrationController.export_migration_results(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/retry', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def retry_failed_records(job_id):
    """
    Retry failed records from migration job
    POST /api/migration/rds-to-dynamo/{job_id}/retry
    
    Body:
    {
        "batch_size": 50  # Retry batch size (1-500)
    }
    """
    return MigrationController.retry_failed_records(job_id)

# Utility and Information Routes
@migration_bp.route('/rds-to-dynamo/estimate', methods=['POST'])
@require_auth(['read'])
@rate_limit("10 per minute")
def estimate_migration():
    """
    Estimate migration time and resources
    POST /api/migration/rds-to-dynamo/estimate
    
    Body:
    {
        "filters": {
            "status": "ACTIVE"
        },
        "batch_size": 500
    }
    
    Response:
    {
        "estimated_records": 15000,
        "estimated_duration_minutes": 45,
        "estimated_cost_usd": 12.50,
        "recommended_batch_size": 500,
        "resource_requirements": {
            "dynamodb_write_capacity": 100,
            "lambda_concurrency": 5
        }
    }
    """
    return MigrationController.estimate_migration()

@migration_bp.route('/rds-to-dynamo/validate', methods=['POST'])
@require_auth(['read'])
@rate_limit("5 per minute")
def validate_migration_data():
    """
    Validate RDS data before migration
    POST /api/migration/rds-to-dynamo/validate
    
    Body:
    {
        "filters": {},
        "sample_size": 1000
    }
    
    Response:
    {
        "validation_score": 98.5,
        "total_records": 15000,
        "sample_size": 1000,
        "issues": [
            {
                "type": "missing_imsi",
                "count": 25,
                "severity": "high"
            }
        ],
        "recommendations": [
            "Clean up records with missing IMSI before migration"
        ]
    }
    """
    return MigrationController.validate_migration_data()

@migration_bp.route('/rds-to-dynamo/compatibility', methods=['GET'])
@require_auth(['read'])
@rate_limit("10 per minute")
def get_system_compatibility():
    """
    Check RDS and DynamoDB compatibility for migration
    GET /api/migration/rds-to-dynamo/compatibility
    
    Response:
    {
        "compatible": true,
        "rds_status": {
            "connected": true,
            "version": "8.0.35",
            "table_exists": true,
            "record_count": 15000
        },
        "dynamodb_status": {
            "accessible": true,
            "table_exists": true,
            "capacity_mode": "ON_DEMAND",
            "encryption_enabled": true
        },
        "schema_compatibility": {
            "fields_mapped": ["uid", "imsi", "msisdn", "status"],
            "missing_fields": [],
            "type_conversions": {"created_at": "datetime_to_iso_string"}
        }
    }
    """
    return MigrationController.get_system_compatibility()

@migration_bp.route('/rds-to-dynamo/metrics', methods=['GET'])
@require_auth(['read'])
@rate_limit("20 per minute")
def get_migration_metrics():
    """
    Get overall migration metrics and statistics
    GET /api/migration/rds-to-dynamo/metrics
    
    Response:
    {
        "total_jobs": 25,
        "completed_jobs": 20,
        "failed_jobs": 2,
        "running_jobs": 3,
        "total_records_migrated": 500000,
        "average_throughput": 1200,  # records per minute
        "success_rate": 98.5,
        "last_migration": "2025-10-29T13:30:00Z"
    }
    """
    return MigrationController.get_migration_metrics()

@migration_bp.route('/rds-to-dynamo/dashboard', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_migration_dashboard():
    """
    Get comprehensive migration dashboard data
    GET /api/migration/rds-to-dynamo/dashboard
    
    Returns data for migration dashboard widgets:
    - Active job progress
    - System health indicators  
    - Migration history charts
    - Performance metrics
    """
    return MigrationController.get_migration_dashboard()

@migration_bp.route('/rds-to-dynamo/<job_id>/rollback-point', methods=['POST'])
@require_auth(['write'])
@rate_limit("3 per minute")
def create_rollback_point(job_id):
    """
    Create rollback point before migration (S3 backup)
    POST /api/migration/rds-to-dynamo/{job_id}/rollback-point
    
    Creates S3 backup of current DynamoDB state for rollback
    """
    return MigrationController.create_rollback_point(job_id)

# Legacy Integration Routes (for your existing system)
@migration_bp.route('/jobs', methods=['GET'])
@require_auth(['read'])
@rate_limit("50 per minute")
def get_legacy_migration_jobs():
    """
    Get legacy migration jobs (backwards compatibility)
    GET /api/migration/jobs
    
    Integrates with your existing job management UI
    """
    return MigrationController.list_migration_jobs()

@migration_bp.route('/jobs', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def create_legacy_migration_job():
    """
    Create migration job (legacy endpoint compatibility)
    POST /api/migration/jobs
    
    Body:
    {
        "source": "rds_mysql",
        "target": "dynamodb", 
        "config": {
            "batch_size": 500,
            "filters": {}
        }
    }
    """
    # Redirect to new RDS-to-DynamoDB endpoint
    return MigrationController.create_migration_job()

@migration_bp.route('/jobs/<job_id>', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_legacy_job_status(job_id):
    """
    Get job status (legacy endpoint compatibility)
    GET /api/migration/jobs/{job_id}
    
    Integrates with your existing job status polling
    """
    return MigrationController.get_migration_status(job_id)

@migration_bp.route('/upload', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def upload_migration_data():
    """
    Upload migration data file (integrates with existing upload UI)
    POST /api/migration/upload
    
    Form Data:
    - file: CSV file with migration data
    - target_system: cloud, legacy, dual
    - job_name: Optional job name
    
    Creates migration job from uploaded file
    """
    try:
        if 'file' not in request.files:
            return {'error': 'No file uploaded'}, 400
        
        file = request.files['file']
        target_system = request.form.get('target_system', 'dual')
        job_name = request.form.get('job_name', f'Upload_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        
        # Process uploaded file and create migration job
        result = MigrationController.process_upload_and_create_job(file, target_system, job_name)
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing migration upload: {str(e)}")
        return {'error': 'Failed to process upload'}, 500

# Error handlers for migration routes
@migration_bp.errorhandler(400)
def handle_bad_request(error):
    return {
        'status': 'error',
        'message': 'Invalid migration request',
        'timestamp': datetime.utcnow().isoformat()
    }, 400

@migration_bp.errorhandler(404)
def handle_job_not_found(error):
    return {
        'status': 'error',
        'message': 'Migration job not found',
        'timestamp': datetime.utcnow().isoformat()
    }, 404

@migration_bp.errorhandler(409)
def handle_job_conflict(error):
    return {
        'status': 'error',
        'message': 'Migration job state conflict',
        'timestamp': datetime.utcnow().isoformat()
    }, 409

# Export blueprint
migration_routes = migration_bp