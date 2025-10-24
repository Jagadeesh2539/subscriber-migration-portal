import boto3
import os
import csv
import io
import json
from datetime import datetime
import urllib.parse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
SUBSCRIBERS_TABLE_NAME = os.environ.get('SUBSCRIBERS_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME')
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Initialize DynamoDB tables
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE_NAME)

def get_db_credentials():
    """Fetches database credentials from Secrets Manager"""
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
        logger.error(f"Error fetching DB credentials: {e}")
        raise

def fetch_subscriber_from_legacy(identifier, db_creds):
    """Fetch subscriber data from legacy database"""
    try:
        # This is a placeholder - implement actual DB connection
        # For now, simulate successful lookup
        return {
            'uid': identifier,
            'imsi': f"imsi_{identifier}",
            'msisdn': f"msisdn_{identifier}",
            'status': 'active'
        }
    except Exception as e:
        logger.error(f"Error fetching subscriber {identifier}: {e}")
        return None

def update_job_status(migration_id, status, **kwargs):
    """Update job status in DynamoDB"""
    try:
        update_expression = "SET #s = :status, lastUpdated = :updated"
        expression_values = {
            ':status': status,
            ':updated': datetime.utcnow().isoformat()
        }
        expression_names = {'#s': 'status'}
        
        # Add optional fields
        for key, value in kwargs.items():
            if value is not None:
                placeholder = f":{key}"
                update_expression += f", {key} = {placeholder}"
                expression_values[placeholder] = value
        
        jobs_table.update_item(
            Key={'JobId': migration_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        logger.info(f"Updated job {migration_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
        raise

def generate_report(migration_id, results, is_simulate_mode):
    """Generate and upload CSV report to S3"""
    try:
        # Create CSV content
        csv_buffer = io.StringIO()
        fieldnames = ['identifier', 'status', 'reason', 'legacy_data', 'timestamp']
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        
        for result in results:
            writer.writerow(result)
        
        csv_content = csv_buffer.getvalue()
        
        # Upload to S3
        report_key = f"reports/{migration_id}/migration-report.csv"
        s3_client.put_object(
            Bucket=REPORT_BUCKET_NAME,
            Key=report_key,
            Body=csv_content,
            ContentType='text/csv',
            Metadata={
                'migration-id': migration_id,
                'generated-at': datetime.utcnow().isoformat(),
                'simulate-mode': str(is_simulate_mode).lower()
            }
        )
        
        logger.info(f"Report uploaded to s3://{REPORT_BUCKET_NAME}/{report_key}")
        return report_key
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return None

def lambda_handler(event, context):
    """Main Lambda handler for processing migration files"""
    logger.info(f"Migration processor invoked with event: {json.dumps(event)}")
    
    try:
        # Parse S3 event
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            logger.info(f"Processing file: s3://{bucket}/{key}")
            
            # Extract migration details from S3 metadata or filename
            migration_id = None
            is_simulate_mode = False
            job_type = 'migration'
            
            try:
                # Get object metadata
                metadata_response = s3_client.head_object(Bucket=bucket, Key=key)
                metadata = metadata_response.get('Metadata', {})
                
                # FIXED: Check both metadata field names for compatibility
                migration_id = (
                    metadata.get('jobid') or 
                    metadata.get('migrationid') or
                    metadata.get('migration-id')
                )
                is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
                job_type = metadata.get('jobtype', 'migration')
                
                if not migration_id:
                    raise KeyError("Migration ID not found in metadata")
                    
                logger.info(f"Extracted from metadata: ID={migration_id}, Simulate={is_simulate_mode}, Type={job_type}")
                
            except Exception as metadata_error:
                logger.warning(f"Metadata extraction failed: {metadata_error}")
                
                # Fallback: extract from filename
                try:
                    migration_id = key.split('/')[-1].replace('.csv', '')
                    
                    # Determine job type from path
                    if 'deletions/' in key:
                        job_type = 'deletion'
                    elif 'audits/' in key:
                        job_type = 'audit_sync'
                    else:
                        job_type = 'migration'
                    
                    logger.info(f"Fallback extraction: ID={migration_id}, Type={job_type}")
                    
                    if not migration_id:
                        raise ValueError("Could not extract migration ID from filename")
                        
                except Exception as fallback_error:
                    logger.error(f"Both metadata and filename extraction failed: {fallback_error}")
                    return {
                        'statusCode': 500,
                        'body': json.dumps({
                            'status': 'error',
                            'message': f'Could not determine migration ID: {str(metadata_error)}'
                        })
                    }
            
            # Update job status to IN_PROGRESS
            update_job_status(migration_id, 'IN_PROGRESS', 
                            statusMessage='Processing CSV file...')
            
            # Download and process CSV file
            try:
                csv_object = s3_client.get_object(Bucket=bucket, Key=key)
                csv_content = csv_object['Body'].read().decode('utf-8')
                csv_reader = csv.DictReader(io.StringIO(csv_content))
                
                # Validate CSV headers
                identifiers = ['uid', 'imsi', 'msisdn', 'subscriberid']
                headers_lower = [h.lower() for h in csv_reader.fieldnames] if csv_reader.fieldnames else []
                
                if not any(identifier in headers_lower for identifier in identifiers):
                    raise Exception(f"CSV must contain at least one identifier column: {', '.join(identifiers)}")
                
                logger.info(f"CSV validated with headers: {headers_lower}")
                
                # Process all rows
                all_rows = list(csv_reader)
                counts = {
                    'total': len(all_rows),
                    'migrated': 0,
                    'alreadyPresent': 0,
                    'not_found_in_legacy': 0,
                    'failed': 0,
                    'deleted': 0
                }
                
                results = []  # For report generation
                
                logger.info(f"Processing {counts['total']} rows (Simulate: {is_simulate_mode}, Type: {job_type})")
                
                # Update job with total count
                update_job_status(migration_id, 'IN_PROGRESS', 
                                totalRecords=counts['total'],
                                statusMessage=f'Processing {counts["total"]} records...')
                
                # Process each row
                for idx, row in enumerate(all_rows, 1):
                    # Get identifier from row
                    identifier = (
                        row.get('uid') or row.get('UID') or
                        row.get('imsi') or row.get('IMSI') or  
                        row.get('msisdn') or row.get('MSISDN') or
                        row.get('subscriberid') or row.get('subscriberId') or 
                        row.get('SUBSCRIBERID')
                    )
                    
                    if not identifier:
                        counts['failed'] += 1
                        results.append({
                            'identifier': 'N/A',
                            'status': 'failed',
                            'reason': 'No identifier found in row',
                            'legacy_data': '',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        continue
                    
                    try:
                        if job_type == 'deletion':
                            # Handle deletion jobs
                            existing_item = subscribers_table.get_item(Key={'SubscriberId': identifier})
                            
                            if 'Item' not in existing_item:
                                counts['not_found_in_legacy'] += 1
                                results.append({
                                    'identifier': identifier,
                                    'status': 'not_found',
                                    'reason': 'Subscriber not found in cloud database',
                                    'legacy_data': '',
                                    'timestamp': datetime.utcnow().isoformat()
                                })
                                continue
                            
                            if not is_simulate_mode:
                                subscribers_table.delete_item(Key={'SubscriberId': identifier})
                                
                            counts['deleted'] += 1
                            results.append({
                                'identifier': identifier,
                                'status': 'deleted' if not is_simulate_mode else 'would_delete',
                                'reason': 'Successfully deleted from cloud',
                                'legacy_data': json.dumps(existing_item['Item']),
                                'timestamp': datetime.utcnow().isoformat()
                            })
                            
                        else:
                            # Handle migration jobs (default)
                            # Check if subscriber already exists in cloud
                            existing_item = subscribers_table.get_item(Key={'SubscriberId': identifier})
                            
                            if 'Item' in existing_item:
                                counts['alreadyPresent'] += 1
                                results.append({
                                    'identifier': identifier,
                                    'status': 'already_present',
                                    'reason': 'Subscriber already exists in cloud',
                                    'legacy_data': json.dumps(existing_item['Item']),
                                    'timestamp': datetime.utcnow().isoformat()
                                })
                                continue
                            
                            # Fetch from legacy system
                            db_creds = get_db_credentials()
                            subscriber_data = fetch_subscriber_from_legacy(identifier, db_creds)
                            
                            if not subscriber_data:
                                counts['not_found_in_legacy'] += 1
                                results.append({
                                    'identifier': identifier,
                                    'status': 'not_found_in_legacy',
                                    'reason': 'Subscriber not found in legacy database',
                                    'legacy_data': '',
                                    'timestamp': datetime.utcnow().isoformat()
                                })
                                continue
                            
                            # Migrate to cloud (unless simulate mode)
                            if not is_simulate_mode:
                                subscribers_table.put_item(Item={
                                    'SubscriberId': identifier,
                                    'uid': subscriber_data.get('uid'),
                                    'imsi': subscriber_data.get('imsi'),
                                    'msisdn': subscriber_data.get('msisdn'),
                                    'status': subscriber_data.get('status', 'active'),
                                    'migrationId': migration_id,
                                    'migratedAt': datetime.utcnow().isoformat()
                                })
                            
                            counts['migrated'] += 1
                            results.append({
                                'identifier': identifier,
                                'status': 'migrated' if not is_simulate_mode else 'would_migrate',
                                'reason': 'Successfully migrated to cloud',
                                'legacy_data': json.dumps(subscriber_data),
                                'timestamp': datetime.utcnow().isoformat()
                            })
                        
                        # Update progress every 100 records
                        if idx % 100 == 0:
                            progress_msg = f'Processed {idx}/{counts["total"]} records...'
                            update_job_status(migration_id, 'IN_PROGRESS',
                                            statusMessage=progress_msg,
                                            **{k: v for k, v in counts.items() if k != 'total'})
                            logger.info(f"Progress update: {progress_msg}")
                        
                    except Exception as row_error:
                        logger.error(f"Error processing row {idx} (identifier: {identifier}): {row_error}")
                        counts['failed'] += 1
                        results.append({
                            'identifier': identifier,
                            'status': 'failed',
                            'reason': f'Processing error: {str(row_error)}',
                            'legacy_data': '',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                
                # Generate report
                report_key = generate_report(migration_id, results, is_simulate_mode)
                
                # Update job to completed status
                final_status = 'COMPLETED'
                status_message = f"Successfully processed {counts['total']} records"
                
                if is_simulate_mode:
                    status_message += " (SIMULATION MODE)"
                
                update_job_status(
                    migration_id, 
                    final_status,
                    statusMessage=status_message,
                    reportS3Key=report_key,
                    **{k: v for k, v in counts.items() if k != 'total'}
                )
                
                logger.info(f"Job {migration_id} completed successfully: {counts}")
                
            except Exception as processing_error:
                logger.error(f"Processing error for job {migration_id}: {processing_error}")
                
                # Update job to failed status
                update_job_status(
                    migration_id,
                    'FAILED',
                    statusMessage=f'Processing failed: {str(processing_error)}',
                    failureReason=str(processing_error)
                )
                
                raise processing_error
                
    except Exception as handler_error:
        logger.error(f"Lambda handler error: {handler_error}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': str(handler_error)
            })
        }
    
    finally:
        # Clean up processed file
        try:
            if 'bucket' in locals() and 'key' in locals():
                s3_client.delete_object(Bucket=bucket, Key=key)
                logger.info(f"Cleaned up file: s3://{bucket}/{key}")
        except Exception as cleanup_error:
            logger.warning(f"File cleanup failed (non-critical): {cleanup_error}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'success',
            'message': 'Migration processing completed'
        })
    }