import os
import pymysql
import pymysql.cursors

# Get connection details from environment variables for local development.
# The password 'Admin@123' matches what you set in the Docker command.
DB_HOST = os.environ.get('LEGACY_DB_HOST', 'localhost')
DB_USER = os.environ.get('LEGACY_DB_USER', 'root')
DB_PASSWORD = os.environ.get('LEGACY_DB_PASSWORD', 'Admin@123')
DB_NAME = os.environ.get('LEGACY_DB_NAME', 'legacydb')

def get_connection():
    """Establishes a new database connection."""
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def get_subscriber_by_any_id(identifier):
    """
    Fetches a complete subscriber profile from the legacy DB using any primary identifier.
    It joins data from all related telecom tables.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # This is the main query that joins the four main tables.
            sql = """
            SELECT
                s.uid, s.imsi, s.msisdn, s.plan, s.subscription_state, s.service_class, s.charging_characteristics,
                hss.subscription_id, hss.profile_type, hss.private_user_id, hss.public_user_id,
                hlr.call_forward_unconditional, hlr.call_barring_all_outgoing, hlr.clip_provisioned, 
                hlr.clir_provisioned, hlr.call_hold_provisioned, hlr.call_waiting_provisioned,
                vas.account_status, vas.service_class_id, vas.language_id, vas.sim_type
            FROM subscribers s
            LEFT JOIN tbl_hss_profiles hss ON s.uid = hss.subscriber_uid
            LEFT JOIN tbl_hlr_features hlr ON s.uid = hlr.subscriber_uid
            LEFT JOIN tbl_vas_services vas ON s.uid = vas.subscriber_uid
            WHERE s.uid = %s OR s.imsi = %s OR s.msisdn = %s;
            """
            cursor.execute(sql, (identifier, identifier, identifier))
            subscriber_profile = cursor.fetchone()

            # If no subscriber was found, return None immediately.
            if not subscriber_profile:
                return None

            # If a subscriber was found, run a second query to get their PDP contexts (APNs).
            # This is done separately because it's a one-to-many relationship.
            pdp_sql = "SELECT context_id, apn, qos_profile FROM tbl_pdp_contexts WHERE subscriber_uid = %s;"
            cursor.execute(pdp_sql, (subscriber_profile['uid'],))
            pdp_contexts = cursor.fetchall()
            
            # Add the list of PDP contexts to the main profile object.
            subscriber_profile['pdp_contexts'] = pdp_contexts
            
            return subscriber_profile
            
    finally:
        conn.close()

def create_subscriber(data):
    """Placeholder for creating a subscriber. To be implemented."""
    print("CREATE subscriber logic needs to be implemented for the new schema.")
    pass

def delete_subscriber(uid):
    """Placeholder for deleting a subscriber. To be implemented."""
    print("DELETE subscriber logic needs to be updated for the new schema.")
    pass

