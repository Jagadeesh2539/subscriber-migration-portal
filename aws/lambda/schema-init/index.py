import json
import boto3
import pymysql
import os
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Schema Initializer Lambda Function
    
    This function runs within the VPC and can connect to RDS MySQL
    to initialize database schemas safely.
    """
    logger.info("🚀 Starting schema initialization...")
    
    try:
        # Get environment variables
        secret_arn = os.environ['LEGACY_DB_SECRET_ARN']
        host = os.environ['LEGACY_DB_HOST']
        
        logger.info(f"📡 Connecting to database host: {host}")
        
        # Get database credentials from Secrets Manager
        sm = boto3.client('secretsmanager')
        secret = json.loads(sm.get_secret_value(SecretId=secret_arn)['SecretString'])
        
        user = secret.get('username') or secret.get('user')
        pwd = secret.get('password') or secret.get('pass')
        db = secret.get('dbname') or secret.get('database') or ''
        
        logger.info(f"🔑 Retrieved credentials for user: {user}, database: {db}")
        
        # Get SQL statements from event payload
        sql_statements = event.get('sql_statements', [])
        
        if not sql_statements:
            logger.info("📝 No SQL statements provided, using default schema")
            # Default basic schema for subscriber migration
            sql_statements = [
                """CREATE TABLE IF NOT EXISTS subscribers (
                    uid VARCHAR(50) PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    phone VARCHAR(20),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    status ENUM('ACTIVE', 'INACTIVE', 'PENDING', 'SUSPENDED') DEFAULT 'ACTIVE',
                    subscription_type VARCHAR(50),
                    plan_id VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    migrated_at TIMESTAMP NULL,
                    migration_status ENUM('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED') DEFAULT 'PENDING'
                )""",
                "CREATE INDEX IF NOT EXISTS idx_email ON subscribers(email)",
                "CREATE INDEX IF NOT EXISTS idx_status ON subscribers(status)",
                "CREATE INDEX IF NOT EXISTS idx_plan_id ON subscribers(plan_id)",
                "CREATE INDEX IF NOT EXISTS idx_migration_status ON subscribers(migration_status)",
                "CREATE INDEX IF NOT EXISTS idx_created_at ON subscribers(created_at)",
                
                """CREATE TABLE IF NOT EXISTS migration_jobs (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    job_id VARCHAR(100) UNIQUE NOT NULL,
                    status ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED') DEFAULT 'PENDING',
                    total_records INT DEFAULT 0,
                    processed_records INT DEFAULT 0,
                    failed_records INT DEFAULT 0,
                    error_details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL
                )""",
                "CREATE INDEX IF NOT EXISTS idx_job_id ON migration_jobs(job_id)",
                "CREATE INDEX IF NOT EXISTS idx_job_status ON migration_jobs(status)",
                "CREATE INDEX IF NOT EXISTS idx_job_created_at ON migration_jobs(created_at)",
                
                """CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    entity_type VARCHAR(50) NOT NULL,
                    entity_id VARCHAR(100) NOT NULL,
                    action ENUM('CREATE', 'UPDATE', 'DELETE', 'MIGRATE') NOT NULL,
                    old_values JSON,
                    new_values JSON,
                    changed_by VARCHAR(100),
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_entity ON audit_log(entity_type, entity_id)",
                "CREATE INDEX IF NOT EXISTS idx_action ON audit_log(action)",
                "CREATE INDEX IF NOT EXISTS idx_changed_at ON audit_log(changed_at)"
            ]
        
        logger.info(f"📊 Processing {len(sql_statements)} SQL statements")
        
        # Connect to MySQL database
        try:
            conn = pymysql.connect(
                host=host,
                user=user,
                password=pwd,
                database=db,
                connect_timeout=30,
                autocommit=True
            )
            logger.info(f"✅ Successfully connected to database: {db}")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {str(e)}")
            raise
        
        # Execute SQL statements
        results = []
        executed = 0
        skipped = 0
        errors = 0
        
        try:
            with conn.cursor() as cursor:
                for i, stmt in enumerate(sql_statements, 1):
                    stmt = stmt.strip()
                    if not stmt or stmt.startswith('--'):
                        continue
                    
                    try:
                        cursor.execute(stmt)
                        executed += 1
                        results.append({
                            'index': i,
                            'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                            'status': 'success'
                        })
                        logger.info(f"✅ [{i}] Executed: {stmt[:80]}...")
                    except Exception as e:
                        error_msg = str(e)
                        if 'already exists' in error_msg.lower():
                            skipped += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'skipped',
                                'reason': 'already exists'
                            })
                            logger.info(f"⏭️ [{i}] Skipped (exists): {stmt[:80]}...")
                        else:
                            errors += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'error',
                                'error': error_msg
                            })
                            logger.error(f"❌ [{i}] Error: {error_msg}")
        finally:
            conn.close()
            logger.info("🔌 Database connection closed")
        
        # Prepare summary
        summary = {
            'executed': executed,
            'skipped': skipped,
            'errors': errors,
            'total': len([s for s in sql_statements if s.strip() and not s.strip().startswith('--')])
        }
        
        logger.info(f"📊 Summary: Executed: {executed}, Skipped: {skipped}, Errors: {errors}")
        
        # Return response
        return {
            'statusCode': 200 if errors == 0 else 207,
            'body': json.dumps({
                'message': 'Schema initialization completed successfully' if errors == 0 else 'Schema initialization completed with some errors',
                'summary': summary,
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Schema initialization failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Schema initialization failed',
                'message': str(e)
            })
        }