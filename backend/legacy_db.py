import os
import pymysql
import pymysql.cursors
import json
import warnings

# Get connection details from environment variables for local development.
# The defaults match your local Docker setup.
DB_HOST = os.environ.get('LEGACY_DB_HOST', 'host.docker.internal') 
DB_PORT = int(os.environ.get('LEGACY_DB_PORT', 3307)) # Using port 3307
DB_USER = os.environ.get('LEGACY_DB_USER', 'root')
DB_PASSWORD = os.environ.get('LEGACY_DB_PASSWORD', 'Admin@123')
DB_NAME = os.environ.get('LEGACY_DB_NAME', 'legacydb')

# --- FIX: Conditionally disable legacy DB access in remote deployment ---
# Check if we are running in a known remote environment (Lambda sets AWS_REGION) 
# AND using one of the common local/docker development hosts. 
IS_LEGACY_DB_DISABLED = (os.environ.get('AWS_REGION') is not None) and (DB_HOST in ['host.docker.internal', '127.0.0.1'])
# ---------------------------------------------------------------------

def get_connection():
    """Establishes a new database connection."""
    if IS_LEGACY_DB_DISABLED:
        # If disabled, raise a RuntimeError to signal the caller to skip the operation.
        raise RuntimeError("Legacy DB connection skipped: Cannot reach local database from a remote environment.")
        
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def check_for_duplicates(uid, imsi, msisdn):
    """
    Checks if a subscriber with the given UID, IMSI, or MSISDN already exists.
    Returns a string detailing the conflict or None if no conflict is found.
    """
    try:
        conn = get_connection()
    except RuntimeError as e:
        warnings.warn(f"INFO: Legacy DB duplicate check skipped: {e}")
        return None 
        
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT uid, imsi, msisdn
            FROM subscribers
            WHERE uid = %s OR imsi = %s OR msisdn = %s
            LIMIT 1;
            """
            cursor.execute(sql, (uid, imsi, msisdn))
            result = cursor.fetchone()
            
            if result:
                if result['uid'] == uid:
                    return f"UID '{uid}' already exists in Legacy DB."
                if result['imsi'] == imsi:
                    return f"IMSI '{imsi}' already exists in Legacy DB."
                if result['msisdn'] == msisdn:
                    return f"MSISDN '{msisdn}' already exists in Legacy DB."
            return None
    finally:
        if conn:
            conn.close()

def get_subscriber_by_any_id(identifier):
    """
    Fetches a full subscriber profile from the legacy DB using UID, IMSI, or MSISDN.
    Uses LEFT JOINs to gather all related data.
    """
    conn = None
    try:
        conn = get_connection()
    except RuntimeError as e:
        # FIX: Gracefully catch the disabled error and return None, which 
        # the calling function in subscriber.py will treat as 'not found'.
        warnings.warn(f"INFO: Legacy DB search skipped: {e}")
        return None 
        
    try:
        with conn.cursor() as cursor:
            # This single, powerful query joins all 5 tables.
            sql = """
            SELECT
                s.*,
                hss.subscription_id, hss.profile_type, hss.private_user_id, hss.public_user_id,
                hlr.call_forward_unconditional, hlr.call_barring_all_outgoing, hlr.clip_provisioned, 
                hlr.clir_provisioned, hlr.call_hold_provisioned, hlr.call_waiting_provisioned,
                vas.account_status, vas.language_id, vas.sim_type,
                (SELECT JSON_ARRAYAGG(JSON_OBJECT('context_id', pdp.context_id, 'apn', pdp.apn, 'qos_profile', pdp.qos_profile))
                 FROM tbl_pdp_contexts pdp WHERE pdp.subscriber_uid = s.uid) AS pdp_contexts
            FROM
                subscribers s
            LEFT JOIN
                tbl_hss_profiles hss ON s.uid = hss.subscriber_uid
            LEFT JOIN
                tbl_hlr_features hlr ON s.uid = hlr.subscriber_uid
            LEFT JOIN
                tbl_vas_services vas ON s.uid = vas.subscriber_uid
            WHERE
                s.uid = %s OR s.imsi = %s OR s.msisdn = %s;
            """
            cursor.execute(sql, (identifier, identifier, identifier))
            result = cursor.fetchone()
            
            if result:
                # Decode JSON string for pdp_contexts if it's not null
                if result.get('pdp_contexts'):
                    result['pdp_contexts'] = json.loads(result['pdp_contexts'])
                else:
                    result['pdp_contexts'] = []

                # Convert boolean values (0/1) from MySQL to true/false for JSON
                for key, value in result.items():
                    if value == 0:
                        result[key] = False
                    elif value == 1:
                        result[key] = True
            return result
    finally:
        if conn:
            conn.close()

def create_subscriber_full_profile(data):
    """
    Creates a full subscriber profile across all tables within a single transaction.
    """
    conn = None
    try:
        conn = get_connection()
    except RuntimeError as e:
        # FIX: Fail the create/provisioning operation if the legacy DB is unreachable, 
        # as the dual-provisioning feature requires both systems to be updated.
        raise Exception(f"Dual Provisioning Failed: Legacy DB Unreachable: {e}") 

    try:
        with conn.cursor() as cursor:
            # Start transaction
            conn.begin()

            # 1. Insert into main subscribers table
            sql_sub = """
            INSERT INTO subscribers (uid, imsi, msisdn, plan, subscription_state, service_class, charging_characteristics)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(sql_sub, (
                data['uid'], data['imsi'], data.get('msisdn'), data.get('plan'),
                data.get('subscription_state'), data.get('service_class'), data.get('charging_characteristics')
            ))

            # 2. Insert into HSS table
            sql_hss = """
            INSERT INTO tbl_hss_profiles (subscriber_uid, profile_type) 
            VALUES (%s, %s);
            """
            cursor.execute(sql_hss, (data['uid'], data.get('profile_type')))

            # 3. Insert into HLR table
            sql_hlr = """
            INSERT INTO tbl_hlr_features (subscriber_uid, call_forward_unconditional, call_barring_all_outgoing, 
                                          clip_provisioned, clir_provisioned, call_hold_provisioned, call_waiting_provisioned)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(sql_hlr, (
                data['uid'], data.get('call_forward_unconditional'), data.get('call_barring_all_outgoing', False),
                data.get('clip_provisioned', True), data.get('clir_provisioned', False),
                data.get('call_hold_provisioned', True), data.get('call_waiting_provisioned', True)
            ))
            
            # 4. Insert into VAS table
            sql_vas = """
            INSERT INTO tbl_vas_services (subscriber_uid, account_status, language_id, sim_type)
            VALUES (%s, %s, %s, %s);
            """
            cursor.execute(sql_vas, (
                data['uid'], data.get('account_status', 'ACTIVE'),
                data.get('language_id', 'en-US'), data.get('sim_type', '4G_USIM')
            ))

            # Commit the transaction
            conn.commit()
    except Exception as e:
        # If anything fails, roll back all changes
        if conn:
            conn.rollback()
        print(f"Transaction failed: {e}")
        raise # Re-raise the exception to be caught by the API layer
    finally:
        if conn:
            conn.close()

def update_subscriber_full_profile(uid, data):
    """
    Updates a subscriber profile across all tables within a single transaction. (Placeholder for full implementation)
    NOTE: For the purposes of this demo, this is a placeholder. A real update requires complex logic.
    """
    conn = None
    try:
        conn = get_connection()
    except RuntimeError as e:
        # Fail the update operation if the legacy DB is unreachable
        raise Exception(f"Dual Provisioning Failed: Legacy DB Unreachable for update: {e}") 

    try:
        with conn.cursor() as cursor:
            conn.begin()

            # 1. Update main subscribers table
            sql_sub = """
            UPDATE subscribers 
            SET imsi=%s, msisdn=%s, plan=%s, subscription_state=%s, service_class=%s
            WHERE uid=%s;
            """
            cursor.execute(sql_sub, (
                data['imsi'], data.get('msisdn'), data.get('plan'),
                data.get('subscription_state'), data.get('service_class'), uid
            ))

            # 2. Update HSS table (e.g., just profile type for simplicity)
            sql_hss = "UPDATE tbl_hss_profiles SET profile_type=%s WHERE subscriber_uid=%s;"
            cursor.execute(sql_hss, (data.get('profile_type'), uid))
            
            # 3. Update HLR table (e.g., just call forward unconditional)
            sql_hlr = "UPDATE tbl_hlr_features SET call_forward_unconditional=%s WHERE subscriber_uid=%s;"
            cursor.execute(sql_hlr, (data.get('call_forward_unconditional'), uid))

            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Update transaction failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

def delete_subscriber(uid):
    """
    Deletes a subscriber. The ON DELETE CASCADE in the database schema
    will automatically delete records from all child tables.
    """
    conn = None
    try:
        conn = get_connection()
    except RuntimeError as e:
        # FIX: Raise a critical exception to ensure dual-provisioning fails if the legacy system is unreachable.
        raise Exception(f"Dual Provisioning Failed: Legacy DB Unreachable: {e}") 
        
    try:
        with conn.cursor() as cursor:
            sql = "DELETE FROM subscribers WHERE uid = %s"
            cursor.execute(sql, (uid,))
        return True
    finally:
        if conn:
            conn.close()
