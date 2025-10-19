import boto3
import os
import csv
import io
import json
from datetime import datetime
import legacy_db # Use the real DB connector

# Get env variables set by CloudFormation/deploy script
SUBSCRIBERS_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME')
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST') # The RDS endpoint

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE_NAME)

def get_db_credentials():
    """Fetches database credentials securely from AWS Secrets Manager."""
    secrets_client = boto3.client('secretsmanager')
    try:
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        return {
            'host': LEGACY_DB_HOST,
            'port': 3306, # Standard RDS MySQL port
            'user': secret['username'],
            'password': secret['password'],
            'database': 'legacydb'
        }
    except Exception as e:
        print(f"FATAL: Could not retrieve DB credentials from Secrets Manager: {e}")
        raise

def find_identifier_key(headers):
    """Detects the main identifier from a list of CSV headers."""
    for header in headers:
        h_lower = header.lower()
        if h_lower in ['uid', 'imsi', 'msisdn', 'subscriberid']:
            return header
    return None

def lambda_handler(event, context):
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']
    
    print(f"Processing s3://{bucket}/{key}")
    
    try:
        head_object = s3_client.head_object(Bucket=bucket, Key=key)
        metadata = head_object.get('Metadata', {})
        migration_id = metadata.get('migrationid')
        is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
        if not migration_id:
            raise Exception("MigrationId not found in S3 metadata.")
    except Exception as e:
        print(f"Error getting metadata: {e}")
        # Update job table to reflect this critical failure
        if 'migration_id' in locals() and migration_id:
             jobs_table.update_item(Key={'migrationId': migration_id},UpdateExpression="SET #s=:s, failureReason=:fr",ExpressionAttributeNames={'#s': 'status'},ExpressionAttributeValues={':s': 'FAILED', ':fr': f'Metadata Read Error: {e}'})
        return {'status': 'error', 'message': str(e)}

    counts = { 'total': 0, 'migrated': 0, 'already_present': 0, 'not_found_in_legacy': 0, 'failed': 0 }
    report_data = [['Identifier', 'Status', 'Details']]

    try:
        # Configure the legacy_db connector with RDS details
        db_creds = get_db_credentials()
        legacy_db.init_connection_details(**db_creds)
        print("Successfully configured legacy DB connector.")
    except Exception as e:
        jobs_table.update_item(Key={'migrationId': migration_id}, UpdateExpression="SET #s = :s, failureReason = :fr", ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':s': 'FAILED', ':fr': f'DB Connection Error: {e}'})
        return {'status': 'error'}

    try:
        csv_object = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = csv_object['Body'].read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(csv_content))
        
        identifier_key = find_identifier_key(reader.fieldnames)
        if not identifier_key:
            raise Exception("Could not find a valid identifier (uid, imsi, or msisdn) in CSV header.")

        all_rows = list(reader)
        counts['total'] = len(all_rows)
        jobs_table.update_item(Key={'migrationId': migration_id}, UpdateExpression="SET #s = :s, totalRecords = :t", ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':s': 'IN_PROGRESS', ':t': counts['total']})

        for row in all_rows:
            identifier_val = row.get(identifier_key)
            if not identifier_val:
                counts['failed'] += 1
                report_data.append([row.get(identifier_key, 'N/A'), 'FAILED', 'Identifier value was blank in CSV row.'])
                continue

            try:
                # Fetch full profile from Legacy DB
                legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val)
                # Check if already exists in Cloud DB
                cloud_data = subscribers_table.get_item(Key={'subscriberId': identifier_val}).get('Item')

                if legacy_data and not cloud_data:
                    status_detail = "Migrated successfully."
                    if not is_simulate_mode:
                        # Ensure subscriberId is set for DynamoDB
                        legacy_data['subscriberId'] = legacy_data['uid']
                        subscribers_table.put_item(Item=legacy_data)
                    else:
                        status_detail = "SIMULATED: Would have been migrated."
                    counts['migrated'] += 1
                    report_data.append([identifier_val, 'MIGRATED', status_detail])
                elif cloud_data:
                    counts['already_present'] += 1
                    report_data.append([identifier_val, 'SKIPPED', 'Already present in cloud.'])
                elif not legacy_data:
                    counts['not_found_in_legacy'] += 1
                    report_data.append([identifier_val, 'SKIPPED', 'Not found in legacy DB.'])
            except Exception as e:
                counts['failed'] += 1
                report_data.append([identifier_val, 'FAILED', str(e)])

        # Generate and upload report
        report_key = f"reports/{migration_id}.csv"
        report_buffer = io.StringIO()
        csv.writer(report_buffer).writerows(report_data)
        s3_client.put_object(Bucket=REPORT_BUCKET_NAME, Key=report_key, Body=report_buffer.getvalue())
        
        # Finalize job status
        jobs_table.update_item(
            Key={'migrationId': migration_id},
            UpdateExpression="SET #s=:s, migrated=:m, alreadyPresent=:ap, notFound=:nf, failed=:f, reportS3Key=:rk",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'COMPLETED', ':m': counts['migrated'], ':ap': counts['already_present'], ':nf': counts['not_found_in_legacy'], ':f': counts['failed'], ':rk': report_key}
        )
    except Exception as e:
        print(f"FATAL ERROR during processing: {e}")
        jobs_table.update_item(Key={'migrationId': migration_id}, UpdateExpression="SET #s = :s, failureReason = :fr", ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':s': 'FAILED', ':fr': str(e)})
    finally:
        # Clean up the original uploaded file
        s3_client.delete_object(Bucket=bucket, Key=key)

    return {'status': 'success'}
