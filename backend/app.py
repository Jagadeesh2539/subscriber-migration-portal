#!/usr/bin/env python3
"""
Subscriber Migration Portal - Production Backend
Consolidated Single Source of Truth Flask Application
Security Hardened with JWT and Proper Error Handling
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
    'JWT_SECRET': os.getenv('JWT_SECRET', 'your-secret-key-change-in-production'),
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

# Legacy database connection with proper error handling
def get_legacy_db_connection():
    """Get legacy MySQL database connection with proper error handling."""
    try:
        if not CONFIG['LEGACY_DB_SECRET_ARN'] or not secrets_client:
            logger.warning("Legacy DB secret ARN not configured or secrets client unavailable")
            return None
            
        # Get credentials from Secrets Manager
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

# Secure User Management with JWT and proper password hashing
class UserManager:
    """Secure user management with JWT and hashed passwords."""
    
    # In production, store these in a database with proper salted hashes
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

# Routes
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
        'provisioning_modes': CONFIG['PROVISIONING_MODES']
    }
    
    # Check if core services are available
    critical_services = ['dynamodb', 's3', 'secrets_manager']
    if not all(health_status['services'][service] for service in critical_services):
        health_status['status'] = 'degraded'
    
    return create_response(data=health_status, message="Health check completed")

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
            'expires_in': CONFIG['JWT_EXPIRY_HOURS'] * 3600  # seconds
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

@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
def get_dashboard_stats():
    """Get dashboard statistics from both systems with proper error handling."""
    try:
        stats = {
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'legacySubscribers': 0,
            'activeMigrations': 0,
            'completedMigrations': 0,
            'systemHealth': 'healthy',
            'lastUpdated': datetime.utcnow().isoformat()
        }
        
        # Get cloud subscriber count
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(
                    Select='COUNT'
                )
                stats['cloudSubscribers'] = response.get('Count', 0)
        except ClientError as e:
            logger.error(f"Error getting cloud stats: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
            stats['systemHealth'] = 'degraded'
        
        # Get legacy subscriber count
        try:
            legacy_conn = get_legacy_db_connection()
            if legacy_conn:
                with legacy_conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers")
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
                    ExpressionAttributeValues={':status': 'running'},
                    Select='COUNT'
                )
                stats['activeMigrations'] = response.get('Count', 0)
                
                # Completed migrations
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'completed'},
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

@app.route('/api/legacy/test', methods=['GET'])
@require_auth(['read'])
def test_legacy_connection():
    """Test legacy database connection with comprehensive error handling."""
    try:
        connection = get_legacy_db_connection()
        if not connection:
            return create_response(
                message="Legacy database connection failed", 
                status_code=503,
                data={'status': 'disconnected', 'reason': 'Connection failed - check VPC/Security Groups'}
            )
        
        # Test basic query
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM subscribers")
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
            'test_time': datetime.utcnow().isoformat()
        }, message="Legacy database connection successful")
        
    except Exception as e:
        logger.error(f"Legacy connection test failed: {str(e)}")
        return create_response(
            message="Legacy database connection failed",
            status_code=503,
            data={'status': 'error', 'error': str(e)}
        )

@app.route('/api/subscribers', methods=['GET'])
@require_auth(['read'])
def get_subscribers():
    """Get subscribers with proper error handling and validation."""
    try:
        mode = request.args.get('mode', 'cloud')
        limit = int(request.args.get('limit', '50'))
        
        # Validate limit
        if limit < 1 or limit > 1000:
            return create_response(message="Limit must be between 1 and 1000", status_code=400)
        
        if mode == 'cloud':
            if 'subscribers' not in tables:
                return create_response(message="Cloud database not available", status_code=503)
            
            try:
                response = tables['subscribers'].scan(Limit=limit)
                subscribers = response.get('Items', [])
            except ClientError as e:
                logger.error(f"DynamoDB scan error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
                return create_response(message="Failed to retrieve cloud subscribers", status_code=503)
            
        elif mode == 'legacy':
            connection = get_legacy_db_connection()
            if not connection:
                return create_response(message="Legacy database not available", status_code=503)
            
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM subscribers LIMIT %s", (limit,))
                    subscribers = cursor.fetchall()
                connection.close()
            except pymysql.Error as e:
                if connection:
                    connection.close()
                logger.error(f"Legacy DB query error: {str(e)}")
                return create_response(message="Failed to retrieve legacy subscribers", status_code=503)
            
        else:
            return create_response(message="Invalid mode. Use 'cloud' or 'legacy'", status_code=400)
        
        audit_log('subscribers_viewed', f'subscribers_{mode}', g.current_user['username'], {'count': len(subscribers)})
        return create_response(data={
            'subscribers': subscribers,
            'count': len(subscribers),
            'mode': mode
        })
        
    except ValueError:
        return create_response(message="Invalid limit parameter", status_code=400)
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500)

@app.route('/api/subscribers', methods=['POST'])
@require_auth(['write'])
def create_subscriber():
    """Create a new subscriber with validation and proper error handling."""
    try:
        data = request.get_json()
        
        if not data:
            return create_response(message="Invalid JSON payload", status_code=400)
        
        mode = data.get('mode', 'cloud')
        
        # Build subscriber object with validation
        subscriber = {
            'name': data.get('name', '').strip(),
            'email': data.get('email', '').strip().lower(),
            'phone': data.get('phone', '').strip(),
            'plan': data.get('plan', 'basic').strip(),
            'status': data.get('status', 'active').strip(),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Validate required fields
        required_fields = ['name', 'email', 'phone']
        for field in required_fields:
            if not subscriber.get(field):
                return create_response(message=f"Missing required field: {field}", status_code=400)
        
        # Basic email validation
        if '@' not in subscriber['email'] or '.' not in subscriber['email'].split('@')[-1]:
            return create_response(message="Invalid email format", status_code=400)
        
        # Validate mode
        if mode not in ['cloud', 'legacy']:
            return create_response(message="Invalid mode. Use 'cloud' or 'legacy'", status_code=400)
        
        if mode == 'cloud':
            if 'subscribers' not in tables:
                return create_response(message="Cloud database not available", status_code=503)
            
            subscriber['id'] = f"sub_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{subscriber['email'].replace('@', '_').replace('.', '_')}"
            
            try:
                tables['subscribers'].put_item(Item=subscriber)
            except ClientError as e:
                logger.error(f"DynamoDB put error: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
                return create_response(message="Failed to create cloud subscriber", status_code=503)
            
        elif mode == 'legacy':
            connection = get_legacy_db_connection()
            if not connection:
                return create_response(message="Legacy database not available", status_code=503)
            
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO subscribers (name, email, phone, plan, status, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                        (subscriber['name'], subscriber['email'], subscriber['phone'], 
                         subscriber['plan'], subscriber['status'], subscriber['created_at'])
                    )
                    connection.commit()
                    subscriber['id'] = cursor.lastrowid
                connection.close()
            except pymysql.Error as e:
                if connection:
                    connection.rollback()
                    connection.close()
                logger.error(f"Legacy DB insert error: {str(e)}")
                return create_response(message="Failed to create legacy subscriber", status_code=503)
            
        audit_log('subscriber_created', f'subscriber_{mode}', g.current_user['username'], 
                 {'subscriber_id': subscriber['id'], 'mode': mode})
        
        return create_response(data=subscriber, message="Subscriber created successfully", status_code=201)
        
    except json.JSONDecodeError:
        return create_response(message="Invalid JSON format", status_code=400)
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_response(message="Failed to create subscriber", status_code=500)

# Lambda handler for AWS Lambda deployment
def lambda_handler(event, context):
    """AWS Lambda entry point."""
    return handle_request(app, event, context)

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = CONFIG['FLASK_ENV'] == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
