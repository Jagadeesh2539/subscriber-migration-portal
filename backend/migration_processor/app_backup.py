import boto3
import os
import csv
import io
import json
from datetime import datetime
import legacy_db

# Environment variables
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME', MIGRATION_UPLOAD_BUCKET_NAME)  # Fallback to upload bucket
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')
MIGRATION_UPLOAD_BUCKET_NAME = os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME')

print(f"Environment check:")
print(f"SUBSCRIBER_TABLE_NAME: {SUBSCRIBER_TABLE_NAME}")
print(f"MIGRATION_JOBS_TABLE_NAME: {MIGRATION_JOBS_TABLE_NAME}")
print(f"REPORT_BUCKET_NAME: {REPORT_BUCKET_NAME}")

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

def get_db_credentials():
    """Fetches database credentials securely from AWS Secrets Manager."""
    secrets_client = boto3.client('secretsmanager')
    try:
        print(f"Getting secret: {LEGACY_DB_SECRET_ARN}")
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        
        creds = {
            'host': LEGACY_DB_HOST,
            'port': 3306,
            'user': secret['username'],
            'password': secret['password'],
            'database': 'legacydb'
        }
        print(f"DB credentials retrieved for host: {creds['host']}")
        return creds
    except Exception as e:
        print(f"FATAL: Could not retrieve DB credentials: {e}")
        raise

def find_identifier_key(headers):
    """Detects the main identifier from a list of CSV headers."""
    print(f"CSV headers: {headers}")
    for header in headers:
        h_lower = header.lower()
        if h_lower in ['uid', 'imsi', 'msisdn', 'subscriberid']:
            print(f"Found identifier key: {header}")
            return header
    print("No valid identifier key found")
    return None

def lambda_handler(event, context):
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']
    
    print(f"Processing s3://{bucket}/{key}")
    
    migration_id = None
    try:
        head_object = s3_client.head_object(Bucket=bucket, Key=key)
        metadata = head_object.get('Metadata', {})
        print(f"S3 metadata: {metadata}")
        
        migration_id = metadata.get('jobid')
        is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
        
        print(f"Migration ID: {migration_id}")
        print(f"Simulate mode: {is_simulate_mode}")
        
        if not migration_id:
            raise Exception("Migration ID not found in S3 metadata.")
            
    except Exception as e:
        print(f"Error getting metadata: {e}")
        if migration_id:
            try:
                jobs_table.update_item(
                    Key={'JobId': migration_id},
                    UpdateExpression="SET #s=:s, failureReason=:fr",
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':s': 'FAILED', ':fr': f'Metadata Read Error: {e}'}
                )
            except Exception as update_e:
                print(f"Failed to update job status: {update_e}")
        return {'status': 'error', 'message': str(e)}

    counts = {'total': 0, 'migrated': 0, 'already_present': 0, 'not_found_in_legacy': 0, 'failed': 0}
    report_data = [['Identifier', 'Status', 'Details']]

    try:
        # Database connection
        db_creds = get_db_credentials()
        legacy_db.init_connection_details(**db_creds)
        print("Successfully configured legacy DB connector.")
        
        # Test legacy DB connection
        test_result = legacy_db.get_subscriber_by_any_id('502122900001234')  # Test with known ID
        print(f"Legacy DB test query result: {test_result is not None}")
        
    except Exception as e:
        print(f"DB Connection Error: {e}")
        try:
            jobs_table.update_item(
                Key={'JobId': migration_id}, 
                UpdateExpression="SET #s = :s, failureReason = :fr", 
                ExpressionAttributeNames={'#s': 'status'}, 
                ExpressionAttributeValues={':s': 'FAILED', ':fr': f'DB Connection Error: {e}'}
            )
        except Exception as update_e:
            print(f"Failed to update job status: {update_e}")
        return {'status': 'error'}

    try:
        # Process CSV
        print("Reading CSV from S3...")
        csv_object = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = csv_object['Body'].read().decode('utf-8')
        print(f"CSV content length: {len(csv_content)} characters")
        
        reader = csv.DictReader(io.StringIO(csv_content))
        
        identifier_key = find_identifier_key(reader.fieldnames)
        if not identifier_key:
            raise Exception("Could not find a valid identifier (uid, imsi, or msisdn) in CSV header.")

        all_rows = list(reader)
        counts['total'] = len(all_rows)
        print(f"Processing {counts['total']} rows")
        
        # Update job to IN_PROGRESS
        print(f"Updating job {migration_id} to IN_PROGRESS...")
        jobs_table.update_item(
            Key={'JobId': migration_id}, 
            UpdateExpression="SET #s = :s, totalRecords = :t", 
            ExpressionAttributeNames={'#s': 'status'}, 
            ExpressionAttributeValues={':s': 'IN_PROGRESS', ':t': counts['total']}
        )
        print("Job status updated to IN_PROGRESS")

        # Process each row
        for i, row in enumerate(all_rows):
            identifier_val = row.get(identifier_key)
            print(f"\n--- Processing row {i+1}/{counts['total']}: {identifier_val} ---")
            
            if not identifier_val:
                print("Identifier value is blank")
                counts['failed'] += 1
                report_data.append([row.get(identifier_key, 'N/A'), 'FAILED', 'Identifier value was blank in CSV row.'])
                continue

            try:
                # Query legacy database
                print(f"Querying legacy DB for {identifier_val}...")
                legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val)
                print(f"Legacy data found: {legacy_data is not None}")
                
                # FIXED: Query cloud database with correct key
                print(f"Querying cloud DB for SubscriberId={identifier_val}...")
                cloud_response = subscribers_table.get_item(Key={'SubscriberId': identifier_val})
                cloud_data = cloud_response.get('Item')
                print(f"Cloud data found: {cloud_data is not None}")

                if legacy_data and not cloud_data:
                    print(f"Migrating {identifier_val}...")
                    status_detail = "Migrated successfully."
                    if not is_simulate_mode:
                        # FIXED: Use correct key name for DynamoDB
                        legacy_data['SubscriberId'] = legacy_data['uid']
                        subscribers_table.put_item(Item=legacy_data)
                        print(f"Successfully migrated {identifier_val}")
                    else:
                        status_detail = "SIMULATED: Would have been migrated."
                        print(f"SIMULATED migration for {identifier_val}")
                    counts['migrated'] += 1
                    report_data.append([identifier_val, 'MIGRATED', status_detail])
                    
                elif cloud_data:
                    print(f"Skipping {identifier_val} - already present in cloud")
                    counts['already_present'] += 1
                    report_data.append([identifier_val, 'SKIPPED', 'Already present in cloud.'])
                    
                elif not legacy_data:
                    print(f"Skipping {identifier_val} - not found in legacy")
                    counts['not_found_in_legacy'] += 1
                    report_data.append([identifier_val, 'SKIPPED', 'Not found in legacy DB.'])
                    
            except Exception as e:
                print(f"ERROR processing {identifier_val}: {e}")
                counts['failed'] += 1
                report_data.append([identifier_val, 'FAILED', str(e)])

        # Create and upload report
        print("Creating migration report...")
        report_key = f"reports/{migration_id}.csv"
        report_buffer = io.StringIO()
        csv.writer(report_buffer).writerows(report_data)
        
        # Use the same bucket for reports if REPORT_BUCKET_NAME is not set
        report_bucket = REPORT_BUCKET_NAME or bucket
        s3_client.put_object(
            Bucket=report_bucket,
            Key=report_key, 
            Body=report_buffer.getvalue()
        )
        print(f"Report uploaded to s3://{report_bucket}/{report_key}")
        
        # Update job to COMPLETED
        print(f"Updating job {migration_id} to COMPLETED...")
        print(f"Final counts: {counts}")
        
        jobs_table.update_item(
            Key={'JobId': migration_id},
            UpdateExpression="SET #s=:s, migrated=:m, alreadyPresent=:ap, not_found_in_legacy=:nf, failed=:f, reportS3Key=:rk",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': 'COMPLETED', 
                ':m': counts['migrated'], 
                ':ap': counts['already_present'], 
                ':nf': counts['not_found_in_legacy'], 
                ':f': counts['failed'], 
                ':rk': report_key
            }
        )
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"FATAL ERROR during processing: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        try:
            jobs_table.update_item(
                Key={'JobId': migration_id}, 
                UpdateExpression="SET #s = :s, failureReason = :fr", 
                ExpressionAttributeNames={'#s': 'status'}, 
                ExpressionAttributeValues={':s': 'FAILED', ':fr': str(e)}
            )
            print("Job marked as FAILED")
        except Exception as update_e:
            print(f"Failed to update job status: {update_e}")
            
    finally:
        # Clean up uploaded CSV
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            print(f"Deleted uploaded CSV: {key}")
        except Exception as e:
            print(f"Warning: Could not delete uploaded file: {e}")

    return {'status': 'success'}
