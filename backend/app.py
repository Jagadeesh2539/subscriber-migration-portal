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
from flask import Flask, g, jsonify, request, Response
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

    SENSITIVE_KEYS = ["password", "token", "secret", "key", "auth", "credential"]

    def format(self, record):
        # Sanitize log message
        if hasattr(record, "msg") and isinstance(record.msg, str):
            msg = record.msg
            for key in self.SENSITIVE_KEYS:
                # Remove sensitive values using regex
                msg = re.sub(rf'("{key}"\s*:\s*")[^"]*(")', "\\1[REDACTED]\\2", msg, flags=re.IGNORECASE)
                msg = re.sub(rf"({key}[\s=:]+)[^\s,}}]+", r"\1[REDACTED]", msg, flags=re.IGNORECASE)
            record.msg = msg
        return super().format(record)


# Configure secure logging
logging.basicConfig(
    level=logging.WARNING,  # Reduced log level for production
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# Set custom formatter
for handler in logging.getLogger().handlers:
    handler.setFormatter(SecureFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logger = logging.getLogger(__name__)

# Initialize Flask app with security
app = Flask(__name__)


# SECURITY: Validate all required environment variables
def validate_environment():
    """Validate required environment variables exist and are secure."""
    required_vars = {
        "JWT_SECRET": "JWT signing secret",
        "SUBSCRIBER_TABLE_NAME": "DynamoDB subscribers table",
        "AUDIT_LOG_TABLE_NAME": "DynamoDB audit logs table",
    }

    missing_vars = []

    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing_vars.append(f"{var} ({description})")
        elif var == "JWT_SECRET" and len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long for security")

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    logger.info("Environment validation passed")


# Validate environment on startup
validate_environment()

# SECURITY: Strict configuration with environment variables only
CONFIG = {
    "VERSION": "2.5.0-complete-migration",  # Updated version
    "JWT_SECRET": os.environ["JWT_SECRET"],  # Required from environment
    "JWT_ALGORITHM": "HS256",
    "JWT_EXPIRY_HOURS": int(os.getenv("JWT_EXPIRY_HOURS", "8")),  # Reduced from 24h
    "SUBSCRIBER_TABLE_NAME": os.environ["SUBSCRIBER_TABLE_NAME"],
    "AUDIT_LOG_TABLE_NAME": os.environ["AUDIT_LOG_TABLE_NAME"],
    "MIGRATION_JOBS_TABLE_NAME": os.getenv("MIGRATION_JOBS_TABLE_NAME", "migration-jobs-table"),
    "TOKEN_BLACKLIST_TABLE_NAME": os.getenv("TOKEN_BLACKLIST_TABLE_NAME", "token-blacklist-table"),
    "MIGRATION_UPLOAD_BUCKET_NAME": os.getenv("MIGRATION_UPLOAD_BUCKET_NAME", "migration-uploads"),
    "USERS_SECRET_ARN": os.getenv("USERS_SECRET_ARN"),
    "LEGACY_DB_SECRET_ARN": os.getenv("LEGACY_DB_SECRET_ARN"),
    "LEGACY_DB_HOST": os.getenv("LEGACY_DB_HOST"),
    "LEGACY_DB_PORT": int(os.getenv("LEGACY_DB_PORT", "3306")),
    "LEGACY_DB_NAME": os.getenv("LEGACY_DB_NAME", "legacydb"),
    "PROV_MODE": os.getenv("PROV_MODE", "cloud"),  # Default to secure cloud-only
    "FRONTEND_ORIGIN": os.getenv("FRONTEND_ORIGIN", "https://your-domain.com"),  # No wildcard default
    "MAX_FILE_SIZE": 10 * 1024 * 1024,  # Reduced to 10MB
    "ALLOWED_EXTENSIONS": {".csv", ".json"},  # Removed .xml for security
    "MAX_LOGIN_ATTEMPTS": int(os.getenv("MAX_LOGIN_ATTEMPTS", "5")),
    "LOCKOUT_DURATION_MINUTES": int(os.getenv("LOCKOUT_DURATION_MINUTES", "15")),
    "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode()),  # For PII encryption
}

# SECURITY: Strict CORS configuration
allowed_origins = []
if CONFIG["FRONTEND_ORIGIN"] != "*":
    allowed_origins = [CONFIG["FRONTEND_ORIGIN"]]
else:
    # In production, never allow wildcard with credentials
    allowed_origins = ["https://localhost:3000"]  # Development fallback

CORS(
    app,
    origins=allowed_origins,
    supports_credentials=True,
    expose_headers=["Content-Disposition"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

# SECURITY: Security headers with Talisman
Talisman(
    app,
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy={
        "default-src": "'self'",
        "script-src": "'self' 'unsafe-inline'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data:",
        "connect-src": "'self'",
    },
    content_security_policy_nonce_in=["script-src", "style-src"],
    referrer_policy="strict-origin-when-cross-origin",
    feature_policy={"geolocation": "'none'", "camera": "'none'", "microphone": "'none'"},
)

# SECURITY: Enhanced rate limiting with IP tracking
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per day", "20 per hour"],  # Stricter limits
    storage_uri="memory://",
    strategy="fixed-window",
)

# SECURITY: Login attempt tracking
login_attempts = {}
locked_accounts = {}

# AWS clients with error handling
aws_clients = {}
try:
    aws_clients["dynamodb"] = boto3.resource("dynamodb")
    aws_clients["s3"] = boto3.client("s3")
    aws_clients["secrets"] = boto3.client("secretsmanager")
    aws_clients["cloudwatch"] = boto3.client("cloudwatch")
    aws_clients["kms"] = boto3.client("kms")  # For encryption
    logger.info("AWS services initialized securely")
except Exception as e:
    logger.error("AWS initialization failed: %s", str(e))
    # In production, fail fast if AWS services unavailable
    raise

# DynamoDB tables with error handling
tables = {}
try:
    tables["subscribers"] = aws_clients["dynamodb"].Table(CONFIG["SUBSCRIBER_TABLE_NAME"])
    tables["audit_logs"] = aws_clients["dynamodb"].Table(CONFIG["AUDIT_LOG_TABLE_NAME"])
    tables["migration_jobs"] = aws_clients["dynamodb"].Table(CONFIG["MIGRATION_JOBS_TABLE_NAME"])
    if CONFIG.get("TOKEN_BLACKLIST_TABLE_NAME"):
        tables["token_blacklist"] = aws_clients["dynamodb"].Table(CONFIG["TOKEN_BLACKLIST_TABLE_NAME"])
    logger.info("DynamoDB tables initialized")
except Exception as e:
    logger.error("DynamoDB initialization failed: %s", str(e))
    raise


# SECURITY: Input validation and sanitization
class InputValidator:
    """Comprehensive input validation and sanitization."""

    # Regex patterns for validation
    PATTERNS = {
        "uid": re.compile(r"^[A-Za-z0-9_-]{1,50}$"),
        "imsi": re.compile(r"^[0-9]{10,15}$"),
        "msisdn": re.compile(r"^\+?[1-9][0-9]{7,14}$"),
        "email": re.compile(r"^[^@]+@[^@]+\.[^@]+$"),
        "alphanumeric": re.compile(r"^[A-Za-z0-9\s_-]+$"),
        "status": re.compile(r"^(ACTIVE|INACTIVE|SUSPENDED|DELETED)$"),
        "job_type": re.compile(r"^(csv_upload|bulk_migration|legacy_sync|audit)$"),
    }

    @staticmethod
    def sanitize_string(value: Any, max_length: int = 255, pattern: str = None) -> str:
        """Sanitize string input with optional pattern validation."""
        if value is None:
            return ""

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
        self.fernet = Fernet(
            CONFIG["ENCRYPTION_KEY"].encode() if isinstance(CONFIG["ENCRYPTION_KEY"], str) else CONFIG["ENCRYPTION_KEY"]
        )

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
    def mask_pii(value: str, mask_char: str = "*", visible_chars: int = 4) -> str:
        """Mask PII for logging/display."""
        if not value or len(value) <= visible_chars:
            return mask_char * len(value) if value else ""

        return value[:2] + mask_char * (len(value) - visible_chars) + value[-2:]


pii_protection = PIIProtection()


# SECURITY: Enhanced user management with Secrets Manager
def load_users_from_secrets() -> Dict:
    """Load users securely from AWS Secrets Manager only."""
    if not CONFIG.get("USERS_SECRET_ARN"):
        # SECURITY: No fallback credentials in production
        raise ValueError("USERS_SECRET_ARN environment variable required for production")

    try:
        response = aws_clients["secrets"].get_secret_value(SecretId=CONFIG["USERS_SECRET_ARN"])
        users = json.loads(response["SecretString"])

        # Validate user structure
        for username, user_data in users.items():
            required_fields = ["password_hash", "role", "permissions"]
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
    if not CONFIG.get("LEGACY_DB_SECRET_ARN"):
        return None

    try:
        response = aws_clients["secrets"].get_secret_value(SecretId=CONFIG["LEGACY_DB_SECRET_ARN"])
        secret = json.loads(response["SecretString"])

        # SECURITY: Validate secret structure
        required_fields = ["username", "password"]
        if not all(field in secret for field in required_fields):
            raise ValueError("Invalid database secret structure")

        # SECURITY: Use least-privilege connection settings
        connection = pymysql.connect(
            host=CONFIG["LEGACY_DB_HOST"],
            port=CONFIG["LEGACY_DB_PORT"],
            user=secret["username"],
            password=secret["password"],
            database=CONFIG["LEGACY_DB_NAME"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
            read_timeout=5,
            write_timeout=5,
            autocommit=False,  # Explicit transaction control
            sql_mode="STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO",
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
        login_attempts[username] = [
            attempt for attempt in login_attempts[username] if now - attempt < timedelta(hours=1)
        ]

        login_attempts[username].append(now)

        # Lock account if too many attempts
        if len(login_attempts[username]) >= CONFIG["MAX_LOGIN_ATTEMPTS"]:
            locked_accounts[username] = now + timedelta(minutes=CONFIG["LOCKOUT_DURATION_MINUTES"])
            logger.warning("Account locked due to failed attempts: %s", InputValidator.sanitize_string(username, 50))

    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        """Secure authentication with attempt tracking."""
        username = InputValidator.sanitize_string(username, 50, "alphanumeric")

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

            if user and check_password_hash(user["password_hash"], password):
                # Clear failed attempts on successful login
                if username in login_attempts:
                    del login_attempts[username]

                return {
                    "username": username,
                    "role": user["role"],
                    "permissions": user["permissions"],
                    "rate_limit_override": user.get("rate_limit_override", False),
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
            "sub": user_data["username"],
            "role": user_data["role"],
            "permissions": user_data["permissions"],
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=CONFIG["JWT_EXPIRY_HOURS"]),
            "jti": str(uuid.uuid4()),
            "iss": "subscriber-migration-portal",
            "aud": "subscriber-portal-api",
        }
        return jwt.encode(payload, CONFIG["JWT_SECRET"], algorithm=CONFIG["JWT_ALGORITHM"])

    @staticmethod
    def verify_jwt_token(token: str) -> Optional[Dict]:
        """Verify JWT token securely."""
        try:
            # Verify token with strict validation
            payload = jwt.decode(
                token,
                CONFIG["JWT_SECRET"],
                algorithms=[CONFIG["JWT_ALGORITHM"]],
                audience="subscriber-portal-api",
                issuer="subscriber-migration-portal",
            )

            # Check token blacklist
            if is_token_blacklisted(payload.get("jti")):
                return None

            return {
                "username": payload["sub"],
                "role": payload["role"],
                "permissions": payload["permissions"],
                "jti": payload.get("jti"),
                "exp": payload.get("exp"),
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
        if "token_blacklist" in tables:
            response = tables["token_blacklist"].get_item(Key={"jti": jti})
            return "Item" in response
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
        if "token_blacklist" in tables:
            tables["token_blacklist"].put_item(
                Item={
                    "jti": jti,
                    "blacklisted_at": datetime.utcnow().isoformat(),
                    "ttl": int(exp),
                    "reason": "user_logout",
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
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                raise Unauthorized("Authorization header required")

            if not auth_header.startswith("Bearer "):
                raise Unauthorized("Bearer token required")

            try:
                token = auth_header.split(" ")[1]
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
                user_perms = user.get("permissions", [])

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
        "status": "success" if status_code < 400 else "error",
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Only include version in non-error responses
    if status_code < 400:
        response["version"] = CONFIG["VERSION"]

    if data is not None:
        # Sanitize data before sending
        response["data"] = sanitize_response_data(data)

    # SECURITY: Never expose internal error details in production
    if error and status_code >= 500:
        # Log full error internally but don't expose to client
        logger.error("Internal error: %s", str(error))
        response["error"] = "Internal server error occurred"
    elif error:
        response["error"] = str(error)

    return jsonify(response), status_code


def sanitize_response_data(data: Any) -> Any:
    """Sanitize response data to remove sensitive information."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Skip sensitive fields
            if any(sensitive in key.lower() for sensitive in ["password", "secret", "token", "key"]):
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
        if "audit_logs" not in tables:
            return

        # Sanitize details to remove PII
        safe_details = {}
        if details:
            for key, value in details.items():
                if any(pii in key.lower() for pii in ["password", "token", "imsi", "msisdn"]):
                    safe_details[key] = PIIProtection.mask_pii(str(value))
                else:
                    safe_details[key] = value

        log_entry = {
            "id": f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}",
            "timestamp": datetime.utcnow().isoformat(),
            "action": InputValidator.sanitize_string(action, 100),
            "resource": InputValidator.sanitize_string(resource, 100),
            "user": InputValidator.sanitize_string(user, 50),
            "ip_address": request.remote_addr if request else "system",
            "user_agent": (
                InputValidator.sanitize_string(request.headers.get("User-Agent", "unknown")[:200], 200)
                if request
                else "system"
            ),
            "details": safe_details,
            "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
        }

        tables["audit_logs"].put_item(Item=log_entry)

    except Exception as e:
        # SECURITY: Don't fail the main operation if audit logging fails
        logger.error("Audit logging failed: %s", str(e))


# === EXISTING SECURE ROUTES (NO CHANGES) ===


@app.route("/api/health", methods=["GET"])
@app.route("/health", methods=["GET"])
@limiter.limit("10 per minute")  # Rate limit even health checks
def health_check():
    """Secure health check with minimal information disclosure."""
    health_status = {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": CONFIG["VERSION"]}

    # SECURITY: Only include basic service status, no detailed configuration
    services_healthy = True
    try:
        # Test DynamoDB connection
        tables["subscribers"].scan(Limit=1)
    except Exception:
        services_healthy = False

    health_status["services"] = {"database": services_healthy}

    if not services_healthy:
        health_status["status"] = "degraded"

    return create_secure_response(data=health_status, message="Health check completed")


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("5 per minute")  # Strict rate limiting for login
def secure_login():
    """Secure login with comprehensive validation."""
    try:
        # SECURITY: Validate request format
        if not request.is_json:
            raise BadRequest("Content-Type must be application/json")

        data = request.get_json(force=True)

        # SECURITY: Validate input structure
        validated_data = InputValidator.validate_json(data, required_fields=["username", "password"])

        username = InputValidator.sanitize_string(validated_data["username"], 50, "alphanumeric")
        password = validated_data["password"]

        # SECURITY: Additional password validation
        if len(password) > 128:  # Prevent DoS via huge passwords
            raise BadRequest("Password too long")

        user = SecureUserManager.authenticate(username, password)
        if not user:
            secure_audit_log("login_failed", "auth", username, {"ip": request.remote_addr})
            raise Unauthorized("Invalid credentials")

        # Generate secure token
        token = SecureUserManager.generate_secure_jwt_token(user)
        secure_audit_log("login_success", "auth", username, {"role": user["role"]})

        return create_secure_response(
            data={
                "token": token,
                "user": {"username": user["username"], "role": user["role"], "permissions": user["permissions"]},
                "expires_in": CONFIG["JWT_EXPIRY_HOURS"] * 3600,
            },
            message="Authentication successful",
        )

    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error("Login error: %s", str(e))
        return create_secure_response(message="Authentication failed", status_code=500)


@app.route("/api/auth/logout", methods=["POST"])
@require_auth()
def secure_logout():
    """Secure logout with token revocation."""
    try:
        user = g.current_user
        if user.get("jti") and user.get("exp"):
            blacklist_token(user["jti"], user["exp"])

        secure_audit_log("logout", "auth", user["username"])
        return create_secure_response(message="Logout successful")

    except Exception as e:
        logger.error("Logout error: %s", str(e))
        return create_secure_response(message="Logout completed")


@app.route("/api/dashboard/stats", methods=["GET"])
@require_auth(["read"])
@limiter.limit("30 per minute")
def get_secure_dashboard_stats():
    """Secure dashboard statistics with data sanitization."""
    try:
        stats = {
            "totalSubscribers": 0,
            "cloudSubscribers": 0,
            "systemHealth": "healthy",
            "provisioningMode": CONFIG["PROV_MODE"],
            "lastUpdated": datetime.utcnow().isoformat(),
        }

        # Get cloud subscriber count securely
        try:
            if "subscribers" in tables:
                response = tables["subscribers"].scan(Select="COUNT")
                stats["cloudSubscribers"] = response.get("Count", 0)
        except Exception as e:
            logger.error("Dashboard query error: %s", str(e))
            stats["systemHealth"] = "degraded"

        # SECURITY: Don't expose legacy DB stats if not configured
        if CONFIG.get("LEGACY_DB_SECRET_ARN"):
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        # SECURITY: Use parameterized query
                        cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != %s", ("DELETED",))
                        result = cursor.fetchone()
                        stats["legacySubscribers"] = result["count"] if result else 0
                    connection.close()
            except Exception as e:
                logger.error("Legacy DB stats error: %s", str(e))

        stats["totalSubscribers"] = stats["cloudSubscribers"] + stats.get("legacySubscribers", 0)

        return create_secure_response(data=stats)

    except Exception as e:
        logger.error("Dashboard stats error: %s", str(e))
        return create_secure_response(message="Failed to retrieve dashboard statistics", status_code=500)


# ========================================================================
# NEW ENHANCED MIGRATION ROUTES (EXISTING - NO CHANGES)
# ========================================================================


@app.route("/api/migration/csv-upload", methods=["POST"])
@require_auth(["write", "admin"])
@limiter.limit("10 per hour")
def csv_migration_upload():
    """
    Enhanced CSV upload with automatic identifier detection and full profile migration.
    Supports: uid, imsi, msisdn
    Auto-detects identifier type from CSV header (first line).
    """
    try:
        if 'file' not in request.files:
            raise BadRequest("No file uploaded")
        
        file = request.files['file']
        if not file or file.filename == '':
            raise BadRequest("Empty file")
        
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise BadRequest("Only CSV files are allowed")
        
        # Read CSV content
        content = file.read().decode('utf-8')
        lines = content.strip().split('\n')
        
        if len(lines) < 2:
            raise BadRequest("CSV must contain header and at least one data row")
        
        # Auto-detect identifier type from header (first line)
        header = lines[0].strip().lower()
        identifier_type = None
        
        if 'uid' in header:
            identifier_type = 'uid'
        elif 'imsi' in header:
            identifier_type = 'imsi'
        elif 'msisdn' in header:
            identifier_type = 'msisdn'
        else:
            raise BadRequest("Invalid CSV header. Must contain: uid, imsi, or msisdn")
        
        # Extract identifiers from remaining lines
        identifiers = []
        for line in lines[1:]:
            line = line.strip()
            if line:
                identifiers.append(line)
        
        if not identifiers:
            raise BadRequest("No valid identifiers found in CSV")
        
        # Create migration job
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = {
            'job_id': job_id,
            'identifier_type': identifier_type,
            'total_subscribers': len(identifiers),
            'identifiers': identifiers,
            'status': 'PENDING',
            'created_at': datetime.utcnow().isoformat(),
            'created_by': g.current_user['username'],
            'filename': file.filename,
            'progress': 0,
            'migrated_count': 0,
            'failed_count': 0,
            'success_details': [],
            'failure_details': []
        }
        
        # Save job to DynamoDB
        tables['migration_jobs'].put_item(Item=job)
        
        # Start migration process (synchronous for now, can be made async with Lambda/SQS)
        migrate_subscribers_batch(job_id, identifiers, identifier_type)
        
        secure_audit_log(
            'csv_migration_started',
            'migration',
            g.current_user['username'],
            {'job_id': job_id, 'count': len(identifiers), 'type': identifier_type}
        )
        
        return create_secure_response(
            data={
                'job_id': job_id,
                'status': 'started',
                'total_subscribers': len(identifiers),
                'identifier_type': identifier_type
            },
            message=f"Migration job created successfully. Detected identifier: {identifier_type}"
        )
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"CSV upload error: {str(e)}")
        return create_secure_response(message="Failed to process CSV upload", status_code=500)


def migrate_subscribers_batch(job_id, identifiers, identifier_type):
    """
    Background function to migrate full subscriber profiles from legacy to cloud.
    Fetches complete profile based on identifier and migrates to DynamoDB.
    """
    try:
        connection = get_legacy_db_connection()
        if not connection:
            raise Exception("Cannot connect to legacy database")
        
        migrated = 0
        failed = 0
        success_details = []
        failure_details = []
        
        with connection.cursor() as cursor:
            for idx, identifier in enumerate(identifiers):
                try:
                    # Fetch full profile from legacy DB based on identifier type
                    if identifier_type == 'uid':
                        query = "SELECT * FROM subscribers WHERE uid = %s AND status != 'DELETED'"
                    elif identifier_type == 'imsi':
                        query = "SELECT * FROM subscribers WHERE imsi = %s AND status != 'DELETED'"
                    else:  # msisdn
                        query = "SELECT * FROM subscribers WHERE msisdn = %s AND status != 'DELETED'"
                    
                    cursor.execute(query, (identifier,))
                    subscriber = cursor.fetchone()
                    
                    if subscriber:
                        # Migrate full profile to DynamoDB (cloud)
                        cloud_subscriber = {
                            'uid': subscriber['uid'],
                            'imsi': subscriber.get('imsi', ''),
                            'msisdn': subscriber.get('msisdn', ''),
                            'email': subscriber.get('email', ''),
                            'status': subscriber.get('status', 'ACTIVE'),
                            'plan': subscriber.get('plan', ''),
                            'created_at': str(subscriber.get('created_at', '')),
                            'migrated_at': datetime.utcnow().isoformat(),
                            'migrated_from': 'legacy',
                            'migration_job_id': job_id
                        }
                        
                        # Add any additional fields from legacy DB
                        for key, value in subscriber.items():
                            if key not in cloud_subscriber and value is not None:
                                cloud_subscriber[key] = str(value)
                        
                        tables['subscribers'].put_item(Item=cloud_subscriber)
                        migrated += 1
                        success_details.append({
                            'identifier': identifier,
                            'uid': subscriber['uid'],
                            'status': 'SUCCESS',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                    else:
                        failed += 1
                        failure_details.append({
                            'identifier': identifier,
                            'reason': 'Subscriber not found in legacy database',
                            'status': 'FAILED',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        
                except Exception as sub_error:
                    failed += 1
                    failure_details.append({
                        'identifier': identifier,
                        'reason': str(sub_error),
                        'status': 'FAILED',
                        'timestamp': datetime.utcnow().isoformat()
                    })
                
                # Update job progress
                progress = int((migrated + failed) / len(identifiers) * 100)
                tables['migration_jobs'].update_item(
                    Key={'job_id': job_id},
                    UpdateExpression='SET progress = :p, migrated_count = :m, failed_count = :f, #status = :s',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':p': progress,
                        ':m': migrated,
                        ':f': failed,
                        ':s': 'IN_PROGRESS'
                    }
                )
        
        connection.close()
        
        # Mark job as completed
        tables['migration_jobs'].update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :s, completed_at = :c, success_details = :sd, failure_details = :fd, progress = :p',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':s': 'COMPLETED',
                ':c': datetime.utcnow().isoformat(),
                ':sd': success_details,
                ':fd': failure_details,
                ':p': 100
            }
        )
        
        logger.info(f"Migration job {job_id} completed: {migrated} succeeded, {failed} failed")
        
    except Exception as e:
        logger.error(f"Migration batch error for job {job_id}: {str(e)}")
        # Mark job as failed
        tables['migration_jobs'].update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :s, error = :e',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':s': 'FAILED',
                ':e': str(e)
            }
        )


@app.route("/api/migration/jobs/<job_id>", methods=["GET"])
@require_auth(["read"])
def get_migration_job_details(job_id):
    """Get detailed migration job information including success/fail details."""
    try:
        response = tables['migration_jobs'].get_item(Key={'job_id': job_id})
        
        if 'Item' not in response:
            return create_secure_response(message="Job not found", status_code=404)
        
        job = response['Item']
        return create_secure_response(data=job)
        
    except Exception as e:
        logger.error(f"Failed to get job details: {str(e)}")
        return create_secure_response(message="Failed to retrieve job details", status_code=500)


@app.route("/api/migration/jobs", methods=["GET"])
@require_auth(["read"])
def list_migration_jobs():
    """List all migration jobs with pagination."""
    try:
        response = tables['migration_jobs'].scan(Limit=100)
        
        jobs = response.get('Items', [])
        
        # Sort by created_at descending
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return create_secure_response(data={'jobs': jobs, 'count': len(jobs)})
        
    except Exception as e:
        logger.error(f"Failed to list jobs: {str(e)}")
        return create_secure_response(message="Failed to list jobs", status_code=500)


@app.route("/api/migration/jobs/<job_id>/report", methods=["GET"])
@require_auth(["read"])
def download_migration_report(job_id):
    """
    Generate and download detailed migration report as CSV.
    Report includes: job summary, success details, failure details with reasons.
    """
    try:
        response = tables['migration_jobs'].get_item(Key={'job_id': job_id})
        
        if 'Item' not in response:
            return create_secure_response(message="Job not found", status_code=404)
        
        job = response['Item']
        
        # Generate CSV report
        csv_lines = []
        csv_lines.append("MIGRATION JOB REPORT")
        csv_lines.append(f"Job ID,{job_id}")
        csv_lines.append(f"Status,{job.get('status', 'UNKNOWN')}")
        csv_lines.append(f"Identifier Type,{job.get('identifier_type', 'N/A')}")
        csv_lines.append(f"Filename,{job.get('filename', 'N/A')}")
        csv_lines.append(f"Created By,{job.get('created_by', 'N/A')}")
        csv_lines.append(f"Created At,{job.get('created_at', '')}")
        csv_lines.append(f"Completed At,{job.get('completed_at', 'In Progress')}")
        csv_lines.append(f"Total Subscribers,{job.get('total_subscribers', 0)}")
        csv_lines.append(f"Successfully Migrated,{job.get('migrated_count', 0)}")
        csv_lines.append(f"Failed,{job.get('failed_count', 0)}")
        csv_lines.append(f"Progress,{job.get('progress', 0)}%")
        csv_lines.append("")
        
        # Success details
        csv_lines.append("SUCCESS DETAILS")
        csv_lines.append("Identifier,UID,Status,Timestamp")
        for detail in job.get('success_details', []):
            csv_lines.append(
                f"{detail.get('identifier', '')},"
                f"{detail.get('uid', '')},"
                f"{detail.get('status', '')},"
                f"{detail.get('timestamp', '')}"
            )
        
        csv_lines.append("")
        
        # Failure details
        csv_lines.append("FAILURE DETAILS")
        csv_lines.append("Identifier,Reason,Status,Timestamp")
        for detail in job.get('failure_details', []):
            csv_lines.append(
                f"{detail.get('identifier', '')},"
                f"\"{detail.get('reason', '')}\"," # Quote reason in case it contains commas
                f"{detail.get('status', '')},"
                f"{detail.get('timestamp', '')}"
            )
        
        report_csv = '\n'.join(csv_lines)
        
        return Response(
            report_csv,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=migration_report_{job_id}.csv'}
        )
        
    except Exception as e:
        logger.error(f"Report generation error: {str(e)}")
        return create_secure_response(message="Failed to generate report", status_code=500)


@app.route("/api/query/subscribers", methods=["POST"])
@require_auth(["read"])
@limiter.limit("20 per minute")
def query_subscribers():
    """
    Advanced subscriber query interface with filters.
    Supports querying by: uid, imsi, msisdn, email
    Supports sources: cloud (DynamoDB) or legacy (MySQL)
    """
    try:
        data = request.get_json()
        
        query_type = data.get('query_type', 'uid')  # uid, imsi, msisdn, email
        query_value = data.get('query_value', '').strip()
        data_source = data.get('data_source', 'both').lower()  # cloud, legacy, or both
        
        if not query_value:
            raise BadRequest("Query value required")
        
        results = []
        
if data_source in ['cloud', 'both']:
    # Query DynamoDB
    if query_type == 'uid':
        response = tables['subscribers'].get_item(Key={'uid': query_value})
        if 'Item' in response:
            response['Item']['_source'] = 'cloud'  # ✅ ADD source tag
            results.append(response['Item'])
    else:
        response = tables['subscribers'].scan(
            FilterExpression=f"#{query_type} = :val",
            ExpressionAttributeNames={f'#{query_type}': query_type},
            ExpressionAttributeValues={':val': query_value},
            Limit=100
        )
        for item in response.get('Items', []):
            item['_source'] = 'cloud'  # ✅ ADD source tag
            results.extend(response.get('Items', []))

if data_source in ['legacy', 'both']:  # ✅ CHANGE from elif to if
    connection = get_legacy_db_connection()
    if connection:
        with connection.cursor() as cursor:
            query = f"SELECT * FROM subscribers WHERE {query_type} = %s AND status != 'DELETED' LIMIT 100"
            cursor.execute(query, (query_value,))
            for row in cursor.fetchall():
                row['_source'] = 'legacy'  # ✅ ADD source tag
                results.append(row)
        connection.close()
            else:
                raise Exception("Legacy database connection not available")
        
        return create_secure_response(
            data={
                'results': results,
                'count': len(results),
                'query_type': query_type,
                'queried_source': data_source  # ✅ NEW parameter
            }
        )
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Query error: {str(e)}")
        return create_secure_response(message="Query failed", status_code=500)

@app.route("/api/migration/jobs/<job_id>/cancel", methods=["POST"])
@require_auth(["write", "admin"])
def cancel_migration_job(job_id):
    """Cancel a running migration job."""
    try:
        response = tables['migration_jobs'].get_item(Key={'job_id': job_id})
        
        if 'Item' not in response:
            return create_secure_response(message="Job not found", status_code=404)
        
        job = response['Item']
        
        if job.get('status') not in ['PENDING', 'IN_PROGRESS']:
            return create_secure_response(
                message=f"Cannot cancel job with status: {job.get('status')}", 
                status_code=400
            )
        
        tables['migration_jobs'].update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :s, cancelled_at = :c, cancelled_by = :u',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':s': 'CANCELLED',
                ':c': datetime.utcnow().isoformat(),
                ':u': g.current_user['username']
            }
        )
        
        secure_audit_log('cancel_migration_job', 'migration', g.current_user['username'], {'job_id': job_id})
        
        return create_secure_response(message="Job cancelled successfully")
        
    except Exception as e:
        logger.error(f"Cancel job error: {str(e)}")
        return create_secure_response(message="Failed to cancel job", status_code=500)
        
        
@app.route("/api/migration/bulk-delete", methods=["POST"])
@require_auth(["admin"])  # Admin only
@limiter.limit("5 per hour")
def bulk_delete_subscribers():
    """Bulk delete subscribers from DynamoDB via CSV."""
    try:
        data = request.get_json()
        csv_data = data.get('csv_data', '')
        
        if not csv_data:
            raise BadRequest("CSV data required")
        
        # Decode base64 CSV
        import base64
        csv_content = base64.b64decode(csv_data).decode('utf-8')
        lines = csv_content.strip().split('\n')
        
        # Skip header, get UIDs
        uids = [line.strip() for line in lines[1:] if line.strip()]
        
        if not uids:
            raise BadRequest("No UIDs found in CSV")
        
        # Create deletion job
        job_id = f"delete_{uuid.uuid4().hex[:12]}"
        job = {
            'job_id': job_id,
            'job_type': 'bulk_delete',
            'total_subscribers': len(uids),
            'status': 'COMPLETED',  # Execute synchronously
            'created_at': datetime.utcnow().isoformat(),
            'created_by': g.current_user['username'],
            'deleted_count': 0,
            'failed_count': 0
        }
        
        # Execute deletions
        deleted = 0
        failed = 0
        for uid in uids:
            try:
                tables['subscribers'].delete_item(Key={'uid': uid})
                deleted += 1
            except Exception:
                failed += 1
        
        job['deleted_count'] = deleted
        job['failed_count'] = failed
        
        tables['migration_jobs'].put_item(Item=job)
        
        secure_audit_log('bulk_delete', 'subscribers', g.current_user['username'], 
                        {'job_id': job_id, 'count': deleted})
        
        return create_secure_response(data={'job_id': job_id, 'deleted': deleted, 'failed': failed})
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Bulk delete error: {str(e)}")
        return create_secure_response(message="Bulk delete failed", status_code=500)


@app.route("/api/migration/sql-export", methods=["POST"])
@require_auth(["read"])
@limiter.limit("10 per hour")
def export_sql_query():
    """Execute SQL query and export results to CSV."""
    try:
        data = request.get_json()
        sql_query = data.get('sql_query', '').strip()
        
        if not sql_query or not sql_query.lower().startswith('select'):
            raise BadRequest("Only SELECT queries allowed")
        
        connection = get_legacy_db_connection()
        if not connection:
            raise Exception("Legacy database not available")
        
        results = []
        with connection.cursor() as cursor:
            cursor.execute(sql_query)
            results = cursor.fetchall()
        connection.close()
        
        # Generate CSV
        if not results:
            raise BadRequest("Query returned no results")
        
        csv_lines = []
        headers = list(results[0].keys())
        csv_lines.append(','.join(headers))
        
        for row in results:
            csv_lines.append(','.join([str(row.get(h, '')) for h in headers]))
        
        csv_content = '\n'.join(csv_lines)
        
        # Upload to S3
        file_key = f"exports/sql_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        aws_clients['s3'].put_object(
            Bucket=CONFIG['MIGRATION_UPLOAD_BUCKET_NAME'],
            Key=file_key,
            Body=csv_content,
            ContentType='text/csv'
        )
        
        # Generate pre-signed URL
        download_url = aws_clients['s3'].generate_presigned_url(
            'get_object',
            Params={'Bucket': CONFIG['MIGRATION_UPLOAD_BUCKET_NAME'], 'Key': file_key},
            ExpiresIn=3600
        )
        
        secure_audit_log('sql_export', 'query', g.current_user['username'], {'rows': len(results)})
        
        return create_secure_response(data={'downloadurl': download_url, 'rowcount': len(results)})
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"SQL export error: {str(e)}")
        return create_secure_response(message="SQL export failed", status_code=500)


@app.route("/api/dashboard/performance", methods=["GET"])
@require_auth(["read"])
def get_performance_metrics():
    """
    Get performance dashboard metrics.
    Includes: migration statistics, system health, recent jobs.
    """
    try:
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'migration_stats': {
                'total_jobs': 0,
                'completed_jobs': 0,
                'failed_jobs': 0,
                'in_progress_jobs': 0,
                'total_migrated': 0,
                'total_failed': 0
            },
            'system_health': {
                'database_status': 'healthy',
                'api_status': 'healthy',
                'storage_status': 'healthy'
            },
            'recent_jobs': []
        }
        
        # Get migration job statistics
        response = tables['migration_jobs'].scan()
        jobs = response.get('Items', [])
        
        metrics['migration_stats']['total_jobs'] = len(jobs)
        
        for job in jobs:
            status = job.get('status', 'UNKNOWN')
            if status == 'COMPLETED':
                metrics['migration_stats']['completed_jobs'] += 1
                metrics['migration_stats']['total_migrated'] += job.get('migrated_count', 0)
                metrics['migration_stats']['total_failed'] += job.get('failed_count', 0)
            elif status == 'FAILED':
                metrics['migration_stats']['failed_jobs'] += 1
            elif status in ['PENDING', 'IN_PROGRESS']:
                metrics['migration_stats']['in_progress_jobs'] += 1
        
        # Get recent jobs (last 10)
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        metrics['recent_jobs'] = jobs[:10]
        
        # Check system health
        try:
            tables['subscribers'].scan(Limit=1)
        except Exception:
            metrics['system_health']['database_status'] = 'unhealthy'
        
        return create_secure_response(data=metrics)
        
    except Exception as e:
        logger.error(f"Performance metrics error: {str(e)}")
        return create_secure_response(message="Failed to get performance metrics", status_code=500)


# ========================================================================
# NEW PROVISIONING ENDPOINTS - ADDED BELOW
# ========================================================================


@app.route("/api/subscribers", methods=["POST"])
@require_auth(["write", "admin"])
@limiter.limit("30 per minute")
def create_subscriber():
    """Create new subscriber in DynamoDB and optionally in Legacy DB."""
    try:
        data = request.get_json()
        
        validated_data = InputValidator.validate_json(
            data,
            required_fields=["uid", "imsi", "msisdn"],
            optional_fields=["email", "status", "plan", "system"]
        )
        
        subscriber = {
            'uid': InputValidator.sanitize_string(validated_data['uid'], 50, 'uid'),
            'imsi': InputValidator.sanitize_string(validated_data['imsi'], 15, 'imsi'),
            'msisdn': InputValidator.sanitize_string(validated_data['msisdn'], 15, 'msisdn'),
            'email': InputValidator.sanitize_string(validated_data.get('email', ''), 100, 'email') if validated_data.get('email') else '',
            'status': validated_data.get('status', 'ACTIVE'),
            'plan': InputValidator.sanitize_string(validated_data.get('plan', ''), 50),
            'created_at': datetime.utcnow().isoformat(),
            'created_by': g.current_user['username']
        }
        
        system = validated_data.get('system', 'cloud')
        
        # Create in Cloud (DynamoDB)
        if system in ['cloud', 'both']:
            tables['subscribers'].put_item(Item=subscriber)
            secure_audit_log('create_subscriber_cloud', 'subscribers', g.current_user['username'],
                           {'uid': subscriber['uid']})
        
        # Create in Legacy (MySQL)
        if system in ['legacy', 'both'] and CONFIG.get("LEGACY_DB_SECRET_ARN"):
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    insert_query = """
                        INSERT INTO subscribers (uid, imsi, msisdn, email, status, plan, created_at, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        subscriber['uid'],
                        subscriber['imsi'],
                        subscriber['msisdn'],
                        subscriber['email'],
                        subscriber['status'],
                        subscriber['plan'],
                        subscriber['created_at'],
                        subscriber['created_by']
                    ))
                    connection.commit()
                connection.close()
                secure_audit_log('create_subscriber_legacy', 'subscribers', g.current_user['username'],
                               {'uid': subscriber['uid']})
        
        return create_secure_response(data=subscriber, message="Subscriber created successfully")
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return create_secure_response(message="Failed to create subscriber", status_code=500, error=e)


@app.route("/api/subscribers/<uid>", methods=["PUT"])
@require_auth(["write", "admin"])
@limiter.limit("30 per minute")
def update_subscriber(uid):
    """Update existing subscriber in specified system(s)."""
    try:
        data = request.get_json()
        system = data.get('system', 'cloud')
        
        update_expr = "SET "
        expr_values = {}
        expr_names = {}
        
        fields_to_update = ["imsi", "msisdn", "email", "status", "plan"]
        updates = []
        
        for field in fields_to_update:
            if field in data and data[field] is not None:
                updates.append(f"#{field} = :{field}")
                expr_names[f"#{field}"] = field
                expr_values[f":{field}"] = data[field]
        
        if not updates:
            raise BadRequest("No fields to update")
        
        update_expr += ", ".join(updates)
        update_expr += ", updated_at = :updated_at, updated_by = :updated_by"
        expr_values[":updated_at"] = datetime.utcnow().isoformat()
        expr_values[":updated_by"] = g.current_user['username']
        
        # Update Cloud
        if system in ['cloud', 'both']:
            tables['subscribers'].update_item(
                Key={'uid': uid},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )
            secure_audit_log('update_subscriber_cloud', 'subscribers', g.current_user['username'],
                           {'uid': uid, 'fields': list(data.keys())})
        
        # Update Legacy
        if system in ['legacy', 'both'] and CONFIG.get("LEGACY_DB_SECRET_ARN"):
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    set_clause = ", ".join([f"{field} = %s" for field in data.keys() if field in fields_to_update])
                    set_clause += ", updated_at = %s, updated_by = %s"
                    
                    values = [data[field] for field in data.keys() if field in fields_to_update]
                    values.extend([datetime.utcnow().isoformat(), g.current_user['username'], uid])
                    
                    update_query = f"UPDATE subscribers SET {set_clause} WHERE uid = %s"
                    cursor.execute(update_query, values)
                    connection.commit()
                connection.close()
                secure_audit_log('update_subscriber_legacy', 'subscribers', g.current_user['username'],
                               {'uid': uid, 'fields': list(data.keys())})
        
        return create_secure_response(message="Subscriber updated successfully")
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Update subscriber error: {str(e)}")
        return create_secure_response(message="Failed to update subscriber", status_code=500, error=e)


@app.route("/api/subscribers/<uid>", methods=["DELETE"])
@require_auth(["write", "admin"])
@limiter.limit("30 per minute")
def delete_subscriber(uid):
    """Delete subscriber from specified system."""
    try:
        system = request.args.get('system', 'cloud')
        
        if system == 'cloud' or system == 'both':
            tables['subscribers'].delete_item(Key={'uid': uid})
            secure_audit_log('delete_subscriber_cloud', 'subscribers', g.current_user['username'], {'uid': uid})
        
        if (system == 'legacy' or system == 'both') and CONFIG.get("LEGACY_DB_SECRET_ARN"):
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM subscribers WHERE uid = %s", (uid,))
                    connection.commit()
                connection.close()
                secure_audit_log('delete_subscriber_legacy', 'subscribers', g.current_user['username'], {'uid': uid})
        
        return create_secure_response(message=f"Subscriber deleted from {system}")
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Delete subscriber error: {str(e)}")
        return create_secure_response(message="Failed to delete subscriber", status_code=500, error=e)


@app.route("/api/subscribers/search", methods=["GET"])
@require_auth(["read"])
@limiter.limit("30 per minute")
def search_subscribers():
    """Search subscribers by query string in specified system."""
    try:
        query = request.args.get('q', '').strip()
        system = request.args.get('system', 'cloud')
        
        if not query:
            raise BadRequest("Query parameter 'q' required")
        
        results = []
        
        if system == 'cloud':
            # Scan and filter (simple implementation)
            response = tables['subscribers'].scan()
            items = response.get('Items', [])
            
            query_lower = query.lower()
            for item in items:
                if (query_lower in str(item.get('uid', '')).lower() or
                    query_lower in str(item.get('email', '')).lower() or
                    query_lower in str(item.get('imsi', '')).lower() or
                    query_lower in str(item.get('msisdn', '')).lower()):
                    results.append(item)
        
        elif system == 'legacy':
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    sql = """
                        SELECT * FROM subscribers 
                        WHERE (uid LIKE %s OR email LIKE %s OR imsi LIKE %s OR msisdn LIKE %s)
                        AND status != 'DELETED'
                        LIMIT 100
                    """
                    search_term = f"%{query}%"
                    cursor.execute(sql, (search_term, search_term, search_term, search_term))
                    results = cursor.fetchall()
                connection.close()
            else:
                raise Exception("Legacy database not available")
        
        return create_secure_response(data={'subscribers': results, 'count': len(results)})
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return create_secure_response(message="Search failed", status_code=500, error=e)


@app.route("/api/subscribers/<uid>", methods=["GET"])
@require_auth(["read"])
@limiter.limit("30 per minute")
def get_subscriber(uid):
    """Get single subscriber by UID from specified system."""
    try:
        system = request.args.get('system', 'cloud')
        
        if system == 'cloud':
            response = tables['subscribers'].get_item(Key={'uid': uid})
            if 'Item' in response:
                return create_secure_response(data=response['Item'])
            else:
                return create_secure_response(message="Subscriber not found", status_code=404)
        
        elif system == 'legacy':
            connection = get_legacy_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM subscribers WHERE uid = %s AND status != 'DELETED'", (uid,))
                    result = cursor.fetchone()
                connection.close()
                
                if result:
                    return create_secure_response(data=result)
                else:
                    return create_secure_response(message="Subscriber not found", status_code=404)
            else:
                raise Exception("Legacy database not available")
        
    except (BadRequest, Unauthorized) as e:
        return create_secure_response(message=str(e), status_code=e.code)
    except Exception as e:
        logger.error(f"Get subscriber error: {str(e)}")
        return create_secure_response(message="Failed to retrieve subscriber", status_code=500, error=e)


# === EXISTING ERROR HANDLERS (NO CHANGES) ===


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
        logger.info(
            "Lambda invoked - Method: %s, Path: %s", event.get("httpMethod", "UNKNOWN"), event.get("path", "UNKNOWN")
        )

        # Handle empty events securely
        if not event:
            event = {}

        # SECURITY: Standard CORS headers with strict configuration
        cors_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": CONFIG["FRONTEND_ORIGIN"],
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With",
            "Access-Control-Allow-Credentials": "true",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        }

        # SECURITY: Standardize event structure with validation
        standardized_event = {
            "httpMethod": InputValidator.sanitize_string(event.get("httpMethod", "GET"), 10),
            "path": InputValidator.sanitize_string(event.get("path", "/api/health"), 200),
            "headers": event.get("headers", {}),
            "multiValueHeaders": event.get("multiValueHeaders", {}),
            "queryStringParameters": event.get("queryStringParameters", {}),
            "multiValueQueryStringParameters": event.get("multiValueQueryStringParameters", {}),
            "body": event.get("body"),
            "isBase64Encoded": bool(event.get("isBase64Encoded", False)),
            "pathParameters": event.get("pathParameters", {}),
            "stageVariables": event.get("stageVariables", {}),
            "requestContext": event.get(
                "requestContext",
                {
                    "requestId": context.aws_request_id if context else f"local-{uuid.uuid4().hex[:8]}",
                    "stage": "prod",
                    "httpMethod": event.get("httpMethod", "GET"),
                    "path": event.get("path", "/api/health"),
                    "identity": {"sourceIp": "127.0.0.1", "userAgent": "AWS Lambda"},
                    "requestTime": datetime.utcnow().strftime("%d/%b/%Y:%H:%M:%S +0000"),
                    "requestTimeEpoch": int(datetime.utcnow().timestamp() * 1000),
                },
            ),
        }

        # SECURITY: Direct health check with minimal data exposure
        if standardized_event["path"] in ["/api/health", "/health", "/"]:
            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps(
                    {
                        "status": "success",
                        "message": "API is operational",
                        "version": CONFIG["VERSION"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "features": ["authentication", "subscriber_management", "audit_logging", "csv_migration", "performance_dashboard", "provisioning"],
                    }
                ),
                "isBase64Encoded": False,
            }

        # Process through Flask with security middleware
        response = handle_request(app, standardized_event, context)

        # SECURITY: Ensure security headers are always present
        if "headers" not in response:
            response["headers"] = {}
        response["headers"].update(cors_headers)

        # SECURITY: Remove server identification headers
        response["headers"].pop("Server", None)
        response["headers"].pop("X-Powered-By", None)

        return response

    except Exception as e:
        # SECURITY: Comprehensive error handling without information disclosure
        error_id = uuid.uuid4().hex[:8]
        logger.error("Lambda handler error [%s]: %s", error_id, str(e))

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Access-Control-Allow-Origin": CONFIG["FRONTEND_ORIGIN"],
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            },
            "body": json.dumps(
                {
                    "status": "error",
                    "message": "Service temporarily unavailable",
                    "timestamp": datetime.utcnow().isoformat(),
                    "error_id": error_id,  # Reference for support without exposing details
                }
            ),
            "isBase64Encoded": False,
        }


# SECURITY: Secure application startup
if __name__ == "__main__":
    # SECURITY: Only run in debug mode if explicitly enabled
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    if debug_mode:
        logger.warning("Running in DEBUG mode - not suitable for production")

    app.run(
        host="127.0.0.1",  # SECURITY: Bind to localhost only
        port=5000,
        debug=debug_mode,
        threaded=True,
        ssl_context="adhoc" if not debug_mode else None,  # HTTPS in production
    )
