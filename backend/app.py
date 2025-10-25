#!/usr/bin/env python3
"""
Subscriber Migration Portal - COMPLETE Production Backend
TRULY Consolidated with ALL Enhanced Features
Security Hardened + JWT + Complete API Set
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from functools import wraps

import boto3
import jwt
import pymysql
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from botocore.exceptions import ClientError
from serverless_wsgi import handle_request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["*"])

# Configuration from environment
CONFIG = {
    'FLASK_ENV': os.getenv('FLASK_ENV', 'production'),
    'VERSION': os.getenv('VERSION', '2.0.0-production'),
    'JWT_SECRET': os.getenv('JWT_SECRET', 'subscriber-portal-jwt-secret-2025-production'),
    'JWT_ALGORITHM': 'HS256',
    'JWT_EXPIRY_HOURS': 24,
    'SUBSCRIBER_TABLE_NAME': os.getenv('SUBSCRIBER_TABLE_NAME', 'subscriber-table'),
    'AUDIT_LOG_TABLE_NAME': os.getenv('AUDIT_LOG_TABLE_NAME', 'audit-log-table'),
    'MIGRATION_JOBS_TABLE_NAME': os.getenv('MIGRATION_JOBS_TABLE_NAME', 'migration-jobs-table'),
    'MIGRATION_UPLOAD_BUCKET_NAME': os.getenv('MIGRATION_UPLOAD_BUCKET_NAME', 'migration-uploads'),
    'LEGACY_DB_SECRET_ARN': os.getenv('LEGACY_DB_SECRET_ARN'),
    'LEGACY_DB_HOST': os.getenv('LEGACY_DB_HOST'),
    'LEGACY_DB_PORT': int(os.getenv('LEGACY_DB_PORT', '3306')),
    'LEGACY_DB_NAME': os.getenv('LEGACY_DB_NAME', 'legacydb'),
    'PROVISIONING_MODES': os.getenv('PROVISIONING_MODES', 'legacy,cloud,dual_prov').split(','),
    'PROV_MODE': os.getenv('PROV_MODE', 'dual_prov'),
}

# AWS clients initialization with error handling
try:
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    secrets_client = boto3.client('secretsmanager')
    logger.info("AWS services initialized successfully")
except ClientError as e:
    logger.error(f"AWS client initialization failed: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
    dynamodb = s3_client = secrets_client = None
except Exception as e:
    logger.error(f"AWS initialization failed: {str(e)}")
    dynamodb = s3_client = secrets_client = None

# DynamoDB tables initialization with error handling
tables = {}
try:
    if dynamodb:
        tables['subscribers'] = dynamodb.Table(CONFIG['SUBSCRIBER_TABLE_NAME'])
        tables['audit_logs'] = dynamodb.Table(CONFIG['AUDIT_LOG_TABLE_NAME'])
        tables['migration_jobs'] = dynamodb.Table(CONFIG['MIGRATION_JOBS_TABLE_NAME'])
        logger.info("DynamoDB tables initialized")
except ClientError as e:
    logger.error(f"DynamoDB table initialization failed: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
except Exception as e:
    logger.error(f"DynamoDB table initialization failed: {str(e)}")

# Enhanced Subscriber Schema (from subscriber_enhanced.py)
SUBSCRIBER_SCHEMA = {
    # Core Identity
    'uid': str, 'imsi': str, 'msisdn': str,
    # Service Configuration
    'odbic': str, 'odboc': str, 'plan_type': str, 'network_type': str, 'call_forwarding': str,
    # Roaming & Limits
    'roaming_enabled': str, 'data_limit_mb': int, 'voice_minutes': str, 'sms_count': str,
    # Status & Billing
    'status': str, 'activation_date': str, 'last_recharge': str, 'balance_amount': float, 'service_class': str,
    # Network Location
    'location_area_code': str, 'routing_area_code': str,
    # Feature Flags
    'gprs_enabled': bool, 'volte_enabled': bool, 'wifi_calling': bool,
    # Services
    'premium_services': str, 'hlr_profile': str, 'auc_profile': str, 'eir_status': str,
    'equipment_identity': str, 'network_access_mode': str,
    # QoS & Policy
    'qos_profile': str, 'apn_profile': str, 'charging_profile': str, 'fraud_profile': str,
    # Financial Limits
    'credit_limit': float, 'spending_limit': float,
    # Roaming Zones
    'international_roaming_zone': str, 'domestic_roaming_zone': str,
    # Supplementary Services
    'supplementary_services': str, 'value_added_services': str,
    # Content & Security
    'content_filtering': str, 'parental_control': str, 'emergency_services': str,
    # Technical Capabilities
    'lte_category': str, 'nr_category': str, 'bearer_capability': str, 'teleservices': str,
    'basic_services': str, 'operator_services': str, 'network_features': str,
    'security_features': str, 'mobility_management': str, 'session_management': str
}

# Default values for enhanced fields
DEFAULT_VALUES = {
    'odbic': 'ODBIC_STD_RESTRICTIONS', 'odboc': 'ODBOC_STD_RESTRICTIONS',
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

# Legacy database connection with proper error handling
def get_legacy_db_connection():
    """Get legacy MySQL database connection with proper error handling."""
    try:
        if not CONFIG['LEGACY_DB_SECRET_ARN'] or not secrets_client:
            logger.warning("Legacy DB secret ARN not configured or secrets client unavailable")
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
            connect_timeout=10,
            read_timeout=10,
            write_timeout=10
        )
        
        return connection
        
    except ClientError as e:
        logger.error(f"Secrets Manager error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
        return None
    except pymysql.Error as e:
        logger.error(f"MySQL connection failed: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid secret JSON format: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Legacy DB connection failed: {str(e)}")
        return None

# Enhanced data sanitization
def sanitize_subscriber_data(data):
    """Sanitize and add default values for subscriber data."""
    sanitized = {}
    
    for field, field_type in SUBSCRIBER_SCHEMA.items():
        if field in data:
            if field_type == int:
                sanitized[field] = int(data[field]) if data[field] != '' else 0
            elif field_type == float:
                sanitized[field] = float(data[field]) if data[field] != '' else 0.0
            elif field_type == bool:
                sanitized[field] = bool(data[field]) if isinstance(data[field], bool) else str(data[field]).lower() in ['true', '1', 'yes']
            else:
                sanitized[field] = str(data[field])
        else:
            if field in DEFAULT_VALUES:
                sanitized[field] = DEFAULT_VALUES[field]
    
    if not sanitized.get('activation_date'):
        sanitized['activation_date'] = datetime.utcnow().isoformat()
    
    if not sanitized.get('balance_amount'):
        sanitized['balance_amount'] = 0.0
        
    return sanitized

# Dual provisioning function
def dual_provision(data, method='put'):
    """Write/update/delete data in both legacy and cloud based on mode."""
    uid = data.get('uid') or data.get('subscriberId')
    
    if method in ['put', 'update']:
        data = sanitize_subscriber_data(data)
    
    # Legacy DB (MySQL) action
    if CONFIG['PROV_MODE'] in ['legacy', 'dual_prov']:
        try:
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    if method == 'put':
                        query = """
                            INSERT INTO subscribers (uid, imsi, msisdn, plan_type, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                        now = datetime.utcnow().isoformat()
                        cursor.execute(query, (
                            data.get('uid'), data.get('imsi'), data.get('msisdn'),
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
                connection.close()
        except Exception as e:
            logger.error(f"Legacy DB operation failed: {str(e)}")
            raise Exception(f"Dual Provisioning Failed: Legacy DB Error: {str(e)}")
            
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

# Secure User Management with JWT and proper password hashing
class UserManager:
    """Secure user management with JWT and hashed passwords."""
    
    USERS = {
        'admin': {
            'password_hash': generate_password_hash('Admin@123'),
            'role': 'admin',
            'permissions': ['read', 'write', 'delete', 'admin']
        },
        'operator': {
            'password_hash': generate_password_hash('Operator@123'), 
            'role': 'operator',
            'permissions': ['read', 'write']
        },
        'guest': {
            'password_hash': generate_password_hash('Guest@123'),
            'role': 'guest', 
            'permissions': ['read']
        }
    }
    
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Authenticate user with secure password checking."""
        user = UserManager.USERS.get(username)
        if user and check_password_hash(user['password_hash'], password):
            return {
                'username': username,
                'role': user['role'],
                'permissions': user['permissions']
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
            'exp': datetime.utcnow() + timedelta(hours=CONFIG['JWT_EXPIRY_HOURS'])
        }
        return jwt.encode(payload, CONFIG['JWT_SECRET'], algorithm=CONFIG['JWT_ALGORITHM'])
    
    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, CONFIG['JWT_SECRET'], algorithms=[CONFIG['JWT_ALGORITHM']])
            return {
                'username': payload['sub'],
                'role': payload['role'],
                'permissions': payload['permissions']
            }
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            return None

# Authentication decorator
def require_auth(permissions=None):
    """Decorator to require authentication and optionally specific permissions."""
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

# Utility functions
def create_response(data=None, message="Success", status_code=200, error=None):
    """Create standardized API response."""
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
    """Log action to audit table with error handling."""
    try:
        if 'audit_logs' in tables:
            log_entry = {
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{action}_{resource}_{user}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': action,
                'resource': resource,
                'user': user,
                'details': details or {}
            }
            tables['audit_logs'].put_item(Item=log_entry)
    except ClientError as e:
        logger.error(f"Audit logging DynamoDB error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
    except Exception as e:
        logger.error(f"Audit logging failed: {str(e)}")

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return create_response(message="Endpoint not found", status_code=404)

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return create_response(message="Internal server error", status_code=500)

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {str(error)}\n{traceback.format_exc()}")
    return create_response(message="An unexpected error occurred", status_code=500)

# === CORE ROUTES ===
@app.route('/api/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint."""
    health_status = {
        'status': 'healthy',
        'version': CONFIG['VERSION'],
        'environment': CONFIG['FLASK_ENV'],
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'dynamodb': bool(dynamodb),
            's3': bool(s3_client),
            'secrets_manager': bool(secrets_client),
            'legacy_db': bool(get_legacy_db_connection())
        },
        'provisioning_modes': CONFIG['PROVISIONING_MODES'],
        'current_mode': CONFIG['PROV_MODE']
    }
    
    critical_services = ['dynamodb', 's3', 'secrets_manager']
    if not all(health_status['services'][service] for service in critical_services):
        health_status['status'] = 'degraded'
    
    return create_response(data=health_status, message="Health check completed")

# === AUTHENTICATION ROUTES ===
@app.route('/api/auth/login', methods=['POST'])
def login():
    """Secure user authentication endpoint with JWT."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        username = data.get('username')
        password = data.get('password')
        
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
            'user': user,
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
    """Logout endpoint."""
    audit_log('logout', 'auth', g.current_user['username'])
    return create_response(message="Logout successful")

# === DASHBOARD ROUTES ===
@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
def get_dashboard_stats():
    """Get comprehensive dashboard statistics."""
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
        
        # Get cloud subscriber count
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(Select='COUNT')
                stats['cloudSubscribers'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Error getting cloud stats: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
            stats['systemHealth'] = 'degraded'
        
        # Get legacy subscriber count
        try:
            legacy_conn = get_legacy_db_connection()
            if legacy_conn:
                with legacy_conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != 'DELETED'")
                    result = cursor.fetchone()
                    stats['legacySubscribers'] = result['count'] if result else 0
                legacy_conn.close()
        except pymysql.Error as e:
            logger.error(f"Error getting legacy stats: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting legacy stats: {str(e)}")
        
        stats['totalSubscribers'] = stats['cloudSubscribers'] + stats['legacySubscribers']
        
        # Get migration job stats
        try:
            if 'migration_jobs' in tables:
                # Active migrations
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'IN_PROGRESS'},
                    Select='COUNT'
                )
                stats['activeMigrations'] = response.get('Count', 0)
                
                # Completed migrations
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'COMPLETED'},
                    Select='COUNT'
                )
                stats['completedMigrations'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Error getting migration stats: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
        
        audit_log('dashboard_stats_viewed', 'dashboard', g.current_user['username'])
        return create_response(data=stats, message="Dashboard stats retrieved")
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return create_response(message="Failed to get dashboard stats", status_code=500)

# === LEGACY DB ROUTES ===
@app.route('/api/legacy/test', methods=['GET'])
@require_auth(['read'])
def test_legacy_connection():
    """Test legacy database connection."""
    try:
        connection = get_legacy_db_connection()
        if not connection:
            return create_response(
                message="Legacy database connection failed", 
                status_code=503,
                data={'status': 'disconnected', 'reason': 'Connection failed - check VPC/Security Groups'}
            )
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != 'DELETED'")
                result = cursor.fetchone()
                subscriber_count = result['count'] if result else 0
        except pymysql.Error as e:
            connection.close()
            return create_response(
                message="Legacy database query failed",
                status_code=503,
                data={'status': 'error', 'error': f"Query failed: {str(e)}"}
            )
        
        connection.close()
        audit_log('legacy_connection_tested', 'legacy_db', g.current_user['username'])
        
        return create_response(data={
            'status': 'connected',
            'host': CONFIG['LEGACY_DB_HOST'],
            'database': CONFIG['LEGACY_DB_NAME'],
            'subscriber_count': subscriber_count,
            'mode': CONFIG['PROV_MODE'],
            'test_time': datetime.utcnow().isoformat()
        }, message="Legacy database connection successful")
        
    except Exception as e:
        logger.error(f"Legacy connection test failed: {str(e)}")
        return create_response(
            message="Legacy database connection failed",
            status_code=503,
            data={'status': 'error', 'error': str(e)}
        )

# === SUBSCRIBER ROUTES ===
@app.route('/api/subscribers', methods=['GET'])
@require_auth(['read'])
def get_subscribers():
    """Get subscribers with enhanced filtering and validation."""
    try:
        mode = request.args.get('mode', CONFIG['PROV_MODE'])
        limit = int(request.args.get('limit', '50'))
        search = request.args.get('search', '')
        
        if limit < 1 or limit > 1000:
            return create_response(message="Limit must be between 1 and 1000", status_code=400)
        
        subscribers = []
        
        if mode in ['cloud', 'dual_prov']:
            if 'subscribers' not in tables:
                return create_response(message="Cloud database not available", status_code=503)
            
            try:
                if search:
                    # Enhanced search across multiple fields
                    response = tables['subscribers'].scan(
                        FilterExpression='contains(#name, :search) OR contains(#email, :search) OR contains(#msisdn, :search)',
                        ExpressionAttributeNames={'#name': 'name', '#email': 'email', '#msisdn': 'msisdn'},
                        ExpressionAttributeValues={':search': search},
                        Limit=limit
                    )
                else:
                    response = tables['subscribers'].scan(Limit=limit)
                
                cloud_subscribers = response.get('Items', [])
                for sub in cloud_subscribers:
                    sub['source'] = 'cloud'
                subscribers.extend(cloud_subscribers)
            except ClientError as e:
                logger.error(f"DynamoDB scan error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
                return create_response(message="Failed to retrieve cloud subscribers", status_code=503)
        
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
                except pymysql.Error as e:
                    if connection:
                        connection.close()
                    logger.error(f"Legacy DB query error: {str(e)}")
        
        audit_log('subscribers_viewed', f'subscribers_{mode}', g.current_user['username'], {'count': len(subscribers), 'search': search})
        return create_response(data={
            'subscribers': subscribers,
            'count': len(subscribers),
            'mode': mode,
            'search': search
        })
        
    except ValueError:
        return create_response(message="Invalid limit parameter", status_code=400)
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500)

@app.route('/api/subscribers', methods=['POST'])
@require_auth(['write'])
def create_subscriber():
    """Create enhanced subscriber with dual provisioning."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        # Validate required fields
        required_fields = ['uid', 'imsi']
        for field in required_fields:
            if not data.get(field):
                return create_response(message=f"Missing required field: {field}", status_code=400)
        
        # Check for duplicates
        if 'subscribers' in tables:
            try:
                existing = tables['subscribers'].get_item(Key={'subscriberId': data['uid']}).get('Item')
                if existing:
                    return create_response(message=f"UID '{data['uid']}' already exists in cloud database", status_code=400)
            except ClientError as e:
                logger.error(f"Duplicate check error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
        
        # Enhanced provisioning
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = g.current_user['username']
        
        dual_provision(data, method='put')
        
        audit_log('subscriber_created', 'subscriber', g.current_user['username'], 
                 {'subscriber_uid': data['uid'], 'mode': CONFIG['PROV_MODE']})
        
        return create_response(data={'uid': data['uid']}, message="Subscriber created successfully", status_code=201)
        
    except json.JSONDecodeError:
        return create_response(message="Invalid JSON format", status_code=400)
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        audit_log('subscriber_create_failed', 'subscriber', g.current_user['username'], {'error': str(e)})
        return create_response(message=f"Failed to create subscriber: {str(e)}", status_code=500)

@app.route('/api/subscribers/search', methods=['GET'])
@require_auth(['read'])
def search_subscriber():
    """Enhanced subscriber search across all systems."""
    try:
        identifier_value = request.args.get('identifier')
        identifier_type = request.args.get('type', 'uid')
        
        if not identifier_value:
            return create_response(message="Identifier query parameter is required", status_code=400)
        
        cloud_data = None
        
        # Search cloud database
        if CONFIG['PROV_MODE'] in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                if identifier_type == 'uid':
                    cloud_data = tables['subscribers'].get_item(Key={'subscriberId': identifier_value}).get('Item')
                elif identifier_type == 'imsi':
                    response = tables['subscribers'].scan(
                        FilterExpression='#imsi = :imsi',
                        ExpressionAttributeNames={'#imsi': 'imsi'},
                        ExpressionAttributeValues={':imsi': identifier_value}
                    )
                    if response['Items']:
                        cloud_data = response['Items'][0]
                elif identifier_type == 'msisdn':
                    response = tables['subscribers'].scan(
                        FilterExpression='#msisdn = :msisdn',
                        ExpressionAttributeNames={'#msisdn': 'msisdn'},
                        ExpressionAttributeValues={':msisdn': identifier_value}
                    )
                    if response['Items']:
                        cloud_data = response['Items'][0]
            except ClientError as e:
                logger.error(f"Cloud search error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
        
        if cloud_data:
            cloud_data['source'] = 'cloud'
            audit_log('subscriber_searched', 'subscriber', g.current_user['username'], 
                     {'identifier': identifier_value, 'type': identifier_type, 'source': 'cloud'})
            return create_response(data=cloud_data, message="Subscriber found in cloud database")
        
        # Search legacy database
        if CONFIG['PROV_MODE'] in ['legacy', 'dual_prov']:
            connection = get_legacy_db_connection()
            if connection:
                try:
                    with connection.cursor() as cursor:
                        if identifier_type == 'uid':
                            cursor.execute("SELECT * FROM subscribers WHERE uid = %s AND status != 'DELETED'", (identifier_value,))
                        elif identifier_type == 'imsi':
                            cursor.execute("SELECT * FROM subscribers WHERE imsi = %s AND status != 'DELETED'", (identifier_value,))
                        elif identifier_type == 'msisdn':
                            cursor.execute("SELECT * FROM subscribers WHERE msisdn = %s AND status != 'DELETED'", (identifier_value,))
                        
                        legacy_data = cursor.fetchone()
                    connection.close()
                    
                    if legacy_data:
                        legacy_data['source'] = 'legacy'
                        audit_log('subscriber_searched', 'subscriber', g.current_user['username'], 
                                 {'identifier': identifier_value, 'type': identifier_type, 'source': 'legacy'})
                        return create_response(data=legacy_data, message="Subscriber found in legacy database")
                except pymysql.Error as e:
                    if connection:
                        connection.close()
                    logger.error(f"Legacy search error: {str(e)}")
        
        # Not found
        audit_log('subscriber_search_not_found', 'subscriber', g.current_user['username'], 
                 {'identifier': identifier_value, 'type': identifier_type})
        return create_response(message="Subscriber not found in any database", status_code=404)
        
    except Exception as e:
        logger.error(f"Search subscriber error: {str(e)}")
        return create_response(message="Search failed", status_code=500)

@app.route('/api/subscribers/schema', methods=['GET'])
@require_auth(['read'])
def get_subscriber_schema():
    """Get complete subscriber schema for frontend forms."""
    try:
        schema_info = {
            'fields': list(SUBSCRIBER_SCHEMA.keys()),
            'defaults': DEFAULT_VALUES,
            'enums': {
                'odbic': ['ODBIC_UNRESTRICTED', 'ODBIC_CAT1_BARRED', 'ODBIC_INTL_BARRED', 'ODBIC_STD_RESTRICTIONS'],
                'odboc': ['ODBOC_UNRESTRICTED', 'ODBOC_PREMIUM_RESTRICTED', 'ODBOC_PREMIUM_BARRED', 'ODBOC_STD_RESTRICTIONS'],
                'plan_type': ['CORPORATE_POSTPAID', 'BUSINESS_POSTPAID', 'PREMIUM_PREPAID', 'STANDARD_PREPAID'],
                'network_type': ['5G_SA_NSA', '5G_NSA', '4G_LTE_ADVANCED', '4G_LTE'],
                'service_class': ['ENTERPRISE_PLATINUM', 'BUSINESS_GOLD', 'CONSUMER_PREMIUM', 'CONSUMER_SILVER'],
                'status': ['ACTIVE', 'SUSPENDED', 'BARRED', 'TERMINATED']
            },
            'provisioning_mode': CONFIG['PROV_MODE']
        }
        
        return create_response(data=schema_info, message="Schema retrieved")
        
    except Exception as e:
        logger.error(f"Schema retrieval error: {str(e)}")
        return create_response(message="Failed to retrieve schema", status_code=500)

# === MIGRATION ROUTES ===
@app.route('/api/migration/jobs', methods=['GET'])
@require_auth(['read'])
def get_migration_jobs():
    """Get all migration jobs with enhanced filtering."""
    try:
        status_filter = request.args.get('status')
        limit = int(request.args.get('limit', '50'))
        
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
            
            # Sort by creation date (most recent first)
            jobs.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
            
        except ClientError as e:
            logger.error(f"Migration jobs query error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
            return create_response(message="Failed to retrieve migration jobs", status_code=503)
        
        audit_log('migration_jobs_viewed', 'migration', g.current_user['username'], 
                 {'count': len(jobs), 'status_filter': status_filter})
        
        return create_response(data={
            'jobs': jobs,
            'count': len(jobs),
            'status_filter': status_filter
        }, message="Migration jobs retrieved")
        
    except ValueError:
        return create_response(message="Invalid limit parameter", status_code=400)
    except Exception as e:
        logger.error(f"Get migration jobs error: {str(e)}")
        return create_response(message="Failed to get migration jobs", status_code=500)

# === BULK OPERATIONS ROUTES ===
@app.route('/api/operations/bulk-delete', methods=['POST'])
@require_auth(['delete'])
def bulk_delete_operation():
    """Enhanced bulk delete operation with comprehensive validation."""
    try:
        data = request.get_json()
        
        if not data or 'identifiers' not in data:
            return create_response(message="Identifiers array required", status_code=400)
        
        identifiers = data['identifiers']
        if not isinstance(identifiers, list) or len(identifiers) == 0:
            return create_response(message="Identifiers must be a non-empty array", status_code=400)
        
        if len(identifiers) > 1000:
            return create_response(message="Maximum 1000 identifiers per bulk operation", status_code=400)
        
        results = []
        success_count = 0
        error_count = 0
        
        for identifier in identifiers:
            try:
                # Find subscriber first
                subscriber_data = None
                
                # Check cloud first
                if CONFIG['PROV_MODE'] in ['cloud', 'dual_prov'] and 'subscribers' in tables:
                    try:
                        response = tables['subscribers'].get_item(Key={'subscriberId': identifier})
                        subscriber_data = response.get('Item')
                    except ClientError as e:
                        logger.error(f"Cloud lookup error for {identifier}: {e.response['Error']['Code']}")
                
                # Check legacy if not found in cloud
                if not subscriber_data and CONFIG['PROV_MODE'] in ['legacy', 'dual_prov']:
                    connection = get_legacy_db_connection()
                    if connection:
                        try:
                            with connection.cursor() as cursor:
                                cursor.execute("SELECT * FROM subscribers WHERE uid = %s AND status != 'DELETED'", (identifier,))
                                subscriber_data = cursor.fetchone()
                            connection.close()
                        except pymysql.Error as e:
                            if connection:
                                connection.close()
                            logger.error(f"Legacy lookup error for {identifier}: {str(e)}")
                
                if not subscriber_data:
                    results.append({
                        'identifier': identifier,
                        'status': 'not_found',
                        'message': 'Subscriber not found'
                    })
                    error_count += 1
                    continue
                
                # Perform dual provisioning delete
                dual_provision({'uid': identifier}, method='delete')
                
                results.append({
                    'identifier': identifier,
                    'status': 'deleted',
                    'message': 'Successfully deleted'
                })
                success_count += 1
                
            except Exception as delete_error:
                logger.error(f"Bulk delete error for {identifier}: {str(delete_error)}")
                results.append({
                    'identifier': identifier,
                    'status': 'error',
                    'message': str(delete_error)
                })
                error_count += 1
        
        audit_log('bulk_delete', 'subscribers', g.current_user['username'], {
            'total': len(identifiers),
            'success': success_count,
            'errors': error_count
        })
        
        return create_response(data={
            'results': results,
            'summary': {
                'total': len(identifiers),
                'success': success_count,
                'errors': error_count
            }
        }, message=f"Bulk delete completed: {success_count} successful, {error_count} errors")
        
    except json.JSONDecodeError:
        return create_response(message="Invalid JSON format", status_code=400)
    except Exception as e:
        logger.error(f"Bulk delete operation error: {str(e)}")
        return create_response(message="Bulk delete operation failed", status_code=500)

# === PROVISIONING ROUTES ===
@app.route('/api/provision/dashboard', methods=['GET'])
@require_auth(['read'])
def provisioning_dashboard():
    """Enhanced provisioning dashboard with comprehensive metrics."""
    try:
        dashboard_data = {
            'provisioning_mode': CONFIG['PROV_MODE'],
            'available_modes': CONFIG['PROVISIONING_MODES'],
            'today_provisions': 0,
            'total_subscribers': 0,
            'active_migrations': 0,
            'system_health': 'healthy',
            'last_updated': datetime.utcnow().isoformat()
        }
        
        # Get today's provisioning count
        today = datetime.utcnow().date().isoformat()
        
        try:
            if 'audit_logs' in tables:
                response = tables['audit_logs'].scan(
                    FilterExpression='#action = :action AND begins_with(#timestamp, :today)',
                    ExpressionAttributeNames={'#action': 'action', '#timestamp': 'timestamp'},
                    ExpressionAttributeValues={':action': 'subscriber_created', ':today': today},
                    Select='COUNT'
                )
                dashboard_data['today_provisions'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Today provisions count error: {e.response['Error']['Code']}")
            dashboard_data['system_health'] = 'degraded'
        
        # Get total subscriber count
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(Select='COUNT')
                dashboard_data['total_subscribers'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Total subscribers count error: {e.response['Error']['Code']}")
        
        # Get active migrations
        try:
            if 'migration_jobs' in tables:
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status IN (:status1, :status2)',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status1': 'IN_PROGRESS', ':status2': 'PENDING_UPLOAD'},
                    Select='COUNT'
                )
                dashboard_data['active_migrations'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Active migrations count error: {e.response['Error']['Code']}")
        
        audit_log('provisioning_dashboard_viewed', 'dashboard', g.current_user['username'])
        return create_response(data=dashboard_data, message="Provisioning dashboard data retrieved")
        
    except Exception as e:
        logger.error(f"Provisioning dashboard error: {str(e)}")
        return create_response(message="Failed to get provisioning dashboard", status_code=500)

# Lambda handler for AWS Lambda deployment
def lambda_handler(event, context):
    """AWS Lambda entry point."""
    return handle_request(app, event, context)

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = CONFIG['FLASK_ENV'] == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
