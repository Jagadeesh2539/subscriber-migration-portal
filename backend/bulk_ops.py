import threading
import uuid
import time
import csv
import boto3
import os
from io import StringIO
from flask import current_app
import legacy_db # Import to access real legacy data if configured

# Global dictionary to track job statuses in memory (not persistent across Lambda invocations, but fine for simulation)
JOBS = {}
JOBS_LOCK = threading.Lock()  # Ensures thread-safe updates

# --- MOCK LEGACY DATA SOURCE ---
# This dictionary simulates the legacy database records that the bulk migration
# job needs to pull full subscriber profiles from. It is used as a fallback.
LEGACY_DB_MOCK = {
    # Standard profile used by the frontend sample CSV
    '502122900001234': {
        'subscriberId': '502122900001234', 
        'uid': '502122900001234', 
        'imsi': '502122900001234', 
        'msisdn': '60132901234', 
        'plan': 'Gold',
        'subscription_state': 'ACTIVE',
        'profile_type': 'DEFAULT_LTE_PROFILE',
        'call_hold_provisioned': True
    },
    '502122900001235': {
        'subscriberId': '502122900001235',
        'uid': '502122900001235', 
        'imsi': '502122900001235', 
        'msisdn': '60132901235', 
        'plan': 'Silver',
        'subscription_state': 'PENDING',
        'profile_type': 'DEFAULT_VOLTE_PROFILE',
        'call_hold_provisioned': False
    },
    # This entry will simulate a 'not found' failure if included in CSV
    '502122900001236': None 
}
# -------------------------------

def start_migration_job(file_obj, username):
    job_id = str(uuid.uuid4())
    
    with JOBS_LOCK:
        JOBS[job_id] = {
            'status': 'IN_PROGRESS',
            'started_at': time.time(),
            'started_by': username,
            'total': 0,
            'processed': 0,
            'failed': 0,
            'progress': 0 
        }
    
    thread = threading.Thread(target=process_migration, args=(job_id, file_obj))
    thread.start()
    current_app.logger.info(f"Migration job {job_id} started by {username}.")
    
    return job_id

def update_job_progress(job_id, processed_increment=0, failed_increment=0):
    """Updates job counters and recalculates percentage in a thread-safe manner."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return

        job['processed'] += processed_increment
        job['failed'] += failed_increment
        
        total = job['total']
        processed = job['processed']
        failed = job['failed']
        
        if total > 0:
            job['progress'] = int((processed + failed) / total * 100)
        else:
            job['progress'] = 0


def process_migration(job_id, file_obj):
    """
    Attempts to fetch data from the real legacy DB (if configured), falling back to mock 
    if the connection is blocked or fails.
    """
    
    # Flag to track if we successfully connected to the real Legacy DB
    using_mock = True

    try:
        content = file_obj.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))
        rows = list(reader)
        
        with JOBS_LOCK:
            JOBS[job_id]['total'] = len(rows)
        
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table_name = os.environ.get('SUBSCRIBER_TABLE_NAME', 'SubscriberTable')
        table = dynamodb.Table(table_name)
        
        # --- Attempt Real Legacy Connection ---
        try:
            # Tell legacy_db to use the migration connection rules (ENABLE_REAL_LEGACY_MIGRATION)
            legacy_db.get_connection(for_migration=True).close()
            using_mock = False
            current_app.logger.info(f"Migration job {job_id}: Successfully connected to real Legacy DB.")
        except Exception as e:
            current_app.logger.warning(f"Migration job {job_id}: Real Legacy DB connection failed or skipped. Falling back to mock data. Error: {e}")
            using_mock = True
        # -------------------------------------

        for row in rows:
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get('status') == 'CANCELLED':
                    current_app.logger.warning(f"Migration job {job_id} cancelled by user.")
                    break
                
            key = row.get('uid') or row.get('imsi') or row.get('msisdn')
            
            try:
                if not key:
                    raise ValueError("Row is missing UID, IMSI, and MSISDN.")

                full_subscriber_data = None
                
                if not using_mock:
                    # Attempt to pull full data from the real Legacy DB
                    full_subscriber_data = legacy_db.get_subscriber_by_any_id(key, for_migration=True)
                else:
                    # Use mock data if real connection failed/blocked
                    full_subscriber_data = LEGACY_DB_MOCK.get(key)
                
                
                if full_subscriber_data:
                    # --- Cloud Write ---
                    data_to_write = full_subscriber_data.copy()
                    data_to_write['subscriberId'] = data_to_write['uid']
                    
                    table.put_item(Item=data_to_write)
                    update_job_progress(job_id, processed_increment=1)
                else:
                    update_job_progress(job_id, failed_increment=1)
                    current_app.logger.warning(f"Migration job {job_id}: Subscriber {key} not found in source ({'MOCK' if using_mock else 'REAL DB'}).")
                    
            except Exception as e:
                update_job_progress(job_id, failed_increment=1)
                current_app.logger.error(f"Error processing row in job {job_id}: {e}")
            
            time.sleep(0.05) 
        
        # Final status update
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get('status') != 'CANCELLED':
                JOBS[job_id]['status'] = 'COMPLETED'
                JOBS[job_id]['completed_at'] = time.time()
                current_app.logger.info(f"Migration job {job_id} completed successfully.")
        
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]['status'] = 'FAILED'
            JOBS[job_id]['error'] = str(e)
        current_app.logger.critical(f"Fatal error during migration job {job_id}: {e}")

def get_job_status(job_id):
    with JOBS_LOCK:
        # Return a deep copy of the job to prevent accidental external modification
        job_copy = JOBS.get(job_id, {'status': 'NOT_FOUND'}).copy()
        
        # Ensure status is always set correctly, particularly if it was paused/cancelled mid-loop
        if job_copy['status'] == 'IN_PROGRESS' and job_copy.get('paused'):
            job_copy['status'] = 'PAUSED'
            
        return job_copy
