import threading
import uuid
import time
import csv
import boto3
import os
from io import StringIO
from flask import current_app

# Global dictionary to track job statuses in memory (not persistent across Lambda invocations, but fine for simulation)
JOBS = {}
JOBS_LOCK = threading.Lock()  # Ensures thread-safe updates

# --- MOCK LEGACY DATA SOURCE ---
# This dictionary simulates the legacy database records that the bulk migration
# job needs to pull full subscriber profiles from.
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
            'progress': 0 # Initialize progress
        }
    
    # Use a thread for asynchronous processing (simulating a background worker)
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
    Simulates fetching subscriber profiles from a legacy source (mock) and
    migrating them to the Cloud DB (DynamoDB).
    """
    
    try:
        # Read file contents and create a dictionary reader
        content = file_obj.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))
        
        rows = list(reader)
        
        with JOBS_LOCK:
            JOBS[job_id]['total'] = len(rows)
        
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table_name = os.environ.get('SUBSCRIBER_TABLE_NAME', 'SubscriberTable')
        table = dynamodb.Table(table_name)
        
        for row in rows:
            # Check for cancellation before processing
            with JOBS_LOCK:
                if JOBS.get(job_id, {}).get('status') == 'CANCELLED':
                    current_app.logger.warning(f"Migration job {job_id} cancelled by user.")
                    break
                
            # Determine the key to search in the mock DB
            key = row.get('uid') or row.get('imsi') or row.get('msisdn')
            
            try:
                # --- MOCK PULL from Legacy Source ---
                full_subscriber_data = LEGACY_DB_MOCK.get(key)
                
                if full_subscriber_data:
                    # --- Cloud Write ---
                    data_to_write = full_subscriber_data.copy()
                    data_to_write['subscriberId'] = data_to_write['uid']
                    
                    table.put_item(Item=data_to_write)
                    update_job_progress(job_id, processed_increment=1)
                else:
                    update_job_progress(job_id, failed_increment=1)
                    current_app.logger.warning(f"Migration job {job_id}: Subscriber with key {key} not found in mock legacy data.")
                    
            except Exception as e:
                update_job_progress(job_id, failed_increment=1)
                current_app.logger.error(f"Error processing row in job {job_id}: {e}")
            
            # Simulate work delay
            time.sleep(0.05) 
        
        # Final status update
        with JOBS_LOCK:
            if JOBS.get(job_id, {}).get('status') != 'CANCELLED':
                JOBS[job_id]['status'] = 'COMPLETED'
                JOBS[job_id]['completed_at'] = time.time()
                current_app.logger.info(f"Migration job {job_id} completed successfully.")
        
    except Exception as e:
        # Critical failure handling
        with JOBS_LOCK:
            JOBS[job_id]['status'] = 'FAILED'
            JOBS[job_id]['error'] = str(e)
        current_app.logger.critical(f"Fatal error during migration job {job_id}: {e}")

def get_job_status(job_id):
    with JOBS_LOCK:
        return JOBS.get(job_id, {'status': 'NOT_FOUND'})
