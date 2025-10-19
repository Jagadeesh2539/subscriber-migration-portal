import os
import pymysql
import pymysql.cursors
from contextlib import contextmanager

# Get connection details from environment variables for local development.
# The password 'Admin@123' matches what you set in the Docker command.
DB_HOST = os.environ.get('LEGACY_DB_HOST', 'localhost')
DB_USER = os.environ.get('LEGACY_DB_USER', 'root')
DB_PASSWORD = os.environ.get('LEGACY_DB_PASSWORD', 'Admin@123')
DB_NAME = os.environ.get('LEGACY_DB_NAME', 'legacydb')

@contextmanager
def get_connection():
    """Provides a database connection that is automatically closed."""
    connection = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        yield connection
    finally:
        connection.close()

def get_subscriber_by_any_id(identifier):
    """
    Fetches a complete subscriber profile by UID, IMSI, or MSISDN
    using a multi-table JOIN.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # This powerful query joins all related tables to get a complete profile
            sql = """
            SELECT
                s.uid, s.imsi, s.msisdn, s.plan, s.subscription_state, s.service_class, s.charging_characteristics,
                hss.subscription_id, hss.profile_type, hss.private_user_id, hss.public_user_id,
                hlr.call_forward_unconditional, hlr.call_barring_all_outgoing, hlr.clip_provisioned, hlr.clir_provisioned,
                hlr.call_hold_provisioned, hlr.call_waiting_provisioned,
                vas.account_status, vas.language_id, vas.sim_type
            FROM subscribers s
            LEFT JOIN tbl_hss_profiles hss ON s.uid = hss.subscriber_uid
            LEFT JOIN tbl_hlr_features hlr ON s.uid = hlr.subscriber_uid
            LEFT JOIN tbl_vas_services vas ON s.uid = vas.subscriber_uid
            WHERE s.uid = %s OR s.imsi = %s OR s.msisdn = %s
            """
            cursor.execute(sql, (identifier, identifier, identifier))
            subscriber_data = cursor.fetchone()

            # If a subscriber was found, fetch their PDP contexts (one-to-many)
            if subscriber_data:
                pdp_sql = "SELECT context_id, apn, qos_profile FROM tbl_pdp_contexts WHERE subscriber_uid = %s"
                cursor.execute(pdp_sql, (subscriber_data['uid'],))
                subscriber_data['pdp_contexts'] = cursor.fetchall()

            return subscriber_data

def create_subscriber_full_profile(data):
    """
    Creates a full subscriber profile across all tables using a database transaction.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                conn.begin() # Start a transaction

                # 1. Insert into main subscribers table
                sub_sql = """
                INSERT INTO subscribers (uid, imsi, msisdn, plan, subscription_state, service_class, charging_characteristics)
                VALUES (%s, %s, %s, %s, %s, %s, '0010')
                """
                cursor.execute(sub_sql, (data['uid'], data['imsi'], data['msisdn'], data['plan'], data['subscription_state'], data['service_class']))

                # 2. Insert into HSS table
                hss_sql = """
                INSERT INTO tbl_hss_profiles (subscriber_uid, profile_type) VALUES (%s, %s)
                """
                cursor.execute(hss_sql, (data['uid'], data['profile_type']))
                
                # 3. Insert into HLR table
                hlr_sql = """
                INSERT INTO tbl_hlr_features (subscriber_uid, call_forward_unconditional, call_barring_all_outgoing, 
                                            clip_provisioned, clir_provisioned, call_hold_provisioned, call_waiting_provisioned,
                                            ts11_provisioned, ts21_provisioned, ts22_provisioned, bs30_genr_provisioned)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(hlr_sql, (data['uid'], data.get('call_forward_unconditional'), data['call_barring_all_outgoing'],
                                        data['clip_provisioned'], data['clir_provisioned'], data['call_hold_provisioned'],
                                        data['call_waiting_provisioned'], data['ts11_provisioned'], data['ts21_provisioned'],
                                        data['ts22_provisioned'], data['bs30_genr_provisioned']))
                
                # 4. Insert into VAS table
                vas_sql = "INSERT INTO tbl_vas_services (subscriber_uid, account_status, language_id, sim_type) VALUES (%s, %s, %s, %s)"
                cursor.execute(vas_sql, (data['uid'], data['account_status'], data['language_id'], data['sim_type']))
                
                conn.commit() # Commit all changes if successful
                return True
            except Exception as e:
                conn.rollback() # Roll back all changes if any part fails
                raise e # Re-raise the exception to be handled by the API layer

def delete_subscriber(uid):
    """Deletes a subscriber. The CASCADE constraint will handle child tables."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            sql = "DELETE FROM subscribers WHERE uid = %s"
            cursor.execute(sql, (uid,))

