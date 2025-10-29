#!/usr/bin/env python3
"""
Subscriber Service - Dual Database Operations
Handles subscriber operations across Cloud (DynamoDB) and Legacy (MySQL RDS) systems
"""

import csv
import io
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from dataclasses import dataclass, asdict

from config.database import get_dynamodb_table, get_legacy_db_connection
from utils.logger import get_logger
from utils.retry import retry_with_backoff
from utils.validation import InputValidator

logger = get_logger(__name__)

@dataclass
class SubscriberData:
    """Standard subscriber data structure"""
    uid: str
    imsi: str
    msisdn: str
    status: str = 'ACTIVE'
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    apn: Optional[str] = None
    service_profile: Optional[str] = None
    roaming_allowed: bool = True
    data_limit: Optional[int] = None
    source_system: Optional[str] = None
    
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = {
            'subscriberId': self.uid,
            'uid': self.uid,
            'imsi': self.imsi,
            'msisdn': self.msisdn,
            'status': self.status,
            'created_at': self.created_at or datetime.utcnow().isoformat(),
            'updated_at': self.updated_at or datetime.utcnow().isoformat(),
            'roaming_allowed': self.roaming_allowed
        }
        
        # Add optional fields
        if self.apn:
            item['apn'] = self.apn
        if self.service_profile:
            item['service_profile'] = self.service_profile
        if self.data_limit:
            item['data_limit'] = Decimal(str(self.data_limit))
        if self.source_system:
            item['source_system'] = self.source_system
            
        return item
    
    def to_mysql_values(self) -> tuple:
        """Convert to MySQL INSERT/UPDATE values"""
        return (
            self.uid,
            self.imsi,
            self.msisdn,
            self.status,
            self.created_at or datetime.utcnow().isoformat(),
            self.updated_at or datetime.utcnow().isoformat(),
            self.apn,
            self.service_profile,
            self.roaming_allowed,
            self.data_limit
        )

class SubscriberService:
    """Service for subscriber operations with dual database support"""
    
    def __init__(self):
        self.dynamodb_table = get_dynamodb_table('SUBSCRIBER_TABLE_NAME')
        self.current_prov_mode = os.environ.get('PROV_MODE', 'dual')
        self.validator = InputValidator()
    
    def create_subscriber(self, data: Dict[str, Any], prov_mode: str = None) -> Dict[str, Any]:
        """
        Create subscriber in specified provisioning mode(s)
        """
        prov_mode = prov_mode or self.current_prov_mode
        
        # Create subscriber data object
        subscriber = SubscriberData(
            uid=data['uid'],
            imsi=data['imsi'],
            msisdn=data.get('msisdn', ''),
            status=data.get('status', 'ACTIVE'),
            apn=data.get('apn'),
            service_profile=data.get('service_profile'),
            roaming_allowed=data.get('roaming_allowed', True),
            data_limit=data.get('data_limit'),
            source_system='api_create'
        )
        
        results = {'cloud': None, 'legacy': None}
        errors = []
        
        # Create in cloud (DynamoDB)
        if prov_mode in ['cloud', 'dual']:
            try:
                results['cloud'] = self._create_in_dynamodb(subscriber)
                logger.info(f"Subscriber {subscriber.uid} created in DynamoDB")
            except Exception as e:
                error_msg = f"DynamoDB creation failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                results['cloud'] = {'status': 'error', 'message': str(e)}
        
        # Create in legacy (MySQL)
        if prov_mode in ['legacy', 'dual']:
            try:
                results['legacy'] = self._create_in_mysql(subscriber)
                logger.info(f"Subscriber {subscriber.uid} created in MySQL")
            except Exception as e:
                error_msg = f"MySQL creation failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                results['legacy'] = {'status': 'error', 'message': str(e)}
        
        # Determine overall success
        successful_systems = [k for k, v in results.items() if v and v.get('status') == 'success']
        
        return {
            'subscriber_id': subscriber.uid,
            'provisioning_mode': prov_mode,
            'results': results,
            'summary': {
                'successful': len(successful_systems),
                'failed': len([k for k, v in results.items() if v and v.get('status') == 'error']),
                'systems': successful_systems,
                'errors': errors
            },
            'created_at': subscriber.created_at or datetime.utcnow().isoformat()
        }
    
    def get_subscribers(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get subscribers from specified systems with filtering and pagination
        """
        source = criteria.get('source', 'all')
        limit = criteria.get('limit', 50)
        offset = criteria.get('offset', 0)
        
        subscribers = []
        cloud_count = 0
        legacy_count = 0
        total_count = 0
        
        # Get from cloud (DynamoDB)
        if source in ['all', 'cloud']:
            try:
                cloud_result = self._get_from_dynamodb(criteria)
                cloud_subscribers = cloud_result['subscribers']
                cloud_count = len(cloud_subscribers)
                
                # Mark source
                for sub in cloud_subscribers:
                    sub['source'] = 'cloud'
                
                subscribers.extend(cloud_subscribers)
                
            except Exception as e:
                logger.error(f"Error getting subscribers from DynamoDB: {str(e)}")
        
        # Get from legacy (MySQL)
        if source in ['all', 'legacy']:
            try:
                legacy_result = self._get_from_mysql(criteria)
                legacy_subscribers = legacy_result['subscribers']
                legacy_count = len(legacy_subscribers)
                
                # Mark source
                for sub in legacy_subscribers:
                    sub['source'] = 'legacy'
                
                subscribers.extend(legacy_subscribers)
                
            except Exception as e:
                logger.error(f"Error getting subscribers from MySQL: {str(e)}")
        
        # Apply pagination to combined results
        total_count = len(subscribers)
        
        # Sort if specified
        sort_by = criteria.get('sort_by', 'created_at')
        sort_order = criteria.get('sort_order', 'desc')
        
        if sort_by in ['created_at', 'updated_at', 'status', 'uid']:
            reverse = sort_order.lower() == 'desc'
            subscribers.sort(key=lambda x: x.get(sort_by, ''), reverse=reverse)
        
        # Apply pagination
        paginated_subscribers = subscribers[offset:offset + limit]
        
        return {
            'subscribers': paginated_subscribers,
            'total_count': total_count,
            'cloud_count': cloud_count,
            'legacy_count': legacy_count,
            'returned_count': len(paginated_subscribers)
        }
    
    def get_subscriber_by_id(self, subscriber_id: str) -> Optional[Dict[str, Any]]:
        """
        Get single subscriber from all configured systems
        """
        results = {'cloud': None, 'legacy': None}
        
        # Try DynamoDB first
        try:
            cloud_subscriber = self._get_by_id_from_dynamodb(subscriber_id)
            if cloud_subscriber:
                cloud_subscriber['source'] = 'cloud'
                results['cloud'] = cloud_subscriber
        except Exception as e:
            logger.error(f"Error getting subscriber from DynamoDB: {str(e)}")
        
        # Try MySQL
        try:
            legacy_subscriber = self._get_by_id_from_mysql(subscriber_id)
            if legacy_subscriber:
                legacy_subscriber['source'] = 'legacy'
                results['legacy'] = legacy_subscriber
        except Exception as e:
            logger.error(f"Error getting subscriber from MySQL: {str(e)}")
        
        # Return the first found, preferring cloud
        if results['cloud']:
            # Add legacy data if available
            if results['legacy']:
                results['cloud']['also_in_legacy'] = True
                results['cloud']['legacy_data'] = results['legacy']
            return results['cloud']
        elif results['legacy']:
            return results['legacy']
        
        return None
    
    def update_subscriber(self, subscriber_id: str, data: Dict[str, Any], prov_mode: str = None) -> Dict[str, Any]:
        """
        Update subscriber in specified provisioning mode(s)
        """
        prov_mode = prov_mode or self.current_prov_mode
        
        # Add updated timestamp
        data['updated_at'] = datetime.utcnow().isoformat()
        
        results = {'cloud': None, 'legacy': None}
        errors = []
        found = False
        
        # Update in cloud (DynamoDB)
        if prov_mode in ['cloud', 'dual']:
            try:
                result = self._update_in_dynamodb(subscriber_id, data)
                results['cloud'] = result
                if result['found']:
                    found = True
                logger.info(f"Subscriber {subscriber_id} updated in DynamoDB")
            except Exception as e:
                error_msg = f"DynamoDB update failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                results['cloud'] = {'status': 'error', 'found': False, 'message': str(e)}
        
        # Update in legacy (MySQL)
        if prov_mode in ['legacy', 'dual']:
            try:
                result = self._update_in_mysql(subscriber_id, data)
                results['legacy'] = result
                if result['found']:
                    found = True
                logger.info(f"Subscriber {subscriber_id} updated in MySQL")
            except Exception as e:
                error_msg = f"MySQL update failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                results['legacy'] = {'status': 'error', 'found': False, 'message': str(e)}
        
        successful_systems = [k for k, v in results.items() if v and v.get('status') == 'success']
        
        return {
            'subscriber_id': subscriber_id,
            'found': found,
            'provisioning_mode': prov_mode,
            'results': results,
            'summary': {
                'successful': len(successful_systems),
                'failed': len([k for k, v in results.items() if v and v.get('status') == 'error']),
                'systems': successful_systems,
                'errors': errors
            },
            'updated_at': data['updated_at']
        }
    
    def delete_subscriber(self, subscriber_id: str, soft_delete: bool = True, prov_mode: str = None) -> Dict[str, Any]:
        """
        Delete subscriber from specified provisioning mode(s)
        """
        prov_mode = prov_mode or self.current_prov_mode
        
        results = {'cloud': None, 'legacy': None}
        errors = []
        found = False
        
        # Delete from cloud (DynamoDB)
        if prov_mode in ['cloud', 'dual']:
            try:
                result = self._delete_from_dynamodb(subscriber_id, soft_delete)
                results['cloud'] = result
                if result['found']:
                    found = True
                logger.info(f"Subscriber {subscriber_id} deleted from DynamoDB (soft: {soft_delete})")
            except Exception as e:
                error_msg = f"DynamoDB deletion failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                results['cloud'] = {'status': 'error', 'found': False, 'message': str(e)}
        
        # Delete from legacy (MySQL)
        if prov_mode in ['legacy', 'dual']:
            try:
                result = self._delete_from_mysql(subscriber_id, soft_delete)
                results['legacy'] = result
                if result['found']:
                    found = True
                logger.info(f"Subscriber {subscriber_id} deleted from MySQL (soft: {soft_delete})")
            except Exception as e:
                error_msg = f"MySQL deletion failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                results['legacy'] = {'status': 'error', 'found': False, 'message': str(e)}
        
        successful_systems = [k for k, v in results.items() if v and v.get('status') == 'success']
        
        return {
            'subscriber_id': subscriber_id,
            'found': found,
            'soft_delete': soft_delete,
            'provisioning_mode': prov_mode,
            'results': results,
            'summary': {
                'successful': len(successful_systems),
                'failed': len([k for k, v in results.items() if v and v.get('status') == 'error']),
                'systems': successful_systems,
                'errors': errors
            },
            'deleted_at': datetime.utcnow().isoformat()
        }
    
    def bulk_delete(self, subscriber_ids: List[str], soft_delete: bool = True, prov_mode: str = None) -> Dict[str, Any]:
        """
        Bulk delete subscribers
        """
        prov_mode = prov_mode or self.current_prov_mode
        
        results = []
        successful = 0
        failed = 0
        
        for subscriber_id in subscriber_ids:
            try:
                result = self.delete_subscriber(subscriber_id, soft_delete, prov_mode)
                if result['found'] and result['summary']['successful'] > 0:
                    successful += 1
                else:
                    failed += 1
                results.append(result)
            except Exception as e:
                failed += 1
                results.append({
                    'subscriber_id': subscriber_id,
                    'error': str(e),
                    'found': False
                })
        
        return {
            'operation': 'bulk_delete',
            'total': len(subscriber_ids),
            'summary': {
                'successful': successful,
                'failed': failed
            },
            'details': results,
            'provisioning_mode': prov_mode,
            'soft_delete': soft_delete
        }
    
    def bulk_status_update(self, subscriber_ids: List[str], new_status: str, prov_mode: str = None) -> Dict[str, Any]:
        """
        Bulk update subscriber status
        """
        prov_mode = prov_mode or self.current_prov_mode
        
        results = []
        successful = 0
        failed = 0
        
        for subscriber_id in subscriber_ids:
            try:
                result = self.update_subscriber(subscriber_id, {'status': new_status}, prov_mode)
                if result['found'] and result['summary']['successful'] > 0:
                    successful += 1
                else:
                    failed += 1
                results.append(result)
            except Exception as e:
                failed += 1
                results.append({
                    'subscriber_id': subscriber_id,
                    'error': str(e),
                    'found': False
                })
        
        return {
            'operation': f'bulk_status_update_to_{new_status}',
            'total': len(subscriber_ids),
            'summary': {
                'successful': successful,
                'failed': failed
            },
            'details': results,
            'provisioning_mode': prov_mode,
            'new_status': new_status
        }
    
    def get_provisioning_config(self) -> Dict[str, Any]:
        """
        Get current provisioning configuration
        """
        return {
            'current_mode': self.current_prov_mode,
            'available_modes': ['legacy', 'cloud', 'dual'],
            'mode_descriptions': {
                'legacy': 'MySQL RDS only - existing data compatibility',
                'cloud': 'DynamoDB only - modern, scalable operations',
                'dual': 'Both systems - atomic operations across both'
            },
            'system_status': {
                'dynamodb': self._check_dynamodb_health(),
                'mysql': self._check_mysql_health()
            }
        }
    
    def set_provisioning_mode(self, new_mode: str) -> Dict[str, Any]:
        """
        Set new provisioning mode
        """
        previous_mode = self.current_prov_mode
        
        # Update environment variable (this would typically update a config service)
        os.environ['PROV_MODE'] = new_mode
        self.current_prov_mode = new_mode
        
        return {
            'previous_mode': previous_mode,
            'new_mode': new_mode,
            'updated_at': datetime.utcnow().isoformat()
        }
    
    def get_system_statistics(self) -> Dict[str, Any]:
        """
        Get statistics from both systems
        """
        stats = {
            'cloud': {'total': 0, 'active': 0, 'inactive': 0, 'status': 'unknown'},
            'legacy': {'total': 0, 'active': 0, 'inactive': 0, 'status': 'unknown'},
            'combined': {'total': 0, 'active': 0, 'inactive': 0},
            'last_updated': datetime.utcnow().isoformat()
        }
        
        # Get DynamoDB stats
        try:
            cloud_stats = self._get_dynamodb_stats()
            stats['cloud'] = cloud_stats
            stats['cloud']['status'] = 'healthy'
        except Exception as e:
            logger.error(f"Error getting DynamoDB stats: {str(e)}")
            stats['cloud']['status'] = 'error'
        
        # Get MySQL stats
        try:
            legacy_stats = self._get_mysql_stats()
            stats['legacy'] = legacy_stats
            stats['legacy']['status'] = 'healthy'
        except Exception as e:
            logger.error(f"Error getting MySQL stats: {str(e)}")
            stats['legacy']['status'] = 'error'
        
        # Calculate combined stats
        stats['combined']['total'] = stats['cloud']['total'] + stats['legacy']['total']
        stats['combined']['active'] = stats['cloud']['active'] + stats['legacy']['active']
        stats['combined']['inactive'] = stats['cloud']['inactive'] + stats['legacy']['inactive']
        
        return stats
    
    def compare_systems(self, sample_size: int = 100) -> Dict[str, Any]:
        """
        Compare data consistency between systems
        """
        # Get sample from both systems
        cloud_sample = self._get_sample_from_dynamodb(sample_size)
        legacy_sample = self._get_sample_from_mysql(sample_size)
        
        # Create lookup maps
        cloud_map = {sub['uid']: sub for sub in cloud_sample}
        legacy_map = {sub['uid']: sub for sub in legacy_sample}
        
        # Find discrepancies
        all_uids = set(cloud_map.keys()) | set(legacy_map.keys())
        matches = 0
        discrepancies = []
        cloud_only = 0
        legacy_only = 0
        
        for uid in all_uids:
            cloud_sub = cloud_map.get(uid)
            legacy_sub = legacy_map.get(uid)
            
            if cloud_sub and legacy_sub:
                # Compare key fields
                diffs = self._compare_subscriber_records(cloud_sub, legacy_sub)
                if diffs:
                    discrepancies.append({
                        'uid': uid,
                        'type': 'field_mismatch',
                        'differences': diffs
                    })
                else:
                    matches += 1
            elif cloud_sub and not legacy_sub:
                cloud_only += 1
                discrepancies.append({
                    'uid': uid,
                    'type': 'cloud_only',
                    'data': self._sanitize_subscriber_data(cloud_sub)
                })
            elif legacy_sub and not cloud_sub:
                legacy_only += 1
                discrepancies.append({
                    'uid': uid,
                    'type': 'legacy_only',
                    'data': self._sanitize_subscriber_data(legacy_sub)
                })
        
        total_compared = len(all_uids)
        accuracy = (matches / total_compared * 100) if total_compared > 0 else 100
        
        return {
            'comparison_timestamp': datetime.utcnow().isoformat(),
            'sample_size': sample_size,
            'total_compared': total_compared,
            'summary': {
                'matches': matches,
                'discrepancies': len(discrepancies),
                'cloud_only': cloud_only,
                'legacy_only': legacy_only,
                'accuracy': round(accuracy, 2)
            },
            'discrepancies': discrepancies[:50]  # Limit to first 50
        }
    
    def export_subscribers(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export subscribers in specified format
        """
        system = criteria['system']
        format_type = criteria['format']
        limit = criteria['limit']
        
        # Get subscribers
        search_criteria = {
            'source': system,
            'status': criteria.get('status'),
            'limit': limit,
            'offset': 0
        }
        
        result = self.get_subscribers(search_criteria)
        subscribers = result['subscribers']
        
        if format_type == 'csv':
            content = self._generate_csv_export(subscribers)
        else:  # json
            content = json.dumps(subscribers, indent=2, default=str)
        
        return {
            'content': content,
            'count': len(subscribers),
            'format': format_type,
            'exported_at': datetime.utcnow().isoformat()
        }
    
    def process_csv_upload(self, file, prov_mode: str = None) -> Dict[str, Any]:
        """
        Process CSV file upload for bulk subscriber creation
        """
        prov_mode = prov_mode or self.current_prov_mode
        
        # Read CSV content
        try:
            csv_content = file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            results = []
            successful = 0
            failed = 0
            
            for row_num, row in enumerate(csv_reader, start=1):
                try:
                    # Validate and clean row data
                    subscriber_data = self._validate_csv_row(row)
                    
                    # Create subscriber
                    result = self.create_subscriber(subscriber_data, prov_mode)
                    
                    if result['summary']['successful'] > 0:
                        successful += 1
                    else:
                        failed += 1
                    
                    results.append({
                        'row': row_num,
                        'uid': subscriber_data.get('uid'),
                        'result': result
                    })
                    
                except Exception as e:
                    failed += 1
                    results.append({
                        'row': row_num,
                        'error': str(e),
                        'data': row
                    })
            
            return {
                'filename': file.filename,
                'total_rows': len(results),
                'summary': {
                    'total': len(results),
                    'successful': successful,
                    'failed': failed
                },
                'details': results[:100],  # Limit details to first 100 rows
                'provisioning_mode': prov_mode,
                'processed_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing CSV upload: {str(e)}")
            raise ValueError(f"Failed to process CSV file: {str(e)}")
    
    # Private helper methods for database operations
    
    @retry_with_backoff(max_retries=3)
    def _create_in_dynamodb(self, subscriber: SubscriberData) -> Dict[str, Any]:
        """Create subscriber in DynamoDB"""
        item = subscriber.to_dynamodb_item()
        
        # Check for existing subscriber
        try:
            response = self.dynamodb_table.get_item(Key={'subscriberId': subscriber.uid})
            if 'Item' in response:
                raise ValueError(f"Subscriber {subscriber.uid} already exists in DynamoDB")
        except Exception as e:
            if "already exists" in str(e):
                raise
        
        # Create new subscriber
        self.dynamodb_table.put_item(Item=item)
        
        return {'status': 'success', 'system': 'dynamodb', 'created_at': item['created_at']}
    
    @retry_with_backoff(max_retries=3)
    def _create_in_mysql(self, subscriber: SubscriberData) -> Dict[str, Any]:
        """Create subscriber in MySQL"""
        connection = get_legacy_db_connection()
        if not connection:
            raise RuntimeError("Failed to connect to MySQL database")
        
        try:
            with connection.cursor() as cursor:
                # Check for existing subscriber
                cursor.execute("SELECT uid FROM subscribers WHERE uid = %s", (subscriber.uid,))
                if cursor.fetchone():
                    raise ValueError(f"Subscriber {subscriber.uid} already exists in MySQL")
                
                # Insert new subscriber
                insert_query = """
                INSERT INTO subscribers (uid, imsi, msisdn, status, created_at, updated_at, 
                                       apn, service_profile, roaming_allowed, data_limit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, subscriber.to_mysql_values())
                connection.commit()
                
                return {'status': 'success', 'system': 'mysql', 'created_at': subscriber.created_at}
                
        finally:
            connection.close()
    
    def _get_from_dynamodb(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Get subscribers from DynamoDB with filtering"""
        search = criteria.get('search', '').lower()
        status = criteria.get('status')
        limit = criteria.get('limit', 50)
        
        # Build scan parameters
        scan_kwargs = {}
        
        if status and status != 'all':
            scan_kwargs['FilterExpression'] = Attr('status').eq(status)
        
        # Add search filter if provided
        if search:
            if 'FilterExpression' in scan_kwargs:
                scan_kwargs['FilterExpression'] = scan_kwargs['FilterExpression'] & (
                    Attr('uid').contains(search) |
                    Attr('imsi').contains(search) |
                    Attr('msisdn').contains(search)
                )
            else:
                scan_kwargs['FilterExpression'] = (
                    Attr('uid').contains(search) |
                    Attr('imsi').contains(search) |
                    Attr('msisdn').contains(search)
                )
        
        # Perform scan
        response = self.dynamodb_table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        # Convert Decimal to float for JSON serialization
        subscribers = []
        for item in items:
            clean_item = {}
            for key, value in item.items():
                if isinstance(value, Decimal):
                    clean_item[key] = float(value)
                else:
                    clean_item[key] = value
            subscribers.append(clean_item)
        
        return {'subscribers': subscribers[:limit]}
    
    def _get_from_mysql(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Get subscribers from MySQL with filtering"""
        connection = get_legacy_db_connection()
        if not connection:
            return {'subscribers': []}
        
        try:
            with connection.cursor() as cursor:
                # Build query
                query = "SELECT * FROM subscribers WHERE 1=1"
                params = []
                
                # Add status filter
                status = criteria.get('status')
                if status and status != 'all':
                    query += " AND status = %s"
                    params.append(status)
                
                # Add search filter
                search = criteria.get('search', '').lower()
                if search:
                    query += " AND (LOWER(uid) LIKE %s OR LOWER(imsi) LIKE %s OR LOWER(msisdn) LIKE %s)"
                    search_param = f"%{search}%"
                    params.extend([search_param, search_param, search_param])
                
                # Add ordering and limit
                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(criteria.get('limit', 50))
                
                cursor.execute(query, params)
                subscribers = cursor.fetchall()
                
                # Convert datetime objects to ISO strings
                for sub in subscribers:
                    if 'created_at' in sub and sub['created_at']:
                        sub['created_at'] = sub['created_at'].isoformat()
                    if 'updated_at' in sub and sub['updated_at']:
                        sub['updated_at'] = sub['updated_at'].isoformat()
                
                return {'subscribers': subscribers}
                
        finally:
            connection.close()
    
    def _check_dynamodb_health(self) -> bool:
        """Check DynamoDB table health"""
        try:
            self.dynamodb_table.scan(Limit=1)
            return True
        except Exception:
            return False
    
    def _check_mysql_health(self) -> bool:
        """Check MySQL connection health"""
        try:
            connection = get_legacy_db_connection()
            if connection:
                connection.close()
                return True
            return False
        except Exception:
            return False
    
    def _generate_csv_export(self, subscribers: List[Dict[str, Any]]) -> str:
        """Generate CSV content from subscribers list"""
        if not subscribers:
            return "uid,imsi,msisdn,status,created_at,source\n"
        
        output = io.StringIO()
        
        # Get all possible fieldnames
        fieldnames = set()
        for sub in subscribers:
            fieldnames.update(sub.keys())
        
        fieldnames = sorted(list(fieldnames))
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for subscriber in subscribers:
            # Clean data for CSV
            clean_row = {}
            for field in fieldnames:
                value = subscriber.get(field, '')
                if isinstance(value, (dict, list)):
                    clean_row[field] = json.dumps(value)
                else:
                    clean_row[field] = str(value) if value is not None else ''
            writer.writerow(clean_row)
        
        return output.getvalue()
    
    def _validate_csv_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        """Validate and clean CSV row data"""
        required_fields = ['uid', 'imsi']
        
        for field in required_fields:
            if not row.get(field, '').strip():
                raise ValueError(f"Missing required field: {field}")
        
        # Clean and validate data
        clean_data = {
            'uid': self.validator.sanitize_string(row['uid'], 50),
            'imsi': self.validator.sanitize_string(row['imsi'], 20),
            'msisdn': self.validator.sanitize_string(row.get('msisdn', ''), 20),
            'status': row.get('status', 'ACTIVE').upper(),
            'apn': self.validator.sanitize_string(row.get('apn', ''), 50),
            'service_profile': self.validator.sanitize_string(row.get('service_profile', ''), 50)
        }
        
        # Validate status
        if clean_data['status'] not in ['ACTIVE', 'INACTIVE', 'SUSPENDED']:
            clean_data['status'] = 'ACTIVE'
        
        return clean_data

# Export service instance
subscriber_service = SubscriberService()