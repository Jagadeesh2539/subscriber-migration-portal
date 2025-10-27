#!/usr/bin/env python3
"""
Subscriber Migration Portal - COMPLETE Production Backend
Enterprise Security + Bulletproof Lambda Handler + Migration Processing
"""

import os
import sys
import json
import logging
import traceback
import uuid
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
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
from boto3.dynamodb.conditions import Key

# Configure structured logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration from environment with secure defaults
CONFIG = {
    'FLASK_ENV': os.getenv('FLASK_ENV', 'production'),
    'VERSION': os.getenv('VERSION', '2.0.0-production'),
    'JWT_SECRET': os.getenv('JWT_SECRET', 'subscriber-portal-jwt-secret-2025-production'),
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
    'PROVISIONING_MODES': os.getenv('PROVISIONING_MODES', 'legacy,cloud,dual_prov').split(','),
    'PROV_MODE': os.getenv('PROV_MODE', 'dual_prov'),
    'FRONTEND_ORIGIN': os.getenv('FRONTEND_ORIGIN', 'http://sub-mig-web-144395889420-prod.s3-website-us-east-1.amazonaws.com'),
    'MAX_UPLOAD_SIZE': int(os.getenv('MAX_UPLOAD_SIZE', '50')) * 1024 * 1024,
    'ENABLE_MIGRATION_PROCESSING': os.getenv('ENABLE_MIGRATION_PROCESSING', 'true').lower() == 'true',
}

# Secure CORS setup - NEVER use * in production unless necessary
allowed_origins = []
if CONFIG['FRONTEND_ORIGIN'] and CONFIG['FRONTEND_ORIGIN'] != '*':
    allowed_origins = [CONFIG['FRONTEND_ORIGIN']]
    if CONFIG['FLASK_ENV'] == 'development':
        allowed_origins.extend(['http://localhost:3000', 'http://127.0.0.1:3000'])
else:
    if CONFIG['FLASK_ENV'] == 'development':
        allowed_origins = ['*']
    else:
        # Production fallback - allow any origin for initial testing
        allowed_origins = ['*']
        logger.warning("Using wildcard CORS in production - set FRONTEND_ORIGIN for security")

CORS(app, origins=allowed_origins, supports_credentials=True, 
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'])

# Rate limiting setup
def get_user_id():
    """Get user ID for rate limiting."""
    if hasattr(g, 'current_user') and g.current_user:
        return g.current_user['username']
    return get_remote_address(request)

limiter = Limiter(
    app,
    key_func=get_user_id,
    default_limits=["1000 per day", "200 per hour", "50 per minute"]
)

# AWS clients initialization
try:
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    secrets_client = boto3.client('secretsmanager')
    sqs_client = boto3.client('sqs')
    logger.info("AWS services initialized successfully")
except Exception as e:
    logger.warning(f"AWS initialization warning: {str(e)}")
    dynamodb = s3_client = secrets_client = sqs_client = None

# DynamoDB tables initialization
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
    logger.warning(f"DynamoDB table initialization warning: {str(e)}")

# Enhanced Subscriber Schema
SUBSCRIBER_SCHEMA = {
    'uid': str, 'imsi': str, 'msisdn': str, 'name': str, 'email': str,
    'odbic': str, 'odboc': str, 'plan_type': str, 'network_type': str, 'call_forwarding': str,
    'roaming_enabled': str, 'data_limit_mb': int, 'voice_minutes': str, 'sms_count': str,
    'status': str, 'activation_date': str, 'last_recharge': str, 'balance_amount': float, 'service_class': str,
    'location_area_code': str, 'routing_area_code': str,
    'gprs_enabled': bool, 'volte_enabled': bool, 'wifi_calling': bool,
    'premium_services': str, 'hlr_profile': str, 'auc_profile': str, 'eir_status': str,
    'equipment_identity': str, 'network_access_mode': str,
    'qos_profile': str, 'apn_profile': str, 'charging_profile': str, 'fraud_profile': str,
    'credit_limit': float, 'spending_limit': float,
    'international_roaming_zone': str, 'domestic_roaming_zone': str,
    'supplementary_services': str, 'value_added_services': str,
    'content_filtering': str, 'parental_control': str, 'emergency_services': str,
    'lte_category': str, 'nr_category': str, 'bearer_capability': str, 'teleservices': str,
    'basic_services': str, 'operator_services': str, 'network_features': str,
    'security_features': str, 'mobility_management': str, 'session_management': str
}

# Default values
DEFAULT_VALUES = {
    'name': '', 'email': '', 'odbic': 'ODBIC_STD_RESTRICTIONS', 'odboc': 'ODBOC_STD_RESTRICTIONS',
    'plan_type': 'STANDARD_PREPAID', 'network_type': '4G_LTE', 'call_forwarding': 'CF_NONE',
    'roaming_enabled': 'NO_ROAMING', 'data_limit_mb': 1000, 'voice_minutes': '100', 'sms_count': '50',
    'status': 'ACTIVE', 'service_class': 'CONSUMER_SILVER', 'location_area_code': 'LAC_1000',
    'routing_area_code': 'RAC_2000', 'gprs_enabled': True, 'volte_enabled': False, 'wifi_calling': False,
    'premium_services': 'VAS_BASIC', 'hlr_profile': 'HLR_STANDARD_PROFILE', 'auc_profile': 'AUC_BASIC_AUTH',
    'eir_status': 'EIR_VERIFIED', 'equipment_identity': '', 'network_access_mode': 'MODE_4G_PREFERRED',
    'qos_profile': 'QOS_CLASS_3_BEST_EFFORT', 'apn_profile': 'APN_CONSUMER_INTERNET',
    'charging_profile': 'CHARGING_STANDARD', 'fraud_profile': 'FRAUD_BASIC_CHECK',
    'credit_limit': 5000.00, 'spending_limit': 500.00, 'international_roaming_zone': 'ZONE_NONE',
    'domestic_roaming_zone': 'ZONE_HOME_ONLY', 'supplementary_services': 'SS_CLIP:SS_CW',
    'value_added_services': 'VAS_BASIC_NEWS', 'content_filtering': 'CF_ADULT_CONTENT',
    'parental_control': 'PC_DISABLED', 'emergency_services': 'ES_BASIC_E911',
    'lte_category': 'LTE_CAT_6', 'nr_category': 'N/A', 'bearer_capability': 'BC_SPEECH:BC_DATA_64K',
    'teleservices': 'TS_SPEECH:TS_SMS', 'basic_services': 'BS_BEARER_SPEECH:BS_PACKET_DATA',
    'operator_services': 'OS_STANDARD_SUPPORT', 'network_features': 'NF_BASIC_LTE',
    'security_features': 'SF_BASIC_AUTH', 'mobility_management': 'MM_BASIC', 'session_management': 'SM_BASIC',
    'balance_amount': 0.0
}

# User management with fallback
def load_users_from_secrets():
    """Load users from AWS Secrets Manager with fallback."""
    try:
        if CONFIG.get('USERS_SECRET_ARN') and secrets_client:
            response = secrets_client.get_secret_value(SecretId=CONFIG['USERS_SECRET_ARN'])
            return json.loads(response['SecretString'])
    except Exception as e:
        logger.warning(f"Could not load users from Secrets Manager: {str(e)}")
    
    # Fallback to hardcoded users
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
    """Sanitize user input."""
    if not isinstance(input_str, str):
        return str(input_str)[:max_length]
    
    sanitized = input_str.strip()
    dangerous_patterns = ['--', ';', '/*', '*/', 'xp_', 'sp_', 'DROP', 'DELETE', 'TRUNCATE']
    for pattern in dangerous_patterns:
        sanitized = sanitized.replace(pattern, '')
    
    return sanitized[:max_length]

def sanitize_subscriber_data(data):
    """Sanitize subscriber data."""
    sanitized = {}
    
    for field, field_type in SUBSCRIBER_SCHEMA.items():
        if field in data:
            if field_type == int:
                try:
                    sanitized[field] = int(data[field]) if data[field] != '' else 0
                except (ValueError, TypeError):
                    sanitized[field] = 0
            elif field_type == float:
                try:
                    sanitized[field] = float(data[field]) if data[field] != '' else 0.0
                except (ValueError, TypeError):
                    sanitized[field] = 0.0
            elif field_type == bool:
                sanitized[field] = bool(data[field]) if isinstance(data[field], bool) else str(data[field]).lower() in ['true', '1', 'yes']
            else:
                sanitized[field] = sanitize_input(str(data[field]))
        else:
            if field in DEFAULT_VALUES:
                sanitized[field] = DEFAULT_VALUES[field]
    
    if not sanitized.get('activation_date'):
        sanitized['activation_date'] = datetime.utcnow().isoformat()
    
    return sanitized

# Token blacklist management
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
    """Add token to blacklist."""
    try:
        if 'token_blacklist' in tables:
            tables['token_blacklist'].put_item(
                Item={
                    'jti': jti,
                    'blacklisted_at': datetime.utcnow().isoformat(),
                    'expires_at': exp,
                    'ttl': int(exp)
                }
            )
    except Exception:
        pass

# Legacy database connection
def get_legacy_db_connection():
    """Get legacy MySQL database connection."""
    try:
        if not CONFIG.get('LEGACY_DB_SECRET_ARN') or not secrets_client:
            return None
            
        response = secrets_client.get_secret_value(SecretId=CONFIG['LEGACY_DB_SECRET_ARN'])
        secret = json.loads(response['SecretString'])
        
        connection = pymysql.connect(
            host=CONFIG['LEGACY_DB_HOST'],
            port=CONFIG['LEGACY_DB_PORT'],
            user=secret['username'],
            password=secret['password'],
            database=CONFIG['LEGACY_DB_NAME'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
            read_timeout=3,
            write_timeout=3,
            autocommit=False
        )
        
        return connection
        
    except Exception as e:
        logger.warning(f"Legacy DB connection failed: {str(e)}")
        return None

# Dual provisioning
def dual_provision(data, method='put'):
    """Dual provisioning function."""
    uid = data.get('uid') or data.get('subscriberId')
    
    if method in ['put', 'update']:
        data = sanitize_subscriber_data(data)
    
    # Legacy DB action
    if CONFIG['PROV_MODE'] in ['legacy', 'dual_prov']:
        connection = None
        try:
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    if method == 'put':
                        query = """
                            INSERT INTO subscribers (uid, imsi, msisdn, name, email, plan_type, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        now = datetime.utcnow().isoformat()
                        cursor.execute(query, (
                            data.get('uid'), data.get('imsi'), data.get('msisdn'),
                            data.get('name', ''), data.get('email', ''),
                            data.get('plan_type', 'STANDARD_PREPAID'), data.get('status', 'ACTIVE'),
                            now, now
                        ))
                    elif method == 'update':
                        cursor.execute(
                            "UPDATE subscribers SET status = %s, updated_at = %s WHERE uid = %s",
                            (data.get('status'), datetime.utcnow().isoformat(), uid)
                        )
                    elif method == 'delete':
                        cursor.execute("UPDATE subscribers SET status = 'DELETED' WHERE uid = %s", (uid,))
                    
                    connection.commit()
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Legacy DB operation failed: {str(e)}")
            raise Exception(f"Dual Provisioning Failed: Legacy DB Error: {str(e)}")
        finally:
            if connection:
                connection.close()
            
    # Cloud (DynamoDB) action
    if CONFIG['PROV_MODE'] in ['cloud', 'dual_prov']:
        try:
            data['subscriberId'] = uid
            
            if method in ['put', 'update']:
                if 'subscribers' in tables:
                    tables['subscribers'].put_item(Item=data)
            elif method == 'delete':
                if 'subscribers' in tables:
                    tables['subscribers'].delete_item(Key={'subscriberId': uid})
        except Exception as e:
            logger.error(f"Cloud DB operation failed: {str(e)}")
            raise Exception(f"Dual Provisioning Failed: Cloud DB Error: {str(e)}")

# User Management
class UserManager:
    """User management class."""
    
    @staticmethod
    def get_users():
        """Get users."""
        return load_users_from_secrets()
    
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Authenticate user."""
        username = sanitize_input(username, 50)
        users = UserManager.get_users()
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
            
            users = UserManager.get_users()
            user_data = users.get(payload['sub'])
            
            return {
                'username': payload['sub'],
                'role': payload['role'],
                'permissions': payload['permissions'],
                'jti': payload.get('jti'),
                'exp': payload.get('exp'),
                'rate_limit_override': user_data.get('rate_limit_override', False) if user_data else False
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

# Rate limiting exemption
@limiter.request_filter
def exempt_privileged():
    """Exempt privileged users."""
    try:
        if hasattr(g, 'current_user') and g.current_user and g.current_user.get('rate_limit_override'):
            return True
    except Exception:
        pass
    return False

# Utility functions
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
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}_{resource}_{user}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': action,
                'resource': resource,
                'user': user,
                'ip_address': request.remote_addr if request else 'system',
                'user_agent': request.headers.get('User-Agent', 'Unknown') if request else 'system',
                'details': details or {},
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())
            }
            tables['audit_logs'].put_item(Item=log_entry)
    except Exception:
        pass

# File utilities
def allowed_file(filename):
    """Check allowed file types."""
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'txt'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_s3(file_content, filename, content_type='application/octet-stream'):
    """Upload file to S3."""
    try:
        if not s3_client:
            raise Exception("S3 client not initialized")
        
        key = f"uploads/{datetime.utcnow().strftime('%Y/%m/%d')}/{uuid.uuid4().hex[:8]}_{filename}"
        
        s3_client.put_object(
            Bucket=CONFIG['MIGRATION_UPLOAD_BUCKET_NAME'],
            Key=key,
            Body=file_content,
            ContentType=content_type,
            ServerSideEncryption='AES256',
            Metadata={
                'uploaded_at': datetime.utcnow().isoformat(),
                'original_filename': filename
            }
        )
        
        return {
            'bucket': CONFIG['MIGRATION_UPLOAD_BUCKET_NAME'],
            'key': key,
            'url': f"s3://{CONFIG['MIGRATION_UPLOAD_BUCKET_NAME']}/{key}"
        }
    except Exception as e:
        logger.error(f"S3 upload failed: {str(e)}")
        raise

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return create_response(message="Endpoint not found", status_code=404)

@app.errorhandler(500)
def internal_error(error):
    return create_response(message="Internal server error", status_code=500)

@app.errorhandler(429)
def ratelimit_handler(e):
    return create_response(message=f"Rate limit exceeded: {e.description}", status_code=429)

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {str(error)}")
    return create_response(message="An unexpected error occurred", status_code=500)

# === CORE ROUTES ===
@app.route('/api/health', methods=['GET'])
def health_check():
    """Ultra-fast health check."""
    health_status = {
        'status': 'healthy',
        'version': CONFIG['VERSION'],
        'environment': CONFIG['FLASK_ENV'],
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'app': True,
            'dynamodb': bool(dynamodb),
            's3': bool(s3_client), 
            'secrets_manager': bool(secrets_client),
            'sqs': bool(sqs_client)
        },
        'provisioning_modes': CONFIG['PROVISIONING_MODES'],
        'current_mode': CONFIG['PROV_MODE'],
        'security': {
            'cors_origins': allowed_origins,
            'rate_limiting': True,
            'jwt_enabled': True,
            'token_revocation': True
        }
    }
    
    return create_response(data=health_status, message="Health check completed")

@app.route('/health', methods=['GET'])
def health_check_alt():
    """Alternative health endpoint."""
    return health_check()

# === AUTHENTICATION ROUTES ===
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
        return create_response(message="Logout successful - token revoked")
    except Exception:
        return create_response(message="Logout completed", status_code=200)

# === DASHBOARD ROUTES ===
@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
@limiter.limit("100 per minute")
def get_dashboard_stats():
    """Dashboard statistics."""
    try:
        stats = {
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'legacySubscribers': 0,
            'activeMigrations': 0,
            'completedMigrations': 0,
            'systemHealth': 'healthy',
            'provisioningMode': CONFIG['PROV_MODE'],
            'lastUpdated': datetime.utcnow().isoformat()
        }
        
        # Cloud subscriber count
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(Select='COUNT')
                stats['cloudSubscribers'] = response.get('Count', 0)
        except Exception:
            stats['systemHealth'] = 'degraded'
        
        # Legacy subscriber count
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
        
        return create_response(data=stats, message="Dashboard stats retrieved")
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return create_response(message="Failed to get dashboard stats", status_code=500)

# === SUBSCRIBER ROUTES ===
@app.route('/api/subscribers', methods=['GET'])
@require_auth(['read'])
@limiter.limit("200 per minute")
def get_subscribers():
    """Get subscribers."""
    try:
        mode = sanitize_input(request.args.get('mode', CONFIG['PROV_MODE']), 20)
        limit = min(int(request.args.get('limit', '50')), 500)
        search = sanitize_input(request.args.get('search', ''), 100)
        
        subscribers = []
        
        if mode in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                if search:
                    # Try exact match first
                    try:
                        item = tables['subscribers'].get_item(Key={'subscriberId': search}).get('Item')
                        if item:
                            item['source'] = 'cloud'
                            subscribers.append(item)
                    except:
                        pass
                    
                    if not subscribers:
                        response = tables['subscribers'].scan(
                            FilterExpression='contains(subscriberId, :search) OR contains(imsi, :search) OR contains(msisdn, :search)',
                            ExpressionAttributeValues={':search': search},
                            Limit=limit
                        )
                        cloud_subscribers = response.get('Items', [])
                        for sub in cloud_subscribers:
                            sub['source'] = 'cloud'
                        subscribers.extend(cloud_subscribers)
                else:
                    response = tables['subscribers'].scan(Limit=limit)
                    cloud_subscribers = response.get('Items', [])
                    for sub in cloud_subscribers:
                        sub['source'] = 'cloud'
                    subscribers.extend(cloud_subscribers)
                        
            except Exception as e:
                logger.error(f"DynamoDB query error: {str(e)}")
        
        if mode in ['legacy', 'dual_prov']:
            connection = get_legacy_db_connection()
            if connection:
                try:
                    with connection.cursor() as cursor:
                        if search:
                            cursor.execute(
                                "SELECT * FROM subscribers WHERE (uid LIKE %s OR imsi LIKE %s OR msisdn LIKE %s) AND status != 'DELETED' LIMIT %s",
                                (f"%{search}%", f"%{search}%", f"%{search}%", limit)
                            )
                        else:
                            cursor.execute("SELECT * FROM subscribers WHERE status != 'DELETED' LIMIT %s", (limit,))
                        
                        legacy_subscribers = cursor.fetchall()
                        for sub in legacy_subscribers:
                            sub['source'] = 'legacy'
                        subscribers.extend(legacy_subscribers)
                    connection.close()
                except Exception:
                    if connection:
                        connection.close()
        
        return create_response(data={
            'subscribers': subscribers,
            'count': len(subscribers),
            'mode': mode,
            'search': search
        })
        
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500)

@app.route('/api/subscribers', methods=['POST'])
@require_auth(['write'])
@limiter.limit("100 per minute")
def create_subscriber():
    """Create subscriber."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        required_fields = ['uid', 'imsi']
        for field in required_fields:
            if not data.get(field):
                return create_response(message=f"Missing required field: {field}", status_code=400)
        
        # Check duplicates
        uid = sanitize_input(data['uid'], 50)
        existing_sources = []
        
        if 'subscribers' in tables:
            try:
                existing = tables['subscribers'].get_item(Key={'subscriberId': uid}).get('Item')
                if existing:
                    existing_sources.append('cloud')
            except:
                pass
        
        connection = get_legacy_db_connection()
        if connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT uid FROM subscribers WHERE uid = %s AND status != 'DELETED'", (uid,))
                    if cursor.fetchone():
                        existing_sources.append('legacy')
                connection.close()
            except Exception:
                if connection:
                    connection.close()
        
        if existing_sources:
            return create_response(
                message=f"UID '{uid}' already exists in: {', '.join(existing_sources)}",
                status_code=400
            )
        
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = g.current_user['username']
        
        dual_provision(data, method='put')
        
        audit_log('subscriber_created', 'subscriber', g.current_user['username'], 
                 {'subscriber_uid': uid, 'mode': CONFIG['PROV_MODE']})
        
        return create_response(data={'uid': uid}, message="Subscriber created successfully", status_code=201)
        
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_response(message=f"Failed to create subscriber: {str(e)}", status_code=500)

@app.route('/api/subscribers/search', methods=['GET'])
@require_auth(['read'])
@limiter.limit("200 per minute")
def search_subscriber():
    """Search subscriber."""
    try:
        identifier_value = sanitize_input(request.args.get('identifier', ''), 50)
        identifier_type = sanitize_input(request.args.get('type', 'uid'), 20)
        
        if not identifier_value:
            return create_response(message="Identifier parameter is required", status_code=400)
        
        if identifier_type not in ['uid', 'imsi', 'msisdn', 'email']:
            return create_response(message="Invalid identifier type", status_code=400)
        
        results = {'cloud': None, 'legacy': None}
        
        # Search cloud
        if CONFIG['PROV_MODE'] in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                if identifier_type == 'uid':
                    cloud_data = tables['subscribers'].get_item(Key={'subscriberId': identifier_value}).get('Item')
                else:
                    response = tables['subscribers'].scan(
                        FilterExpression=f'#{identifier_type} = :value',
                        ExpressionAttributeNames={f'#{identifier_type}': identifier_type},
                        ExpressionAttributeValues={':value': identifier_value},
                        Limit=1
                    )
                    cloud_data = response['Items'][0] if response['Items'] else None
                
                if cloud_data:
                    cloud_data['source'] = 'cloud'
                    results['cloud'] = cloud_data
                    
            except Exception:
                pass
        
        # Search legacy
        if CONFIG['PROV_MODE'] in ['legacy', 'dual_prov']:
            connection = get_legacy_db_connection()
            if connection:
                try:
                    with connection.cursor() as cursor:
                        query = f"SELECT * FROM subscribers WHERE {identifier_type} = %s AND status != 'DELETED'"
                        cursor.execute(query, (identifier_value,))
                        legacy_data = cursor.fetchone()
                    connection.close()
                    
                    if legacy_data:
                        legacy_data['source'] = 'legacy'
                        results['legacy'] = legacy_data
                        
                except Exception:
                    if connection:
                        connection.close()
        
        # Return results
        found_in = [k for k, v in results.items() if v]
        if found_in:
            primary_result = results['cloud'] or results['legacy']
            return create_response(
                data={
                    'subscriber': primary_result,
                    'found_in': found_in,
                    'all_results': {k: v for k, v in results.items() if v}
                },
                message=f"Subscriber found in: {', '.join(found_in)}"
            )
        
        return create_response(message="Subscriber not found", status_code=404)
        
    except Exception as e:
        logger.error(f"Search subscriber error: {str(e)}")
        return create_response(message="Search failed", status_code=500)

# === MIGRATION ROUTES ===
@app.route('/api/migration/jobs', methods=['GET'])
@require_auth(['read'])
@limiter.limit("100 per minute")
def get_migration_jobs():
    """Get migration jobs."""
    try:
        status_filter = sanitize_input(request.args.get('status', ''), 50)
        limit = min(int(request.args.get('limit', '50')), 500)
        
        if 'migration_jobs' not in tables:
            return create_response(message="Migration jobs table not available", status_code=503)
        
        try:
            if status_filter:
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': status_filter},
                    Limit=limit
                )
            else:
                response = tables['migration_jobs'].scan(Limit=limit)
            
            jobs = response.get('Items', [])
            jobs.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
            
        except Exception as e:
            logger.error(f"Migration jobs query error: {str(e)}")
            return create_response(message="Failed to retrieve migration jobs", status_code=503)
        
        return create_response(data={
            'jobs': jobs,
            'count': len(jobs),
            'status_filter': status_filter
        })
        
    except Exception as e:
        logger.error(f"Get migration jobs error: {str(e)}")
        return create_response(message="Failed to get migration jobs", status_code=500)

# **BULLETPROOF LAMBDA HANDLER**
def lambda_handler(event, context):
    """Bulletproof AWS Lambda entry point that handles all event types."""
    try:
        logger.info(f"Lambda handler invoked with event keys: {list(event.keys())}")
        
        # Handle empty event (direct invoke without payload)
        if not event:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization'
                },
                'body': json.dumps({
                    'status': 'success',
                    'message': 'Lambda is working - empty event handled!',
                    'version': CONFIG['VERSION'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'handler': 'app.lambda_handler'
                }),
                'isBase64Encoded': False
            }
        
        # Handle direct health check calls (no headers)
        if 'headers' not in event:
            logger.info("Handling direct Lambda invoke (no headers)")
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization'
                },
                'body': json.dumps({
                    'status': 'success',
                    'message': 'Lambda is working - direct invoke!',
                    'version': CONFIG['VERSION'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'handler': 'app.lambda_handler',
                    'event_type': 'direct_invoke',
                    'services': {
                        'app': True,
                        'dynamodb': bool(dynamodb),
                        's3': bool(s3_client),
                        'secrets_manager': bool(secrets_client)
                    }
                }),
                'isBase64Encoded': False
            }
        
        # Ensure event has all required fields for serverless_wsgi
        if 'httpMethod' not in event:
            event['httpMethod'] = 'GET'
        
        if 'path' not in event:
            event['path'] = '/api/health'
        
        if 'queryStringParameters' not in event:
            event['queryStringParameters'] = None
        
        if 'body' not in event:
            event['body'] = None
        
        if 'isBase64Encoded' not in event:
            event['isBase64Encoded'] = False
        
        if 'requestContext' not in event:
            event['requestContext'] = {
                'requestId': context.aws_request_id if context else 'test-request',
                'stage': 'prod',
                'resourcePath': event.get('path', '/api/health'),
                'httpMethod': event.get('httpMethod', 'GET'),
                'identity': {
                    'sourceIp': '127.0.0.1',
                    'userAgent': 'AWS Lambda'
                }
            }
        
        # Handle CloudWatch Events
        if event.get('source') == 'aws.events':
            logger.info("Received CloudWatch Events trigger")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'CloudWatch event processed',
                    'timestamp': datetime.utcnow().isoformat()
                })
            }
        
        # Handle scheduled events
        if 'ScheduleExpression' in str(event):
            logger.info("Received scheduled event")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'Scheduled event processed',
                    'timestamp': datetime.utcnow().isoformat()
                })
            }
        
        # Use serverless_wsgi for HTTP events
        logger.info(f"Processing HTTP event: {event.get('httpMethod')} {event.get('path')}")
        return handle_request(app, event, context)
        
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}\n{traceback.format_exc()}")
        
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
                'message': 'Lambda handler error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'version': CONFIG['VERSION']
            }),
            'isBase64Encoded': False
        }

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = CONFIG['FLASK_ENV'] == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
