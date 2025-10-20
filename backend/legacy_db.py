import os
import pymysql
import pymysql.cursors
import json
import warnings
from contextlib import contextmanager

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

@contextmanager
def get_connection():
    """Provides a database connection that is automatically closed."""
    if IS_LEGACY_DB_DISABLED:
        raise RuntimeError("Legacy DB connection is disabled in this environment.")
        
    connection = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, cursorclass=pymysql.cursors.DictCursor)
    try:
        yield connection
    finally:
        connection.close()

def get_subscriber_by_any_id(identifier):
    """Fetches a full subscriber profile from the legacy DB using UID, IMSI, or MSISDN."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
            SELECT s.*, hss.subscription_id, hss.profile_type, hss.private_user_id, hss.public_user_id, hlr.call_forward_unconditional, hlr.call_barring_all_outgoing, hlr.clip_provisioned, hlr.clir_provisioned, hlr.call_hold_provisioned, hlr.call_waiting_provisioned, vas.account_status, vas.language_id, vas.sim_type, (SELECT JSON_ARRAYAGG(JSON_OBJECT('context_id', pdp.context_id, 'apn', pdp.apn, 'qos_profile', pdp.qos_profile)) FROM tbl_pdp_contexts pdp WHERE pdp.subscriber_uid = s.uid) AS pdp_contexts
            FROM subscribers s
            LEFT JOIN tbl_hss_profiles hss ON s.uid = hss.subscriber_uid
            LEFT JOIN tbl_hlr_features hlr ON s.uid = hlr.subscriber_uid
            LEFT JOIN tbl_vas_services vas ON s.uid = vas.subscriber_uid
            WHERE s.uid = %s OR s.imsi = %s OR s.msisdn = %s;
            """
            cursor.execute(sql, (identifier, identifier, identifier))
            result = cursor.fetchone()
            
            if result:
                if result.get('pdp_contexts'):
                    try:
                        result['pdp_contexts'] = json.loads(result['pdp_contexts'])
                    except (json.JSONDecodeError, TypeError):
                         result['pdp_contexts'] = [] # Handle cases where it's not valid JSON
                else:
                    result['pdp_contexts'] = []
                for key, value in result.items():
                    if value == 0: result[key] = False
                    elif value == 1: result[key] = True
            return result

def create_subscriber_full_profile(data):
    """Creates a full subscriber profile across all tables within a single transaction."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                conn.begin()
                sql_sub = """INSERT INTO subscribers (uid, imsi, msisdn, plan, subscription_state, service_class, charging_characteristics) VALUES (%s, %s, %s, %s, %s, %s, %s);"""
                cursor.execute(sql_sub, (data['uid'], data['imsi'], data.get('msisdn'), data.get('plan'), data.get('subscription_state'), data.get('service_class'), data.get('charging_characteristics')))
                sql_hss = """INSERT INTO tbl_hss_profiles (subscriber_uid, profile_type) VALUES (%s, %s);"""
                cursor.execute(sql_hss, (data['uid'], data.get('profile_type')))
                sql_hlr = """INSERT INTO tbl_hlr_features (subscriber_uid, call_forward_unconditional, call_barring_all_outgoing, clip_provisioned, clir_provisioned, call_hold_provisioned, call_waiting_provisioned) VALUES (%s, %s, %s, %s, %s, %s, %s);"""
                cursor.execute(sql_hlr, (data['uid'], data.get('call_forward_unconditional'), data.get('call_barring_all_outgoing', False), data.get('clip_provisioned', True), data.get('clir_provisioned', False), data.get('call_hold_provisioned', True), data.get('call_waiting_provisioned', True)))
                sql_vas = """INSERT INTO tbl_vas_services (subscriber_uid, account_status, language_id, sim_type) VALUES (%s, %s, %s, %s);"""
                cursor.execute(sql_vas, (data['uid'], data.get('account_status', 'ACTIVE'), data.get('language_id', 'en-US'), data.get('sim_type', '4G_USIM')))
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"Transaction failed: {e}")
                raise
            
def delete_subscriber(uid):
    """Deletes a subscriber. CASCADE constraint handles child tables."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            sql = "DELETE FROM subscribers WHERE uid = %s"
            cursor.execute(sql, (uid,))
