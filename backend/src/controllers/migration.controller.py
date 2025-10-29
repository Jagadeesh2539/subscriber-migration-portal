#!/usr/bin/env python3
"""
Migration Controller - RDS to DynamoDB Migration Operations
Handles: Create, Monitor, and Manage migration jobs with Step Functions integration
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import g, jsonify, request

from services.audit.service import AuditService
from services.rds_migration.service import RDSMigrationService
from utils.logger import get_logger
from utils.response import create_error_response, create_response
from utils.validation import InputValidator, ValidationError

logger = get_logger(__name__)
migration_service = RDSMigrationService()
audit_service = AuditService()

class MigrationController:
    """Controller for RDS to DynamoDB migration operations"""
    
    @staticmethod
    def create_migration_job():
        """
        Create new migration job
        POST /api/migration/rds-to-dynamo
        """
        try:
            data = request.get_json() or {}
            
            # Validate input
            validator = InputValidator()
            
            filters = data.get('filters', {})
            batch_size = data.get('batch_size', 100)
            
            # Validate batch size
            if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 1000:
                return create_error_response("Batch size must be between 1 and 1000", 400)
            
            # Validate filters
            if filters:
                if 'status' in filters and filters['status'] not in ['ACTIVE', 'INACTIVE', 'SUSPENDED', 'DELETED']:
                    return create_error_response("Invalid status filter", 400)
                
                # Validate date filters
                for date_field in ['date_from', 'date_to']:
                    if date_field in filters:
                        try:
                            datetime.fromisoformat(filters[date_field].replace('Z', '+00:00'))
                        except ValueError:
                            return create_error_response(f"Invalid {date_field} format. Use ISO format.", 400)
            
            # Create migration job
            job = migration_service.create_migration_job(filters, batch_size)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_job_created',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': job.id,
                    'source': 'rds_mysql',
                    'target': 'dynamodb',
                    'estimated_records': job.stats['total'],
                    'batch_size': batch_size,
                    'filters': filters
                }
            )
            
            return create_response(
                data={
                    'job_id': job.id,
                    'status': job.status,
                    'estimated_records': job.stats['total'],
                    'batch_size': job.batch_size,
                    'filters': job.filters,
                    'created_at': job.created_at
                },
                message=f"Migration job created with {job.stats['total']} records to migrate"
            )
            
        except ValidationError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error creating migration job: {str(e)}")
            return create_error_response("Failed to create migration job", 500)
    
    @staticmethod
    def start_migration_job(job_id: str):
        """
        Start migration job execution
        POST /api/migration/rds-to-dynamo/{job_id}/start
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            if not clean_job_id:
                return create_error_response("Invalid job ID", 400)
            
            # Start the migration job
            result = migration_service.start_migration_job(clean_job_id)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_job_started',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': clean_job_id,
                    'execution_arn': result.get('execution_arn')
                }
            )
            
            return create_response(
                data=result,
                message=f"Migration job {clean_job_id} started successfully"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error starting migration job {job_id}: {str(e)}")
            return create_error_response("Failed to start migration job", 500)
    
    @staticmethod
    def pause_migration_job(job_id: str):
        """
        Pause running migration job
        POST /api/migration/rds-to-dynamo/{job_id}/pause
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            result = migration_service.pause_migration_job(clean_job_id)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_job_paused',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={'job_id': clean_job_id}
            )
            
            return create_response(
                data=result,
                message=f"Migration job {clean_job_id} paused successfully"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error pausing migration job {job_id}: {str(e)}")
            return create_error_response("Failed to pause migration job", 500)
    
    @staticmethod
    def resume_migration_job(job_id: str):
        """
        Resume paused migration job
        POST /api/migration/rds-to-dynamo/{job_id}/resume
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            result = migration_service.resume_migration_job(clean_job_id)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_job_resumed',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': clean_job_id,
                    'execution_arn': result.get('execution_arn')
                }
            )
            
            return create_response(
                data=result,
                message=f"Migration job {clean_job_id} resumed successfully"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error resuming migration job {job_id}: {str(e)}")
            return create_error_response("Failed to resume migration job", 500)
    
    @staticmethod
    def cancel_migration_job(job_id: str):
        """
        Cancel migration job
        POST /api/migration/rds-to-dynamo/{job_id}/cancel
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            result = migration_service.cancel_migration_job(clean_job_id)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_job_cancelled',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={'job_id': clean_job_id}
            )
            
            return create_response(
                data=result,
                message=f"Migration job {clean_job_id} cancelled successfully"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error cancelling migration job {job_id}: {str(e)}")
            return create_error_response("Failed to cancel migration job", 500)
    
    @staticmethod
    def get_migration_status(job_id: str):
        """
        Get migration job status and progress
        GET /api/migration/rds-to-dynamo/{job_id}/status
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            status = migration_service.get_migration_status(clean_job_id)
            
            return create_response(
                data=status,
                message="Migration status retrieved successfully"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error getting migration status for {job_id}: {str(e)}")
            return create_error_response("Failed to get migration status", 500)
    
    @staticmethod
    def list_migration_jobs():
        """
        List all migration jobs with filtering
        GET /api/migration/rds-to-dynamo/jobs?status=&limit=&offset=
        """
        try:
            # Parse query parameters
            status_filter = request.args.get('status', 'all')
            limit = min(int(request.args.get('limit', 20)), 100)
            offset = int(request.args.get('offset', 0))
            
            # Get jobs from service
            result = migration_service.list_migration_jobs({
                'status': status_filter if status_filter != 'all' else None,
                'limit': limit,
                'offset': offset
            })
            
            return create_response(data=result)
            
        except Exception as e:
            logger.error(f"Error listing migration jobs: {str(e)}")
            return create_error_response("Failed to list migration jobs", 500)
    
    @staticmethod
    def run_migration_audit(job_id: str):
        """
        Run post-migration audit
        POST /api/migration/rds-to-dynamo/{job_id}/audit
        """
        try:
            data = request.get_json() or {}
            sample_size = data.get('sample_size', 1000)
            
            # Validate sample size
            if not isinstance(sample_size, int) or sample_size < 1 or sample_size > 10000:
                return create_error_response("Sample size must be between 1 and 10000", 400)
            
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            # Run audit
            audit_result = migration_service.run_migration_audit(clean_job_id, sample_size)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_audit_requested',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': clean_job_id,
                    'sample_size': sample_size,
                    'accuracy': audit_result['results']['accuracy_percentage']
                }
            )
            
            return create_response(
                data=audit_result,
                message=f"Migration audit completed - {audit_result['results']['accuracy_percentage']:.2f}% accuracy"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error running migration audit for {job_id}: {str(e)}")
            return create_error_response("Failed to run migration audit", 500)
    
    @staticmethod
    def get_migration_metrics():
        """
        Get overall migration metrics and statistics
        GET /api/migration/rds-to-dynamo/metrics
        """
        try:
            metrics = migration_service.get_migration_metrics()
            
            return create_response(
                data=metrics,
                message="Migration metrics retrieved successfully"
            )
            
        except Exception as e:
            logger.error(f"Error getting migration metrics: {str(e)}")
            return create_error_response("Failed to get migration metrics", 500)
    
    @staticmethod
    def estimate_migration():
        """
        Estimate migration time and resources
        POST /api/migration/rds-to-dynamo/estimate
        """
        try:
            data = request.get_json() or {}
            filters = data.get('filters', {})
            batch_size = data.get('batch_size', 100)
            
            # Get estimation
            estimation = migration_service.estimate_migration(filters, batch_size)
            
            return create_response(
                data=estimation,
                message="Migration estimation completed"
            )
            
        except Exception as e:
            logger.error(f"Error estimating migration: {str(e)}")
            return create_error_response("Failed to estimate migration", 500)
    
    @staticmethod
    def validate_migration_data():
        """
        Validate RDS data before migration
        POST /api/migration/rds-to-dynamo/validate
        """
        try:
            data = request.get_json() or {}
            filters = data.get('filters', {})
            sample_size = data.get('sample_size', 1000)
            
            # Run validation
            validation_result = migration_service.validate_source_data(filters, sample_size)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_data_validated',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'sample_size': sample_size,
                    'validation_score': validation_result['validation_score'],
                    'issues_found': len(validation_result.get('issues', []))
                }
            )
            
            return create_response(
                data=validation_result,
                message=f"Data validation completed - {validation_result['validation_score']:.1f}% valid"
            )
            
        except Exception as e:
            logger.error(f"Error validating migration data: {str(e)}")
            return create_error_response("Failed to validate migration data", 500)
    
    @staticmethod
    def export_migration_results(job_id: str):
        """
        Export migration job results
        GET /api/migration/rds-to-dynamo/{job_id}/export?format=csv
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            format_type = request.args.get('format', 'csv')
            
            if format_type not in ['csv', 'json']:
                return create_error_response("Invalid format. Use 'csv' or 'json'", 400)
            
            # Export results
            export_data = migration_service.export_job_results(clean_job_id, format_type)
            
            # Create file response
            from flask import make_response
            
            response = make_response(export_data['content'])
            
            if format_type == 'csv':
                response.headers['Content-Type'] = 'text/csv; charset=utf-8'
                response.headers['Content-Disposition'] = f'attachment; filename=migration_results_{clean_job_id}.csv'
            else:
                response.headers['Content-Type'] = 'application/json'
                response.headers['Content-Disposition'] = f'attachment; filename=migration_results_{clean_job_id}.json'
            
            # Log audit trail
            audit_service.log_action(
                action='migration_results_exported',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': clean_job_id,
                    'format': format_type,
                    'record_count': export_data['record_count']
                }
            )
            
            return response
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error exporting migration results for {job_id}: {str(e)}")
            return create_error_response("Failed to export migration results", 500)
    
    @staticmethod
    def get_migration_dashboard():
        """
        Get migration dashboard with overall statistics
        GET /api/migration/rds-to-dynamo/dashboard
        """
        try:
            dashboard_data = migration_service.get_migration_dashboard()
            
            return create_response(
                data=dashboard_data,
                message="Migration dashboard data retrieved successfully"
            )
            
        except Exception as e:
            logger.error(f"Error getting migration dashboard: {str(e)}")
            return create_error_response("Failed to get migration dashboard", 500)
    
    @staticmethod
    def retry_failed_records(job_id: str):
        """
        Retry failed records from a migration job
        POST /api/migration/rds-to-dynamo/{job_id}/retry
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            data = request.get_json() or {}
            retry_batch_size = data.get('batch_size', 50)
            
            # Validate retry batch size
            if not isinstance(retry_batch_size, int) or retry_batch_size < 1 or retry_batch_size > 500:
                return create_error_response("Retry batch size must be between 1 and 500", 400)
            
            # Retry failed records
            result = migration_service.retry_failed_records(clean_job_id, retry_batch_size)
            
            # Log audit trail
            audit_service.log_action(
                action='migration_retry_initiated',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': clean_job_id,
                    'retry_batch_size': retry_batch_size,
                    'failed_records_count': result.get('failed_records_count', 0)
                }
            )
            
            return create_response(
                data=result,
                message=f"Retry initiated for {result.get('failed_records_count', 0)} failed records"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error retrying failed records for {job_id}: {str(e)}")
            return create_error_response("Failed to retry failed records", 500)
    
    @staticmethod
    def get_system_compatibility():
        """
        Check RDS and DynamoDB compatibility for migration
        GET /api/migration/rds-to-dynamo/compatibility
        """
        try:
            compatibility = migration_service.check_system_compatibility()
            
            return create_response(
                data=compatibility,
                message="System compatibility check completed"
            )
            
        except Exception as e:
            logger.error(f"Error checking system compatibility: {str(e)}")
            return create_error_response("Failed to check system compatibility", 500)
    
    @staticmethod
    def create_rollback_point(job_id: str):
        """
        Create rollback point before migration
        POST /api/migration/rds-to-dynamo/{job_id}/rollback-point
        """
        try:
            validator = InputValidator()
            clean_job_id = validator.sanitize_string(job_id, 50)
            
            rollback_result = migration_service.create_rollback_point(clean_job_id)
            
            # Log audit trail
            audit_service.log_action(
                action='rollback_point_created',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'job_id': clean_job_id,
                    'rollback_id': rollback_result.get('rollback_id'),
                    's3_backup_location': rollback_result.get('backup_location')
                }
            )
            
            return create_response(
                data=rollback_result,
                message="Rollback point created successfully"
            )
            
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error creating rollback point for {job_id}: {str(e)}")
            return create_error_response("Failed to create rollback point", 500)

# Export controller instance
migration_controller = MigrationController()