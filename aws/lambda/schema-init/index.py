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
    Schema Initializer Lambda Function - MySQL 5.7 Compatible
    
    This function runs within the VPC and can connect to RDS MySQL
    to initialize database schemas safely with proper error handling
    for MySQL 5.7 compatibility.
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
                "SET names utf8mb4",
                "SET sql_mode = 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'",
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
                "CREATE INDEX idx_email ON subscribers(email)",
                "CREATE INDEX idx_status ON subscribers(status)",
                "CREATE INDEX idx_plan_id ON subscribers(plan_id)",
                "CREATE INDEX idx_migration_status ON subscribers(migration_status)"
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
        
        # Execute SQL statements with MySQL 5.7 compatible error handling
        results = []
        executed = 0
        skipped = 0
        errors = 0
        
        # Error codes that should be treated as "already exists" (non-fatal)
        IGNORABLE_ERROR_CODES = {
            1061: "Duplicate key name (index already exists)",
            1050: "Table already exists", 
            1062: "Duplicate entry for key",
            1068: "Multiple primary key defined",
            1826: "Duplicate foreign key constraint name"
        }
        
        # Error message patterns to treat as "already exists"
        IGNORABLE_PATTERNS = [
            'already exists',
            'duplicate key name',
            'duplicate entry',
            'duplicate constraint'
        ]
        
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
                    
                    except pymysql.err.OperationalError as e:
                        error_code = e.args[0]
                        error_msg = str(e)
                        
                        # Check if this is a known ignorable error
                        if error_code in IGNORABLE_ERROR_CODES:
                            skipped += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'skipped',
                                'reason': IGNORABLE_ERROR_CODES[error_code],
                                'error_code': error_code
                            })
                            logger.info(f"⏭️ [{i}] Skipped ({error_code}): {stmt[:80]}...")
                        else:
                            # Check if error message contains ignorable patterns
                            is_ignorable = any(pattern in error_msg.lower() for pattern in IGNORABLE_PATTERNS)
                            
                            if is_ignorable:
                                skipped += 1
                                results.append({
                                    'index': i,
                                    'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                    'status': 'skipped',
                                    'reason': 'Already exists (pattern match)',
                                    'error_code': error_code
                                })
                                logger.info(f"⏭️ [{i}] Skipped (pattern): {stmt[:80]}...")
                            else:
                                errors += 1
                                results.append({
                                    'index': i,
                                    'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                    'status': 'error',
                                    'error': error_msg,
                                    'error_code': error_code
                                })
                                logger.error(f"❌ [{i}] Error {error_code}: {error_msg}")
                    
                    except pymysql.err.ProgrammingError as e:
                        error_code = e.args[0]
                        error_msg = str(e)
                        
                        # Programming errors are usually syntax issues - treat as real errors
                        errors += 1
                        results.append({
                            'index': i,
                            'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                            'status': 'error',
                            'error': error_msg,
                            'error_code': error_code
                        })
                        logger.error(f"❌ [{i}] Programming Error {error_code}: {error_msg}")
                    
                    except Exception as e:
                        error_msg = str(e).lower()
                        
                        # Check if message indicates "already exists"
                        if any(pattern in error_msg for pattern in IGNORABLE_PATTERNS):
                            skipped += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'skipped',
                                'reason': 'Already exists (message pattern)'
                            })
                            logger.info(f"⏭️ [{i}] Skipped (msg pattern): {stmt[:80]}...")
                        else:
                            errors += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'error',
                                'error': str(e)
                            })
                            logger.error(f"❌ [{i}] Generic Error: {str(e)}")
        finally:
            conn.close()
            logger.info("🔌 Database connection closed")
        
        # Prepare summary
        total_statements = len([s for s in sql_statements if s.strip() and not s.strip().startswith('--')])
        summary = {
            'executed': executed,
            'skipped': skipped,
            'errors': errors,
            'total': total_statements
        }
        
        # Determine success - only fail if there are actual errors (not skipped)
        is_successful = errors == 0
        
        logger.info(f"📊 Summary: Executed: {executed}, Skipped: {skipped}, Errors: {errors}")
        
        # Return response with proper success flag
        return {
            'statusCode': 200 if is_successful else 207,
            'body': json.dumps({
                'message': 'Schema initialization completed successfully' if is_successful else 'Schema initialization completed with some errors',
                'summary': summary,
                'results': results,
                'success': is_successful,  # Important for workflow validation
                'mysql_version': '5.7 compatible'
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Schema initialization failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Schema initialization failed',
                'message': str(e),
                'success': False
            })
        }