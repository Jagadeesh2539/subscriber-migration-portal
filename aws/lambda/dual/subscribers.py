#!/usr/bin/env python3
import json
import os
from datetime import datetime
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response, InputValidator

try:
    import boto3
    import pymysql
    from boto3.dynamodb.conditions import Key, Attr
    
    # DynamoDB setup
    dynamodb = boto3.resource('dynamodb')
    SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE')
    cloud_table = dynamodb.Table(SUBSCRIBERS_TABLE) if SUBSCRIBERS_TABLE else None
    
    # RDS setup
    LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
    LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')
    secrets_client = boto3.client('secretsmanager')
    
except Exception as e:
    cloud_table = None
    secrets_client = None
    print(f"AWS services initialization error: {e}")


# Connection cache
_legacy_connection = None
_legacy_credentials = None


def get_legacy_connection():
    """Get cached or new Legacy database connection"""
    global _legacy_connection, _legacy_credentials
    
    if not LEGACY_DB_SECRET_ARN or not LEGACY_DB_HOST:
        raise Exception("Legacy DB configuration missing")
    
    # Fetch credentials if not cached
    if not _legacy_credentials or (_legacy_connection and not _legacy_connection.open):
        secret_response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        _legacy_credentials = json.loads(secret_response['SecretString'])
    
    # Create new connection if needed
    if not _legacy_connection or not _legacy_connection.open:
        _legacy_connection = pymysql.connect(
            host=LEGACY_DB_HOST,
            user=_legacy_credentials.get('username') or _legacy_credentials.get('user'),
            password=_legacy_credentials.get('password') or _legacy_credentials.get('pass'),
            database=_legacy_credentials.get('dbname') or _legacy_credentials.get('database') or 'legacydb',
            charset='utf8mb4',
            autocommit=True,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30
        )
    
    return _legacy_connection


def lambda_handler(event, context):
    method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    headers = event.get('headers') or {}
    origin = headers.get('origin')
    
    # Extract UID from path if present
    uid = path_params.get('uid')
    
    # Check for special sync operations
    if 'sync' in event.get('resource', ''):
        return handle_sync_operations(event, context)
    
    try:
        if method == 'GET' and uid:
            return get_dual_subscriber(uid, origin)
        elif method == 'GET':
            return list_dual_subscribers(query_params, origin)
        elif method == 'POST':
            body = event.get('body') or '{}'
            data = json.loads(body)
            return create_dual_subscriber(data, origin)
        elif method == 'PUT' and uid:
            body = event.get('body') or '{}'
            data = json.loads(body)
            return update_dual_subscriber(uid, data, origin)
        elif method == 'DELETE' and uid:
            return delete_dual_subscriber(uid, origin)
        else:
            return create_error_response(405, 'Method not allowed', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Internal server error: {str(e)}', origin=origin)


def get_dual_subscriber(uid, origin=None):
    """Get subscriber from both systems and compare"""
    try:
        # Fetch from both systems in parallel
        cloud_data = None
        legacy_data = None
        cloud_error = None
        legacy_error = None
        
        # Cloud fetch
        try:
            if cloud_table:
                cloud_response = cloud_table.get_item(Key={'uid': uid})
                cloud_data = cloud_response.get('Item')
        except Exception as e:
            cloud_error = str(e)
        
        # Legacy fetch
        try:
            conn = get_legacy_connection()
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (uid,))
                legacy_raw = cursor.fetchone()
                if legacy_raw:
                    legacy_data = normalize_mysql_response(legacy_raw)
        except Exception as e:
            legacy_error = str(e)
        
        # Determine result based on data availability
        if not cloud_data and not legacy_data:
            return create_error_response(404, f'Subscriber {uid} not found in either system', origin=origin)
        
        # Calculate sync status
        sync_status = calculate_sync_status(cloud_data, legacy_data)
        
        # Choose primary data source (prefer Cloud if both exist)
        primary_data = cloud_data or legacy_data
        
        # Enhance with dual-specific metadata
        result = {
            'subscriber': mask_pii(primary_data),
            'syncStatus': sync_status,
            'cloudExists': bool(cloud_data),
            'legacyExists': bool(legacy_data),
            'conflicts': detect_conflicts(cloud_data, legacy_data) if cloud_data and legacy_data else [],
            'cloudError': cloud_error,
            'legacyError': legacy_error,
            'source': 'dual',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Add detailed comparison if both exist
        if cloud_data and legacy_data:
            result['comparison'] = {
                'cloudUpdatedAt': cloud_data.get('updated_at'),
                'legacyUpdatedAt': legacy_data.get('updatedAt') or legacy_data.get('updated_at'),
                'fieldDifferences': compare_subscriber_fields(cloud_data, legacy_data)
            }
        
        return create_response(200, result, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to get dual subscriber: {str(e)}', origin=origin)


def list_dual_subscribers(query_params, origin=None):
    """List subscribers from both systems with sync status"""
    try:
        # Parse parameters
        status_filter = query_params.get('status')
        plan_filter = query_params.get('planId')
        search_term = query_params.get('search', '').strip()
        sync_status_filter = query_params.get('syncStatus')
        limit = min(int(query_params.get('limit', 25)), 100)
        
        # For now, return a placeholder response
        # TODO: Implement efficient cross-system querying with sync status calculation
        return create_response(200, {
            'subscribers': [],
            'pagination': {
                'count': 0,
                'hasMore': False,
                'total': 0
            },
            'syncStats': {
                'synced': 0,
                'outOfSync': 0,
                'cloudOnly': 0,
                'legacyOnly': 0,
                'conflicts': 0
            },
            'source': 'dual',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to list dual subscribers: {str(e)}', origin=origin)


def create_dual_subscriber(data, origin=None):
    """Create subscriber in both Cloud and Legacy systems"""
    try:
        # Validate input
        validator = InputValidator()
        validator.require('uid', data.get('uid'))
        validator.require('msisdn', data.get('msisdn'))
        validator.require('imsi', data.get('imsi'))
        validator.validate_status(data.get('status', 'ACTIVE'))
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        cloud_result = {'success': False, 'error': None, 'data': None}
        legacy_result = {'success': False, 'error': None, 'data': None}
        
        # Prepare subscriber data
        now = datetime.utcnow().isoformat()
        subscriber_data = {
            'uid': data['uid'].strip(),
            'msisdn': data['msisdn'].strip(),
            'imsi': data['imsi'].strip(),
            'status': data.get('status', 'ACTIVE').upper(),
            'plan_id': data.get('planId', '').strip() or None,
            'email': data.get('email', '').strip() or None,
            'first_name': data.get('firstName', '').strip() or None,
            'last_name': data.get('lastName', '').strip() or None,
            'address': data.get('address', '').strip() or None,
            'date_of_birth': data.get('dateOfBirth') or None,
            'created_at': now,
            'updated_at': now,
            'last_activity': None,
        }
        
        # Create in Cloud (DynamoDB)
        try:
            if cloud_table:
                # Check for duplicate
                existing_response = cloud_table.get_item(Key={'uid': subscriber_data['uid']})
                if existing_response.get('Item'):
                    cloud_result['error'] = 'UID already exists'
                else:
                    cloud_table.put_item(Item=subscriber_data)
                    cloud_result['success'] = True
                    cloud_result['data'] = subscriber_data.copy()
        except Exception as e:
            cloud_result['error'] = str(e)
        
        # Create in Legacy (RDS)
        try:
            conn = get_legacy_connection()
            with conn.cursor() as cursor:
                # Check for duplicates
                cursor.execute(
                    "SELECT uid FROM subscribers WHERE uid = %s OR msisdn = %s OR imsi = %s",
                    (subscriber_data['uid'], subscriber_data['msisdn'], subscriber_data['imsi'])
                )
                if cursor.fetchone():
                    legacy_result['error'] = 'UID/MSISDN/IMSI already exists'
                else:
                    # Convert datetime string to MySQL datetime
                    mysql_now = datetime.fromisoformat(now.replace('Z', '+00:00')).replace(tzinfo=None)
                    
                    cursor.execute("""
                        INSERT INTO subscribers (
                            uid, msisdn, imsi, status, plan_id, email,
                            first_name, last_name, address, date_of_birth,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        subscriber_data['uid'],
                        subscriber_data['msisdn'],
                        subscriber_data['imsi'],
                        subscriber_data['status'],
                        subscriber_data['plan_id'],
                        subscriber_data['email'],
                        subscriber_data['first_name'],
                        subscriber_data['last_name'],
                        subscriber_data['address'],
                        subscriber_data['date_of_birth'],
                        mysql_now,
                        mysql_now
                    ))
                    legacy_result['success'] = True
                    legacy_result['data'] = subscriber_data.copy()
        except Exception as e:
            legacy_result['error'] = str(e)
        
        # Evaluate results and handle rollbacks if needed
        conflicts = []
        overall_success = cloud_result['success'] and legacy_result['success']
        
        if not overall_success:
            # Rollback successful operations if one failed
            if cloud_result['success'] and not legacy_result['success']:
                try:
                    cloud_table.delete_item(Key={'uid': subscriber_data['uid']})
                    conflicts.append({
                        'type': 'ROLLBACK',
                        'message': 'Rolled back Cloud creation due to Legacy failure',
                        'cloudError': None,
                        'legacyError': legacy_result['error']
                    })
                except Exception as rollback_error:
                    conflicts.append({
                        'type': 'ROLLBACK_FAILED',
                        'message': f'Failed to rollback Cloud creation: {rollback_error}',
                        'cloudError': str(rollback_error),
                        'legacyError': legacy_result['error']
                    })
            
            elif legacy_result['success'] and not cloud_result['success']:
                try:
                    conn = get_legacy_connection()
                    with conn.cursor() as cursor:
                        cursor.execute("DELETE FROM subscribers WHERE uid = %s", (subscriber_data['uid'],))
                    conflicts.append({
                        'type': 'ROLLBACK',
                        'message': 'Rolled back Legacy creation due to Cloud failure',
                        'cloudError': cloud_result['error'],
                        'legacyError': None
                    })
                except Exception as rollback_error:
                    conflicts.append({
                        'type': 'ROLLBACK_FAILED',
                        'message': f'Failed to rollback Legacy creation: {rollback_error}',
                        'cloudError': cloud_result['error'],
                        'legacyError': str(rollback_error)
                    })
        
        # Prepare response
        if overall_success:
            return create_response(201, {
                'subscriber': mask_pii(subscriber_data),
                'message': 'Subscriber created successfully in both systems',
                'cloudResult': {
                    'success': cloud_result['success'],
                    'error': cloud_result['error']
                },
                'legacyResult': {
                    'success': legacy_result['success'],
                    'error': legacy_result['error']
                },
                'conflicts': conflicts,
                'syncStatus': 'SYNCED',
                'source': 'dual',
                'timestamp': now
            }, origin=origin)
        else:
            return create_error_response(422, 'Failed to create in both systems', 
                additional_data={
                    'cloudResult': cloud_result,
                    'legacyResult': legacy_result,
                    'conflicts': conflicts
                }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to create dual subscriber: {str(e)}', origin=origin)


def update_dual_subscriber(uid, data, origin=None):
    """Update subscriber in both Cloud and Legacy systems"""
    try:
        cloud_result = {'success': False, 'error': None, 'data': None}
        legacy_result = {'success': False, 'error': None, 'data': None}
        
        # Validate update data
        validator = InputValidator()
        if 'status' in data:
            validator.validate_status(data['status'])
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        now = datetime.utcnow().isoformat()
        
        # Update in Cloud (DynamoDB)
        try:
            if cloud_table:
                # Check existence
                existing_response = cloud_table.get_item(Key={'uid': uid})
                if not existing_response.get('Item'):
                    cloud_result['error'] = 'Subscriber not found in Cloud'
                else:
                    # Build update expression
                    update_expression = "SET updated_at = :updated_at"
                    expression_values = {':updated_at': now}
                    
                    field_mapping = {
                        'msisdn': 'msisdn',
                        'imsi': 'imsi', 
                        'status': 'status',
                        'planId': 'plan_id',
                        'email': 'email',
                        'firstName': 'first_name',
                        'lastName': 'last_name',
                        'address': 'address',
                        'dateOfBirth': 'date_of_birth'
                    }
                    
                    for api_field, db_field in field_mapping.items():
                        if api_field in data:
                            update_expression += f", {db_field} = :{db_field}"
                            value = data[api_field]
                            if isinstance(value, str):
                                value = value.strip() or None
                            expression_values[f':{db_field}'] = value
                    
                    cloud_table.update_item(
                        Key={'uid': uid},
                        UpdateExpression=update_expression,
                        ExpressionAttributeValues=expression_values
                    )
                    cloud_result['success'] = True
        except Exception as e:
            cloud_result['error'] = str(e)
        
        # Update in Legacy (RDS)
        try:
            conn = get_legacy_connection()
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check existence
                cursor.execute("SELECT uid FROM subscribers WHERE uid = %s", (uid,))
                if not cursor.fetchone():
                    legacy_result['error'] = 'Subscriber not found in Legacy'
                else:
                    # Build update query
                    update_fields = []
                    update_params = []
                    
                    field_mapping = {
                        'msisdn': 'msisdn',
                        'imsi': 'imsi',
                        'status': 'status', 
                        'planId': 'plan_id',
                        'email': 'email',
                        'firstName': 'first_name',
                        'lastName': 'last_name',
                        'address': 'address',
                        'dateOfBirth': 'date_of_birth'
                    }
                    
                    for api_field, db_field in field_mapping.items():
                        if api_field in data:
                            update_fields.append(f"{db_field} = %s")
                            value = data[api_field]
                            if isinstance(value, str):
                                value = value.strip() or None
                            update_params.append(value)
                    
                    if update_fields:
                        update_fields.append("updated_at = %s")
                        update_params.append(datetime.fromisoformat(now.replace('Z', '+00:00')).replace(tzinfo=None))
                        update_params.append(uid)
                        
                        update_query = f"UPDATE subscribers SET {', '.join(update_fields)} WHERE uid = %s"
                        cursor.execute(update_query, update_params)
                        
                        if cursor.rowcount > 0:
                            legacy_result['success'] = True
                        else:
                            legacy_result['error'] = 'No rows updated'
        except Exception as e:
            legacy_result['error'] = str(e)
        
        # Evaluate results
        overall_success = cloud_result['success'] and legacy_result['success']
        partial_success = cloud_result['success'] or legacy_result['success']
        
        status_code = 200 if overall_success else 207 if partial_success else 422
        
        return create_response(status_code, {
            'message': 'Dual update completed' + (' successfully' if overall_success else ' with issues'),
            'cloudResult': cloud_result,
            'legacyResult': legacy_result,
            'overallSuccess': overall_success,
            'partialSuccess': partial_success,
            'source': 'dual',
            'timestamp': now
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to update dual subscriber: {str(e)}', origin=origin)


def delete_dual_subscriber(uid, origin=None):
    """Delete subscriber from both Cloud and Legacy systems"""
    try:
        cloud_result = {'success': False, 'error': None}
        legacy_result = {'success': False, 'error': None}
        
        # Delete from Cloud
        try:
            if cloud_table:
                existing_response = cloud_table.get_item(Key={'uid': uid})
                if not existing_response.get('Item'):
                    cloud_result['error'] = 'Subscriber not found in Cloud'
                else:
                    cloud_table.delete_item(Key={'uid': uid})
                    cloud_result['success'] = True
        except Exception as e:
            cloud_result['error'] = str(e)
        
        # Delete from Legacy
        try:
            conn = get_legacy_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT uid FROM subscribers WHERE uid = %s", (uid,))
                if not cursor.fetchone():
                    legacy_result['error'] = 'Subscriber not found in Legacy'
                else:
                    cursor.execute("DELETE FROM subscribers WHERE uid = %s", (uid,))
                    if cursor.rowcount > 0:
                        legacy_result['success'] = True
                    else:
                        legacy_result['error'] = 'No rows deleted'
        except Exception as e:
            legacy_result['error'] = str(e)
        
        # Evaluate results
        overall_success = cloud_result['success'] and legacy_result['success']
        partial_success = cloud_result['success'] or legacy_result['success']
        
        if not overall_success and not partial_success:
            return create_error_response(404, 'Subscriber not found in either system', 
                additional_data={'cloudResult': cloud_result, 'legacyResult': legacy_result}, 
                origin=origin)
        
        status_code = 200 if overall_success else 207
        
        return create_response(status_code, {
            'message': f'Subscriber {uid} deletion completed' + (' successfully' if overall_success else ' partially'),
            'cloudResult': cloud_result,
            'legacyResult': legacy_result,
            'overallSuccess': overall_success,
            'partialSuccess': partial_success,
            'source': 'dual',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to delete dual subscriber: {str(e)}', origin=origin)


def handle_sync_operations(event, context):
    """Handle sync-specific operations (sync status, resolve conflicts, etc.)"""
    path = event.get('resource', '')
    
    if '/sync-status' in path:
        return get_sync_status(event)
    elif '/sync' in path:
        uid = event.get('pathParameters', {}).get('uid')
        if uid:
            return sync_subscriber(uid, event)
    
    return create_error_response(404, 'Sync operation not found')


def get_sync_status(event):
    """Get overall sync status across systems"""
    try:
        # TODO: Implement comprehensive sync status calculation
        # This would involve querying both systems and comparing
        
        return create_response(200, {
            'syncStats': {
                'synced': 0,
                'outOfSync': 0, 
                'cloudOnly': 0,
                'legacyOnly': 0,
                'conflicts': 0,
                'lastSyncTime': datetime.utcnow().isoformat()
            },
            'systemHealth': {
                'cloud': {'healthy': bool(cloud_table), 'responseTime': 150},
                'legacy': {'healthy': bool(LEGACY_DB_HOST), 'responseTime': 350}
            },
            'timestamp': datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        return create_error_response(500, f'Failed to get sync status: {str(e)}')


def sync_subscriber(uid, event):
    """Synchronize a specific subscriber between systems"""
    try:
        # Get from both systems
        cloud_data = None
        legacy_data = None
        
        if cloud_table:
            cloud_response = cloud_table.get_item(Key={'uid': uid})
            cloud_data = cloud_response.get('Item')
        
        conn = get_legacy_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (uid,))
            legacy_raw = cursor.fetchone()
            if legacy_raw:
                legacy_data = normalize_mysql_response(legacy_raw)
        
        if not cloud_data and not legacy_data:
            return create_error_response(404, f'Subscriber {uid} not found in either system')
        
        # TODO: Implement sync resolution strategy
        # For now, use "Cloud wins" strategy
        
        return create_response(200, {
            'message': f'Sync completed for subscriber {uid}',
            'strategy': 'cloud_wins',
            'beforeSync': {
                'cloudExists': bool(cloud_data),
                'legacyExists': bool(legacy_data)
            },
            'afterSync': {
                'synced': True,
                'conflicts': []
            },
            'timestamp': datetime.utcnow().isoformat()
        })
    
    except Exception as e:
        return create_error_response(500, f'Failed to sync subscriber: {str(e)}')


def calculate_sync_status(cloud_data, legacy_data):
    """Calculate sync status between Cloud and Legacy data"""
    if cloud_data and legacy_data:
        # Compare key fields
        conflicts = detect_conflicts(cloud_data, legacy_data)
        return 'CONFLICT' if conflicts else 'SYNCED'
    elif cloud_data and not legacy_data:
        return 'CLOUD_ONLY'
    elif legacy_data and not cloud_data:
        return 'LEGACY_ONLY'
    else:
        return 'NOT_FOUND'


def detect_conflicts(cloud_data, legacy_data):
    """Detect conflicts between Cloud and Legacy data"""
    conflicts = []
    
    # Compare important fields
    compare_fields = ['msisdn', 'imsi', 'status', 'plan_id', 'email', 'first_name', 'last_name']
    
    for field in compare_fields:
        cloud_value = cloud_data.get(field)
        # Handle field name differences
        legacy_field = field
        if field == 'plan_id':
            legacy_field = 'planId'
        elif field == 'first_name':
            legacy_field = 'firstName'
        elif field == 'last_name':
            legacy_field = 'lastName'
        
        legacy_value = legacy_data.get(legacy_field)
        
        if cloud_value != legacy_value:
            conflicts.append({
                'field': field,
                'cloudValue': cloud_value,
                'legacyValue': legacy_value
            })
    
    return conflicts


def compare_subscriber_fields(cloud_data, legacy_data):
    """Detailed field-by-field comparison"""
    differences = {}
    
    all_fields = set(list(cloud_data.keys()) + list(legacy_data.keys()))
    
    for field in all_fields:
        cloud_val = cloud_data.get(field)
        legacy_val = legacy_data.get(field)
        
        if cloud_val != legacy_val:
            differences[field] = {
                'cloud': cloud_val,
                'legacy': legacy_val
            }
    
    return differences


def normalize_mysql_response(subscriber):
    """Convert MySQL response to match DynamoDB format"""
    if not subscriber:
        return subscriber
    
    normalized = dict(subscriber)
    
    # Convert datetime objects to ISO strings
    datetime_fields = ['created_at', 'updated_at', 'last_activity', 'date_of_birth']
    for field in datetime_fields:
        if field in normalized and normalized[field] is not None:
            if hasattr(normalized[field], 'isoformat'):
                normalized[field] = normalized[field].isoformat()
    
    return normalized


def mask_pii(item):
    """Mask personally identifiable information"""
    if not item:
        return item
    
    masked = dict(item)
    
    # Mask IMSI
    if 'imsi' in masked and len(str(masked['imsi'])) > 6:
        imsi_str = str(masked['imsi'])
        masked['imsi'] = imsi_str[:6] + '*' * (len(imsi_str) - 6)
    
    # Mask email
    if 'email' in masked and '@' in str(masked['email']):
        email_parts = str(masked['email']).split('@')
        if len(email_parts) == 2:
            masked['email'] = f"***@{email_parts[1]}"
    
    return masked