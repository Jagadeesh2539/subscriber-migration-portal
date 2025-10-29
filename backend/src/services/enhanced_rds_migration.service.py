#!/usr/bin/env python3
"""
Enhanced RDS Migration Service - Handles rich subscriber data migration
Supports planId, barring controls, addons, services, and all extended fields
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from config.database import get_dynamodb_table, get_legacy_db_connection
from models.subscriber.model import BarringControls, SubscriberData
from services.audit.service import AuditService
from utils.logger import get_logger
from utils.validation import InputValidator

logger = get_logger(__name__)

class EnhancedRDSMigrationService:
    """Enhanced RDS Migration Service with rich subscriber data support"""
    
    def __init__(self):
        self.dynamodb_table = get_dynamodb_table('SUBSCRIBER_TABLE_NAME')
        self.audit_service = AuditService()
        self.validator = InputValidator()
        
        # Migration tracking
        self.migration_table = get_dynamodb_table('MIGRATION_JOBS_TABLE_NAME')
        
        # Supported addon and service types (can be configured)
        self.supported_addons = {
            'ADD_INTL_ROAM', 'ADD_OTT_PACK', 'ADD_DATA_BOOST', 
            'ADD_VOICE_PACK', 'ADD_SMS_PACK', 'ADD_MUSIC_STREAM',
            'ADD_VIDEO_STREAM', 'ADD_CLOUD_STORAGE', 'ADD_SECURITY'
        }
        
        self.supported_services = {
            'VOLTE', '5G', 'VoWiFi', '4G', '3G', '2G', 
            'SMS', 'MMS', 'DATA', 'VOICE', 'USSD', 'STK'
        }
    
    def migrate_subscriber_batch(self, subscriber_uids: List[str], 
                                migration_id: str) -> Dict[str, Any]:
        """
        Migrate batch of subscribers from RDS to DynamoDB with enhanced data
        
        Args:
            subscriber_uids: List of UIDs to migrate
            migration_id: Migration job ID for tracking
        
        Returns:
            Migration results with detailed per-subscriber status
        """
        results = {
            'migration_id': migration_id,
            'total_requested': len(subscriber_uids),
            'successful': 0,
            'failed': 0,
            'already_exists': 0,
            'not_found': 0,
            'details': [],
            'started_at': datetime.utcnow().isoformat()
        }
        
        for uid in subscriber_uids:
            try:
                result = self._migrate_single_subscriber(uid, migration_id)
                results['details'].append(result)
                
                if result['status'] == 'SUCCESS':
                    results['successful'] += 1
                elif result['status'] == 'ALREADY_EXISTS':
                    results['already_exists'] += 1
                elif result['status'] == 'NOT_FOUND':
                    results['not_found'] += 1
                else:
                    results['failed'] += 1
                    
            except Exception as e:
                error_result = {
                    'uid': uid,
                    'status': 'ERROR',
                    'message': f'Processing error: {str(e)}',
                    'error_details': str(e)
                }
                results['details'].append(error_result)
                results['failed'] += 1
                logger.error(f"Error migrating subscriber {uid}: {str(e)}")
        
        results['completed_at'] = datetime.utcnow().isoformat()
        results['success_rate'] = (results['successful'] / results['total_requested'] * 100) if results['total_requested'] > 0 else 0
        
        # Store batch results
        self._store_batch_results(results)
        
        return results
    
    def _migrate_single_subscriber(self, uid: str, migration_id: str) -> Dict[str, Any]:
        """
        Migrate single subscriber with enhanced data mapping
        """
        try:
            # Step 1: Fetch from RDS with enhanced fields
            legacy_data = self._fetch_enhanced_legacy_data(uid)
            
            if not legacy_data:
                return {
                    'uid': uid,
                    'status': 'NOT_FOUND',
                    'message': 'Subscriber not found in legacy RDS system'
                }
            
            # Step 2: Check if already exists in DynamoDB
            if self._check_dynamodb_exists(uid):
                return {
                    'uid': uid,
                    'status': 'ALREADY_EXISTS',
                    'message': 'Subscriber already exists in DynamoDB',
                    'legacy_data': self._sanitize_for_response(legacy_data)
                }
            
            # Step 3: Transform and validate enhanced data
            subscriber = SubscriberData.from_mysql_row(legacy_data)
            subscriber.normalize()
            
            validation_errors = subscriber.validate()
            if validation_errors:
                return {
                    'uid': uid,
                    'status': 'VALIDATION_FAILED',
                    'message': 'Data validation failed',
                    'validation_errors': validation_errors,
                    'legacy_data': self._sanitize_for_response(legacy_data)
                }
            
            # Step 4: Migrate to DynamoDB with enhanced fields
            cloud_item = subscriber.to_dynamodb_item()
            cloud_item['migrated_from'] = 'legacy_rds'
            cloud_item['migrated_at'] = datetime.utcnow().isoformat()
            cloud_item['migration_id'] = migration_id
            
            self.dynamodb_table.put_item(Item=cloud_item)
            
            # Log successful migration
            self._log_migration_event(migration_id, uid, 'SUCCESS', 
                                    'Successfully migrated with enhanced data', 
                                    legacy_data, cloud_item)
            
            return {
                'uid': uid,
                'status': 'SUCCESS',
                'message': 'Successfully migrated to DynamoDB',
                'legacy_data': self._sanitize_for_response(legacy_data),
                'cloud_data': self._sanitize_dynamodb_item(cloud_item),
                'enhanced_fields_migrated': {
                    'planId': subscriber.plan_id,
                    'barring_controls': subscriber.barring.to_dict() if subscriber.barring else None,
                    'addons_count': len(subscriber.addons),
                    'services_count': len(subscriber.services)
                }
            }
            
        except Exception as e:
            logger.error(f"Error migrating subscriber {uid}: {str(e)}")
            return {
                'uid': uid,
                'status': 'ERROR',
                'message': f'Migration failed: {str(e)}',
                'error_details': str(e)
            }
    
    def _fetch_enhanced_legacy_data(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Fetch subscriber data from RDS with all enhanced fields
        """
        connection = get_legacy_db_connection()
        if not connection:
            raise RuntimeError("Cannot connect to legacy database")
        
        try:
            with connection.cursor() as cursor:
                # Enhanced query with all fields including JSON columns
                query = """
                SELECT uid, imsi, msisdn, status, plan_id,
                       barr_all, odbic, odboc, addons, services,
                       apn, service_profile, roaming_allowed, data_limit,
                       created_at, updated_at
                FROM subscribers 
                WHERE uid = %s AND status != 'DELETED'
                """
                
                cursor.execute(query, (uid,))
                result = cursor.fetchone()
                
                if result:
                    # Convert datetime objects to ISO strings
                    for key, value in result.items():
                        if hasattr(value, 'isoformat'):
                            result[key] = value.isoformat()
                
                return result
                
        except Exception as e:
            logger.error(f"Error fetching enhanced legacy data for {uid}: {str(e)}")
            raise
        finally:
            connection.close()
    
    def _check_dynamodb_exists(self, uid: str) -> bool:
        """Check if subscriber exists in DynamoDB"""
        try:
            response = self.dynamodb_table.get_item(
                Key={'subscriberId': uid}
            )
            return 'Item' in response
        except Exception as e:
            logger.error(f"Error checking DynamoDB existence for {uid}: {str(e)}")
            return False
    
    def validate_and_fix_legacy_data(self, limit: int = 1000) -> Dict[str, Any]:
        """
        Validate legacy data and provide fix recommendations
        
        Args:
            limit: Number of records to validate
        
        Returns:
            Validation report with issues and fixes
        """
        connection = get_legacy_db_connection()
        if not connection:
            raise RuntimeError("Cannot connect to legacy database")
        
        validation_results = {
            'total_checked': 0,
            'valid_records': 0,
            'issues_found': 0,
            'issues': [],
            'fix_recommendations': [],
            'started_at': datetime.utcnow().isoformat()
        }
        
        try:
            with connection.cursor() as cursor:
                # Get sample of subscribers for validation
                cursor.execute(
                    "SELECT * FROM subscribers WHERE status != 'DELETED' LIMIT %s",
                    (limit,)
                )
                
                for row in cursor.fetchall():
                    validation_results['total_checked'] += 1
                    
                    try:
                        # Create subscriber model and validate
                        subscriber = SubscriberData.from_mysql_row(row)
                        validation_errors = subscriber.validate()
                        
                        if validation_errors:
                            validation_results['issues_found'] += 1
                            validation_results['issues'].append({
                                'uid': subscriber.uid,
                                'errors': validation_errors,
                                'current_data': self._sanitize_for_response(row)
                            })
                        else:
                            validation_results['valid_records'] += 1
                    
                    except Exception as e:
                        validation_results['issues_found'] += 1
                        validation_results['issues'].append({
                            'uid': row.get('uid', 'unknown'),
                            'errors': [f'Processing error: {str(e)}'],
                            'current_data': self._sanitize_for_response(row)
                        })
        
        finally:
            connection.close()
        
        # Generate fix recommendations
        validation_results['fix_recommendations'] = self._generate_fix_recommendations(
            validation_results['issues']
        )
        
        validation_results['completed_at'] = datetime.utcnow().isoformat()
        validation_results['accuracy_percentage'] = (
            validation_results['valid_records'] / validation_results['total_checked'] * 100
        ) if validation_results['total_checked'] > 0 else 0
        
        return validation_results
    
    def _generate_fix_recommendations(self, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate SQL fix recommendations based on validation issues"""
        recommendations = []
        
        # Count issue types
        issue_counts = {}
        for issue in issues:
            for error in issue['errors']:
                if error not in issue_counts:
                    issue_counts[error] = []
                issue_counts[error].append(issue['uid'])
        
        # Generate SQL fixes for common issues
        for error_type, uids in issue_counts.items():
            uid_list = "', '".join(uids[:10])  # Limit examples
            
            if 'IMSI must be' in error_type:
                recommendations.append({
                    'issue': error_type,
                    'affected_count': len(uids),
                    'sql_fix': f"UPDATE subscribers SET imsi = REGEXP_REPLACE(imsi, '[^0-9]', '') WHERE uid IN ('{uid_list}');",
                    'description': 'Remove non-digit characters from IMSI'
                })
            
            elif 'MSISDN must be' in error_type:
                recommendations.append({
                    'issue': error_type,
                    'affected_count': len(uids),
                    'sql_fix': f"UPDATE subscribers SET msisdn = CONCAT('+', REGEXP_REPLACE(msisdn, '[^0-9]', '')) WHERE uid IN ('{uid_list}');",
                    'description': 'Normalize MSISDN to E.164 format'
                })
            
            elif 'Status must be' in error_type:
                recommendations.append({
                    'issue': error_type,
                    'affected_count': len(uids),
                    'sql_fix': f"UPDATE subscribers SET status = 'ACTIVE' WHERE status NOT IN ('ACTIVE','INACTIVE','SUSPENDED','DELETED') AND uid IN ('{uid_list}');",
                    'description': 'Set invalid status values to ACTIVE'
                })
            
            elif 'ODBIC must be' in error_type or 'ODBOC must be' in error_type:
                recommendations.append({
                    'issue': error_type,
                    'affected_count': len(uids),
                    'sql_fix': f"UPDATE subscribers SET odbic = 'notbarred', odboc = 'notbarred' WHERE uid IN ('{uid_list}');",
                    'description': 'Set invalid barring controls to default values'
                })
        
        return recommendations
    
    def bulk_migrate_by_plan(self, plan_ids: List[str], migration_id: str) -> Dict[str, Any]:
        """
        Migrate all subscribers with specific plan IDs
        
        Args:
            plan_ids: List of plan IDs to migrate
            migration_id: Migration job ID
        
        Returns:
            Migration results grouped by plan
        """
        connection = get_legacy_db_connection()
        if not connection:
            raise RuntimeError("Cannot connect to legacy database")
        
        results = {
            'migration_id': migration_id,
            'plan_results': {},
            'total_found': 0,
            'total_migrated': 0,
            'total_failed': 0,
            'started_at': datetime.utcnow().isoformat()
        }
        
        try:
            with connection.cursor() as cursor:
                for plan_id in plan_ids:
                    # Get all subscribers with this plan
                    cursor.execute(
                        "SELECT uid FROM subscribers WHERE plan_id = %s AND status != 'DELETED'",
                        (plan_id,)
                    )
                    
                    uids = [row['uid'] for row in cursor.fetchall()]
                    results['total_found'] += len(uids)
                    
                    if uids:
                        # Migrate batch
                        plan_result = self.migrate_subscriber_batch(uids, f"{migration_id}_PLAN_{plan_id}")
                        results['plan_results'][plan_id] = plan_result
                        results['total_migrated'] += plan_result['successful']
                        results['total_failed'] += plan_result['failed']
                    else:
                        results['plan_results'][plan_id] = {
                            'message': 'No subscribers found with this plan',
                            'total_requested': 0
                        }
        
        finally:
            connection.close()
        
        results['completed_at'] = datetime.utcnow().isoformat()
        
        return results
    
    def get_migration_analytics(self, migration_id: str) -> Dict[str, Any]:
        """
        Get detailed analytics for migration including enhanced field analysis
        """
        batch_results = self._get_batch_results(migration_id)
        if not batch_results:
            return {'error': 'Migration not found'}
        
        analytics = {
            'migration_id': migration_id,
            'summary': batch_results,
            'enhanced_field_analysis': self._analyze_enhanced_fields(batch_results),
            'error_analysis': self._analyze_errors(batch_results),
            'performance_metrics': self._calculate_performance_metrics(batch_results)
        }
        
        return analytics
    
    def _analyze_enhanced_fields(self, batch_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze enhanced fields in migration results"""
        analysis = {
            'plan_distribution': {},
            'barring_analysis': {'barred_count': 0, 'not_barred_count': 0},
            'addon_analysis': {},
            'service_analysis': {},
            'data_completeness': {
                'with_plan_id': 0,
                'with_addons': 0,
                'with_services': 0,
                'with_data_limit': 0
            }
        }
        
        for detail in batch_results.get('details', []):
            if detail['status'] == 'SUCCESS' and 'enhanced_fields_migrated' in detail:
                enhanced = detail['enhanced_fields_migrated']
                
                # Plan distribution
                plan_id = enhanced.get('planId', 'Unknown')
                analysis['plan_distribution'][plan_id] = analysis['plan_distribution'].get(plan_id, 0) + 1
                
                # Data completeness
                if enhanced.get('planId'):
                    analysis['data_completeness']['with_plan_id'] += 1
                if enhanced.get('addons_count', 0) > 0:
                    analysis['data_completeness']['with_addons'] += 1
                if enhanced.get('services_count', 0) > 0:
                    analysis['data_completeness']['with_services'] += 1
                
                # Barring analysis
                barring = enhanced.get('barring_controls', {})
                if barring and barring.get('barAll'):
                    analysis['barring_analysis']['barred_count'] += 1
                else:
                    analysis['barring_analysis']['not_barred_count'] += 1
        
        return analysis
    
    def _analyze_errors(self, batch_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze error patterns in migration results"""
        error_analysis = {
            'error_types': {},
            'validation_issues': {},
            'common_patterns': []
        }
        
        for detail in batch_results.get('details', []):
            if detail['status'] in ['ERROR', 'VALIDATION_FAILED']:
                # Error type analysis
                error_type = detail['status']
                error_analysis['error_types'][error_type] = error_analysis['error_types'].get(error_type, 0) + 1
                
                # Validation issue analysis
                if 'validation_errors' in detail:
                    for error in detail['validation_errors']:
                        error_analysis['validation_issues'][error] = error_analysis['validation_issues'].get(error, 0) + 1
        
        return error_analysis
    
    def _calculate_performance_metrics(self, batch_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate performance metrics"""
        started_at = datetime.fromisoformat(batch_results['started_at'].replace('Z', '+00:00'))
        completed_at = datetime.fromisoformat(batch_results['completed_at'].replace('Z', '+00:00'))
        duration_seconds = (completed_at - started_at).total_seconds()
        
        return {
            'duration_seconds': duration_seconds,
            'duration_minutes': round(duration_seconds / 60, 2),
            'records_per_second': round(batch_results['total_requested'] / duration_seconds, 2) if duration_seconds > 0 else 0,
            'success_rate': batch_results.get('success_rate', 0),
            'throughput_rating': self._get_throughput_rating(batch_results['total_requested'], duration_seconds)
        }
    
    def _get_throughput_rating(self, total_records: int, duration_seconds: float) -> str:
        """Get throughput performance rating"""
        if duration_seconds <= 0:
            return 'N/A'
        
        records_per_second = total_records / duration_seconds
        
        if records_per_second >= 50:
            return 'Excellent'
        elif records_per_second >= 20:
            return 'Good'
        elif records_per_second >= 10:
            return 'Average'
        else:
            return 'Needs Improvement'
    
    def _sanitize_for_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize sensitive data for API responses"""
        if not data:
            return {}
        
        sanitized = {}
        for key, value in data.items():
            if key in ['imsi', 'msisdn']:
                # Mask PII
                sanitized[key] = f"{str(value)[:3]}***{str(value)[-3:]}" if value else None
            elif key == 'addons' and value:
                # Show count instead of actual addons for privacy
                try:
                    addon_list = json.loads(value) if isinstance(value, str) else value
                    sanitized[key + '_count'] = len(addon_list)
                except (json.JSONDecodeError, TypeError):
                    sanitized[key + '_count'] = 0
            elif key == 'services' and value:
                # Show count instead of actual services for privacy
                try:
                    service_list = json.loads(value) if isinstance(value, str) else value
                    sanitized[key + '_count'] = len(service_list)
                except (json.JSONDecodeError, TypeError):
                    sanitized[key + '_count'] = 0
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize DynamoDB item for response"""
        sanitized = {}
        for key, value in item.items():
            if key in ['imsi', 'msisdn']:
                sanitized[key] = f"{str(value)[:3]}***{str(value)[-3:]}" if value else None
            elif isinstance(value, Decimal):
                sanitized[key] = float(value)
            elif key in ['addons', 'services'] and isinstance(value, list):
                sanitized[key + '_count'] = len(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _log_migration_event(self, migration_id: str, uid: str, status: str, 
                           message: str, legacy_data: Dict[str, Any], 
                           cloud_data: Dict[str, Any] = None):
        """Log migration event with enhanced data details"""
        try:
            log_entry = {
                'id': f"{migration_id}_{uid}_{int(datetime.utcnow().timestamp())}",
                'migration_id': migration_id,
                'uid': uid,
                'status': status,
                'message': message,
                'timestamp': datetime.utcnow().isoformat(),
                'legacy_plan_id': legacy_data.get('plan_id'),
                'has_addons': bool(legacy_data.get('addons')),
                'has_services': bool(legacy_data.get('services')),
                'barring_enabled': bool(legacy_data.get('barr_all')),
                'cloud_migrated': cloud_data is not None
            }
            
            audit_table = get_dynamodb_table('AUDIT_LOG_TABLE_NAME')
            audit_table.put_item(Item=log_entry)
            
        except Exception as e:
            logger.error(f"Failed to log enhanced migration event: {str(e)}")
    
    def _store_batch_results(self, results: Dict[str, Any]):
        """Store batch migration results in DynamoDB"""
        try:
            # Convert for DynamoDB storage
            item = {
                'id': results['migration_id'],
                'migration_type': 'enhanced_rds_migration',
                'status': 'COMPLETED',
                'total_requested': Decimal(str(results['total_requested'])),
                'successful': Decimal(str(results['successful'])),
                'failed': Decimal(str(results['failed'])),
                'already_exists': Decimal(str(results['already_exists'])),
                'not_found': Decimal(str(results['not_found'])),
                'success_rate': Decimal(str(round(results['success_rate'], 2))),
                'started_at': results['started_at'],
                'completed_at': results['completed_at']
            }
            
            self.migration_table.put_item(Item=item)
            
        except Exception as e:
            logger.error(f"Failed to store batch results: {str(e)}")
    
    def _get_batch_results(self, migration_id: str) -> Optional[Dict[str, Any]]:
        """Get stored batch results"""
        try:
            response = self.migration_table.get_item(
                Key={'id': migration_id}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting batch results {migration_id}: {str(e)}")
            return None

# Export service instance
enhanced_rds_migration_service = EnhancedRDSMigrationService()