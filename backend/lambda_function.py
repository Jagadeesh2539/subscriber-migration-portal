#!/usr/bin/env python3
"""
Subscriber Migration Portal - Complete Production Lambda Handler
Version: 4.3-production

Features:
- Full CRUD operations for subscribers (CLOUD/LEGACY/HYBRID modes)
- Mode-independent RDS → DynamoDB migration with detailed reports
- Bulk deletion from DynamoDB with detailed reports
- SQL query export to CSV/Excel
- Job cancellation
- Comprehensive health check for all components
- Detailed UID-level tracking with downloadable reports
"""

import json
import logging
import os
import uuid
import base64
import io
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
import jwt
import pymysql
from boto3.dynamodb.conditions import Attr
import re
from boto3.dynamodb.types import TypeDeserializer

# ================================ LOGGING ====================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================== CONFIGURATION ================================
CONFIG = {
    "VERSION": "4.3-production",
    "JWT_SECRET": os.getenv("JWT_SECRET", "SXxxqrDnwcb4l9D9GEjZUzdAOzGAa2Teu8ApD4n7ZUiEfqXs0LQk9DxuEzF8d0Er"),
    "JWT_ALGORITHM": "HS256",
    "JWT_EXPIRY_HOURS": 8,
    "SUBSCRIBER_TABLE_NAME": os.getenv("SUBSCRIBER_TABLE_NAME", "subscriber-migration-portal-prod-subscribers-20251031"),
    "JOBS_TABLE_NAME": os.getenv("MIGRATION_JOBS_TABLE_NAME", "subscriber-migration-portal-prod-jobs-20251031"),
    "SETTINGS_TABLE_NAME": os.getenv("SETTINGS_TABLE", "subscriber-migration-portal-prod-settings-20251031"),
    "UPLOADS_BUCKET": os.getenv("UPLOADS_BUCKET", "subscriber-migration-portal-prod-uploadsbucket-0mw5pccabh0h"),
    "LEGACY_DB_SECRET_ARN": os.getenv("LEGACY_DB_SECRET_ARN"),
    "LEGACY_DB_HOST": os.getenv("LEGACY_DB_HOST"),
    "LEGACY_DB_PORT": int(os.getenv("LEGACY_DB_PORT", "3306")),
    "LEGACY_DB_NAME": os.getenv("LEGACY_DB_NAME", os.getenv("DB_NAME", "legacydb")),
    "CORS_ORIGIN": os.getenv("CORS_ORIGINS", "*"),
    "MAX_MIGRATION_BATCH": 200,
}

# AWS Clients
dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")
dynamodb_client = boto3.client('dynamodb') # <-- ADD new

# Boto3 utilities
deserializer = TypeDeserializer() # <-- ADD new

# Tables
subscribers_table = dynamodb.Table(CONFIG["SUBSCRIBER_TABLE_NAME"])
jobs_table = dynamodb.Table(CONFIG["JOBS_TABLE_NAME"])
settings_table = dynamodb.Table(CONFIG["SETTINGS_TABLE_NAME"])

# RDS credentials cache
_rds_credentials = None

# ============================ UTILITY FUNCTIONS ==============================
def get_cors_headers():
    origin = CONFIG.get(
        "CORS_ORIGIN",
        "http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com"
    )
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "Authorization,Content-Type,X-Requested-With",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Vary": "Origin",
    }


def create_response(data=None, message="Success", status_code=200):
    """Create standardized API response"""
    body = {
        "status": "success" if status_code < 400 else "error",
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if data is not None:
        body["data"] = json.loads(json.dumps(data, default=str))
    return {
        'statusCode': status_code,
        'headers': get_cors_headers(),
        'body': json.dumps(body)
    }

def generate_report_csv(job_details: List[Dict], job_type: str) -> str:
    """Generate detailed CSV report for migration/deletion job"""
    output = io.StringIO()
    if job_type == 'MIGRATION':
        fieldnames = ['uid', 'status', 'reason', 'imsi', 'msisdn', 'email', 'timestamp']
    else:  # DELETION
        fieldnames = ['uid', 'status', 'reason', 'timestamp']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(job_details)
    return output.getvalue()

# ========================== MODE MANAGEMENT ==================================
def get_provisioning_mode() -> str:
    """Get current provisioning mode from DynamoDB settings table"""
    try:
        response = settings_table.get_item(Key={'sk': 'provisioning_mode'})
        if 'Item' in response:
            return response['Item']['setting_value'].upper()
    except Exception as e:
        logger.error(f"Error getting provisioning mode: {e}")
    return 'CLOUD'

# ============================ AUTHENTICATION =================================
def authenticate(username: str, password: str) -> Optional[Dict]:
    """Authenticate user (simple admin/password for now)"""
    if username == "admin" and password == "password":
        return {
            "username": "admin",
            "role": "admin",
            "permissions": ["read", "write", "admin"]
        }
    return None

def generate_jwt_token(user_data: Dict) -> str:
    """Generate JWT token for authenticated user"""
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "permissions": user_data["permissions"],
        "exp": datetime.utcnow() + timedelta(hours=CONFIG["JWT_EXPIRY_HOURS"]),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, CONFIG["JWT_SECRET"], algorithm=CONFIG["JWT_ALGORITHM"])

def verify_jwt_token(token: str) -> Optional[Dict]:
    """Verify JWT token and return user data"""
    try:
        payload = jwt.decode(token, CONFIG["JWT_SECRET"], algorithms=[CONFIG["JWT_ALGORITHM"]])
        return {
            "username": payload["sub"],
            "role": payload["role"],
            "permissions": payload["permissions"]
        }
    except:
        return None

def require_auth(event: Dict) -> Optional[Dict]:
    """Extract and verify JWT from Authorization header"""
    headers = event.get('headers') or {}
    auth_header = headers.get('Authorization') or headers.get('authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    return verify_jwt_token(token)

# ======================== DATABASE CONNECTIVITY =============================
def get_rds_credentials():
    """Get RDS credentials from Secrets Manager (cached)"""
    global _rds_credentials
    if _rds_credentials is None:
        try:
            response = secrets_client.get_secret_value(SecretId=CONFIG["LEGACY_DB_SECRET_ARN"])
            _rds_credentials = json.loads(response['SecretString'])
        except Exception as e:
            logger.error(f"Error getting RDS credentials: {e}")
            _rds_credentials = {}
    return _rds_credentials

def get_rds_connection():
    """Create MySQL RDS connection"""
    creds = get_rds_credentials()
    if not creds:
        raise Exception("RDS credentials not available")
    return pymysql.connect(
        host=CONFIG["LEGACY_DB_HOST"],
        port=CONFIG["LEGACY_DB_PORT"],
        user=creds['username'],
        password=creds['password'],
        database=CONFIG["LEGACY_DB_NAME"],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        autocommit=False
    )

# =========================== HELPER FUNCTIONS ================================
def check_subscriber_exists_cloud(uid: str) -> bool:
    """Check if subscriber exists in DynamoDB"""
    try:
        response = subscribers_table.get_item(Key={'uid': uid})
        return 'Item' in response
    except:
        return False

def check_subscriber_exists_legacy(uid: str) -> bool:
    """Check if subscriber exists in RDS"""
    try:
        conn = get_rds_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE uid = %s", (uid,))
            result = cursor.fetchone()
            count = result['count'] if result else 0
        conn.close()
        return count > 0
    except:
        return False

def check_unique_fields_cloud(imsi: str, msisdn: str, exclude_uid: str = None) -> List[str]:
    """Check for duplicate IMSI/MSISDN in DynamoDB"""
    conflicts = []
    try:
        for field, value in [('imsi', imsi), ('msisdn', msisdn)]:
            if value:
                response = subscribers_table.scan(
                    FilterExpression=Attr(field).eq(value),
                    Limit=1
                )
                if response.get('Items'):
                    item = response['Items'][0]
                    if exclude_uid is None or item['uid'] != exclude_uid:
                        conflicts.append(f"{field.upper()} {value} exists in Cloud (UID: {item['uid']})")
    except Exception as e:
        logger.error(f"Error checking unique fields in cloud: {e}")
    return conflicts

def check_unique_fields_legacy(imsi: str, msisdn: str, exclude_uid: str = None) -> List[str]:
    """Check for duplicate IMSI/MSISDN in RDS"""
    conflicts = []
    try:
        conn = get_rds_connection()
        with conn.cursor() as cursor:
            for field, value in [('imsi', imsi), ('msisdn', msisdn)]:
                if value:
                    query = f"SELECT uid FROM subscribers WHERE {field} = %s"
                    params = [value]
                    if exclude_uid:
                        query += " AND uid != %s"
                        params.append(exclude_uid)
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    if result:
                        conflicts.append(f"{field.upper()} {value} exists in Legacy (UID: {result['uid']})")
        conn.close()
    except Exception as e:
        logger.error(f"Error checking unique fields in legacy: {e}")
    return conflicts

# ======================== ROUTE HANDLERS =====================================

# -------------------- Health Check Handler -----------------------------------
def handle_health(event):
    """
    Comprehensive health check for all backend components
    Checks: DynamoDB, RDS MySQL, S3, Secrets Manager, VPC, Provisioning Mode
    """
    components = {}
    warnings = []
    # DynamoDB
    dynamodb_details = {}
    try:
        subscribers_table.scan(Limit=1, Select='COUNT')
        total_estimate = subscribers_table.item_count
        dynamodb_details['subscribers_table'] = {
            "status": "healthy",
            "table_name": CONFIG["SUBSCRIBER_TABLE_NAME"],
            "item_count": total_estimate,
            "accessible": True
        }
    except Exception as e:
        dynamodb_details['subscribers_table'] = {
            "status": "error",
            "table_name": CONFIG["SUBSCRIBER_TABLE_NAME"],
            "error": str(e),
            "accessible": False
        }
    try:
        job_count = jobs_table.item_count
        dynamodb_details['jobs_table'] = {
            "status": "healthy",
            "table_name": CONFIG["JOBS_TABLE_NAME"],
            "item_count": job_count,
            "accessible": True
        }
    except Exception as e:
        dynamodb_details['jobs_table'] = {
            "status": "error",
            "table_name": CONFIG["JOBS_TABLE_NAME"],
            "error": str(e),
            "accessible": False
        }
    try:
        response = settings_table.get_item(Key={'sk': 'provisioning_mode'})
        current_mode = response.get('Item', {}).get('setting_value', 'NOT_SET')
        dynamodb_details['settings_table'] = {
            "status": "healthy",
            "table_name": CONFIG["SETTINGS_TABLE_NAME"],
            "current_mode": current_mode,
            "accessible": True
        }
    except Exception as e:
        dynamodb_details['settings_table'] = {
            "status": "error",
            "table_name": CONFIG["SETTINGS_TABLE_NAME"],
            "error": str(e),
            "accessible": False
        }
        current_mode = "UNKNOWN"
    dynamodb_healthy = all(tbl.get("status") == "healthy" for tbl in dynamodb_details.values())
    components['dynamodb'] = {
        "status": "healthy" if dynamodb_healthy else "error",
        "details": dynamodb_details,
        "summary": f"{len([t for t in dynamodb_details.values() if t.get('status') == 'healthy'])}/3 tables healthy"
    }
    # RDS
    rds_details = {}
    required_rds_vars = {
        "LEGACY_DB_SECRET_ARN": CONFIG.get("LEGACY_DB_SECRET_ARN"),
        "LEGACY_DB_HOST": CONFIG.get("LEGACY_DB_HOST"),
        "LEGACY_DB_PORT": CONFIG.get("LEGACY_DB_PORT"),
        "LEGACY_DB_NAME": CONFIG.get("LEGACY_DB_NAME"),
    }
    missing_vars = [k for k, v in required_rds_vars.items() if not v]
    if missing_vars:
        components['legacy_rds'] = {
            "status": "error",
            "details": {"error": f"Missing environment variables: {', '.join(missing_vars)}", "configured": False},
            "summary": "Not configured"
        }
    else:
        try:
            creds = get_rds_credentials()
            if not creds or not creds.get('username') or not creds.get('password'):
                raise ValueError("Invalid credentials")
            rds_details['secrets_manager'] = {
                "status": "healthy",
                "secret_arn": CONFIG["LEGACY_DB_SECRET_ARN"],
                "credentials_retrieved": True
            }
        except Exception as e:
            rds_details['secrets_manager'] = {
                "status": "error",
                "secret_arn": CONFIG["LEGACY_DB_SECRET_ARN"],
                "error": str(e),
                "credentials_retrieved": False
            }
        try:
            conn = get_rds_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 as ping")
                result = cursor.fetchone()
                if not result or result.get('ping') != 1:
                    raise ValueError("Ping test failed")
            rds_details['connection'] = {
                "status": "healthy",
                "host": CONFIG["LEGACY_DB_HOST"],
                "port": CONFIG["LEGACY_DB_PORT"],
                "database": CONFIG["LEGACY_DB_NAME"],
                "connected": True
            }
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers")
                    result = cursor.fetchone()
                    subscriber_count = result.get('count', 0) if result else 0
                    cursor.execute("DESCRIBE subscribers")
                    columns = cursor.fetchall()
                    column_names = [col['Field'] for col in columns]
                rds_details['subscribers_table'] = {
                    "status": "healthy",
                    "exists": True,
                    "row_count": subscriber_count,
                    "columns": column_names,
                    "column_count": len(column_names)
                }
            except Exception as e:
                rds_details['subscribers_table'] = {
                    "status": "error",
                    "exists": False,
                    "error": str(e)
                }
            conn.close()
        except Exception as e:
            rds_details['connection'] = {
                "status": "error",
                "host": CONFIG.get("LEGACY_DB_HOST", "NOT_SET"),
                "error": str(e),
                "connected": False
            }
        rds_healthy = all(comp.get("status") == "healthy" for comp in rds_details.values())
        components['legacy_rds'] = {
            "status": "healthy" if rds_healthy else "error",
            "details": rds_details,
            "summary": f"{len([c for c in rds_details.values() if c.get('status') == 'healthy'])}/{len(rds_details)} components healthy"
        }
    # S3
    try:
        bucket_name = CONFIG["UPLOADS_BUCKET"]
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        location = s3_client.get_bucket_location(Bucket=bucket_name)
        components['s3_uploads'] = {
            "status": "healthy",
            "details": {
                "bucket_name": bucket_name,
                "accessible": True,
                "region": location.get('LocationConstraint', 'us-east-1'),
                "object_count_sample": response.get('KeyCount', 0)
            },
            "summary": "S3 bucket accessible"
        }
    except Exception as e:
        components['s3_uploads'] = {
            "status": "error",
            "details": {"bucket_name": CONFIG.get("UPLOADS_BUCKET", "NOT_SET"), "accessible": False, "error": str(e)},
            "summary": "S3 bucket not accessible"
        }
    # VPC info (best effort)
    try:
        lambda_client = boto3.client('lambda')
        function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        if function_name:
            func_config = lambda_client.get_function_configuration(FunctionName=function_name)
            vpc_config = func_config.get('VpcConfig', {})
            if vpc_config.get('VpcId'):
                vpc_info = {
                    "status": "healthy",
                    "vpc_id": vpc_config.get('VpcId'),
                    "subnet_ids": vpc_config.get('SubnetIds', []),
                    "security_group_ids": vpc_config.get('SecurityGroupIds', []),
                    "in_vpc": True
                }
            else:
                vpc_info = {"status": "info", "in_vpc": False, "note": "Lambda not in VPC"}
            components['vpc'] = {
                "status": vpc_info.get("status", "info"),
                "details": vpc_info,
                "summary": "In VPC" if vpc_info.get("in_vpc") else "Not in VPC"
            }
    except Exception as e:
        components['vpc'] = {"status": "info", "details": {"error": str(e)}, "summary": "VPC info unavailable"}
    # Mode
    try:
        mode = get_provisioning_mode()
        components['provisioning_mode'] = {
            "status": "healthy",
            "details": {"current_mode": mode, "valid_modes": ["CLOUD", "LEGACY", "HYBRID"], "source": "DynamoDB settings table"},
            "summary": f"Current mode: {mode}"
        }
    except Exception as e:
        components['provisioning_mode'] = {"status": "error", "details": {"error": str(e)}, "summary": "Unable to determine mode"}
        mode = "UNKNOWN"
    # Overall
    critical_healthy = all(components.get(comp, {}).get("status") == "healthy" for comp in ['dynamodb', 'legacy_rds'])
    all_healthy = all(components.get(comp, {}).get("status") in ["healthy", "info"] for comp in components.keys())
    if critical_healthy and all_healthy:
        overall_status = "healthy"
    elif critical_healthy:
        overall_status = "healthy_with_warnings"
    else:
        overall_status = "degraded"
    response_data = {
        "status": overall_status,
        "version": CONFIG["VERSION"],
        "timestamp": datetime.utcnow().isoformat(),
        "mode": mode,
        "components": components,
        "summary": {
            "total_components": len(components),
            "healthy_components": len([c for c in components.values() if c.get("status") == "healthy"]),
            "error_components": len([c for c in components.values() if c.get("status") == "error"]),
        }
    }
    message = "All systems operational" if overall_status == "healthy" else ("System operational with warnings" if overall_status == "healthy_with_warnings" else "System degraded - critical components have errors")
    return create_response(data=response_data, message=message, status_code=200 if overall_status != "degraded" else 503)

# -------------------- Authentication Handler ---------------------------------
def handle_login(event):
    """User login endpoint"""
    try:
        body = json.loads(event.get('body', '{}'))
        username = body.get('username')
        password = body.get('password')
        if not username or not password:
            return create_response(message="Username and password required", status_code=400)
        user = authenticate(username, password)
        if not user:
            return create_response(message="Invalid credentials", status_code=401)
        token = generate_jwt_token(user)
        return create_response(
            data={
                'token': token,
                'user': {'username': user['username'], 'role': user['role'], 'permissions': user['permissions']},
                'expires_in': CONFIG['JWT_EXPIRY_HOURS'] * 3600
            }
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        return create_response(message="Authentication failed", status_code=500)

# -------------------- Dashboard Handlers -------------------------------------
def handle_dashboard_stats(event):
    """Dashboard statistics endpoint (HYBRID shows Cloud-only)"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)

    mode = (get_provisioning_mode() or 'CLOUD').upper()

    # In HYBRID, we will only compute Cloud counts and set Legacy = 0
    count_cloud  = mode in ('CLOUD', 'HYBRID')
    count_legacy = mode == 'LEGACY'  # <- not counted in HYBRID

    stats = {
        'totalSubscribers': 0,
        'cloudSubscribers': 0,
        'legacySubscribers': 0,
        'systemHealth': 'healthy',
        'provisioningMode': mode,
        'lastUpdated': datetime.utcnow().isoformat() + 'Z',
    }

    # CLOUD (DynamoDB)
    if count_cloud:
        try:
            subscribers_table.load()                         # refreshes .item_count
            response = subscribers_table.scan(Select='COUNT')
            stats['cloudSubscribers'] = int(response.get('Count', 0))
        except Exception as e:
            logger.error(f"Error getting cloud subscriber count: {e}")
            stats['systemHealth'] = 'degraded'

    # LEGACY (MySQL) — skipped in HYBRID by design
    if count_legacy:
        conn = None
        try:
            conn = get_rds_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM subscribers")
                row = cursor.fetchone()
                legacy_cnt = row['count'] if (row and isinstance(row, dict) and 'count' in row) else (row[0] if row else 0)
                stats['legacySubscribers'] = int(legacy_cnt)
        except Exception as e:
            logger.error(f"Error counting legacy subscribers: {e}")
            stats['systemHealth'] = 'degraded'
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    # HYBRID => total = cloud only; LEGACY/CLOUD => sum of what we counted
    stats['totalSubscribers'] = int(stats['cloudSubscribers']) + (int(stats['legacySubscribers']) if count_legacy else 0)

    return create_response(data=stats)


def handle_dashboard_performance(event):
    """Dashboard performance metrics"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        jobs = jobs_table.scan().get('Items', [])
        return create_response(data={
            'migration_stats': {
                'total_jobs': len(jobs),
                'completed_jobs': len([j for j in jobs if j.get('status') == 'COMPLETED']),
                'failed_jobs': len([j for j in jobs if j.get('status') == 'FAILED']),
                'in_progress_jobs': len([j for j in jobs if j.get('status') in ['PENDING', 'RUNNING']]),
                'total_migrated': sum(int(j.get('successful_items', 0)) for j in jobs),
                'total_failed': sum(int(j.get('failed_items', 0)) for j in jobs),
            },
            'system_health': {'database_status': 'healthy', 'api_status': 'healthy'},
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Dashboard performance error: {e}")
        return create_response(message="Failed to get performance metrics", status_code=500)

# -------------------- Subscriber CRUD Handlers -------------------------------
def handle_search_subscribers(event):
    """Search subscribers with exact match"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    # Support GET query param and POST body aliases
    params = event.get('queryStringParameters') or {}
    if not params and event.get('body'):
        try:
            body = json.loads(event['body'])
            q = body.get('q')
            if q:
                params = {'q': q}
        except:
            pass
    query = (params.get('q') or '').strip()
    if not query:
        return create_response(data={'subscribers': [], 'count': 0})
    mode = get_provisioning_mode()
    results = []
    if mode in ['CLOUD', 'HYBRID']:
        try:
            response = subscribers_table.get_item(Key={'uid': query})
            if 'Item' in response:
                response['Item']['_source'] = 'cloud'
                results.append(response['Item'])
            if not results:
                response = subscribers_table.scan(FilterExpression=Attr('imsi').eq(query), Limit=1)
                for item in response.get('Items', []):
                    item['_source'] = 'cloud'
                    results.append(item)
            if not results:
                response = subscribers_table.scan(FilterExpression=Attr('msisdn').eq(query), Limit=1)
                for item in response.get('Items', []):
                    item['_source'] = 'cloud'
                    results.append(item)
        except Exception as e:
            logger.error(f"Cloud search error: {e}")
    if mode in ['LEGACY', 'HYBRID'] and not results:
        try:
            conn = get_rds_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM subscribers WHERE uid = %s OR imsi = %s OR msisdn = %s LIMIT 1", (query, query, query))
                for row in cursor.fetchall():
                    row['_source'] = 'legacy'
                    results.append(row)
            conn.close()
        except Exception as e:
            logger.error(f"Legacy search error: {e}")
    return create_response(data={'subscribers': results, 'count': len(results)})

def handle_create_subscriber(event):
    """Create new subscriber"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        body = json.loads(event.get('body', '{}'))
        uid = body.get('uid')
        imsi = body.get('imsi', '')
        msisdn = body.get('msisdn', '')
        if not uid:
            return create_response(message="UID is required", status_code=400)
        mode = get_provisioning_mode()
        exists_cloud = check_subscriber_exists_cloud(uid) if mode in ['CLOUD', 'HYBRID'] else False
        exists_legacy = check_subscriber_exists_legacy(uid) if mode in ['LEGACY', 'HYBRID'] else False
        if exists_cloud or exists_legacy:
            return create_response(message=f"Subscriber {uid} already exists", status_code=409)
        conflicts = []
        if mode in ['CLOUD', 'HYBRID']:
            conflicts.extend(check_unique_fields_cloud(imsi, msisdn))
        if mode in ['LEGACY', 'HYBRID']:
            conflicts.extend(check_unique_fields_legacy(imsi, msisdn))
        if conflicts:
            return create_response(message="Duplicate IMSI or MSISDN found", data={'conflicts': conflicts}, status_code=409)
        subscriber = {
            'uid': uid,
            'imsi': imsi,
            'msisdn': msisdn,
            'email': body.get('email', ''),
            'status': body.get('status', 'ACTIVE'),
            'plan': body.get('plan', ''),
            'created_at': datetime.utcnow().isoformat(),
            'created_by': user['username']
        }
        results = {'mode': mode, 'cloud': False, 'legacy': False}
        if mode in ['CLOUD', 'HYBRID']:
            try:
                subscribers_table.put_item(Item=subscriber, ConditionExpression='attribute_not_exists(uid)')
                results['cloud'] = True
            except Exception as e:
                logger.error(f"Error creating in cloud: {e}")
                return create_response(message=f"Failed to create in cloud: {str(e)}", status_code=500)
        if mode in ['LEGACY', 'HYBRID']:
            try:
                conn = get_rds_connection()
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO subscribers (uid, imsi, msisdn, email, status, plan, created_at, created_by)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (uid, imsi, msisdn, subscriber['email'], subscriber['status'], subscriber['plan'], subscriber['created_at'], subscriber['created_by'])
                    )
                    conn.commit()
                results['legacy'] = True
                conn.close()
            except Exception as e:
                logger.error(f"Error creating in legacy: {e}")
                if mode == 'HYBRID' and results['cloud']:
                    try:
                        subscribers_table.delete_item(Key={'uid': uid})
                    except:
                        pass
                return create_response(message=f"Failed to create in legacy: {str(e)}", status_code=500)
        subscriber['_provisioning'] = results
        return create_response(data=subscriber, message=f"Subscriber created in {mode} mode")
    except Exception as e:
        logger.error(f"Create subscriber error: {e}")
        return create_response(message=str(e), status_code=500)

def handle_get_subscriber(event, uid):
    """Get subscriber by UID"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    mode = get_provisioning_mode()
    if mode in ['CLOUD', 'HYBRID']:
        try:
            response = subscribers_table.get_item(Key={'uid': uid})
            if 'Item' in response:
                response['Item']['_source'] = 'cloud'
                return create_response(data=response['Item'])
        except Exception as e:
            logger.error(f"Cloud get error: {e}")
    if mode in ['LEGACY', 'HYBRID']:
        try:
            conn = get_rds_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (uid,))
                result = cursor.fetchone()
                if result:
                    result['_source'] = 'legacy'
                    conn.close()
                    return create_response(data=result)
            conn.close()
        except Exception as e:
            logger.error(f"Legacy get error: {e}")
    return create_response(message="Subscriber not found", status_code=404)

def handle_update_subscriber(event, uid):
    """Update subscriber"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        body = json.loads(event.get('body', '{}'))
        mode = get_provisioning_mode()
        exists_cloud = check_subscriber_exists_cloud(uid) if mode in ['CLOUD', 'HYBRID'] else False
        exists_legacy = check_subscriber_exists_legacy(uid) if mode in ['LEGACY', 'HYBRID'] else False
        if not exists_cloud and not exists_legacy:
            return create_response(message=f"Subscriber {uid} not found", status_code=404)
        conflicts = []
        if mode in ['CLOUD', 'HYBRID']:
            conflicts.extend(check_unique_fields_cloud(body.get('imsi', ''), body.get('msisdn', ''), exclude_uid=uid))
        if mode in ['LEGACY', 'HYBRID']:
            conflicts.extend(check_unique_fields_legacy(body.get('imsi', ''), body.get('msisdn', ''), exclude_uid=uid))
        if conflicts:
            return create_response(message="Duplicate fields found", data={'conflicts': conflicts}, status_code=409)
        updated = {'cloud': False, 'legacy': False}
        if mode in ['CLOUD', 'HYBRID'] and exists_cloud:
            try:
                update_expr = "SET "
                expr_values = {}
                expr_names = {}
                updates = []
                for field in ['imsi', 'msisdn', 'email', 'status', 'plan']:
                    if field in body:
                        updates.append(f"#{field} = :{field}")
                        expr_values[f":{field}"] = body[field]
                        expr_names[f"#{field}"] = field
                if updates:
                    update_expr += ", ".join(updates) + ", #updated_at = :updated_at"
                    expr_values[':updated_at'] = datetime.utcnow().isoformat()
                    expr_names['#updated_at'] = 'updated_at'
                    subscribers_table.update_item(Key={'uid': uid}, UpdateExpression=update_expr, ExpressionAttributeValues=expr_values, ExpressionAttributeNames=expr_names)
                    updated['cloud'] = True
            except Exception as e:
                logger.error(f"Cloud update error: {e}")
        if mode in ['LEGACY', 'HYBRID'] and exists_legacy:
            try:
                conn = get_rds_connection()
                with conn.cursor() as cursor:
                    set_clauses = []
                    values = []
                    for field in ['imsi', 'msisdn', 'email', 'status', 'plan']:
                        if field in body:
                            set_clauses.append(f"{field} = %s")
                            values.append(body[field])
                    if set_clauses:
                        set_clauses.append("updated_at = %s")
                        values.append(datetime.utcnow().isoformat())
                        values.append(uid)
                        cursor.execute(f"UPDATE subscribers SET {', '.join(set_clauses)} WHERE uid = %s", values)
                        conn.commit()
                        updated['legacy'] = True
                conn.close()
            except Exception as e:
                logger.error(f"Legacy update error: {e}")
        return create_response(data={'uid': uid, 'updated': updated})
    except Exception as e:
        logger.error(f"Update error: {e}")
        return create_response(message=str(e), status_code=500)

def handle_delete_subscriber(event, uid):
    """Delete subscriber"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    mode = get_provisioning_mode()
    deleted = {'cloud': False, 'legacy': False}
    if mode in ['CLOUD', 'HYBRID']:
        try:
            response = subscribers_table.delete_item(Key={'uid': uid}, ReturnValues='ALL_OLD')
            deleted['cloud'] = 'Attributes' in response
        except Exception as e:
            logger.error(f"Cloud delete error: {e}")
    if mode in ['LEGACY', 'HYBRID']:
        try:
            conn = get_rds_connection()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM subscribers WHERE uid = %s", (uid,))
                deleted['legacy'] = cursor.rowcount > 0
                if deleted['legacy']:
                    conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Legacy delete error: {e}")
    if deleted['cloud'] or deleted['legacy']:
        return create_response(data={'deleted': deleted})
    else:
        return create_response(message="Subscriber not found", status_code=404)

def handle_list_subscribers(event):
    """List all subscribers"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    mode = get_provisioning_mode()
    all_subscribers = []
    if mode in ['CLOUD', 'HYBRID']:
        try:
            response = subscribers_table.scan()
            for sub in response.get('Items', []):
                sub['_source'] = 'cloud'
                all_subscribers.append(sub)
        except Exception as e:
            logger.error(f"Cloud list error: {e}")
    if mode in ['LEGACY', 'HYBRID']:
        try:
            conn = get_rds_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM subscribers")
                for sub in cursor.fetchall():
                    sub['_source'] = 'legacy'
                    all_subscribers.append(sub)
            conn.close()
        except Exception as e:
            logger.error(f"Legacy list error: {e}")
    return create_response(data={'subscribers': all_subscribers, 'count': len(all_subscribers), 'mode': mode})

def handle_query_subscribers(event):
    """Query subscribers with specific criteria"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        body = json.loads(event.get('body', '{}'))
        query_type = body.get('query_type') or body.get('querytype')
        query_value = body.get('query_value') or body.get('queryvalue')
        if not query_value or not query_type:
            return create_response(data={'results': [], 'count': 0})
        data_source = body.get('data_source', 'both').lower()  # 'cloud', 'legacy', or 'both'
        results = []
        if data_source in ['cloud', 'both']:
            try:
                if query_type == 'uid':
                    response = subscribers_table.get_item(Key={'uid': query_value})
                    if 'Item' in response:
                        response['Item']['_source'] = 'cloud'
                        results.append(response['Item'])
                else:
                    response = subscribers_table.scan(FilterExpression=Attr(query_type).eq(query_value))
                    for item in response.get('Items', []):
                        item['_source'] = 'cloud'
                        results.append(item)
            except Exception as e:
                logger.error(f"Cloud query error: {e}")
        if data_source in ['legacy', 'both']:
            try:
                conn = get_rds_connection()
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT * FROM subscribers WHERE {query_type} = %s", (query_value,))
                    for row in cursor.fetchall():
                        row['_source'] = 'legacy'
                        results.append(row)
                conn.close()
            except Exception as e:
                logger.error(f"Legacy query error: {e}")
        return create_response(data={'results': results, 'count': len(results), 'queried_source': data_source})
    except Exception as e:
        logger.error(f"Query error: {e}")
        return create_response(message=str(e), status_code=500)

# -------------------- Migration Handlers -------------------------------------
def parse_multipart_formdata(body: str, content_type: str, is_base64: bool = False) -> Optional[str]:
    """
    Parse multipart/form-data request body to extract file content.
    """
    try:
        if 'multipart/form-data' not in content_type:
            logger.warning(f"Invalid content type for multipart parsing: {content_type}")
            return None
        if 'boundary=' not in content_type:
            logger.error("No boundary found in Content-Type header")
            return None
        boundary = content_type.split('boundary=')[-1].strip()
        try:
            body_bytes = base64.b64decode(body) if is_base64 else (body.encode('utf-8') if isinstance(body, str) else body)
        except Exception as e:
            logger.error(f"Failed to decode body: {e}")
            return None
        boundary_bytes = f'--{boundary}'.encode()
        parts = body_bytes.split(boundary_bytes)
        file_content = None
        for part in parts:
            if not part or part == b'--\r\n' or part == b'--':
                continue
            if b'Content-Disposition' in part and b'filename=' in part:
                content_start = part.find(b'\r\n\r\n')
                if content_start == -1:
                    content_start = part.find(b'\n\n')
                    if content_start != -1:
                        content_start += 2
                else:
                    content_start += 4
                if content_start == -1:
                    continue
                raw_content = part[content_start:]
                raw_content = raw_content.rstrip(b'\r\n').rstrip(b'\n')
                try:
                    file_content = raw_content.decode('utf-8')
                    break
                except UnicodeDecodeError:
                    try:
                        file_content = raw_content.decode('latin-1')
                        break
                    except Exception:
                        continue
        if file_content is None:
            logger.error("No file content found in any part")
            return None
        return file_content.strip()
    except Exception as e:
        logger.error(f"Multipart parsing error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def handle_migrate_from_rds(event):
    """Mode-independent migration from RDS → DynamoDB with detailed tracking"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        headers = event.get('headers') or {}
        content_type = headers.get('content-type', '') or headers.get('Content-Type', '')
        file_content = None
        if 'multipart/form-data' in content_type:
            file_content = parse_multipart_formdata(body, content_type, is_base64)
            if not file_content:
                return create_response(message="Failed to parse file upload. Please ensure you're uploading a valid CSV file.", status_code=400)
        elif 'application/json' in content_type:
            try:
                json_body = json.loads(body)
                file_content = json_body.get('file', '')
                if not file_content:
                    return create_response(message="'file' field is required in JSON body", status_code=400)
            except json.JSONDecodeError:
                return create_response(message="Invalid JSON in request body", status_code=400)
        else:
            return create_response(message=f"Unsupported Content-Type: {content_type}. Use multipart/form-data or application/json", status_code=415)
        if not file_content or not file_content.strip():
            return create_response(message="Uploaded file is empty", status_code=400)
        # Extract UIDs
        uids = []
        try:
            csv_reader = csv.DictReader(io.StringIO(file_content))
            if not csv_reader.fieldnames:
                return create_response(message="CSV file has no headers", status_code=400)
            for row in csv_reader:
                uid = row.get('uid') or row.get('UID') or row.get('Uid')
                if uid and uid.strip():
                    uids.append(uid.strip())
        except csv.Error as e:
            return create_response(message=f"Invalid CSV format: {str(e)}. Ensure file is properly formatted.", status_code=400)
        if not uids:
            return create_response(message="No valid UIDs found in CSV. Ensure the CSV has a 'uid' column with values.", status_code=400)
        # Create job
        job_id = f"migrate_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        s3_key_input = f"migrations/{job_id}/input.csv"
        s3_client.put_object(Bucket=CONFIG["UPLOADS_BUCKET"], Key=s3_key_input, Body=file_content, ContentType='text/csv')
        jobs_table.put_item(Item={
            'job_id': job_id,
            'type': 'MIGRATION',
            'status': 'RUNNING',
            'total_items': len(uids),
            'processed_items': 0,
            'successful_items': 0,
            'failed_items': 0,
            'progress': 0,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': user['username'],
            's3_input_key': s3_key_input,
        })
        # Process
        job_details = process_migration_with_details(job_id, uids)
        # Report
        report_csv = generate_report_csv(job_details, 'MIGRATION')
        s3_key_report = f"migrations/{job_id}/detailed_report.csv"
        s3_client.put_object(Bucket=CONFIG["UPLOADS_BUCKET"], Key=s3_key_report, Body=report_csv, ContentType='text/csv', ContentDisposition=f'attachment; filename=\"migration_report_{job_id}.csv\"')
        report_url = s3_client.generate_presigned_url('get_object', Params={'Bucket': CONFIG["UPLOADS_BUCKET"], 'Key': s3_key_report}, ExpiresIn=86400)
        successful = len([d for d in job_details if d['status'] == 'SUCCESS'])
        failed = len([d for d in job_details if d['status'] == 'FAILED'])
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :status, processed_items = :proc, successful_items = :succ, failed_items = :fail, progress = :prog, completed_at = :completed_at, report_s3_key = :report_key',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'COMPLETED' if failed == 0 else 'COMPLETED_WITH_ERRORS',
                ':proc': len(uids),
                ':succ': successful,
                ':fail': failed,
                ':prog': 100,
                ':completed_at': datetime.utcnow().isoformat(),
                ':report_key': s3_key_report
            }
        )
        return create_response(data={
            'job_id': job_id,
            'jobid': job_id,  # compatibility for frontend reading 'jobid'
            'total_items': len(uids),
            'successful': successful,
            'failed': failed,
            'report_download_url': report_url,
            'summary': {'success_rate': f"{(successful/len(uids)*100):.2f}%", 'total_processed': len(uids)}
        })
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return create_response(message=str(e), status_code=500)

def process_migration_with_details(job_id: str, uids: List[str]) -> List[Dict]:
    """Process migration and return detailed UID-level results"""
    job_details = []
    conn = get_rds_connection()
    for uid in uids:
        detail = {'uid': uid, 'status': '', 'reason': '', 'imsi': '', 'msisdn': '', 'email': '', 'timestamp': datetime.utcnow().isoformat()}
        try:
            if check_subscriber_exists_cloud(uid):
                detail['status'] = 'FAILED'
                detail['reason'] = 'Already exists in DynamoDB'
                job_details.append(detail)
                continue
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM subscribers WHERE uid = %s", (uid,))
                subscriber = cursor.fetchone()
            if not subscriber:
                detail['status'] = 'FAILED'
                detail['reason'] = 'Not found in RDS'
                job_details.append(detail)
                continue
            detail['imsi'] = subscriber.get('imsi', '')
            detail['msisdn'] = subscriber.get('msisdn', '')
            detail['email'] = subscriber.get('email', '')
            dynamodb_item = {
                'uid': subscriber['uid'],
                'imsi': subscriber.get('imsi', ''),
                'msisdn': subscriber.get('msisdn', ''),
                'email': subscriber.get('email', ''),
                'status': subscriber.get('status', 'ACTIVE'),
                'plan': subscriber.get('plan', ''),
                'created_at': str(subscriber.get('created_at', datetime.utcnow().isoformat())),
                'created_by': subscriber.get('created_by', 'migration'),
                'migrated_at': datetime.utcnow().isoformat(),
                'migrated_from': 'RDS',
                'migration_job_id': job_id
            }
            subscribers_table.put_item(Item=dynamodb_item)
            detail['status'] = 'SUCCESS'
            detail['reason'] = 'Successfully migrated from RDS to DynamoDB'
            job_details.append(detail)
        except Exception as e:
            detail['status'] = 'FAILED'
            detail['reason'] = f"Error: {str(e)}"
            job_details.append(detail)
            logger.error(f"Error migrating {uid}: {e}")
    conn.close()
    return job_details

# -------------------- Bulk Deletion Handler ----------------------------------
def handle_bulk_delete_cloud(event):
    """Bulk delete from DynamoDB with detailed tracking"""
    user = require_auth(event)
    if not user or 'admin' not in user.get('permissions', []):
        return create_response(message="Admin permission required", status_code=403)
    try:
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        headers = event.get('headers') or {}
        content_type = headers.get('content-type', '') or headers.get('Content-Type', '')
        if 'multipart/form-data' in content_type:
            file_content = parse_multipart_formdata(body, content_type, is_base64)
            if not file_content:
                return create_response(message="No file content found", status_code=400)
        else:
            # allow { "file": "...csv..." } or { "uids": ["..."] }
            try:
                payload = json.loads(body or '{}')
            except:
                payload = {}
            if 'uids' in payload and isinstance(payload.get('uids'), list) and payload['uids']:
                # synthesize a csv
                output = io.StringIO()
                w = csv.writer(output)
                w.writerow(['uid'])
                for u in payload['uids']:
                    w.writerow([u])
                file_content = output.getvalue()
            else:
                file_content = payload.get('file', '')
        # Extract UIDs
        uids = []
        try:
            csv_reader = csv.DictReader(io.StringIO(file_content))
            for row in csv_reader:
                uid = row.get('uid') or row.get('UID') or row.get('Uid')
                if uid:
                    uids.append(uid.strip())
        except Exception:
            pass
        if not uids:
            return create_response(message="No UIDs found for deletion", status_code=400)
        # Create job
        job_id = f"delete_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        s3_key_input = f"deletions/{job_id}/input.csv"
        s3_client.put_object(Bucket=CONFIG["UPLOADS_BUCKET"], Key=s3_key_input, Body=file_content, ContentType='text/csv')
        jobs_table.put_item(Item={
            'job_id': job_id,
            'type': 'BULK_DELETE_CLOUD',
            'job_type': 'bulk_delete',
            'status': 'RUNNING',
            'total_items': len(uids),
            'processed_items': 0,
            'successful_items': 0,
            'failed_items': 0,
            'progress': 0,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': user['username'],
            's3_input_key': s3_key_input,
        })
        # Process
        job_details = []
        for idx, uid in enumerate(uids):
            detail = {'uid': uid, 'status': '', 'reason': '', 'timestamp': datetime.utcnow().isoformat()}
            try:
                response = subscribers_table.delete_item(Key={'uid': uid}, ReturnValues='ALL_OLD')
                if 'Attributes' in response:
                    detail['status'] = 'SUCCESS'
                    detail['reason'] = 'Successfully deleted from DynamoDB'
                else:
                    detail['status'] = 'FAILED'
                    detail['reason'] = 'Not found in DynamoDB'
            except Exception as e:
                detail['status'] = 'FAILED'
                detail['reason'] = f"Error: {str(e)}"
                logger.error(f"Error deleting {uid}: {e}")
            job_details.append(detail)
            if (idx + 1) % 10 == 0 or idx == len(uids) - 1:
                progress = int((idx + 1) / len(uids) * 100)
                jobs_table.update_item(
                    Key={'job_id': job_id},
                    UpdateExpression='SET progress = :p, processed_items = :proc',
                    ExpressionAttributeValues={
                        ':p': progress,
                        ':proc': idx + 1
                    }
                )
        # Report
        report_csv = generate_report_csv(job_details, 'DELETION')
        s3_key_report = f"deletions/{job_id}/detailed_report.csv"
        s3_client.put_object(Bucket=CONFIG["UPLOADS_BUCKET"], Key=s3_key_report, Body=report_csv, ContentType='text/csv', ContentDisposition=f'attachment; filename=\"deletion_report_{job_id}.csv\"')
        report_url = s3_client.generate_presigned_url('get_object', Params={'Bucket': CONFIG["UPLOADS_BUCKET"], 'Key': s3_key_report}, ExpiresIn=86400)
        successful = len([d for d in job_details if d['status'] == 'SUCCESS'])
        failed = len([d for d in job_details if d['status'] == 'FAILED'])
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :status, processed_items = :proc, successful_items = :succ, failed_items = :fail, progress = :prog, completed_at = :completed_at, report_s3_key = :report_key',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'COMPLETED' if failed == 0 else 'COMPLETED_WITH_ERRORS',
                ':proc': len(uids),
                ':succ': successful,
                ':fail': failed,
                ':prog': 100,
                ':completed_at': datetime.utcnow().isoformat(),
                ':report_key': s3_key_report
            }
        )
        return create_response(data={
            'job_id': job_id,
            'jobid': job_id,  # compatibility
            'total_items': len(uids),
            'successful': successful,
            'failed': failed,
            'report_download_url': report_url,
            'summary': {'success_rate': f"{(successful/len(uids)*100):.2f}%", 'total_processed': len(uids)}
        })
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        return create_response(message=str(e), status_code=500)

# -------------------- SQL Query Export Handler -------------------------------
def handle_sql_query_export(event):
    """
    Execute SQL (RDS) or PartiQL (DynamoDB) query and export to CSV.
    Driven by the 'mode' field from the frontend.
    """
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)

    try:
        body = json.loads(event.get('body', '{}'))
        sql_query = body.get('query', '').strip()
        mode = body.get('mode', 'LEGACY').upper() # Get mode from frontend

        if not sql_query:
            return create_response(message="SQL/PartiQL query required", status_code=400)
        if not sql_query.upper().startswith('SELECT'):
            return create_response(message="Only SELECT queries are allowed", status_code=400)

        results = []
        column_names = []

        if mode == 'LEGACY':
            # ... (Your existing LEGACY logic is correct, no changes needed) ...
            logger.info(f"Executing SQL query on LEGACY (RDS): {sql_query}")
            try:
                conn = get_rds_connection()
                with conn.cursor() as cursor:
                    cursor.execute(sql_query)
                    results = cursor.fetchall()
                    if not results:
                        conn.close()
                        return create_response(message="Query returned no results from RDS", status_code=404)
                    column_names = [desc[0] for desc in cursor.description]
                conn.close()
            except Exception as e:
                logger.error(f"SQL query error (RDS): {e}")
                return create_response(message=f"RDS Query failed: {str(e)}", status_code=500)

        else: # CLOUD or HYBRID mode
            logger.info(f"Executing PartiQL query on CLOUD (DynamoDB): {sql_query}")
            try:
                # --- FIX FOR LIMIT CLAUSE ---
                limit_value = None
                # Find 'LIMIT [number]' (case-insensitive)
                limit_match = re.search(r'LIMIT\s+(\d+)', sql_query, re.IGNORECASE)
                if limit_match:
                    limit_value = int(limit_match.group(1))
                    # Remove the LIMIT clause from the query string
                    sql_query = re.sub(r'LIMIT\s+(\d+)', '', sql_query, flags=re.IGNORECASE).strip()
                # --- END OF FIX ---

                table_name = CONFIG["SUBSCRIBER_TABLE_NAME"]
                partiql_query = re.sub(
                    r'FROM\s+subscribers', 
                    f'FROM "{table_name}"', 
                    sql_query, 
                    flags=re.IGNORECASE
                )
                logger.info(f"Transformed PartiQL query: {partiql_query} (MaxItems: {limit_value})")

                # Prepare execute_statement arguments
                statement_args = {'Statement': partiql_query}
                if limit_value is not None:
                    statement_args['Limit'] = limit_value

                response = dynamodb_client.execute_statement(**statement_args)
                items_ddb_json = response.get('Items', [])

                if not items_ddb_json:
                    return create_response(message="Query returned no results from DynamoDB", status_code=404)
                
                results = [deserializer.deserialize({'M': item}) for item in items_ddb_json]
                column_names = list(results[0].keys())

            except Exception as e:
                logger.error(f"PartiQL query error (DynamoDB): {e}")
                return create_response(message=f"DynamoDB Query failed: {str(e)}", status_code=500)

        # --- CSV Generation (this is the same for both) ---
        # ... (Your CSV generation logic from line 1172 is correct, no changes needed) ...
        output = io.StringIO()
        csv_writer = csv.DictWriter(output, fieldnames=column_names, extrasaction='ignore')
        csv_writer.writeheader()
        csv_writer.writerows(results)
        csv_content = output.getvalue()
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"query_results_{mode.lower()}_{timestamp}.csv"
        s3_key = f"query-exports/{filename}"
        
        s3_client.put_object(
            Bucket=CONFIG["UPLOADS_BUCKET"], 
            Key=s3_key, 
            Body=csv_content, 
            ContentType='text/csv', 
            ContentDisposition=f'attachment; filename=\"{filename}\"'
        )
        
        download_url = s3_client.generate_presigned_url(
            'get_object', 
            Params={'Bucket': CONFIG["UPLOADS_BUCKET"], 'Key': s3_key}, 
            ExpiresIn=3600
        )
        
        return create_response(data={
            'row_count': len(results),
            'column_count': len(column_names),
            'columns': column_names,
            'download_url': download_url,
            'filename': filename,
            'preview': results[:10]
        })

    except Exception as e:
        logger.error(f"SQL/PartiQL export handler error: {e}")
        return create_response(message=str(e), status_code=500)

# -------------------- Job Management Handlers --------------------------------
def handle_list_jobs(event):
    """List migration jobs"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        response = jobs_table.scan(Limit=100)
        jobs = response.get('Items', [])
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return create_response(data={'jobs': jobs, 'count': len(jobs)})
    except Exception as e:
        logger.error(f"List jobs error: {e}")
        return create_response(message="Failed to list jobs", status_code=500)

def handle_get_job(event, job_id):
    """Get job details"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        response = jobs_table.get_item(Key={'job_id': job_id})
        if 'Item' in response:
            item = response['Item']
            # add jobid alias for frontend
            item['jobid'] = item.get('job_id', job_id)
            return create_response(data=item)
        else:
            return create_response(message="Job not found", status_code=404)
    except Exception as e:
        logger.error(f"Get job error: {e}")
        return create_response(message="Failed to get job", status_code=500)

def handle_cancel_job(event, job_id):
    """Cancel a running job"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        response = jobs_table.get_item(Key={'job_id': job_id})
        if 'Item' not in response:
            return create_response(message="Job not found", status_code=404)
        job = response['Item']
        if job['status'] in ['COMPLETED', 'CANCELLED', 'FAILED', 'COMPLETED_WITH_ERRORS']:
            return create_response(message=f"Cannot cancel job with status {job['status']}", status_code=400)
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :status, cancelled_at = :cancelled_at, cancelled_by = :cancelled_by',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'CANCELLED',
                ':cancelled_at': datetime.utcnow().isoformat(),
                ':cancelled_by': user['username']
            }
        )
        return create_response(data={'job_id': job_id, 'jobid': job_id, 'status': 'CANCELLED', 'message': 'Job cancelled successfully'})
    except Exception as e:
        logger.error(f"Cancel job error: {e}")
        return create_response(message=str(e), status_code=500)

def handle_download_job_report(event, job_id):
    """Download detailed CSV report for a specific job"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    try:
        response = jobs_table.get_item(Key={'job_id': job_id})
        if 'Item' not in response:
            return create_response(message="Job not found", status_code=404)
        job = response['Item']
        report_key = job.get('report_s3_key')
        if not report_key:
            return create_response(message="Report not available for this job", status_code=404)
        download_url = s3_client.generate_presigned_url('get_object', Params={'Bucket': CONFIG["UPLOADS_BUCKET"], 'Key': report_key}, ExpiresIn=3600)
        return create_response(data={
            'job_id': job_id,
            'jobid': job_id,
            'job_type': job['type'],
            'download_url': download_url,
            'report_filename': f"{job['type'].lower()}_report_{job_id}.csv",
            'expires_in': 3600
        })
    except Exception as e:
        logger.error(f"Download report error: {e}")
        return create_response(message=str(e), status_code=500)
        
        
# -------------------- Job Management Handlers --------------------------------

def handle_delete_job(event, job_id):
    """Deletes a job from the DynamoDB jobs table"""
    user = require_auth(event)
    if not user or 'admin' not in user.get('permissions', []):
        return create_response(message="Admin permission required", status_code=403)

    try:
        jobs_table.delete_item(
            Key={'job_id': job_id}
        )
        return create_response(data={'job_id': job_id, 'deleted': True}, message="Job deleted")
    except Exception as e:
        logger.error(f"Delete job error: {e}")
        return create_response(message=str(e), status_code=500)

# -------------------- Settings Handlers --------------------------------------
def handle_get_provisioning_mode(event):
    """Get current provisioning mode"""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    mode = get_provisioning_mode()
    return create_response(data={'mode': mode})

def handle_set_provisioning_mode(event):
    """Set provisioning mode"""
    user = require_auth(event)
    if not user or 'admin' not in user.get('permissions', []):
        return create_response(message="Admin permission required", status_code=403)
    try:
        body = json.loads(event.get('body', '{}'))
        mode = (body.get('mode') or 'CLOUD').upper()
        if mode not in ['CLOUD', 'LEGACY', 'HYBRID']:
            return create_response(message="Invalid mode. Must be CLOUD, LEGACY, or HYBRID", status_code=400)
        settings_table.put_item(Item={
            'sk': 'provisioning_mode',
            'setting_value': mode,
            'updated_at': datetime.utcnow().isoformat(),
            'updated_by': user['username']
        })
        logger.info(f"Provisioning mode set to {mode} by {user['username']}")
        return create_response(data={'mode': mode}, message=f"Provisioning mode set to {mode}")
    except Exception as e:
        logger.error(f"Set provisioning mode error: {e}")
        return create_response(message=str(e), status_code=500)

# ==========================================
# ADD THIS: CSV MIGRATION UPLOAD HANDLER
# (Kept for compatibility, but real work is in handle_migrate_from_rds)
# ==========================================
def handle_migration_upload(event):
    """Handle CSV file upload for migration (compat stub)"""
    try:
        user = require_auth(event)
        if not user:
            return create_response({'error': 'Authentication required'}, status_code=401)
        body = event.get('body', '')
        if event.get('isBase64Encoded'):
            try:
                body = base64.b64decode(body).decode('utf-8')
            except Exception:
                pass
        job_id = str(uuid.uuid4())
        return create_response({
            'message': 'Migration started',
            'jobid': job_id,
            'job_id': job_id,
            'reportdownloadurl': '',
            'totalsubscribers': 0,
            'successful': 0,
            'failed': 0
        })
    except Exception as e:
        logger.error(f'Migration upload error: {e}')
        return create_response({'error': str(e)}, status_code=500)

# ==========================================
# ADD THIS: QUERY HANDLER
# ==========================================
def handle_query(event):
    """Execute query for subscribers"""
    try:
        user = require_auth(event)
        if not user:
            return create_response({'error': 'Authentication required'}, status_code=401)
        body = json.loads(event.get('body', '{}'))
        query_type = body.get('querytype') or body.get('query_type')
        query_value = body.get('queryvalue') or body.get('query_value')
        if not query_type or not query_value:
            return create_response({'error': 'Missing querytype or queryvalue'}, status_code=400)
        # Use existing query path
        return handle_query_subscribers(event)
    except Exception as e:
        logger.error(f'Query error: {e}')
        return create_response({'error': str(e)}, status_code=500)

# ==========================================
# ADD THIS: BULK DELETE HANDLER (compat)
# ==========================================
def handle_bulk_delete(event):
    """Delete multiple subscribers (compat stub uses detailed handler)"""
    try:
        user = require_auth(event)
        if not user:
            return create_response({'error': 'Authentication required'}, status_code=401)
        # Delegate to detailed cloud delete to keep single implementation
        return handle_bulk_delete_cloud(event)
    except Exception as e:
        logger.error(f'Bulk delete error: {e}')
        return create_response({'error': str(e)}, status_code=500)

# ========================== MAIN LAMBDA HANDLER ==============================
def lambda_handler(event, context):
    """Main Lambda handler"""
    try:
        # Path & method
        raw_path = event.get('rawPath', '') or event.get('path', '')
        http_method = (event.get('requestContext', {}).get('http', {}) or {}).get('method') or event.get('httpMethod', 'GET')
        http_method = http_method.upper()
        # normalize (strip trailing slash)
        if raw_path.endswith('/') and raw_path != '/':
            raw_path = raw_path[:-1]
        logger.info(f'Request: {http_method} {raw_path}')

        # Preflight
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': get_cors_headers(),
                'body': ''
            }

        # ---- Auth & Health & Dashboard
        if raw_path in ['/api/auth/login'] and http_method == 'POST':
            return handle_login(event)

        if raw_path in ['/api/ping'] and http_method == 'GET':
            return handle_api_ping(event)

        # ADD THIS NEW ROUTE:
        if raw_path in ['/api/health-ping', '/api/health/ping'] and http_method == 'GET':
            return handle_health_ping(event)

        if raw_path in ['/api/health'] and http_method == 'GET':
            return handle_health(event)

        if raw_path in ['/api/dashboard', '/api/dashboard-stats', '/api/dashboard/stats'] and http_method == 'GET':
            return handle_dashboard_stats(event)

        if raw_path == '/api/dashboard/performance' and http_method == 'GET':
            return handle_dashboard_performance(event)

        # ---- Jobs list / details / cancel / report
        if raw_path in ['/api/migration', '/api/migration/jobs', '/api/migration/jobs/list', '/api/jobs', '/api/jobs/list'] and http_method == 'GET':
            return handle_list_jobs(event)

        # /api/migration/jobs/{job_id} (GET)
        if raw_path.startswith('/api/migration/jobs/') and http_method == 'GET':
            tail = raw_path[len('/api/migration/jobs/'):]
            if '/' not in tail:  # just an id
                return handle_get_job(event, tail)

        # /api/migration/jobs/{job_id}/cancel (POST)
        if raw_path.startswith('/api/migration/jobs/') and raw_path.endswith('/cancel') and http_method == 'POST':
            job_id = raw_path.split('/')[-2]
            return handle_cancel_job(event, job_id)

        # /api/migration/jobs/{job_id}/report (GET)
        if raw_path.startswith('/api/migration/jobs/') and raw_path.endswith('/report') and http_method == 'GET':
            job_id = raw_path.split('/')[-2]
            return handle_download_job_report(event, job_id)
            
            # === NEW ROUTE ===
        if raw_path.startswith('/api/migration/jobs/') and http_method == 'DELETE':
           job_id = raw_path.split('/')[-1]
           return handle_delete_job(event, job_id)

        # ---- Migration upload aliases
        if raw_path in ['/api/migration/upload', '/api/migration/upload-csv', '/api/migration/csv-upload'] and http_method == 'POST':
            return handle_migrate_from_rds(event)

        # ---- Query/search aliases
        if raw_path in ['/api/query', '/api/query/subscribers'] and http_method == 'POST':
            return handle_query(event)

        if raw_path in ['/api/search-subscribers'] and http_method in ['GET', 'POST']:
            return handle_search_subscribers(event)

        if raw_path == '/api/query/subscribers' and http_method == 'GET':
            return handle_search_subscribers(event)

        # ---- Bulk delete aliases
        if raw_path in ['/api/bulk-delete', '/api/migration/bulk-delete'] and http_method == 'POST':
            return handle_bulk_delete_cloud(event)

        # ---- Subscribers CRUD + helpers
        if raw_path == '/api/subscribers' and http_method == 'GET':
            return handle_list_subscribers(event)

        if raw_path == '/api/list-subscribers' and http_method == 'GET':
            return handle_list_subscribers(event)

        if raw_path == '/api/subscribers/search' and http_method == 'GET':
            return handle_search_subscribers(event)

        if raw_path == '/api/subscribers' and http_method == 'POST':
            return handle_create_subscriber(event)

        if raw_path == '/api/create-subscriber' and http_method == 'POST':
            return handle_create_subscriber(event)

        if raw_path.startswith('/api/subscribers/') and http_method == 'PUT':
            uid = raw_path.split('/')[-1]
            return handle_update_subscriber(event, uid)

        if raw_path.startswith('/api/subscribers/') and http_method == 'DELETE':
            uid = raw_path.split('/')[-1]
            return handle_delete_subscriber(event, uid)

        # ---- SQL export aliases
        if raw_path in ['/api/migration/sql-export', '/api/sql-export', '/api/export'] and http_method == 'POST':
            return handle_sql_query_export(event)

        # ---- Settings
        if raw_path == '/api/settings/provisioning-mode' and http_method == 'GET':
            return handle_get_provisioning_mode(event)

        if raw_path == '/api/settings/provisioning-mode' and http_method == 'POST':
            return handle_set_provisioning_mode(event)

        # Not found
        return create_response({'error': f'Route not found: {http_method} {raw_path}'}, status_code=404)

    except Exception as e:
        logger.error(f'Lambda handler error: {e}')
        return create_response({'error': str(e)}, status_code=500)
        
# -------------------- Health Ping Handler (FAST) ---------------------------
import os, time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.config import Config as BotoConfig

HEALTH_TIMEOUT_MS   = int(os.getenv("HEALTH_TIMEOUT_MS", "10000"))   # per check
OVERALL_TIMEOUT_MS  = int(os.getenv("OVERALL_TIMEOUT_MS", "25000"))  # full call
HEALTH_CACHE_SEC    = int(os.getenv("HEALTH_CACHE_SECONDS", "8"))   # cache per function instance

DDB_TABLE_NAME = CONFIG.get("SUBSCRIBER_TABLE_NAME")
S3_BUCKET      = CONFIG.get("UPLOADS_BUCKET")

_HEALTH_BOTO = BotoConfig(retries={"max_attempts": 1, "mode": "standard"}, read_timeout=1, connect_timeout=1)

_last_health = {"ts": 0.0, "data": None}

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _ok(data):
    return create_response(data=data)

def _check_dynamo():
    try:
        if not DDB_TABLE_NAME:
            return {"status": "skipped", "reason": "no_table_env"}
        ddb = boto3.resource("dynamodb", config=_HEALTH_BOTO)
        tbl = ddb.Table(DDB_TABLE_NAME)
        tbl.load()
        return {"status": "ok", "details": {"itemCount": int(tbl.item_count or 0)}}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

def _check_rds():
    conn = None
    try:
        conn = get_rds_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

def _check_s3():
    try:
        if not S3_BUCKET:
            return {"status": "skipped", "reason": "no_bucket_env"}
        s3 = boto3.client("s3", config=_HEALTH_BOTO)
        s3.head_bucket(Bucket=S3_BUCKET)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

def _check_vpc():
    try:
        lf = boto3.client("lambda", config=_HEALTH_BOTO)
        fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        cfg = lf.get_function_configuration(FunctionName=fn)
        vpc = cfg.get("VpcConfig") or {}
        subnets = vpc.get("SubnetIds") or []
        sgs = vpc.get("SecurityGroupIds") or []
        enabled = bool(subnets or sgs)
        return {"status": "info", "details": {"enabled": enabled, "subnets": len(subnets), "securityGroups": len(sgs)}}
    except Exception as e:
        return {"status": "info", "error": str(e)}

def _run_with_timeout(fn, per_ms):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        return fut.result(timeout=per_ms / 1000.0)

def handle_health_ping(event, context=None):
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)

    now = time.time()
    if _last_health["data"] and now - _last_health["ts"] < HEALTH_CACHE_SEC:
        cached = dict(_last_health["data"])
        cached["cached"] = True
        return _ok(cached)

    start = time.time()

    checks = {
        "dynamodb": lambda: _run_with_timeout(_check_dynamo, HEALTH_TIMEOUT_MS),
        "rds":      lambda: _run_with_timeout(_check_rds,    HEALTH_TIMEOUT_MS),
        "s3":       lambda: _run_with_timeout(_check_s3,     HEALTH_TIMEOUT_MS),
       # "vpc":      lambda: _run_with_timeout(_check_vpc,    HEALTH_TIMEOUT_MS),
        "mode":     lambda: {"status": "ok", "details": {"provisioningMode": (get_provisioning_mode() or "CLOUD").upper()}},
    }

    results = {}
    try:
        with ThreadPoolExecutor(max_workers=len(checks)) as pool:
            futs = {pool.submit(fn): name for name, fn in checks.items()}
            for fut in as_completed(futs, timeout=OVERALL_TIMEOUT_MS / 1000.0):
                name = futs[fut]
                try:
                    results[name] = fut.result()
                except Exception as e:
                    results[name] = {"status": "degraded", "error": f"timeout_or_error: {e}"}
    except Exception:
        pass

    for name in checks:
        if name not in results:
            results[name] = {"status": "degraded", "error": "global_timeout"}

    def _okish(v):
        return v.get("status") in ("ok", "info", "skipped")
    summary = "healthy" if all(_okish(v) for v in results.values()) else "degraded"

    payload = {
        "summary": summary,
        "version": "4.3-production",
        "components": results,
        "tookMs": int((time.time() - start) * 1000),
        "checkedAt": _now_iso(),
    }

    _last_health["ts"] = now
    _last_health["data"] = payload
    return _ok(payload)

def handle_api_ping(event):
    """A lightning-fast ping that only returns the version."""
    user = require_auth(event)
    if not user:
        return create_response(message="Authentication required", status_code=401)
    
    return create_response(data={'version': CONFIG["VERSION"], 'message': 'pong'})