import threading
import uuid
import time
import csv
import boto3
import os
from io import StringIO

JOBS = {}
LEGACY_DB = {
    "502122900001234": {"uid": "502122900001234", "imsi": "502122900001234", "msisdn": "60132901234", "plan": "Gold"},
    "502122900001235": {"uid": "502122900001235", "imsi": "502122900001235", "msisdn": "60132901235", "plan": "Silver"}
}

def start_migration_job(file_obj, username):
    job_id = str(uuid.uuid4())
    
    JOBS[job_id] = {
        'status': 'IN_PROGRESS',
        'started_at': time.time(),
        'started_by': username,
        'total': 0,
        'processed': 0,
        'failed': 0
    }
    
    thread = threading.Thread(target=process_migration, args=(job_id, file_obj))
    thread.start()
    
    return job_id

def process_migration(job_id, file_obj):
    try:
        content = file_obj.read().decode('utf-8')
        reader = csv.DictReader(StringIO(content))
        
        rows = list(reader)
        JOBS[job_id]['total'] = len(rows)
        
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('SubscriberTable')
        
        for row in rows:
            if JOBS.get(job_id, {}).get('status') == 'CANCELLED':
                break
                
            try:
                uid = row.get('uid') or row.get('imsi') or row.get('msisdn')
                full_subscriber_data = LEGACY_DB.get(uid)
                
                if full_subscriber_data:
                    table.put_item(Item=full_subscriber_data)
                    JOBS[job_id]['processed'] += 1
                else:
                    JOBS[job_id]['failed'] += 1
            except Exception as e:
                JOBS[job_id]['failed'] += 1
                print(f"Error processing row: {e}")
            
            JOBS[job_id]['progress'] = int((JOBS[job_id]['processed'] / JOBS[job_id]['total']) * 100)
            time.sleep(0.01)
        
        if JOBS.get(job_id, {}).get('status') != 'CANCELLED':
            JOBS[job_id]['status'] = 'COMPLETED'
            JOBS[job_id]['completed_at'] = time.time()
        
    except Exception as e:
        JOBS[job_id]['status'] = 'FAILED'
        JOBS[job_id]['error'] = str(e)

def get_job_status(job_id):
    return JOBS.get(job_id, {'status': 'NOT_FOUND'})
