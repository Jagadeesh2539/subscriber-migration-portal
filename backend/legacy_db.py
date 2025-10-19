import os
import pymysql
import pymysql.cursors
import json
import warnings

# --- Global connection details, used as defaults or can be overridden ---
DB_HOST = os.environ.get('LEGACY_DB_HOST', 'host.docker.internal')
DB_PORT = int(os.environ.get('LEGACY_DB_PORT', 3307))
DB_USER = os.environ.get('LEGACY_DB_USER', 'root')
DB_PASSWORD = os.environ.get('LEGACY_DB_PASSWORD', 'Admin@123')
DB_NAME = os.environ.get('LEGACY_DB_NAME', 'legacydb')
IS_LEGACY_DB_DISABLED = False # Default

def init_connection_details(host, port, user, password, database):
    """Allows runtime configuration of DB connection, used by the Lambda."""
    global DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, IS_LEGACY_DB_DISABLED
    DB_HOST = host
    DB_PORT = int(port)
    DB_USER = user
    DB_PASSWORD = password
    DB_NAME = database
    IS_LEGACY_DB_DISABLED = False # Ensure it's enabled when configured

# --- (The rest of your legacy_db.py file remains unchanged) ---
# ... get_connection(), get_subscriber_by_any_id(), etc. ...
