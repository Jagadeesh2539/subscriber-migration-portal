#!/usr/bin/env python3
"""
Migration Routes - RDS to DynamoDB Migration API Endpoints
Integrates with your existing portal architecture
"""

import logging
from datetime import datetime

from flask import Blueprint, request
from middleware.auth import require_auth
from middleware.rate_limiter import rate_limit

from controllers.migration.controller import MigrationController

logger = logging.getLogger(__name__)

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
    """
    return MigrationController.create_migration_job()

@migration_bp.route('/rds-to-dynamo/jobs', methods=['GET'])
@require_auth(['read'])
@rate_limit("20 per minute")
def list_migration_jobs():
    """List all migration jobs with filtering"""
    return MigrationController.list_migration_jobs()

@migration_bp.route('/rds-to-dynamo/<job_id>/start', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def start_migration_job(job_id):
    """Start migration job execution using Step Functions"""
    return MigrationController.start_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/pause', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def pause_migration_job(job_id):
    """Pause running migration job"""
    return MigrationController.pause_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/resume', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def resume_migration_job(job_id):
    """Resume paused migration job"""
    return MigrationController.resume_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/cancel', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def cancel_migration_job(job_id):
    """Cancel migration job"""
    return MigrationController.cancel_migration_job(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/status', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_migration_status(job_id):
    """Get detailed migration job status and progress"""
    return MigrationController.get_migration_status(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/audit', methods=['POST'])
@require_auth(['read'])
@rate_limit("5 per minute")
def run_migration_audit(job_id):
    """Run post-migration audit to verify data integrity"""
    return MigrationController.run_migration_audit(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/export', methods=['GET'])
@require_auth(['read'])
@rate_limit("3 per minute")
def export_migration_results(job_id):
    """Export migration job results (csv or json)"""
    return MigrationController.export_migration_results(job_id)

@migration_bp.route('/rds-to-dynamo/<job_id>/retry', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def retry_failed_records(job_id):
    """Retry failed records from migration job"""
    return MigrationController.retry_failed_records(job_id)

# Utility and Information Routes
@migration_bp.route('/rds-to-dynamo/estimate', methods=['POST'])
@require_auth(['read'])
@rate_limit("10 per minute")
def estimate_migration():
    """Estimate migration time and resources"""
    return MigrationController.estimate_migration()

@migration_bp.route('/rds-to-dynamo/validate', methods=['POST'])
@require_auth(['read'])
@rate_limit("5 per minute")
def validate_migration_data():
    """Validate RDS data before migration"""
    return MigrationController.validate_migration_data()

@migration_bp.route('/rds-to-dynamo/compatibility', methods=['GET'])
@require_auth(['read'])
@rate_limit("10 per minute")
def get_system_compatibility():
    """Check RDS and DynamoDB compatibility for migration"""
    return MigrationController.get_system_compatibility()

@migration_bp.route('/rds-to-dynamo/metrics', methods=['GET'])
@require_auth(['read'])
@rate_limit("20 per minute")
def get_migration_metrics():
    """Get overall migration metrics and statistics"""
    return MigrationController.get_migration_metrics()

@migration_bp.route('/rds-to-dynamo/dashboard', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_migration_dashboard():
    """Get comprehensive migration dashboard data"""
    return MigrationController.get_migration_dashboard()

@migration_bp.route('/rds-to-dynamo/<job_id>/rollback-point', methods=['POST'])
@require_auth(['write'])
@rate_limit("3 per minute")
def create_rollback_point(job_id):
    """Create rollback point before migration (S3 backup)"""
    return MigrationController.create_rollback_point(job_id)

# Legacy Integration Routes (for your existing system)
@migration_bp.route('/jobs', methods=['GET'])
@require_auth(['read'])
@rate_limit("50 per minute")
def get_legacy_migration_jobs():
    """Get legacy migration jobs (backwards compatibility)"""
    return MigrationController.list_migration_jobs()

@migration_bp.route('/jobs', methods=['POST'])
@require_auth(['write'])
@rate_limit("10 per minute")
def create_legacy_migration_job():
    """Create migration job (legacy endpoint compatibility)"""
    # Redirect to new RDS-to-DynamoDB endpoint
    return MigrationController.create_migration_job()

@migration_bp.route('/jobs/<job_id>', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_legacy_job_status(job_id):
    """Get job status (legacy endpoint compatibility)"""
    return MigrationController.get_migration_status(job_id)

@migration_bp.route('/upload', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def upload_migration_data():
    """Upload migration data file (integrates with existing upload UI)"""
    try:
        if 'file' not in request.files:
            return {'error': 'No file uploaded'}, 400
        file = request.files['file']
        target_system = request.form.get('target_system', 'dual')
        job_name = request.form.get('job_name', f'Upload_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
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
        'timestamp': datetime.utcnow().isoformat(),
    }, 400

@migration_bp.errorhandler(404)
def handle_job_not_found(error):
    return {
        'status': 'error',
        'message': 'Migration job not found',
        'timestamp': datetime.utcnow().isoformat(),
    }, 404

@migration_bp.errorhandler(409)
def handle_job_conflict(error):
    return {
        'status': 'error',
        'message': 'Migration job state conflict',
        'timestamp': datetime.utcnow().isoformat(),
    }, 409

# Export blueprint
migration_routes = migration_bp
