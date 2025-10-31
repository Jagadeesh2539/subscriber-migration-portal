#!/usr/bin/env python3
"""
Common utilities for AWS Lambda functions
Replaces Flask-specific functionality with pure AWS services
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import boto3
import jwt
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients (initialized once per container)
aws_clients = {
    'dynamodb': boto3.resource('dynamodb'),
    's3': boto3.client('s3'),
    'secrets': boto3.client('secretsmanager'),
    'cloudwatch': boto3.client('cloudwatch')
}

# Environment variables
ENV_CONFIG = {
    'JWT_SECRET': os.environ.get('JWT_SECRET'),
    'SUBSCRIBER_TABLE': os.environ.get('SUBSCRIBER_TABLE'),
    'AUDIT_LOG_TABLE': os.environ.get('AUDIT_LOG_TABLE'),
    'MIGRATION_JOBS_TABLE': os.environ.get('MIGRATION_JOBS_TABLE'),
    'UPLOAD_BUCKET': os.environ.get('UPLOAD_BUCKET'),
    'USERS_SECRET_ARN': os.environ.get('USERS_SECRET_ARN'),
    'STAGE': os.environ.get('STAGE', 'dev'),
    'CORS_ORIGINS': os.environ.get('CORS_ORIGINS', '*').split(',')
}

# ======================
# CORS HANDLER
# ======================
def get_cors_headers(origin: str = None) -> Dict[str, str]:
    """Get CORS headers for API responses."""
    allowed_origins = ENV_CONFIG['CORS_ORIGINS']
    
    # Check if origin is allowed
    if origin and origin in allowed_origins:
        cors_origin = origin
    elif '*' in allowed_origins:
        cors_origin = '*'
    else:
        cors_origin = allowed_origins[0] if allowed_origins else '*'
    
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': cors_origin,
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With',
        'Access-Control-Allow-Credentials': 'true',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block'
    }

# ======================
# RESPONSE HELPERS
# ======================
def create_response(
    status_code: int = 200,
    body: Dict = None,
    headers: Dict = None,
    origin: str = None
) -> Dict:
    """Create standardized Lambda response."""
    
    response_headers = get_cors_headers(origin)
    if headers:
        response_headers.update(headers)
    
    response_body = {
        'status': 'success' if status_code < 400 else 'error',
        'timestamp': datetime.utcnow().isoformat(),
        'data': body if status_code < 400 else None
    }
    
    if status_code >= 400 and body:
        response_body['error'] = body.get('message', 'An error occurred')
        response_body['error_code'] = body.get('code', 'UNKNOWN_ERROR')
    
    return {
        'statusCode': status_code,
        'headers': response_headers,
        'body': json.dumps(response_body, default=str),
        'isBase64Encoded': False
    }

def create_error_response(
    status_code: int,
    message: str,
    error_code: str = None,
    origin: str = None
) -> Dict:
    """Create error response."""
    return create_response(
        status_code=status_code,
        body={
            'message': message,
            'code': error_code or 'ERROR'
        },
        origin=origin
    )

# ======================
# INPUT VALIDATION
# ======================
class InputValidator:
    """Input validation and sanitization utilities."""
    
    PATTERNS = {
        'uid': re.compile(r'^[A-Za-z0-9_-]{1,50}$'),
        'imsi': re.compile(r'^[0-9]{10,15}$'),
        'msisdn': re.compile(r'^\+?[1-9][0-9]{7,14}$'),
        'email': re.compile(r'^[^@]+@[^@]+\.[^@]+$'),
        'alphanumeric': re.compile(r'^[A-Za-z0-9\s_-]+$'),
        'status': re.compile(r'^(ACTIVE|INACTIVE|SUSPENDED|DELETED)$')
    }
    
    @staticmethod
    def sanitize_string(value: Any, max_length: int = 255, pattern: str = None) -> str:
        """Sanitize string input."""
        if value is None:
            return ''
        
        # Convert to string and strip
        clean_value = str(value).strip()[:max_length]
        
        # Validate pattern if provided
        if pattern and pattern in InputValidator.PATTERNS:
            if not InputValidator.PATTERNS[pattern].match(clean_value):
                raise ValueError(f'Invalid format for {pattern}')
        
        return clean_value
    
    @staticmethod
    def validate_required_fields(data: Dict, required_fields: List[str]) -> None:
        """Validate required fields exist."""
        missing = [field for field in required_fields if not data.get(field)]
        if missing:
            raise ValueError(f'Missing required fields: {", ".join(missing)}')
    
    @staticmethod
    def validate_pagination(limit: Any = None, offset: Any = None) -> tuple:
        """Validate pagination parameters."""
        try:
            limit = min(int(limit or 50), 100)
            offset = max(int(offset or 0), 0)
        except (ValueError, TypeError):
            raise ValueError('Invalid pagination parameters')
        return limit, offset

# ======================
# JWT AUTHENTICATION
# ======================
class JWTAuth:
    """JWT authentication utilities."""
    
    @staticmethod
    def generate_token(user_data: Dict) -> str:
        """Generate JWT token."""
        payload = {
            'sub': user_data['username'],
            'role': user_data['role'],
            'permissions': user_data['permissions'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=8),
            'jti': str(uuid.uuid4()),
            'iss': 'subscriber-migration-portal',
            'aud': 'subscriber-portal-api'
        }
        
        return jwt.encode(
            payload,
            ENV_CONFIG['JWT_SECRET'],
            algorithm='HS256'
        )
    
    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """Verify JWT token."""
        try:
            payload = jwt.decode(
                token,
                ENV_CONFIG['JWT_SECRET'],
                algorithms=['HS256'],
                audience='subscriber-portal-api',
                issuer='subscriber-migration-portal'
            )
            
            return {
                'username': payload['sub'],
                'role': payload['role'],
                'permissions': payload['permissions'],
                'jti': payload.get('jti'),
                'exp': payload.get('exp')
            }
        except jwt.ExpiredSignatureError:
            logger.warning('JWT token expired')
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f'Invalid JWT token: {str(e)}')
            return None
    
    @staticmethod
    def extract_token_from_event(event: Dict) -> Optional[str]:
        """Extract JWT token from Lambda event."""
        # Check Authorization header
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header[7:]
        
        # Check query parameters (for WebSocket connections)
        query_params = event.get('queryStringParameters') or {}
        return query_params.get('token')
    
    @staticmethod
    def check_permissions(user: Dict, required_permissions: List[str]) -> bool:
        """Check if user has required permissions."""
        if not user or not required_permissions:
            return False
        
        user_permissions = user.get('permissions', [])
        return any(perm in user_permissions for perm in required_permissions)

# ======================
# DATABASE HELPERS
# ======================
class DynamoDBHelper:
    """DynamoDB helper functions."""
    
    @staticmethod
    def get_table(table_name: str):
        """Get DynamoDB table resource."""
        return aws_clients['dynamodb'].Table(table_name)
    
    @staticmethod
    def scan_with_pagination(table_name: str, limit: int = 50, last_key: Dict = None, 
                           filter_expression = None, **kwargs) -> Dict:
        """Scan table with pagination support."""
        table = DynamoDBHelper.get_table(table_name)
        
        scan_kwargs = {
            'Limit': limit
        }
        
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = last_key
        
        if filter_expression:
            scan_kwargs['FilterExpression'] = filter_expression
        
        scan_kwargs.update(kwargs)
        
        try:
            response = table.scan(**scan_kwargs)
            return {
                'items': response.get('Items', []),
                'last_key': response.get('LastEvaluatedKey'),
                'count': response.get('Count', 0),
                'scanned_count': response.get('ScannedCount', 0)
            }
        except ClientError as e:
            logger.error(f'DynamoDB scan error: {str(e)}')
            raise
    
    @staticmethod
    def query_with_pagination(table_name: str, key_condition_expression,
                            limit: int = 50, last_key: Dict = None, 
                            index_name: str = None, **kwargs) -> Dict:
        """Query table with pagination support."""
        table = DynamoDBHelper.get_table(table_name)
        
        query_kwargs = {
            'KeyConditionExpression': key_condition_expression,
            'Limit': limit
        }
        
        if last_key:
            query_kwargs['ExclusiveStartKey'] = last_key
        
        if index_name:
            query_kwargs['IndexName'] = index_name
        
        query_kwargs.update(kwargs)
        
        try:
            response = table.query(**query_kwargs)
            return {
                'items': response.get('Items', []),
                'last_key': response.get('LastEvaluatedKey'),
                'count': response.get('Count', 0)
            }
        except ClientError as e:
            logger.error(f'DynamoDB query error: {str(e)}')
            raise
    
    @staticmethod
    def put_item_safe(table_name: str, item: Dict) -> bool:
        """Put item with error handling."""
        table = DynamoDBHelper.get_table(table_name)
        
        try:
            table.put_item(Item=item)
            return True
        except ClientError as e:
            logger.error(f'DynamoDB put_item error: {str(e)}')
            return False
    
    @staticmethod
    def update_item_safe(table_name: str, key: Dict, 
                        update_expression: str, expression_values: Dict,
                        condition_expression = None) -> bool:
        """Update item with error handling."""
        table = DynamoDBHelper.get_table(table_name)
        
        try:
            update_kwargs = {
                'Key': key,
                'UpdateExpression': update_expression,
                'ExpressionAttributeValues': expression_values,
                'ReturnValues': 'UPDATED_NEW'
            }
            
            if condition_expression:
                update_kwargs['ConditionExpression'] = condition_expression
            
            table.update_item(**update_kwargs)
            return True
        except ClientError as e:
            logger.error(f'DynamoDB update_item error: {str(e)}')
            return False

# ======================
# SECRETS MANAGER
# ======================
class SecretsManager:
    """AWS Secrets Manager utilities."""
    
    @staticmethod
    def get_secret(secret_arn: str) -> Dict:
        """Get secret value from AWS Secrets Manager."""
        try:
            response = aws_clients['secrets'].get_secret_value(SecretId=secret_arn)
            return json.loads(response['SecretString'])
        except ClientError as e:
            logger.error(f'Failed to get secret {secret_arn}: {str(e)}')
            raise
    
    @staticmethod
    def get_users() -> Dict:
        """Get users from secrets manager."""
        if not ENV_CONFIG['USERS_SECRET_ARN']:
            raise ValueError('USERS_SECRET_ARN not configured')
        
        return SecretsManager.get_secret(ENV_CONFIG['USERS_SECRET_ARN'])

# ======================
# AUDIT LOGGING
# ======================
class AuditLogger:
    """Audit logging utilities."""
    
    @staticmethod
    def log_activity(action: str, resource: str, user: str = 'system', 
                    details: Dict = None, event: Dict = None) -> bool:
        """Log activity to audit table."""
        if not ENV_CONFIG['AUDIT_LOG_TABLE']:
            return False
        
        try:
            log_entry = {
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': InputValidator.sanitize_string(action, 100),
                'resource': InputValidator.sanitize_string(resource, 100),
                'user': InputValidator.sanitize_string(user, 50),
                'ip_address': AuditLogger._extract_ip(event),
                'user_agent': AuditLogger._extract_user_agent(event),
                'details': AuditLogger._sanitize_details(details or {}),
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())
            }
            
            return DynamoDBHelper.put_item_safe(ENV_CONFIG['AUDIT_LOG_TABLE'], log_entry)
        except Exception as e:
            logger.error(f'Audit logging failed: {str(e)}')
            return False
    
    @staticmethod
    def _extract_ip(event: Dict) -> str:
        """Extract IP address from Lambda event."""
        if not event:
            return 'unknown'
        
        request_context = event.get('requestContext', {})
        identity = request_context.get('identity', {})
        return identity.get('sourceIp', 'unknown')
    
    @staticmethod
    def _extract_user_agent(event: Dict) -> str:
        """Extract user agent from Lambda event."""
        if not event:
            return 'unknown'
        
        headers = event.get('headers', {})
        user_agent = headers.get('User-Agent') or headers.get('user-agent', 'unknown')
        return InputValidator.sanitize_string(user_agent, 200)
    
    @staticmethod
    def _sanitize_details(details: Dict) -> Dict:
        """Sanitize audit log details to remove PII."""
        safe_details = {}
        
        for key, value in details.items():
            if any(pii in key.lower() for pii in ['password', 'token', 'imsi', 'msisdn']):
                safe_details[key] = AuditLogger._mask_pii(str(value))
            else:
                safe_details[key] = value
        
        return safe_details
    
    @staticmethod
    def _mask_pii(value: str, mask_char: str = '*', visible_chars: int = 4) -> str:
        """Mask PII data for logging."""
        if not value or len(value) <= visible_chars:
            return mask_char * len(value) if value else ''
        
        return value[:2] + mask_char * (len(value) - visible_chars) + value[-2:]

# ======================
# S3 HELPERS
# ======================
class S3Helper:
    """S3 utilities."""
    
    @staticmethod
    def upload_file(bucket: str, key: str, file_content: bytes, 
                   content_type: str = 'application/octet-stream') -> bool:
        """Upload file to S3."""
        try:
            aws_clients['s3'].put_object(
                Bucket=bucket,
                Key=key,
                Body=file_content,
                ContentType=content_type,
                ServerSideEncryption='AES256'
            )
            return True
        except ClientError as e:
            logger.error(f'S3 upload error: {str(e)}')
            return False
    
    @staticmethod
    def generate_presigned_url(bucket: str, key: str, expiration: int = 3600) -> Optional[str]:
        """Generate presigned URL for S3 object."""
        try:
            return aws_clients['s3'].generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
        except ClientError as e:
            logger.error(f'Presigned URL generation error: {str(e)}')
            return None

# ======================
# CLOUDWATCH METRICS
# ======================
class MetricsHelper:
    """CloudWatch metrics utilities."""
    
    @staticmethod
    def put_metric(metric_name: str, value: float, unit: str = 'Count', 
                  namespace: str = 'SubscriberPortal', dimensions: Dict = None):
        """Put custom metric to CloudWatch."""
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': str(v)} for k, v in dimensions.items()
                ]
            
            aws_clients['cloudwatch'].put_metric_data(
                Namespace=namespace,
                MetricData=[metric_data]
            )
        except ClientError as e:
            logger.error(f'CloudWatch metrics error: {str(e)}')

# ======================
# LAMBDA EVENT HELPERS
# ======================
def parse_lambda_event(event: Dict) -> Dict:
    """Parse and normalize Lambda event."""
    return {
        'http_method': event.get('httpMethod', 'GET'),
        'path': event.get('path', '/'),
        'path_parameters': event.get('pathParameters') or {},
        'query_parameters': event.get('queryStringParameters') or {},
        'headers': event.get('headers', {}),
        'body': event.get('body'),
        'is_base64_encoded': event.get('isBase64Encoded', False),
        'request_context': event.get('requestContext', {}),
        'stage_variables': event.get('stageVariables', {})
    }

def parse_request_body(event: Dict) -> Dict:
    """Parse JSON request body from Lambda event."""
    body = event.get('body')
    if not body:
        return {}
    
    try:
        if event.get('isBase64Encoded', False):
            import base64
            body = base64.b64decode(body).decode('utf-8')
        
        return json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f'Failed to parse request body: {str(e)}')
        raise ValueError('Invalid JSON in request body')

# ======================
# EXCEPTION HANDLING
# ======================
class APIException(Exception):
    """Custom API exception."""
    
    def __init__(self, message: str, status_code: int = 400, error_code: str = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or 'API_ERROR'

def handle_exceptions(func):
    """Decorator to handle exceptions in Lambda functions."""
    def wrapper(event, context):
        try:
            return func(event, context)
        except APIException as e:
            logger.error(f'API Exception: {e.message}')
            return create_error_response(
                status_code=e.status_code,
                message=e.message,
                error_code=e.error_code,
                origin=event.get('headers', {}).get('origin')
            )
        except ValueError as e:
            logger.error(f'Validation error: {str(e)}')
            return create_error_response(
                status_code=400,
                message=str(e),
                error_code='VALIDATION_ERROR',
                origin=event.get('headers', {}).get('origin')
            )
        except Exception as e:
            logger.error(f'Unexpected error: {str(e)}')
            return create_error_response(
                status_code=500,
                message='Internal server error',
                error_code='INTERNAL_ERROR',
                origin=event.get('headers', {}).get('origin')
            )
    
    return wrapper