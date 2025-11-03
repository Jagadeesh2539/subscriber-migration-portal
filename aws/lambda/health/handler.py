#!/usr/bin/env python3
import json
import os
from datetime import datetime
from typing import Dict, Any

def create_cors_response(status_code: int, data: Dict, origin: str = None) -> Dict[str, Any]:
    """Create response with proper CORS headers for API Gateway"""
    
    # Always allow all origins for health endpoints
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',  # Allow all origins for health checks
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token, X-Requested-With',
        'Access-Control-Allow-Credentials': 'false',  # No credentials needed for health
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    return {
        'statusCode': status_code,
        'headers': cors_headers,
        'body': json.dumps(data, default=str, ensure_ascii=False),
        'isBase64Encoded': False
    }

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Health check endpoint handler with proper CORS"""
    
    try:
        # Get request details
        path = event.get('path', '/')
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers') or {}
        origin = headers.get('origin') or headers.get('Origin')
        
        print(f"Health check - Path: {path}, Method: {method}, Origin: {origin}")
        
        # Handle preflight OPTIONS request
        if method == 'OPTIONS':
            return create_cors_response(200, {
                'message': 'CORS preflight successful',
                'allowed_methods': ['GET', 'OPTIONS'],
                'allowed_headers': ['Content-Type', 'Authorization']
            }, origin)
        
        # Only allow GET for health checks
        if method != 'GET':
            return create_cors_response(405, {
                'error': 'Method not allowed',
                'allowed_methods': ['GET', 'OPTIONS'],
                'received_method': method
            }, origin)
        
        # Build health response
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'Subscriber Migration Portal',
            'version': '3.2.0',
            'path': path,
            'method': method,
            'origin': origin,
            'environment': {
                'subscribers_table': bool(os.environ.get('SUBSCRIBERS_TABLE')),
                'settings_table': bool(os.environ.get('SETTINGS_TABLE')),
                'migration_jobs_table': bool(os.environ.get('MIGRATION_JOBS_TABLE')),
                'legacy_db_host': bool(os.environ.get('LEGACY_DB_HOST'))
            }
        }
        
        # Add endpoint-specific messages
        if path == '/':
            health_data['message'] = 'API Gateway root endpoint operational'
        elif path == '/health':
            health_data['message'] = 'Health check endpoint operational'
        elif path == '/status':
            health_data['message'] = 'Status endpoint operational'
        elif path == '/ping':
            return create_cors_response(200, {
                'pong': True,
                'timestamp': datetime.utcnow().isoformat(),
                'message': 'Ping successful',
                'path': path
            }, origin)
        else:
            health_data['message'] = f'Health endpoint operational for {path}'
        
        print(f"Health check successful - returning 200 for {path}")
        return create_cors_response(200, health_data, origin)
        
    except Exception as e:
        print(f"Health check error: {str(e)}")
        print(f"Event: {json.dumps(event, default=str)}")
        
        error_data = {
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'Subscriber Migration Portal',
            'error': str(e),
            'error_type': type(e).__name__,
            'path': event.get('path', '/'),
            'method': event.get('httpMethod', 'GET'),
            'debug': True
        }
        
        return create_cors_response(500, error_data, event.get('headers', {}).get('origin'))
