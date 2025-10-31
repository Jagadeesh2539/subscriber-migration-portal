#!/usr/bin/env python3
import json
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import uuid
import time

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, InputValidator,
    handle_cors_preflight, log_request, log_response,
    JobType, JobStatus, SubscriberStatus
)

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    sfn_client = boto3.client('stepfunctions')
    
    # Environment variables
    MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE')
    UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')
    MIGRATION_WORKFLOW_ARN = os.environ.get('MIGRATION_WORKFLOW_ARN')
    AUDIT_WORKFLOW_ARN = os.environ.get('AUDIT_WORKFLOW_ARN')
    EXPORT_WORKFLOW_ARN = os.environ.get('EXPORT_WORKFLOW_ARN')
    
    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE) if MIGRATION_JOBS_TABLE else None
    
except Exception as e:
    print(f"AWS services initialization error: {e}")
    dynamodb = None
    s3_client = None
    sfn_client = None
    jobs_table = None


def lambda_handler(event, context):
    """Main orchestrator for Step Functions job management"""
    start_time = time.time()
    
    try:
        # Log request
        log_request(event, context)
        
        method = event.get('httpMethod', 'GET')
        path = event.get('resource', event.get('path', ''))
        headers = event.get('headers', {})
        origin = headers.get('origin')
        
        # Handle CORS preflight
        cors_response = handle_cors_preflight(event)
        if cors_response:
            return cors_response
        
        # Route to appropriate handler
        if '/migration/upload' in path and method == 'POST':
            response = handle_upload_request(event, origin)
        elif '/migration/jobs' in path and method == 'POST':
            response = handle_create_migration_job(event, origin)
        elif '/audit/jobs' in path and method == 'POST':
            response = handle_create_audit_job(event, origin)
        elif '/export/jobs' in path and method == 'POST':
            response = handle_create_export_job(event, origin)
        elif '/jobs/' in path and '/cancel' in path and method == 'POST':
            response = handle_cancel_job(event, origin)
        elif '/jobs/' in path and method == 'GET':
            response = handle_get_job_status(event, origin)
        elif '/jobs' in path and method == 'GET':
            response = handle_list_jobs(event, origin)
        else:
            response = create_error_response(404, 'Endpoint not found', origin=origin)
        
        # Log response
        duration_ms = (time.time() - start_time) * 1000
        response_size = len(json.dumps(response))
        log_response(response['statusCode'], response_size, duration_ms)
        
        return response
    
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        print(f"Orchestrator error: {str(e)}")
        response = create_error_response(500, f'Orchestrator service error: {str(e)}', origin=headers.get('origin'))
        log_response(500, len(json.dumps(response)), duration_ms)
        return response


def handle_upload_request(event, origin=None):
    """Generate pre-signed S3 URL for file upload"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        # Validate input
        validator = InputValidator()
        validator.require('fileName', body.get('fileName'))
        validator.require('fileType', body.get('fileType'))
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        file_name = body['fileName']
        file_type = body['fileType']
        
        # Validate file type
        allowed_types = ['text/csv', 'application/csv', 'text/plain']
        if file_type not in allowed_types:
            return create_error_response(400, f'Unsupported file type: {file_type}. Allowed: {allowed_types}', origin=origin)
        
        # Generate job ID and S3 key
        job_id = str(uuid.uuid4())
        s3_key = f"uploads/{job_id}/{file_name}"
        
        # Generate pre-signed URL for upload
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': UPLOADS_BUCKET,
                'Key': s3_key,
                'ContentType': file_type
            },
            ExpiresIn=3600  # 1 hour
        )
        
        return create_response(200, {
            'jobId': job_id,
            'uploadUrl': upload_url,
            's3Key': s3_key,
            'expiresIn': 3600
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Upload URL generation failed: {str(e)}', origin=origin)


def handle_create_migration_job(event, origin=None):
    """Create migration job and start Step Function"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        job_id = body.get('jobId') or str(uuid.uuid4())
        input_file_key = body.get('inputFileKey', '')
        job_type = body.get('jobType', JobType.MIGRATION)
        filters = body.get('filters', {})
        
        # Validate input
        validator = InputValidator()
        validator.require('inputFileKey', input_file_key)
        validator.validate_enum('jobType', job_type, [JobType.MIGRATION, JobType.BULK_DELETE], required=True)
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Create job record
        job_record = create_job_record(job_id, job_type, 'CLOUD', 'CLOUD', filters, input_file_key=input_file_key)
        
        # Start Migration Step Function
        execution_response = sfn_client.start_execution(
            stateMachineArn=MIGRATION_WORKFLOW_ARN,
            name=f'migration-{job_id}',
            input=json.dumps({
                'jobId': job_id,
                'inputFileKey': input_file_key,
                'jobType': job_type,
                'filters': filters
            })
        )
        
        # Update job with execution ARN
        job_record['execution_arn'] = execution_response['executionArn']
        job_record['job_status'] = JobStatus.QUEUED
        
        # Save job record
        jobs_table.put_item(Item=job_record)
        
        return create_response(201, {
            'jobId': job_id,
            'executionArn': execution_response['executionArn'],
            'status': JobStatus.QUEUED,
            'message': 'Migration job created and queued'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Migration job creation failed: {str(e)}', origin=origin)


def handle_create_audit_job(event, origin=None):
    """Create audit job and start Step Function"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        job_id = str(uuid.uuid4())
        job_type = JobType.AUDIT
        audit_type = body.get('auditType', 'CONSISTENCY_CHECK')
        source = body.get('source', 'dual')
        filters = body.get('filters', {})
        
        # Validate audit type
        allowed_audit_types = ['CONSISTENCY_CHECK', 'DATA_VALIDATION', 'FULL_AUDIT']
        validator = InputValidator()
        validator.validate_enum('auditType', audit_type, allowed_audit_types, required=True)
        validator.validate_enum('source', source, ['cloud', 'legacy', 'dual'], required=True)
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Create job record
        job_record = create_job_record(job_id, job_type, source.upper(), source.upper(), filters)
        
        # Start Audit Step Function
        execution_response = sfn_client.start_execution(
            stateMachineArn=AUDIT_WORKFLOW_ARN,
            name=f'audit-{job_id}',
            input=json.dumps({
                'jobId': job_id,
                'auditType': audit_type,
                'source': source,
                'filters': filters
            })
        )
        
        # Update job with execution ARN
        job_record['execution_arn'] = execution_response['executionArn']
        job_record['job_status'] = JobStatus.QUEUED
        
        # Save job record
        jobs_table.put_item(Item=job_record)
        
        return create_response(201, {
            'jobId': job_id,
            'executionArn': execution_response['executionArn'],
            'auditType': audit_type,
            'status': JobStatus.QUEUED,
            'message': 'Audit job created and queued'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Audit job creation failed: {str(e)}', origin=origin)


def handle_create_export_job(event, origin=None):
    """Create export job and start Step Function"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        job_id = str(uuid.uuid4())
        job_type = JobType.EXPORT
        export_scope = body.get('exportScope', 'BOTH_SYSTEMS')
        format_type = body.get('format', 'CSV')
        filters = body.get('filters', {})
        
        # Validate input
        allowed_scopes = ['CLOUD_ONLY', 'LEGACY_ONLY', 'BOTH_SYSTEMS', 'COMPARISON']
        allowed_formats = ['CSV', 'JSON', 'XML']
        
        validator = InputValidator()
        validator.validate_enum('exportScope', export_scope, allowed_scopes, required=True)
        validator.validate_enum('format', format_type, allowed_formats, required=True)
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Create job record
        job_record = create_job_record(job_id, job_type, 'DUAL', 'DUAL', filters)
        
        # Start Export Step Function
        execution_response = sfn_client.start_execution(
            stateMachineArn=EXPORT_WORKFLOW_ARN,
            name=f'export-{job_id}',
            input=json.dumps({
                'jobId': job_id,
                'exportScope': export_scope,
                'format': format_type,
                'filters': filters
            })
        )
        
        # Update job with execution ARN
        job_record['execution_arn'] = execution_response['executionArn']
        job_record['job_status'] = JobStatus.QUEUED
        
        # Save job record
        jobs_table.put_item(Item=job_record)
        
        return create_response(201, {
            'jobId': job_id,
            'executionArn': execution_response['executionArn'],
            'exportScope': export_scope,
            'format': format_type,
            'status': JobStatus.QUEUED,
            'message': 'Export job created and queued'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Export job creation failed: {str(e)}', origin=origin)


def handle_get_job_status(event, origin=None):
    """Get job status using execution ARN"""
    try:
        job_id = event.get('pathParameters', {}).get('id')
        if not job_id:
            return create_error_response(400, 'Job ID is required', origin=origin)
        
        # Get job record from DynamoDB
        try:
            response = jobs_table.get_item(Key={'job_id': job_id})
            job_record = response.get('Item')
            
            if not job_record:
                return create_error_response(404, f'Job not found: {job_id}', origin=origin)
        
        except Exception as e:
            return create_error_response(500, f'Failed to retrieve job record: {str(e)}', origin=origin)
        
        # Get Step Functions execution status
        execution_arn = job_record.get('execution_arn')
        if execution_arn and sfn_client:
            try:
                execution_response = sfn_client.describe_execution(executionArn=execution_arn)
                
                # Map Step Functions status to job status
                sf_status = execution_response['status']
                if sf_status == 'RUNNING':
                    job_status = JobStatus.RUNNING
                elif sf_status == 'SUCCEEDED':
                    job_status = JobStatus.COMPLETED
                elif sf_status == 'FAILED':
                    job_status = JobStatus.FAILED
                elif sf_status == 'ABORTED':
                    job_status = JobStatus.CANCELLED
                else:
                    job_status = job_record.get('job_status', JobStatus.PENDING)
                
                # Update job record with current status if changed
                if job_status != job_record.get('job_status'):
                    jobs_table.update_item(
                        Key={'job_id': job_id},
                        UpdateExpression='SET job_status = :status, updated_at = :timestamp',
                        ExpressionAttributeValues={
                            ':status': job_status,
                            ':timestamp': datetime.utcnow().isoformat()
                        }
                    )
                    job_record['job_status'] = job_status
                
            except Exception as e:
                print(f"Failed to get Step Functions status: {e}")
                job_status = job_record.get('job_status', JobStatus.PENDING)
        else:
            job_status = job_record.get('job_status', JobStatus.PENDING)
        
        # Format response
        status_response = {
            'jobId': job_id,
            'jobType': job_record.get('job_type'),
            'status': job_status,
            'sourceSystem': job_record.get('source_system'),
            'targetSystem': job_record.get('target_system'),
            'processedRecords': job_record.get('processed_records', 0),
            'successRecords': job_record.get('success_records', 0),
            'failedRecords': job_record.get('failed_records', 0),
            'createdAt': job_record.get('created_at'),
            'startedAt': job_record.get('started_at'),
            'finishedAt': job_record.get('finished_at'),
            'errorMessage': job_record.get('error_message'),
            'outputFileKey': job_record.get('output_file_key')
        }
        
        # Add download URL if output file exists
        if job_record.get('output_file_key'):
            try:
                download_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': UPLOADS_BUCKET,
                        'Key': job_record['output_file_key']
                    },
                    ExpiresIn=3600  # 1 hour
                )
                status_response['downloadUrl'] = download_url
            except Exception as e:
                print(f"Failed to generate download URL: {e}")
        
        return create_response(200, status_response, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Job status retrieval failed: {str(e)}', origin=origin)


def handle_cancel_job(event, origin=None):
    """Cancel running job by stopping Step Function execution"""
    try:
        job_id = event.get('pathParameters', {}).get('id')
        if not job_id:
            return create_error_response(400, 'Job ID is required', origin=origin)
        
        # Get job record
        response = jobs_table.get_item(Key={'job_id': job_id})
        job_record = response.get('Item')
        
        if not job_record:
            return create_error_response(404, f'Job not found: {job_id}', origin=origin)
        
        execution_arn = job_record.get('execution_arn')
        if not execution_arn:
            return create_error_response(400, 'Job has no execution ARN - cannot cancel', origin=origin)
        
        # Stop Step Functions execution
        try:
            sfn_client.stop_execution(
                executionArn=execution_arn,
                error='UserCancellation',
                cause='Job cancelled by user request'
            )
            
            # Update job status
            jobs_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression='SET job_status = :status, finished_at = :timestamp, updated_at = :timestamp',
                ExpressionAttributeValues={
                    ':status': JobStatus.CANCELLED,
                    ':timestamp': datetime.utcnow().isoformat()
                }
            )
            
            return create_response(200, {
                'jobId': job_id,
                'status': JobStatus.CANCELLED,
                'message': 'Job cancelled successfully'
            }, origin=origin)
        
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ExecutionDoesNotExist':
                return create_error_response(404, 'Job execution not found', origin=origin)
            elif error_code == 'InvalidParameterValue':
                return create_error_response(400, 'Job cannot be cancelled (already completed or failed)', origin=origin)
            else:
                raise e
    
    except Exception as e:
        return create_error_response(500, f'Job cancellation failed: {str(e)}', origin=origin)


def handle_list_jobs(event, origin=None):
    """List jobs with pagination and filtering"""
    try:
        query_params = event.get('queryStringParameters') or {}
        
        # Parse parameters
        job_type = query_params.get('jobType', '').strip()
        status = query_params.get('status', '').strip()
        limit = min(int(query_params.get('limit', 25)), 100)
        last_key_str = query_params.get('lastKey', '').strip()
        
        # Build scan parameters
        scan_kwargs = {'Limit': limit}
        
        # Apply filters
        filter_expressions = []
        expression_values = {}
        
        if job_type:
            filter_expressions.append('job_type = :job_type')
            expression_values[':job_type'] = job_type
        
        if status:
            filter_expressions.append('job_status = :status')
            expression_values[':status'] = status
        
        if filter_expressions:
            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
            scan_kwargs['ExpressionAttributeValues'] = expression_values
        
        # Handle pagination
        if last_key_str:
            try:
                last_key = json.loads(last_key_str)
                scan_kwargs['ExclusiveStartKey'] = last_key
            except Exception as e:
                print(f"Invalid lastKey parameter: {e}")
        
        # Scan jobs table
        response = jobs_table.scan(**scan_kwargs)
        jobs = response.get('Items', [])
        
        # Format jobs for response (remove sensitive data)
        formatted_jobs = []
        for job in jobs:
            formatted_job = {
                'jobId': job['job_id'],
                'jobType': job['job_type'],
                'status': job['job_status'],
                'sourceSystem': job.get('source_system'),
                'processedRecords': job.get('processed_records', 0),
                'successRecords': job.get('success_records', 0),
                'failedRecords': job.get('failed_records', 0),
                'createdAt': job.get('created_at'),
                'finishedAt': job.get('finished_at'),
                'hasOutput': bool(job.get('output_file_key'))
            }
            formatted_jobs.append(formatted_job)
        
        # Sort by creation date (newest first)
        formatted_jobs.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        
        return create_response(200, {
            'jobs': formatted_jobs,
            'pagination': {
                'count': len(formatted_jobs),
                'hasMore': bool(response.get('LastEvaluatedKey')),
                'lastKey': json.dumps(response.get('LastEvaluatedKey')) if response.get('LastEvaluatedKey') else None,
                'limit': limit
            }
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Job listing failed: {str(e)}', origin=origin)


def create_job_record(job_id, job_type, source_system, target_system, filters, input_file_key=None):
    """Create job record for DynamoDB"""
    now = datetime.utcnow().isoformat()
    
    return {
        'job_id': job_id,
        'job_type': job_type,
        'job_status': JobStatus.PENDING,
        'source_system': source_system,
        'target_system': target_system,
        'input_file_key': input_file_key,
        'filters': filters,
        'processed_records': 0,
        'success_records': 0,
        'failed_records': 0,
        'created_at': now,
        'updated_at': now
    }