#!/usr/bin/env python3
"""
Migration Controller - RDS to DynamoDB Migration Operations
Handles: Create, Monitor, and Manage migration jobs with Step Functions integration
"""

from datetime import datetime
from typing import Any, Dict

from flask import g, request
from services.audit.service import AuditService
from services.rds_migration.service import RDSMigrationService
from utils.logger import get_logger
from utils.response import create_error_response, create_response
from utils.validation import InputValidator, ValidationError

logger = get_logger(__name__)
migration_service = RDSMigrationService()
audit_service = AuditService()


class MigrationController:
    """Migration operations controller with comprehensive job management"""

    @staticmethod
    def create_migration_job():
        """
        Create new RDS to DynamoDB migration job
        POST /api/migration/rds-to-dynamo
        """
        try:
            data = request.get_json()
            if not data:
                return create_error_response("Request body is required", 400)

            validator = InputValidator()

            # Validate required fields
            required_fields = ["job_name", "source_config", "target_config"]
            validated_data = validator.validate_json(data, required_fields)

            # Create migration job
            result = migration_service.create_migration_job(validated_data)

            # Log audit trail
            audit_service.log_action(
                action="migration_job_created",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={
                    "job_id": result.get("job_id"),
                    "job_name": validated_data.get("job_name"),
                    "source_type": validated_data.get("source_config", {}).get("type", "unknown"),
                    "target_type": validated_data.get("target_config", {}).get("type", "unknown"),
                },
            )

            return create_response(data=result, message="Migration job created successfully")

        except ValidationError as e:
            logger.warning("Validation error in create_migration_job: %s", str(e))
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error("Error creating migration job: %s", str(e))
            return create_error_response("Failed to create migration job", 500)

    @staticmethod
    def list_migration_jobs():
        """
        List all migration jobs with filtering and pagination
        GET /api/migration/rds-to-dynamo/jobs
        """
        try:
            # Parse query parameters
            status_filter = request.args.get("status", "all")
            limit = min(int(request.args.get("limit", 50)), 100)
            offset = int(request.args.get("offset", 0))
            sort_by = request.args.get("sort", "created_at")
            sort_order = request.args.get("order", "desc")

            # Build filter criteria
            filter_criteria = {
                "status": status_filter if status_filter != "all" else None,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
            }

            # Get jobs from service
            result = migration_service.list_migration_jobs(filter_criteria)

            return create_response(data=result, message="Migration jobs retrieved successfully")

        except Exception as e:
            logger.error("Error listing migration jobs: %s", str(e))
            return create_error_response("Failed to retrieve migration jobs", 500)

    @staticmethod
    def start_migration_job(job_id: str):
        """
        Start migration job execution
        POST /api/migration/rds-to-dynamo/{job_id}/start
        """
        try:
            # Start the job
            result = migration_service.start_migration_job(job_id)

            # Log audit trail
            audit_service.log_action(
                action="migration_job_started",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={"job_id": job_id},
            )

            return create_response(data=result, message="Migration job started successfully")

        except Exception as e:
            logger.error("Error starting migration job %s: %s", job_id, str(e))
            return create_error_response("Failed to start migration job", 500)

    @staticmethod
    def pause_migration_job(job_id: str):
        """
        Pause running migration job
        POST /api/migration/rds-to-dynamo/{job_id}/pause
        """
        try:
            result = migration_service.pause_migration_job(job_id)

            audit_service.log_action(
                action="migration_job_paused",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={"job_id": job_id},
            )

            return create_response(data=result, message="Migration job paused successfully")

        except Exception as e:
            logger.error("Error pausing migration job %s: %s", job_id, str(e))
            return create_error_response("Failed to pause migration job", 500)

    @staticmethod
    def resume_migration_job(job_id: str):
        """
        Resume paused migration job
        POST /api/migration/rds-to-dynamo/{job_id}/resume
        """
        try:
            result = migration_service.resume_migration_job(job_id)

            audit_service.log_action(
                action="migration_job_resumed",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={"job_id": job_id},
            )

            return create_response(data=result, message="Migration job resumed successfully")

        except Exception as e:
            logger.error("Error resuming migration job %s: %s", job_id, str(e))
            return create_error_response("Failed to resume migration job", 500)

    @staticmethod
    def cancel_migration_job(job_id: str):
        """
        Cancel migration job
        POST /api/migration/rds-to-dynamo/{job_id}/cancel
        """
        try:
            result = migration_service.cancel_migration_job(job_id)

            audit_service.log_action(
                action="migration_job_cancelled",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={"job_id": job_id},
            )

            return create_response(data=result, message="Migration job cancelled successfully")

        except Exception as e:
            logger.error("Error cancelling migration job %s: %s", job_id, str(e))
            return create_error_response("Failed to cancel migration job", 500)

    @staticmethod
    def get_migration_status(job_id: str):
        """
        Get detailed migration job status and progress
        GET /api/migration/rds-to-dynamo/{job_id}/status
        """
        try:
            result = migration_service.get_migration_status(job_id)

            if not result:
                return create_error_response("Migration job not found", 404)

            return create_response(data=result, message="Migration job status retrieved successfully")

        except Exception as e:
            logger.error("Error getting migration job status %s: %s", job_id, str(e))
            return create_error_response("Failed to get migration job status", 500)

    @staticmethod
    def run_migration_audit(job_id: str):
        """
        Run post-migration audit to verify data integrity
        POST /api/migration/rds-to-dynamo/{job_id}/audit
        """
        try:
            data = request.get_json() or {}
            audit_options = {
                "sample_size": data.get("sample_size", 1000),
                "detailed_check": data.get("detailed_check", False),
                "check_data_integrity": data.get("check_data_integrity", True),
            }

            result = migration_service.run_migration_audit(job_id, audit_options)

            audit_service.log_action(
                action="migration_audit_run",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={"job_id": job_id, "audit_options": audit_options, "audit_result": result.get("summary", {})},
            )

            return create_response(data=result, message="Migration audit completed successfully")

        except Exception as e:
            logger.error("Error running migration audit %s: %s", job_id, str(e))
            return create_error_response("Failed to run migration audit", 500)

    @staticmethod
    def export_migration_results(job_id: str):
        """
        Export migration job results
        GET /api/migration/rds-to-dynamo/{job_id}/export
        """
        try:
            # Parse export parameters
            export_format = request.args.get("format", "csv")  # csv, json, excel
            include_errors = request.args.get("include_errors", "true").lower() == "true"
            include_audit = request.args.get("include_audit", "false").lower() == "true"

            if export_format not in ["csv", "json", "excel"]:
                return create_error_response("Invalid export format. Supported: csv, json, excel", 400)

            export_options = {"format": export_format, "include_errors": include_errors, "include_audit": include_audit}

            result = migration_service.export_migration_results(job_id, export_options)

            audit_service.log_action(
                action="migration_results_exported",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={
                    "job_id": job_id,
                    "export_format": export_format,
                    "records_exported": result.get("record_count", 0),
                },
            )

            # Return file download response
            from flask import make_response

            response = make_response(result["content"])

            # Set appropriate content type and filename
            if export_format == "csv":
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                filename = f"migration_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            elif export_format == "json":
                response.headers["Content-Type"] = "application/json"
                filename = f"migration_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            else:  # excel
                response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                filename = f"migration_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

            response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

            return response

        except Exception as e:
            logger.error("Error exporting migration results %s: %s", job_id, str(e))
            return create_error_response("Failed to export migration results", 500)

    @staticmethod
    def retry_failed_records(job_id: str):
        """
        Retry failed records from migration job
        POST /api/migration/rds-to-dynamo/{job_id}/retry
        """
        try:
            data = request.get_json() or {}
            retry_options = {
                "max_retries": data.get("max_retries", 3),
                "retry_delay": data.get("retry_delay", 5),
                "specific_errors_only": data.get("specific_errors_only", []),
            }

            result = migration_service.retry_failed_records(job_id, retry_options)

            audit_service.log_action(
                action="migration_failed_records_retried",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={"job_id": job_id, "retry_options": retry_options, "retry_result": result.get("summary", {})},
            )

            return create_response(data=result, message="Failed records retry completed")

        except Exception as e:
            logger.error("Error retrying failed records %s: %s", job_id, str(e))
            return create_error_response("Failed to retry failed records", 500)

    @staticmethod
    def estimate_migration():
        """
        Estimate migration time and resources
        POST /api/migration/rds-to-dynamo/estimate
        """
        try:
            data = request.get_json()
            if not data:
                return create_error_response("Request body is required", 400)

            # Validate estimation request
            validator = InputValidator()
            required_fields = ["source_config"]
            validated_data = validator.validate_json(data, required_fields)

            result = migration_service.estimate_migration(validated_data)

            return create_response(data=result, message="Migration estimation completed")

        except ValidationError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error("Error estimating migration: %s", str(e))
            return create_error_response("Failed to estimate migration", 500)

    @staticmethod
    def validate_migration_data():
        """
        Validate RDS data before migration
        POST /api/migration/rds-to-dynamo/validate
        """
        try:
            data = request.get_json()
            if not data:
                return create_error_response("Request body is required", 400)

            validator = InputValidator()
            required_fields = ["source_config"]
            validated_data = validator.validate_json(data, required_fields)

            result = migration_service.validate_source_data(validated_data)

            return create_response(data=result, message="Data validation completed")

        except ValidationError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error("Error validating migration data: %s", str(e))
            return create_error_response("Failed to validate migration data", 500)

    @staticmethod
    def get_system_compatibility():
        """
        Check RDS and DynamoDB compatibility for migration
        GET /api/migration/rds-to-dynamo/compatibility
        """
        try:
            result = migration_service.check_system_compatibility()

            return create_response(data=result, message="System compatibility check completed")

        except Exception as e:
            logger.error("Error checking system compatibility: %s", str(e))
            return create_error_response("Failed to check system compatibility", 500)

    @staticmethod
    def get_migration_metrics():
        """
        Get overall migration metrics and statistics
        GET /api/migration/rds-to-dynamo/metrics
        """
        try:
            # Parse time range parameters
            days = int(request.args.get("days", 30))
            include_details = request.args.get("include_details", "false").lower() == "true"

            metrics_options = {"days": days, "include_details": include_details}

            result = migration_service.get_migration_metrics(metrics_options)

            return create_response(data=result, message="Migration metrics retrieved successfully")

        except Exception as e:
            logger.error("Error getting migration metrics: %s", str(e))
            return create_error_response("Failed to get migration metrics", 500)

    @staticmethod
    def get_migration_dashboard():
        """
        Get comprehensive migration dashboard data
        GET /api/migration/rds-to-dynamo/dashboard
        """
        try:
            dashboard_data = migration_service.get_migration_dashboard()

            return create_response(data=dashboard_data, message="Migration dashboard data retrieved successfully")

        except Exception as e:
            logger.error("Error getting migration dashboard: %s", str(e))
            return create_error_response("Failed to get migration dashboard data", 500)

    @staticmethod
    def create_rollback_point(job_id: str):
        """
        Create rollback point before migration
        POST /api/migration/rds-to-dynamo/{job_id}/rollback-point
        """
        try:
            data = request.get_json() or {}
            rollback_options = {
                "backup_location": data.get("backup_location", "s3"),
                "include_data": data.get("include_data", True),
                "include_schema": data.get("include_schema", True),
                "compression": data.get("compression", "gzip"),
            }

            result = migration_service.create_rollback_point(job_id, rollback_options)

            audit_service.log_action(
                action="migration_rollback_point_created",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={
                    "job_id": job_id,
                    "rollback_point_id": result.get("rollback_point_id"),
                    "backup_location": result.get("backup_location"),
                },
            )

            return create_response(data=result, message="Rollback point created successfully")

        except Exception as e:
            logger.error("Error creating rollback point %s: %s", job_id, str(e))
            return create_error_response("Failed to create rollback point", 500)

    @staticmethod
    def process_upload_and_create_job(file, target_system: str, job_name: str):
        """
        Process uploaded file and create migration job
        """
        try:
            # Validate file
            if not file.filename:
                return create_error_response("No file selected", 400)

            if not file.filename.lower().endswith((".csv", ".json", ".sql")):
                return create_error_response("Unsupported file format. Use CSV, JSON, or SQL", 400)

            # Process upload and create job
            result = migration_service.process_upload_and_create_job(file, target_system, job_name)

            # Log audit trail
            audit_service.log_action(
                action="migration_upload_processed",
                resource="migration",
                user=g.current_user.get("username", "system"),
                details={
                    "filename": file.filename,
                    "target_system": target_system,
                    "job_name": job_name,
                    "job_id": result.get("job_id"),
                },
            )

            return create_response(data=result, message="Upload processed and migration job created successfully")

        except Exception as e:
            logger.error("Error processing upload: %s", str(e))
            return create_error_response("Failed to process upload", 500)


# Export controller instance
migration_controller = MigrationController()
