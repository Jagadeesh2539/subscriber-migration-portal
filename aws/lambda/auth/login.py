#!/usr/bin/env python3
"""
Login Lambda Function
Handles user authentication and JWT token generation
"""

import json
import sys
import logging
from typing import Dict, Any
from werkzeug.security import check_password_hash

# Import from Lambda layer
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, parse_request_body,
    InputValidator, JWTAuth, SecretsManager, AuditLogger, 
    handle_exceptions, APIException
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Simple rate limiting (in-memory for demonstration)
# In production, use DynamoDB or Redis for distributed rate limiting
login_attempts = {}
max_attempts = 5
lockout_duration = 300  # 5 minutes

@handle_exceptions
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Handle user login
    
    Args:
        event: API Gateway event
        context: Lambda context
    
    Returns:
        API Gateway response with JWT token
    """
    
    # Parse request
    request_body = parse_request_body(event)
    origin = event.get('headers', {}).get('origin')
    
    # Extract IP for rate limiting
    client_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
    
    # Validate required fields
    try:
        InputValidator.validate_required_fields(request_body, ['username', 'password'])
    except ValueError as e:
        return create_error_response(
            status_code=400,
            message=str(e),
            error_code='VALIDATION_ERROR',
            origin=origin
        )
    
    username = InputValidator.sanitize_string(
        request_body['username'], 
        max_length=50, 
        pattern='alphanumeric'
    )
    password = request_body['password']
    
    # Basic password validation
    if len(password) < 8 or len(password) > 128:
        return create_error_response(
            status_code=400,
            message='Password must be between 8 and 128 characters',
            error_code='VALIDATION_ERROR',
            origin=origin
        )
    
    # Check rate limiting
    if is_rate_limited(client_ip):
        AuditLogger.log_activity(
            action='login_rate_limited',
            resource='auth',
            user=username,
            details={'ip': client_ip},
            event=event
        )
        
        return create_error_response(
            status_code=429,
            message='Too many login attempts. Please try again later.',
            error_code='RATE_LIMITED',
            origin=origin
        )
    
    try:
        # Get users from Secrets Manager
        users = SecretsManager.get_users()
        
        # Find user
        user_data = users.get(username)
        
        if not user_data:
            record_failed_attempt(client_ip)
            
            AuditLogger.log_activity(
                action='login_failed',
                resource='auth',
                user=username,
                details={'reason': 'user_not_found', 'ip': client_ip},
                event=event
            )
            
            return create_error_response(
                status_code=401,
                message='Invalid credentials',
                error_code='AUTHENTICATION_FAILED',
                origin=origin
            )
        
        # Verify password
        if not check_password_hash(user_data['password_hash'], password):
            record_failed_attempt(client_ip)
            
            AuditLogger.log_activity(
                action='login_failed',
                resource='auth',
                user=username,
                details={'reason': 'invalid_password', 'ip': client_ip},
                event=event
            )
            
            return create_error_response(
                status_code=401,
                message='Invalid credentials',
                error_code='AUTHENTICATION_FAILED',
                origin=origin
            )
        
        # Clear failed attempts on successful login
        clear_failed_attempts(client_ip)
        
        # Generate JWT token
        token = JWTAuth.generate_token({
            'username': username,
            'role': user_data['role'],
            'permissions': user_data['permissions']
        })
        
        # Log successful login
        AuditLogger.log_activity(
            action='login_success',
            resource='auth',
            user=username,
            details={
                'role': user_data['role'],
                'ip': client_ip,
                'user_agent': event.get('headers', {}).get('User-Agent', 'unknown')
            },
            event=event
        )
        
        # Return success response
        return create_response(
            status_code=200,
            body={
                'token': token,
                'user': {
                    'username': username,
                    'role': user_data['role'],
                    'permissions': user_data['permissions']
                },
                'expires_in': 8 * 3600,  # 8 hours in seconds
                'token_type': 'Bearer'
            },
            origin=origin
        )
        
    except Exception as e:
        logger.error(f'Login error for user {username}: {str(e)}')
        
        AuditLogger.log_activity(
            action='login_error',
            resource='auth',
            user=username,
            details={'error': str(e), 'ip': client_ip},
            event=event
        )
        
        return create_error_response(
            status_code=500,
            message='Authentication service temporarily unavailable',
            error_code='SERVICE_ERROR',
            origin=origin
        )

def is_rate_limited(client_ip: str) -> bool:
    """
    Check if client IP is rate limited
    
    Args:
        client_ip: Client IP address
    
    Returns:
        True if rate limited, False otherwise
    """
    import time
    
    current_time = time.time()
    
    if client_ip not in login_attempts:
        return False
    
    attempts = login_attempts[client_ip]
    
    # Clean old attempts
    attempts['timestamps'] = [
        timestamp for timestamp in attempts['timestamps']
        if current_time - timestamp < lockout_duration
    ]
    
    # Check if locked out
    if attempts.get('locked_until', 0) > current_time:
        return True
    
    # Check if too many attempts
    if len(attempts['timestamps']) >= max_attempts:
        attempts['locked_until'] = current_time + lockout_duration
        return True
    
    return False

def record_failed_attempt(client_ip: str):
    """
    Record failed login attempt
    
    Args:
        client_ip: Client IP address
    """
    import time
    
    current_time = time.time()
    
    if client_ip not in login_attempts:
        login_attempts[client_ip] = {
            'timestamps': [],
            'locked_until': 0
        }
    
    login_attempts[client_ip]['timestamps'].append(current_time)
    
    # Clean old attempts
    login_attempts[client_ip]['timestamps'] = [
        timestamp for timestamp in login_attempts[client_ip]['timestamps']
        if current_time - timestamp < lockout_duration
    ]

def clear_failed_attempts(client_ip: str):
    """
    Clear failed login attempts for IP
    
    Args:
        client_ip: Client IP address
    """
    if client_ip in login_attempts:
        del login_attempts[client_ip]