#!/usr/bin/env python3
"""
Enhanced Provisioning Service - Rich subscriber provisioning with plan support
Supports planId, barring controls, addons, and services provisioning
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from config.database import get_dynamodb_table, get_legacy_db_connection
from models.subscriber.model import SubscriberData
from services.audit.service import AuditService
from services.provisioning.service import ProvisioningMode, ProvisioningResult
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)


class EnhancedProvisioningService:
    """Enhanced provisioning service with rich subscriber data support"""

    def __init__(self):
        self.dynamodb_table = get_dynamodb_table("SUBSCRIBER_TABLE_NAME")
        self.audit_service = AuditService()
        self.validator = InputValidator()

        # Supported values for validation
        self.supported_statuses = ["ACTIVE", "INACTIVE", "SUSPENDED", "DELETED"]
        self.supported_barring_states = ["barred", "notbarred"]

        # Common addon and service types
        self.common_addons = {
            "ADD_INTL_ROAM": "International Roaming",
            "ADD_OTT_PACK": "OTT Entertainment Package",
            "ADD_DATA_BOOST": "Data Speed Boost",
            "ADD_VOICE_PACK": "Voice Call Package",
            "ADD_SMS_PACK": "SMS Package",
            "ADD_MUSIC_STREAM": "Music Streaming",
            "ADD_VIDEO_STREAM": "Video Streaming",
            "ADD_CLOUD_STORAGE": "Cloud Storage",
            "ADD_SECURITY": "Mobile Security",
        }

        self.common_services = {
            "VOLTE": "Voice over LTE",
            "5G": "5G Network Access",
            "VoWiFi": "Voice over WiFi",
            "4G": "4G LTE Access",
            "3G": "3G Network Access",
            "2G": "2G Network Access",
            "SMS": "Short Message Service",
            "MMS": "Multimedia Message Service",
            "DATA": "Data Services",
            "VOICE": "Voice Services",
            "USSD": "USSD Services",
            "STK": "SIM Toolkit",
        }

    def create_enhanced_subscriber(
        self, subscriber_data: Dict[str, Any], mode: ProvisioningMode = ProvisioningMode.DUAL_PROV
    ) -> ProvisioningResult:
        """
        Create subscriber with enhanced data and provisioning mode logic

        Example subscriber_data:
        {
            "uid": "1222222222222212",
            "msisdn": "919812345678",
            "imsi": "404990123456789",
            "status": "ACTIVE",
            "planId": "PLN_5G_MAX",
            "barring": {
                "barAll": true,
                "odbic": "barred",
                "odboc": "notbarred"
            },
            "addons": ["ADD_INTL_ROAM", "ADD_OTT_PACK"],
            "services": ["VOLTE", "5G", "VoWiFi"]
        }
        """
        result = ProvisioningResult()

        try:
            # Parse and validate enhanced subscriber data
            subscriber = SubscriberData.from_api_payload(subscriber_data)
            subscriber.normalize()

            # Validate data
            validation_errors = subscriber.validate()
            if validation_errors:
                result.add_error(f"Data validation failed: {'; '.join(validation_errors)}")
                return result

            # Additional enhanced field validation
            enhanced_validation = self._validate_enhanced_fields(subscriber)
            if enhanced_validation:
                result.add_error(f"Enhanced field validation failed: {'; '.join(enhanced_validation)}")
                return result

            uid = subscriber.uid

            if mode == ProvisioningMode.CLOUD_ONLY:
                # Create only in cloud system
                result.cloud_result = self._create_enhanced_in_cloud(subscriber)
                result.success = result.cloud_result["success"]
                result.add_operation("cloud_create_enhanced")

            elif mode == ProvisioningMode.LEGACY_ONLY:
                # Create only in legacy system
                result.legacy_result = self._create_enhanced_in_legacy(subscriber)
                result.success = result.legacy_result["success"]
                result.add_operation("legacy_create_enhanced")

            elif mode == ProvisioningMode.DUAL_PROV:
                # Dual provisioning with enhanced data

                # Check existence in both systems
                cloud_exists = self._check_cloud_exists(uid)
                legacy_exists = self._check_legacy_exists(uid)

                if cloud_exists or legacy_exists:
                    result.add_error(
                        f"Subscriber {uid} already present in {'cloud' if cloud_exists else 'legacy'} system"
                    )
                    result.success = False
                    return result

                # Create in cloud first (with enhanced data)
                result.cloud_result = self._create_enhanced_in_cloud(subscriber)
                result.add_operation("cloud_create_enhanced")

                if result.cloud_result["success"]:
                    # Create in legacy with enhanced data
                    result.legacy_result = self._create_enhanced_in_legacy(subscriber)
                    result.add_operation("legacy_create_enhanced")

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

            # Log provisioning operation with enhanced data details
            self._log_enhanced_provisioning_operation("create", uid, mode, result, subscriber)

            return result

        except Exception as e:
            logger.error(f"Error creating enhanced subscriber {subscriber_data.get('uid', 'unknown')}: {str(e)}")
            result.add_error(f"Unexpected error: {str(e)}")
            return result

    def update_enhanced_subscriber(
        self, uid: str, update_data: Dict[str, Any], mode: ProvisioningMode = ProvisioningMode.DUAL_PROV
    ) -> ProvisioningResult:
        """
        Update subscriber with enhanced data fields

        Example update_data:
        {
            "status": "ACTIVE",
            "planId": "PLN_5G_PREMIUM",
            "barring": {"barAll": false, "odbic": "notbarred", "odboc": "notbarred"},
            "addons": ["ADD_OTT_PACK"],
            "services": ["VOLTE", "5G"]
        }
        """
        result = ProvisioningResult()

        try:
            # Validate update data
            validation_errors = self._validate_update_data(update_data)
            if validation_errors:
                result.add_error(f"Update validation failed: {'; '.join(validation_errors)}")
                return result

            # Add updated timestamp
            update_data["updated_at"] = datetime.utcnow().isoformat()

            if mode == ProvisioningMode.CLOUD_ONLY:
                # Update only in cloud
                result.cloud_result = self._update_enhanced_in_cloud(uid, update_data)
                result.success = result.cloud_result["success"]
                result.add_operation("cloud_update_enhanced")

            elif mode == ProvisioningMode.LEGACY_ONLY:
                # Update only in legacy
                result.legacy_result = self._update_enhanced_in_legacy(uid, update_data)
                result.success = result.legacy_result["success"]
                result.add_operation("legacy_update_enhanced")

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
                    result.cloud_result = self._update_enhanced_in_cloud(uid, update_data)
                    result.add_operation("cloud_update_enhanced")
                    total_operations += 1
                    if result.cloud_result["success"]:
                        success_count += 1
                    else:
                        result.add_error(f"Cloud update failed: {result.cloud_result['error']}")

                # Update in legacy if exists
                if legacy_exists:
                    result.legacy_result = self._update_enhanced_in_legacy(uid, update_data)
                    result.add_operation("legacy_update_enhanced")
                    total_operations += 1
                    if result.legacy_result["success"]:
                        success_count += 1
                    else:
                        result.add_error(f"Legacy update failed: {result.legacy_result['error']}")

                # Success if at least one update succeeded
                result.success = success_count > 0

            # Log the operation
            self._log_enhanced_provisioning_operation("update", uid, mode, result, update_data)

            return result

        except Exception as e:
            logger.error(f"Error updating enhanced subscriber {uid}: {str(e)}")
            result.add_error(f"Unexpected error: {str(e)}")
            return result

    def search_enhanced_subscriber(self, uid: str) -> Dict[str, Any]:
        """
        Search subscriber with enhanced data, cloud-first fallback
        """
        try:
            # Try cloud first
            cloud_subscriber = self._get_enhanced_from_cloud(uid)

            if cloud_subscriber:
                # Check if also in legacy for discrepancy detection
                legacy_subscriber = self._get_enhanced_from_legacy(uid)

                if legacy_subscriber:
                    # Compare enhanced fields for discrepancies
                    discrepancies = self._detect_enhanced_discrepancies(cloud_subscriber, legacy_subscriber)
                    if discrepancies:
                        # Log discrepancies
                        self.audit_service.log_action(
                            action="enhanced_subscriber_discrepancy",
                            resource="subscriber",
                            user="system",
                            details={
                                "uid": uid,
                                "discrepancies": discrepancies,
                                "cloud_plan": cloud_subscriber.get("planId"),
                                "legacy_plan": legacy_subscriber.get("plan_id"),
                            },
                        )

                    return {
                        "found": True,
                        "source": "both",
                        "primary_data": cloud_subscriber,
                        "secondary_data": legacy_subscriber,
                        "discrepancies": discrepancies,
                        "enhanced_fields": {
                            "cloud": self._extract_enhanced_summary(cloud_subscriber),
                            "legacy": self._extract_enhanced_summary(legacy_subscriber),
                        },
                    }
                else:
                    return {
                        "found": True,
                        "source": "cloud_only",
                        "primary_data": cloud_subscriber,
                        "enhanced_fields": {"cloud": self._extract_enhanced_summary(cloud_subscriber)},
                    }

            # Fallback to legacy
            legacy_subscriber = self._get_enhanced_from_legacy(uid)

            if legacy_subscriber:
                return {
                    "found": True,
                    "source": "legacy_only",
                    "primary_data": legacy_subscriber,
                    "enhanced_fields": {"legacy": self._extract_enhanced_summary(legacy_subscriber)},
                }

            # Not found in either system
            return {"found": False, "source": "none"}

        except Exception as e:
            logger.error(f"Error searching enhanced subscriber {uid}: {str(e)}")
            return {"found": False, "source": "error", "error": str(e)}

    def bulk_update_plan(
        self, plan_updates: List[Dict[str, Any]], mode: ProvisioningMode = ProvisioningMode.DUAL_PROV
    ) -> Dict[str, Any]:
        """
        Bulk update subscribers' plan and related services

        Args:
            plan_updates: List of {"uid": "...", "planId": "...", "addons": [...], "services": [...]}
            mode: Provisioning mode

        Returns:
            Bulk operation results
        """
        results = {
            "total_requested": len(plan_updates),
            "successful": 0,
            "failed": 0,
            "details": [],
            "started_at": datetime.utcnow().isoformat(),
        }

        for update_item in plan_updates:
            try:
                uid = update_item.get("uid")
                if not uid:
                    results["details"].append({"uid": "missing", "status": "ERROR", "message": "UID is required"})
                    results["failed"] += 1
                    continue

                # Prepare update data
                update_data = {
                    "planId": update_item.get("planId"),
                    "addons": update_item.get("addons", []),
                    "services": update_item.get("services", []),
                }

                # Remove None values
                update_data = {k: v for k, v in update_data.items() if v is not None}

                # Update subscriber
                result = self.update_enhanced_subscriber(uid, update_data, mode)

                if result.success:
                    results["successful"] += 1
                    results["details"].append(
                        {
                            "uid": uid,
                            "status": "SUCCESS",
                            "message": "Plan updated successfully",
                            "operations": result.operations_performed,
                        }
                    )
                else:
                    results["failed"] += 1
                    results["details"].append(
                        {
                            "uid": uid,
                            "status": "FAILED",
                            "message": "; ".join(result.errors),
                            "operations": result.operations_performed,
                        }
                    )

            except Exception as e:
                results["failed"] += 1
                results["details"].append(
                    {
                        "uid": update_item.get("uid", "unknown"),
                        "status": "ERROR",
                        "message": f"Processing error: {str(e)}",
                    }
                )
                logger.error(f"Error in bulk plan update for {update_item.get('uid')}: {str(e)}")

        results["completed_at"] = datetime.utcnow().isoformat()
        results["success_rate"] = (
            (results["successful"] / results["total_requested"] * 100) if results["total_requested"] > 0 else 0
        )

        return results

    def get_subscribers_by_plan(self, plan_id: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get all subscribers with specific plan ID
        """
        try:
            # Search in DynamoDB using planId GSI
            response = self.dynamodb_table.query(
                IndexName="planId-index",
                KeyConditionExpression="planId = :planId",
                ExpressionAttributeValues={":planId": plan_id},
                Limit=limit,
            )

            cloud_subscribers = response.get("Items", [])

            # Also search in legacy database
            legacy_subscribers = self._get_legacy_subscribers_by_plan(plan_id, limit)

            return {
                "plan_id": plan_id,
                "cloud_subscribers": cloud_subscribers,
                "legacy_subscribers": legacy_subscribers,
                "cloud_count": len(cloud_subscribers),
                "legacy_count": len(legacy_subscribers),
                "total_count": len(cloud_subscribers) + len(legacy_subscribers),
            }

        except Exception as e:
            logger.error(f"Error getting subscribers by plan {plan_id}: {str(e)}")
            return {
                "plan_id": plan_id,
                "error": str(e),
                "cloud_subscribers": [],
                "legacy_subscribers": [],
                "cloud_count": 0,
                "legacy_count": 0,
                "total_count": 0,
            }

    def get_addon_service_analytics(self) -> Dict[str, Any]:
        """
        Get analytics on addon and service usage across both systems
        """
        analytics = {
            "addon_distribution": {},
            "service_distribution": {},
            "plan_distribution": {},
            "barring_statistics": {"barred": 0, "not_barred": 0},
            "system_comparison": {"cloud_only": 0, "legacy_only": 0, "both": 0},
            "generated_at": datetime.utcnow().isoformat(),
        }

        try:
            # Analyze cloud data
            cloud_analytics = self._analyze_cloud_enhancements()
            analytics.update(cloud_analytics)

            # Analyze legacy data
            legacy_analytics = self._analyze_legacy_enhancements()

            # Combine analytics
            self._combine_analytics(analytics, legacy_analytics)

        except Exception as e:
            logger.error(f"Error generating addon/service analytics: {str(e)}")
            analytics["error"] = str(e)

        return analytics

    # Private helper methods for enhanced operations

    def _validate_enhanced_fields(self, subscriber: SubscriberData) -> List[str]:
        """Additional validation for enhanced fields"""
        errors = []

        # Validate addons
        if subscriber.addons:
            for addon in subscriber.addons:
                if len(addon) > 32:
                    errors.append(f'Addon "{addon}" exceeds 32 character limit')

        # Validate services
        if subscriber.services:
            for service in subscriber.services:
                if len(service) > 32:
                    errors.append(f'Service "{service}" exceeds 32 character limit')

        # Validate plan ID format (example validation)
        if subscriber.plan_id and not subscriber.plan_id.startswith("PLN_"):
            errors.append('Plan ID should start with "PLN_" prefix')

        return errors

    def _validate_update_data(self, update_data: Dict[str, Any]) -> List[str]:
        """Validate update data for enhanced fields"""
        errors = []

        # Validate status if provided
        if "status" in update_data and update_data["status"] not in self.supported_statuses:
            errors.append(f'Invalid status: {update_data["status"]}')

        # Validate barring if provided
        if "barring" in update_data:
            barring = update_data["barring"]
            if isinstance(barring, dict):
                if "odbic" in barring and barring["odbic"] not in self.supported_barring_states:
                    errors.append(f'Invalid odbic value: {barring["odbic"]}')
                if "odboc" in barring and barring["odboc"] not in self.supported_barring_states:
                    errors.append(f'Invalid odboc value: {barring["odboc"]}')

        # Validate addons if provided
        if "addons" in update_data:
            addons = update_data["addons"]
            if not isinstance(addons, list):
                errors.append("Addons must be a list")
            else:
                for addon in addons:
                    if not isinstance(addon, str) or len(addon) > 32:
                        errors.append(f"Invalid addon: {addon}")

        # Validate services if provided
        if "services" in update_data:
            services = update_data["services"]
            if not isinstance(services, list):
                errors.append("Services must be a list")
            else:
                for service in services:
                    if not isinstance(service, str) or len(service) > 32:
                        errors.append(f"Invalid service: {service}")

        return errors

    def _create_enhanced_in_cloud(self, subscriber: SubscriberData) -> Dict[str, Any]:
        """Create subscriber in cloud with enhanced data"""
        try:
            # Check if already exists
            if self._check_cloud_exists(subscriber.uid):
                return {"success": False, "error": "Subscriber already exists in cloud system"}

            # Create enhanced DynamoDB item
            cloud_item = subscriber.to_dynamodb_item()

            self.dynamodb_table.put_item(Item=cloud_item)

            return {
                "success": True,
                "data": cloud_item,
                "enhanced_fields_created": {
                    "planId": subscriber.plan_id,
                    "barring": subscriber.barring.to_dict() if subscriber.barring else None,
                    "addons": subscriber.addons,
                    "services": subscriber.services,
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_enhanced_in_legacy(self, subscriber: SubscriberData) -> Dict[str, Any]:
        """Create subscriber in legacy with enhanced data"""
        connection = get_legacy_db_connection()
        if not connection:
            return {"success": False, "error": "Cannot connect to legacy database"}

        try:
            with connection.cursor() as cursor:
                # Check if already exists
                if self._check_legacy_exists(subscriber.uid):
                    return {"success": False, "error": "Subscriber already exists in legacy system"}

                # Enhanced insert with all fields
                insert_query = """
                INSERT INTO subscribers (uid, imsi, msisdn, status, plan_id,
                                       barr_all, odbic, odboc, addons, services,
                                       apn, service_profile, roaming_allowed, data_limit,
                                       created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cursor.execute(insert_query, subscriber.to_mysql_values())
                connection.commit()

                return {
                    "success": True,
                    "rows_affected": cursor.rowcount,
                    "enhanced_fields_created": {
                        "plan_id": subscriber.plan_id,
                        "barr_all": subscriber.barring.bar_all if subscriber.barring else False,
                        "addons": subscriber.addons,
                        "services": subscriber.services,
                    },
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            connection.close()

    def _update_enhanced_in_cloud(self, uid: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update subscriber in cloud with enhanced data"""
        try:
            if not self._check_cloud_exists(uid):
                return {"success": False, "error": "Subscriber not found in cloud system"}

            # Build enhanced update expression
            update_expression = "SET updated_at = :updated_at"
            expression_values = {":updated_at": datetime.utcnow().isoformat()}
            expression_names = {}

            for key, value in update_data.items():
                if key not in ["uid", "subscriberId", "updated_at"]:
                    if key == "planId":
                        update_expression += f", planId = :planId"
                        expression_values[":planId"] = value
                    elif key == "barring" and isinstance(value, dict):
                        # Update nested barring object
                        for barring_key, barring_value in value.items():
                            update_expression += f", barring.{barring_key} = :barring_{barring_key}"
                            expression_values[f":barring_{barring_key}"] = barring_value
                    elif key in ["addons", "services"]:
                        update_expression += f", {key} = :{key}"
                        expression_values[f":{key}"] = value
                    else:
                        # Handle reserved keywords
                        attr_name = f"#{key}"
                        update_expression += f", {attr_name} = :{key}"
                        expression_names[attr_name] = key
                        expression_values[f":{key}"] = value

            update_kwargs = {
                "Key": {"subscriberId": uid},
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": expression_values,
            }

            if expression_names:
                update_kwargs["ExpressionAttributeNames"] = expression_names

            self.dynamodb_table.update_item(**update_kwargs)

            return {"success": True, "updated_fields": list(update_data.keys())}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _update_enhanced_in_legacy(self, uid: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update subscriber in legacy with enhanced data"""
        connection = get_legacy_db_connection()
        if not connection:
            return {"success": False, "error": "Cannot connect to legacy database"}

        try:
            with connection.cursor() as cursor:
                if not self._check_legacy_exists(uid):
                    return {"success": False, "error": "Subscriber not found in legacy system"}

                # Build enhanced update query
                set_clauses = ["updated_at = %s"]
                values = [datetime.utcnow()]

                for key, value in update_data.items():
                    if key == "planId":
                        set_clauses.append("plan_id = %s")
                        values.append(value)
                    elif key == "barring" and isinstance(value, dict):
                        if "barAll" in value:
                            set_clauses.append("barr_all = %s")
                            values.append(1 if value["barAll"] else 0)
                        if "odbic" in value:
                            set_clauses.append("odbic = %s")
                            values.append(value["odbic"])
                        if "odboc" in value:
                            set_clauses.append("odboc = %s")
                            values.append(value["odboc"])
                    elif key == "addons":
                        set_clauses.append("addons = %s")
                        values.append(json.dumps(value) if value else None)
                    elif key == "services":
                        set_clauses.append("services = %s")
                        values.append(json.dumps(value) if value else None)
                    elif key not in ["uid", "updated_at"]:
                        # Map other fields
                        db_field = key
                        if key == "roaming_allowed":
                            values.append(1 if value else 0)
                        else:
                            values.append(value)
                        set_clauses.append(f"{db_field} = %s")

                values.append(uid)  # For WHERE clause

                update_query = f"UPDATE subscribers SET {', '.join(set_clauses)} WHERE uid = %s"

                cursor.execute(update_query, values)
                connection.commit()

                return {"success": True, "rows_affected": cursor.rowcount}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            connection.close()

    def _get_enhanced_from_cloud(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get subscriber with enhanced data from cloud"""
        try:
            response = self.dynamodb_table.get_item(Key={"subscriberId": uid})
            item = response.get("Item")
            if item:
                # Convert Decimal to proper types
                return self._convert_dynamodb_item(item)
            return None
        except Exception as e:
            logger.error(f"Error getting enhanced data from cloud for {uid}: {str(e)}")
            return None

    def _get_enhanced_from_legacy(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get subscriber with enhanced data from legacy"""
        connection = get_legacy_db_connection()
        if not connection:
            return None

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT uid, imsi, msisdn, status, plan_id,
                              barr_all, odbic, odboc, addons, services,
                              apn, service_profile, roaming_allowed, data_limit,
                              created_at, updated_at
                       FROM subscribers WHERE uid = %s AND status != 'DELETED'""",
                    (uid,),
                )
                row = cursor.fetchone()
                if row:
                    # Convert datetime to ISO string
                    for key, value in row.items():
                        if hasattr(value, "isoformat"):
                            row[key] = value.isoformat()
                return row
        except Exception as e:
            logger.error(f"Error getting enhanced data from legacy for {uid}: {str(e)}")
            return None
        finally:
            connection.close()

    def _convert_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB item with Decimal handling"""
        converted = {}
        for key, value in item.items():
            if isinstance(value, Decimal):
                converted[key] = int(value) if value % 1 == 0 else float(value)
            else:
                converted[key] = value
        return converted

    def _detect_enhanced_discrepancies(self, cloud_data: Dict[str, Any], legacy_data: Dict[str, Any]) -> List[str]:
        """Detect discrepancies in enhanced fields"""
        discrepancies = []

        # Check planId vs plan_id
        cloud_plan = cloud_data.get("planId")
        legacy_plan = legacy_data.get("plan_id")
        if cloud_plan != legacy_plan:
            discrepancies.append(f"planId: cloud='{cloud_plan}' vs legacy='{legacy_plan}'")

        # Check barring settings
        cloud_barring = cloud_data.get("barring", {})
        legacy_barr_all = bool(legacy_data.get("barr_all", 0))
        cloud_barr_all = cloud_barring.get("barAll", False)
        if cloud_barr_all != legacy_barr_all:
            discrepancies.append(f"barAll: cloud='{cloud_barr_all}' vs legacy='{legacy_barr_all}'")

        # Check addons
        cloud_addons = set(cloud_data.get("addons", []))
        try:
            legacy_addons_raw = legacy_data.get("addons")
            legacy_addons = set(json.loads(legacy_addons_raw) if legacy_addons_raw else [])
        except (json.JSONDecodeError, TypeError):
            legacy_addons = set()

        if cloud_addons != legacy_addons:
            discrepancies.append(f"addons: cloud={cloud_addons} vs legacy={legacy_addons}")

        # Check services
        cloud_services = set(cloud_data.get("services", []))
        try:
            legacy_services_raw = legacy_data.get("services")
            legacy_services = set(json.loads(legacy_services_raw) if legacy_services_raw else [])
        except (json.JSONDecodeError, TypeError):
            legacy_services = set()

        if cloud_services != legacy_services:
            discrepancies.append(f"services: cloud={cloud_services} vs legacy={legacy_services}")

        return discrepancies

    def _extract_enhanced_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract enhanced field summary for response"""
        summary = {}

        # Plan information
        summary["planId"] = data.get("planId") or data.get("plan_id")

        # Barring information
        if "barring" in data:
            summary["barring"] = data["barring"]
        elif "barr_all" in data:
            summary["barring"] = {
                "barAll": bool(data.get("barr_all", 0)),
                "odbic": data.get("odbic", "notbarred"),
                "odboc": data.get("odboc", "notbarred"),
            }

        # Addons and services
        summary["addons"] = data.get("addons", [])
        summary["services"] = data.get("services", [])

        # If legacy JSON fields, parse them
        try:
            if isinstance(summary["addons"], str):
                summary["addons"] = json.loads(summary["addons"])
        except (json.JSONDecodeError, TypeError):
            summary["addons"] = []

        try:
            if isinstance(summary["services"], str):
                summary["services"] = json.loads(summary["services"])
        except (json.JSONDecodeError, TypeError):
            summary["services"] = []

        return summary

    def _check_cloud_exists(self, uid: str) -> bool:
        """Check if subscriber exists in cloud"""
        try:
            response = self.dynamodb_table.get_item(Key={"subscriberId": uid})
            return "Item" in response
        except Exception:
            return False

    def _check_legacy_exists(self, uid: str) -> bool:
        """Check if subscriber exists in legacy"""
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

    def _rollback_cloud_create(self, uid: str) -> Dict[str, Any]:
        """Rollback cloud creation"""
        try:
            self.dynamodb_table.delete_item(Key={"subscriberId": uid})
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_legacy_subscribers_by_plan(self, plan_id: str, limit: int) -> List[Dict[str, Any]]:
        """Get legacy subscribers by plan ID"""
        connection = get_legacy_db_connection()
        if not connection:
            return []

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT uid, imsi, msisdn, status, plan_id, addons, services, created_at
                       FROM subscribers WHERE plan_id = %s AND status != 'DELETED' LIMIT %s""",
                    (plan_id, limit),
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting legacy subscribers by plan {plan_id}: {str(e)}")
            return []
        finally:
            connection.close()

    def _analyze_cloud_enhancements(self) -> Dict[str, Any]:
        """Analyze enhanced fields in cloud data"""
        # This would typically scan DynamoDB with pagination
        # For now, return sample structure
        return {"cloud_addon_distribution": {}, "cloud_service_distribution": {}, "cloud_plan_distribution": {}}

    def _analyze_legacy_enhancements(self) -> Dict[str, Any]:
        """Analyze enhanced fields in legacy data"""
        # This would query MySQL with aggregation
        # For now, return sample structure
        return {"legacy_addon_distribution": {}, "legacy_service_distribution": {}, "legacy_plan_distribution": {}}

    def _combine_analytics(self, main_analytics: Dict[str, Any], legacy_analytics: Dict[str, Any]):
        """Combine cloud and legacy analytics"""
        # Combine distributions
        for key in ["addon_distribution", "service_distribution", "plan_distribution"]:
            cloud_key = f"cloud_{key}"
            legacy_key = f"legacy_{key}"

            if cloud_key in main_analytics and legacy_key in legacy_analytics:
                # Merge distributions
                combined = main_analytics[cloud_key].copy()
                for item, count in legacy_analytics[legacy_key].items():
                    combined[item] = combined.get(item, 0) + count
                main_analytics[key] = combined

    def _log_enhanced_provisioning_operation(
        self,
        operation: str,
        uid: str,
        mode: ProvisioningMode,
        result: ProvisioningResult,
        subscriber_data: Union[SubscriberData, Dict[str, Any]],
    ):
        """Log enhanced provisioning operation"""
        try:
            # Extract enhanced field details
            if isinstance(subscriber_data, SubscriberData):
                enhanced_details = {
                    "planId": subscriber_data.plan_id,
                    "has_addons": len(subscriber_data.addons) > 0,
                    "has_services": len(subscriber_data.services) > 0,
                    "barring_enabled": subscriber_data.barring.bar_all if subscriber_data.barring else False,
                }
            else:
                enhanced_details = {
                    "planId": subscriber_data.get("planId"),
                    "has_addons": len(subscriber_data.get("addons", [])) > 0,
                    "has_services": len(subscriber_data.get("services", [])) > 0,
                    "barring_updated": "barring" in subscriber_data,
                }

            self.audit_service.log_action(
                action=f"enhanced_provisioning_{operation}",
                resource="subscriber",
                user="system",
                details={
                    "uid": uid,
                    "mode": mode.value,
                    "success": result.success,
                    "operations": result.operations_performed,
                    "errors": result.errors,
                    "rollback_performed": result.rollback_performed,
                    "enhanced_fields": enhanced_details,
                },
            )
        except Exception as e:
            logger.error(f"Failed to log enhanced provisioning operation: {str(e)}")


# Export service instance
enhanced_provisioning_service = EnhancedProvisioningService()
