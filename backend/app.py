#!/usr/bin/env python3
"""
Subscriber Migration Portal - Bulletproof Production Backend
"""

import os
import json
import logging
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from functools import wraps

import boto3
import jwt
import pymysql
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from botocore.exceptions import ClientError
from serverless_wsgi import handle_request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration
CONFIG = {
    'VERSION': '2.0.1-production',
    'JWT_SECRET': os.getenv('JWT_SECRET', 'subscriber-portal-jwt-secret-2025'),
    'JWT_ALGORITHM': 'HS256',
    'JWT_EXPIRY_HOURS': 24,
    'SUBSCRIBER_TABLE_NAME': os.getenv('SUBSCRIBER_TABLE_NAME', 'subscriber-table'),
    'AUDIT_LOG_TABLE_NAME': os.getenv('AUDIT_LOG_TABLE_NAME', 'audit-log-table'),
    'MIGRATION_JOBS_TABLE_NAME': os.getenv('MIGRATION_JOBS_TABLE_NAME', 'migration-jobs-table'),
    'TOKEN_BLACKLIST_TABLE_NAME': os.getenv('TOKEN_BLACKLIST_TABLE_NAME', 'token-blacklist-table'),
    'MIGRATION_UPLOAD_BUCKET_NAME': os.getenv('MIGRATION_UPLOAD_BUCKET_NAME', 'migration-uploads'),
    'USERS_SECRET_ARN': os.getenv('USERS_SECRET_ARN'),
    'LEGACY_DB_SECRET_ARN': os.getenv('LEGACY_DB_SECRET_ARN'),
    'LEGACY_DB_HOST': os.getenv('LEGACY_DB_HOST'),
    'LEGACY_DB_PORT': int(os.getenv('LEGACY_DB_PORT', '3306')),
    'LEGACY_DB_NAME': os.getenv('LEGACY_DB_NAME', 'legacydb'),
    'PROV_MODE': os.getenv('PROV_MODE', 'dual_prov'),
    'FRONTEND_ORIGIN': os.getenv('FRONTEND_ORIGIN', '*'),
}

# CORS setup
CORS(app, origins=[CONFIG['FRONTEND_ORIGIN']] if CONFIG['FRONTEND_ORIGIN'] != '*' else ['*'], 
     supports_credentials=True)

# Rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["1000 per day", "200 per hour"]
)

# AWS clients
try:
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    secrets_client = boto3.client('secretsmanager')
    logger.info("AWS services initialized")
except Exception as e:
    logger.warning(f"AWS initialization: {str(e)}")
    dynamodb = s3_client = secrets_client = None

# DynamoDB tables
tables = {}
try:
    if dynamodb:
        tables['subscribers'] = dynamodb.Table(CONFIG['SUBSCRIBER_TABLE_NAME'])
        tables['audit_logs'] = dynamodb.Table(CONFIG['AUDIT_LOG_TABLE_NAME'])
        tables['migration_jobs'] = dynamodb.Table(CONFIG['MIGRATION_JOBS_TABLE_NAME'])
        if CONFIG.get('TOKEN_BLACKLIST_TABLE_NAME'):
            tables['token_blacklist'] = dynamodb.Table(CONFIG['TOKEN_BLACKLIST_TABLE_NAME'])
        logger.info("DynamoDB tables initialized")
except Exception as e:
    logger.warning(f"DynamoDB initialization: {str(e)}")

# User management
def load_users_from_secrets():
    """Load users from Secrets Manager."""
    try:
        if CONFIG.get('USERS_SECRET_ARN') and secrets_client:
            response = secrets_client.get_secret_value(SecretId=CONFIG['USERS_SECRET_ARN'])
            return json.loads(response['SecretString'])
    except Exception as e:
        logger.warning(f"Could not load users from secrets: {str(e)}")
    
    # Fallback users
    return {
        'admin': {
            'password_hash': generate_password_hash('Admin@123'),
            'role': 'admin',
            'permissions': ['read', 'write', 'delete', 'admin'],
            'rate_limit_override': True
        },
        'operator': {
            'password_hash': generate_password_hash('Operator@123'), 
            'role': 'operator',
            'permissions': ['read', 'write'],
            'rate_limit_override': False
        },
        'guest': {
            'password_hash': generate_password_hash('Guest@123'),
            'role': 'guest', 
            'permissions': ['read'],
            'rate_limit_override': False
        }
    }

# Input sanitization
def sanitize_input(input_str, max_length=255):
    """Sanitize input."""
    if not isinstance(input_str, str):
        return str(input_str)[:max_length]
    return input_str.strip()[:max_length]

# Token blacklist
def is_token_blacklisted(jti):
    """Check if token is blacklisted."""
    try:
        if 'token_blacklist' in tables:
            response = tables['token_blacklist'].get_item(Key={'jti': jti})
            return 'Item' in response
    except Exception:
        pass
    return False

def blacklist_token(jti, exp):
    """Blacklist token."""
    try:
        if 'token_blacklist' in tables:
            tables['token_blacklist'].put_item(
                Item={'jti': jti, 'blacklisted_at': datetime.utcnow().isoformat(), 'ttl': int(exp)}
            )
    except Exception:
        pass

# Database connections
def get_legacy_db_connection():
    """Get legacy DB connection."""
    try:
        if not CONFIG.get('LEGACY_DB_SECRET_ARN') or not secrets_client:
            return None
            
        response = secrets_client.get_secret_value(SecretId=CONFIG['LEGACY_DB_SECRET_ARN'])
        secret = json.loads(response['SecretString'])
        
        return pymysql.connect(
            host=CONFIG['LEGACY_DB_HOST'],
            port=CONFIG['LEGACY_DB_PORT'],
            user=secret['username'],
            password=secret['password'],
            database=CONFIG['LEGACY_DB_NAME'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
            read_timeout=3,
            write_timeout=3
        )
    except Exception as e:
        logger.warning(f"Legacy DB connection failed: {str(e)}")
        return None

# User Management
class UserManager:
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Authenticate user."""
        username = sanitize_input(username, 50)
        users = load_users_from_secrets()
        user = users.get(username)
        
        if user and check_password_hash(user['password_hash'], password):
            return {
                'username': username,
                'role': user['role'],
                'permissions': user['permissions'],
                'rate_limit_override': user.get('rate_limit_override', False)
            }
        return None
    
    @staticmethod
    def generate_jwt_token(user_data: Dict) -> str:
        """Generate JWT token."""
        payload = {
            'sub': user_data['username'],
            'role': user_data['role'],
            'permissions': user_data['permissions'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=CONFIG['JWT_EXPIRY_HOURS']),
            'jti': str(uuid.uuid4())
        }
        return jwt.encode(payload, CONFIG['JWT_SECRET'], algorithm=CONFIG['JWT_ALGORITHM'])
    
    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict]:
        """Verify JWT token."""
        try:
            payload = jwt.decode(token, CONFIG['JWT_SECRET'], algorithms=[CONFIG['JWT_ALGORITHM']])
            
            if is_token_blacklisted(payload.get('jti')):
                return None
            
            return {
                'username': payload['sub'],
                'role': payload['role'],
                'permissions': payload['permissions'],
                'jti': payload.get('jti'),
                'exp': payload.get('exp')
            }
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

# Authentication decorator
def require_auth(permissions=None):
    """Authentication decorator."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return create_response(message="Authentication required", status_code=401)
            
            token = auth_header.split(' ')[1]
            user = UserManager.verify_jwt_token(token)
            
            if not user:
                return create_response(message="Invalid or expired token", status_code=401)
            
            if permissions:
                required_perms = permissions if isinstance(permissions, list) else [permissions]
                if not any(perm in user['permissions'] for perm in required_perms):
                    return create_response(message="Insufficient permissions", status_code=403)
            
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Utilities
def create_response(data=None, message="Success", status_code=200, error=None):
    """Create API response."""
    response = {
        'status': 'success' if status_code < 400 else 'error',
        'message': message,
        'timestamp': datetime.utcnow().isoformat(),
        'version': CONFIG['VERSION']
    }
    
    if data is not None:
        response['data'] = data
    
    if error:
        response['error'] = error
    
    return jsonify(response), status_code

def audit_log(action: str, resource: str, user: str = "system", details: Dict = None):
    """Audit logging."""
    try:
        if 'audit_logs' in tables:
            log_entry = {
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': action,
                'resource': resource,
                'user': user,
                'ip_address': request.remote_addr if request else 'system',
                'details': details or {},
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())
            }
            tables['audit_logs'].put_item(Item=log_entry)
    except Exception:
        pass

# === ROUTES ===

@app.route('/api/health', methods=['GET'])
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    health_status = {
        'status': 'healthy',
        'version': CONFIG['VERSION'],
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'app': True,
            'dynamodb': bool(dynamodb),
            's3': bool(s3_client), 
            'secrets_manager': bool(secrets_client)
        },
        'current_mode': CONFIG['PROV_MODE']
    }
    
    return create_response(data=health_status, message="Health check completed")

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """User authentication."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        username = sanitize_input(data.get('username', ''), 50)
        password = data.get('password', '')
        
        if not username or not password:
            return create_response(message="Username and password required", status_code=400)
        
        user = UserManager.authenticate(username, password)
        if not user:
            audit_log('login_failed', 'auth', username)
            return create_response(message="Invalid credentials", status_code=401)
        
        token = UserManager.generate_jwt_token(user)
        audit_log('login_success', 'auth', username)
        
        return create_response(data={
            'token': token,
            'user': {
                'username': user['username'],
                'role': user['role'],
                'permissions': user['permissions']
            },
            'expires_in': CONFIG['JWT_EXPIRY_HOURS'] * 3600
        }, message="Login successful")
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return create_response(message="Login failed", status_code=500)

@app.route('/api/auth/logout', methods=['POST'])
@require_auth()
def logout():
    """Logout with token revocation."""
    try:
        user = g.current_user
        if user.get('jti') and user.get('exp'):
            blacklist_token(user['jti'], user['exp'])
        
        audit_log('logout', 'auth', user['username'])
        return create_response(message="Logout successful")
    except Exception:
        return create_response(message="Logout completed")

@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
def get_dashboard_stats():
    """Dashboard statistics."""
    try:
        stats = {
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'legacySubscribers': 0,
            'systemHealth': 'healthy',
            'provisioningMode': CONFIG['PROV_MODE'],
            'lastUpdated': datetime.utcnow().isoformat()
        }
        
        # Get cloud subscriber count
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(Select='COUNT')
                stats['cloudSubscribers'] = response.get('Count', 0)
        except Exception:
            stats['systemHealth'] = 'degraded'
        
        # Get legacy subscriber count
        try:
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != 'DELETED'")
                    result = cursor.fetchone()
                    stats['legacySubscribers'] = result['count'] if result else 0
                connection.close()
        except Exception:
            pass
        
        stats['totalSubscribers'] = stats['cloudSubscribers'] + stats['legacySubscribers']
        
        return create_response(data=stats)
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return create_response(message="Failed to get dashboard stats", status_code=500)

@app.route('/api/subscribers', methods=['GET'])
@require_auth(['read'])
def get_subscribers():
    """Get subscribers."""
    try:
        limit = min(int(request.args.get('limit', '50')), 100)
        search = sanitize_input(request.args.get('search', ''), 100)
        
        subscribers = []
        
        # Cloud subscribers
        if 'subscribers' in tables:
            try:
                if search:
                    response = tables['subscribers'].scan(
                        FilterExpression='contains(subscriberId, :search) OR contains(imsi, :search)',
                        ExpressionAttributeValues={':search': search},
                        Limit=limit
                    )
                else:
                    response = tables['subscribers'].scan(Limit=limit)
                
                cloud_subscribers = response.get('Items', [])
                for sub in cloud_subscribers:
                    sub['source'] = 'cloud'
                subscribers.extend(cloud_subscribers)
            except Exception as e:
                logger.error(f"Cloud query error: {str(e)}")
        
        return create_response(data={
            'subscribers': subscribers,
            'count': len(subscribers),
            'search': search
        })
        
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500)

@app.route('/api/subscribers', methods=['POST'])
@require_auth(['write'])
def create_subscriber():
    """Create subscriber."""
    try:
        data = request.get_json()
        
        if not data or not data.get('uid') or not data.get('imsi'):
            return create_response(message="Missing required fields: uid, imsi", status_code=400)
        
        # Basic data preparation
        uid = sanitize_input(data['uid'], 50)
        data['subscriberId'] = uid
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = g.current_user['username']
        
        # Store in DynamoDB
        if 'subscribers' in tables:
            tables['subscribers'].put_item(Item=data)
        
        audit_log('subscriber_created', 'subscriber', g.current_user['username'], {'uid': uid})
        
        return create_response(data={'uid': uid}, message="Subscriber created", status_code=201)
        
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_response(message=f"Failed to create subscriber: {str(e)}", status_code=500)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return create_response(message="Endpoint not found", status_code=404)

@app.errorhandler(500)
def internal_error(error):
    return create_response(message="Internal server error", status_code=500)

@app.errorhandler(429)
def ratelimit_handler(e):
    return create_response(message="Rate limit exceeded", status_code=429)

# **BULLETPROOF LAMBDA HANDLER - FIXED**
def lambda_handler(event, context):
    """Bulletproof AWS Lambda entry point with proper event handling."""
    try:
        logger.info(f"Lambda invoked with event: {json.dumps(event, default=str)[:500]}")
        
        # Handle completely empty event
        if not event:
            logger.info("Handling empty event")
            event = {}
        
        # Create standard CORS headers
        cors_headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With'
        }
        
        # **CRITICAL FIX**: Ensure ALL required serverless_wsgi fields exist
        # This prevents the KeyError: 'headers' issue
        standardized_event = {
            'httpMethod': event.get('httpMethod', 'GET'),
            'path': event.get('path', '/api/health'),
            'headers': event.get('headers', {}),
            'multiValueHeaders': event.get('multiValueHeaders', {}),
            'queryStringParameters': event.get('queryStringParameters', {}),
            'multiValueQueryStringParameters': event.get('multiValueQueryStringParameters', {}),
            'body': event.get('body', None),
            'isBase64Encoded': event.get('isBase64Encoded', False),
            'pathParameters': event.get('pathParameters', {}),
            'stageVariables': event.get('stageVariables', {}),
            'requestContext': event.get('requestContext', {
                'requestId': context.aws_request_id if context else f'local-{uuid.uuid4().hex[:8]}',
                'stage': 'prod',
                'httpMethod': event.get('httpMethod', 'GET'),
                'path': event.get('path', '/api/health'),
                'identity': {
                    'sourceIp': '127.0.0.1',
                    'userAgent': 'AWS Lambda'
                },
                'requestTime': datetime.utcnow().strftime('%d/%b/%Y:%H:%M:%S +0000'),
                'requestTimeEpoch': int(datetime.utcnow().timestamp() * 1000)
            })
        }
        
        # Handle health check directly for reliability
        if standardized_event['path'] in ['/api/health', '/health', '/']:
            logger.info("Direct health check response")
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'Subscriber Migration Portal API is healthy',
                    'version': CONFIG['VERSION'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'handler': 'lambda_handler',
                    'services': {
                        'app': True,
                        'dynamodb': bool(dynamodb),
                        's3': bool(s3_client),
                        'secrets_manager': bool(secrets_client)
                    },
                    'event_received': True,
                    'path': standardized_event['path'],
                    'method': standardized_event['httpMethod']
                }),
                'isBase64Encoded': False
            }
        
        # Process through Flask using serverless_wsgi
        logger.info(f"Processing Flask request: {standardized_event['httpMethod']} {standardized_event['path']}")
        
        # **FIXED**: Pass the properly structured event to serverless_wsgi
        response = handle_request(app, standardized_event, context)
        
        # Ensure CORS headers are in response
        if 'headers' not in response:
            response['headers'] = {}
        response['headers'].update(cors_headers)
        
        logger.info(f"Lambda response status: {response.get('statusCode', 'unknown')}")
        return response
        
    except Exception as e:
        logger.error(f"Lambda handler critical error: {str(e)}\n{traceback.format_exc()}")
        
        # Return error response with proper structure
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization'
            },
            'body': json.dumps({
                'status': 'error',
                'message': 'Lambda handler encountered an error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'version': CONFIG['VERSION'],
                'debug_info': {
                    'error_type': type(e).__name__,
                    'handler': 'lambda_handler'
                }
            }),
            'isBase64Encoded': False
        }

# For local development
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)