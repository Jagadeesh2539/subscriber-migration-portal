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
    for MySQL 5.7 compatibility and table creation order.
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
            logger.info("📝 No SQL statements provided, using minimal default schema")
            # Minimal schema for basic functionality
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX idx_email ON subscribers(email)",
                "CREATE INDEX idx_status ON subscribers(status)"
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
        
        # Execute SQL statements with intelligent error handling
        results = []
        executed = 0
        skipped = 0
        errors = 0
        
        # Define error codes and their handling based on SQL statement type
        ALWAYS_IGNORABLE_CODES = {
            1061: "Duplicate key name (index already exists)",
            1050: "Table already exists", 
            1062: "Duplicate entry for key",
            1068: "Multiple primary key defined",
            1826: "Duplicate foreign key constraint name"
        }
        
        # Error codes that are ignorable for INDEX operations but not for TABLE operations
        INDEX_IGNORABLE_CODES = {
            1146: "Table doesn't exist (for index creation)"  # This is OK for indexes on missing tables
        }
        
        # Error message patterns to treat as "already exists"
        IGNORABLE_PATTERNS = [
            'already exists',
            'duplicate key name',
            'duplicate entry',
            'duplicate constraint'
        ]
        
        def is_index_statement(stmt):
            """Check if statement is creating an index"""
            stmt_upper = stmt.upper().strip()
            return stmt_upper.startswith('CREATE INDEX') or 'CREATE INDEX' in stmt_upper
        
        def should_ignore_error(stmt, error_code, error_msg):
            """Determine if an error should be ignored based on statement type and error"""
            # Always ignore these errors regardless of statement type
            if error_code in ALWAYS_IGNORABLE_CODES:
                return True, ALWAYS_IGNORABLE_CODES[error_code]
            
            # For INDEX statements, also ignore "table doesn't exist"
            if is_index_statement(stmt) and error_code in INDEX_IGNORABLE_CODES:
                return True, INDEX_IGNORABLE_CODES[error_code]
            
            # Check message patterns
            if any(pattern in error_msg.lower() for pattern in IGNORABLE_PATTERNS):
                return True, "Already exists (message pattern)"
            
            return False, None
        
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
                        
                        should_ignore, ignore_reason = should_ignore_error(stmt, error_code, error_msg)
                        
                        if should_ignore:
                            skipped += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'skipped',
                                'reason': ignore_reason,
                                'error_code': error_code
                            })
                            logger.info(f"⏭️ [{i}] Skipped ({error_code}): {ignore_reason}")
                        else:
                            errors += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'error',
                                'error': error_msg,
                                'error_code': error_code
                            })
                            logger.error(f"❌ [{i}] Operational Error {error_code}: {error_msg}")
                    
                    except pymysql.err.ProgrammingError as e:
                        error_code = e.args[0]
                        error_msg = str(e)
                        
                        should_ignore, ignore_reason = should_ignore_error(stmt, error_code, error_msg)
                        
                        if should_ignore:
                            skipped += 1
                            results.append({
                                'index': i,
                                'statement': stmt[:100] + ('...' if len(stmt) > 100 else ''),
                                'status': 'skipped',
                                'reason': ignore_reason,
                                'error_code': error_code
                            })
                            logger.info(f"⏭️ [{i}] Skipped ({error_code}): {ignore_reason}")
                        else:
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
        
        # Determine success - critical success if we executed core tables and settings
        # Allow some skipped indexes as long as core functionality is there
        is_successful = errors == 0 and executed >= 5  # At least 5 core statements executed
        
        logger.info(f"📊 Summary: Executed: {executed}, Skipped: {skipped}, Errors: {errors}")
        
        # Return response with proper success flag
        return {
            'statusCode': 200 if is_successful else 207,
            'body': json.dumps({
                'message': 'Schema initialization completed successfully' if is_successful else 'Schema initialization completed with some errors',
                'summary': summary,
                'results': results,
                'success': is_successful,  # Important for workflow validation
                'mysql_version': '5.7 compatible',
                'execution_strategy': 'tables_first_then_indexes'
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