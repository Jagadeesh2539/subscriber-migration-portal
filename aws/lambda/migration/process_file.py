#!/usr/bin/env python3
import json
import os
import boto3
from botocore.exceptions import ClientError
import csv
from io import StringIO
from datetime import datetime
import uuid

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, InputValidator,
    format_subscriber_for_db, SubscriberStatus, JobType, JobStatus
)

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    
    # Environment variables
    SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE')
    MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE')
    UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')
    
    subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE) if SUBSCRIBERS_TABLE else None
    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE) if MIGRATION_JOBS_TABLE else None
    
except Exception as e:
    print(f"AWS services initialization error: {e}")
    dynamodb = None
    s3_client = None
    subscribers_table = None
    jobs_table = None


def lambda_handler(event, context):
    """Process migration file and perform bulk operations"""
    try:
        # Handle both Step Functions and S3 event triggers
        if 'Records' in event:  # S3 event
            return handle_s3_trigger(event, context)
        else:  # Step Functions trigger
            return handle_step_functions_trigger(event, context)
    
    except Exception as e:
        print(f"File processing error: {str(e)}")
        return {
            'statusCode': 500,
            'processedRecords': 0,
            'successRecords': 0,
            'failedRecords': 0,
            'error': str(e)
        }


def handle_s3_trigger(event, context):
    """Handle S3 object creation trigger"""
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        # Extract job ID from file key (uploads/{job_id}/filename.csv)
        try:
            job_id = key.split('/')[1]
        except IndexError:
            print(f"Could not extract job ID from key: {key}")
            continue
        
        print(f"Processing S3 upload: {key} for job {job_id}")
        
        # Process the file
        result = process_migration_file({
            'jobId': job_id,
            'inputFileKey': key,
            'jobType': 'MIGRATION',  # Default for S3 uploads
            'batchSize': 100
        })
        
        return result


def handle_step_functions_trigger(event, context):
    """Handle Step Functions trigger"""
    job_id = event.get('jobId')
    input_file_key = event.get('inputFileKey')
    job_type = event.get('jobType', 'MIGRATION')
    batch_size = event.get('batchSize', 100)
    filters = event.get('filters', {})
    
    print(f"Processing Step Functions job {job_id}: {job_type}")
    
    if job_type in [JobType.MIGRATION, JobType.BULK_DELETE]:
        return process_migration_file(event)
    else:
        return {
            'statusCode': 400,
            'error': f'Unsupported job type for file processing: {job_type}'
        }


def process_migration_file(event):
    """Process migration CSV file"""
    job_id = event.get('jobId')
    input_file_key = event.get('inputFileKey')
    job_type = event.get('jobType', 'MIGRATION')
    batch_size = event.get('batchSize', 100)
    
    if not all([job_id, input_file_key, s3_client, subscribers_table]):
        return {
            'statusCode': 500,
            'error': 'Required services not available',
            'processedRecords': 0,
            'successRecords': 0,
            'failedRecords': 0
        }
    
    processed_count = 0
    success_count = 0
    failed_count = 0
    errors = []
    
    try:
        # Download file from S3
        response = s3_client.get_object(Bucket=UPLOADS_BUCKET, Key=input_file_key)
        content = response['Body'].read().decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(StringIO(content))
        
        # Process records in batches
        batch = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Clean and validate row
                clean_row = {k.strip(): v.strip() if v else '' for k, v in row.items()}
                
                # Skip empty rows
                if not any(clean_row.values()):
                    continue
                
                processed_count += 1
                
                # Validate required fields
                if not clean_row.get('uid'):
                    errors.append(f'Row {row_num}: UID is required')
                    failed_count += 1
                    continue
                
                # Add to batch
                batch.append(clean_row)
                
                # Process batch when full
                if len(batch) >= batch_size:
                    batch_result = process_batch(batch, job_type)
                    success_count += batch_result['success']
                    failed_count += batch_result['failed']
                    errors.extend(batch_result['errors'])
                    batch = []
            
            except Exception as e:
                print(f"Error processing row {row_num}: {e}")
                errors.append(f'Row {row_num}: {str(e)}')
                failed_count += 1
        
        # Process remaining batch
        if batch:
            batch_result = process_batch(batch, job_type)
            success_count += batch_result['success']
            failed_count += batch_result['failed']
            errors.extend(batch_result['errors'])
        
        # Generate output file if there are errors
        output_file_key = None
        if errors:
            output_file_key = generate_error_report(job_id, errors)
        
        return {
            'statusCode': 200,
            'processedRecords': processed_count,
            'successRecords': success_count,
            'failedRecords': failed_count,
            'errors': errors[:100],  # Limit errors in response
            'outputFileKey': output_file_key
        }
    
    except Exception as e:
        print(f"File processing failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'processedRecords': processed_count,
            'successRecords': success_count,
            'failedRecords': failed_count
        }


def process_batch(batch, job_type):
    """Process a batch of records"""
    success_count = 0
    failed_count = 0
    errors = []
    
    if job_type == JobType.MIGRATION:
        return process_migration_batch(batch)
    elif job_type == JobType.BULK_DELETE:
        return process_delete_batch(batch)
    else:
        return {
            'success': 0,
            'failed': len(batch),
            'errors': [f'Unsupported job type: {job_type}'] * len(batch)
        }


def process_migration_batch(batch):
    """Process migration batch - create/update subscribers"""
    success_count = 0
    failed_count = 0
    errors = []
    
    try:
        # Batch write to DynamoDB
        with subscribers_table.batch_writer() as batch_writer:
            for record in batch:
                try:
                    # Format record for DynamoDB
                    formatted_record = format_subscriber_for_db(record, system='cloud')
                    
                    # Validate required fields
                    if not all([formatted_record.get('uid'), formatted_record.get('msisdn'), formatted_record.get('imsi')]):
                        errors.append(f"UID {record.get('uid', 'unknown')}: Missing required fields")
                        failed_count += 1
                        continue
                    
                    # Write to DynamoDB
                    batch_writer.put_item(Item=formatted_record)
                    success_count += 1
                
                except Exception as e:
                    print(f"Error processing record {record.get('uid', 'unknown')}: {e}")
                    errors.append(f"UID {record.get('uid', 'unknown')}: {str(e)}")
                    failed_count += 1
    
    except Exception as e:
        print(f"Batch migration failed: {e}")
        # If batch fails, mark all as failed
        failed_count = len(batch)
        success_count = 0
        errors = [f'Batch operation failed: {str(e)}'] * len(batch)
    
    return {
        'success': success_count,
        'failed': failed_count,
        'errors': errors
    }


def process_delete_batch(batch):
    """Process delete batch - remove subscribers"""
    success_count = 0
    failed_count = 0
    errors = []
    
    try:
        # Batch delete from DynamoDB
        with subscribers_table.batch_writer() as batch_writer:
            for record in batch:
                try:
                    uid = record.get('uid', '').strip()
                    
                    if not uid:
                        errors.append(f"Row: UID is required for deletion")
                        failed_count += 1
                        continue
                    
                    # Delete from DynamoDB
                    batch_writer.delete_item(Key={'uid': uid})
                    success_count += 1
                
                except Exception as e:
                    print(f"Error deleting record {record.get('uid', 'unknown')}: {e}")
                    errors.append(f"UID {record.get('uid', 'unknown')}: {str(e)}")
                    failed_count += 1
    
    except Exception as e:
        print(f"Batch deletion failed: {e}")
        failed_count = len(batch)
        success_count = 0
        errors = [f'Batch deletion failed: {str(e)}'] * len(batch)
    
    return {
        'success': success_count,
        'failed': failed_count,
        'errors': errors
    }


def generate_error_report(job_id, errors):
    """Generate error report and upload to S3"""
    try:
        if not errors:
            return None
        
        # Create error report content
        error_report = {
            'jobId': job_id,
            'timestamp': datetime.utcnow().isoformat(),
            'totalErrors': len(errors),
            'errors': errors
        }
        
        # Convert to CSV format
        csv_content = "Row,Error\n"
        for error in errors:
            csv_content += f'"{error.replace('"', '""')}"\n'
        
        # Upload to S3
        output_key = f"reports/{job_id}/errors_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        
        s3_client.put_object(
            Bucket=UPLOADS_BUCKET,
            Key=output_key,
            Body=csv_content,
            ContentType='text/csv',
            Metadata={
                'job-id': job_id,
                'report-type': 'errors',
                'error-count': str(len(errors))
            }
        )
        
        print(f"Error report uploaded: {output_key}")
        return output_key
    
    except Exception as e:
        print(f"Failed to generate error report: {e}")
        return None