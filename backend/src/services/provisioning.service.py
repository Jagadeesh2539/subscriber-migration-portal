#!/usr/bin/env python3
# Provisioning Service - Base Logic for Subscriber CRUD Operations
# Handles interaction with Legacy (MySQL) and Cloud (DynamoDB) based on mode

# Removed unused logging import
from datetime import datetime
from enum import Enum
# Removed unused List, Tuple; Added Dict, Optional for F821 Fix
from typing import Dict, Optional

from config.database import get_dynamodb_table, get_legacy_db_connection
from services.audit.service import AuditService
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


class ProvisioningMode(Enum):
    """Defines the target system(s) for provisioning operations."""

    LEGACY = "legacy"
    CLOUD = "cloud"
    DUAL_PROV = "dual_prov"


class ProvisioningResult:
    """Represents the outcome of a provisioning operation."""

    def __init__(
        self,
        success: bool,
        mode: ProvisioningMode,
        operation: str,
        # F821 Fix: Added Optional import
        uid: Optional[str] = None,
        # F821 Fix: Added Optional import
        message: Optional[str] = None,
        # F821 Fix: Added Optional import
        legacy_status: Optional[str] = None,
        # F821 Fix: Added Optional import
        cloud_status: Optional[str] = None,
        duration_ms: int = 0,
        # F821 Fix: Added Optional import
        timestamp: Optional[str] = None,
    ):
        self.success = success
        self.mode = mode
        self.operation = operation
        self.uid = uid
        self.message = message
        self.legacy_status = legacy_status
        self.cloud_status = cloud_status
        self.duration_ms = duration_ms
        self.timestamp = timestamp or datetime.utcnow().isoformat()

    # F821 Fix: Added Dict import
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "mode": self.mode.name,
            "operation": self.operation,
            "uid": self.uid,
            "message": self.message,
            "legacy_status": self.legacy_status,
            "cloud_status": self.cloud_status,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


class ProvisioningService:
    """Base service for subscriber provisioning operations."""

    def __init__(self):
        self.subscribers_table = get_dynamodb_table("subscribers")
        self.audit_service = AuditService()
        self.validator = InputValidator()

    # F821 Fix: Added Dict import
    def provision_subscriber(
        self,
        mode: ProvisioningMode,
        data: Dict,
        operation: str = "CREATE",
        created_by: str = "system",
    ) -> ProvisioningResult:
        """
        Main entry point for provisioning a subscriber based on mode.
        """
        start_time = datetime.utcnow()
        result = ProvisioningResult(success=False, mode=mode, operation=operation)

        try:
            # Basic validation
            validated_data = self.validator.validate_json(
                data, required_fields=["uid", "imsi"]
            )
            result.uid = validated_data.get("uid")

            # Perform operation based on mode
            if mode == ProvisioningMode.LEGACY:
                result = self._provision_legacy(validated_data, operation)
            elif mode == ProvisioningMode.CLOUD:
                result = self._provision_cloud(validated_data, operation)
            elif mode == ProvisioningMode.DUAL_PROV:
                result = self._provision_dual(validated_data, operation)
            else:
                raise ValueError(f"Unsupported provisioning mode: {mode}")

            result.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result.timestamp = start_time.isoformat()

            # Audit logging
            self._log_provision_audit(created_by, result)

            return result

        except Exception as e:
            logger.error(
                "Provisioning error for UID %s (Op: %s, Mode: %s): %s",
                data.get("uid", "UNKNOWN"),
                operation,
                mode.name,
                str(e),
            )
            result.success = False
            result.message = f"Provisioning failed: {str(e)}"
            result.duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result.timestamp = start_time.isoformat()
            self._log_provision_audit(created_by, result, is_error=True, error_message=str(e))
            return result

    # F821 Fix: Added Dict import
    def _provision_legacy(self, data: Dict, operation: str) -> ProvisioningResult:
        """Handle provisioning only in the legacy system (MySQL)."""
        result = ProvisioningResult(
            success=False, mode=ProvisioningMode.LEGACY, operation=operation, uid=data["uid"]
        )
        try:
            with get_legacy_db_connection() as conn:
                with conn.cursor() as cursor:
                    if operation == "CREATE":
                        # Basic INSERT example - needs field mapping
                        # E501 Fix: Broke line
                        sql = (
                            "INSERT INTO subscribers (uid, imsi, msisdn, status, created_at, updated_at) "
                            "VALUES (%s, %s, %s, %s, NOW(), NOW())"
                        )
                        cursor.execute(
                            sql,
                            (
                                data["uid"],
                                data["imsi"],
                                data.get("msisdn"),
                                data.get("status", "ACTIVE"),
                            ),
                        )
                        result.legacy_status = "CREATED"
                    elif operation == "UPDATE":
                        # Basic UPDATE example - needs field mapping
                        sql = "UPDATE subscribers SET status=%s, updated_at=NOW() WHERE uid=%s"
                        cursor.execute(sql, (data.get("status", "ACTIVE"), data["uid"]))
                        result.legacy_status = "UPDATED"
                    elif operation == "DELETE":
                        # Soft delete example
                        sql = "UPDATE subscribers SET status='DELETED', updated_at=NOW() WHERE uid=%s"
                        cursor.execute(sql, (data["uid"],))
                        result.legacy_status = "DELETED"
                    else:
                        raise ValueError(f"Unsupported operation: {operation}")
                conn.commit()
            result.success = True
            result.message = f"Operation '{operation}' successful in Legacy system."
            logger.info("Legacy provisioning successful for UID %s", data["uid"])
        except Exception as e:
            logger.error("Legacy provisioning failed for UID %s: %s", data["uid"], str(e))
            result.legacy_status = f"FAILED: {str(e)}"
            result.message = f"Legacy operation failed: {str(e)}"
        return result

    # F821 Fix: Added Dict import
    def _provision_cloud(self, data: Dict, operation: str) -> ProvisioningResult:
        """Handle provisioning only in the cloud system (DynamoDB)."""
        result = ProvisioningResult(
            success=False, mode=ProvisioningMode.CLOUD, operation=operation, uid=data["uid"]
        )
        try:
            # Prepare item for DynamoDB (map uid to subscriberId)
            item = data.copy()
            item["subscriberId"] = item.pop("uid")
            item["updated_at"] = datetime.utcnow().isoformat()

            if operation == "CREATE":
                item["created_at"] = item["updated_at"]
                self.subscribers_table.put_item(Item=item)
                result.cloud_status = "CREATED"
            elif operation == "UPDATE":
                # Use put_item for simplicity (upsert)
                # For partial updates, build UpdateExpression
                self.subscribers_table.put_item(Item=item)
                result.cloud_status = "UPDATED"
            elif operation == "DELETE":
                self.subscribers_table.delete_item(Key={"subscriberId": item["subscriberId"]})
                result.cloud_status = "DELETED"
            else:
                raise ValueError(f"Unsupported operation: {operation}")

            result.success = True
            result.message = f"Operation '{operation}' successful in Cloud system."
            logger.info("Cloud provisioning successful for UID %s", item["subscriberId"])
        except Exception as e:
            logger.error("Cloud provisioning failed for UID %s: %s", data["uid"], str(e))
            result.cloud_status = f"FAILED: {str(e)}"
            result.message = f"Cloud operation failed: {str(e)}"
        return result

    # F821 Fix: Added Dict import
    def _provision_dual(self, data: Dict, operation: str) -> ProvisioningResult:
        """
        Handle provisioning in both systems with best-effort consistency.
        Executes Legacy first, then Cloud. Rolls back Legacy if Cloud fails.
        """
        result = ProvisioningResult(
            success=False, mode=ProvisioningMode.DUAL_PROV, operation=operation, uid=data["uid"]
        )
        legacy_conn = None
        legacy_done = False

        try:
            # Phase 1: Execute Legacy DB operation (without commit initially)
            logger.debug("Dual Provision Phase 1: Preparing Legacy DB for UID %s", data["uid"])
            legacy_conn = get_legacy_db_connection()
            if not legacy_conn:
                raise ConnectionError("Failed to connect to Legacy DB for dual provisioning")

            with legacy_conn.cursor() as cursor:
                if operation == "CREATE":
                    # E501 Fix: Broke line
                    sql = (
                        "INSERT INTO subscribers (uid, imsi, msisdn, status, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, NOW(), NOW())"
                    )
                    cursor.execute(
                        sql,
                        (
                            data["uid"],
                            data["imsi"],
                            data.get("msisdn"),
                            data.get("status", "ACTIVE"),
                        ),
                    )
                elif operation == "UPDATE":
                    sql = "UPDATE subscribers SET status=%s, updated_at=NOW() WHERE uid=%s"
                    cursor.execute(sql, (data.get("status", "ACTIVE"), data["uid"]))
                elif operation == "DELETE":
                    sql = "UPDATE subscribers SET status='DELETED', updated_at=NOW() WHERE uid=%s"
                    cursor.execute(sql, (data["uid"],))
                else:
                    raise ValueError(f"Unsupported operation: {operation}")
            legacy_done = True  # Mark that legacy operation was attempted
            logger.debug("Dual Provision Phase 1: Legacy DB prepared for UID %s", data["uid"])

            # Phase 2: Execute Cloud DB operation
            logger.debug("Dual Provision Phase 2: Executing Cloud DB for UID %s", data["uid"])
            cloud_result = self._provision_cloud(data, operation)
            if not cloud_result.success:
                raise Exception(f"Cloud operation failed: {cloud_result.message}")
            result.cloud_status = cloud_result.cloud_status
            logger.debug("Dual Provision Phase 2: Cloud DB successful for UID %s", data["uid"])

            # Phase 3: Commit Legacy DB operation
            logger.debug("Dual Provision Phase 3: Committing Legacy DB for UID %s", data["uid"])
            legacy_conn.commit()
            result.legacy_status = f"{operation}_COMMITTED"
            logger.debug("Dual Provision Phase 3: Legacy DB committed for UID %s", data["uid"])

            result.success = True
            result.message = f"Operation '{operation}' successful in both systems."
            logger.info("Dual provisioning successful for UID %s", data["uid"])

        except Exception as e:
            logger.error("Dual provisioning failed for UID %s: %s", data["uid"], str(e))
            result.message = f"Dual provisioning failed: {str(e)}"
            if result.cloud_status and "FAILED" not in result.cloud_status:
                result.cloud_status = result.cloud_status + " (Potential Inconsistency)"
            else:
                result.cloud_status = f"FAILED_OR_NOT_ATTEMPTED: {str(e)}"

            # Attempt Legacy DB rollback only if the operation was attempted
            if legacy_conn and legacy_done:
                try:
                    logger.warning(
                        "Attempting Legacy DB rollback for UID %s due to dual provision failure.",
                        data["uid"],
                    )
                    legacy_conn.rollback()
                    result.legacy_status = f"{operation}_ROLLEDBACK"
                    logger.info("Legacy DB rollback successful for UID %s", data["uid"])
                except Exception as rollback_err:
                    logger.error(
                        "Legacy DB rollback FAILED for UID %s: %s",
                        data["uid"],
                        str(rollback_err),
                    )
                    result.legacy_status = f"ROLLBACK_FAILED: {str(rollback_err)}"
                    result.message += " CRITICAL: Legacy DB rollback failed!"
            # E111/E117 Fix: Corrected indentation
            elif legacy_conn:  # Connection opened but operation not attempted
                result.legacy_status = "NOT_ATTEMPTED_DUE_TO_ERROR"
            else:  # Connection failed
                result.legacy_status = "CONNECTION_FAILED"

        finally:
            if legacy_conn:
                legacy_conn.close()

        return result

    # E303 Fix: Reduced blank lines
    def _log_provision_audit(
        self, user: str, result: ProvisioningResult, is_error: bool = False, error_message: str = None
    ):
        """Helper function to log provisioning actions."""
        action = f"provision_{result.operation.lower()}"
        status = "FAILED" if is_error or not result.success else "SUCCESS"
        details = {
            "uid": result.uid,
            "mode": result.mode.name,
            "operation": result.operation,
            "status": status,
            "duration_ms": result.duration_ms,
        }
        if result.legacy_status:
            details["legacy_status"] = result.legacy_status
        if result.cloud_status:
            details["cloud_status"] = result.cloud_status
        if error_message:
            details["error"] = error_message
        elif result.message:
            details["message"] = result.message

        self.audit_service.log_action(action=action, resource="subscriber", user=user, details=details, status=status)


# Instantiate service
provisioning_service = ProvisioningService()
