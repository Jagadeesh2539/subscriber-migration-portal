import json
import boto3
import pymysql
import os
import logging
import re

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Minimal table DDLs map for auto-create when missing
# Keep lightweight and safe. Extend as needed.
AUTO_CREATE_TABLES = {
    'subscribers': (
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            uid VARCHAR(50) PRIMARY KEY,
            msisdn VARCHAR(20),
            imsi VARCHAR(20),
            plan_id VARCHAR(50),
            status VARCHAR(32) DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    ),
    'migration_jobs': (
        """
        CREATE TABLE IF NOT EXISTS migration_jobs (
            job_id VARCHAR(36) PRIMARY KEY,
            job_type VARCHAR(32),
            job_status VARCHAR(32) DEFAULT 'PENDING',
            source_system VARCHAR(16),
            target_system VARCHAR(16),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    ),
    'audit_log': (
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            entity_type VARCHAR(32),
            entity_id VARCHAR(100),
            action VARCHAR(16),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    ),
    'users': (
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(100) UNIQUE,
            email VARCHAR(255) UNIQUE,
            role VARCHAR(32) DEFAULT 'VIEWER',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    ),
    'user_sessions': (
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    ),
    'plan_definitions': (
        """
        CREATE TABLE IF NOT EXISTS plan_definitions (
            plan_id VARCHAR(50) PRIMARY KEY,
            plan_name VARCHAR(200) NOT NULL,
            plan_type VARCHAR(16) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    ),
    'user_sessions': (
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
}

INDEX_TABLE_REGEX = re.compile(r"CREATE\s+INDEX\s+[^\s]+\s+ON\s+`?(\w+)`?\s*\(", re.IGNORECASE)

def handler(event, context):
    logger.info("🚀 Starting schema initialization...")

    try:
        secret_arn = os.environ['LEGACY_DB_SECRET_ARN']
        host = os.environ['LEGACY_DB_HOST']

        sm = boto3.client('secretsmanager')
        secret = json.loads(sm.get_secret_value(SecretId=secret_arn)['SecretString'])

        user = secret.get('username') or secret.get('user')
        pwd = secret.get('password') or secret.get('pass')
        db = secret.get('dbname') or secret.get('database') or ''

        sql_statements = event.get('sql_statements', [])
        if not sql_statements:
            sql_statements = [
                "SET names utf8mb4",
                "SET sql_mode = 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'",
            ]

        conn = pymysql.connect(
            host=host,
            user=user,
            password=pwd,
            database=db,
            connect_timeout=30,
            autocommit=True
        )
        logger.info(f"✅ Connected to database: {db}")

        results, executed, skipped, errors, autocreated = [], 0, 0, 0, 0

        ALWAYS_IGNORABLE_CODES = {1061: "Duplicate key name", 1050: "Table already exists", 1062: "Duplicate entry", 1068: "Multiple primary key", 1826: "Duplicate FK name"}
        INDEX_IGNORABLE_CODES = {1146: "Table doesn't exist (index creation)"}

        def is_index_stmt(stmt: str) -> bool:
            s = stmt.strip().upper()
            return s.startswith('CREATE INDEX')

        def extract_table_from_index(stmt: str) -> str:
            m = INDEX_TABLE_REGEX.search(stmt)
            return m.group(1) if m else ''

        with conn.cursor() as cursor:
            for i, stmt in enumerate(sql_statements, 1):
                stmt = stmt.strip()
                if not stmt or stmt.startswith('--'):
                    continue
                try:
                    cursor.execute(stmt)
                    executed += 1
                    results.append({'index': i, 'statement': stmt[:120], 'status': 'success'})
                    logger.info(f"✅ [{i}] Executed: {stmt[:80]}...")
                except (pymysql.err.OperationalError, pymysql.err.ProgrammingError) as e:
                    code = e.args[0] if e.args else -1
                    msg = str(e)

                    # If index creation fails due to missing table (1146), auto-create minimal table and retry once
                    if code == 1146 and is_index_stmt(stmt):
                        table = extract_table_from_index(stmt)
                        ddl = AUTO_CREATE_TABLES.get(table)
                        if table and ddl:
                            try:
                                logger.info(f"🏗️ Auto-creating missing table '{table}' to satisfy index...")
                                cursor.execute(ddl)
                                autocreated += 1
                                # retry index once
                                cursor.execute(stmt)
                                executed += 1
                                results.append({'index': i, 'statement': stmt[:120], 'status': 'success', 'auto_created_table': table})
                                logger.info(f"✅ [{i}] Executed after auto-create: {stmt[:80]}...")
                                continue
                            except Exception as retry_err:
                                msg = f"Auto-create+retry failed: {retry_err}"
                                # fall-through to classification
                    # classify ignorable
                    ignorable = code in ALWAYS_IGNORABLE_CODES or (is_index_stmt(stmt) and code in INDEX_IGNORABLE_CODES) or any(x in msg.lower() for x in ['already exists','duplicate key name','duplicate entry','duplicate constraint'])
                    if ignorable:
                        skipped += 1
                        reason = ALWAYS_IGNORABLE_CODES.get(code) or INDEX_IGNORABLE_CODES.get(code) or 'Already exists (pattern)'
                        results.append({'index': i, 'statement': stmt[:120], 'status': 'skipped', 'reason': reason, 'error_code': code})
                        logger.info(f"⏭️ [{i}] Skipped ({code}): {reason}")
                    else:
                        errors += 1
                        results.append({'index': i, 'statement': stmt[:120], 'status': 'error', 'error': msg, 'error_code': code})
                        logger.error(f"❌ [{i}] Error {code}: {msg}")
                except Exception as ge:
                    errors += 1
                    results.append({'index': i, 'statement': stmt[:120], 'status': 'error', 'error': str(ge)})
                    logger.error(f"❌ [{i}] Generic Error: {ge}")

        total = len([s for s in sql_statements if s.strip() and not s.strip().startswith('--')])
        summary = {'executed': executed, 'skipped': skipped, 'errors': errors, 'auto_created_tables': autocreated, 'total': total}
        success = errors == 0
        logger.info(f"📊 Summary: {summary}")
        return {'statusCode': 200 if success else 207, 'body': json.dumps({'message': 'Schema initialization completed' if success else 'Schema initialization completed with some errors', 'summary': summary, 'results': results, 'success': success})}
    except Exception as e:
        logger.error(f"❌ Schema initialization failed: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Schema initialization failed', 'message': str(e), 'success': False})}
