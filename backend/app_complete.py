#!/usr/bin/env python3
"""
Subscriber Migration Portal - Complete Production Backend
Features: Bulk Operations, Analytics, Migration, Provisioning, Monitoring
"""

import os
import json
import logging
import traceback
import uuid
import csv
import io
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from functools import wraps
from decimal import Decimal

import boto3
import jwt
import pymysql
from flask import Flask, request, jsonify, g, make_response, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError
from serverless_wsgi import handle_request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration
CONFIG = {
    'VERSION': '2.1.0-production-complete',
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
    'MAX_FILE_SIZE': 50 * 1024 * 1024,  # 50MB
    'ALLOWED_EXTENSIONS': {'.csv', '.json', '.xml'}
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
    cloudwatch = boto3.client('cloudwatch')
    logger.info("AWS services initialized")
except Exception as e:
    logger.warning(f"AWS initialization: {str(e)}")
    dynamodb = s3_client = secrets_client = cloudwatch = None

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

# Token blacklist functions
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
            connect_timeout=5,
            read_timeout=10,
            write_timeout=10
        )
    except Exception as e:
        logger.warning(f"Legacy DB connection failed: {str(e)}")
        return None

# User Management Class
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
    """Enhanced audit logging."""
    try:
        if 'audit_logs' in tables:
            log_entry = {
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': action,
                'resource': resource,
                'user': user,
                'ip_address': request.remote_addr if request else 'system',
                'user_agent': request.headers.get('User-Agent', 'unknown') if request else 'system',
                'details': details or {},
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())
            }
            tables['audit_logs'].put_item(Item=log_entry)
    except Exception as e:
        logger.error(f"Audit log error: {str(e)}")

# File validation
def validate_file(file):
    """Validate uploaded file."""
    if not file or not file.filename:
        return False, "No file provided"
    
    if file.content_length and file.content_length > CONFIG['MAX_FILE_SIZE']:
        return False, f"File too large. Max size: {CONFIG['MAX_FILE_SIZE'] // (1024*1024)}MB"
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in CONFIG['ALLOWED_EXTENSIONS']:
        return False, f"Invalid file type. Allowed: {', '.join(CONFIG['ALLOWED_EXTENSIONS'])}"
    
    return True, "Valid file"

# === ROUTES ===

# Health and System
@app.route('/api/health', methods=['GET'])
@app.route('/health', methods=['GET'])
def health_check():
    """Enhanced health check."""
    health_status = {
        'status': 'healthy',
        'version': CONFIG['VERSION'],
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'app': True,
            'dynamodb': bool(dynamodb),
            's3': bool(s3_client), 
            'secrets_manager': bool(secrets_client),
            'cloudwatch': bool(cloudwatch)
        },
        'current_mode': CONFIG['PROV_MODE'],
        'environment': {
            'region': os.getenv('AWS_REGION', 'unknown'),
            'lambda_function': os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'local')
        }
    }
    
    # Check database connectivity
    try:
        if 'subscribers' in tables:
            tables['subscribers'].scan(Limit=1)
            health_status['services']['dynamodb_tables'] = True
    except Exception:
        health_status['services']['dynamodb_tables'] = False
        health_status['status'] = 'degraded'
    
    try:
        connection = get_legacy_db_connection()
        if connection:
            connection.close()
            health_status['services']['legacy_db'] = True
        else:
            health_status['services']['legacy_db'] = False
    except Exception:
        health_status['services']['legacy_db'] = False
    
    return create_response(data=health_status, message="Health check completed")

# Authentication Routes
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

# Dashboard and Statistics
@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
def get_dashboard_stats():
    """Comprehensive dashboard statistics."""
    try:
        stats = {
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'legacySubscribers': 0,
            'systemHealth': 'healthy',
            'provisioningMode': CONFIG['PROV_MODE'],
            'lastUpdated': datetime.utcnow().isoformat(),
            'migrationJobs': {
                'active': 0,
                'completed': 0,
                'failed': 0,
                'pending': 0
            },
            'recentActivity': [],
            'performanceMetrics': {
                'avgResponseTime': 0,
                'successRate': 0,
                'throughput': 0
            }
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
        
        # Get migration job stats
        try:
            if 'migration_jobs' in tables:
                response = tables['migration_jobs'].scan(Select='ALL_ATTRIBUTES')
                jobs = response.get('Items', [])
                
                for job in jobs:
                    status = job.get('status', 'unknown').lower()
                    if status in stats['migrationJobs']:
                        stats['migrationJobs'][status] += 1
                
                # Recent activity
                recent_jobs = sorted(jobs, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
                stats['recentActivity'] = [{
                    'id': job.get('id'),
                    'type': 'migration',
                    'status': job.get('status'),
                    'timestamp': job.get('created_at'),
                    'description': f"Migration job {job.get('id', 'unknown')}"
                } for job in recent_jobs]
        except Exception:
            pass
        
        stats['totalSubscribers'] = stats['cloudSubscribers'] + stats['legacySubscribers']
        
        return create_response(data=stats)
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return create_response(message="Failed to get dashboard stats", status_code=500)

# Subscriber Management Routes
@app.route('/api/subscribers', methods=['GET'])
@require_auth(['read'])
def get_subscribers():
    """Get subscribers with advanced filtering."""
    try:
        limit = min(int(request.args.get('limit', '50')), 100)
        search = sanitize_input(request.args.get('search', ''), 100)
        source = request.args.get('source', 'all')  # all, cloud, legacy
        status = request.args.get('status', 'all')
        
        subscribers = []
        total_count = 0
        
        # Cloud subscribers
        if source in ['all', 'cloud'] and 'subscribers' in tables:
            try:
                if search:
                    response = tables['subscribers'].scan(
                        FilterExpression='contains(subscriberId, :search) OR contains(imsi, :search) OR contains(msisdn, :search)',
                        ExpressionAttributeValues={':search': search},
                        Limit=limit
                    )
                else:
                    response = tables['subscribers'].scan(Limit=limit)
                
                cloud_subscribers = response.get('Items', [])
                for sub in cloud_subscribers:
                    sub['source'] = 'cloud'
                    # Convert Decimal types to float for JSON serialization
                    for key, value in sub.items():
                        if isinstance(value, Decimal):
                            sub[key] = float(value)
                subscribers.extend(cloud_subscribers)
                total_count += response.get('Count', 0)
            except Exception as e:
                logger.error(f"Cloud query error: {str(e)}")
        
        # Legacy subscribers
        if source in ['all', 'legacy']:
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        where_clause = "WHERE status != 'DELETED'"
                        params = []
                        
                        if search:
                            where_clause += " AND (uid LIKE %s OR imsi LIKE %s OR msisdn LIKE %s)"
                            search_param = f"%{search}%"
                            params.extend([search_param, search_param, search_param])
                        
                        if status != 'all':
                            where_clause += " AND status = %s"
                            params.append(status.upper())
                        
                        query = f"SELECT * FROM subscribers {where_clause} LIMIT {limit}"
                        cursor.execute(query, params)
                        legacy_subscribers = cursor.fetchall()
                        
                        for sub in legacy_subscribers:
                            sub['source'] = 'legacy'
                        
                        subscribers.extend(legacy_subscribers)
                    connection.close()
            except Exception as e:
                logger.error(f"Legacy query error: {str(e)}")
        
        return create_response(data={
            'subscribers': subscribers[:limit],
            'count': len(subscribers),
            'total_count': total_count,
            'search': search,
            'source': source,
            'status': status
        })
        
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500)

@app.route('/api/subscribers', methods=['POST'])
@require_auth(['write'])
def create_subscriber():
    """Create subscriber in specified system."""
    try:
        data = request.get_json()
        
        if not data or not data.get('uid') or not data.get('imsi'):
            return create_response(message="Missing required fields: uid, imsi", status_code=400)
        
        uid = sanitize_input(data['uid'], 50)
        mode = data.get('mode', CONFIG['PROV_MODE'])
        
        # Enhanced data preparation
        subscriber_data = {
            'subscriberId': uid,
            'uid': uid,
            'imsi': sanitize_input(data['imsi'], 20),
            'msisdn': sanitize_input(data.get('msisdn', ''), 20),
            'status': data.get('status', 'ACTIVE'),
            'created_at': datetime.utcnow().isoformat(),
            'created_by': g.current_user['username'],
            'last_updated': datetime.utcnow().isoformat(),
            'provisioning_mode': mode
        }
        
        # Add optional fields
        for field in ['apn', 'service_profile', 'roaming_allowed', 'data_limit']:
            if field in data:
                subscriber_data[field] = data[field]
        
        results = {}
        
        # Store in cloud (DynamoDB)
        if mode in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                tables['subscribers'].put_item(Item=subscriber_data)
                results['cloud'] = 'success'
            except Exception as e:
                logger.error(f"Cloud storage error: {str(e)}")
                results['cloud'] = f'error: {str(e)}'
        
        # Store in legacy system
        if mode in ['legacy', 'dual_prov']:
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        # Insert into legacy database
                        cursor.execute("""
                            INSERT INTO subscribers (uid, imsi, msisdn, status, created_at, created_by)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            subscriber_data['uid'],
                            subscriber_data['imsi'],
                            subscriber_data.get('msisdn'),
                            subscriber_data['status'],
                            subscriber_data['created_at'],
                            subscriber_data['created_by']
                        ))
                    connection.commit()
                    connection.close()
                    results['legacy'] = 'success'
                else:
                    results['legacy'] = 'error: no connection'
            except Exception as e:
                logger.error(f"Legacy storage error: {str(e)}")
                results['legacy'] = f'error: {str(e)}'
        
        audit_log('subscriber_created', 'subscriber', g.current_user['username'], {
            'uid': uid,
            'mode': mode,
            'results': results
        })
        
        return create_response(data={
            'uid': uid,
            'mode': mode,
            'results': results
        }, message="Subscriber created", status_code=201)
        
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_response(message=f"Failed to create subscriber: {str(e)}", status_code=500)

@app.route('/api/subscribers/<subscriber_id>', methods=['PUT'])
@require_auth(['write'])
def update_subscriber(subscriber_id):
    """Update subscriber."""
    try:
        data = request.get_json()
        if not data:
            return create_response(message="No data provided", status_code=400)
        
        mode = data.get('mode', CONFIG['PROV_MODE'])
        update_data = {
            'last_updated': datetime.utcnow().isoformat(),
            'updated_by': g.current_user['username']
        }
        
        # Update allowed fields
        for field in ['status', 'msisdn', 'apn', 'service_profile', 'roaming_allowed', 'data_limit']:
            if field in data:
                update_data[field] = data[field]
        
        results = {}
        
        # Update in cloud
        if mode in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                # Build update expression
                update_expression = "SET "
                expression_values = {}
                
                for key, value in update_data.items():
                    update_expression += f"{key} = :{key}, "
                    expression_values[f":{key}"] = value
                
                update_expression = update_expression.rstrip(", ")
                
                tables['subscribers'].update_item(
                    Key={'subscriberId': subscriber_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values
                )
                results['cloud'] = 'success'
            except Exception as e:
                logger.error(f"Cloud update error: {str(e)}")
                results['cloud'] = f'error: {str(e)}'
        
        # Update in legacy
        if mode in ['legacy', 'dual_prov']:
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        # Build update query
                        set_clause = ", ".join([f"{key} = %s" for key in update_data.keys()])
                        query = f"UPDATE subscribers SET {set_clause} WHERE uid = %s"
                        values = list(update_data.values()) + [subscriber_id]
                        
                        cursor.execute(query, values)
                    connection.commit()
                    connection.close()
                    results['legacy'] = 'success'
                else:
                    results['legacy'] = 'error: no connection'
            except Exception as e:
                logger.error(f"Legacy update error: {str(e)}")
                results['legacy'] = f'error: {str(e)}'
        
        audit_log('subscriber_updated', 'subscriber', g.current_user['username'], {
            'subscriber_id': subscriber_id,
            'mode': mode,
            'results': results,
            'changes': update_data
        })
        
        return create_response(data={
            'subscriber_id': subscriber_id,
            'results': results
        }, message="Subscriber updated")
        
    except Exception as e:
        logger.error(f"Update subscriber error: {str(e)}")
        return create_response(message=f"Failed to update subscriber: {str(e)}", status_code=500)

@app.route('/api/subscribers/<subscriber_id>', methods=['DELETE'])
@require_auth(['delete'])
def delete_subscriber(subscriber_id):
    """Delete subscriber from specified systems."""
    try:
        mode = request.args.get('mode', CONFIG['PROV_MODE'])
        soft_delete = request.args.get('soft', 'true').lower() == 'true'
        
        results = {}
        
        # Delete from cloud
        if mode in ['cloud', 'dual_prov'] and 'subscribers' in tables:
            try:
                if soft_delete:
                    tables['subscribers'].update_item(
                        Key={'subscriberId': subscriber_id},
                        UpdateExpression="SET #status = :status, deleted_at = :deleted_at, deleted_by = :deleted_by",
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={
                            ':status': 'DELETED',
                            ':deleted_at': datetime.utcnow().isoformat(),
                            ':deleted_by': g.current_user['username']
                        }
                    )
                else:
                    tables['subscribers'].delete_item(Key={'subscriberId': subscriber_id})
                results['cloud'] = 'success'
            except Exception as e:
                logger.error(f"Cloud delete error: {str(e)}")
                results['cloud'] = f'error: {str(e)}'
        
        # Delete from legacy
        if mode in ['legacy', 'dual_prov']:
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        if soft_delete:
                            cursor.execute(
                                "UPDATE subscribers SET status = 'DELETED', deleted_at = %s, deleted_by = %s WHERE uid = %s",
                                (datetime.utcnow().isoformat(), g.current_user['username'], subscriber_id)
                            )
                        else:
                            cursor.execute("DELETE FROM subscribers WHERE uid = %s", (subscriber_id,))
                    connection.commit()
                    connection.close()
                    results['legacy'] = 'success'
                else:
                    results['legacy'] = 'error: no connection'
            except Exception as e:
                logger.error(f"Legacy delete error: {str(e)}")
                results['legacy'] = f'error: {str(e)}'
        
        audit_log('subscriber_deleted', 'subscriber', g.current_user['username'], {
            'subscriber_id': subscriber_id,
            'mode': mode,
            'soft_delete': soft_delete,
            'results': results
        })
        
        return create_response(data={
            'subscriber_id': subscriber_id,
            'results': results
        }, message="Subscriber deleted")
        
    except Exception as e:
        logger.error(f"Delete subscriber error: {str(e)}")
        return create_response(message=f"Failed to delete subscriber: {str(e)}", status_code=500)

# Bulk Operations Routes
@app.route('/api/operations/bulk-delete', methods=['POST'])
@require_auth(['delete'])
def bulk_delete():
    """Bulk delete subscribers."""
    try:
        data = request.get_json()
        identifiers = data.get('identifiers', [])
        mode = data.get('mode', CONFIG['PROV_MODE'])
        soft_delete = data.get('soft_delete', True)
        
        if not identifiers:
            return create_response(message="No identifiers provided", status_code=400)
        
        if len(identifiers) > 100:
            return create_response(message="Maximum 100 identifiers allowed", status_code=400)
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        for identifier in identifiers:
            try:
                # Delete from cloud
                if mode in ['cloud', 'dual_prov'] and 'subscribers' in tables:
                    if soft_delete:
                        tables['subscribers'].update_item(
                            Key={'subscriberId': str(identifier)},
                            UpdateExpression="SET #status = :status, deleted_at = :deleted_at, deleted_by = :deleted_by",
                            ExpressionAttributeNames={'#status': 'status'},
                            ExpressionAttributeValues={
                                ':status': 'DELETED',
                                ':deleted_at': datetime.utcnow().isoformat(),
                                ':deleted_by': g.current_user['username']
                            }
                        )
                    else:
                        tables['subscribers'].delete_item(Key={'subscriberId': str(identifier)})
                
                # Delete from legacy
                if mode in ['legacy', 'dual_prov']:
                    connection = get_legacy_db_connection()
                    if connection:
                        with connection.cursor() as cursor:
                            if soft_delete:
                                cursor.execute(
                                    "UPDATE subscribers SET status = 'DELETED', deleted_at = %s, deleted_by = %s WHERE uid = %s",
                                    (datetime.utcnow().isoformat(), g.current_user['username'], str(identifier))
                                )
                            else:
                                cursor.execute("DELETE FROM subscribers WHERE uid = %s", (str(identifier),))
                        connection.commit()
                        connection.close()
                
                results['successful'] += 1
                
            except Exception as e:
                results['errors'].append({
                    'identifier': identifier,
                    'error': str(e)
                })
                results['failed'] += 1
            
            results['processed'] += 1
        
        audit_log('bulk_delete', 'subscriber', g.current_user['username'], {
            'count': len(identifiers),
            'mode': mode,
            'results': results
        })
        
        return create_response(data=results, message=f"Bulk delete completed: {results['successful']} successful, {results['failed']} failed")
        
    except Exception as e:
        logger.error(f"Bulk delete error: {str(e)}")
        return create_response(message=f"Bulk delete failed: {str(e)}", status_code=500)

@app.route('/api/audit/compare', methods=['POST'])
@require_auth(['read'])
def bulk_audit():
    """Compare data between systems."""
    try:
        data = request.get_json()
        systems = data.get('systems', ['legacy', 'cloud'])
        sample_size = min(int(data.get('sample_size', 100)), 1000)
        
        audit_results = {
            'comparison_timestamp': datetime.utcnow().isoformat(),
            'systems_compared': systems,
            'sample_size': sample_size,
            'discrepancies': [],
            'stats': {
                'total_compared': 0,
                'matches': 0,
                'discrepancies': 0,
                'cloud_only': 0,
                'legacy_only': 0
            }
        }
        
        cloud_data = {}
        legacy_data = {}
        
        # Get cloud data
        if 'cloud' in systems and 'subscribers' in tables:
            response = tables['subscribers'].scan(Limit=sample_size)
            for item in response.get('Items', []):
                cloud_data[item['subscriberId']] = item
        
        # Get legacy data
        if 'legacy' in systems:
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT * FROM subscribers WHERE status != 'DELETED' LIMIT {sample_size}")
                    for item in cursor.fetchall():
                        legacy_data[item['uid']] = item
                connection.close()
        
        # Compare data
        all_ids = set(cloud_data.keys()) | set(legacy_data.keys())
        audit_results['stats']['total_compared'] = len(all_ids)
        
        for uid in all_ids:
            cloud_record = cloud_data.get(uid)
            legacy_record = legacy_data.get(uid)
            
            if cloud_record and legacy_record:
                # Compare key fields
                discrepancy = {
                    'uid': uid,
                    'type': 'field_mismatch',
                    'differences': []
                }
                
                for field in ['imsi', 'msisdn', 'status']:
                    cloud_val = cloud_record.get(field)
                    legacy_val = legacy_record.get(field)
                    if cloud_val != legacy_val:
                        discrepancy['differences'].append({
                            'field': field,
                            'cloud_value': cloud_val,
                            'legacy_value': legacy_val
                        })
                
                if discrepancy['differences']:
                    audit_results['discrepancies'].append(discrepancy)
                    audit_results['stats']['discrepancies'] += 1
                else:
                    audit_results['stats']['matches'] += 1
            
            elif cloud_record and not legacy_record:
                audit_results['discrepancies'].append({
                    'uid': uid,
                    'type': 'cloud_only',
                    'data': cloud_record
                })
                audit_results['stats']['cloud_only'] += 1
            
            elif legacy_record and not cloud_record:
                audit_results['discrepancies'].append({
                    'uid': uid,
                    'type': 'legacy_only',
                    'data': legacy_record
                })
                audit_results['stats']['legacy_only'] += 1
        
        audit_log('bulk_audit', 'system', g.current_user['username'], {
            'systems': systems,
            'stats': audit_results['stats']
        })
        
        return create_response(data=audit_results, message="Audit comparison completed")
        
    except Exception as e:
        logger.error(f"Bulk audit error: {str(e)}")
        return create_response(message=f"Bulk audit failed: {str(e)}", status_code=500)

# Migration Routes (continued in part 2...)

def lambda_handler(event, context):
    """Bulletproof AWS Lambda entry point."""
    try:
        logger.info(f"Lambda invoked with event: {json.dumps(event, default=str)[:500]}")
        
        if not event:
            event = {}
        
        cors_headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With'
        }
        
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
                        'secrets_manager': bool(secrets_client),
                        'cloudwatch': bool(cloudwatch)
                    },
                    'features': [
                        'authentication',
                        'subscriber_management',
                        'bulk_operations',
                        'migration_jobs',
                        'analytics',
                        'provisioning',
                        'audit_logging'
                    ]
                }),
                'isBase64Encoded': False
            }
        
        logger.info(f"Processing Flask request: {standardized_event['httpMethod']} {standardized_event['path']}")
        response = handle_request(app, standardized_event, context)
        
        if 'headers' not in response:
            response['headers'] = {}
        response['headers'].update(cors_headers)
        
        logger.info(f"Lambda response status: {response.get('statusCode', 'unknown')}")
        return response
        
    except Exception as e:
        logger.error(f"Lambda handler critical error: {str(e)}\n{traceback.format_exc()}")
        
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
                'version': CONFIG['VERSION']
            }),
            'isBase64Encoded': False
        }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)