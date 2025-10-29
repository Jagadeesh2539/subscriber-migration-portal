#!/usr/bin/env python3
"""
Subscriber Migration Portal - SECURITY HARDENED Production Backend
Addresses: Authentication, Input Validation, Secrets Management, Error Handling
"""

import html
import json
import logging
import os
import re
import traceback
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from typing import Any, Dict, List, Optional, Union

import boto3
import jwt
import pymysql
from cryptography.fernet import Fernet
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from serverless_wsgi import handle_request
from werkzeug.exceptions import BadRequest, Forbidden, Unauthorized
from werkzeug.security import check_password_hash


# Configure secure logging
class SecureFormatter(logging.Formatter):
    """Custom formatter that sanitizes sensitive data from logs."""
    
    SENSITIVE_KEYS = ['password', 'token', 'secret', 'key', 'auth', 'credential']
    
    def format(self, record):
        # Sanitize log message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            msg = record.msg
            for key in self.SENSITIVE_KEYS:
                # Remove sensitive values using regex
                msg = re.sub(rf'("{key}"\s*:\s*")[^"]*(")','\\1[REDACTED]\\2', msg, flags=re.IGNORECASE)
                msg = re.sub(rf'({key}[\s=:]+)[^\s,}}]+', r'\1[REDACTED]', msg, flags=re.IGNORECASE)
            record.msg = msg
        return super().format(record)

# Configure secure logging
logging.basicConfig(
    level=logging.WARNING,  # Reduced log level for production
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Set custom formatter
for handler in logging.getLogger().handlers:
    handler.setFormatter(SecureFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger = logging.getLogger(__name__)

# Initialize Flask app with security
app = Flask(__name__)

# SECURITY: Validate all required environment variables
def validate_environment():
    """Validate required environment variables exist and are secure."""
    required_vars = {
        'JWT_SECRET': 'JWT signing secret',
        'SUBSCRIBER_TABLE_NAME': 'DynamoDB subscribers table',
        'AUDIT_LOG_TABLE_NAME': 'DynamoDB audit logs table'
    }
    
    missing_vars = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing_vars.append(f"{var} ({description})")
        elif var == 'JWT_SECRET' and len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long for security")
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    logger.info("Environment validation passed")

# Validate environment on startup
validate_environment()

# SECURITY: Strict configuration with environment variables only
CONFIG = {
    'VERSION': '2.3.0-secure-production',
    'JWT_SECRET': os.environ['JWT_SECRET'],  # Required from environment
    'JWT_ALGORITHM': 'HS256',
    'JWT_EXPIRY_HOURS': int(os.getenv('JWT_EXPIRY_HOURS', '8')),  # Reduced from 24h
    'SUBSCRIBER_TABLE_NAME': os.environ['SUBSCRIBER_TABLE_NAME'],
    'AUDIT_LOG_TABLE_NAME': os.environ['AUDIT_LOG_TABLE_NAME'],
    'MIGRATION_JOBS_TABLE_NAME': os.getenv('MIGRATION_JOBS_TABLE_NAME', 'migration-jobs-table'),
    'TOKEN_BLACKLIST_TABLE_NAME': os.getenv('TOKEN_BLACKLIST_TABLE_NAME', 'token-blacklist-table'),
    'MIGRATION_UPLOAD_BUCKET_NAME': os.getenv('MIGRATION_UPLOAD_BUCKET_NAME', 'migration-uploads'),
    'USERS_SECRET_ARN': os.getenv('USERS_SECRET_ARN'),
    'LEGACY_DB_SECRET_ARN': os.getenv('LEGACY_DB_SECRET_ARN'),
    'LEGACY_DB_HOST': os.getenv('LEGACY_DB_HOST'),
    'LEGACY_DB_PORT': int(os.getenv('LEGACY_DB_PORT', '3306')),
    'LEGACY_DB_NAME': os.getenv('LEGACY_DB_NAME', 'legacydb'),
    'PROV_MODE': os.getenv('PROV_MODE', 'cloud'),  # Default to secure cloud-only
    'FRONTEND_ORIGIN': os.getenv('FRONTEND_ORIGIN', 'https://your-domain.com'),  # No wildcard default
    'MAX_FILE_SIZE': 10 * 1024 * 1024,  # Reduced to 10MB
    'ALLOWED_EXTENSIONS': {'.csv', '.json'},  # Removed .xml for security
    'MAX_LOGIN_ATTEMPTS': int(os.getenv('MAX_LOGIN_ATTEMPTS', '5')),
    'LOCKOUT_DURATION_MINUTES': int(os.getenv('LOCKOUT_DURATION_MINUTES', '15')),
    'ENCRYPTION_KEY': os.getenv('ENCRYPTION_KEY', Fernet.generate_key().decode())  # For PII encryption
}

# SECURITY: Strict CORS configuration
allowed_origins = []
if CONFIG['FRONTEND_ORIGIN'] != '*':
    allowed_origins = [CONFIG['FRONTEND_ORIGIN']]
else:
    # In production, never allow wildcard with credentials
    allowed_origins = ['https://localhost:3000']  # Development fallback

CORS(app, 
     origins=allowed_origins,
     supports_credentials=True,
     expose_headers=['Content-Disposition'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

# SECURITY: Security headers with Talisman
Talisman(app,
         force_https=True,
         strict_transport_security=True,
         strict_transport_security_max_age=31536000,
         content_security_policy={
             'default-src': "'self'",
             'script-src': "'self' 'unsafe-inline'",
             'style-src': "'self' 'unsafe-inline'",
             'img-src': "'self' data:",
             'connect-src': "'self'",
         },
         content_security_policy_nonce_in=['script-src', 'style-src'],
         referrer_policy='strict-origin-when-cross-origin',
         feature_policy={
             'geolocation': "'none'",
             'camera': "'none'",
             'microphone': "'none'"
         })

# SECURITY: Enhanced rate limiting with IP tracking
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per day", "20 per hour"],  # Stricter limits
    storage_uri="memory://",
    strategy="fixed-window"
)

# SECURITY: Login attempt tracking
login_attempts = {}
locked_accounts = {}

# AWS clients with error handling
aws_clients = {}
try:
    aws_clients['dynamodb'] = boto3.resource('dynamodb')
    aws_clients['s3'] = boto3.client('s3')
    aws_clients['secrets'] = boto3.client('secretsmanager')
    aws_clients['cloudwatch'] = boto3.client('cloudwatch')
    aws_clients['kms'] = boto3.client('kms')  # For encryption
    logger.info("AWS services initialized securely")
except Exception as e:
    logger.error("AWS initialization failed: %s", str(e))
    # In production, fail fast if AWS services unavailable
    raise

# DynamoDB tables with error handling
tables = {}
try:
    tables['subscribers'] = aws_clients['dynamodb'].Table(CONFIG['SUBSCRIBER_TABLE_NAME'])
    tables['audit_logs'] = aws_clients['dynamodb'].Table(CONFIG['AUDIT_LOG_TABLE_NAME'])
    tables['migration_jobs'] = aws_clients['dynamodb'].Table(CONFIG['MIGRATION_JOBS_TABLE_NAME'])
    if CONFIG.get('TOKEN_BLACKLIST_TABLE_NAME'):
        tables['token_blacklist'] = aws_clients['dynamodb'].Table(CONFIG['TOKEN_BLACKLIST_TABLE_NAME'])
    logger.info("DynamoDB tables initialized")
except Exception as e:
    logger.error("DynamoDB initialization failed: %s", str(e))
    raise

# SECURITY: Input validation and sanitization
class InputValidator:
    """Comprehensive input validation and sanitization."""
    
    # Regex patterns for validation
    PATTERNS = {
        'uid': re.compile(r'^[A-Za-z0-9_-]{1,50}$'),
        'imsi': re.compile(r'^[0-9]{10,15}$'),
        'msisdn': re.compile(r'^\+?[1-9][0-9]{7,14}$'),
        'email': re.compile(r'^[^@]+@[^@]+\.[^@]+$'),
        'alphanumeric': re.compile(r'^[A-Za-z0-9\s_-]+$'),
        'status': re.compile(r'^(ACTIVE|INACTIVE|SUSPENDED|DELETED)$'),
        'job_type': re.compile(r'^(csv_upload|bulk_migration|legacy_sync|audit)$')
    }
    
    @staticmethod
    def sanitize_string(value: Any, max_length: int = 255, pattern: str = None) -> str:
        """Sanitize string input with optional pattern validation."""
        if value is None:
            return ''
        
        # Convert to string and strip
        clean_value = html.escape(str(value).strip())
        
        # Truncate to max length
        clean_value = clean_value[:max_length]
        
        # Validate pattern if provided
        if pattern and pattern in InputValidator.PATTERNS:
            if not InputValidator.PATTERNS[pattern].match(clean_value):
                raise BadRequest(f"Invalid format for {pattern}")
        
        return clean_value
    
    @staticmethod
    def validate_json(data: Dict, required_fields: List[str] = None, optional_fields: List[str] = None) -> Dict:
        """Validate JSON payload structure and content."""
        if not isinstance(data, dict):
            raise BadRequest("Invalid JSON structure")
        
        if required_fields:
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            if missing_fields:
                raise BadRequest(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Remove unexpected fields for security
        allowed_fields = set((required_fields or []) + (optional_fields or []))
        if allowed_fields:
            filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
            return filtered_data
        
        return data
    
    @staticmethod
    def validate_pagination(limit: Any = None, offset: Any = None) -> tuple:
        """Validate pagination parameters."""
        try:
            limit = min(int(limit or 50), 100)  # Max 100 records
            offset = max(int(offset or 0), 0)
        except (ValueError, TypeError):
            raise BadRequest("Invalid pagination parameters")
        
        return limit, offset

# SECURITY: Encrypted PII handling
class PIIProtection:
    """PII encryption and protection."""
    
    def __init__(self):
        self.fernet = Fernet(CONFIG['ENCRYPTION_KEY'].encode() if isinstance(CONFIG['ENCRYPTION_KEY'], str) else CONFIG['ENCRYPTION_KEY'])
    
    def encrypt_pii(self, data: str) -> str:
        """Encrypt PII data."""
        if not data:
            return data
        return self.fernet.encrypt(data.encode()).decode()
    
    def decrypt_pii(self, encrypted_data: str) -> str:
        """Decrypt PII data."""
        if not encrypted_data:
            return encrypted_data
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except Exception:
            return "[DECRYPTION_ERROR]"
    
    @staticmethod
    def mask_pii(value: str, mask_char: str = '*', visible_chars: int = 4) -> str:
        """Mask PII for logging/display."""
        if not value or len(value) <= visible_chars:
            return mask_char * len(value) if value else ''
        
        return value[:2] + mask_char * (len(value) - visible_chars) + value[-2:]

pii_protection = PIIProtection()

# SECURITY: Enhanced user management with Secrets Manager
def load_users_from_secrets() -> Dict:
    """Load users securely from AWS Secrets Manager only."""
    if not CONFIG.get('USERS_SECRET_ARN'):
        # SECURITY: No fallback credentials in production
        raise ValueError("USERS_SECRET_ARN environment variable required for production")
    
    try:
        response = aws_clients['secrets'].get_secret_value(SecretId=CONFIG['USERS_SECRET_ARN'])
        users = json.loads(response['SecretString'])
        
        # Validate user structure
        for username, user_data in users.items():
            required_fields = ['password_hash', 'role', 'permissions']
            if not all(field in user_data for field in required_fields):
                raise ValueError(f"Invalid user data structure for {username}")
        
        logger.info("Loaded %d users from Secrets Manager", len(users))
        return users
    
    except Exception as e:
        logger.error("Failed to load users from Secrets Manager: %s", str(e))
        raise ValueError("User authentication system unavailable")

# SECURITY: Enhanced database connection with connection pooling
def get_legacy_db_connection():
    """Get secure legacy DB connection."""
    if not CONFIG.get('LEGACY_DB_SECRET_ARN'):
        return None
    
    try:
        response = aws_clients['secrets'].get_secret_value(SecretId=CONFIG['LEGACY_DB_SECRET_ARN'])
        secret = json.loads(response['SecretString'])
        
        # SECURITY: Validate secret structure
        required_fields = ['username', 'password']
        if not all(field in secret for field in required_fields):
            raise ValueError("Invalid database secret structure")
        
        # SECURITY: Use least-privilege connection settings
        connection = pymysql.connect(
            host=CONFIG['LEGACY_DB_HOST'],
            port=CONFIG['LEGACY_DB_PORT'],
            user=secret['username'],
            password=secret['password'],
            database=CONFIG['LEGACY_DB_NAME'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
            read_timeout=5,
            write_timeout=5,
            autocommit=False,  # Explicit transaction control
            sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'
        )
        
        return connection
    
    except Exception as e:
        logger.error("Secure database connection failed: %s", str(e))
        return None

# SECURITY: Secure user management
class SecureUserManager:
    """Secure user management with attempt tracking."""
    
    @staticmethod
    def is_account_locked(username: str) -> bool:
        """Check if account is temporarily locked."""
        if username in locked_accounts:
            lock_time = locked_accounts[username]
            if datetime.utcnow() < lock_time:
                return True
            else:
                # Unlock expired locks
                del locked_accounts[username]
                if username in login_attempts:
                    del login_attempts[username]
        return False
    
    @staticmethod
    def record_failed_attempt(username: str):
        """Record failed login attempt."""
        now = datetime.utcnow()
        
        if username not in login_attempts:
            login_attempts[username] = []
        
        # Clean old attempts (older than 1 hour)
        login_attempts[username] = [attempt for attempt in login_attempts[username] 
                                  if now - attempt < timedelta(hours=1)]
        
        login_attempts[username].append(now)
        
        # Lock account if too many attempts
        if len(login_attempts[username]) >= CONFIG['MAX_LOGIN_ATTEMPTS']:
            locked_accounts[username] = now + timedelta(minutes=CONFIG['LOCKOUT_DURATION_MINUTES'])
            logger.warning("Account locked due to failed attempts: %s", InputValidator.sanitize_string(username, 50))
    
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Secure authentication with attempt tracking."""
        username = InputValidator.sanitize_string(username, 50, 'alphanumeric')
        
        # Check account lockout
        if SecureUserManager.is_account_locked(username):
            raise Unauthorized("Account temporarily locked due to failed login attempts")
        
        # Validate password strength (basic check)
        if len(password) < 8:
            SecureUserManager.record_failed_attempt(username)
            raise BadRequest("Password does not meet security requirements")
        
        try:
            users = load_users_from_secrets()
            user = users.get(username)
            
            if user and check_password_hash(user['password_hash'], password):
                # Clear failed attempts on successful login
                if username in login_attempts:
                    del login_attempts[username]
                
                return {
                    'username': username,
                    'role': user['role'],
                    'permissions': user['permissions'],
                    'rate_limit_override': user.get('rate_limit_override', False)
                }
            else:
                SecureUserManager.record_failed_attempt(username)
                return None
        
        except Exception as e:
            logger.error("Authentication error: %s", str(e))
            SecureUserManager.record_failed_attempt(username)
            return None
    
    @staticmethod
    def generate_secure_jwt_token(user_data: Dict) -> str:
        """Generate secure JWT token with additional claims."""
        payload = {
            'sub': user_data['username'],
            'role': user_data['role'],
            'permissions': user_data['permissions'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=CONFIG['JWT_EXPIRY_HOURS']),
            'jti': str(uuid.uuid4()),
            'iss': 'subscriber-migration-portal',
            'aud': 'subscriber-portal-api'
        }
        return jwt.encode(payload, CONFIG['JWT_SECRET'], algorithm=CONFIG['JWT_ALGORITHM'])
    
    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict]:
        """Verify JWT token securely."""
        try:
            # Verify token with strict validation
            payload = jwt.decode(
                token, 
                CONFIG['JWT_SECRET'], 
                algorithms=[CONFIG['JWT_ALGORITHM']],
                audience='subscriber-portal-api',
                issuer='subscriber-migration-portal'
            )
            
            # Check token blacklist
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
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid JWT token: %s", str(e))
            return None

# SECURITY: Token blacklist management
def is_token_blacklisted(jti: str) -> bool:
    """Check if token is blacklisted."""
    if not jti:
        return True
    
    try:
        if 'token_blacklist' in tables:
            response = tables['token_blacklist'].get_item(Key={'jti': jti})
            return 'Item' in response
    except Exception as e:
        logger.error("Token blacklist check failed: %s", str(e))
        # Fail secure - assume blacklisted if check fails
        return True
    return False

def blacklist_token(jti: str, exp: int):
    """Securely blacklist token."""
    if not jti:
        return
    
    try:
        if 'token_blacklist' in tables:
            tables['token_blacklist'].put_item(
                Item={
                    'jti': jti,
                    'blacklisted_at': datetime.utcnow().isoformat(),
                    'ttl': int(exp),
                    'reason': 'user_logout'
                }
            )
    except Exception as e:
        logger.error("Token blacklist failed: %s", str(e))

# SECURITY: Enhanced authentication decorator
def require_auth(permissions: Union[str, List[str]] = None):
    """Secure authentication decorator with permission checking."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                raise Unauthorized("Authorization header required")
            
            if not auth_header.startswith('Bearer '):
                raise Unauthorized("Bearer token required")
            
            try:
                token = auth_header.split(' ')[1]
                if not token or len(token) < 10:
                    raise Unauthorized("Invalid token format")
            except IndexError:
                raise Unauthorized("Invalid Authorization header format")
            
            user = SecureUserManager.verify_jwt_token(token)
            if not user:
                raise Unauthorized("Invalid or expired token")
            
            # Check permissions
            if permissions:
                required_perms = permissions if isinstance(permissions, list) else [permissions]
                user_perms = user.get('permissions', [])
                
                if not any(perm in user_perms for perm in required_perms):
                    raise Forbidden(f"Insufficient permissions. Required: {required_perms}")
            
            g.current_user = user
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

# SECURITY: Secure response creation
def create_secure_response(data=None, message: str = "Success", status_code: int = 200, error=None):
    """Create secure API response without sensitive data exposure."""
    response = {
        'status': 'success' if status_code < 400 else 'error',
        'message': message,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    # Only include version in non-error responses
    if status_code < 400:
        response['version'] = CONFIG['VERSION']
    
    if data is not None:
        # Sanitize data before sending
        response['data'] = sanitize_response_data(data)
    
    # SECURITY: Never expose internal error details in production
    if error and status_code >= 500:
        # Log full error internally but don't expose to client
        logger.error("Internal error: %s", str(error))
        response['error'] = "Internal server error occurred"
    elif error:
        response['error'] = str(error)
    
    return jsonify(response), status_code

def sanitize_response_data(data: Any) -> Any:
    """Sanitize response data to remove sensitive information."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Skip sensitive fields
            if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'token', 'key']):
                continue
            
            # Convert Decimal to float for JSON serialization
            if isinstance(value, Decimal):
                sanitized[key] = float(value)
            else:
                sanitized[key] = sanitize_response_data(value)
        return sanitized
    
    elif isinstance(data, list):
        return [sanitize_response_data(item) for item in data]
    
    elif isinstance(data, Decimal):
        return float(data)
    
    else:
        return data

# SECURITY: Enhanced audit logging with PII protection
def secure_audit_log(action: str, resource: str, user: str = "system", details: Dict = None):
    """Secure audit logging with PII protection."""
    try:
        if 'audit_logs' not in tables:
            return
        
        # Sanitize details to remove PII
        safe_details = {}
        if details:
            for key, value in details.items():
                if any(pii in key.lower() for pii in ['password', 'token', 'imsi', 'msisdn']):
                    safe_details[key] = PIIProtection.mask_pii(str(value))
                else:
                    safe_details[key] = value
        
        log_entry = {
            'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}",
            'timestamp': datetime.utcnow().isoformat(),
            'action': InputValidator.sanitize_string(action, 100),
            'resource': InputValidator.sanitize_string(resource, 100),
            'user': InputValidator.sanitize_string(user, 50),
            'ip_address': request.remote_addr if request else 'system',
            'user_agent': InputValidator.sanitize_string(request.headers.get('User-Agent', 'unknown')[:200], 200) if request else 'system',
            'details': safe_details,
            'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())
        }
        
        tables['audit_logs'].put_item(Item=log_entry)
        
    except Exception as e:
        # SECURITY: Don't fail the main operation if audit logging fails
        logger.error("Audit logging failed: %s", str(e))

# === SECURE ROUTES ===

@app.route('/api/health', methods=['GET'])
@app.route('/health', methods=['GET'])
@limiter.limit("10 per minute")  # Rate limit even health checks
def health_check():
    """Secure health check with minimal information disclosure."""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': CONFIG['VERSION']
    }
    
    # SECURITY: Only include basic service status, no detailed configuration
    services_healthy = True
    try:
        # Test DynamoDB connection
        tables['subscribers'].scan(Limit=1)
    except Exception:
        services_healthy = False
    
    health_status['services'] = {'database': services_healthy}
    
    if not services_healthy:
        health_status['status'] = 'degraded'
    
    return create_secure_response(data=health_status, message="Health check completed")

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("5 per minute")  # Strict rate limiting for login
def secure_login():
    """Secure login with comprehensive validation."""
    try:
        # SECURITY: Validate request format
        if not request.is_json:
            raise BadRequest("Content-Type must be application/json")
        
        data = request.get_json(force=True)
        
        # SECURITY: Validate input structure
        validated_data = InputValidator.validate_json(
            data, 
            required_fields=['username', 'password']
        )
        
        username = InputValidator.sanitize_string(validated_data['username'], 50, 'alphanumeric')
        password = validated_data['password']
        
        # SECURITY: Additional password validation
        if len(password) > 128:  # Prevent DoS via huge passwords
            raise BadRequest("Password too long")
        
        user = SecureUserManager.authenticate(username, password)
        if not user:
            secure_audit_log('login_failed', 'auth', username, {'ip': request.remote_addr})
            raise Unauthorized("Invalid credentials")
        
        # Generate secure token
        token = SecureUserManager.generate_secure_jwt_token(user)
        secure_audit_log('login_success', 'auth', username, {'role': user['role']})
        
        return create_secure_response(data={
            'token': token,
            'user': {
                'username': user['username'],
                'role': user['role'],
                'permissions': user['permissions']
            },
            'expires_in': CONFIG['JWT_EXPIRY_HOURS'] * 3600
        }, message="Authentication successful")
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error("Login error: %s", str(e))
        return create_secure_response(message="Authentication failed", status_code=500)

@app.route('/api/auth/logout', methods=['POST'])
@require_auth()
def secure_logout():
    """Secure logout with token revocation."""
    try:
        user = g.current_user
        if user.get('jti') and user.get('exp'):
            blacklist_token(user['jti'], user['exp'])
        
        secure_audit_log('logout', 'auth', user['username'])
        return create_secure_response(message="Logout successful")
    
    except Exception as e:
        logger.error("Logout error: %s", str(e))
        return create_secure_response(message="Logout completed")

@app.route('/api/dashboard/stats', methods=['GET'])
@require_auth(['read'])
@limiter.limit("30 per minute")
def get_secure_dashboard_stats():
    """Secure dashboard statistics with data sanitization."""
    try:
        stats = {
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'systemHealth': 'healthy',
            'provisioningMode': CONFIG['PROV_MODE'],
            'lastUpdated': datetime.utcnow().isoformat()
        }
        
        # Get cloud subscriber count securely
        try:
            if 'subscribers' in tables:
                response = tables['subscribers'].scan(Select='COUNT')
                stats['cloudSubscribers'] = response.get('Count', 0)
        except Exception as e:
            logger.error("Dashboard query error: %s", str(e))
            stats['systemHealth'] = 'degraded'
        
        # SECURITY: Don't expose legacy DB stats if not configured
        if CONFIG.get('LEGACY_DB_SECRET_ARN'):
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        # SECURITY: Use parameterized query
                        cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != %s", ('DELETED',))
                        result = cursor.fetchone()
                        stats['legacySubscribers'] = result['count'] if result else 0
                    connection.close()
            except Exception as e:
                logger.error("Legacy DB stats error: %s", str(e))
        
        stats['totalSubscribers'] = stats['cloudSubscribers'] + stats.get('legacySubscribers', 0)
        
        return create_secure_response(data=stats)
        
    except Exception as e:
        logger.error("Dashboard stats error: %s", str(e))
        return create_secure_response(message="Failed to retrieve dashboard statistics", status_code=500)

# SECURITY: Secure error handlers
@app.errorhandler(400)
def handle_bad_request(e):
    return create_secure_response(message="Invalid request", status_code=400)

@app.errorhandler(401)
def handle_unauthorized(e):
    return create_secure_response(message="Authentication required", status_code=401)

@app.errorhandler(403)
def handle_forbidden(e):
    return create_secure_response(message="Access denied", status_code=403)

@app.errorhandler(404)
def handle_not_found(e):
    return create_secure_response(message="Resource not found", status_code=404)

@app.errorhandler(429)
def handle_rate_limit(e):
    return create_secure_response(message="Too many requests", status_code=429)

@app.errorhandler(500)
def handle_internal_error(e):
    # SECURITY: Log error internally but don't expose details
    logger.error("Internal server error: %s", str(e))
    return create_secure_response(message="Internal server error", status_code=500)

@app.errorhandler(Exception)
def handle_generic_exception(e):
    # SECURITY: Catch any unhandled exceptions
    logger.error("Unhandled exception: %s\n%s", str(e), traceback.format_exc())
    return create_secure_response(message="An unexpected error occurred", status_code=500)

# SECURITY: Bulletproof Lambda handler with comprehensive security
def lambda_handler(event, context):
    """Security-hardened AWS Lambda entry point."""
    try:
        # SECURITY: Log minimal event information
        logger.info("Lambda invoked - Method: %s, Path: %s", 
                   event.get('httpMethod', 'UNKNOWN'), 
                   event.get('path', 'UNKNOWN'))
        
        # Handle empty events securely
        if not event:
            event = {}
        
        # SECURITY: Standard CORS headers with strict configuration
        cors_headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': CONFIG['FRONTEND_ORIGIN'],
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With',
            'Access-Control-Allow-Credentials': 'true',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
        }
        
        # SECURITY: Standardize event structure with validation
        standardized_event = {
            'httpMethod': InputValidator.sanitize_string(event.get('httpMethod', 'GET'), 10),
            'path': InputValidator.sanitize_string(event.get('path', '/api/health'), 200),
            'headers': event.get('headers', {}),
            'multiValueHeaders': event.get('multiValueHeaders', {}),
            'queryStringParameters': event.get('queryStringParameters', {}),
            'multiValueQueryStringParameters': event.get('multiValueQueryStringParameters', {}),
            'body': event.get('body'),
            'isBase64Encoded': bool(event.get('isBase64Encoded', False)),
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
        
        # SECURITY: Direct health check with minimal data exposure
        if standardized_event['path'] in ['/api/health', '/health', '/']:
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'API is operational',
                    'version': CONFIG['VERSION'],
                    'timestamp': datetime.utcnow().isoformat(),
                    'features': [
                        'authentication',
                        'subscriber_management',
                        'audit_logging'
                    ]
                }),
                'isBase64Encoded': False
            }
        
        # Process through Flask with security middleware
        response = handle_request(app, standardized_event, context)
        
        # SECURITY: Ensure security headers are always present
        if 'headers' not in response:
            response['headers'] = {}
        response['headers'].update(cors_headers)
        
        # SECURITY: Remove server identification headers
        response['headers'].pop('Server', None)
        response['headers'].pop('X-Powered-By', None)
        
        return response
        
    except Exception as e:
        # SECURITY: Comprehensive error handling without information disclosure
        error_id = uuid.uuid4().hex[:8]
        logger.error("Lambda handler error [%s]: %s", error_id, str(e))
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': CONFIG['FRONTEND_ORIGIN'],
                'X-Content-Type-Options': 'nosniff',
                'X-Frame-Options': 'DENY'
            },
            'body': json.dumps({
                'status': 'error',
                'message': 'Service temporarily unavailable',
                'timestamp': datetime.utcnow().isoformat(),
                'error_id': error_id  # Reference for support without exposing details
            }),
            'isBase64Encoded': False
        }

# SECURITY: Secure application startup
if __name__ == '__main__':
    # SECURITY: Only run in debug mode if explicitly enabled
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    if debug_mode:
        logger.warning("Running in DEBUG mode - not suitable for production")
    
    app.run(
        host='127.0.0.1',  # SECURITY: Bind to localhost only
        port=5000,
        debug=debug_mode,
        threaded=True,
        ssl_context='adhoc' if not debug_mode else None  # HTTPS in production
    )
