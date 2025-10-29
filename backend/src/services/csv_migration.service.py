# backend/src/services/csv_migration.service.py

#!/usr/bin/env python3
"""
CSV Migration Service - Handles bulk data migration from CSV files
Supports: Legacy -> Cloud, Cloud -> Legacy, External -> Cloud
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from config.database import get_dynamodb_table
from services.audit.service import AuditService
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


@dataclass
class MigrationJob:
    """Represents a migration job initiated via CSV upload"""

    job_id: str
    filename: str
    target_system: str
    created_by: str
    created_at: str
    status: str = "PENDING"
    total_records: int = 0
    processed_records: int = 0
    successful_records: int = 0
    failed_records: int = 0
    error_log: List[Dict] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class CSVMigrationService:
    """Service to handle CSV-based migration operations"""

    def __init__(self):
        self.jobs_table = get_dynamodb_table("migration_jobs")
        self.subscribers_table = get_dynamodb_table("subscribers")
        self.audit_service = AuditService()
        self.validator = InputValidator()

    def create_csv_migration_job(self, filename: str, target_system: str, created_by: str) -> str:
        """
        Create a new migration job record in DynamoDB.
        """
        job_id = f"csv-{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow().isoformat()

        job_item = {
            "job_id": job_id,
            "job_type": "CSV_UPLOAD",
            "filename": filename,
            "target_system": target_system,
            "created_by": created_by,
            "created_at": created_at,
            "status": "PENDING_UPLOAD",
            "total_records": 0,
            "processed_records": 0,
            "successful_records": 0,
            "failed_records": 0,
        }

        try:
            self.jobs_table.put_item(Item=job_item)
            logger.info("Created CSV migration job %s for file %s", job_id, filename)

            # Log audit trail
            job_details = {
                "job_id": job_id,
                "filename": filename,
                "target_system": target_system,
            }
            self.audit_service.log_action(
                action="csv_migration_job_created",
                resource="migration",
                user=created_by,
                details=job_details,
            )

            return job_id

        except Exception as e:
            logger.error("Error creating CSV migration job: %s", str(e))
            raise Exception("Failed to create migration job record")

    def process_csv_file(self, job_id: str, csv_content: str):
        """
        Process the uploaded CSV file and migrate data.
        """
        try:
            logger.info("Starting CSV processing for job %s", job_id)

            # Update job status to RUNNING
            self._update_job_status(job_id, "RUNNING", start_time=datetime.utcnow().isoformat())

            # Read CSV content
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(csv_reader)
            total_records = len(rows)

            # Update total records
            self._update_job_progress(job_id, total_records=total_records)

            processed = 0
            successful = 0
            failed = 0
            error_log = []

            for i, row in enumerate(rows):
                try:
                    # Validate row data
                    validated_data = self._validate_and_sanitize_row(row)

                    # TODO: Implement actual migration logic based on target_system
                    # Example: Assuming target is Cloud (DynamoDB)
                    self.subscribers_table.put_item(Item=validated_data)

                    successful += 1

                except ValidationError as ve:
                    failed += 1
                    error_log.append(
                        {
                            "row_number": i + 1,
                            "error": str(ve),
                            "data": row,
                        }
                    )
                except Exception as row_error:
                    failed += 1
                    logger.error(
                        "Error processing row %d for job %s: %s",
                        i + 1,
                        job_id,
                        str(row_error),
                    )
                    error_log.append(
                        {
                            "row_number": i + 1,
                            "error": f"Internal processing error: {str(row_error)}",
                            "data": row,
                        }
                    )
                finally:
                    processed += 1
                    # Update progress periodically
                    if processed % 50 == 0 or processed == total_records:
                        self._update_job_progress(
                            job_id,
                            processed_records=processed,
                            successful_records=successful,
                            failed_records=failed,
                        )

            # Finalize job status
            final_status = "COMPLETED" if failed == 0 else "COMPLETED_WITH_ERRORS"
            self._update_job_status(
                job_id,
                final_status,
                end_time=datetime.utcnow().isoformat(),
                error_log=error_log,
            )

            logger.info(
                "CSV processing completed for job %s. Total: %d, Success: %d, Failed: %d",
                job_id,
                total_records,
                successful,
                failed,
            )

            # Log audit trail for completion
            completion_details = {
                "job_id": job_id,
                "status": final_status,
                "total_records": total_records,
                "successful_records": successful,
                "failed_records": failed,
            }
            self.audit_service.log_action(
                action="csv_migration_job_completed",
                resource="migration",
                user="system",
                details=completion_details,
            )

        except Exception as e:
            logger.error("Fatal error during CSV processing for job %s: %s", job_id, str(e))
            try:
                self._update_job_status(
                    job_id,
                    "FAILED",
                    end_time=datetime.utcnow().isoformat(),
                    error_log=[{"error": f"Fatal processing error: {str(e)}"}],
                )
                # Log audit trail for failure
                failure_details = {"job_id": job_id, "error": str(e)}
                self.audit_service.log_action(
                    action="csv_migration_job_failed",
                    resource="migration",
                    user="system",
                    details=failure_details,
                )
            except Exception as update_err:
                logger.error("Failed to update job status to FAILED for job %s: %s", job_id, str(update_err))
            raise Exception("CSV processing failed")

    def _validate_and_sanitize_row(self, row: Dict) -> Dict:
        """
        Validate and sanitize a single row from the CSV.
        """
        # Required fields check
        required = ["uid", "imsi"]
        missing = [field for field in required if not row.get(field)]
        if missing:
            raise ValidationError(f"Missing required fields: {', '.join(missing)}")

        # Sanitize and validate types
        sanitized = {}
        sanitized["uid"] = self.validator.sanitize_string(row["uid"], max_length=50, pattern="uid")
        sanitized["imsi"] = self.validator.sanitize_string(row["imsi"], max_length=15, pattern="imsi")
        sanitized["msisdn"] = self.validator.sanitize_string(row.get("msisdn", ""), max_length=15, pattern="msisdn")

        # Sanitize optional fields with defaults
        sanitized["status"] = self.validator.sanitize_string(
            row.get("status", "ACTIVE"), max_length=20, pattern="status"
        ).upper()
        sanitized["plan_type"] = self.validator.sanitize_string(row.get("plan_type", "STANDARD_PREPAID"), max_length=50)
        sanitized["network_type"] = self.validator.sanitize_string(row.get("network_type", "4G_LTE"), max_length=50)
        sanitized["service_class"] = self.validator.sanitize_string(
            row.get("service_class", "CONSUMER_SILVER"), max_length=50
        )

        # Handle numeric and boolean fields
        try:
            sanitized["data_limit_mb"] = int(row.get("data_limit_mb", 1000))
        except (ValueError, TypeError):
            sanitized["data_limit_mb"] = 1000

        sanitized["gprs_enabled"] = str(row.get("gprs_enabled", "true")).lower() == "true"
        sanitized["volte_enabled"] = str(row.get("volte_enabled", "false")).lower() == "true"

        # Add timestamps
        sanitized["created_at"] = datetime.utcnow().isoformat()
        sanitized["updated_at"] = datetime.utcnow().isoformat()

        # Map to DynamoDB primary key
        sanitized["subscriberId"] = sanitized["uid"]

        return sanitized

    def _update_job_status(self, job_id: str, status: str, **kwargs):
        """
        Update the status and other attributes of a migration job.
        """
        try:
            update_expression = "SET #status = :status, updated_at = :updated_at"
            expression_values = {
                ":status": status,
                ":updated_at": datetime.utcnow().isoformat(),
            }
            expression_names = {"#status": "status"}

            for key, value in kwargs.items():
                if value is not None:
                    placeholder = f":{key}"
                    update_expression += f", #{key} = {placeholder}"
                    expression_values[placeholder] = value
                    expression_names[f"#{key}"] = key

            self.jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )
            logger.debug("Updated job %s status to %s", job_id, status)

        except Exception as e:
            logger.error("Error updating job status for %s: %s", job_id, str(e))
            # Don't re-raise, as the main process might still need to complete

    def _update_job_progress(self, job_id: str, **kwargs):
        """
        Update the progress counters for a migration job.
        Uses UpdateItem with Add action for atomic increments.
        """
        try:
            update_expression = "SET updated_at = :updated_at"
            expression_values = {":updated_at": datetime.utcnow().isoformat()}
            expression_names = {}

            # Handle atomic increments/decrements if needed, otherwise SET
            set_actions = []
            add_actions = []

            for key, value in kwargs.items():
                if value is not None:
                    placeholder = f":{key}"
                    attr_name_placeholder = f"#{key}"
                    expression_names[attr_name_placeholder] = key

                    # Determine if it's a counter to ADD or a value to SET
                    if key in [
                        "processed_records",
                        "successful_records",
                        "failed_records",
                    ]:
                        # Use ADD for counters if value represents an increment
                        # If the value is the absolute count, use SET
                        # Assuming kwargs provides absolute counts here based on previous usage
                        set_actions.append(f"{attr_name_placeholder} = {placeholder}")
                        expression_values[placeholder] = int(value)
                    elif key == "total_records":
                        set_actions.append(f"{attr_name_placeholder} = {placeholder}")
                        expression_values[placeholder] = int(value)
                    else:
                        # For other fields like error_log, start_time, end_time - use SET
                        set_actions.append(f"{attr_name_placeholder} = {placeholder}")
                        expression_values[placeholder] = value

            if set_actions:
                update_expression += ", " + ", ".join(set_actions)

            # If ADD actions were used, append them
            # if add_actions:
            #     update_expression += " ADD " + ", ".join(add_actions)

            self.jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )

        except Exception as e:
            logger.error("Error updating job progress for %s: %s", job_id, str(e))


# Instantiate service
csv_migration_service = CSVMigrationService()
