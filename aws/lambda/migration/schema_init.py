#!/usr/bin/env python3
"""
SchemaInit for Aurora Serverless v1 (MySQL-compatible) from within VPC.
- Reads SQL from packaged file database/rds_schema_update.sql (default)
- Optional S3 override via event: {"s3": {"bucket": "...", "key": "..."}}
- Idempotent execution: skips "already exists" errors, fails on others
- Prints concise progress for CI visibility
"""
import json
import os
import boto3
import pymysql

ALLOWED_EXISTENCE_PHRASES = [
    'already exists',
    'duplicate',
    'exists'
]


def _read_sql_packaged() -> str | None:
    paths = ['/var/task/database/rds_schema_update.sql', 'database/rds_schema_update.sql']
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()
    return None


def _read_sql_from_s3(bucket: str, key: str) -> str | None:
    try:
        s3 = boto3.client('s3')
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj['Body'].read().decode('utf-8')
    except Exception as e:
        print(f"Failed to read SQL from s3://{bucket}/{key}: {e}")
        return None


def _get_db_credentials(secret_arn: str):
    sm = boto3.client('secretsmanager')
    sec = json.loads(sm.get_secret_value(SecretId=secret_arn)['SecretString'])
    user = sec.get('username') or sec.get('user')
    pwd = sec.get('password') or sec.get('pass')
    db = sec.get('dbname') or sec.get('database') or ''
    if not user or not pwd:
        raise RuntimeError('Secret missing username or password')
    return user, pwd, db


def lambda_handler(event, context):
    try:
        secret_arn = os.environ['LEGACY_DB_SECRET_ARN']
        host = os.environ['LEGACY_DB_HOST']
        port = int(os.environ.get('LEGACY_DB_PORT', '3306'))

        # Determine SQL source
        sql_text = None
        s3_cfg = (event or {}).get('s3') if isinstance(event, dict) else None
        if s3_cfg and s3_cfg.get('bucket') and s3_cfg.get('key'):
            sql_text = _read_sql_from_s3(s3_cfg['bucket'], s3_cfg['key'])
        if not sql_text:
            sql_text = _read_sql_packaged()
        if not sql_text:
            return _resp(400, success=False, message='No SQL file found')

        # Credentials
        user, pwd, db = _get_db_credentials(secret_arn)

        # Connect to Aurora MySQL endpoint
        print(f"Connecting to Aurora at {host}:{port} db={db}")
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=pwd,
            database=db,
            autocommit=True,
            connect_timeout=30,
            charset='utf8mb4'
        )

        executed = skipped = errors = 0
        try:
            with conn.cursor() as cur:
                # Split statements safely by semicolon at top level
                stmts = [s.strip() for s in sql_text.split(';') if s.strip() and not s.strip().startswith('--')]
                print(f"Executing {len(stmts)} SQL statements...")
                for i, stmt in enumerate(stmts, 1):
                    try:
                        cur.execute(stmt)
                        executed += 1
                        if i % 10 == 0 or i == len(stmts):
                            print(f"Executed {i}/{len(stmts)}")
                    except Exception as e:
                        emsg = str(e).lower()
                        if any(ph in emsg for ph in ALLOWED_EXISTENCE_PHRASES):
                            skipped += 1
                            print(f"Skip exists {i}/{len(stmts)}: {stmt[:80]}...")
                        else:
                            errors += 1
                            print(f"ERROR {i}/{len(stmts)}: {e} for: {stmt[:120]}...")
            
        finally:
            try:
                conn.close()
            except Exception:
                pass

        success = errors == 0
        return _resp(200 if success else 500, success=success,
                     executed=executed, skipped=skipped, errors=errors,
                     message=f"Schema init: executed={executed}, skipped={skipped}, errors={errors}")

    except Exception as e:
        print(f"Schema init fatal error: {e}")
        return _resp(500, success=False, message=str(e))


def _resp(code, **body):
    return {'statusCode': code, **body}
