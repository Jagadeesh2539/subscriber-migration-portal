from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import os
import boto3
import uuid
from datetime import datetime

mig_bp = Blueprint('migration', __name__)

# Get table/bucket names from Lambda environment variables
MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
MIGRATION_UPLOAD_BUCKET_NAME = os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME')

dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
s3_client = boto3.client('s3')

@mig_bp.route('/bulk', methods=['POST', 'OPTIONS'])
@login_required()
def start_bulk_migration():
    """
    Starts a new migration job: creates a job entry and returns an S3 pre-signed URL
    for the client to upload the CSV file directly.
    """
    user = request.environ['user']
    data = request.json
    is_simulate_mode = data.get('isSimulateMode', False)
    
    try:
        migration_id = str(uuid.uuid4())
        # Define where the upload will go in S3
        upload_key = f"uploads/{migration_id}.csv" 
        
        # Generate the secure, time-limited URL for the PUT request
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': upload_key,
                'ContentType': 'text/csv',
                'Metadata': { # Pass job settings via metadata
                    'migrationid': migration_id,
                    'issimulatemode': str(is_simulate_mode).lower(),
                    'userid': user['sub']
                }
            },
            ExpiresIn=3600 # URL valid for 1 hour
        )
        
        # Create the initial tracking entry in DynamoDB
        jobs_table.put_item(
            Item={
                'migrationId': migration_id,
                'status': 'PENDING_UPLOAD', # Initial status
                'startedBy': user['sub'],
                'startedAt': datetime.utcnow().isoformat(),
                'isSimulateMode': is_simulate_mode
            }
        )
        
        log_audit(user['sub'], 'START_MIGRATION', {'migrationId': migration_id, 'simulate': is_simulate_mode}, 'SUCCESS')
        # Return the ID and URL to the frontend
        return jsonify(migrationId=migration_id, uploadUrl=upload_url), 200
        
    except Exception as e:
        log_audit(user['sub'], 'START_MIGRATION', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error initiating migration: {str(e)}'), 500

@mig_bp.route('/status/<migration_id>', methods=['GET'])
@login_required()
def get_migration_status(migration_id):
    """Fetches the current status of a migration job from DynamoDB."""
    try:
        response = jobs_table.get_item(Key={'migrationId': migration_id})
        status = response.get('Item')
        if not status:
            return jsonify(msg='Job not found'), 404
        return jsonify(status)
    except Exception as e:
        return jsonify(msg=f'Error getting job status: {str(e)}'), 500

@mig_bp.route('/report/<migration_id>', methods=['GET'])
@login_required()
def get_migration_report(migration_id):
    """Generates a pre-signed URL to download the migration report CSV."""
    try:
        response = jobs_table.get_item(Key={'migrationId': migration_id})
        job = response.get('Item')
        if not job:
            return jsonify(msg='Job not found'), 404
        
        report_key = job.get('reportS3Key')
        if not report_key:
            # Check if the job failed before report generation
            if job.get('status') == 'FAILED':
                 return jsonify(msg=f"Job failed: {job.get('failureReason', 'Unknown error')}"), 404
            return jsonify(msg='Report not yet available or job is still processing'), 404
            
        # Generate secure URL for downloading the report
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME, # Report is in the same bucket
                'Key': report_key,
                'ResponseContentDisposition': f'attachment; filename="report-{migration_id}.csv"' # Suggest filename
            },
            ExpiresIn=3600 # URL valid for 1 hour
        )
        
        return jsonify(downloadUrl=download_url), 200
        
    except Exception as e:
        return jsonify(msg=f'Error generating report URL: {str(e)}'), 500
