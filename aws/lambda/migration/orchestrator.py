#!/usr/bin/env python3
import json
import os
import boto3
from botocoreexceptions import ClientError
from datetime import datetime
import uuid
import time

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, InputValidator,
    handle_cors_preflight, log_request, log_response,
    JobType, JobStatus
)
from workflow_resolver import get_workflow_arns

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    sfn_client = boto3.client('stepfunctions')
    cfn_client = boto3.client('cloudformation')

    # Environment variables
    MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE')
    UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')
    AWS_STACK_NAME = os.environ.get('AWS_STACK_NAME', os.environ.get('STACK_NAME', ''))

    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE) if MIGRATION_JOBS_TABLE else None

except Exception as e:
    print(f"AWS services initialization error: {e}")
    dynamodb = None
    s3_client = None
    sfn_client = None
    cfn_client = None
    jobs_table = None


# Resolve Step Functions ARNs at runtime
def resolve_workflows():
    arns = get_workflow_arns()
    return arns['migration'], arns['audit'], arns['export']


def lambda_handler(event, context):
    """Main orchestrator for Step Functions job management"""
    start_time = time.time()

    try:
        log_request(event, context)

        method = event.get('httpMethod', 'GET')
        path = event.get('resource', event.get('path', ''))
        headers = event.get('headers', {})
        origin = headers.get('origin')

        cors_response = handle_cors_preflight(event)
        if cors_response:
            return cors_response

        # Route
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


def handle_create_migration_job(event, origin=None):
    try:
        migration_arn, _, _ = resolve_workflows()
        body = json.loads(event.get('body', '{}'))

        job_id = body.get('jobId') or str(uuid.uuid4())
        input_file_key = body.get('inputFileKey', '')
        job_type = body.get('jobType', JobType.MIGRATION)
        filters = body.get('filters', {})

        validator = InputValidator()
        validator.require('inputFileKey', input_file_key)
        validator.validate_enum('jobType', job_type, [JobType.MIGRATION, JobType.BULK_DELETE], required=True)
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)

        job_record = create_job_record(job_id, job_type, 'CLOUD', 'CLOUD', filters, input_file_key=input_file_key)

        exec_resp = sfn_client.start_execution(
            stateMachineArn=migration_arn,
            name=f'migration-{job_id}',
            input=json.dumps({'jobId': job_id,'inputFileKey': input_file_key,'jobType': job_type,'filters': filters})
        )

        job_record['execution_arn'] = exec_resp['executionArn']
        job_record['job_status'] = JobStatus.QUEUED
        jobs_table.put_item(Item=job_record)

        return create_response(201, {'jobId': job_id,'executionArn': exec_resp['executionArn'],'status': JobStatus.QUEUED,'message': 'Migration job created and queued'}, origin=origin)
    except Exception as e:
        return create_error_response(500, f'Migration job creation failed: {str(e)}', origin=origin)


def handle_create_audit_job(event, origin=None):
    try:
        _, audit_arn, _ = resolve_workflows()
        body = json.loads(event.get('body', '{}'))

        job_id = str(uuid.uuid4())
        audit_type = body.get('auditType', 'CONSISTENCY_CHECK')
        source = body.get('source', 'dual')
        filters = body.get('filters', {})

        validator = InputValidator()
        validator.validate_enum('auditType', audit_type, ['CONSISTENCY_CHECK', 'DATA_VALIDATION', 'FULL_AUDIT'], required=True)
        validator.validate_enum('source', source, ['cloud', 'legacy', 'dual'], required=True)
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)

        job_record = create_job_record(job_id, JobType.AUDIT, source.upper(), source.upper(), filters)

        exec_resp = sfn_client.start_execution(
            stateMachineArn=audit_arn,
            name=f'audit-{job_id}',
            input=json.dumps({'jobId': job_id,'auditType': audit_type,'source': source,'filters': filters})
        )
        job_record['execution_arn'] = exec_resp['executionArn']
        job_record['job_status'] = JobStatus.QUEUED
        jobs_table.put_item(Item=job_record)

        return create_response(201, {'jobId': job_id,'executionArn': exec_resp['executionArn'],'auditType': audit_type,'status': JobStatus.QUEUED,'message': 'Audit job created and queued'}, origin=origin)
    except Exception as e:
        return create_error_response(500, f'Audit job creation failed: {str(e)}', origin=origin)


def handle_create_export_job(event, origin=None):
    try:
        _, _, export_arn = resolve_workflows()
        body = json.loads(event.get('body', '{}'))

        job_id = str(uuid.uuid4())
        export_scope = body.get('exportScope', 'BOTH_SYSTEMS')
        format_type = body.get('format', 'CSV')
        filters = body.get('filters', {})

        validator = InputValidator()
        validator.validate_enum('exportScope', export_scope, ['CLOUD_ONLY','LEGACY_ONLY','BOTH_SYSTEMS','COMPARISON'], required=True)
        validator.validate_enum('format', format_type, ['CSV','JSON','XML'], required=True)
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)

        job_record = create_job_record(job_id, JobType.EXPORT, 'DUAL', 'DUAL', filters)

        exec_resp = sfn_client.start_execution(
            stateMachineArn=export_arn,
            name=f'export-{job_id}',
            input=json.dumps({'jobId': job_id,'exportScope': export_scope,'format': format_type,'filters': filters})
        )
        job_record['execution_arn'] = exec_resp['executionArn']
        job_record['job_status'] = JobStatus.QUEUED
        jobs_table.put_item(Item=job_record)

        return create_response(201, {'jobId': job_id,'executionArn': exec_resp['executionArn'],'exportScope': export_scope,'format': format_type,'status': JobStatus.QUEUED,'message': 'Export job created and queued'}, origin=origin)
    except Exception as e:
        return create_error_response(500, f'Export job creation failed: {str(e)}', origin=origin)
