#!/usr/bin/env python3
"""
Subscriber Migration Portal - Production Backend
Single Source of Truth Flask Application
Consolidated from all app_*.py files
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any
from functools import wraps

import boto3
import pymysql
from flask import Flask, request, jsonify
from flask_cors import CORS
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

# AWS clients
try:
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    secrets_client = boto3.client('secretsmanager')
    logger.info("AWS services initialized successfully")
except Exception as e:
    logger.error(f"AWS initialization failed: {str(e)}")
    dynamodb = None
    s3_client = None
    secrets_client = None

# DynamoDB tables
tables = {}
try:
    if dynamodb:
        tables['subscribers'] = dynamodb.Table(CONFIG['SUBSCRIBER_TABLE_NAME'])
        tables['audit_logs'] = dynamodb.Table(CONFIG['AUDIT_LOG_TABLE_NAME'])
        tables['migration_jobs'] = dynamodb.Table(CONFIG['MIGRATION_JOBS_TABLE_NAME'])
        logger.info("DynamoDB tables initialized")
except Exception as e:
    logger.error(f"DynamoDB table initialization failed: {str(e)}")

# Legacy database connection
def get_legacy_db_connection():
    """Get legacy MySQL database connection."""
    try:
        if not CONFIG['LEGACY_DB_SECRET_ARN']:
            logger.warning("Legacy DB secret ARN not configured")
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
            cursorclass=pymysql.cursors.DictCursor
        )
        
        return connection
        
    except Exception as e:
        logger.error(f"Legacy DB connection failed: {str(e)}")
        return None

# User authentication (simplified for production)
class UserManager:
    """Simplified user management for production."""
    
    USERS = {
        'admin': {
            'password': 'Admin@123',
            'role': 'admin',
            'permissions': ['read', 'write', 'delete', 'admin']
        },
        'operator': {
            'password': 'Operator@123', 
            'role': 'operator',
            'permissions': ['read', 'write']
        },
        'guest': {
            'password': 'Guest@123',
            'role': 'guest', 
            'permissions': ['read']
        }
    }
    
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user data."""
        user = UserManager.USERS.get(username)
        if user and user['password'] == password:
            return {
                'username': username,
                'role': user['role'],
                'permissions': user['permissions']
            }
        return None
    
    @staticmethod
    def generate_token(user_data: Dict) -> str:
        """Generate simple auth token (in production, use JWT)."""
        import base64
        token_data = {
            'user': user_data,
            'timestamp': datetime.utcnow().isoformat()
        }
        return base64.b64encode(json.dumps(token_data).encode()).decode()

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
    """Log action to audit table."""
    try:
        if 'audit_logs' in tables:
            log_entry = {
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{action}_{resource}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': action,
                'resource': resource,
                'user': user,
                'details': details or {}
            }
            tables['audit_logs'].put_item(Item=log_entry)
    except Exception as e:
        logger.error(f"Audit logging failed: {str(e)}")

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return create_response(message="Endpoint not found", status_code=404)

@app.errorhandler(500)
def internal_error(error):
    return create_response(message="Internal server error", status_code=500, error=str(error))

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"Unhandled exception: {str(error)}\n{traceback.format_exc()}")
    return create_response(message="An unexpected error occurred", status_code=500, error=str(error))

# Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
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
    
    return create_response(data=health_status, message="System healthy")

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User authentication endpoint."""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return create_response(message="Username and password required", status_code=400)
        
        user = UserManager.authenticate(username, password)
        if not user:
            audit_log('login_failed', 'auth', username)
            return create_response(message="Invalid credentials", status_code=401)
        
        token = UserManager.generate_token(user)
        audit_log('login_success', 'auth', username)
        
        return create_response(data={
            'token': token,
            'user': user
        }, message="Login successful")
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return create_response(message="Login failed", status_code=500, error=str(e))

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics from both systems."""
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
        except Exception as e:
            logger.error(f"Error getting cloud stats: {str(e)}")
        
        # Get legacy subscriber count
        try:
            legacy_conn = get_legacy_db_connection()
            if legacy_conn:
                with legacy_conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers")
                    result = cursor.fetchone()
                    stats['legacySubscribers'] = result['count'] if result else 0
                legacy_conn.close()
        except Exception as e:
            logger.error(f"Error getting legacy stats: {str(e)}")
        
        stats['totalSubscribers'] = stats['cloudSubscribers'] + stats['legacySubscribers']
        
        # Get migration job stats
        try:
            if 'migration_jobs' in tables:
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'running'},
                    Select='COUNT'
                )
                stats['activeMigrations'] = response.get('Count', 0)
                
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'completed'},
                    Select='COUNT'
                )
                stats['completedMigrations'] = response.get('Count', 0)
        except Exception as e:
            logger.error(f"Error getting migration stats: {str(e)}")
        
        return create_response(data=stats, message="Dashboard stats retrieved")
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return create_response(message="Failed to get dashboard stats", status_code=500, error=str(e))

@app.route('/api/legacy/test', methods=['GET'])
def test_legacy_connection():
    """Test legacy database connection."""
    try:
        connection = get_legacy_db_connection()
        if not connection:
            return create_response(
                message="Legacy database connection failed", 
                status_code=503,
                data={'status': 'disconnected', 'reason': 'Connection failed'}
            )
        
        # Test basic query
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM subscribers")
            result = cursor.fetchone()
            subscriber_count = result['count'] if result else 0
        
        connection.close()
        
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
def get_subscribers():
    """Get subscribers based on mode parameter."""
    try:
        mode = request.args.get('mode', 'cloud')
        limit = int(request.args.get('limit', '50'))
        
        if mode == 'cloud':
            if 'subscribers' not in tables:
                return create_response(message="DynamoDB not available", status_code=503)
            
            response = tables['subscribers'].scan(Limit=limit)
            subscribers = response.get('Items', [])
            
        elif mode == 'legacy':
            connection = get_legacy_db_connection()
            if not connection:
                return create_response(message="Legacy database not available", status_code=503)
            
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM subscribers LIMIT {limit}")
                subscribers = cursor.fetchall()
            connection.close()
            
        else:
            return create_response(message="Invalid mode. Use 'cloud' or 'legacy'", status_code=400)
        
        return create_response(data={
            'subscribers': subscribers,
            'count': len(subscribers),
            'mode': mode
        })
        
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return create_response(message="Failed to get subscribers", status_code=500, error=str(e))

@app.route('/api/subscribers', methods=['POST'])
def create_subscriber():
    """Create a new subscriber."""
    try:
        data = request.get_json()
        mode = data.get('mode', 'cloud')
        
        subscriber = {
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'plan': data.get('plan', 'basic'),
            'status': data.get('status', 'active'),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Validate required fields
        required_fields = ['name', 'email', 'phone']
        for field in required_fields:
            if not subscriber.get(field):
                return create_response(message=f"Missing required field: {field}", status_code=400)
        
        if mode == 'cloud':
            subscriber['id'] = f"sub_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{data.get('email', 'unknown').replace('@', '_')}"
            tables['subscribers'].put_item(Item=subscriber)
            
        elif mode == 'legacy':
            connection = get_legacy_db_connection()
            if not connection:
                return create_response(message="Legacy database not available", status_code=503)
            
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO subscribers (name, email, phone, plan, status, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (subscriber['name'], subscriber['email'], subscriber['phone'], 
                     subscriber['plan'], subscriber['status'], subscriber['created_at'])
                )
                connection.commit()
                subscriber['id'] = cursor.lastrowid
            connection.close()
            
        audit_log('create', 'subscriber', 'system', {'mode': mode, 'subscriber_id': subscriber['id']})
        
        return create_response(data=subscriber, message="Subscriber created successfully", status_code=201)
        
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_response(message="Failed to create subscriber", status_code=500, error=str(e))

# Additional endpoints for migration jobs, bulk operations, etc. would go here
# This is a consolidated foundation that can be extended

# Lambda handler for AWS Lambda deployment
def lambda_handler(event, context):
    """AWS Lambda entry point."""
    return handle_request(app, event, context)

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = CONFIG['FLASK_ENV'] == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
