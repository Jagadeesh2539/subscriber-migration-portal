#!/usr/bin/env python3
import json
import os
from datetime import datetime, timedelta
import hashlib
import hmac
import base64
import time

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response, InputValidator

# JWT implementation (simple, for production consider using a proper JWT library)
def create_jwt_token(payload, secret, expiry_hours=24):
    """Create a simple JWT token"""
    try:
        # Header
        header = {
            "alg": "HS256",
            "typ": "JWT"
        }
        
        # Payload with expiry
        now = datetime.utcnow()
        jwt_payload = {
            **payload,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=expiry_hours)).timestamp()),
            "iss": "subscriber-migration-portal"
        }
        
        # Encode header and payload
        header_encoded = base64.urlsafe_b64encode(
            json.dumps(header).encode('utf-8')
        ).decode('utf-8').rstrip('=')
        
        payload_encoded = base64.urlsafe_b64encode(
            json.dumps(jwt_payload).encode('utf-8')
        ).decode('utf-8').rstrip('=')
        
        # Create signature
        message = f"{header_encoded}.{payload_encoded}"
        signature = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        signature_encoded = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')
        
        return f"{header_encoded}.{payload_encoded}.{signature_encoded}"
    
    except Exception as e:
        print(f"JWT creation failed: {e}")
        return None


def hash_password(password, salt=None):
    """Hash password with salt"""
    if salt is None:
        salt = os.urandom(32)
    elif isinstance(salt, str):
        salt = salt.encode('utf-8')
    
    # Use PBKDF2 for password hashing
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    
    return {
        'hash': base64.b64encode(password_hash).decode('utf-8'),
        'salt': base64.b64encode(salt).decode('utf-8')
    }


def verify_password(password, stored_hash, stored_salt):
    """Verify password against stored hash"""
    try:
        salt = base64.b64decode(stored_salt.encode('utf-8'))
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        computed_hash = base64.b64encode(password_hash).decode('utf-8')
        
        return hmac.compare_digest(computed_hash, stored_hash)
    except Exception as e:
        print(f"Password verification failed: {e}")
        return False


def lambda_handler(event, context):
    """Authentication handler for login and token validation"""
    method = event.get('httpMethod', 'GET')
    headers = event.get('headers', {})
    origin = headers.get('origin')
    path = event.get('resource', event.get('path', ''))
    
    # Handle CORS preflight
    if method == 'OPTIONS':
        return create_response(200, {'message': 'CORS preflight handled'}, origin=origin)
    
    try:
        if '/auth/login' in path and method == 'POST':
            return handle_login(event, origin)
        elif '/auth/verify' in path and method == 'POST':
            return handle_verify_token(event, origin)
        elif '/auth/refresh' in path and method == 'POST':
            return handle_refresh_token(event, origin)
        else:
            return create_error_response(404, 'Endpoint not found', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Authentication service error: {str(e)}', origin=origin)


def handle_login(event, origin=None):
    """Handle user login with username/password"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        # Validate input
        validator = InputValidator()
        validator.require('username', body.get('username'))
        validator.require('password', body.get('password'))
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        username = body['username'].strip()
        password = body['password']
        
        # For now, use hardcoded admin credentials
        # In production, these should be stored securely (DynamoDB, Secrets Manager)
        admin_users = {
            'admin': {
                'password_hash': 'qvMvCy7rCGSbQEPeP+Qr0VFNAjfPnVcPYzKnSjw+bpE=',  # SecureAdmin123!
                'salt': 'U2VjdXJlU2FsdEZvckFkbWluVXNlcjEyMyE=',
                'role': 'admin',
                'permissions': ['read', 'write', 'admin']
            }
        }
        
        if username not in admin_users:
            # Add delay to prevent timing attacks
            time.sleep(0.5)
            return create_error_response(401, 'Invalid credentials', origin=origin)
        
        user_data = admin_users[username]
        
        if not verify_password(password, user_data['password_hash'], user_data['salt']):
            # Add delay to prevent timing attacks
            time.sleep(0.5)
            return create_error_response(401, 'Invalid credentials', origin=origin)
        
        # Generate JWT token
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            return create_error_response(500, 'JWT secret not configured', origin=origin)
        
        token_payload = {
            'username': username,
            'role': user_data['role'],
            'permissions': user_data['permissions']
        }
        
        token = create_jwt_token(token_payload, jwt_secret, expiry_hours=24)
        
        if not token:
            return create_error_response(500, 'Token generation failed', origin=origin)
        
        return create_response(200, {
            'token': token,
            'user': {
                'username': username,
                'role': user_data['role'],
                'permissions': user_data['permissions']
            },
            'expiresIn': 24 * 3600,  # 24 hours in seconds
            'message': 'Login successful'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Login failed: {str(e)}', origin=origin)


def handle_verify_token(event, origin=None):
    """Verify JWT token validity"""
    try:
        body = json.loads(event.get('body', '{}'))
        token = body.get('token', '')
        
        if not token:
            return create_error_response(400, 'Token is required', origin=origin)
        
        # Simple token validation (in production, use proper JWT validation)
        try:
            header, payload, signature = token.split('.')
            
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            
            decoded_payload = base64.urlsafe_b64decode(payload)
            token_data = json.loads(decoded_payload)
            
            # Check expiry
            exp = token_data.get('exp', 0)
            if exp < int(datetime.utcnow().timestamp()):
                return create_error_response(401, 'Token expired', origin=origin)
            
            return create_response(200, {
                'valid': True,
                'user': {
                    'username': token_data.get('username'),
                    'role': token_data.get('role'),
                    'permissions': token_data.get('permissions')
                },
                'expiresAt': datetime.fromtimestamp(exp).isoformat()
            }, origin=origin)
        
        except Exception as e:
            return create_error_response(401, 'Invalid token', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Token verification failed: {str(e)}', origin=origin)


def handle_refresh_token(event, origin=None):
    """Refresh JWT token"""
    try:
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization', '') or headers.get('authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return create_error_response(400, 'Bearer token required', origin=origin)
        
        old_token = auth_header[7:]
        
        try:
            header, payload, signature = old_token.split('.')
            payload += '=' * (4 - len(payload) % 4)
            decoded_payload = base64.urlsafe_b64decode(payload)
            token_data = json.loads(decoded_payload)
            
            # Check if token is close to expiry (within 1 hour)
            exp = token_data.get('exp', 0)
            now = int(datetime.utcnow().timestamp())
            
            if exp < now:
                return create_error_response(401, 'Token expired', origin=origin)
            
            if exp - now > 3600:  # More than 1 hour remaining
                return create_error_response(400, 'Token does not need refresh yet', origin=origin)
            
            # Generate new token
            jwt_secret = os.environ.get('JWT_SECRET')
            if not jwt_secret:
                return create_error_response(500, 'JWT secret not configured', origin=origin)
            
            new_payload = {
                'username': token_data.get('username'),
                'role': token_data.get('role'),
                'permissions': token_data.get('permissions')
            }
            
            new_token = create_jwt_token(new_payload, jwt_secret, expiry_hours=24)
            
            if not new_token:
                return create_error_response(500, 'Token refresh failed', origin=origin)
            
            return create_response(200, {
                'token': new_token,
                'expiresIn': 24 * 3600,
                'message': 'Token refreshed successfully'
            }, origin=origin)
        
        except Exception as e:
            return create_error_response(401, 'Invalid token for refresh', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Token refresh failed: {str(e)}', origin=origin)


# For testing password hashing
if __name__ == "__main__":
    # Generate hash for default admin password
    result = hash_password("SecureAdmin123!")
    print(f"Password hash: {result['hash']}")
    print(f"Salt: {result['salt']}")
    
    # Test verification
    is_valid = verify_password("SecureAdmin123!", result['hash'], result['salt'])
    print(f"Verification result: {is_valid}")