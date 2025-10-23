from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import os
import boto3
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Attr

mig_bp = Blueprint('migration', __name__)

# Environment variables with fallback and validation
MIGRATION_JOBS_TABLE_NAME = os.getenv('MIGRATION_JOBS_TABLE_NAME')
MIGRATION_UPLOAD_BUCKET_NAME = os.getenv('MIGRATION_UPLOAD_BUCKET_NAME')

if not MIGRATION_JOBS_TABLE_NAME or not MIGRATION_UPLOAD_BUCKET_NAME:
    raise ValueError("MIGRATION_JOBS_TABLE_NAME or MIGRATION_UPLOAD_BUCKET_NAME environment variables are not set")

dynamodb = boto3.resource('dynamodb')

try:
    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
except Exception as e:
    print(f"Error creating DynamoDB table reference: {e}")
    jobs_table = None

s3_client = boto3.client('s3')

@mig_bp.route('/bulk', methods=['POST', 'OPTIONS'])
@login_required()
def start_bulk_migration():
    user = request.environ['user']
    data = request.json
    is_simulate_mode = data.get('isSimulateMode', False)

    try:
        migration_id = str(uuid.uuid4())
        upload_key = f"uploads/{migration_id}.csv"

        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': upload_key,
                'ContentType': 'text/csv',
                'Metadata': {
                    'jobid': migration_id,
                    'issimulatemode': str(is_simulate_mode).lower(),
                    'userid': user['sub']
                }
            },
            ExpiresIn=3600
        )

        jobs_table.put_item(
            Item={
                'JobId': migration_id,
                'status': 'PENDING_UPLOAD',
                'startedBy': user['sub'],
                'startedAt': datetime.utcnow().isoformat(),
                'isSimulateMode': is_simulate_mode
            }
        )

        log_audit(user['sub'], 'START_MIGRATION', {'migrationId': migration_id, 'simulate': is_simulate_mode}, 'SUCCESS')

        return jsonify(migrationId=migration_id, uploadUrl=upload_url), 200

    except Exception as e:
        log_audit(user['sub'], 'START_MIGRATION', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error initiating migration: {str(e)}'), 500

@mig_bp.route('/status/<migration_id>', methods=['GET'])
@login_required()
def get_migration_status(migration_id):
    try:
        response = jobs_table.get_item(Key={'JobId': migration_id})
        status = response.get('Item')
        if not status:
            return jsonify(msg='Job not found'), 404
        
        # Ensure JobId is in response for frontend
        status['JobId'] = migration_id
        
        return jsonify(status)
    except Exception as e:  # ← FIXED: Added missing except block
        return jsonify(msg=f'Error getting job status: {str(e)}'), 500

@mig_bp.route('/report/<migration_id>', methods=['GET'])
@login_required()
def get_migration_report(migration_id):
    try:
        response = jobs_table.get_item(Key={'JobId': migration_id})
        job = response.get('Item')
        if not job:
            return jsonify(msg='Job not found'), 404

        report_key = job.get('reportS3Key')
        if not report_key:
            if job.get('status') == 'FAILED':
                 return jsonify(msg=f"Job failed: {job.get('failureReason', 'Unknown error')}"), 404
            return jsonify(msg='Report not yet available or job is still processing'), 404

        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': report_key,
                'ResponseContentDisposition': f'attachment; filename="report-{migration_id}.csv"'
            },
            ExpiresIn=3600
        )
        
        return jsonify(downloadUrl=download_url), 200

    except Exception as e:
        return jsonify(msg=f'Error generating report URL: {str(e)}'), 500

@mig_bp.route('/jobs', methods=['GET'])
@login_required()
def get_migration_jobs():
    """Get migration jobs for the current user"""
    user = request.environ['user']
    try:
        limit = int(request.args.get('limit', 20))
        
        response = jobs_table.scan(
            FilterExpression=Attr('startedBy').eq(user['sub'])
        )
        jobs = response.get('Items', [])
        
        # Sort by startedAt descending
        jobs.sort(key=lambda x: x.get('startedAt', ''), reverse=True)
        jobs = jobs[:limit]
        
        # Ensure JobId is included
        for job in jobs:
            if 'JobId' not in job:
                job['JobId'] = job.get('migrationId', job.get('JobId', 'unknown'))
        
        return jsonify({'jobs': jobs})
        
    except Exception as e:
        return jsonify(msg=f'Error getting migration jobs: {str(e)}'), 500
