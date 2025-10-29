#!/usr/bin/env python3
"""
CSV Migration Service - Handles CSV file upload, validation, and processing
Supports batch operations with detailed reporting and error handling
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from config.database import get_dynamodb_table, get_legacy_db_connection
from services.audit.service import AuditService
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


@dataclass
class MigrationRecord:
    """Single migration record with processing results"""

    identifier: str
    identifier_type: str  # imsi, msisdn, uid
    status: str  # SUCCESS, ALREADY_PRESENT, NOT_FOUND, FAILED
    reason: str
    legacy_data: Optional[Dict] = None
    cloud_data: Optional[Dict] = None
    error_details: Optional[str] = None


@dataclass
class MigrationSummary:
    """Migration batch summary report"""

    migration_id: str
    total_processed: int
    migrated_successfully: int
    already_present: int
    not_found_in_legacy: int
    failed: int
    identifier_type: str
    cloud_migration_enabled: bool
    started_at: str
    completed_at: str
    records: List[MigrationRecord]


class CSVMigrationService:
    """Service for CSV-based subscriber migration with identifier detection"""

    def __init__(self):
        self.dynamodb_table = get_dynamodb_table("SUBSCRIBER_TABLE_NAME")
        self.audit_service = AuditService()
        self.validator = InputValidator()

        # Migration tracking table
        self.migration_table = get_dynamodb_table("MIGRATION_JOBS_TABLE_NAME")

    def process_csv_migration(
        self, csv_file, migration_id: str, cloud_migration_enabled: bool = True
    ) -> MigrationSummary:
        """
        Process CSV file for migration with automatic identifier detection

        Args:
            csv_file: Uploaded CSV file
            migration_id: Mandatory Migration ID for tracking
            cloud_migration_enabled: If False, only logs without cloud migration

        Returns:
            MigrationSummary with detailed results
        """
        started_at = datetime.utcnow().isoformat()

        try:
            # Read and parse CSV
            csv_content = csv_file.read().decode("utf-8")
            csv_reader = csv.DictReader(io.StringIO(csv_content))

            # Get CSV headers for identifier detection
            headers = csv_reader.fieldnames
            if not headers:
                raise ValueError("CSV file must have headers")

            # Detect identifier type from first line (header)
            identifier_type = self._detect_identifier_type(headers)
            if not identifier_type:
                raise ValueError(f"No valid identifier found in headers: {headers}. Expected: imsi, msisdn, or uid")

            logger.info(f"Migration {migration_id}: Detected identifier type '{identifier_type}' from CSV headers")

            # Process each record
            records = []
            stats = {
                "total_processed": 0,
                "migrated_successfully": 0,
                "already_present": 0,
                "not_found_in_legacy": 0,
                "failed": 0,
            }

            for row_num, row in enumerate(csv_reader, start=1):
                try:
                    identifier_value = row.get(identifier_type, "").strip()
                    if not identifier_value:
                        # Skip empty rows
                        continue

                    # Process this subscriber
                    migration_record = self._process_single_subscriber(
                        identifier_value, identifier_type, migration_id, cloud_migration_enabled, row_num
                    )

                    records.append(migration_record)
                    stats["total_processed"] += 1

                    # Update counters based on result
                    if migration_record.status == "SUCCESS":
                        stats["migrated_successfully"] += 1
                    elif migration_record.status == "ALREADY_PRESENT":
                        stats["already_present"] += 1
                    elif migration_record.status == "NOT_FOUND":
                        stats["not_found_in_legacy"] += 1
                    else:
                        stats["failed"] += 1

                except Exception as e:
                    stats["failed"] += 1
                    stats["total_processed"] += 1

                    error_record = MigrationRecord(
                        identifier=identifier_value if "identifier_value" in locals() else f"Row_{row_num}",
                        identifier_type=identifier_type,
                        status="FAILED",
                        reason=f"Processing error: {str(e)}",
                        error_details=str(e),
                    )
                    records.append(error_record)

                    logger.error(f"Migration {migration_id} - Row {row_num} failed: {str(e)}")

            completed_at = datetime.utcnow().isoformat()

            # Create summary
            summary = MigrationSummary(
                migration_id=migration_id,
                total_processed=stats["total_processed"],
                migrated_successfully=stats["migrated_successfully"],
                already_present=stats["already_present"],
                not_found_in_legacy=stats["not_found_in_legacy"],
                failed=stats["failed"],
                identifier_type=identifier_type,
                cloud_migration_enabled=cloud_migration_enabled,
                started_at=started_at,
                completed_at=completed_at,
                records=records,
            )

            # Store migration summary in DynamoDB
            self._store_migration_summary(summary)

            # Log audit trail
            self.audit_service.log_action(
                action="csv_migration_completed",
                resource="migration",
                user="system",
                details={
                    "migration_id": migration_id,
                    "identifier_type": identifier_type,
                    "cloud_migration_enabled": cloud_migration_enabled,
                    "total_processed": stats["total_processed"],
                    "success_rate": (
                        (stats["migrated_successfully"] / stats["total_processed"] * 100)
                        if stats["total_processed"] > 0
                        else 0
                    ),
                },
            )

            logger.info(
                f"Migration {migration_id} completed: {stats['migrated_successfully']} successful, {stats['failed']} failed"
            )

            return summary

        except Exception as e:
            logger.error(f"CSV migration {migration_id} failed: {str(e)}")
            raise ValueError(f"Failed to process CSV migration: {str(e)}")

    def _detect_identifier_type(self, headers: List[str]) -> Optional[str]:
        """
        Automatic Identifier Detection from CSV headers
        Reads first line (header) to detect identifier type
        """
        # Convert headers to lowercase for case-insensitive detection
        lower_headers = [h.lower().strip() for h in headers]

        # Check for identifier types in priority order
        if "imsi" in lower_headers:
            return "imsi"
        elif "uid" in lower_headers:
            return "uid"
        elif "msisdn" in lower_headers:
            return "msisdn"

        # Check for variations
        for header in lower_headers:
            if "imsi" in header:
                return "imsi"
            elif "uid" in header or "user" in header:
                return "uid"
            elif "msisdn" in header or "phone" in header or "mobile" in header:
                return "msisdn"

        return None

    def _process_single_subscriber(
        self, identifier: str, identifier_type: str, migration_id: str, cloud_migration_enabled: bool, row_num: int
    ) -> MigrationRecord:
        """
        Process single subscriber according to migration logic:
        1. Check Legacy System (RDS)
        2. Check Cloud System
        3. Handle Missing Records
        4. Error Handling
        """
        try:
            # Step 1: Check Legacy System (RDS)
            legacy_subscriber = self._fetch_from_legacy(identifier, identifier_type)

            if not legacy_subscriber:
                # Handle Missing Records
                self._log_migration_event(
                    migration_id, identifier, "NOT_FOUND", f"Subscriber not found in legacy system", row_num
                )
                return MigrationRecord(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    status="NOT_FOUND",
                    reason="Not found in legacy system",
                )

            # Step 2: Check Cloud System
            cloud_subscriber = self._fetch_from_cloud(legacy_subscriber["uid"])

            if cloud_subscriber:
                # Subscriber already exists in cloud
                self._log_migration_event(
                    migration_id, identifier, "ALREADY_PRESENT", "Already present in cloud", row_num
                )
                return MigrationRecord(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    status="ALREADY_PRESENT",
                    reason="Already present in cloud",
                    legacy_data=legacy_subscriber,
                    cloud_data=cloud_subscriber,
                )

            # Step 3: Migrate from legacy to cloud (if enabled)
            if not cloud_migration_enabled:
                self._log_migration_event(
                    migration_id, identifier, "SIMULATION", "Cloud migration disabled for this Migration ID", row_num
                )
                return MigrationRecord(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    status="SIMULATION",
                    reason="Cloud migration disabled for simulation/testing",
                    legacy_data=legacy_subscriber,
                )

            # Perform migration
            migration_result = self._migrate_to_cloud(legacy_subscriber)

            if migration_result["success"]:
                self._log_migration_event(
                    migration_id, identifier, "SUCCESS", "Migrated successfully to cloud", row_num
                )
                return MigrationRecord(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    status="SUCCESS",
                    reason="Migrated successfully to cloud",
                    legacy_data=legacy_subscriber,
                    cloud_data=migration_result["cloud_data"],
                )
            else:
                # Migration failed
                self._log_migration_event(
                    migration_id, identifier, "FAILED", f'Migration failed: {migration_result["error"]}', row_num
                )
                return MigrationRecord(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    status="FAILED",
                    reason=f'Migration failed: {migration_result["error"]}',
                    legacy_data=legacy_subscriber,
                    error_details=migration_result["error"],
                )

        except Exception as e:
            # Error Handling - Any DB/network/validation error
            error_msg = f"Processing error: {str(e)}"
            self._log_migration_event(migration_id, identifier, "FAILED", error_msg, row_num)

            return MigrationRecord(
                identifier=identifier,
                identifier_type=identifier_type,
                status="FAILED",
                reason=error_msg,
                error_details=str(e),
            )

    def _fetch_from_legacy(self, identifier: str, identifier_type: str) -> Optional[Dict[str, Any]]:
        """Fetch full subscriber data from legacy RDS using provided identifier"""
        connection = get_legacy_db_connection()
        if not connection:
            raise RuntimeError("Cannot connect to legacy database")

        try:
            with connection.cursor() as cursor:
                # Build query based on identifier type
                if identifier_type == "imsi":
                    query = "SELECT * FROM subscribers WHERE imsi = %s AND status != 'DELETED'"
                elif identifier_type == "uid":
                    query = "SELECT * FROM subscribers WHERE uid = %s AND status != 'DELETED'"
                elif identifier_type == "msisdn":
                    query = "SELECT * FROM subscribers WHERE msisdn = %s AND status != 'DELETED'"
                else:
                    raise ValueError(f"Unsupported identifier type: {identifier_type}")

                cursor.execute(query, (identifier,))
                result = cursor.fetchone()

                if result:
                    # Convert datetime objects to ISO strings
                    for key, value in result.items():
                        if hasattr(value, "isoformat"):
                            result[key] = value.isoformat()

                return result

        except Exception as e:
            logger.error(f"Error fetching from legacy DB: {str(e)}")
            raise
        finally:
            connection.close()

    def _fetch_from_cloud(self, uid: str) -> Optional[Dict[str, Any]]:
        """Check if subscriber exists in cloud system"""
        try:
            response = self.dynamodb_table.get_item(Key={"subscriberId": uid})
            return response.get("Item")
        except Exception as e:
            logger.error(f"Error fetching from cloud DB: {str(e)}")
            raise

    def _migrate_to_cloud(self, legacy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate subscriber from legacy to cloud"""
        try:
            # Transform legacy data to cloud format
            cloud_item = {
                "subscriberId": legacy_data["uid"],
                "uid": legacy_data["uid"],
                "imsi": legacy_data.get("imsi", ""),
                "msisdn": legacy_data.get("msisdn", ""),
                "status": legacy_data.get("status", "ACTIVE"),
                "created_at": legacy_data.get("created_at", datetime.utcnow().isoformat()),
                "updated_at": datetime.utcnow().isoformat(),
                "migrated_from": "legacy_rds",
                "migrated_at": datetime.utcnow().isoformat(),
                "apn": legacy_data.get("apn", ""),
                "service_profile": legacy_data.get("service_profile", ""),
                "roaming_allowed": legacy_data.get("roaming_allowed", True),
            }

            # Handle optional numeric fields
            if legacy_data.get("data_limit"):
                cloud_item["data_limit"] = Decimal(str(legacy_data["data_limit"]))

            # Store in DynamoDB
            self.dynamodb_table.put_item(Item=cloud_item)

            return {"success": True, "cloud_data": cloud_item}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _log_migration_event(self, migration_id: str, identifier: str, status: str, reason: str, row_num: int):
        """Log individual migration event for audit trail"""
        try:
            log_entry = {
                "id": f"{migration_id}_{row_num}_{identifier}_{int(datetime.utcnow().timestamp())}",
                "migration_id": migration_id,
                "identifier": identifier,
                "row_number": row_num,
                "status": status,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
                "ttl": int((datetime.utcnow() + timedelta(days=30)).timestamp()),  # 30-day retention
            }

            # Store in audit logs table
            audit_table = get_dynamodb_table("AUDIT_LOG_TABLE_NAME")
            audit_table.put_item(Item=log_entry)

        except Exception as e:
            logger.error(f"Failed to log migration event: {str(e)}")

    def _store_migration_summary(self, summary: MigrationSummary):
        """Store migration summary in DynamoDB for tracking"""
        try:
            # Convert summary to DynamoDB format
            item = {
                "id": summary.migration_id,
                "migration_type": "csv_migration",
                "status": "COMPLETED",
                "identifier_type": summary.identifier_type,
                "cloud_migration_enabled": summary.cloud_migration_enabled,
                "started_at": summary.started_at,
                "completed_at": summary.completed_at,
                "stats": {
                    "total_processed": Decimal(str(summary.total_processed)),
                    "migrated_successfully": Decimal(str(summary.migrated_successfully)),
                    "already_present": Decimal(str(summary.already_present)),
                    "not_found_in_legacy": Decimal(str(summary.not_found_in_legacy)),
                    "failed": Decimal(str(summary.failed)),
                },
                "success_rate": Decimal(
                    str(
                        round(
                            (
                                (summary.migrated_successfully / summary.total_processed * 100)
                                if summary.total_processed > 0
                                else 0
                            ),
                            2,
                        )
                    )
                ),
                "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),  # 90-day retention
            }

            self.migration_table.put_item(Item=item)

            logger.info(f"Migration summary stored for {summary.migration_id}")

        except Exception as e:
            logger.error(f"Failed to store migration summary: {str(e)}")

    def get_migration_summary(self, migration_id: str) -> Optional[Dict[str, Any]]:
        """Get stored migration summary by Migration ID"""
        try:
            response = self.migration_table.get_item(Key={"id": migration_id})
            return response.get("Item")
        except Exception as e:
            logger.error(f"Error getting migration summary {migration_id}: {str(e)}")
            return None

    def generate_migration_report(self, summary: MigrationSummary, format_type: str = "csv") -> str:
        """Generate downloadable migration report"""
        if format_type == "csv":
            return self._generate_csv_report(summary)
        else:
            return self._generate_json_report(summary)

    def _generate_csv_report(self, summary: MigrationSummary) -> str:
        """Generate CSV format migration report"""
        output = io.StringIO()

        # Write summary header
        output.write(f"Migration Report - {summary.migration_id}\n")
        output.write(f"Generated: {datetime.utcnow().isoformat()}\n")
        output.write(f"Identifier Type: {summary.identifier_type}\n")
        output.write(f"Cloud Migration Enabled: {summary.cloud_migration_enabled}\n")
        output.write("\n")

        # Write summary table
        output.write("SUMMARY\n")
        output.write("Metric,Count\n")
        output.write(f"Total Processed,{summary.total_processed}\n")
        output.write(f"Migrated Successfully,{summary.migrated_successfully}\n")
        output.write(f"Already Present,{summary.already_present}\n")
        output.write(f"Not Found in Legacy,{summary.not_found_in_legacy}\n")
        output.write(f"Failed,{summary.failed}\n")
        output.write("\n")

        # Write detailed records
        output.write("DETAILED RESULTS\n")
        output.write("Identifier,Type,Status,Reason,Error Details\n")

        for record in summary.records:
            error_details = record.error_details.replace(",", ";") if record.error_details else ""
            reason = record.reason.replace(",", ";") if record.reason else ""

            output.write(f"{record.identifier},{record.identifier_type},{record.status},{reason},{error_details}\n")

        return output.getvalue()

    def _generate_json_report(self, summary: MigrationSummary) -> str:
        """Generate JSON format migration report"""
        report = {
            "migration_id": summary.migration_id,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "identifier_type": summary.identifier_type,
                "cloud_migration_enabled": summary.cloud_migration_enabled,
                "timing": {"started_at": summary.started_at, "completed_at": summary.completed_at},
                "metrics": {
                    "total_processed": summary.total_processed,
                    "migrated_successfully": summary.migrated_successfully,
                    "already_present": summary.already_present,
                    "not_found_in_legacy": summary.not_found_in_legacy,
                    "failed": summary.failed,
                },
            },
            "detailed_results": [
                {
                    "identifier": record.identifier,
                    "identifier_type": record.identifier_type,
                    "status": record.status,
                    "reason": record.reason,
                    "error_details": record.error_details,
                    "legacy_data_present": record.legacy_data is not None,
                    "cloud_data_present": record.cloud_data is not None,
                }
                for record in summary.records
            ],
        }

        return json.dumps(report, indent=2)

    def list_migration_summaries(self, limit: int = 20, status: str = None) -> List[Dict[str, Any]]:
        """List migration summaries with filtering"""
        try:
            scan_kwargs = {
                "FilterExpression": "migration_type = :type",
                "ExpressionAttributeValues": {":type": "csv_migration"},
                "Limit": limit,
            }

            if status:
                scan_kwargs["FilterExpression"] += " AND #status = :status"
                scan_kwargs["ExpressionAttributeNames"] = {"#status": "status"}
                scan_kwargs["ExpressionAttributeValues"][":status"] = status

            response = self.migration_table.scan(**scan_kwargs)
            items = response.get("Items", [])

            # Convert Decimal values for JSON serialization
            summaries = []
            for item in items:
                clean_item = {}
                for key, value in item.items():
                    if isinstance(value, Decimal):
                        clean_item[key] = float(value)
                    elif isinstance(value, dict):
                        clean_item[key] = {k: float(v) if isinstance(v, Decimal) else v for k, v in value.items()}
                    else:
                        clean_item[key] = value
                summaries.append(clean_item)

            return summaries

        except Exception as e:
            logger.error(f"Error listing migration summaries: {str(e)}")
            return []


# Export service instance
csv_migration_service = CSVMigrationService()
