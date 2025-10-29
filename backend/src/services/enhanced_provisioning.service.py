#!/usr/bin/env python3
"""
Enhanced Provisioning Service - Single Source of Truth
Consolidated logic for Legacy, Cloud, and Dual Provisioning modes
Handles complex subscriber data structures and validation
"""

# Removed unused json, logging imports
from dataclasses import asdict  # Added for F821 Fix
from datetime import datetime
from decimal import Decimal
# Removed unused Any, Union; Added Optional for F821 Fix
from typing import Dict, Optional

from config.database import get_dynamodb_table, get_legacy_db_connection
from models.subscriber.model import BarringControls, SubscriberData
from services.audit.service import AuditService
from services.provisioning.service import ProvisioningMode, ProvisioningResult
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


class EnhancedProvisioningService:
    """Service handling subscriber provisioning across different modes."""

    def __init__(self):
        self.subscribers_table = get_dynamodb_table("subscribers")
        self.audit_service = AuditService()
        self.validator = InputValidator()

    def provision_subscriber(
        self,
        mode: ProvisioningMode,
        data: Dict,
        operation: str = "CREATE",
        created_by: str = "system",
    ) -> ProvisioningResult:
        """
        Provision a subscriber based on the selected mode and operation.
        """
        start_time = datetime.utcnow()
        result = ProvisioningResult(success=False, mode=mode, operation=operation)
        # F821 Fix: Added Optional import
        subscriber_data: Optional[SubscriberData] = None

        try:
            # 1. Validate and Transform Input Data
            validated_data = self._validate_and_transform(data)
            subscriber_data = SubscriberData(**validated_data)
            result.uid = subscriber_data.uid

            logger.info(
                "Starting provisioning operation '%s' for UID '%s' in mode '%s'",
                operation,
                subscriber_data.uid,
                mode.name,
            )

            # 2. Perform Operation based on Mode
            if mode == ProvisioningMode.LEGACY:
                result = self._provision_legacy(subscriber_data, operation)
            elif mode == ProvisioningMode.CLOUD:
                result = self._provision_cloud(subscriber_data, operation)
            elif mode == ProvisioningMode.DUAL_PROV:
                result = self._provision_dual(subscriber_data, operation)
            else:
                raise ValueError(f"Unsupported provisioning mode: {mode}")

            result.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result.timestamp = start_time.isoformat()

            # 3. Log Audit Trail
            audit_details = {
                "uid": result.uid,
                "mode": mode.name,
                "operation": operation,
                "status": "SUCCESS" if result.success else "FAILED",
                "duration_ms": result.duration_ms,
            }
            if result.message:
                audit_details["message"] = result.message
            if result.legacy_status:
                audit_details["legacy_status"] = result.legacy_status
            if result.cloud_status:
                audit_details["cloud_status"] = result.cloud_status

            self.audit_service.log_action(
                action=f"provision_{operation.lower()}",
                resource="subscriber",
                user=created_by,
                details=audit_details,
            )

            logger.info(
                "Provisioning '%s' for UID '%s' completed. Success: %s. Duration: %dms",
                operation,
                result.uid,
                result.success,
                result.duration_ms,
            )
            return result

        except Exception as e:
            logger.error(
                "Provisioning error for UID '%s' (Op: %s, Mode: %s): %s",
                data.get("uid", "UNKNOWN"),
                operation,
                mode.name,
                str(e),
            )
            result.success = False
            result.message = f"Provisioning failed: {str(e)}"
            result.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result.timestamp = start_time.isoformat()

            # Log audit trail for failure
            self.audit_service.log_action(
                action=f"provision_{operation.lower()}_failed",
                resource="subscriber",
                user=created_by,
                details={
                    "uid": data.get("uid", "UNKNOWN"),
                    "mode": mode.name,
                    "operation": operation,
                    "error": str(e),
                    "duration_ms": result.duration_ms,
                },
            )
            return result

    def _provision_legacy(self, data: SubscriberData, operation: str) -> ProvisioningResult:
        """Handle provisioning only in the legacy system."""
        result = ProvisioningResult(
            success=False, mode=ProvisioningMode.LEGACY, operation=operation, uid=data.uid
        )
        try:
            with get_legacy_db_connection() as conn:
                with conn.cursor() as cursor:
                    if operation == "CREATE":
                        # Convert dataclass to dict, handle potential None values
                        # F821 Fix: Added import for asdict
                        item_dict = {
                            k: v for k, v in asdict(data).items() if v is not None
                        }
                        # TODO: Adapt SQL INSERT to match SubscriberData fields
                        sql = "INSERT INTO subscribers_enhanced (uid, imsi, msisdn, status, ...) VALUES (%s, %s, ...)"
                        cursor.execute(sql, (item_dict["uid"], item_dict["imsi"], ...))
                        result.legacy_status = "CREATED"
                    elif operation == "UPDATE":
                        # TODO: Adapt SQL UPDATE
                        sql = "UPDATE subscribers_enhanced SET status=%s, ... WHERE uid=%s"
                        cursor.execute(sql, (data.status, ..., data.uid))
                        result.legacy_status = "UPDATED"
                    elif operation == "DELETE":
                        # TODO: Implement soft or hard delete
                        sql = "UPDATE subscribers_enhanced SET status='DELETED' WHERE uid=%s"
                        cursor.execute(sql, (data.uid,))
                        result.legacy_status = "DELETED"
                    else:
                        raise ValueError(f"Unsupported operation: {operation}")
                conn.commit()
            result.success = True
            result.message = f"Operation '{operation}' successful in Legacy system."
            logger.info("Legacy provisioning successful for UID %s", data.uid)
        except Exception as e:
            logger.error("Legacy provisioning failed for UID %s: %s", data.uid, str(e))
            result.legacy_status = f"FAILED: {str(e)}"
            result.message = f"Legacy operation failed: {str(e)}"
        return result

    def _provision_cloud(self, data: SubscriberData, operation: str) -> ProvisioningResult:
        """Handle provisioning only in the cloud system (DynamoDB)."""
        result = ProvisioningResult(
            success=False, mode=ProvisioningMode.CLOUD, operation=operation, uid=data.uid
        )
        try:
            item = self._prepare_dynamodb_item(data)
            if operation == "CREATE" or operation == "UPDATE":
                self.subscribers_table.put_item(Item=item)
                result.cloud_status = "CREATED_OR_UPDATED"
            elif operation == "DELETE":
                self.subscribers_table.delete_item(Key={"subscriberId": data.uid})
                result.cloud_status = "DELETED"
            else:
                raise ValueError(f"Unsupported operation: {operation}")
            result.success = True
            result.message = f"Operation '{operation}' successful in Cloud system."
            logger.info("Cloud provisioning successful for UID %s", data.uid)
        except Exception as e:
            logger.error("Cloud provisioning failed for UID %s: %s", data.uid, str(e))
            result.cloud_status = f"FAILED: {str(e)}"
            result.message = f"Cloud operation failed: {str(e)}"
        return result

    def _provision_dual(self, data: SubscriberData, operation: str) -> ProvisioningResult:
        """
        Handle provisioning in both systems with consistency.
        Uses a basic two-phase commit approach (best effort).
        """
        result = ProvisioningResult(
            success=False, mode=ProvisioningMode.DUAL_PROV, operation=operation, uid=data.uid
        )
        legacy_conn = None

        try:
            # Phase 1: Prepare and execute Legacy DB operation (without commit)
            logger.debug("Dual Provision Phase 1: Preparing Legacy DB for UID %s", data.uid)
            legacy_conn = get_legacy_db_connection()
            if not legacy_conn:
                raise ConnectionError("Failed to connect to Legacy DB")

            with legacy_conn.cursor() as cursor:
                if operation == "CREATE":
                    # F821 Fix: Added import for asdict
                    item_dict = {
                        k: v for k, v in asdict(data).items() if v is not None
                    }
                    sql = "INSERT INTO subscribers_enhanced (uid, imsi, msisdn, status, ...) VALUES (%s, %s, ...)"
                    cursor.execute(sql, (item_dict["uid"], item_dict["imsi"], ...))
                elif operation == "UPDATE":
                    sql = "UPDATE subscribers_enhanced SET status=%s, ... WHERE uid=%s"
                    cursor.execute(sql, (data.status, ..., data.uid))
                elif operation == "DELETE":
                    sql = "UPDATE subscribers_enhanced SET status='DELETED' WHERE uid=%s"
                    cursor.execute(sql, (data.uid,))
                else:
                    raise ValueError(f"Unsupported operation: {operation}")
            logger.debug("Dual Provision Phase 1: Legacy DB prepared for UID %s", data.uid)

            # Phase 2: Execute Cloud DB operation
            logger.debug("Dual Provision Phase 2: Executing Cloud DB for UID %s", data.uid)
            cloud_result = self._provision_cloud(data, operation)
            if not cloud_result.success:
                # If Cloud fails, rollback Legacy
                raise Exception(f"Cloud operation failed: {cloud_result.message}")
            result.cloud_status = cloud_result.cloud_status
            logger.debug("Dual Provision Phase 2: Cloud DB successful for UID %s", data.uid)

            # Phase 3: Commit Legacy DB operation
            logger.debug("Dual Provision Phase 3: Committing Legacy DB for UID %s", data.uid)
            legacy_conn.commit()
            result.legacy_status = f"{operation}_COMMITTED"
            logger.debug("Dual Provision Phase 3: Legacy DB committed for UID %s", data.uid)

            result.success = True
            result.message = f"Operation '{operation}' successful in both systems."
            logger.info("Dual provisioning successful for UID %s", data.uid)

        except Exception as e:
            logger.error("Dual provisioning failed for UID %s: %s", data.uid, str(e))
            result.message = f"Dual provisioning failed: {str(e)}"
            if result.cloud_status and "FAILED" not in result.cloud_status:
                result.cloud_status += " (Potential Inconsistency)"
            else:
                result.cloud_status = f"FAILED_OR_NOT_ATTEMPTED: {str(e)}"

            # Rollback Legacy DB if connection exists and commit didn't happen
            if legacy_conn:
                try:
                    logger.warning(
                        "Attempting Legacy DB rollback for UID %s due to failure.",
                        data.uid,
                    )
                    legacy_conn.rollback()
                    result.legacy_status = f"{operation}_ROLLEDBACK"
                    logger.info("Legacy DB rollback successful for UID %s", data.uid)
                except Exception as rollback_err:
                    logger.error(
                        "Legacy DB rollback FAILED for UID %s: %s",
                        data.uid,
                        str(rollback_err),
                    )
                    result.legacy_status = f"ROLLBACK_FAILED: {str(rollback_err)}"
                    result.message += " CRITICAL: Legacy DB rollback failed!"

        finally:
            if legacy_conn:
                legacy_conn.close()

        return result

    def _validate_and_transform(self, data: Dict) -> Dict:
        """Validate input data and transform into SubscriberData structure."""
        # Use InputValidator for basic checks
        validated = self.validator.validate_json(
            data,
            required_fields=["uid", "imsi"],
            optional_fields=[
                "msisdn",
                "status",
                "plan_type",
                "network_type",
                "service_class",
                "odbic",
                "odboc",
                "data_limit_mb",
                "voice_minutes",
                "sms_count",
                "gprs_enabled",
                "volte_enabled",
                "activation_date",
                # ... add all other fields from SubscriberData ...
            ],
        )

        # Apply specific field validations and transformations
        validated["uid"] = self.validator.sanitize_string(
            validated["uid"], 50, "uid"
        )
        validated["imsi"] = self.validator.sanitize_string(
            validated["imsi"], 15, "imsi"
        )
        if "msisdn" in validated:
            validated["msisdn"] = self.validator.sanitize_string(
                validated["msisdn"], 15, "msisdn"
            )

        # Handle BarringControls if present
        if "odbic" in validated or "odboc" in validated:
            validated["barring_controls"] = BarringControls(
                odbic=validated.pop("odbic", None), odboc=validated.pop("odboc", None)
            )

        # Convert numeric types
        for field in ["data_limit_mb", "balance_amount", "credit_limit", "spending_limit"]:
            if field in validated and validated[field] is not None:
                try:
                    validated[field] = Decimal(str(validated[field]))
                except Exception:
                    raise ValueError(f"Invalid numeric value for {field}")

        # Convert boolean types
        for field in ["gprs_enabled", "volte_enabled", "wifi_calling"]:
            if field in validated and validated[field] is not None:
                validated[field] = str(validated[field]).lower() in ["true", "1", "yes"]

        # Ensure timestamps are valid ISO format or generate defaults
        now_iso = datetime.utcnow().isoformat()
        validated["created_at"] = validated.get("created_at") or now_iso
        validated["updated_at"] = now_iso

        # Filter out None values before returning, as DynamoDB doesn't like None
        return {k: v for k, v in validated.items() if v is not None}

    def _prepare_dynamodb_item(self, data: SubscriberData) -> Dict:
        """Convert SubscriberData dataclass to a DynamoDB-compatible dictionary."""
        # F821 Fix: Added import for asdict
        item_dict = asdict(data)

        # Map uid to subscriberId for DynamoDB primary key
        item_dict["subscriberId"] = item_dict.pop("uid")

        # Flatten nested structures like BarringControls
        if "barring_controls" in item_dict and isinstance(
            item_dict["barring_controls"], BarringControls
        ):
            barring = item_dict.pop("barring_controls")
            item_dict["odbic"] = barring.odbic
            item_dict["odboc"] = barring.odboc

        # Convert Decimals to strings or numbers based on DynamoDB best practices
        # For simplicity here, converting to float (consider strings for precision)
        final_item = {}
        for k, v in item_dict.items():
            if isinstance(v, Decimal):
                final_item[k] = float(v)
            elif v is not None:  # Filter out None values explicitly
                final_item[k] = v

        return final_item


# Instantiate service
enhanced_provisioning_service = EnhancedProvisioningService()
