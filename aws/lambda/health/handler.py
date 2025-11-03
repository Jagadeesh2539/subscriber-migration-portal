#!/usr/bin/env python3
import json
import os
from datetime import datetime
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError

def create_response(status_code: int, body: Dict, origin: str = '*') -> Dict[str, Any]:
    """Helper to create responses with proper CORS headers"""
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
        'Access-Control-Allow-Credentials': 'false',
        'Access-Control-Max-Age': '600'
    }
    return {
        'statusCode': status_code,
        'headers': cors_headers,
        'body': json.dumps(body, default=str)
    }

def check_dynamodb_table(table_name: str) -> Dict[str, Any]:
    """Enhanced DynamoDB table check with status info"""
    if not table_name:
        return {'status': 'not_configured', 'table_name': None}
    
    try:
        dynamodb = boto3.client('dynamodb')
        response = dynamodb.describe_table(TableName=table_name)
        table_status = response['Table']['TableStatus']
        
        return {
            'status': 'healthy' if table_status == 'ACTIVE' else 'unhealthy',
            'table_name': table_name,
            'table_status': table_status
        }
    except ClientError as e:
        return {
            'status': 'error',
            'table_name': table_name,
            'error': e.response['Error']['Code']
        }
    except Exception as e:
        return {
            'status': 'error',
            'table_name': table_name,
            'error': str(e)
        }

def check_rds_connectivity() -> Dict[str, Any]:
    """Basic RDS connectivity check"""
    rds_host = os.environ.get('LEGACY_DB_HOST')
    if not rds_host:
        return {'status': 'not_configured', 'configured': False}
    
    try:
        # Simple RDS instance check
        rds = boto3.client('rds')
        instances = rds.describe_db_instances()
        
        # Look for instance with matching host
        for instance in instances.get('DBInstances', []):
            if rds_host in instance.get('Endpoint', {}).get('Address', ''):
                return {
                    'status': 'healthy' if instance['DBInstanceStatus'] == 'available' else 'unhealthy',
                    'configured': True,
                    'instance_status': instance['DBInstanceStatus'],
                    'engine': instance.get('Engine')
                }
        
        return {'status': 'error', 'configured': True, 'error': 'Instance not found'}
    except Exception as e:
        return {'status': 'error', 'configured': True, 'error': str(e)}

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Enhanced health check handler with comprehensive checks"""
    try:
        path = event.get('path', '/')
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers', {}) or {}
        origin = headers.get('origin') or headers.get('Origin') or '*'
        query_params = event.get('queryStringParameters') or {}
        
        print(f"Health check - Path: {path}, Method: {method}, Origin: {origin}")
        
        # Handle OPTIONS (CORS preflight)
        if method == 'OPTIONS':
            return create_response(200, {'message': 'CORS preflight successful'}, origin)
        
        # Only allow GET
        if method != 'GET':
            return create_response(405, {
                'error': 'Method Not Allowed',
                'allowed_methods': ['GET', 'OPTIONS'],
                'received_method': method
            }, origin)
        
        # Check if detailed health check is requested
        detailed = query_params.get('detailed', '').lower() == 'true'
        
        # Perform health checks
        table_checks = {
            'subscribers': check_dynamodb_table(os.environ.get('SUBSCRIBERS_TABLE')),
            'settings': check_dynamodb_table(os.environ.get('SETTINGS_TABLE')),
            'migration_jobs': check_dynamodb_table(os.environ.get('MIGRATION_JOBS_TABLE'))
        }
        
        rds_check = check_rds_connectivity()
        
        # Build response data
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'Subscriber Migration Portal',
            'version': os.environ.get('VERSION', '3.4.0'),
            'path': path,
            'function_name': context.function_name if context else 'local',
            'aws_request_id': context.aws_request_id if context else 'local-test'
        }
        
        # Add detailed checks if requested or for /status endpoint
        if detailed or path == '/status':
            health_data['checks'] = {
                'dynamodb_tables': table_checks,
                'rds': rds_check
            }
            
            # Determine overall health status
            table_healthy = all(check['status'] == 'healthy' for check in table_checks.values())
            rds_healthy = rds_check['status'] in ['healthy', 'not_configured']
            
            if not table_healthy or not rds_healthy:
                health_data['status'] = 'degraded'
        else:
            # Simple environment check for basic endpoints
            health_data['environment'] = {
                'tables_configured': sum(1 for env_var in ['SUBSCRIBERS_TABLE', 'SETTINGS_TABLE', 'MIGRATION_JOBS_TABLE'] if os.environ.get(env_var)),
                'rds_configured': bool(os.environ.get('LEGACY_DB_HOST'))
            }
        
        # Path-specific responses
        if path == '/health':
            health_data['message'] = 'Health endpoint operational'
        elif path == '/status':
            health_data['message'] = 'Status endpoint operational with detailed checks'
        elif path == '/':
            health_data['message'] = 'API Gateway root endpoint operational'
        elif path == '/ping':
            return create_response(200, {
                'pong': True,
                'timestamp': datetime.utcnow().isoformat(),
                'service': 'Subscriber Migration Portal',
                'latency_ms': round((datetime.utcnow().timestamp() * 1000)) % 1000  # Simple latency indicator
            }, origin)
        else:
            health_data['message'] = f'Endpoint operational for {path}'
        
        # Return appropriate status code
        status_code = 200 if health_data['status'] == 'healthy' else 503
        return create_response(status_code, health_data, origin)
    
    except Exception as e:
        print(f"Health check error: {str(e)}")
        import traceback
        traceback.print_exc()  # Log full stack trace for debugging
        
        error_data = {
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
            'timestamp': datetime.utcnow().isoformat(),
            'path': event.get('path', '/'),
            'service': 'Subscriber Migration Portal'
        }
        return create_response(500, error_data, '*')
