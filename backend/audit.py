import boto3
import os
import uuid
from datetime import datetime

# --- INTEGRATION FIX ---
# Get the table name from the Lambda environment variables.
# This name is set by the deploy.yml workflow.
AUDIT_LOG_TABLE_NAME = os.environ.get('AUDIT_LOG_TABLE_NAME')
if not AUDIT_LOG_TABLE_NAME:
    print("FATAL: AUDIT_LOG_TABLE_NAME environment variable not set.")

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
# Use the environment variable to connect to the correct table
audit_table = dynamodb.Table(AUDIT_LOG_TABLE_NAME)
# --- END FIX ---

def log_audit(user, action, details, status):
    entry = {
        'id': str(uuid.uuid4()),
        'user': user,
        'action': action,
        'details': details,
        'status': status,
        'timestamp': datetime.utcnow().isoformat()
    }
    try:
        audit_table.put_item(Item=entry)
    except Exception as e:
        # Don't fail the main request, just print the log error
        print(f"Error logging to DynamoDB: {e}")
    return entry
