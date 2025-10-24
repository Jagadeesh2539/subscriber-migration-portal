import boto3
import os
import csv
import io
import json
from datetime import datetime
import legacy_db # Use the real DB connector
import urllib.parse # Needed to decode S3 key names with special characters

# Get env variables set by CloudFormation/deploy script
SUBSCRIBERS_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME')
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
    if not headers: return None
    for header in headers:
        h_lower = header.lower()
        if h_lower in ['uid', 'imsi', 'msisdn', 'subscriberid']:
            return header
    return None

def lambda_handler(event, context):
    print(f"Lambda invoked with event: {json.dumps(event)}") # Log the full event

    # --- FIX: Parse event correctly for S3 NotificationConfiguration ---
    # The actual S3 event information is nested within the 'Records' list.
    if not event.get('Records'):
        print("Error: Event payload does not contain 'Records'. Exiting.")
        return {'status': 'error', 'message': 'Invalid S3 event format'}

    record = event['Records'][0]
    
    # Check if the event is an S3 event
    if 's3' not in record:
        print(f"Error: Record does not contain 's3' key. Record: {record}")
        return {'status': 'error', 'message': 'Record is not an S3 event'}
        
    # Extract bucket name and object key
    try:
        bucket = record['s3']['bucket']['name']
        # S3 keys might have URL-encoded characters (like spaces becoming '+')
        key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8') 
    except KeyError as e:
        print(f"Error extracting bucket/key from S3 event: {e}. Event structure: {record.get('s3')}")
        return {'status': 'error', 'message': f'Missing key in S3 event structure: {e}'}
    # --- END FIX ---
    
    print(f"Processing s3://{bucket}/{key}")
    
    # Check if this is a valid trigger event (optional, but good practice)
    # The filter in CloudFormation should handle this, but double-checking adds robustness.
    if not key.startswith("uploads/") or not key.endswith(".csv"):
         print(f"Skipping file {key} as it does not match the required prefix/suffix.")
         return {'status': 'skipped', 'message': 'File path/type mismatch'}

    migration_id = None # Initialize migration_id
    try:
        head_object = s3_client.head_object(Bucket=bucket, Key=key)
        metadata = head_object.get('Metadata', {})
        migration_id = metadata.get('migrationid') # Use lowercase key consistent with API
        is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
        if not migration_id:
            raise Exception("migrationid not found in S3 metadata.")
    except Exception as e:
        print(f"Error getting metadata for {key}: {e}")
        # Try to extract migration_id from key if metadata fails (less reliable)
        if not migration_id and key.startswith("uploads/"):
             try:
                 filename = key.split('/')[-1]
                 migration_id = filename.replace(".csv", "")
                 print(f"Recovered migration_id from filename: {migration_id}")
             except Exception:
                 print("Could not recover migration_id from filename.")

        if migration_id: # Update job status if we have an ID
             jobs_table.update_item(Key={'migrationId': migration_id},UpdateExpression="SET #s=:s, failureReason=:fr",ExpressionAttributeNames={'#s': 'status'},ExpressionAttributeValues={':s': 'FAILED', ':fr': f'Metadata Read Error: {e}'})
        return {'status': 'error', 'message': str(e)}

    counts = { 'total': 0, 'migrated': 0, 'already_present': 0, 'not_found_in_legacy': 0, 'failed': 0 }
    report_data = [['Identifier', 'Status', 'Details']]

    try:
        db_creds = get_db_credentials()
        legacy_db.init_connection_details(**db_creds)
        print(f"Job {migration_id}: Successfully configured legacy DB connector.")
    except Exception as e:
        print(f"Job {migration_id}: DB Connection setup failed: {e}")
        jobs_table.update_item(Key={'migrationId': migration_id}, UpdateExpression="SET #s = :s, failureReason = :fr", ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':s': 'FAILED', ':fr': f'DB Connection Error: {e}'})
        return {'status': 'error'}

    try:
        csv_object = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = csv_object['Body'].read().decode('utf-8-sig') # Handle potential BOM
        reader = csv.DictReader(io.StringIO(csv_content))
        
        identifier_key = find_identifier_key(reader.fieldnames)
        if not identifier_key:
            raise Exception("Could not find a valid identifier (uid, imsi, or msisdn) in CSV header.")

        all_rows = list(reader)
        counts['total'] = len(all_rows)
        jobs_table.update_item(Key={'migrationId': migration_id}, UpdateExpression="SET #s = :s, totalRecords = :t", ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':s': 'IN_PROGRESS', ':t': counts['total']})
        print(f"Job {migration_id}: Starting processing for {counts['total']} records.")

        processed_count = 0
        for row in all_rows:
            processed_count += 1
            identifier_val = row.get(identifier_key)
            if not identifier_val:
                counts['failed'] += 1
                report_data.append([row.get(identifier_key, 'N/A'), 'FAILED', 'Identifier value was blank in CSV row.'])
                continue

            try:
                legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val) or {}
                cloud_data = subscribers_table.get_item(Key={'subscriberId': identifier_val}).get('Item')

                if legacy_data and not cloud_data:
                    status_detail = "Migrated successfully."
                    if not is_simulate_mode:
                        legacy_data['subscriberId'] = legacy_data.get('uid', identifier_val)
                        subscribers_table.put_item(Item=legacy_data)
                    else:
                        status_detail = "SIMULATED: Would have been migrated."
                    counts['migrated'] += 1
                    report_data.append([identifier_val, 'MIGRATED', status_detail])
                
                elif cloud_data:
                    counts['already_present'] += 1
                    report_data.append([identifier_val, 'SKIPPED', 'Already present in cloud.'])
                
                elif not legacy_data: # Check if legacy_data is empty dict
                    counts['not_found_in_legacy'] += 1
                    report_data.append([identifier_val, 'SKIPPED', 'Not found in legacy DB.'])
                    
            except Exception as row_error:
                print(f"Job {migration_id}: Error processing row for identifier {identifier_val}: {row_error}")
                counts['failed'] += 1
                report_data.append([identifier_val, 'FAILED', str(row_error)])
            
            # Optional: Update progress periodically for very large files
            # if processed_count % 100 == 0:
            #     print(f"Job {migration_id}: Processed {processed_count}/{counts['total']}...")
            #     # Consider updating DynamoDB progress here if needed

        print(f"Job {migration_id}: Processing complete. Migrated: {counts['migrated']}, Skipped: {counts['already_present'] + counts['not_found_in_legacy']}, Failed: {counts['failed']}")

        # Generate and upload report
        report_key = f"reports/{migration_id}.csv"
        report_buffer = io.StringIO()
        csv.writer(report_buffer).writerows(report_data)
        s3_client.put_object(Bucket=REPORT_BUCKET_NAME, Key=report_key, Body=report_buffer.getvalue())
        print(f"Job {migration_id}: Report uploaded to s3://{REPORT_BUCKET_NAME}/{report_key}")
        
        # Finalize job status
        jobs_table.update_item(
            Key={'migrationId': migration_id},
            UpdateExpression="SET #s=:s, migrated=:m, alreadyPresent=:ap, notFound_in_legacy=:nf, failed=:f, reportS3Key=:rk", # Corrected attribute name
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': 'COMPLETED', 
                ':m': counts['migrated'], 
                ':ap': counts['already_present'], 
                ':nf': counts['not_found_in_legacy'], # Corrected attribute name
                ':f': counts['failed'], 
                ':rk': report_key
            }
        )
        print(f"Job {migration_id}: Status updated to COMPLETED.")

    except Exception as e:
        print(f"Job {migration_id}: FATAL ERROR during processing: {e}")
        jobs_table.update_item(Key={'migrationId': migration_id}, UpdateExpression="SET #s = :s, failureReason = :fr", ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':s': 'FAILED', ':fr': str(e)})
    finally:
        # Clean up the original uploaded file
        try:
             s3_client.delete_object(Bucket=bucket, Key=key)
             print(f"Job {migration_id}: Deleted original upload file: s3://{bucket}/{key}")
        except Exception as delete_error:
             print(f"Job {migration_id}: Warning - Failed to delete original upload file s3://{bucket}/{key}. Error: {delete_error}")


    return {'status': 'success'}

