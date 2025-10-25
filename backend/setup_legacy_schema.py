import os
import json
import pymysql
from datetime import datetime

"""
Idempotent legacy schema setup/upgrade to enhanced subscribers_enhanced.
- Creates table if missing
- Ensures required columns and indexes exist
- Prints a concise JSON summary for CI visibility
"""

def connect_legacy():
    host = os.environ.get('LEGACY_DB_HOST')
    user = os.environ.get('LEGACY_DB_USER', 'admin')
    password = os.environ.get('LEGACY_DB_PASSWORD')
    database = os.environ.get('LEGACY_DB_NAME', 'legacydb')
    port = int(os.environ.get('LEGACY_DB_PORT', '3306'))
    return pymysql.connect(host=host, user=user, password=password, database=database,
                           port=port, cursorclass=pymysql.cursors.DictCursor)

DDL_PATH = os.path.join(os.path.dirname(__file__), '..', 'aws', 'rds_schema_update.sql')


def run_sql_file(conn, path):
    with open(path, 'r', encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        for statement in [s.strip() for s in sql.split(';') if s.strip()]:
            cur.execute(statement)
    conn.commit()


def ensure():
    summary = {
        'startedAt': datetime.utcnow().isoformat(),
        'createdTable': False,
        'columnsAdded': [],
        'indexesAdded': [],
        'notes': []
    }
    conn = connect_legacy()
    try:
        # Execute idempotent DDL script
        run_sql_file(conn, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'aws', 'rds_schema_update.sql')))
        # Check existence
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = DATABASE() AND table_name='subscribers_enhanced'
            """)
            if cur.fetchone():
                summary['createdTable'] = True
        # Note: Column/index adds are handled inside the SQL via helper procedures; we capture generic success
        summary['notes'].append('Executed idempotent DDL for subscribers_enhanced and indexes')
        summary['status'] = 'ok'
    except Exception as e:
        summary['status'] = 'error'
        summary['error'] = str(e)
    finally:
        conn.close()
        summary['finishedAt'] = datetime.utcnow().isoformat()
        print(json.dumps(summary))

if __name__ == '__main__':
    ensure()
