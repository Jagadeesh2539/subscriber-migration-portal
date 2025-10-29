#!/usr/bin/env python3
"""
Provisioning Service - Handles dual provisioning logic as per specifications
Implements create/update/delete operations with proper system coordination
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from config.database import get_dynamodb_table, get_legacy_db_connection
from services.audit.service import AuditService
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


class ProvisioningMode(Enum):
    """Provisioning modes as per specification"""

    CLOUD_ONLY = "cloud_only"
    LEGACY_ONLY = "legacy_only"
    DUAL_PROV = "dual_prov"


class ProvisioningResult:
    """Result of provisioning operation"""

    def __init__(self):
        self.success = False
        self.cloud_result = None
        self.legacy_result = None
        self.errors = []
        self.rollback_performed = False
        self.operations_performed = []

    def add_error(self, error: str):
        self.errors.append(error)

    def add_operation(self, operation: str):
        self.operations_performed.append(operation)


class ProvisioningService:
    """Service implementing dual provisioning logic per specifications"""

    def __init__(self):
        self.dynamodb_table = get_dynamodb_table("SUBSCRIBER_TABLE_NAME")
        self.audit_service = AuditService()
        self.validator = InputValidator()

    def create_subscriber(
        self, subscriber_data: Dict[str, Any], mode: ProvisioningMode = ProvisioningMode.DUAL_PROV
    ) -> ProvisioningResult:
        """
        Create subscriber with provisioning mode logic

        Dual provisioning ensures both systems are updated.
        If subscriber exists in one system → error: "Subscriber already present".
        Rollback if one system fails.
        """
        result = ProvisioningResult()
        uid = subscriber_data.get("uid")

        try:
            if mode == ProvisioningMode.CLOUD_ONLY:
                # Operate only on cloud system
                result.cloud_result = self._create_in_cloud(subscriber_data)
                result.success = result.cloud_result["success"]
                result.add_operation("cloud_create")

            elif mode == ProvisioningMode.LEGACY_ONLY:
                # Operate only on legacy system (MySQL)
                result.legacy_result = self._create_in_legacy(subscriber_data)
                result.success = result.legacy_result["success"]
                result.add_operation("legacy_create")

            elif mode == ProvisioningMode.DUAL_PROV:
                # Dual provisioning: both systems must be updated

                # Step 1: Check if subscriber exists in either system
                cloud_exists = self._check_cloud_exists(uid)
                legacy_exists = self._check_legacy_exists(uid)

                if cloud_exists or legacy_exists:
                    result.add_error(
                        f"Subscriber {uid} already present in {'cloud' if cloud_exists else 'legacy'} system"
                    )
                    result.success = False
                    return result

                # Step 2: Create in both systems
                result.cloud_result = self._create_in_cloud(subscriber_data)
                result.add_operation("cloud_create")

                if result.cloud_result["success"]:
                    result.legacy_result = self._create_in_legacy(subscriber_data)
                    result.add_operation("legacy_create")

                    if result.legacy_result["success"]:
                        result.success = True
                    else:
                        # Rollback cloud creation
                        rollback_result = self._rollback_cloud_create(uid)
                        result.rollback_performed = True
                        result.add_operation("cloud_rollback")
                        result.add_error(f"Legacy creation failed, rolled back cloud: {result.legacy_result['error']}")
                else:
                    result.add_error(f"Cloud creation failed: {result.cloud_result['error']}")

            # Log the operation
            self._log_provisioning_operation("create", uid, mode, result)

            return result

        except Exception as e:
            logger.error(f"Error creating subscriber {uid}: {str(e)}")
            result.add_error(f"Unexpected error: {str(e)}")
            return result

    def update_subscriber(
        self, uid: str, update_data: Dict[str, Any], mode: ProvisioningMode = ProvisioningMode.DUAL_PROV
    ) -> ProvisioningResult:
        """
        Update subscriber with dual provisioning logic

        Dual provisioning updates only in the system where the subscriber exists.
        Do not replicate to missing system.
        Update in both only if subscriber exists in both systems.
        """
        result = ProvisioningResult()

        try:
            if mode == ProvisioningMode.CLOUD_ONLY:
                # Update only in cloud
                result.cloud_result = self._update_in_cloud(uid, update_data)
                result.success = result.cloud_result["success"]
                result.add_operation("cloud_update")

            elif mode == ProvisioningMode.LEGACY_ONLY:
                # Update only in legacy
                result.legacy_result = self._update_in_legacy(uid, update_data)
                result.success = result.legacy_result["success"]
                result.add_operation("legacy_update")

            elif mode == ProvisioningMode.DUAL_PROV:
                # Dual provisioning: update only where subscriber exists

                cloud_exists = self._check_cloud_exists(uid)
                legacy_exists = self._check_legacy_exists(uid)

                if not cloud_exists and not legacy_exists:
                    result.add_error(f"Subscriber {uid} not found in any system")
                    result.success = False
                    return result

                success_count = 0
                total_operations = 0

                # Update in cloud if exists
                if cloud_exists:
                    result.cloud_result = self._update_in_cloud(uid, update_data)
                    result.add_operation("cloud_update")
                    total_operations += 1
                    if result.cloud_result["success"]:
                        success_count += 1
                    else:
                        result.add_error(f"Cloud update failed: {result.cloud_result['error']}")

                # Update in legacy if exists
                if legacy_exists:
                    result.legacy_result = self._update_in_legacy(uid, update_data)
                    result.add_operation("legacy_update")
                    total_operations += 1
                    if result.legacy_result["success"]:
                        success_count += 1
                    else:
                        result.add_error(f"Legacy update failed: {result.legacy_result['error']}")

                # Success if at least one update succeeded
                result.success = success_count > 0

            # Log the operation
            self._log_provisioning_operation("update", uid, mode, result)

            return result

        except Exception as e:
            logger.error(f"Error updating subscriber {uid}: {str(e)}")
            result.add_error(f"Unexpected error: {str(e)}")
            return result

    def delete_subscriber(self, uid: str, mode: ProvisioningMode = ProvisioningMode.DUAL_PROV) -> ProvisioningResult:
        """
        Delete subscriber with dual provisioning logic

        Deletes subscriber in both systems if present.
        Logs missing subscriber for auditing.
        """
        result = ProvisioningResult()

        try:
            if mode == ProvisioningMode.CLOUD_ONLY:
                # Delete only from cloud
                result.cloud_result = self._delete_from_cloud(uid)
                result.success = result.cloud_result["success"]
                result.add_operation("cloud_delete")

            elif mode == ProvisioningMode.LEGACY_ONLY:
                # Delete only from legacy
                result.legacy_result = self._delete_from_legacy(uid)
                result.success = result.legacy_result["success"]
                result.add_operation("legacy_delete")

            elif mode == ProvisioningMode.DUAL_PROV:
                # Dual provisioning: delete from both systems if present

                cloud_exists = self._check_cloud_exists(uid)
                legacy_exists = self._check_legacy_exists(uid)

                if not cloud_exists and not legacy_exists:
                    result.add_error(f"Subscriber {uid} not found in any system")
                    result.success = False
                    return result

                success_count = 0
                total_operations = 0

                # Delete from cloud if exists
                if cloud_exists:
                    result.cloud_result = self._delete_from_cloud(uid)
                    result.add_operation("cloud_delete")
                    total_operations += 1
                    if result.cloud_result["success"]:
                        success_count += 1
                    else:
                        result.add_error(f"Cloud deletion failed: {result.cloud_result['error']}")
                else:
                    # Log missing subscriber for auditing
                    self.audit_service.log_action(
                        action="subscriber_missing_in_cloud",
                        resource="subscriber",
                        user="system",
                        details={"uid": uid, "operation": "delete"},
                    )

                # Delete from legacy if exists
                if legacy_exists:
                    result.legacy_result = self._delete_from_legacy(uid)
                    result.add_operation("legacy_delete")
                    total_operations += 1
                    if result.legacy_result["success"]:
                        success_count += 1
                    else:
                        result.add_error(f"Legacy deletion failed: {result.legacy_result['error']}")
                else:
                    # Log missing subscriber for auditing
                    self.audit_service.log_action(
                        action="subscriber_missing_in_legacy",
                        resource="subscriber",
                        user="system",
                        details={"uid": uid, "operation": "delete"},
                    )

                # Success if at least one deletion succeeded
                result.success = success_count > 0

            # Log the operation
            self._log_provisioning_operation("delete", uid, mode, result)

            return result

        except Exception as e:
            logger.error(f"Error deleting subscriber {uid}: {str(e)}")
            result.add_error(f"Unexpected error: {str(e)}")
            return result

    def search_subscriber(self, uid: str) -> Dict[str, Any]:
        """
        Search subscriber with dual provisioning fallback logic

        Fetch from cloud first, fallback to legacy if not found.
        Flag discrepancies between systems in logs.
        """
        try:
            # Step 1: Try cloud first
            cloud_subscriber = self._get_from_cloud(uid)

            if cloud_subscriber:
                # Step 2: Check if also in legacy for discrepancy detection
                legacy_subscriber = self._get_from_legacy(uid)

                if legacy_subscriber:
                    # Subscriber exists in both - check for discrepancies
                    discrepancies = self._detect_discrepancies(cloud_subscriber, legacy_subscriber)
                    if discrepancies:
                        # Flag discrepancies in logs
                        self.audit_service.log_action(
                            action="subscriber_discrepancy_detected",
                            resource="subscriber",
                            user="system",
                            details={
                                "uid": uid,
                                "discrepancies": discrepancies,
                                "cloud_data": self._sanitize_for_log(cloud_subscriber),
                                "legacy_data": self._sanitize_for_log(legacy_subscriber),
                            },
                        )

                    return {
                        "found": True,
                        "source": "both",
                        "primary_data": cloud_subscriber,
                        "secondary_data": legacy_subscriber,
                        "discrepancies": discrepancies,
                    }
                else:
                    return {"found": True, "source": "cloud_only", "primary_data": cloud_subscriber}

            # Step 3: Fallback to legacy if not found in cloud
            legacy_subscriber = self._get_from_legacy(uid)

            if legacy_subscriber:
                return {"found": True, "source": "legacy_only", "primary_data": legacy_subscriber}

            # Not found in either system
            return {"found": False, "source": "none"}

        except Exception as e:
            logger.error(f"Error searching subscriber {uid}: {str(e)}")
            return {"found": False, "source": "error", "error": str(e)}

    def get_system_status(self) -> Dict[str, Any]:
        """
        Get status of both provisioning systems
        """
        try:
            cloud_status = self._check_cloud_health()
            legacy_status = self._check_legacy_health()

            return {
                "cloud_system": {"healthy": cloud_status, "type": "DynamoDB"},
                "legacy_system": {"healthy": legacy_status, "type": "MySQL RDS"},
                "overall_status": "healthy" if cloud_status and legacy_status else "degraded",
                "last_checked": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting system status: {str(e)}")
            return {
                "cloud_system": {"healthy": False, "type": "DynamoDB"},
                "legacy_system": {"healthy": False, "type": "MySQL RDS"},
                "overall_status": "error",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat(),
            }

    # Private helper methods

    def _check_cloud_exists(self, uid: str) -> bool:
        """Check if subscriber exists in cloud system"""
        try:
            response = self.dynamodb_table.get_item(Key={"subscriberId": uid})
            return "Item" in response
        except Exception:
            return False

    def _check_legacy_exists(self, uid: str) -> bool:
        """Check if subscriber exists in legacy system"""
        connection = get_legacy_db_connection()
        if not connection:
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT uid FROM subscribers WHERE uid = %s AND status != 'DELETED'", (uid,))
                return cursor.fetchone() is not None
        except Exception:
            return False
        finally:
            connection.close()

    def _create_in_cloud(self, subscriber_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create subscriber in cloud system"""
        try:
            # Check if already exists
            if self._check_cloud_exists(subscriber_data["uid"]):
                return {"success": False, "error": "Subscriber already exists in cloud system"}

            # Transform data for DynamoDB
            cloud_item = {
                "subscriberId": subscriber_data["uid"],
                "uid": subscriber_data["uid"],
                "imsi": subscriber_data.get("imsi", ""),
                "msisdn": subscriber_data.get("msisdn", ""),
                "status": subscriber_data.get("status", "ACTIVE"),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "apn": subscriber_data.get("apn", ""),
                "service_profile": subscriber_data.get("service_profile", ""),
                "roaming_allowed": subscriber_data.get("roaming_allowed", True),
            }

            self.dynamodb_table.put_item(Item=cloud_item)

            return {"success": True, "data": cloud_item}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_in_legacy(self, subscriber_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create subscriber in legacy system"""
        connection = get_legacy_db_connection()
        if not connection:
            return {"success": False, "error": "Cannot connect to legacy database"}

        try:
            with connection.cursor() as cursor:
                # Check if already exists
                if self._check_legacy_exists(subscriber_data["uid"]):
                    return {"success": False, "error": "Subscriber already exists in legacy system"}

                # Insert new subscriber
                insert_query = """
                INSERT INTO subscribers (uid, imsi, msisdn, status, created_at, updated_at, 
                                       apn, service_profile, roaming_allowed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                values = (
                    subscriber_data["uid"],
                    subscriber_data.get("imsi", ""),
                    subscriber_data.get("msisdn", ""),
                    subscriber_data.get("status", "ACTIVE"),
                    datetime.utcnow(),
                    datetime.utcnow(),
                    subscriber_data.get("apn", ""),
                    subscriber_data.get("service_profile", ""),
                    subscriber_data.get("roaming_allowed", True),
                )

                cursor.execute(insert_query, values)
                connection.commit()

                return {"success": True, "rows_affected": cursor.rowcount}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            connection.close()

    def _update_in_cloud(self, uid: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update subscriber in cloud system"""
        try:
            if not self._check_cloud_exists(uid):
                return {"success": False, "error": "Subscriber not found in cloud system"}

            # Build update expression
            update_expression = "SET updated_at = :updated_at"
            expression_values = {":updated_at": datetime.utcnow().isoformat()}

            for key, value in update_data.items():
                if key not in ["uid", "subscriberId"]:  # Don't update primary keys
                    update_expression += f", {key} = :{key}"
                    expression_values[f":{key}"] = value

            self.dynamodb_table.update_item(
                Key={"subscriberId": uid},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
            )

            return {"success": True, "updated_fields": list(update_data.keys())}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _update_in_legacy(self, uid: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update subscriber in legacy system"""
        connection = get_legacy_db_connection()
        if not connection:
            return {"success": False, "error": "Cannot connect to legacy database"}

        try:
            with connection.cursor() as cursor:
                if not self._check_legacy_exists(uid):
                    return {"success": False, "error": "Subscriber not found in legacy system"}

                # Build update query
                set_clauses = ["updated_at = %s"]
                values = [datetime.utcnow()]

                for key, value in update_data.items():
                    if key != "uid":  # Don't update primary key
                        set_clauses.append(f"{key} = %s")
                        values.append(value)

                values.append(uid)  # For WHERE clause

                update_query = f"UPDATE subscribers SET {', '.join(set_clauses)} WHERE uid = %s"

                cursor.execute(update_query, values)
                connection.commit()

                return {"success": True, "rows_affected": cursor.rowcount}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            connection.close()

    def _delete_from_cloud(self, uid: str) -> Dict[str, Any]:
        """Delete subscriber from cloud system"""
        try:
            if not self._check_cloud_exists(uid):
                return {"success": False, "error": "Subscriber not found in cloud system"}

            self.dynamodb_table.delete_item(Key={"subscriberId": uid})

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _delete_from_legacy(self, uid: str) -> Dict[str, Any]:
        """Delete subscriber from legacy system"""
        connection = get_legacy_db_connection()
        if not connection:
            return {"success": False, "error": "Cannot connect to legacy database"}

        try:
            with connection.cursor() as cursor:
                if not self._check_legacy_exists(uid):
                    return {"success": False, "error": "Subscriber not found in legacy system"}

                # Soft delete by setting status to DELETED
                cursor.execute(
                    "UPDATE subscribers SET status = 'DELETED', updated_at = %s WHERE uid = %s",
                    (datetime.utcnow(), uid),
                )
                connection.commit()

                return {"success": True, "rows_affected": cursor.rowcount}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            connection.close()

    def _rollback_cloud_create(self, uid: str) -> Dict[str, Any]:
        """Rollback cloud creation"""
        try:
            self.dynamodb_table.delete_item(Key={"subscriberId": uid})
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_from_cloud(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get subscriber from cloud system"""
        try:
            response = self.dynamodb_table.get_item(Key={"subscriberId": uid})
            return response.get("Item")
        except Exception:
            return None

    def _get_from_legacy(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get subscriber from legacy system"""
        connection = get_legacy_db_connection()
        if not connection:
            return None

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM subscribers WHERE uid = %s AND status != 'DELETED'", (uid,))
                return cursor.fetchone()
        except Exception:
            return None
        finally:
            connection.close()

    def _detect_discrepancies(self, cloud_data: Dict[str, Any], legacy_data: Dict[str, Any]) -> List[str]:
        """Detect discrepancies between cloud and legacy data"""
        discrepancies = []

        # Check key fields
        key_fields = ["imsi", "msisdn", "status"]

        for field in key_fields:
            cloud_value = cloud_data.get(field)
            legacy_value = legacy_data.get(field)

            if cloud_value != legacy_value:
                discrepancies.append(f"{field}: cloud='{cloud_value}' vs legacy='{legacy_value}'")

        return discrepancies

    def _sanitize_for_log(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize data for logging (remove PII)"""
        if not data:
            return {}

        sanitized = {}
        for key, value in data.items():
            if key in ["imsi", "msisdn"]:
                # Mask PII
                sanitized[key] = f"{str(value)[:2]}***{str(value)[-2:]}" if value else None
            else:
                sanitized[key] = value

        return sanitized

    def _check_cloud_health(self) -> bool:
        """Check cloud system health"""
        try:
            self.dynamodb_table.scan(Limit=1)
            return True
        except Exception:
            return False

    def _check_legacy_health(self) -> bool:
        """Check legacy system health"""
        connection = get_legacy_db_connection()
        if not connection:
            return False

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception:
            return False
        finally:
            connection.close()

    # ... all existing content ...

    def _log_provisioning_operation(self, operation: str, uid: str, mode: ProvisioningMode, result: ProvisioningResult):
        """Log provisioning operation for audit"""
        try:
            self.audit_service.log_action(
                action=f"provisioning_{operation}",
                resource="subscriber",
                user="system",
                details={
                    "uid": uid,
                    "mode": mode.value,
                    "success": result.success,
                    "operations": result.operations_performed,
                    "errors": result.errors,
                    "rollback_performed": result.rollback_performed,
                },
            )
        except Exception as e:
            logger.error(f"Failed to log provisioning operation: {str(e)}")


# Export service instance
provisioning_service = ProvisioningService()
