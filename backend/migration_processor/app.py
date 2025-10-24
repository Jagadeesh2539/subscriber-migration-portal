import boto3
import os
import csv
import io
import json
from datetime import datetime
import legacy_db  # Legacy DB connection
import urllib.parse

# Get env variables
SUBSCRIBERS_TABLE_NAME = os.environ.get('SUBSCRIBERS_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME')
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE_NAME)

def get_db_credentials():
    """Fetches database credentials from Secrets Manager"""
    secrets_client = boto3.client('secretsmanager')
    try:
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        return {
            'host': LEGACY_DB_HOST,
            'user': secret.get('username'),
            'password': secret.get('password'),
            'database': secret.get('database', 'legacy_subscribers')
        }
    except Exception as e:
        print(f"Error fetching DB credentials: {e}")
        raise

def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event received: {json.dumps(event)}")
    
    bucket = None
    key = None
    
    try:
        # Parse S3 event
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            print(f"Processing file: s3://{bucket}/{key}")
            
            migration_id = None
            is_simulate_mode = False
            
            # Extract migration_id from S3 metadata
            try:
                metadata_response = s3_client.head_object(Bucket=bucket, Key=key)
                metadata = metadata_response.get('Metadata', {})
                migration_id = metadata.get('migrationid')
                is_simulate_mode = metadata.get('simulate', 'false').lower() == 'true'
                
                if not migration_id:
                    raise KeyError("migrationid not found in S3 metadata")
                    
                print(f"Migration ID from metadata: {migration_id}, Simulate Mode: {is_simulate_mode}")
                
            except Exception as metadata_error:
                print(f"Error getting metadata for {key}: {metadata_error}")
                
                # Fallback: extract migration_id from filename
                try:
                    # Assuming filename format: uploads/{migration_id}.csv
                    migration_id = key.split('/')[-1].replace('.csv', '')
                    print(f"Recovered migration_id from filename: {migration_id}")
                    
                    if not migration_id:
                        raise ValueError("Could not extract migration_id from filename")
                    
                    # Log warning but continue processing
                    print(f"Continuing processing with recovered migration_id: {migration_id}")
                    
                except Exception as fallback_error:
                    print(f"Fallback failed: {fallback_error}")
                    # If we can't get migration_id at all, fail the job
                    return {
                        'statusCode': 500,
                        'body': json.dumps({
                            'status': 'error',
                            'message': f'Could not determine migration_id: {str(metadata_error)}'
                        })
                    }
            
            # Ensure we have a migration_id before proceeding
            if not migration_id:
                print("ERROR: migration_id is still None after all attempts")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Failed to extract migration_id from metadata or filename'
                    })
                }
            
            # Update job status to PROCESSING
            try:
                jobs_table.update_item(
                    Key={'JobId': migration_id},
                    UpdateExpression="SET jobStatus = :status",
                    ExpressionAttributeValues={':status': 'PROCESSING'}
                )
                print(f"Updated job {migration_id} status to PROCESSING")
            except Exception as update_error:
                print(f"Error updating job status to PROCESSING: {update_error}")
            
            # Download and process CSV
            try:
                csv_object = s3_client.get_object(Bucket=bucket, Key=key)
                csv_content = csv_object['Body'].read().decode('utf-8')
                reader = csv.DictReader(io.StringIO(csv_content))
                
                # Validate CSV headers
                identifiers = ['uid', 'imsi', 'msisdn', 'subscriberid']
                headers_lower = [h.lower() for h in reader.fieldnames] if reader.fieldnames else []
                
                if not any(identifier in headers_lower for identifier in identifiers):
                    raise Exception(f"CSV must contain at least one identifier column: {', '.join(identifiers)}")
                
                print(f"CSV headers validated: {headers_lower}")
                
                # Count rows
                all_rows = list(reader)
                counts = {'total': len(all_rows), 'migrated': 0, 'skipped': 0, 'failed': 0}
                
                print(f"Job {migration_id}: Processing {counts['total']} subscribers (Simulate: {is_simulate_mode})")
                
                # Process each row
                processed_count = 0
                for row in all_rows:
                    processed_count += 1
                    
                    # Get identifier value from any available column
                    identifier_value = (
                        row.get('uid') or row.get('UID') or
                        row.get('imsi') or row.get('IMSI') or
                        row.get('msisdn') or row.get('MSISDN') or
                        row.get('subscriberid') or row.get('subscriberId') or row.get('SUBSCRIBERID')
                    )
                    
                    if not identifier_value:
                        counts['skipped'] += 1
                        print(f"Row {processed_count}: No identifier found, skipping")
                        continue
                    
                    try:
                        # Fetch data from legacy DB
                        db_creds = get_db_credentials()
                        subscriber_data = legacy_db.fetch_subscriber(identifier_value, db_creds)
                        
                        if not subscriber_data:
                            counts['skipped'] += 1
                            print(f"Subscriber {identifier_value} not found in legacy DB")
                            continue
                        
                        # Check if subscriber already exists in DynamoDB
                        try:
                            existing = subscribers_table.get_item(Key={'subscriberId': identifier_value})
                            
                            if 'Item' in existing:
                                counts['skipped'] += 1
                                print(f"Subscriber {identifier_value} already exists in DynamoDB")
                                continue
                        except Exception as check_error:
                            print(f"Error checking existing subscriber {identifier_value}: {check_error}")
                            # Continue to attempt migration anyway
                        
                        # Insert into DynamoDB (only if not simulate mode)
                        if not is_simulate_mode:
                            subscribers_table.put_item(Item={
                                'subscriberId': identifier_value,
                                'uid': subscriber_data.get('uid'),
                                'imsi': subscriber_data.get('imsi'),
                                'msisdn': subscriber_data.get('msisdn'),
                                'migrationId': migration_id,
                                'migratedAt': datetime.now().isoformat()
                            })
                            print(f"Successfully migrated subscriber: {identifier_value}")
                        else:
                            print(f"SIMULATE MODE: Would migrate subscriber: {identifier_value}")
                        
                        counts['migrated'] += 1
                        
                    except Exception as row_error:
                        counts['failed'] += 1
                        print(f"Error processing subscriber {identifier_value}: {row_error}")
                
                # Update job status to COMPLETED
                final_status = 'COMPLETED' if not is_simulate_mode else 'SIMULATED'
                try:
                    jobs_table.update_item(
                        Key={'JobId': migration_id},
                        UpdateExpression="SET jobStatus = :status, migratedCount = :migrated, skippedCount = :skipped, failedCount = :failed, totalCount = :total",
                        ExpressionAttributeValues={
                            ':status': final_status,
                            ':migrated': counts['migrated'],
                            ':skipped': counts['skipped'],
                            ':failed': counts['failed'],
                            ':total': counts['total']
                        }
                    )
                    print(f"Job {migration_id} completed with status {final_status}: {counts}")
                except Exception as final_update_error:
                    print(f"Error updating final job status: {final_update_error}")
                
            except Exception as processing_error:
                print(f"Job {migration_id} failed during processing: {processing_error}")
                try:
                    jobs_table.update_item(
                        Key={'JobId': migration_id},
                        UpdateExpression="SET jobStatus = :status, errorMessage = :error",
                        ExpressionAttributeValues={
                            ':status': 'FAILED',
                            ':error': str(processing_error)
                        }
                    )
                except Exception as error_update_error:
                    print(f"Error updating job status to FAILED: {error_update_error}")
                
                raise processing_error
                
    except Exception as handler_error:
        print(f"Handler error: {handler_error}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': str(handler_error)
            })
        }
    
    finally:
        # Clean up - delete processed file
        if bucket and key:
            try:
                s3_client.delete_object(Bucket=bucket, Key=key)
                print(f"Deleted processed file: s3://{bucket}/{key}")
            except Exception as cleanup_error:
                print(f"Cleanup error (non-critical): {cleanup_error}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'status': 'success'})
    }
