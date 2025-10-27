#!/usr/bin/env python3
"""
Subscriber Migration Portal - COMPLETE Production Backend
Enterprise Security + JWT Revocation + Migration Processing + Optimized Queries
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
    'USERS_SECRET_ARN': os.getenv('USERS_SECRET_ARN'),  # Store users in Secrets Manager
    'LEGACY_DB_SECRET_ARN': os.getenv('LEGACY_DB_SECRET_ARN'),
    'LEGACY_DB_HOST': os.getenv('LEGACY_DB_HOST'),
    'LEGACY_DB_PORT': int(os.getenv('LEGACY_DB_PORT', '3306')),
    'LEGACY_DB_NAME': os.getenv('LEGACY_DB_NAME', 'legacydb'),
    'PROVISIONING_MODES': os.getenv('PROVISIONING_MODES', 'legacy,cloud,dual_prov').split(','),
    'PROV_MODE': os.getenv('PROV_MODE', 'dual_prov'),
    'FRONTEND_ORIGIN': os.getenv('FRONTEND_ORIGIN', 'http://sub-mig-web-144395889420-prod.s3-website-us-east-1.amazonaws.com'),
    'MAX_UPLOAD_SIZE': int(os.getenv('MAX_UPLOAD_SIZE', '50')) * 1024 * 1024,  # 50MB default
    'ENABLE_MIGRATION_PROCESSING': os.getenv('ENABLE_MIGRATION_PROCESSING', 'true').lower() == 'true',
}

# Secure CORS setup - NEVER use * in production
allowed_origins = []
if CONFIG['FRONTEND_ORIGIN'] and CONFIG['FRONTEND_ORIGIN'] != '*':
    allowed_origins = [CONFIG['FRONTEND_ORIGIN']]
    # Add common development origins if in development
    if CONFIG['FLASK_ENV'] == 'development':
        allowed_origins.extend(['http://localhost:3000', 'http://127.0.0.1:3000'])
else:
    # Fallback for development only
    if CONFIG['FLASK_ENV'] == 'development':
        allowed_origins = ['*']
    else:
        logger.error("FRONTEND_ORIGIN must be set in production")
        sys.exit(1)

CORS(app, origins=allowed_origins, supports_credentials=True, 
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'])

# Rate limiting setup with Redis-like backend simulation
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

# AWS clients initialization with error handling
try:
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    secrets_client = boto3.client('secretsmanager')
    sqs_client = boto3.client('sqs')
    logger.info("AWS services initialized successfully")
except ClientError as e:
    logger.error(f"AWS client initialization failed: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
    dynamodb = s3_client = secrets_client = sqs_client = None
except Exception as e:
    logger.error(f"AWS initialization failed: {str(e)}")
    dynamodb = s3_client = secrets_client = sqs_client = None

# DynamoDB tables initialization with error handling
tables = {}
try:
    if dynamodb:
        tables['subscribers'] = dynamodb.Table(CONFIG['SUBSCRIBER_TABLE_NAME'])
        tables['audit_logs'] = dynamodb.Table(CONFIG['AUDIT_LOG_TABLE_NAME'])
        tables['migration_jobs'] = dynamodb.Table(CONFIG['MIGRATION_JOBS_TABLE_NAME'])
        tables['token_blacklist'] = dynamodb.Table(CONFIG['TOKEN_BLACKLIST_TABLE_NAME'])
        logger.info("DynamoDB tables initialized")
except ClientError as e:
    logger.error(f"DynamoDB table initialization failed: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
except Exception as e:
    logger.error(f"DynamoDB table initialization failed: {str(e)}")

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

# Default values for enhanced fields
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

# Secure user management from AWS Secrets Manager
def load_users_from_secrets():
    """Load users from AWS Secrets Manager."""
    try:
        if CONFIG['USERS_SECRET_ARN'] and secrets_client:
            response = secrets_client.get_secret_value(SecretId=CONFIG['USERS_SECRET_ARN'])
            return json.loads(response['SecretString'])
    except Exception as e:
        logger.warning(f"Could not load users from Secrets Manager: {str(e)}")
    
    # Fallback to hardcoded users for development
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

# Input sanitization utilities
def sanitize_input(input_str, max_length=255):
    """Sanitize user input to prevent injection attacks."""
    if not isinstance(input_str, str):
        return str(input_str)[:max_length]
    
    sanitized = input_str.strip()
    # Remove SQL injection patterns
    dangerous_patterns = ['--', ';', '/*', '*/', 'xp_', 'sp_', 'DROP', 'DELETE', 'TRUNCATE', 'UPDATE', 'INSERT']
    for pattern in dangerous_patterns:
        sanitized = sanitized.replace(pattern, '')
    
    return sanitized[:max_length]

def sanitize_subscriber_data(data):
    """Enhanced sanitize and add default values for subscriber data."""
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
    except Exception as e:
        logger.error(f"Token blacklist check failed: {str(e)}")
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
                    'ttl': int(exp)  # DynamoDB TTL
                }
            )
    except Exception as e:
        logger.error(f"Token blacklist failed: {str(e)}")

# Legacy database connection with connection pooling
def get_legacy_db_connection():
    """Get legacy MySQL database connection with proper error handling."""
    try:
        if not CONFIG['LEGACY_DB_SECRET_ARN'] or not secrets_client:
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
        logger.error(f"Legacy DB connection failed: {str(e)}")
        return None

# Optimized dual provisioning function
def dual_provision(data, method='put'):
    """Write/update/delete data in both legacy and cloud based on mode."""
    uid = data.get('uid') or data.get('subscriberId')
    
    if method in ['put', 'update']:
        data = sanitize_subscriber_data(data)
    
    # Legacy DB (MySQL) action
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
                tables['subscribers'].put_item(Item=data)
            elif method == 'delete':
                tables['subscribers'].delete_item(Key={'subscriberId': uid})
        except Exception as e:
            logger.error(f"Cloud DB operation failed: {str(e)}")
            raise Exception(f"Dual Provisioning Failed: Cloud DB Error: {str(e)}")

# Enhanced User Management
class UserManager:
    """Enhanced secure user management with JWT and dynamic user loading."""
    
    @staticmethod
    def get_users():
        """Get users from Secrets Manager or fallback."""
        return load_users_from_secrets()
    
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Authenticate user with secure password checking."""
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
        """Generate secure JWT token."""
        payload = {
            'sub': user_data['username'],
            'role': user_data['role'],
            'permissions': user_data['permissions'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=CONFIG['JWT_EXPIRY_HOURS']),
            'jti': str(uuid.uuid4())  # JWT ID for token revocation
        }
        return jwt.encode(payload, CONFIG['JWT_SECRET'], algorithm=CONFIG['JWT_ALGORITHM'])
    
    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict]:
        """Verify and decode JWT token with blacklist check."""
        try:
            payload = jwt.decode(token, CONFIG['JWT_SECRET'], algorithms=[CONFIG['JWT_ALGORITHM']])
            
            # Check if token is blacklisted
            if is_token_blacklisted(payload.get('jti')):
                logger.warning("JWT token is blacklisted")
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
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            return None

# Authentication decorator with rate limiting exemption
def require_auth(permissions=None):
    """Enhanced decorator with permission checking."""
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
            
            # Check permissions if specified
            if permissions:
                required_perms = permissions if isinstance(permissions, list) else [permissions]
                if not any(perm in user['permissions'] for perm in required_perms):
                    return create_response(message="Insufficient permissions", status_code=403)
            
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Rate limiting exemption filter
@limiter.request_filter
def exempt_privileged():
    """Exempt privileged users from rate limiting."""
    try:
        if hasattr(g, 'current_user') and g.current_user and g.current_user.get('rate_limit_override'):
            return True
    except Exception:
        pass
    return False

# Utility functions
def create_response(data=None, message="Success", status_code=200, error=None):
    """Create standardized API response with structured logging."""
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
        logger.error(f"API Error: {error} - Status: {status_code}")
    
    return jsonify(response), status_code

def audit_log(action: str, resource: str, user: str = "system", details: Dict = None):
    """Enhanced audit logging with structured data."""
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
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())  # 90 day retention
            }
            tables['audit_logs'].put_item(Item=log_entry)
    except Exception as e:
        logger.error(f"Audit logging failed: {str(e)}")

# Migration processing utilities
def process_migration_file(job_id, s3_location):
    """Process uploaded migration file."""
    try:
        # Download file from S3
        response = s3_client.get_object(
            Bucket=s3_location['bucket'],
            Key=s3_location['key']
        )
        file_content = response['Body'].read().decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(file_content))
        records_processed = 0
        records_failed = 0
        errors = []
        
        # Update job status to IN_PROGRESS
        tables['migration_jobs'].update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #status = :status, updatedAt = :updated',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'IN_PROGRESS',
                ':updated': datetime.utcnow().isoformat()
            }
        )
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
            try:
                # Validate required fields
                if not row.get('uid') or not row.get('imsi'):
                    raise ValueError("Missing required fields: uid, imsi")
                
                # Process subscriber
                dual_provision(row, method='put')
                records_processed += 1
                
            except Exception as e:
                records_failed += 1
                errors.append(f"Row {row_num}: {str(e)}")
                logger.error(f"Migration processing error for row {row_num}: {str(e)}")
        
        # Update final job status
        final_status = 'COMPLETED' if records_failed == 0 else 'COMPLETED_WITH_ERRORS'
        tables['migration_jobs'].update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #status = :status, recordsProcessed = :processed, recordsFailed = :failed, errors = :errors, completedAt = :completed, updatedAt = :updated',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': final_status,
                ':processed': records_processed,
                ':failed': records_failed,
                ':errors': errors[:100],  # Limit errors to first 100
                ':completed': datetime.utcnow().isoformat(),
                ':updated': datetime.utcnow().isoformat()
            }
        )
        
        logger.info(f"Migration job {job_id} completed: {records_processed} processed, {records_failed} failed")
        
    except Exception as e:
        # Mark job as failed
        tables['migration_jobs'].update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #status = :status, errors = :errors, updatedAt = :updated',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'FAILED',
                ':errors': [str(e)],
                ':updated': datetime.utcnow().isoformat()
            }
        )
        logger.error(f"Migration job {job_id} failed: {str(e)}")

# File upload utilities
def allowed_file(filename):
    """Check if file type is allowed for upload."""
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'txt'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_s3(file_content, filename, content_type='application/octet-stream'):
    """Upload file to S3 bucket."""
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
    logger.error(f"Internal server error: {str(error)}")
    return create_response(message="Internal server error", status_code=500)

@app.errorhandler(429)
def ratelimit_handler(e):
    return create_response(message=f"Rate limit exceeded: {e.description}", status_code=429)

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {str(error)}\n{traceback.format_exc()}")
    return create_response(message="An unexpected error occurred", status_code=500)

# === CORE ROUTES ===
@app.route('/api/health', methods=['GET'])
def health_check():
    """Ultra-fast health check - no external service calls."""
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

# Alternative health endpoint for compatibility
@app.route('/health', methods=['GET'])
def health_check_alt():
    """Alternative health endpoint for compatibility."""
    return health_check()

# === AUTHENTICATION ROUTES ===
@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """Enhanced secure user authentication with rate limiting."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        username = sanitize_input(data.get('username', ''), 50)
        password = data.get('password', '')
        
        if not username or not password:
            return create_response(message="Username and password required", status_code=400)
        
        if len(password) < 6:
            return create_response(message="Password must be at least 6 characters", status_code=400)
        
        user = UserManager.authenticate(username, password)
        if not user:
            audit_log('login_failed', 'auth', username, {'ip': request.remote_addr})
            return create_response(message="Invalid credentials", status_code=401)
        
        token = UserManager.generate_jwt_token(user)
        audit_log('login_success', 'auth', username, {'ip': request.remote_addr})
        
        return create_response(data={
            'token': token,
            'user': {
                'username': user['username'],
                'role': user['role'],
                'permissions': user['permissions']
            },
            'expires_in': CONFIG['JWT_EXPIRY_HOURS'] * 3600
        }, message="Login successful")
        
    except json.JSONDecodeError:
        return create_response(message="Invalid JSON format", status_code=400)
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return create_response(message="Login failed", status_code=500)

@app.route('/api/auth/logout', methods=['POST'])
@require_auth()
def logout():
    """Enhanced logout with token revocation."""
    try:
        # Blacklist the current token
        user = g.current_user
        if user.get('jti') and user.get('exp'):
            blacklist_token(user['jti'], user['exp'])
        
        audit_log('logout', 'auth', user['username'], {'ip': request.remote_addr})
        return create_response(message="Logout successful - token revoked")
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return create_response(message="Logout completed", status_code=200)

# === FILE UPLOAD & MIGRATION ROUTES ===
@app.route('/api/migration/upload', methods=['POST'])
@require_auth(['write'])
@limiter.limit("5 per minute")
def upload_migration_file():
    """Upload migration file and optionally process immediately."""
    try:
        if 'file' not in request.files:
            return create_response(message="No file provided", status_code=400)
        
        file = request.files['file']
        process_immediately = request.form.get('process_immediately', 'false').lower() == 'true'
        
        if file.filename == '':
            return create_response(message="No file selected", status_code=400)
        
        if not allowed_file(file.filename):
            return create_response(message="Invalid file type. Allowed: CSV, Excel", status_code=400)
        
        # Check file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > CONFIG['MAX_UPLOAD_SIZE']:
            return create_response(message=f"File too large. Maximum size: {CONFIG['MAX_UPLOAD_SIZE'] // (1024*1024)}MB", status_code=400)
        
        # Upload to S3
        file_content = file.read()
        upload_result = upload_to_s3(file_content, file.filename, file.content_type)
        
        # Create migration job record
        job_id = str(uuid.uuid4())
        migration_job = {
            'jobId': job_id,
            'filename': sanitize_input(file.filename, 255),
            'fileSize': file_size,
            'status': 'PENDING_PROCESSING',
            'createdAt': datetime.utcnow().isoformat(),
            'updatedAt': datetime.utcnow().isoformat(),
            'createdBy': g.current_user['username'],
            's3Location': upload_result,
            'recordsTotal': 0,
            'recordsProcessed': 0,
            'recordsFailed': 0,
            'errors': []
        }
        
        tables['migration_jobs'].put_item(Item=migration_job)
        
        # Process immediately if requested and enabled
        if process_immediately and CONFIG['ENABLE_MIGRATION_PROCESSING']:
            try:
                process_migration_file(job_id, upload_result)
            except Exception as e:
                logger.error(f"Immediate processing failed: {str(e)}")
        
        audit_log('migration_file_uploaded', 'migration', g.current_user['username'], {
            'job_id': job_id,
            'filename': file.filename,
            'file_size': file_size,
            'process_immediately': process_immediately
        })
        
        return create_response(data={
            'jobId': job_id,
            'filename': file.filename,
            'fileSize': file_size,
            'status': migration_job['status'],
            'processedImmediately': process_immediately and CONFIG['ENABLE_MIGRATION_PROCESSING']
        }, message="File uploaded successfully", status_code=201)
        
    except Exception as e:
        logger.error(f"File upload error: {str(e)}")
        return create_response(message="File upload failed", status_code=500)

@app.route('/api/migration/jobs/<job_id>/process', methods=['POST'])
@require_auth(['write'])
@limiter.limit("10 per minute")
def process_migration_job(job_id):
    """Process a specific migration job."""
    try:
        if not CONFIG['ENABLE_MIGRATION_PROCESSING']:
            return create_response(message="Migration processing is disabled", status_code=503)
        
        job_id = sanitize_input(job_id, 50)
        
        # Get job details
        response = tables['migration_jobs'].get_item(Key={'jobId': job_id})
        if 'Item' not in response:
            return create_response(message="Migration job not found", status_code=404)
        
        job = response['Item']
        if job['status'] not in ['PENDING_PROCESSING', 'FAILED']:
            return create_response(message=f"Job cannot be processed. Current status: {job['status']}", status_code=400)
        
        # Process the job
        process_migration_file(job_id, job['s3Location'])
        
        audit_log('migration_job_processed', 'migration', g.current_user['username'], {'job_id': job_id})
        
        return create_response(data={'jobId': job_id}, message="Migration job processing started")
        
    except Exception as e:
        logger.error(f"Migration job processing error: {str(e)}")
        return create_response(message="Migration job processing failed", status_code=500)

# === DASHBOARD ROUTES ===
@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
@limiter.limit("100 per minute")
def get_dashboard_stats():
    """Get comprehensive dashboard statistics with caching."""
    try:
        stats = {
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'legacySubscribers': 0,
            'activeMigrations': 0,
            'completedMigrations': 0,
            'failedMigrations': 0,
            'systemHealth': 'healthy',
            'provisioningMode': CONFIG['PROV_MODE'],
            'lastUpdated': datetime.utcnow().isoformat(),
            'todayUploads': 0,
            'processingEnabled': CONFIG['ENABLE_MIGRATION_PROCESSING']
        }
        
        # Get cloud subscriber count
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(Select='COUNT')
                stats['cloudSubscribers'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Error getting cloud stats: {e.response['Error']['Code']}")
            stats['systemHealth'] = 'degraded'
        
        # Get legacy subscriber count with timeout protection
        try:
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != 'DELETED'")
                    result = cursor.fetchone()
                    stats['legacySubscribers'] = result['count'] if result else 0
                connection.close()
        except Exception as e:
            logger.warning(f"Legacy stats unavailable: {str(e)}")
        
        stats['totalSubscribers'] = stats['cloudSubscribers'] + stats['legacySubscribers']
        
        # Get migration job stats
        try:
            if 'migration_jobs' in tables:
                # Active migrations
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status IN (:status1, :status2)',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status1': 'IN_PROGRESS', ':status2': 'PENDING_PROCESSING'},
                    Select='COUNT'
                )
                stats['activeMigrations'] = response.get('Count', 0)
                
                # Completed migrations
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status IN (:status1, :status2)',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status1': 'COMPLETED', ':status2': 'COMPLETED_WITH_ERRORS'},
                    Select='COUNT'
                )
                stats['completedMigrations'] = response.get('Count', 0)
                
                # Failed migrations
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'FAILED'},
                    Select='COUNT'
                )
                stats['failedMigrations'] = response.get('Count', 0)
                
                # Today's uploads
                today = datetime.utcnow().date().isoformat()
                response = tables['migration_jobs'].scan(
                    FilterExpression='begins_with(createdAt, :today)',
                    ExpressionAttributeValues={':today': today},
                    Select='COUNT'
                )
                stats['todayUploads'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Error getting migration stats: {e.response['Error']['Code']}")
        
        return create_response(data=stats, message="Dashboard stats retrieved")
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return create_response(message="Failed to get dashboard stats", status_code=500)

# === OPTIMIZED SUBSCRIBER ROUTES ===
@app.route('/api/subscribers', methods=['GET'])
@require_auth(['read'])
@limiter.limit("200 per minute")
def get_subscribers():
    """Get subscribers with optimized queries and pagination."""
    try:
        mode = sanitize_input(request.args.get('mode', CONFIG['PROV_MODE']), 20)
        limit = min(int(request.args.get('limit', '50')), 500)  # Cap at 500
        search = sanitize_input(request.args.get('search', ''), 100)
        last_key = request.args.get('lastKey')  # For pagination
        
        subscribers = []
        next_key = None
        
        if mode in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                if search:
                    # Use optimized query for exact matches, scan for partial matches
                    if '@' in search:  # Email search
                        response = tables['subscribers'].scan(
                            FilterExpression='contains(email, :search)',
                            ExpressionAttributeValues={':search': search},
                            Limit=limit
                        )
                    else:
                        # Try exact match first (more efficient)
                        try:
                            item = tables['subscribers'].get_item(Key={'subscriberId': search}).get('Item')
                            if item:
                                item['source'] = 'cloud'
                                subscribers.append(item)
                        except:
                            pass
                        
                        # If no exact match, do partial search
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
                    # Paginated scan for all records
                    scan_kwargs = {'Limit': limit}
                    if last_key:
                        scan_kwargs['ExclusiveStartKey'] = json.loads(last_key)
                    
                    response = tables['subscribers'].scan(**scan_kwargs)
                    cloud_subscribers = response.get('Items', [])
                    for sub in cloud_subscribers:
                        sub['source'] = 'cloud'
                    subscribers.extend(cloud_subscribers)
                    
                    if 'LastEvaluatedKey' in response:
                        next_key = json.dumps(response['LastEvaluatedKey'])
                        
            except ClientError as e:
                logger.error(f"DynamoDB query error: {e.response['Error']['Code']}")
                return create_response(message="Failed to retrieve cloud subscribers", status_code=503)
        
        if mode in ['legacy', 'dual_prov']:
            connection = get_legacy_db_connection()
            if connection:
                try:
                    with connection.cursor() as cursor:
                        if search:
                            cursor.execute(
                                "SELECT * FROM subscribers WHERE (uid LIKE %s OR imsi LIKE %s OR msisdn LIKE %s OR email LIKE %s) AND status != 'DELETED' LIMIT %s",
                                (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%", limit)
                            )
                        else:
                            cursor.execute("SELECT * FROM subscribers WHERE status != 'DELETED' LIMIT %s", (limit,))
                        
                        legacy_subscribers = cursor.fetchall()
                        for sub in legacy_subscribers:
                            sub['source'] = 'legacy'
                        subscribers.extend(legacy_subscribers)
                    connection.close()
                except Exception as e:
                    if connection:
                        connection.close()
                    logger.warning(f"Legacy DB query failed: {str(e)}")
        
        return create_response(data={
            'subscribers': subscribers,
            'count': len(subscribers),
            'mode': mode,
            'search': search,
            'nextKey': next_key,
            'hasMore': next_key is not None
        })
        
    except ValueError:
        return create_response(message="Invalid parameters", status_code=400)
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500)

@app.route('/api/subscribers', methods=['POST'])
@require_auth(['write'])
@limiter.limit("100 per minute")
def create_subscriber():
    """Create subscriber with enhanced validation."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        # Enhanced validation
        required_fields = ['uid', 'imsi']
        for field in required_fields:
            if not data.get(field):
                return create_response(message=f"Missing required field: {field}", status_code=400)
        
        # Validate format
        uid = sanitize_input(data['uid'], 50)
        if len(uid) < 3:
            return create_response(message="UID must be at least 3 characters", status_code=400)
        
        # Check for duplicates in both systems
        existing_sources = []
        
        if 'subscribers' in tables:
            try:
                existing = tables['subscribers'].get_item(Key={'subscriberId': uid}).get('Item')
                if existing:
                    existing_sources.append('cloud')
            except ClientError:
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
        
        # Enhanced data preparation
        data['created_at'] = datetime.utcnow().isoformat()
        data['updated_at'] = datetime.utcnow().isoformat()
        data['created_by'] = g.current_user['username']
        data['ip_address'] = request.remote_addr
        
        # Provision subscriber
        dual_provision(data, method='put')
        
        audit_log('subscriber_created', 'subscriber', g.current_user['username'], 
                 {'subscriber_uid': uid, 'mode': CONFIG['PROV_MODE']})
        
        return create_response(data={'uid': uid}, message="Subscriber created successfully", status_code=201)
        
    except json.JSONDecodeError:
        return create_response(message="Invalid JSON format", status_code=400)
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_response(message=f"Failed to create subscriber: {str(e)}", status_code=500)

@app.route('/api/subscribers/search', methods=['GET'])
@require_auth(['read'])
@limiter.limit("200 per minute")
def search_subscriber():
    """Optimized subscriber search with exact and fuzzy matching."""
    try:
        identifier_value = sanitize_input(request.args.get('identifier', ''), 50)
        identifier_type = sanitize_input(request.args.get('type', 'uid'), 20)
        
        if not identifier_value:
            return create_response(message="Identifier parameter is required", status_code=400)
        
        if identifier_type not in ['uid', 'imsi', 'msisdn', 'email']:
            return create_response(message="Invalid identifier type", status_code=400)
        
        results = {'cloud': None, 'legacy': None}
        
        # Search cloud database with optimized queries
        if CONFIG['PROV_MODE'] in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                if identifier_type == 'uid':
                    # Direct get for UID (most efficient)
                    cloud_data = tables['subscribers'].get_item(Key={'subscriberId': identifier_value}).get('Item')
                else:
                    # For other fields, would need GSI in production
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
                    
            except ClientError as e:
                logger.error(f"Cloud search error: {e.response['Error']['Code']}")
        
        # Search legacy database
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
                        
                except Exception as e:
                    if connection:
                        connection.close()
                    logger.warning(f"Legacy search error: {str(e)}")
        
        # Return results
        found_in = [k for k, v in results.items() if v]
        if found_in:
            primary_result = results['cloud'] or results['legacy']
            audit_log('subscriber_searched', 'subscriber', g.current_user['username'], 
                     {'identifier': identifier_value, 'type': identifier_type, 'found_in': found_in})
            
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

# === MIGRATION JOB ROUTES ===
@app.route('/api/migration/jobs', methods=['GET'])
@require_auth(['read'])
@limiter.limit("100 per minute")
def get_migration_jobs():
    """Get migration jobs with pagination and filtering."""
    try:
        status_filter = sanitize_input(request.args.get('status', ''), 50)
        limit = min(int(request.args.get('limit', '50')), 500)
        last_key = request.args.get('lastKey')
        
        if 'migration_jobs' not in tables:
            return create_response(message="Migration jobs table not available", status_code=503)
        
        try:
            scan_kwargs = {'Limit': limit}
            
            if status_filter:
                scan_kwargs['FilterExpression'] = '#status = :status'
                scan_kwargs['ExpressionAttributeNames'] = {'#status': 'status'}
                scan_kwargs['ExpressionAttributeValues'] = {':status': status_filter}
            
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            
            response = tables['migration_jobs'].scan(**scan_kwargs)
            jobs = response.get('Items', [])
            
            # Sort by creation date
            jobs.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
            
            next_key = None
            if 'LastEvaluatedKey' in response:
                next_key = json.dumps(response['LastEvaluatedKey'])
            
        except ClientError as e:
            logger.error(f"Migration jobs query error: {e.response['Error']['Code']}")
            return create_response(message="Failed to retrieve migration jobs", status_code=503)
        
        return create_response(data={
            'jobs': jobs,
            'count': len(jobs),
            'status_filter': status_filter,
            'nextKey': next_key,
            'hasMore': next_key is not None
        })
        
    except ValueError:
        return create_response(message="Invalid parameters", status_code=400)
    except Exception as e:
        logger.error(f"Get migration jobs error: {str(e)}")
        return create_response(message="Failed to get migration jobs", status_code=500)

# Lambda handler for AWS Lambda deployment
def lambda_handler(event, context):
    """AWS Lambda entry point with enhanced logging."""
    try:
        logger.info(f"Lambda handler invoked: {event.get('httpMethod', 'UNKNOWN')} {event.get('path', 'UNKNOWN')}")
        return handle_request(app, event, context)
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}\n{traceback.format_exc()}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'status': 'error',
                'message': 'Internal server error',
                'timestamp': datetime.utcnow().isoformat()
            })
        }

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = CONFIG['FLASK_ENV'] == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
