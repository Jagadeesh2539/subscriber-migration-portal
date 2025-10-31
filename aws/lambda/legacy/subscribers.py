#!/usr/bin/env python3
import json
import os
from datetime import datetime
import uuid

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response, InputValidator

try:
    import boto3
    import pymysql
    
    # Get RDS connection details from environment/secrets
    LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
    LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')
    
    secrets_client = boto3.client('secretsmanager')
except Exception as e:
    secrets_client = None
    print(f"AWS services initialization error: {e}")


# Connection cache to reuse across Lambda invocations
_db_connection = None
_db_credentials = None


def get_db_connection():
    """Get cached or new database connection"""
    global _db_connection, _db_credentials
    
    if not LEGACY_DB_SECRET_ARN or not LEGACY_DB_HOST:
        raise Exception("Legacy DB configuration missing")
    
    # Fetch credentials if not cached or connection is stale
    if not _db_credentials or (_db_connection and not _db_connection.open):
        try:
            secret_response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
            _db_credentials = json.loads(secret_response['SecretString'])
        except Exception as e:
            raise Exception(f"Failed to get DB credentials: {e}")
    
    # Create new connection if needed
    if not _db_connection or not _db_connection.open:
        try:
            _db_connection = pymysql.connect(
                host=LEGACY_DB_HOST,
                user=_db_credentials.get('username') or _db_credentials.get('user'),
                password=_db_credentials.get('password') or _db_credentials.get('pass'),
                database=_db_credentials.get('dbname') or _db_credentials.get('database') or 'legacydb',
                charset='utf8mb4',
                autocommit=True,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30
            )
        except Exception as e:
            raise Exception(f"Failed to connect to Legacy DB: {e}")
    
    return _db_connection


def lambda_handler(event, context):
    method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    headers = event.get('headers') or {}
    origin = headers.get('origin')
    
    # Extract UID from path if present
    uid = path_params.get('uid')
    
    try:
        if method == 'GET' and uid:
            return get_subscriber(uid, origin)
        elif method == 'GET':
            return list_subscribers(query_params, origin)
        elif method == 'POST':
            body = event.get('body') or '{}'
            data = json.loads(body)
            return create_subscriber(data, origin)
        elif method == 'PUT' and uid:
            body = event.get('body') or '{}'
            data = json.loads(body)
            return update_subscriber(uid, data, origin)
        elif method == 'DELETE' and uid:
            return delete_subscriber(uid, origin)
        else:
            return create_error_response(405, 'Method not allowed', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Internal server error: {str(e)}', origin=origin)


def get_subscriber(uid, origin=None):
    """Get a single subscriber by UID from RDS MySQL"""
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM subscribers WHERE uid = %s",
                (uid,)
            )
            subscriber = cursor.fetchone()
            
            if not subscriber:
                return create_error_response(404, f'Subscriber {uid} not found in Legacy', origin=origin)
            
            # Convert datetime objects to ISO strings
            normalized = normalize_mysql_response(subscriber)
            
            # Mask PII in response
            masked_subscriber = mask_pii(normalized)
            
            return create_response(200, {
                'subscriber': masked_subscriber,
                'source': 'legacy',
                'timestamp': datetime.utcnow().isoformat()
            }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to get subscriber from Legacy: {str(e)}', origin=origin)


def list_subscribers(query_params, origin=None):
    """List subscribers with filtering and pagination from RDS MySQL"""
    try:
        conn = get_db_connection()
        
        # Parse query parameters
        status_filter = query_params.get('status')
        plan_filter = query_params.get('planId')
        search_term = query_params.get('search', '').strip()
        limit = min(int(query_params.get('limit', 25)), 100)
        offset = int(query_params.get('offset', 0))
        
        # Build SQL query with proper indexing
        base_query = "SELECT * FROM subscribers"
        count_query = "SELECT COUNT(*) as total FROM subscribers"
        where_conditions = []
        params = []
        
        # Add filters
        if status_filter:
            where_conditions.append("status = %s")
            params.append(status_filter)
        
        if plan_filter:
            where_conditions.append("plan_id = %s")
            params.append(plan_filter)
        
        if search_term:
            search_condition = """(
                uid LIKE %s OR 
                msisdn LIKE %s OR 
                imsi LIKE %s OR 
                email LIKE %s OR 
                first_name LIKE %s OR 
                last_name LIKE %s
            )"""
            where_conditions.append(search_condition)
            search_param = f"%{search_term}%"
            params.extend([search_param] * 6)
        
        # Build WHERE clause
        if where_conditions:
            where_clause = " WHERE " + " AND ".join(where_conditions)
        else:
            where_clause = ""
        
        # Execute count query
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(count_query + where_clause, params)
            total_count = cursor.fetchone()['total']
            
            # Execute main query with pagination
            full_query = f"{base_query}{where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
            cursor.execute(full_query, params + [limit, offset])
            subscribers = cursor.fetchall()
        
        # Normalize MySQL response
        normalized_subscribers = [normalize_mysql_response(sub) for sub in subscribers]
        
        # Mask PII in all items
        masked_subscribers = [mask_pii(sub) for sub in normalized_subscribers]
        
        # Calculate pagination info
        has_more = (offset + limit) < total_count
        next_offset = offset + limit if has_more else None
        
        return create_response(200, {
            'subscribers': masked_subscribers,
            'pagination': {
                'count': len(masked_subscribers),
                'total': total_count,
                'hasMore': has_more,
                'offset': offset,
                'nextOffset': next_offset,
                'limit': limit
            },
            'filters': {
                'status': status_filter,
                'planId': plan_filter,
                'search': search_term
            },
            'source': 'legacy',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to list Legacy subscribers: {str(e)}', origin=origin)


def create_subscriber(data, origin=None):
    """Create a new subscriber in RDS MySQL"""
    try:
        conn = get_db_connection()
        
        # Validate required fields
        validator = InputValidator()
        validator.require('uid', data.get('uid'))
        validator.require('msisdn', data.get('msisdn'))
        validator.require('imsi', data.get('imsi'))
        validator.validate_status(data.get('status', 'ACTIVE'))
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Check for duplicates
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT uid FROM subscribers WHERE uid = %s OR msisdn = %s OR imsi = %s",
                (data['uid'], data['msisdn'], data['imsi'])
            )
            existing = cursor.fetchone()
            
            if existing:
                return create_error_response(409, f'Subscriber with UID/MSISDN/IMSI already exists in Legacy', origin=origin)
        
        # Create subscriber record
        now = datetime.utcnow()
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO subscribers (
                    uid, msisdn, imsi, status, plan_id, email, 
                    first_name, last_name, address, date_of_birth,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                data['uid'].strip(),
                data['msisdn'].strip(),
                data['imsi'].strip(),
                data.get('status', 'ACTIVE').upper(),
                data.get('planId', '').strip() or None,
                data.get('email', '').strip() or None,
                data.get('firstName', '').strip() or None,
                data.get('lastName', '').strip() or None,
                data.get('address', '').strip() or None,
                data.get('dateOfBirth') or None,
                now,
                now
            ))
        
        # Fetch created subscriber
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (data['uid'],))
            created_subscriber = cursor.fetchone()
        
        normalized = normalize_mysql_response(created_subscriber)
        masked_subscriber = mask_pii(normalized)
        
        return create_response(201, {
            'subscriber': masked_subscriber,
            'message': 'Subscriber created successfully in Legacy',
            'source': 'legacy',
            'timestamp': now.isoformat()
        }, origin=origin)
    
    except pymysql.IntegrityError as e:
        return create_error_response(409, f'Duplicate key constraint: {str(e)}', origin=origin)
    except Exception as e:
        return create_error_response(500, f'Failed to create subscriber in Legacy: {str(e)}', origin=origin)


def update_subscriber(uid, data, origin=None):
    """Update an existing subscriber in RDS MySQL"""
    try:
        conn = get_db_connection()
        
        # Check if subscriber exists
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (uid,))
            existing = cursor.fetchone()
            
            if not existing:
                return create_error_response(404, f'Subscriber {uid} not found in Legacy', origin=origin)
        
        # Validate update data
        validator = InputValidator()
        if 'status' in data:
            validator.validate_status(data['status'])
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Build UPDATE query dynamically
        update_fields = []
        update_params = []
        
        # Field mapping from API to DB
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
        
        # Add fields to update
        for api_field, db_field in field_mapping.items():
            if api_field in data:
                update_fields.append(f"{db_field} = %s")
                value = data[api_field]
                if isinstance(value, str):
                    value = value.strip() or None
                update_params.append(value)
        
        if not update_fields:
            return create_error_response(400, 'No fields to update', origin=origin)
        
        # Add updated_at timestamp
        update_fields.append("updated_at = %s")
        update_params.append(datetime.utcnow())
        update_params.append(uid)  # For WHERE clause
        
        # Execute update
        with conn.cursor() as cursor:
            update_query = f"UPDATE subscribers SET {', '.join(update_fields)} WHERE uid = %s"
            cursor.execute(update_query, update_params)
            
            if cursor.rowcount == 0:
                return create_error_response(404, f'No rows updated for UID {uid}', origin=origin)
        
        # Fetch updated subscriber
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (uid,))
            updated_subscriber = cursor.fetchone()
        
        normalized = normalize_mysql_response(updated_subscriber)
        masked_subscriber = mask_pii(normalized)
        
        return create_response(200, {
            'subscriber': masked_subscriber,
            'message': 'Subscriber updated successfully in Legacy',
            'source': 'legacy',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except pymysql.IntegrityError as e:
        return create_error_response(409, f'Integrity constraint violation: {str(e)}', origin=origin)
    except Exception as e:
        return create_error_response(500, f'Failed to update subscriber in Legacy: {str(e)}', origin=origin)


def delete_subscriber(uid, origin=None):
    """Delete a subscriber from RDS MySQL"""
    try:
        conn = get_db_connection()
        
        # Check if subscriber exists
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT uid FROM subscribers WHERE uid = %s", (uid,))
            existing = cursor.fetchone()
            
            if not existing:
                return create_error_response(404, f'Subscriber {uid} not found in Legacy', origin=origin)
        
        # Delete subscriber
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM subscribers WHERE uid = %s", (uid,))
            
            if cursor.rowcount == 0:
                return create_error_response(404, f'No rows deleted for UID {uid}', origin=origin)
        
        return create_response(200, {
            'message': f'Subscriber {uid} deleted successfully from Legacy',
            'source': 'legacy',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to delete subscriber from Legacy: {str(e)}', origin=origin)


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
            elif hasattr(normalized[field], 'strftime'):
                normalized[field] = normalized[field].strftime('%Y-%m-%d')
    
    # Ensure consistent field names (match DynamoDB)
    field_renames = {
        'plan_id': 'planId',
        'first_name': 'firstName', 
        'last_name': 'lastName',
        'date_of_birth': 'dateOfBirth',
        'last_activity': 'lastActivity',
        'created_at': 'createdAt',
        'updated_at': 'updatedAt'
    }
    
    for old_name, new_name in field_renames.items():
        if old_name in normalized:
            normalized[new_name] = normalized.pop(old_name)
    
    return normalized


def mask_pii(item):
    """Mask personally identifiable information in subscriber data"""
    if not item:
        return item
    
    masked = dict(item)
    
    # Mask IMSI (show only first 6 digits)
    if 'imsi' in masked and len(str(masked['imsi'])) > 6:
        imsi_str = str(masked['imsi'])
        masked['imsi'] = imsi_str[:6] + '*' * (len(imsi_str) - 6)
    
    # Mask email (show only domain)
    if 'email' in masked and '@' in str(masked['email']):
        email_parts = str(masked['email']).split('@')
        if len(email_parts) == 2:
            masked['email'] = f"***@{email_parts[1]}"
    
    return masked


# Connection cleanup on Lambda termination
def cleanup_connection():
    global _db_connection
    if _db_connection and _db_connection.open:
        try:
            _db_connection.close()
        except:
            pass
        _db_connection = None