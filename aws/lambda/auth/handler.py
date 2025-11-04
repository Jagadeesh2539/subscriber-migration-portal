#!/usr/bin/env python3
"""
Enterprise Migration Portal - Authentication Handler
Self-contained version with embedded common utilities
Fixes: ImportModuleError: No module named 'common_utils'
"""
import json
import os
from datetime import datetime, timedelta
import hashlib
import hmac
import base64
import time

# EMBEDDED COMMON UTILS (to fix import error)
def create_response(status_code, body, origin=None):
    """Create API Gateway response with CORS headers"""
    headers = {
        'Content-Type': 'application/json'
    }
    
    # Add CORS headers
    if origin:
        headers['Access-Control-Allow-Origin'] = origin
    else:
        headers['Access-Control-Allow-Origin'] = '*'
    
    headers['Access-Control-Allow-Headers'] = 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS,PATCH'
    headers['Access-Control-Max-Age'] = '86400'
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body)
    }

def create_error_response(status_code, message, origin=None):
    """Create error response with CORS headers"""
    return create_response(status_code, {
        'error': True,
        'message': message,
        'statusCode': status_code,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }, origin)

class InputValidator:
    """Simple input validation utility"""
    def __init__(self):
        self.errors = []
    
    def require(self, field_name, value):
        if not value or (isinstance(value, str) and not value.strip()):
            self.errors.append(f"{field_name} is required")
    
    def email(self, field_name, value):
        if value and '@' not in value:
            self.errors.append(f"{field_name} must be a valid email")
    
    def get_errors(self):
        return self.errors

# JWT IMPLEMENTATION
def create_jwt_token(payload, secret, expiry_hours=24):
    """Create a simple JWT token"""
    try:
        header = {
            "alg": "HS256",
            "typ": "JWT"
        }
        
        now = datetime.utcnow()
        jwt_payload = {
            **payload,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=expiry_hours)).timestamp()),
            "iss": "subscriber-migration-portal",
            "aud": "migration-portal-users"
        }
        
        # Encode header and payload
        header_encoded = base64.urlsafe_b64encode(
            json.dumps(header, separators=(',', ':')).encode('utf-8')
        ).decode('utf-8').rstrip('=')
        
        payload_encoded = base64.urlsafe_b64encode(
            json.dumps(jwt_payload, separators=(',', ':')).encode('utf-8')
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

def verify_jwt_token(token, secret):
    """Verify JWT token signature and expiry"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
            
        header, payload, signature = parts
        
        # Verify signature
        message = f"{header}.{payload}"
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        expected_signature_encoded = base64.urlsafe_b64encode(expected_signature).decode('utf-8').rstrip('=')
        
        if not hmac.compare_digest(signature, expected_signature_encoded):
            return None
        
        # Decode payload
        payload += '=' * (4 - len(payload) % 4)
        decoded_payload = base64.urlsafe_b64decode(payload)
        token_data = json.loads(decoded_payload)
        
        # Check expiry
        exp = token_data.get('exp', 0)
        if exp < int(datetime.utcnow().timestamp()):
            return None
        
        return token_data
    
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

def hash_password(password, salt=None):
    """Hash password with salt using PBKDF2"""
    if salt is None:
        salt = os.urandom(32)
    elif isinstance(salt, str):
        salt = salt.encode('utf-8')
    
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

# MAIN LAMBDA HANDLER
def lambda_handler(event, context):
    """Authentication handler for login and token validation"""
    try:
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers', {})
        origin = headers.get('origin') or headers.get('Origin') or '*'
        path = event.get('resource', event.get('path', ''))
        
        print(f"🔑 Auth Lambda called: {method} {path} from origin: {origin}")
        
        # Handle CORS preflight
        if method == 'OPTIONS':
            print("Handling CORS preflight request")
            return create_response(200, {'message': 'CORS preflight handled'}, origin=origin)
        
        # Route to appropriate handler
        if '/auth/login' in path and method == 'POST':
            return handle_login(event, origin)
        elif '/auth/verify' in path and method == 'POST':
            return handle_verify_token(event, origin)
        elif '/auth/refresh' in path and method == 'POST':
            return handle_refresh_token(event, origin)
        else:
            print(f"Unknown auth endpoint: {method} {path}")
            return create_error_response(404, 'Authentication endpoint not found', origin=origin)
    
    except Exception as e:
        print(f"❌ Auth handler error: {str(e)}")
        return create_error_response(500, f'Authentication service error: {str(e)}', origin=origin)

def handle_login(event, origin=None):
    """Handle user login with username/password"""
    try:
        print("🔑 Processing login request")
        
        body_str = event.get('body', '{}')
        if isinstance(body_str, str):
            body = json.loads(body_str)
        else:
            body = body_str
        
        print(f"Login body received: {list(body.keys()) if body else 'empty'}")
        
        # Validate input
        validator = InputValidator()
        validator.require('username', body.get('username'))
        validator.require('password', body.get('password'))
        
        errors = validator.get_errors()
        if errors:
            print(f"Validation errors: {errors}")
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        username = body['username'].strip().lower()
        password = body['password']
        
        print(f"Login attempt for user: {username}")
        
        # Demo credentials - in production, use DynamoDB or Secrets Manager
        valid_users = {
            'admin': {
                'password': 'password',
                'role': 'admin',
                'permissions': ['read', 'write', 'admin', 'migration', 'provisioning']
            },
            'user': {
                'password': 'user123',
                'role': 'user',
                'permissions': ['read']
            }
        }
        
        if username not in valid_users or valid_users[username]['password'] != password:
            print(f"❌ Invalid credentials for user: {username}")
            time.sleep(0.5)  # Prevent timing attacks
            return create_error_response(401, 'Invalid username or password', origin=origin)
        
        # Get JWT secret from environment
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            print("❌ JWT_SECRET environment variable not set")
            return create_error_response(500, 'Authentication service misconfigured', origin=origin)
        
        print(f"JWT_SECRET length: {len(jwt_secret)}")
        
        # Create token payload
        user_data = valid_users[username]
        token_payload = {
            'username': username,
            'role': user_data['role'],
            'permissions': user_data['permissions'],
            'login_time': datetime.utcnow().isoformat()
        }
        
        # Generate JWT token
        token = create_jwt_token(token_payload, jwt_secret, expiry_hours=24)
        
        if not token:
            print("❌ Token generation failed")
            return create_error_response(500, 'Token generation failed', origin=origin)
        
        print(f"✅ Login successful for {username}, token length: {len(token)}")
        
        response_data = {
            'success': True,
            'token': token,
            'user': {
                'username': username,
                'role': user_data['role'],
                'permissions': user_data['permissions']
            },
            'expiresIn': 24 * 3600,  # 24 hours in seconds
            'expiresAt': (datetime.utcnow() + timedelta(hours=24)).isoformat() + 'Z',
            'message': 'Login successful'
        }
        
        return create_response(200, response_data, origin=origin)
    
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        return create_error_response(400, 'Invalid JSON in request body', origin=origin)
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return create_error_response(500, f'Login failed: {str(e)}', origin=origin)

def handle_verify_token(event, origin=None):
    """Verify JWT token validity"""
    try:
        print("🔍 Processing token verification request")
        
        body_str = event.get('body', '{}')
        if isinstance(body_str, str):
            body = json.loads(body_str)
        else:
            body = body_str
        
        token = body.get('token', '').strip()
        
        if not token:
            return create_error_response(400, 'Token is required', origin=origin)
        
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            return create_error_response(500, 'JWT secret not configured', origin=origin)
        
        # Verify token
        token_data = verify_jwt_token(token, jwt_secret)
        
        if not token_data:
            return create_error_response(401, 'Invalid or expired token', origin=origin)
        
        print(f"✅ Token verified for user: {token_data.get('username')}")
        
        return create_response(200, {
            'valid': True,
            'user': {
                'username': token_data.get('username'),
                'role': token_data.get('role'),
                'permissions': token_data.get('permissions')
            },
            'expiresAt': datetime.fromtimestamp(token_data.get('exp', 0)).isoformat() + 'Z'
        }, origin=origin)
    
    except Exception as e:
        print(f"❌ Token verification error: {str(e)}")
        return create_error_response(500, f'Token verification failed: {str(e)}', origin=origin)

def handle_refresh_token(event, origin=None):
    """Refresh JWT token"""
    try:
        print("🔄 Processing token refresh request")
        
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization', '') or headers.get('authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return create_error_response(400, 'Bearer token required in Authorization header', origin=origin)
        
        old_token = auth_header[7:].strip()
        
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            return create_error_response(500, 'JWT secret not configured', origin=origin)
        
        # Verify old token
        token_data = verify_jwt_token(old_token, jwt_secret)
        
        if not token_data:
            return create_error_response(401, 'Invalid token for refresh', origin=origin)
        
        # Check if token is close to expiry (within 2 hours)
        exp = token_data.get('exp', 0)
        now = int(datetime.utcnow().timestamp())
        
        if exp - now > 7200:  # More than 2 hours remaining
            return create_error_response(400, 'Token does not need refresh yet', origin=origin)
        
        # Generate new token with same payload
        new_payload = {
            'username': token_data.get('username'),
            'role': token_data.get('role'),
            'permissions': token_data.get('permissions'),
            'refresh_time': datetime.utcnow().isoformat()
        }
        
        new_token = create_jwt_token(new_payload, jwt_secret, expiry_hours=24)
        
        if not new_token:
            return create_error_response(500, 'Token refresh failed', origin=origin)
        
        print(f"✅ Token refreshed for user: {token_data.get('username')}")
        
        return create_response(200, {
            'token': new_token,
            'expiresIn': 24 * 3600,
            'expiresAt': (datetime.utcnow() + timedelta(hours=24)).isoformat() + 'Z',
            'message': 'Token refreshed successfully'
        }, origin=origin)
    
    except Exception as e:
        print(f"❌ Token refresh error: {str(e)}")
        return create_error_response(500, f'Token refresh failed: {str(e)}', origin=origin)

# UTILITY FUNCTIONS FOR PASSWORD MANAGEMENT
def hash_password(password, salt=None):
    """Hash password with salt using PBKDF2"""
    if salt is None:
        salt = os.urandom(32)
    elif isinstance(salt, str):
        salt = salt.encode('utf-8')
    
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

# For testing password hashing
if __name__ == "__main__":
    # Generate hash for default admin password
    print("🔐 Testing password hashing...")
    
    test_passwords = ['password', 'admin123', 'SecureAdmin123!']
    
    for pwd in test_passwords:
        result = hash_password(pwd)
        print(f"Password '{pwd}':")
        print(f"  Hash: {result['hash']}")
        print(f"  Salt: {result['salt']}")
        
        # Test verification
        is_valid = verify_password(pwd, result['hash'], result['salt'])
        print(f"  Verification: {'✅' if is_valid else '❌'}")
        print()
    
    # Test JWT creation
    print("🔑 Testing JWT creation...")
    test_secret = "test_secret_key_123"
    test_payload = {"username": "admin", "role": "admin"}
    
    token = create_jwt_token(test_payload, test_secret)
    if token:
        print(f"✅ JWT created: {token[:50]}...")
        
        # Test verification
        verified = verify_jwt_token(token, test_secret)
        if verified:
            print(f"✅ JWT verified: {verified}")
        else:
            print("❌ JWT verification failed")
    else:
        print("❌ JWT creation failed")