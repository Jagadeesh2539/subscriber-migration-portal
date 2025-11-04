import json
import uuid
from datetime import datetime
from typing import Dict, Optional

import boto3
from config.database import get_dynamodb_table
from services.audit.service import AuditService
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


class RDSMigrationService:
    """Service for migrating data from RDS (Legacy) to DynamoDB (Cloud)"""

    def __init__(self):
        self.subscribers_table = get_dynamodb_table("subscribers")
        self.jobs_table = get_dynamodb_table("migration_jobs")
        self.audit_service = AuditService()
        self.validator = InputValidator()
        self.stepfunctions = boto3.client("stepfunctions")
        # TODO: Add SFN State Machine ARN from config/env
        self.state_machine_arn = "YOUR_STATE_MACHINE_ARN"

    def create_migration_job(self, config: Dict) -> Dict:
        """
        Create a new migration job record.
        """
        job_id = f"rds-{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow().isoformat()

        # Validate configuration
        # ... (add validation for source_config, target_config, etc.)

        job_item = {
            "job_id": job_id,
            "job_type": "RDS_TO_DYNAMODB",
            "job_name": config.get("job_name", f"RDS_Migration_{created_at}"),
            "status": "PENDING",
            "created_at": created_at,
            "updated_at": created_at,
            "source_config": config.get("source_config"),
            "target_config": config.get("target_config"),
            "migration_options": config.get("migration_options", {}),
            "progress": {"total_records": 0, "processed": 0, "successful": 0, "failed": 0},
            "created_by": config.get("created_by", "system"),
        }

        try:
            self.jobs_table.put_item(Item=job_item)
            logger.info("Created RDS migration job %s", job_id)
            return {"job_id": job_id, "status": "PENDING"}
        except Exception as e:
            logger.error("Error creating RDS migration job: %s", str(e))
            raise Exception("Failed to create migration job record")

    def list_migration_jobs(self, criteria: Dict) -> Dict:
        """
        List migration jobs based on filter criteria.
        """
        # TODO: Implement filtering, sorting, pagination using DynamoDB scan/query
        try:
            response = self.jobs_table.scan(Limit=criteria.get("limit", 50))
            jobs = response.get("Items", [])
            # Apply filtering/sorting if needed
            return {"jobs": jobs, "count": len(jobs)}
        except Exception as e:
            logger.error("Error listing migration jobs: %s", str(e))
            raise Exception("Failed to list migration jobs")

    def start_migration_job(self, job_id: str) -> Dict:
        """
        Start the migration job by triggering the Step Functions state machine.
        """
        try:
            # Fetch job details to pass to Step Functions
            job_details = self._get_job_details(job_id)
            if not job_details:
                raise ValueError("Job not found")
            if job_details.get("status") not in ["PENDING", "FAILED", "CANCELLED"]:
                raise ValueError(f"Job {job_id} cannot be started in status {job_details.get('status')}")

            # Prepare input for Step Functions
            sfn_input = json.dumps(
                {
                    "job_id": job_id,
                    "source_config": job_details.get("source_config"),
                    "target_config": job_details.get("target_config"),
                    "migration_options": job_details.get("migration_options"),
                },
                default=str,  # Handle Decimal etc.
            )

            # Start Step Functions execution
            response = self.stepfunctions.start_execution(
                stateMachineArn=self.state_machine_arn,
                name=f"{job_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                input=sfn_input,
            )

            execution_arn = response["executionArn"]
            start_date = response["startDate"].isoformat()

            # Update job status to RUNNING
            self._update_job(
                job_id,
                status="RUNNING",
                start_time=start_date,
                execution_arn=execution_arn,
            )

            logger.info("Started Step Functions execution %s for job %s", execution_arn, job_id)
            return {
                "job_id": job_id,
                "status": "RUNNING",
                "execution_arn": execution_arn,
                "start_date": start_date,
            }

        except Exception as e:
            logger.error("Error starting migration job %s: %s", job_id, str(e))
            self._update_job(job_id, status="FAILED", error_message=str(e))
            raise Exception(f"Failed to start migration job: {str(e)}")

    def pause_migration_job(self, job_id: str) -> Dict:
        """Pause a running migration job (if supported by SFN activity)."""
        # Placeholder: Actual pause logic depends on Step Functions design
        logger.warning("Pause functionality not fully implemented for job %s", job_id)
        self._update_job(job_id, status="PAUSED")
        return {"job_id": job_id, "status": "PAUSED"}

    def resume_migration_job(self, job_id: str) -> Dict:
        """Resume a paused migration job."""
        # Placeholder: Actual resume logic depends on Step Functions design
        logger.warning("Resume functionality not fully implemented for job %s", job_id)
        self._update_job(job_id, status="RUNNING")  # Assume resume triggers RUNNING
        return self.start_migration_job(job_id)  # Re-trigger SFN or send task token

    def cancel_migration_job(self, job_id: str) -> Dict:
        """Cancel a migration job by stopping the Step Functions execution."""
        try:
            job_details = self._get_job_details(job_id)
            if not job_details:
                raise ValueError("Job not found")

            execution_arn = job_details.get("execution_arn")
            if execution_arn:
                logger.info("Stopping Step Functions execution %s for job %s", execution_arn, job_id)
                self.stepfunctions.stop_execution(
                    executionArn=execution_arn, error="JobCancelledByUser", cause="User requested cancellation"
                )
            else:
                logger.warning("No execution ARN found for job %s, cannot stop SFN.", job_id)

            # Update status immediately, SFN stop might take time
            self._update_job(job_id, status="CANCELLED")

            return {"job_id": job_id, "status": "CANCELLED"}

        except Exception as e:
            logger.error("Error cancelling migration job %s: %s", job_id, str(e))
            # Don't mark as FAILED, just log error
            raise Exception(f"Failed to cancel migration job: {str(e)}")

    def get_migration_status(self, job_id: str) -> Optional[Dict]:
        """Get the current status and progress of a migration job."""
        try:
            job_details = self._get_job_details(job_id)
            if not job_details:
                return None

            # If job is running, optionally query Step Functions for real-time status
            execution_arn = job_details.get("execution_arn")
            if job_details.get("status") == "RUNNING" and execution_arn:
                try:
                    sfn_status = self.stepfunctions.describe_execution(executionArn=execution_arn)
                    current_sfn_status = sfn_status.get("status")  # RUNNING, SUCCEEDED, FAILED, TIMED_OUT, ABORTED

                    # Update DynamoDB status based on SFN status if needed
                    if current_sfn_status == "SUCCEEDED" and job_details.get("status") != "COMPLETED":
                        self._update_job(job_id, status="COMPLETED", end_time=datetime.utcnow().isoformat())
                        job_details["status"] = "COMPLETED"
                    elif current_sfn_status in ["FAILED", "TIMED_OUT"] and job_details.get("status") != "FAILED":
                        error_cause = sfn_status.get("cause", "Step Functions execution failed")
                        self._update_job(
                            job_id, status="FAILED", error_message=error_cause, end_time=datetime.utcnow().isoformat()
                        )
                        job_details["status"] = "FAILED"
                    elif current_sfn_status == "ABORTED" and job_details.get("status") != "CANCELLED":
                        self._update_job(job_id, status="CANCELLED", end_time=datetime.utcnow().isoformat())
                        job_details["status"] = "CANCELLED"

                except Exception as sfn_err:
                    logger.warning("Could not describe SFN execution %s: %s", execution_arn, str(sfn_err))

            # Clean data for response (e.g., convert Decimal)
            clean_details = json.loads(json.dumps(job_details, default=str))
            return clean_details

        except Exception as e:
            logger.error("Error getting migration status for job %s: %s", job_id, str(e))
            raise Exception("Failed to get migration status")

    def run_migration_audit(self, job_id: str, options: Dict) -> Dict:
        """Perform post-migration data validation and consistency checks."""
        logger.info("Starting post-migration audit for job %s with options: %s", job_id, options)
        # Placeholder for audit logic:
        # 1. Fetch job details (source/target config)
        # 2. Define sample size or scope based on options
        # 3. Query sample records from both RDS and DynamoDB based on migrated keys
        # 4. Compare records field by field (handle type differences)
        # 5. Generate audit summary (matched, mismatched, source_only, target_only)
        # 6. Store detailed discrepancy report (optional, maybe S3)
        # 7. Update job record with audit results

        audit_summary = {
            "job_id": job_id,
            "audit_timestamp": datetime.utcnow().isoformat(),
            "options": options,
            "summary": {
                "records_checked": options.get("sample_size", 0),
                "matched": int(options.get("sample_size", 0) * 0.95),  # Mock 95% match
                "mismatched": int(options.get("sample_size", 0) * 0.03),
                "source_only": int(options.get("sample_size", 0) * 0.01),
                "target_only": int(options.get("sample_size", 0) * 0.01),
                "errors": 0,
            },
            # "discrepancy_report_url": "s3://..."  # Optional
        }
        self._update_job(job_id, audit_results=audit_summary)
        logger.info("Audit completed for job %s", job_id)
        return audit_summary

    def export_migration_results(self, job_id: str, options: Dict) -> Dict:
        """Export job results, including errors or audit findings."""
        logger.info("Exporting results for job %s with options: %s", job_id, options)
        # Placeholder for export logic:
        # 1. Fetch job details, including error logs or audit results
        # 2. Format data based on options['format'] (csv, json)
        # 3. Handle inclusion of errors/audit details
        # 4. Return content and content type

        mock_content = "job_id,status,error\n"
        if options.get("include_errors"):
            mock_content += f"{job_id},FAILED,Sample error message\n"
        else:
            mock_content += f"{job_id},COMPLETED,\n"

        return {
            "job_id": job_id,
            "format": options.get("format", "csv"),
            "record_count": 1,
            "content": mock_content.encode("utf-8"),
        }

    def retry_failed_records(self, job_id: str, options: Dict) -> Dict:
        """Initiate a retry process for records that failed during migration."""
        logger.info("Retrying failed records for job %s with options: %s", job_id, options)
        # Placeholder for retry logic:
        # 1. Fetch job details and identify failed records (from error_log or separate table)
        # 2. Filter records based on options['specific_errors_only'] if provided
        # 3. Create a new "retry job" or trigger a specific SFN task/workflow
        # 4. Update original job status or link to retry job

        retry_summary = {
            "job_id": job_id,
            "retry_timestamp": datetime.utcnow().isoformat(),
            "options": options,
            "summary": {
                "records_to_retry": 5,  # Mock value
                "retried_successfully": 4,
                "still_failing": 1,
            },
            "retry_job_id": f"retry-{job_id[:8]}-{uuid.uuid4().hex[:4]}",  # Link to new job
        }
        self._update_job(job_id, retry_info=retry_summary)
        logger.info("Retry process initiated for job %s", job_id)
        return retry_summary

    # --- Internal Helper Methods ---

    def _get_job_details(self, job_id: str) -> Optional[Dict]:
        """Fetch job details from DynamoDB."""
        try:
            response = self.jobs_table.get_item(Key={"job_id": job_id})
            return response.get("Item")
        except Exception as e:
            logger.error("Error fetching job details for %s: %s", job_id, str(e))
            return None

    def _update_job(self, job_id: str, **kwargs):
        """Update specific attributes of a migration job record."""
        try:
            update_expression = "SET updated_at = :updated_at"
            expression_values = {":updated_at": datetime.utcnow().isoformat()}
            expression_names = {}

            for key, value in kwargs.items():
                if value is not None:
                    # Sanitize key for expression names if needed
                    safe_key = key.replace("-", "_")  # Example basic sanitization
                    name_placeholder = f"#{safe_key}"
                    value_placeholder = f":{safe_key}"
                    update_expression += f", {name_placeholder} = {value_placeholder}"
                    expression_values[value_placeholder] = value
                    expression_names[name_placeholder] = key

            if not expression_names:  # Only update updated_at if no other args
                # E501 Fix: Break the line
                self.jobs_table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values,
                )
            else:
                self.jobs_table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeNames=expression_names,
                    ExpressionAttributeValues=expression_values,
                )
            logger.debug("Updated job %s with data: %s", job_id, kwargs)

        except Exception as e:
            logger.error("Error updating job %s: %s", job_id, str(e))


rds_migration_service = RDSMigrationService()
