#!/usr/bin/env python3
"""
VPC-only Lambda for initializing Legacy RDS schema from within VPC.
Reads SQL from packaged file or optional S3 source.
Executes DDL statements idempotently.
"""
import json
import os
import boto3
from botocore.exceptions import ClientError
import pymysql

def lambda_handler(event, context):
    """Initialize Legacy RDS schema from within VPC"""
    try:
        print("Starting schema initialization...")
        
        # Get database connection details from environment
        secret_arn = os.environ.get('LEGACY_DB_SECRET_ARN')
        host = os.environ.get('LEGACY_DB_HOST')
        
        if not secret_arn or not host:
            return {
                'statusCode': 500,
                'error': 'LEGACY_DB_SECRET_ARN and LEGACY_DB_HOST must be set'
            }
        
        # Get SQL source (packaged file or S3)
        sql_content = get_sql_content(event)
        if not sql_content:
            return {
                'statusCode': 400,
                'error': 'No SQL content found - missing database/rds_schema_update.sql or invalid S3 path'
            }
        
        # Get database credentials from Secrets Manager
        sm_client = boto3.client('secretsmanager')
        try:
            secret_response = sm_client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(secret_response['SecretString'])
            
            username = secret.get('username') or secret.get('user')
            password = secret.get('password') or secret.get('pass')
            dbname = secret.get('dbname') or secret.get('database') or ''
            
            if not username or not password:
                return {
                    'statusCode': 500,
                    'error': 'Invalid secret format - missing username or password'
                }
        
        except Exception as e:
            return {
                'statusCode': 500,
                'error': f'Failed to retrieve database credentials: {str(e)}'
            }
        
        # Connect to database
        try:
            connection = pymysql.connect(
                host=host,
                user=username,
                password=password,
                database=dbname,
                autocommit=True,
                connect_timeout=30,
                charset='utf8mb4'
            )
            print(f"Connected to database: {host}")
        
        except Exception as e:
            return {
                'statusCode': 500,
                'error': f'Database connection failed: {str(e)}'
            }
        
        # Execute SQL statements
        executed_count = 0
        skipped_count = 0
        error_count = 0
        
        try:\n            with connection.cursor() as cursor:\n                # Split SQL into individual statements\n                statements = [\n                    stmt.strip() \n                    for stmt in sql_content.split(';') \n                    if stmt.strip() and not stmt.strip().startswith('--')\n                ]\n                \n                print(f\"Executing {len(statements)} SQL statements...\")\n                \n                for i, statement in enumerate(statements, 1):\n                    try:\n                        cursor.execute(statement)\n                        executed_count += 1\n                        print(f\"[{i}/{len(statements)}] Executed: {statement[:80]}...\")\n                    \n                    except Exception as e:\n                        error_msg = str(e).lower()\n                        if any(phrase in error_msg for phrase in ['already exists', 'duplicate', 'exists']):\n                            skipped_count += 1\n                            print(f\"[{i}/{len(statements)}] Skipped (exists): {statement[:80]}...\")\n                        else:\n                            error_count += 1\n                            print(f\"[{i}/{len(statements)}] ERROR: {statement[:80]}... -> {e}\")\n                            # Continue with other statements rather than failing immediately\n        \n        finally:\n            connection.close()\n        \n        # Return summary\n        success = error_count == 0\n        result = {\n            'statusCode': 200 if success else 500,\n            'executed': executed_count,\n            'skipped': skipped_count,\n            'errors': error_count,\n            'totalStatements': executed_count + skipped_count + error_count,\n            'success': success,\n            'message': f'Schema init completed: {executed_count} executed, {skipped_count} skipped, {error_count} errors'\n        }\n        \n        print(f\"✅ Schema initialization completed: {result['message']}\")\n        return result\n    \n    except Exception as e:\n        print(f\"❌ Schema initialization failed: {str(e)}\")\n        return {\n            'statusCode': 500,\n            'error': str(e),\n            'executed': 0,\n            'skipped': 0,\n            'errors': 1,\n            'success': False\n        }\n\n\ndef get_sql_content(event):\n    \"\"\"Get SQL content from packaged file or S3\"\"\"\n    # Check for S3 override in event\n    s3_config = event.get('s3')\n    if s3_config and s3_config.get('bucket') and s3_config.get('key'):\n        print(f\"Reading SQL from S3: {s3_config['bucket']}/{s3_config['key']}\")\n        return get_sql_from_s3(s3_config['bucket'], s3_config['key'])\n    \n    # Default: read from packaged file\n    sql_file_path = '/var/task/database/rds_schema_update.sql'\n    if os.path.exists(sql_file_path):\n        print(f\"Reading SQL from packaged file: {sql_file_path}\")\n        with open(sql_file_path, 'r', encoding='utf-8') as f:\n            return f.read()\n    \n    # Fallback: try relative path\n    relative_path = 'database/rds_schema_update.sql'\n    if os.path.exists(relative_path):\n        print(f\"Reading SQL from relative path: {relative_path}\")\n        with open(relative_path, 'r', encoding='utf-8') as f:\n            return f.read()\n    \n    print(\"❌ No SQL file found in Lambda package or relative path\")\n    return None\n\n\ndef get_sql_from_s3(bucket, key):\n    \"\"\"Get SQL content from S3 (optional)\"\"\"\n    try:\n        s3_client = boto3.client('s3')\n        response = s3_client.get_object(Bucket=bucket, Key=key)\n        return response['Body'].read().decode('utf-8')\n    \n    except Exception as e:\n        print(f\"Failed to read SQL from S3 {bucket}/{key}: {e}\")\n        return None