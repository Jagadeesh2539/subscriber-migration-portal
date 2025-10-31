#!/usr/bin/env python3
"""
Common utilities for Lambda functions
Provides shared functionality across all Lambda functions
"""

import json
import os
from datetime import datetime
import re
import boto3
from typing import Dict, List, Optional, Any, Union


def create_response(status_code: int, body: Dict[str, Any], origin: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Create standardized API Gateway response with CORS headers"""
    
    # Default headers
    response_headers = {
        'Content-Type': 'application/json',
        'X-Timestamp': datetime.utcnow().isoformat(),
        'X-Request-ID': os.environ.get('AWS_REQUEST_ID', 'unknown')
    }
    
    # Add CORS headers
    cors_origins = os.environ.get('CORS_ORIGINS', '*')
    if origin and origin in cors_origins.split(','):
        response_headers['Access-Control-Allow-Origin'] = origin
    else:
        response_headers['Access-Control-Allow-Origin'] = cors_origins.split(',')[0] if cors_origins != '*' else '*'
    
    response_headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response_headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
    response_headers['Access-Control-Max-Age'] = '600'
    
    # Add custom headers
    if headers:
        response_headers.update(headers)
    
    # Ensure body is properly formatted
    if isinstance(body, dict):
        response_body = {
            'success': status_code < 400,
            'statusCode': status_code,
            'data': body,
            'timestamp': datetime.utcnow().isoformat()
        }
    else:
        response_body = body
    
    return {
        'statusCode': status_code,
        'headers': response_headers,
        'body': json.dumps(response_body, default=str),
        'isBase64Encoded': False
    }


def create_error_response(status_code: int, message: str, error_code: Optional[str] = None, 
                         details: Optional[Dict[str, Any]] = None, origin: Optional[str] = None) -> Dict[str, Any]:
    """Create standardized error response"""
    
    error_body = {
        'error': message,
        'code': error_code or f'HTTP_{status_code}',
        'statusCode': status_code
    }
    
    if details:
        error_body['details'] = details
    
    return create_response(status_code, error_body, origin)


class InputValidator:
    """Input validation utility class"""
    
    def __init__(self):
        self.errors = []
    
    def require(self, field_name: str, value: Any, custom_message: Optional[str] = None) -> 'InputValidator':
        """Validate that a field is required and not empty"""
        if value is None or (isinstance(value, str) and not value.strip()):
            message = custom_message or f"{field_name} is required"
            self.errors.append(message)
        return self
    
    def validate_email(self, field_name: str, value: Optional[str], required: bool = False) -> 'InputValidator':
        """Validate email format"""
        if not value:
            if required:
                self.errors.append(f"{field_name} is required")
            return self
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, value.strip()):
            self.errors.append(f"{field_name} must be a valid email address")
        return self
    
    def validate_msisdn(self, field_name: str, value: Optional[str], required: bool = True) -> 'InputValidator':
        """Validate MSISDN (E.164 format)"""
        if not value:
            if required:
                self.errors.append(f"{field_name} is required")
            return self
        
        # E.164 format: + followed by 7-15 digits
        msisdn_pattern = r'^\+[1-9][0-9]{7,14}$'
        if not re.match(msisdn_pattern, value.strip()):
            self.errors.append(f"{field_name} must be in E.164 format (e.g., +1234567890)")
        return self
    
    def validate_imsi(self, field_name: str, value: Optional[str], required: bool = True) -> 'InputValidator':
        """Validate IMSI (15 digits)"""
        if not value:
            if required:
                self.errors.append(f"{field_name} is required")
            return self
        
        # IMSI: exactly 15 digits
        imsi_pattern = r'^[0-9]{15}$'
        if not re.match(imsi_pattern, value.strip()):
            self.errors.append(f"{field_name} must be exactly 15 digits")
        return self
    
    def validate_enum(self, field_name: str, value: Optional[str], allowed_values: List[str], 
                     required: bool = False) -> 'InputValidator':
        """Validate enum field"""
        if not value:
            if required:
                self.errors.append(f"{field_name} is required")
            return self
        
        if value not in allowed_values:
            self.errors.append(f"{field_name} must be one of: {', '.join(allowed_values)}")
        return self
    
    def validate_length(self, field_name: str, value: Optional[str], min_length: Optional[int] = None,
                       max_length: Optional[int] = None) -> 'InputValidator':
        """Validate string length"""
        if not value:
            return self
        
        value_len = len(value.strip())
        if min_length is not None and value_len < min_length:
            self.errors.append(f"{field_name} must be at least {min_length} characters")
        
        if max_length is not None and value_len > max_length:
            self.errors.append(f"{field_name} must be at most {max_length} characters")
        
        return self
    
    def validate_date(self, field_name: str, value: Optional[str], required: bool = False) -> 'InputValidator':
        """Validate date format (YYYY-MM-DD)"""
        if not value:
            if required:
                self.errors.append(f"{field_name} is required")
            return self
        
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(date_pattern, value.strip()):
            self.errors.append(f"{field_name} must be in YYYY-MM-DD format")
        else:
            try:
                datetime.strptime(value.strip(), '%Y-%m-%d')
            except ValueError:
                self.errors.append(f"{field_name} is not a valid date")
        
        return self
    
    def get_errors(self) -> List[str]:
        """Get all validation errors"""
        return self.errors
    
    def is_valid(self) -> bool:
        """Check if validation passed"""
        return len(self.errors) == 0


def mask_pii(data: Dict[str, Any], fields_to_mask: Optional[List[str]] = None) -> Dict[str, Any]:
    """Mask personally identifiable information in response data"""
    if fields_to_mask is None:
        fields_to_mask = ['imsi', 'email', 'msisdn']
    
    masked_data = data.copy()
    
    for field in fields_to_mask:
        if field in masked_data and masked_data[field]:
            value = str(masked_data[field])
            if field == 'imsi' and len(value) >= 10:
                # Mask middle digits of IMSI: 123456***890123 
                masked_data[field] = value[:6] + '***' + value[-6:]
            elif field == 'email' and '@' in value:
                # Mask email: te***@ex***.com
                local, domain = value.split('@', 1)
                domain_parts = domain.split('.')
                masked_local = local[:2] + '***' if len(local) > 4 else local
                masked_domain = domain_parts[0][:2] + '***' if len(domain_parts[0]) > 4 else domain_parts[0]
                masked_data[field] = f"{masked_local}@{masked_domain}.{'.'.join(domain_parts[1:])}"
            elif field == 'msisdn' and len(value) >= 8:
                # Mask middle digits of MSISDN: +12***567890
                masked_data[field] = value[:3] + '***' + value[-6:]
    
    return masked_data


def get_db_connection_params(secret_arn: str, region: str = 'us-east-1') -> Dict[str, str]:
    """Get database connection parameters from AWS Secrets Manager"""
    try:
        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret.get('host', ''),
            'username': secret.get('username', ''),
            'password': secret.get('password', ''),
            'database': secret.get('dbname', secret.get('database', '')),
            'port': secret.get('port', 3306)
        }
    except Exception as e:
        print(f"Failed to get database credentials: {str(e)}")
        raise Exception(f"Database connection failed: {str(e)}")


def paginate_dynamodb_response(items: List[Dict[str, Any]], last_evaluated_key: Optional[Dict[str, Any]] = None,
                              limit: Optional[int] = None) -> Dict[str, Any]:
    """Format DynamoDB pagination response"""
    return {
        'items': items,
        'pagination': {
            'count': len(items),
            'hasMore': bool(last_evaluated_key),
            'lastKey': json.dumps(last_evaluated_key) if last_evaluated_key else None,
            'limit': limit
        }
    }


def paginate_sql_response(items: List[Dict[str, Any]], total_count: int, offset: int = 0, 
                         limit: int = 25) -> Dict[str, Any]:
    """Format SQL pagination response"""
    has_more = offset + len(items) < total_count
    next_offset = offset + limit if has_more else None
    
    return {
        'items': items,
        'pagination': {
            'count': len(items),
            'total': total_count,
            'offset': offset,
            'nextOffset': next_offset,
            'hasMore': has_more,
            'limit': limit
        }
    }


def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize data for logging (remove PII)"""
    sensitive_fields = ['password', 'token', 'secret', 'key', 'imsi', 'msisdn', 'email']
    
    def sanitize_value(key: str, value: Any) -> Any:
        if isinstance(key, str) and any(field in key.lower() for field in sensitive_fields):
            if isinstance(value, str) and len(value) > 4:
                return f"{value[:2]}***{value[-2:]}"
            else:
                return "***"
        elif isinstance(value, dict):
            return {k: sanitize_value(k, v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(str(i), item) for i, item in enumerate(value)]
        return value
    
    return {k: sanitize_value(k, v) for k, v in data.items()}


def parse_query_params(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and validate API Gateway query parameters"""
    query_params = event.get('queryStringParameters') or {}
    
    # Handle common pagination parameters
    try:
        limit = min(int(query_params.get('limit', 25)), 100)
    except (ValueError, TypeError):
        limit = 25
    
    try:
        page = max(int(query_params.get('page', 0)), 0)
    except (ValueError, TypeError):
        page = 0
    
    try:
        offset = max(int(query_params.get('offset', page * limit)), 0)
    except (ValueError, TypeError):
        offset = page * limit
    
    return {
        'limit': limit,
        'page': page,
        'offset': offset,
        'search': query_params.get('search', '').strip(),
        'status': query_params.get('status', '').strip(),
        'planId': query_params.get('planId', '').strip(),
        'lastKey': query_params.get('lastKey', '').strip(),
        'raw': query_params
    }


def get_request_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract request context information"""
    request_context = event.get('requestContext', {})
    headers = event.get('headers', {})
    
    return {
        'requestId': request_context.get('requestId', 'unknown'),
        'sourceIp': request_context.get('identity', {}).get('sourceIp', 'unknown'),
        'userAgent': headers.get('User-Agent', 'unknown'),
        'method': event.get('httpMethod', 'unknown'),
        'path': event.get('path', 'unknown'),
        'stage': request_context.get('stage', os.environ.get('STAGE', 'unknown')),
        'accountId': request_context.get('accountId', 'unknown')
    }


def format_subscriber_for_api(subscriber: Dict[str, Any], mask_pii: bool = True) -> Dict[str, Any]:
    """Format subscriber data for API response"""
    # Convert DynamoDB/RDS data to consistent API format
    formatted = {
        'uid': subscriber.get('uid', ''),
        'msisdn': subscriber.get('msisdn', ''),
        'imsi': subscriber.get('imsi', ''),
        'status': subscriber.get('status', 'ACTIVE'),
        'planId': subscriber.get('plan_id', subscriber.get('planId', '')),
        'email': subscriber.get('email', ''),
        'firstName': subscriber.get('first_name', subscriber.get('firstName', '')),
        'lastName': subscriber.get('last_name', subscriber.get('lastName', '')),
        'address': subscriber.get('address', ''),
        'dateOfBirth': subscriber.get('date_of_birth', subscriber.get('dateOfBirth', '')),
        'lastActivity': subscriber.get('last_activity', subscriber.get('lastActivity', '')),
        'createdAt': subscriber.get('created_at', subscriber.get('createdAt', '')),
        'updatedAt': subscriber.get('updated_at', subscriber.get('updatedAt', ''))
    }
    
    # Convert datetime objects to ISO strings
    for date_field in ['lastActivity', 'createdAt', 'updatedAt']:
        if formatted[date_field] and not isinstance(formatted[date_field], str):
            try:
                formatted[date_field] = formatted[date_field].isoformat()
            except:
                formatted[date_field] = str(formatted[date_field])
    
    # Mask PII if requested
    if mask_pii:
        formatted = mask_pii(formatted)
    
    return formatted


def format_subscriber_for_db(subscriber: Dict[str, Any], system: str = 'cloud') -> Dict[str, Any]:
    """Format subscriber data for database storage"""
    
    # Common fields
    formatted = {
        'uid': subscriber.get('uid', '').strip(),
        'msisdn': subscriber.get('msisdn', '').strip(),
        'imsi': subscriber.get('imsi', '').strip(),
        'status': subscriber.get('status', 'ACTIVE').upper(),
        'email': subscriber.get('email', '').strip() or None,
        'first_name': subscriber.get('firstName', '').strip() or None,
        'last_name': subscriber.get('lastName', '').strip() or None,
        'address': subscriber.get('address', '').strip() or None,
        'date_of_birth': subscriber.get('dateOfBirth', '').strip() or None
    }
    
    # Handle plan_id field name differences
    plan_id = subscriber.get('planId') or subscriber.get('plan_id', '')
    if plan_id:
        if system == 'cloud':
            formatted['plan_id'] = plan_id.strip()  # DynamoDB uses plan_id
        else:
            formatted['plan_id'] = plan_id.strip()  # RDS also uses plan_id
    
    # Add timestamps for new records
    now = datetime.utcnow()
    if not subscriber.get('uid'):  # New record
        formatted['created_at'] = now.isoformat()
    formatted['updated_at'] = now.isoformat()
    
    # Remove None values for DynamoDB
    if system == 'cloud':
        formatted = {k: v for k, v in formatted.items() if v is not None}
    
    return formatted


def handle_cors_preflight(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle CORS preflight OPTIONS requests"""
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {'message': 'CORS preflight handled'})
    return None


def extract_jwt_payload(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract and validate JWT payload from Authorization header"""
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization', '') or headers.get('authorization', '')
    
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]  # Remove 'Bearer ' prefix
    
    try:
        # Simple JWT payload extraction (not validating signature for now)
        import base64
        header, payload, signature = token.split('.')
        
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        
        decoded_payload = base64.urlsafe_b64decode(payload)
        return json.loads(decoded_payload)
    except Exception as e:
        print(f"Failed to decode JWT: {e}")
        return None


def log_request(event: Dict[str, Any], context: Any, extra_data: Optional[Dict[str, Any]] = None) -> None:
    """Log request with sanitized data"""
    request_context = get_request_context(event)
    
    log_data = {
        'requestId': context.aws_request_id,
        'method': event.get('httpMethod'),
        'path': event.get('path'),
        'stage': request_context['stage'],
        'sourceIp': request_context['sourceIp'],
        'userAgent': request_context['userAgent'][:100],  # Truncate long user agents
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if extra_data:
        log_data.update(sanitize_log_data(extra_data))
    
    print(f"REQUEST: {json.dumps(log_data, default=str)}")


def log_response(status_code: int, response_size: int, duration_ms: float, 
                extra_data: Optional[Dict[str, Any]] = None) -> None:
    """Log response with performance metrics"""
    log_data = {
        'statusCode': status_code,
        'responseSize': response_size,
        'duration': f"{duration_ms:.2f}ms",
        'timestamp': datetime.utcnow().isoformat()
    }
    
    if extra_data:
        log_data.update(sanitize_log_data(extra_data))
    
    print(f"RESPONSE: {json.dumps(log_data, default=str)}")


# Status constants
class SubscriberStatus:
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'
    SUSPENDED = 'SUSPENDED'
    DELETED = 'DELETED'
    
    ALL = [ACTIVE, INACTIVE, SUSPENDED, DELETED]


class JobStatus:
    PENDING = 'PENDING'
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    
    ALL = [PENDING, QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED]
    TERMINAL = [COMPLETED, FAILED, CANCELLED]


class JobType:
    MIGRATION = 'MIGRATION'
    BULK_DELETE = 'BULK_DELETE'
    AUDIT = 'AUDIT'
    EXPORT = 'EXPORT'
    
    ALL = [MIGRATION, BULK_DELETE, AUDIT, EXPORT]


# Default plan options
DEFAULT_PLANS = ['BASIC', 'PREMIUM', 'ENTERPRISE']