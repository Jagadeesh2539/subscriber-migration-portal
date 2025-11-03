#!/usr/bin/env python3
import json
import os
import boto3
from datetime import datetime
from typing import Dict, Any

# Import from layer
try:
    from common_utils import create_response, create_error_response, DynamoDBHelper
except ImportError:
    # Fallback for local testing
    def create_response(status_code: int = 200, body: Dict = None, headers: Dict = None, origin: str = None) -> Dict[str, Any]:
        response_headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': origin or '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        }
        if headers:
            response_headers.update(headers)
        
        return {
            'statusCode': status_code,
            'headers': response_headers,
            'body': json.dumps(body or {}, default=str)
        }
    
    def create_error_response(status_code: int, message: str, error_code: str = None, origin: str = None) -> Dict[str, Any]:
        return create_response(status_code, {'error': message, 'code': error_code}, origin=origin)
    
    class DynamoDBHelper:
        @staticmethod
        def get_table(table_name: str):
            return boto3.resource('dynamodb').Table(table_name)

# Initialize AWS resources
dynamodb = boto3.resource('dynamodb')
rds_client = boto3.client('rds')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Health check endpoint handler
    """
    # Get request details
    path = event.get('path', '/')
    method = event.get('httpMethod', 'GET')
    headers = event.get('headers', {})
    origin = headers.get('origin')
    
    # Handle OPTIONS for CORS
    if method == 'OPTIONS':
        return create_response(200, {'message': 'OK'}, origin=origin)
    
    # Only allow GET for health checks
    if method != 'GET':
        return create_error_response(405, 'Method not allowed', 'METHOD_NOT_ALLOWED', origin=origin)
    
    # Build health response
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'Subscriber Migration Portal',
        'version': '3.0.0',
        'path': path,
        'function': context.function_name if context else 'local',
        'request_id': context.aws_request_id if context else 'local-test'
    }
    
    # Check environment variables and dependencies
    try:
        checks = {
            'environment': check_environment(),
            'dynamodb': check_dynamodb(),
            'rds': check_rds()
        }
        
        # Add detailed checks if requested
        query_params = event.get('queryStringParameters') or {}
        if query_params.get('detailed') == 'true':
            health_data['checks'] = checks
            
            # Determine overall health
            all_healthy = all(check.get('status') == 'healthy' for check in checks.values())
            health_data['status'] = 'healthy' if all_healthy else 'degraded'
        
        # Add endpoint-specific messages
        if path == '/':
            health_data['message'] = 'API Gateway root endpoint is operational'
        elif path == '/health':
            health_data['message'] = 'Health check endpoint is operational'
        elif path == '/status':
            health_data['message'] = 'Status endpoint is operational'
            health_data['checks'] = checks  # Always include checks for /status
        elif path == '/ping':
            return create_response(200, {
                'pong': True, 
                'timestamp': datetime.utcnow().isoformat(),
                'message': 'Ping successful'
            }, origin=origin)
        
        # Determine status code based on health
        status_code = 200
        if health_data.get('status') == 'degraded':
            status_code = 503
            
        return create_response(status_code, health_data, origin=origin)
        
    except Exception as e:
        # Log error but don't expose internal details
        print(f"Health check error: {str(e)}")
        return create_response(503, {
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'Subscriber Migration Portal',
            'message': 'Health check failed',
            'path': path
        }, origin=origin)

def check_environment() -> Dict[str, Any]:
    """Check environment variables"""
    required_vars = [
        'SUBSCRIBERS_TABLE',
        'SETTINGS_TABLE',
        'MIGRATION_JOBS_TABLE'
    ]
    
    missing = []
    present = []
    
    for var in required_vars:
        if os.environ.get(var):
            present.append(var)
        else:
            missing.append(var)
    
    return {
        'status': 'healthy' if not missing else 'unhealthy',
        'present': present,
        'missing': missing
    }

def check_dynamodb() -> Dict[str, Any]:
    """Check DynamoDB tables"""
    try:
        tables_status = {}
        
        table_vars = {
            'subscribers': os.environ.get('SUBSCRIBERS_TABLE'),
            'settings': os.environ.get('SETTINGS_TABLE'),
            'migration_jobs': os.environ.get('MIGRATION_JOBS_TABLE')
        }
        
        healthy_tables = 0
        total_tables = len([t for t in table_vars.values() if t])
        
        for table_type, table_name in table_vars.items():
            if table_name:
                try:
                    table = DynamoDBHelper.get_table(table_name)
                    table.load()
                    status = table.table_status
                    tables_status[table_type] = {
                        'name': table_name,
                        'status': status
                    }
                    if status == 'ACTIVE':
                        healthy_tables += 1
                except Exception as e:
                    tables_status[table_type] = {
                        'name': table_name,
                        'status': 'ERROR',
                        'error': str(e)
                    }
        
        return {
            'status': 'healthy' if healthy_tables == total_tables else 'unhealthy',
            'tables': tables_status,
            'summary': f'{healthy_tables}/{total_tables} tables healthy'
        }
        
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }

def check_rds() -> Dict[str, Any]:
    """Check RDS connectivity"""
    try:
        legacy_db_host = os.environ.get('LEGACY_DB_HOST')
        if not legacy_db_host:
            return {
                'status': 'healthy',
                'message': 'RDS not configured (optional)',
                'configured': False
            }
        
        # Try to describe DB instances to check connectivity
        response = rds_client.describe_db_instances()
        
        # Find the instance with matching endpoint
        db_instance = None
        for instance in response.get('DBInstances', []):
            if legacy_db_host in instance.get('Endpoint', {}).get('Address', ''):
                db_instance = instance
                break
        
        if db_instance:
            return {
                'status': 'healthy' if db_instance['DBInstanceStatus'] == 'available' else 'unhealthy',
                'instance_status': db_instance['DBInstanceStatus'],
                'engine': db_instance['Engine'],
                'configured': True
            }
        else:
            return {
                'status': 'unhealthy',
                'message': 'RDS instance not found',
                'configured': True
            }
            
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'configured': True
        }
