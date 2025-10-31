#!/usr/bin/env python3
import json
import os
from datetime import datetime
import uuid
import boto3
from botocore.exceptions import ClientError

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response, InputValidator

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    sfn_client = boto3.client('stepfunctions')
    
    # Environment variables
    MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE')
    UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')
    
    # Step Function ARNs
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
    """Main orchestrator for all job-related operations"""
    method = event.get('httpMethod', 'GET')
    path = event.get('resource', '')
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    headers = event.get('headers') or {}
    origin = headers.get('origin')
    
    try:
        # Route to appropriate handler based on path and method
        if '/migration/upload' in path and method == 'POST':
            return handle_upload_request(event, origin)
        elif '/migration/jobs' in path and method == 'POST':
            return handle_create_migration_job(event, origin)
        elif '/audit/jobs' in path and method == 'POST':
            return handle_create_audit_job(event, origin)
        elif '/export/jobs' in path and method == 'POST':
            return handle_create_export_job(event, origin)
        elif '/jobs/' in path and method == 'GET':
            job_id = path_params.get('id')
            return handle_get_job_status(job_id, origin)
        elif '/jobs/' in path and '/cancel' in path and method == 'POST':
            job_id = path_params.get('id')
            return handle_cancel_job(job_id, origin)
        elif '/jobs' in path and method == 'GET':
            return handle_list_jobs(query_params, origin)
        else:
            return create_error_response(404, 'Endpoint not found', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Internal server error: {str(e)}', origin=origin)


def handle_upload_request(event, origin=None):
    """Generate pre-signed S3 URL for file upload"""
    if not s3_client or not UPLOADS_BUCKET:
        return create_error_response(503, 'Upload service not available', origin=origin)
    
    try:
        body = json.loads(event.get('body', '{}'))
        
        # Validate request
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
            return create_error_response(400, f'File type {file_type} not allowed. Allowed: {allowed_types}', origin=origin)
        
        # Generate unique key
        job_id = str(uuid.uuid4())
        file_key = f"uploads/{job_id}/{file_name}"
        
        # Generate pre-signed URL
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': UPLOADS_BUCKET,
                'Key': file_key,
                'ContentType': file_type
            },
            ExpiresIn=3600  # 1 hour
        )
        
        return create_response(200, {
            'uploadUrl': presigned_url,
            'fileKey': file_key,
            'jobId': job_id,
            'expiresIn': 3600,
            'message': 'Upload URL generated successfully'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to generate upload URL: {str(e)}', origin=origin)


def handle_create_migration_job(event, origin=None):
    """Create and start migration job using Step Functions"""
    if not jobs_table or not sfn_client or not MIGRATION_WORKFLOW_ARN:
        return create_error_response(503, 'Migration service not available', origin=origin)
    
    try:
        body = json.loads(event.get('body', '{}'))
        
        # Validate request
        validator = InputValidator()
        validator.require('jobType', body.get('jobType'))
        validator.require('inputFileKey', body.get('inputFileKey'))
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        # Create job record
        job_record = {
            'job_id': job_id,
            'job_type': body['jobType'],
            'job_status': 'PENDING',
            'input_file_key': body['inputFileKey'],
            'filters': body.get('filters', {}),
            'created_at': now,
            'updated_at': now,
            'created_by': body.get('userId', 'anonymous')
        }
        
        jobs_table.put_item(Item=job_record)
        
        # Start Step Function execution
        execution_input = {
            'jobId': job_id,
            'jobType': body['jobType'],
            'inputFileKey': body['inputFileKey'],
            'filters': body.get('filters', {})
        }
        
        response = sfn_client.start_execution(
            stateMachineArn=MIGRATION_WORKFLOW_ARN,
            name=f"migration-{job_id}",
            input=json.dumps(execution_input)
        )
        
        # Update job with execution ARN
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET execution_arn = :arn, job_status = :status',
            ExpressionAttributeValues={
                ':arn': response['executionArn'],
                ':status': 'QUEUED'
            }
        )
        
        return create_response(201, {
            'jobId': job_id,
            'status': 'QUEUED',
            'executionArn': response['executionArn'],
            'message': 'Migration job created and started successfully'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to create migration job: {str(e)}', origin=origin)


def handle_create_audit_job(event, origin=None):
    """Create and start audit job using Step Functions"""
    if not jobs_table or not sfn_client or not AUDIT_WORKFLOW_ARN:
        return create_error_response(503, 'Audit service not available', origin=origin)
    
    try:
        body = json.loads(event.get('body', '{}'))
        
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        # Create job record
        job_record = {
            'job_id': job_id,
            'job_type': 'AUDIT',
            'job_status': 'PENDING',
            'audit_type': body.get('auditType', 'CONSISTENCY_CHECK'),
            'filters': body.get('filters', {}),
            'created_at': now,
            'updated_at': now,
            'created_by': body.get('userId', 'anonymous')
        }
        
        jobs_table.put_item(Item=job_record)
        
        # Start Step Function execution
        execution_input = {
            'jobId': job_id,
            'auditType': body.get('auditType', 'CONSISTENCY_CHECK'),
            'filters': body.get('filters', {})
        }
        
        response = sfn_client.start_execution(
            stateMachineArn=AUDIT_WORKFLOW_ARN,
            name=f"audit-{job_id}",
            input=json.dumps(execution_input)
        )
        
        # Update job with execution ARN
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET execution_arn = :arn, job_status = :status',
            ExpressionAttributeValues={
                ':arn': response['executionArn'],
                ':status': 'QUEUED'
            }
        )
        
        return create_response(201, {
            'jobId': job_id,
            'status': 'QUEUED',
            'executionArn': response['executionArn'],
            'message': 'Audit job created and started successfully'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to create audit job: {str(e)}', origin=origin)


def handle_create_export_job(event, origin=None):
    """Create and start export job using Step Functions"""
    if not jobs_table or not sfn_client or not EXPORT_WORKFLOW_ARN:
        return create_error_response(503, 'Export service not available', origin=origin)
    
    try:
        body = json.loads(event.get('body', '{}'))
        
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        # Create job record
        job_record = {
            'job_id': job_id,
            'job_type': 'EXPORT',
            'job_status': 'PENDING',
            'export_scope': body.get('exportScope', 'BOTH_SYSTEMS'),
            'format': body.get('format', 'CSV'),
            'filters': body.get('filters', {}),
            'mask_pii': body.get('maskPii', True),
            'created_at': now,
            'updated_at': now,
            'created_by': body.get('userId', 'anonymous')
        }
        
        jobs_table.put_item(Item=job_record)
        
        # Start Step Function execution
        execution_input = {
            'jobId': job_id,
            'exportScope': body.get('exportScope', 'BOTH_SYSTEMS'),
            'format': body.get('format', 'CSV'),
            'filters': body.get('filters', {}),
            'maskPii': body.get('maskPii', True)
        }
        
        response = sfn_client.start_execution(
            stateMachineArn=EXPORT_WORKFLOW_ARN,
            name=f"export-{job_id}",
            input=json.dumps(execution_input)
        )
        
        # Update job with execution ARN
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET execution_arn = :arn, job_status = :status',
            ExpressionAttributeValues={
                ':arn': response['executionArn'],
                ':status': 'QUEUED'
            }
        )
        
        return create_response(201, {
            'jobId': job_id,
            'status': 'QUEUED',
            'executionArn': response['executionArn'],
            'message': 'Export job created and started successfully'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to create export job: {str(e)}', origin=origin)


def handle_get_job_status(job_id, origin=None):
    """Get job status from DynamoDB and Step Functions"""
    if not jobs_table or not sfn_client:
        return create_error_response(503, 'Job tracking service not available', origin=origin)
    
    try:
        # Get job from DynamoDB
        response = jobs_table.get_item(Key={'job_id': job_id})
        job = response.get('Item')
        
        if not job:
            return create_error_response(404, f'Job {job_id} not found', origin=origin)
        
        # Get execution status from Step Functions if available
        if job.get('execution_arn'):
            try:
                sf_response = sfn_client.describe_execution(
                    executionArn=job['execution_arn']
                )
                
                # Update job status based on Step Function status
                sf_status = sf_response['status']
                if sf_status == 'SUCCEEDED':
                    job['job_status'] = 'COMPLETED'
                elif sf_status == 'FAILED':
                    job['job_status'] = 'FAILED'
                elif sf_status == 'RUNNING':
                    job['job_status'] = 'RUNNING'
                elif sf_status == 'ABORTED':
                    job['job_status'] = 'CANCELLED'
                
                job['execution_status'] = sf_status
                job['execution_started_at'] = sf_response.get('startDate', '').isoformat() if sf_response.get('startDate') else None
                job['execution_stopped_at'] = sf_response.get('stopDate', '').isoformat() if sf_response.get('stopDate') else None
                
            except ClientError as e:
                # Step Function execution might not exist or be accessible
                job['execution_error'] = str(e)
        
        # Format response
        return create_response(200, {
            'job': job,
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to get job status: {str(e)}', origin=origin)


def handle_cancel_job(job_id, origin=None):
    """Cancel running job by stopping Step Function execution"""
    if not jobs_table or not sfn_client:
        return create_error_response(503, 'Job management service not available', origin=origin)
    
    try:
        # Get job from DynamoDB
        response = jobs_table.get_item(Key={'job_id': job_id})
        job = response.get('Item')
        
        if not job:
            return create_error_response(404, f'Job {job_id} not found', origin=origin)
        
        if job.get('job_status') in ['COMPLETED', 'FAILED', 'CANCELLED']:
            return create_error_response(400, f'Job {job_id} is already finished and cannot be cancelled', origin=origin)
        
        # Stop Step Function execution
        if job.get('execution_arn'):
            try:
                sfn_client.stop_execution(
                    executionArn=job['execution_arn'],
                    cause='User requested cancellation'
                )
            except ClientError as e:
                if 'ExecutionDoesNotExist' not in str(e):
                    raise e
        
        # Update job status
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET job_status = :status, updated_at = :timestamp, cancelled_at = :timestamp',
            ExpressionAttributeValues={
                ':status': 'CANCELLED',
                ':timestamp': datetime.utcnow().isoformat()
            }
        )
        
        return create_response(200, {
            'jobId': job_id,
            'status': 'CANCELLED',
            'message': 'Job cancelled successfully'
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to cancel job: {str(e)}', origin=origin)


def handle_list_jobs(query_params, origin=None):
    """List jobs with filtering and pagination"""
    if not jobs_table:
        return create_error_response(503, 'Job listing service not available', origin=origin)
    
    try:
        # Parse query parameters
        job_type = query_params.get('jobType')
        status = query_params.get('status')
        limit = min(int(query_params.get('limit', 25)), 100)
        last_key = query_params.get('lastKey')
        
        # Build scan parameters
        scan_kwargs = {
            'Limit': limit,
            'ScanIndexForward': False  # Sort by newest first
        }
        
        if last_key:
            try:
                scan_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            except:
                pass
        
        # Add filters
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
        
        # Execute scan
        response = jobs_table.scan(**scan_kwargs)
        
        jobs = response.get('Items', [])
        last_evaluated_key = response.get('LastEvaluatedKey')
        
        return create_response(200, {
            'jobs': jobs,
            'pagination': {
                'count': len(jobs),
                'hasMore': bool(last_evaluated_key),
                'lastKey': json.dumps(last_evaluated_key) if last_evaluated_key else None
            },
            'filters': {
                'jobType': job_type,
                'status': status
            },
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to list jobs: {str(e)}', origin=origin)