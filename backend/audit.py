import boto3
import os
import uuid
from datetime import datetime

# --- INTEGRATION FIX ---
AUDIT_LOG_TABLE_NAME = os.environ.get('AUDIT_LOG_TABLE_NAME')
if not AUDIT_LOG_TABLE_NAME:
    print("FATAL: AUDIT_LOG_TABLE_NAME environment variable not set.")

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
audit_table = dynamodb.Table(AUDIT_LOG_TABLE_NAME)
# --- END FIX ---

def log_audit(user, action, details, status):
    entry = {
        'LogId': str(uuid.uuid4()),        # Changed this key name to LogId
        'user': user,
        'action': action,
        'details': details,
        'status': status,
        'timestamp': datetime.utcnow().isoformat()
    }
    try:
        audit_table.put_item(Item=entry)
    except Exception as e:
        print(f"Error logging to DynamoDB: {e}")
    return entry
