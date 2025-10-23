import json
import boto3
import pandas as pd
import logging
import traceback
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
import io
import os
import csv
import legacy_db

# Configure comprehensive logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter for detailed logs
formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s')
for handler in logger.handlers:
    handler.setFormatter(formatter)

# Environment variables with validation
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
REPORT_BUCKET_NAME = os.environ.get('REPORT_BUCKET_NAME', os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME'))
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')

logger.info(f"?? Lambda Environment Configuration:")
logger.info(f"  SUBSCRIBER_TABLE_NAME: {SUBSCRIBER_TABLE_NAME}")
logger.info(f"  MIGRATION_JOBS_TABLE_NAME: {MIGRATION_JOBS_TABLE_NAME}")
logger.info(f"  REPORT_BUCKET_NAME: {REPORT_BUCKET_NAME}")
logger.info(f"  LEGACY_DB_HOST: {LEGACY_DB_HOST}")
logger.info(f"  LEGACY_DB_SECRET_ARN: {'***configured***' if LEGACY_DB_SECRET_ARN else 'NOT SET'}")

# AWS clients - initialize once for performance
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
subscribers_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

def get_db_credentials():
    """Fetches database credentials securely from AWS Secrets Manager with enhanced error handling."""
    try:
        logger.info(f"?? Retrieving DB credentials from Secrets Manager: {LEGACY_DB_SECRET_ARN}")
        
        if not LEGACY_DB_SECRET_ARN:
            raise ValueError("LEGACY_DB_SECRET_ARN environment variable not set")
        
        secrets_client = boto3.client('secretsmanager')
        response = secrets_client.get_secret_value(SecretId=LEGACY_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])

        creds = {
            'host': LEGACY_DB_HOST,
            'port': 3306,
            'user': secret['username'],
            'password': secret['password'],
            'database': 'legacydb'
        }
        
        logger.info(f"? DB credentials retrieved successfully for host: {creds['host']}")
        return creds
        
    except Exception as e:
        logger.error(f"? FATAL: Could not retrieve DB credentials: {str(e)}")
        raise Exception(f"Database credentials error: {str(e)}")

def find_identifier_key(headers):
    """Detects the main identifier from CSV headers with enhanced logic."""
    logger.info(f"?? Analyzing CSV headers: {headers}")
    
    if not headers:
        logger.error("? No headers provided")
        return None
    
    # Priority order for identifiers
    priority_identifiers = [
        'uid', 'subscriber_id', 'subscriberId', 'imsi', 'msisdn', 
        'user_id', 'userId', 'id', 'subscriber_uid'
    ]
    
    # Convert headers to lowercase for comparison
    header_map = {h.lower().strip(): h for h in headers}
    
    for identifier in priority_identifiers:
        if identifier.lower() in header_map:
            found_header = header_map[identifier.lower()]
            logger.info(f"? Found primary identifier: '{found_header}' (matched: {identifier})")
            return found_header
    
    logger.error(f"? No valid identifier key found in headers: {headers}")
    logger.error(f"   Expected one of: {priority_identifiers}")
    return None

def lambda_handler(event, context):
    """
    Enhanced Lambda handler for processing S3-triggered migration files
    """
    try:
        logger.info(f"?? Lambda invoked with event: {json.dumps(event, default=str, indent=2)}")
        
        # Validate event structure
        if 'Records' not in event or len(event['Records']) == 0:
            raise ValueError("Invalid event structure - no S3 records found")
        
        results = []
        
        # Process each S3 record
        for record_index, record in enumerate(event['Records']):
            try:
                logger.info(f"?? Processing record {record_index + 1}/{len(event['Records'])}")
                
                # Extract S3 event details
                bucket_name = record['s3']['bucket']['name']
                object_key = unquote_plus(record['s3']['object']['key'])
                event_name = record['eventName']
                object_size = record['s3']['object'].get('size', 0)
                
                logger.info(f"?? S3 Event: {event_name}")
                logger.info(f"   File: s3://{bucket_name}/{object_key}")
                logger.info(f"   Size: {object_size} bytes")
                
                # Validate file type
                if not object_key.lower().endswith('.csv'):
                    logger.warning(f"?? Skipping non-CSV file: {object_key}")
                    continue
                
                # Process the migration file
                result = process_migration_file(bucket_name, object_key)
                results.append({
                    'file': object_key,
                    'status': 'success',
                    'result': result
                })
                
            except Exception as record_error:
                logger.error(f"?? Failed to process record {record_index + 1}: {str(record_error)}")
                logger.error(traceback.format_exc())
                
                # Try to extract job ID for error reporting
                try:
                    job_id = extract_job_id_from_key_or_metadata(bucket_name, record['s3']['object']['key'])
                    if job_id:
                        update_job_status(job_id, 'FAILED', f'Processing error: {str(record_error)}')
                except Exception as update_error:
                    logger.error(f"? Could not update job status: {str(update_error)}")
                
                results.append({
                    'file': record['s3']['object']['key'],
                    'status': 'error',
                    'error': str(record_error)
                })
                
                # Continue processing other records
                continue
        
        logger.info(f"?? Lambda execution completed. Processed {len(results)} records")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {len(results)} records',
                'results': results
            }, default=str)
        }
        
    except Exception as e:
        logger.error(f"?? Lambda execution failed: {str(e)}")
        logger.error(traceback.format_exc())
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Lambda execution failed',
                'message': str(e)
            })
        }

def extract_job_id_from_key_or_metadata(bucket_name, object_key):
    """Extract job ID from S3 object key or metadata"""
    try:
        # First try to get from metadata
        head_object = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        metadata = head_object.get('Metadata', {})
        
        job_id = metadata.get('jobid')
        if job_id:
            logger.info(f"?? Job ID from metadata: {job_id}")
            return job_id
        
        # Fallback: extract from key path
        key = object_key.strip()
        if '/' in key:
            filename = key.split('/')[-1]
        else:
            filename = key
        
        if filename.lower().endswith('.csv'):
            job_id = filename[:-4]
        else:
            job_id = filename
        
        if len(job_id) >= 8:  # Basic UUID validation
            logger.info(f"?? Job ID from filename: {job_id}")
            return job_id
        
        logger.warning(f"?? Could not extract valid job ID from: {object_key}")
        return None
        
    except Exception as e:
        logger.error(f"? Error extracting job ID: {str(e)}")
        return None

def process_migration_file(bucket_name, object_key):
    """Main file processing logic with comprehensive error handling"""
    job_id = None
    
    try:
        logger.info(f"?? Starting file processing: s3://{bucket_name}/{object_key}")
        
        # Extract job metadata
        job_id, job_type, is_simulate_mode, sync_direction = extract_job_metadata(bucket_name, object_key)
        logger.info(f"?? Job Configuration:")
        logger.info(f"   ID: {job_id}")
        logger.info(f"   Type: {job_type}")
        logger.info(f"   Simulate: {is_simulate_mode}")
        logger.info(f"   Sync Direction: {sync_direction}")
        
        # Update status to processing
        update_job_status(job_id, 'IN_PROGRESS', 'CSV file downloaded, initializing processing...')
        
        # Initialize database connection
        initialize_database_connection()
        
        # Download and validate file
        csv_content = download_and_validate_csv(bucket_name, object_key)
        
        # Parse CSV data
        df, identifier_key = parse_and_validate_csv(csv_content, job_id)
        total_records = len(df)
        logger.info(f"?? Processing {total_records} records with identifier: {identifier_key}")
        
        # Update job with total records
        update_job_status(job_id, 'IN_PROGRESS', f'Processing {total_records} records...', {
            'totalRecords': total_records
        })
        
        # Process records based on job type
        if job_type == 'MIGRATION':
            result = process_migration_records(df, identifier_key, job_id, is_simulate_mode)
        elif job_type == 'BULK_DELETION':
            result = process_deletion_records(df, identifier_key, job_id, is_simulate_mode)
        elif job_type == 'AUDIT_SYNC':
            result = process_audit_sync_records(df, identifier_key, job_id, sync_direction, is_simulate_mode)
        else:
            raise ValueError(f"Unsupported job type: {job_type}")
        
        # Generate and upload report
        report_s3_key = generate_processing_report(job_id, result, job_type, bucket_name)
        result['report_s3_key'] = report_s3_key
        
        # Update job with final results
        success_message = f"{job_type.replace('_', ' ').title()} completed successfully"
        if is_simulate_mode:
            success_message += " (Simulation Mode)"
        
        update_job_status(job_id, 'COMPLETED', success_message, result)
        
        # Clean up uploaded file
        cleanup_uploaded_file(bucket_name, object_key)
        
        logger.info(f"?? Job {job_id} completed successfully: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Processing failed: {str(e)}"
        logger.error(f"?? Job {job_id} failed: {error_msg}")
        logger.error(traceback.format_exc())
        
        if job_id:
            update_job_status(job_id, 'FAILED', error_msg)
        
        raise

def extract_job_metadata(bucket_name, object_key):
    """Extract job metadata from S3 object"""
    try:
        head_object = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        metadata = head_object.get('Metadata', {})
        
        job_id = metadata.get('jobid')
        if not job_id:
            # Try to extract from filename as fallback
            filename = object_key.split('/')[-1]
            if filename.lower().endswith('.csv'):
                job_id = filename[:-4]
        
        if not job_id:
            raise ValueError("Job ID not found in metadata or filename")
        
        # Determine job type
        job_type_meta = metadata.get('jobtype', 'migration').lower()
        if 'deletion' in job_type_meta or object_key.startswith('deletions/'):
            job_type = 'BULK_DELETION'
        elif 'audit' in job_type_meta or object_key.startswith('audits/'):
            job_type = 'AUDIT_SYNC'
        else:
            job_type = 'MIGRATION'
        
        is_simulate_mode = metadata.get('issimulatemode', 'false').lower() == 'true'
        sync_direction = metadata.get('syncdirection', 'LEGACY_TO_CLOUD')
        
        return job_id, job_type, is_simulate_mode, sync_direction
        
    except Exception as e:
        logger.error(f"? Error extracting job metadata: {str(e)}")
        raise

def initialize_database_connection():
    """Initialize database connection with enhanced error handling"""
    try:
        logger.info("?? Initializing database connection...")
        db_creds = get_db_credentials()
        legacy_db.init_connection_details(**db_creds)
        logger.info("? Database connection initialized successfully")
        
    except Exception as e:
        logger.error(f"? Database connection failed: {str(e)}")
        raise Exception(f"Database connection error: {str(e)}")

def download_and_validate_csv(bucket_name, object_key):
    """Download and validate CSV file from S3"""
    try:
        logger.info(f"?? Downloading CSV from s3://{bucket_name}/{object_key}")
        
        csv_object = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        csv_content = csv_object['Body'].read().decode('utf-8')
        
        if not csv_content.strip():
            raise ValueError("CSV file is empty")
        
        logger.info(f"? CSV downloaded successfully: {len(csv_content)} characters")
        return csv_content
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchKey':
            raise FileNotFoundError(f"CSV file not found: s3://{bucket_name}/{object_key}")
        elif error_code == 'AccessDenied':
            raise PermissionError(f"Access denied to CSV file: s3://{bucket_name}/{object_key}")
        else:
            raise Exception(f"S3 error ({error_code}): {e.response['Error']['Message']}")
    except UnicodeDecodeError:
        raise ValueError("CSV file contains invalid characters - please ensure UTF-8 encoding")
    except Exception as e:
        raise Exception(f"Failed to download CSV file: {str(e)}")

def parse_and_validate_csv(csv_content, job_id):
    """Parse and validate CSV content"""
    try:
        logger.info(f"?? Parsing CSV content for job {job_id}")
        
        # Parse CSV using DictReader for better handling
        reader = csv.DictReader(io.StringIO(csv_content))
        
        if not reader.fieldnames:
            raise ValueError("CSV file has no headers")
        
        # Find identifier key
        identifier_key = find_identifier_key(reader.fieldnames)
        if not identifier_key:
            raise ValueError(f"CSV must contain a valid identifier. Found headers: {list(reader.fieldnames)}")
        
        # Convert to pandas DataFrame for easier processing
        all_rows = list(reader)
        if not all_rows:
            raise ValueError("CSV file contains no data rows")
        
        df = pd.DataFrame(all_rows)
        
        # Remove empty rows
        df = df.dropna(how='all')
        if df.empty:
            raise ValueError("CSV file contains no valid data after removing empty rows")
        
        logger.info(f"? CSV parsed successfully:")
        logger.info(f"   Headers: {list(df.columns)}")
        logger.info(f"   Records: {len(df)}")
        logger.info(f"   Identifier: {identifier_key}")
        
        return df, identifier_key
        
    except pd.errors.EmptyDataError:
        raise ValueError("CSV file is empty or corrupted")
    except pd.errors.ParserError as e:
        raise ValueError(f"CSV parsing error: {str(e)}")
    except Exception as e:
        raise ValueError(f"CSV validation failed: {str(e)}")

def process_migration_records(df, identifier_key, job_id, is_simulate_mode):
    """Process migration records with enhanced progress tracking"""
    logger.info(f"?? Processing {len(df)} migration records (simulate: {is_simulate_mode})")
    
    counts = {
        'total_records': len(df),
        'migrated': 0,
        'failed': 0,
        'already_present': 0,
        'not_found_in_legacy': 0
    }
    
    report_data = [['Identifier', 'Status', 'Details']]
    batch_size = 50  # Process in batches for better performance
    
    try:
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            logger.info(f"?? Processing batch {i//batch_size + 1}: records {i+1}-{min(i+batch_size, len(df))}")
            
            batch_result = process_migration_batch(batch, identifier_key, is_simulate_mode)
            
            # Update counts
            for key in counts:
                if key != 'total_records':
                    counts[key] += batch_result.get(key, 0)
            
            # Add to report
            report_data.extend(batch_result.get('report_rows', []))
            
            # Update progress every 10 batches
            if (i // batch_size) % 10 == 0:
                progress = min(100, int(((i + batch_size) / len(df)) * 100))
                update_job_status(job_id, 'IN_PROGRESS', 
                    f"Migrated {counts['migrated']}/{len(df)} records ({progress}%)", counts)
        
        # Store report data for later use
        counts['report_data'] = report_data
        
        logger.info(f"? Migration processing completed: {counts}")
        return counts
        
    except Exception as e:
        logger.error(f"? Migration processing failed: {str(e)}")
        raise

def process_migration_batch(batch_df, identifier_key, is_simulate_mode):
    """Process a batch of migration records"""
    batch_counts = {
        'migrated': 0,
        'failed': 0,
        'already_present': 0,
        'not_found_in_legacy': 0
    }
    
    report_rows = []
    
    for index, row in batch_df.iterrows():
        try:
            identifier_val = row.get(identifier_key, '').strip()
            if not identifier_val:
                batch_counts['failed'] += 1
                report_rows.append([f"Row {index}", 'FAILED', 'Empty identifier value'])
                continue
            
            result = process_single_migration(identifier_val, is_simulate_mode)
            batch_counts[result['status']] += 1
            report_rows.append([identifier_val, result['status'].upper().replace('_', ' '), result['details']])
            
        except Exception as e:
            logger.warning(f"?? Error processing row {index}: {str(e)}")
            batch_counts['failed'] += 1
            report_rows.append([f"Row {index}", 'FAILED', str(e)])
    
    return {**batch_counts, 'report_rows': report_rows}

def process_single_migration(identifier_val, is_simulate_mode):
    """Process a single migration record"""
    try:
        logger.debug(f"?? Processing migration for: {identifier_val}")
        
        # Query legacy database
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val)
        
        # Query cloud database (using subscriberId as primary key)
        cloud_response = subscribers_table.get_item(Key={'subscriberId': identifier_val})
        cloud_data = cloud_response.get('Item')
        
        logger.debug(f"   Legacy data: {'Found' if legacy_data else 'Not found'}")
        logger.debug(f"   Cloud data: {'Found' if cloud_data else 'Not found'}")
        
        if legacy_data and not cloud_data:
            if not is_simulate_mode:
                # Prepare data for cloud insertion
                legacy_data['subscriberId'] = legacy_data.get('uid', identifier_val)
                subscribers_table.put_item(Item=legacy_data)
                return {'status': 'migrated', 'details': 'Successfully migrated from legacy to cloud'}
            else:
                return {'status': 'migrated', 'details': 'SIMULATED: Would have been migrated'}
        
        elif cloud_data:
            return {'status': 'already_present', 'details': 'Already exists in cloud database'}
        
        elif not legacy_data:
            return {'status': 'not_found_in_legacy', 'details': 'Not found in legacy database'}
        
        else:
            return {'status': 'failed', 'details': 'Unexpected state during processing'}
        
    except Exception as e:
        logger.error(f"? Error processing migration for {identifier_val}: {str(e)}")
        return {'status': 'failed', 'details': str(e)}

def process_deletion_records(df, identifier_key, job_id, is_simulate_mode):
    """Process deletion records"""
    logger.info(f"??? Processing {len(df)} deletion records (simulate: {is_simulate_mode})")
    
    counts = {
        'total_records': len(df),
        'deleted': 0,
        'failed': 0,
        'not_found_in_cloud': 0
    }
    
    report_data = [['Identifier', 'Status', 'Details']]
    
    try:
        for index, row in df.iterrows():
            try:
                identifier_val = row.get(identifier_key, '').strip()
                if not identifier_val:
                    counts['failed'] += 1
                    report_data.append([f"Row {index}", 'FAILED', 'Empty identifier'])
                    continue
                
                result = process_single_deletion(identifier_val, is_simulate_mode)
                counts[result['status']] += 1
                report_data.append([identifier_val, result['status'].upper().replace('_', ' '), result['details']])
                
                # Update progress periodically
                if index % 100 == 0:
                    progress = int((index / len(df)) * 100)
                    update_job_status(job_id, 'IN_PROGRESS', 
                        f"Processed {index}/{len(df)} deletions ({progress}%)", counts)
                
            except Exception as e:
                counts['failed'] += 1
                report_data.append([f"Row {index}", 'FAILED', str(e)])
        
        counts['report_data'] = report_data
        return counts
        
    except Exception as e:
        logger.error(f"? Deletion processing failed: {str(e)}")
        raise

def process_single_deletion(identifier_val, is_simulate_mode):
    """Process a single deletion record"""
    try:
        # Query cloud database
        cloud_response = subscribers_table.get_item(Key={'subscriberId': identifier_val})
        cloud_data = cloud_response.get('Item')
        
        if cloud_data:
            if not is_simulate_mode:
                subscribers_table.delete_item(Key={'subscriberId': identifier_val})
                return {'status': 'deleted', 'details': 'Successfully deleted from cloud'}
            else:
                return {'status': 'deleted', 'details': 'SIMULATED: Would have been deleted'}
        else:
            return {'status': 'not_found_in_cloud', 'details': 'Not found in cloud database'}
            
    except Exception as e:
        return {'status': 'failed', 'details': str(e)}

def process_audit_sync_records(df, identifier_key, job_id, sync_direction, is_simulate_mode):
    """Process audit and sync records"""
    logger.info(f"?? Processing {len(df)} audit records (direction: {sync_direction}, simulate: {is_simulate_mode})")
    
    counts = {
        'total_records': len(df),
        'synced': 0,
        'migrated': 0,
        'failed': 0,
        'conflicts': 0
    }
    
    report_data = [['Identifier', 'Status', 'Details']]
    
    try:
        for index, row in df.iterrows():
            try:
                identifier_val = row.get(identifier_key, '').strip()
                if not identifier_val:
                    counts['failed'] += 1
                    report_data.append([f"Row {index}", 'FAILED', 'Empty identifier'])
                    continue
                
                result = process_single_audit_sync(identifier_val, sync_direction, is_simulate_mode)
                counts[result['status']] += 1
                report_data.append([identifier_val, result['status'].upper().replace('_', ' '), result['details']])
                
                # Update progress periodically
                if index % 50 == 0:
                    progress = int((index / len(df)) * 100)
                    update_job_status(job_id, 'IN_PROGRESS', 
                        f"Audited {index}/{len(df)} records ({progress}%)", counts)
                
            except Exception as e:
                counts['failed'] += 1
                report_data.append([f"Row {index}", 'FAILED', str(e)])
        
        counts['report_data'] = report_data
        return counts
        
    except Exception as e:
        logger.error(f"? Audit sync processing failed: {str(e)}")
        raise

def process_single_audit_sync(identifier_val, sync_direction, is_simulate_mode):
    """Process a single audit sync record"""
    try:
        # Query both databases
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier_val)
        cloud_response = subscribers_table.get_item(Key={'subscriberId': identifier_val})
        cloud_data = cloud_response.get('Item')
        
        if legacy_data and cloud_data:
            # Compare data for differences
            differences = []
            for field in ['imsi', 'msisdn', 'plan']:
                if legacy_data.get(field) != cloud_data.get(field):
                    differences.append(field)
            
            if differences:
                if sync_direction in ['LEGACY_TO_CLOUD', 'BOTH_WAYS'] and not is_simulate_mode:
                    legacy_data['subscriberId'] = legacy_data.get('uid', identifier_val)
                    subscribers_table.put_item(Item=legacy_data)
                    return {'status': 'synced', 'details': f'Synced differences in: {", ".join(differences)}'}
                else:
                    return {'status': 'synced', 'details': f'SIMULATED: Would sync: {", ".join(differences)}'}
            else:
                return {'status': 'synced', 'details': 'Data already in sync'}
        
        elif legacy_data and not cloud_data:
            if sync_direction in ['LEGACY_TO_CLOUD', 'BOTH_WAYS']:
                if not is_simulate_mode:
                    legacy_data['subscriberId'] = legacy_data.get('uid', identifier_val)
                    subscribers_table.put_item(Item=legacy_data)
                    return {'status': 'migrated', 'details': 'Migrated from legacy to cloud'}
                else:
                    return {'status': 'migrated', 'details': 'SIMULATED: Would migrate to cloud'}
            else:
                return {'status': 'failed', 'details': 'Exists in legacy only, sync direction prevents migration'}
        
        elif cloud_data and not legacy_data:
            return {'status': 'failed', 'details': 'Exists in cloud only, not in legacy'}
        
        else:
            return {'status': 'failed', 'details': 'Not found in either database'}
            
    except Exception as e:
        return {'status': 'failed', 'details': str(e)}

def update_job_status(job_id, status, message, result_data=None):
    """Update job status in DynamoDB with comprehensive error handling"""
    try:
        update_expression = "SET #status = :status, #msg = :msg, #updated = :updated"
        expression_attribute_names = {
            '#status': 'status',
            '#msg': 'statusMessage',
            '#updated': 'lastUpdated'
        }
        expression_attribute_values = {
            ':status': status,
            ':msg': message,
            ':updated': int(time.time())
        }
        
        # Add result data if provided
        if result_data:
            for key, value in result_data.items():
                if value is not None and key != 'report_data':
                    attr_name = f"#{key}"
                    attr_value = f":{key}"
                    update_expression += f", {attr_name} = {attr_value}"
                    expression_attribute_names[attr_name] = key
                    expression_attribute_values[attr_value] = value
        
        jobs_table.update_item(
            Key={'JobId': job_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        logger.info(f"? Updated job {job_id} status to {status}")
        
    except Exception as e:
        logger.error(f"? Failed to update job status for {job_id}: {str(e)}")
        # Don't re-raise to avoid breaking the main flow

def generate_processing_report(job_id, result, job_type, bucket_name):
    """Generate and upload comprehensive processing report"""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Get report data
        report_data = result.get('report_data', [])
        
        if not report_data:
            logger.warning("?? No report data available, generating summary only")
            report_data = [['Summary', 'Status', 'Details']]
        
        # Create CSV report
        report_buffer = io.StringIO()
        writer = csv.writer(report_buffer)
        
        # Add header information
        writer.writerow([f'# {job_type.replace("_", " ").title()} Report'])
        writer.writerow([f'# Job ID: {job_id}'])
        writer.writerow([f'# Generated: {timestamp}'])
        writer.writerow(['# '])
        writer.writerow([f'# Summary Statistics:'])
        
        for key, value in result.items():
            if key not in ['report_data', 'report_s3_key'] and isinstance(value, (int, float, str)):
                writer.writerow([f'# {key}: {value}'])
        
        writer.writerow(['# '])
        
        # Add detailed results
        writer.writerows(report_data)
        
        # Upload report to S3
        report_key = f"reports/{job_id}-{job_type.lower()}-report.csv"
        report_bucket = REPORT_BUCKET_NAME or bucket_name
        
        s3_client.put_object(
            Bucket=report_bucket,
            Key=report_key,
            Body=report_buffer.getvalue(),
            ContentType='text/csv',
            Metadata={
                'job-id': job_id,
                'job-type': job_type,
                'generated-at': timestamp
            }
        )
        
        logger.info(f"?? Report uploaded: s3://{report_bucket}/{report_key}")
        return report_key
        
    except Exception as e:
        logger.error(f"? Failed to generate report for job {job_id}: {str(e)}")
        return None

def cleanup_uploaded_file(bucket_name, object_key):
    """Clean up the uploaded CSV file"""
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=object_key)
        logger.info(f"??? Cleaned up uploaded file: s3://{bucket_name}/{object_key}")
    except Exception as e:
        logger.warning(f"?? Could not clean up uploaded file: {str(e)}")
