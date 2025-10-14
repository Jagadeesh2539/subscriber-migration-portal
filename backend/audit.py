import boto3
import os
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
audit_table = dynamodb.Table('AuditLogTable')

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
        print(f"Error logging to DynamoDB: {e}")
    return entry
