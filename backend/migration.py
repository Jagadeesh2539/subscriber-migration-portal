from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import os
import boto3
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Attr, Key
import json

mig_bp = Blueprint('migration', __name__)

# Environment variables with fallback and validation
MIGRATION_JOBS_TABLE_NAME = os.getenv('MIGRATION_JOBS_TABLE_NAME')
MIGRATION_UPLOAD_BUCKET_NAME = os.getenv('MIGRATION_UPLOAD_BUCKET_NAME')
SUBSCRIBER_TABLE_NAME = os.getenv('SUBSCRIBER_TABLE_NAME')

if not MIGRATION_JOBS_TABLE_NAME or not MIGRATION_UPLOAD_BUCKET_NAME:
    raise ValueError("MIGRATION_JOBS_TABLE_NAME or MIGRATION_UPLOAD_BUCKET_NAME environment variables are not set")

dynamodb = boto3.resource('dynamodb')

try:
    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
    subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME) if SUBSCRIBER_TABLE_NAME else None
except Exception as e:
    print(f"Error creating DynamoDB table reference: {e}")
    jobs_table = None
    subscriber_table = None

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
                    'userid': user['sub'],
                    'jobtype': 'migration'
                }
            },
            ExpiresIn=3600
        )

        jobs_table.put_item(
            Item={
                'JobId': migration_id,
                'jobType': 'MIGRATION',
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

@mig_bp.route('/bulk-delete', methods=['POST', 'OPTIONS'])
@login_required()
def start_bulk_deletion():
    """Start bulk deletion of subscribers from cloud (DynamoDB) only"""
    user = request.environ['user']
    data = request.json
    is_simulate_mode = data.get('isSimulateMode', False)

    try:
        deletion_id = str(uuid.uuid4())
        upload_key = f"deletions/{deletion_id}.csv"

        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': upload_key,
                'ContentType': 'text/csv',
                'Metadata': {
                    'jobid': deletion_id,
                    'issimulatemode': str(is_simulate_mode).lower(),
                    'userid': user['sub'],
                    'jobtype': 'deletion'
                }
            },
            ExpiresIn=3600
        )

        jobs_table.put_item(
            Item={
                'JobId': deletion_id,
                'jobType': 'BULK_DELETION',
                'status': 'PENDING_UPLOAD',
                'startedBy': user['sub'],
                'startedAt': datetime.utcnow().isoformat(),
                'isSimulateMode': is_simulate_mode,
                'targetSystem': 'CLOUD_ONLY'
            }
        )

        log_audit(user['sub'], 'START_BULK_DELETION', {'deletionId': deletion_id, 'simulate': is_simulate_mode}, 'SUCCESS')

        return jsonify(deletionId=deletion_id, uploadUrl=upload_url), 200

    except Exception as e:
        log_audit(user['sub'], 'START_BULK_DELETION', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error initiating bulk deletion: {str(e)}'), 500

@mig_bp.route('/audit-sync', methods=['POST', 'OPTIONS'])
@login_required()
def start_audit_sync():
    """Start audit/sync between legacy and cloud databases"""
    user = request.environ['user']
    data = request.json
    sync_direction = data.get('syncDirection', 'LEGACY_TO_CLOUD')  # LEGACY_TO_CLOUD, CLOUD_TO_LEGACY, BOTH_WAYS
    is_simulate_mode = data.get('isSimulateMode', True)  # Default to simulate for safety

    try:
        audit_id = str(uuid.uuid4())
        upload_key = f"audits/{audit_id}.csv"

        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': upload_key,
                'ContentType': 'text/csv',
                'Metadata': {
                    'jobid': audit_id,
                    'issimulatemode': str(is_simulate_mode).lower(),
                    'userid': user['sub'],
                    'jobtype': 'audit_sync',
                    'syncdirection': sync_direction
                }
            },
            ExpiresIn=3600
        )

        jobs_table.put_item(
            Item={
                'JobId': audit_id,
                'jobType': 'AUDIT_SYNC',
                'status': 'PENDING_UPLOAD',
                'startedBy': user['sub'],
                'startedAt': datetime.utcnow().isoformat(),
                'isSimulateMode': is_simulate_mode,
                'syncDirection': sync_direction
            }
        )

        log_audit(user['sub'], 'START_AUDIT_SYNC', {
            'auditId': audit_id, 
            'simulate': is_simulate_mode, 
            'direction': sync_direction
        }, 'SUCCESS')

        return jsonify(auditId=audit_id, uploadUrl=upload_url), 200

    except Exception as e:
        log_audit(user['sub'], 'START_AUDIT_SYNC', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error initiating audit sync: {str(e)}'), 500

@mig_bp.route('/status/<job_id>', methods=['GET'])
@login_required()
def get_job_status(job_id):
    try:
        response = jobs_table.get_item(Key={'JobId': job_id})
        status = response.get('Item')
        if not status:
            return jsonify(msg='Job not found'), 404
        
        # Ensure JobId is in response for frontend
        status['JobId'] = job_id
        
        return jsonify(status)
    except Exception as e:
        return jsonify(msg=f'Error getting job status: {str(e)}'), 500

@mig_bp.route('/report/<job_id>', methods=['GET'])
@login_required()
def get_job_report(job_id):
    try:
        response = jobs_table.get_item(Key={'JobId': job_id})
        job = response.get('Item')
        if not job:
            return jsonify(msg='Job not found'), 404

        report_key = job.get('reportS3Key')
        if not report_key:
            if job.get('status') == 'FAILED':
                 return jsonify(msg=f"Job failed: {job.get('failureReason', 'Unknown error')}"), 404
            return jsonify(msg='Report not yet available or job is still processing'), 404

        # Generate appropriate filename based on job type
        job_type = job.get('jobType', 'migration').lower()
        filename = f"{job_type}-report-{job_id}.csv"

        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': report_key,
                'ResponseContentDisposition': f'attachment; filename="{filename}"'
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
        limit = int(request.args.get('limit', 50))
        job_type = request.args.get('type', 'all').upper()  # ALL, MIGRATION, BULK_DELETION, AUDIT_SYNC
        
        if job_type == 'ALL':
            response = jobs_table.scan(
                FilterExpression=Attr('startedBy').eq(user['sub'])
            )
        else:
            response = jobs_table.scan(
                FilterExpression=Attr('startedBy').eq(user['sub']) & Attr('jobType').eq(job_type)
            )
            
        jobs = response.get('Items', [])
        
        # Sort by startedAt descending
        jobs.sort(key=lambda x: x.get('startedAt', ''), reverse=True)
        jobs = jobs[:limit]
        
        # Ensure JobId is included and add display properties
        for job in jobs:
            if 'JobId' not in job:
                job['JobId'] = job.get('migrationId', job.get('JobId', 'unknown'))
            
            # Add display-friendly job type
            job_type_display = {
                'MIGRATION': 'Migration',
                'BULK_DELETION': 'Bulk Deletion',
                'AUDIT_SYNC': 'Audit & Sync'
            }.get(job.get('jobType', 'MIGRATION'), 'Migration')
            
            job['jobTypeDisplay'] = job_type_display
            
            # Add progress percentage
            total = job.get('totalRecords', 0)
            if total > 0:
                processed = (job.get('migrated', 0) + job.get('failed', 0) + 
                           job.get('alreadyPresent', 0) + job.get('deleted', 0) + 
                           job.get('not_found_in_legacy', 0) + job.get('not_found_in_cloud', 0))
                job['progressPercent'] = min(100, (processed / total) * 100)
            else:
                job['progressPercent'] = 0 if job.get('status') in ['PENDING_UPLOAD', 'IN_PROGRESS'] else 100
        
        return jsonify({'jobs': jobs})
        
    except Exception as e:
        return jsonify(msg=f'Error getting migration jobs: {str(e)}'), 500

@mig_bp.route('/cancel/<job_id>', methods=['POST'])
@login_required()
def cancel_job(job_id):
    """Cancel a migration/deletion/audit job"""
    user = request.environ['user']
    try:
        # Get current job status
        response = jobs_table.get_item(Key={'JobId': job_id})
        job = response.get('Item')
        
        if not job:
            return jsonify(msg='Job not found'), 404
            
        # Check if user owns the job
        if job.get('startedBy') != user['sub']:
            return jsonify(msg='Unauthorized to cancel this job'), 403
            
        # Only allow cancellation of pending or in-progress jobs
        current_status = job.get('status')
        if current_status in ['COMPLETED', 'FAILED', 'CANCELLED']:
            return jsonify(msg=f'Cannot cancel job with status: {current_status}'), 400
            
        # Update job status to cancelled
        jobs_table.update_item(
            Key={'JobId': job_id},
            UpdateExpression="SET #s = :s, cancelledAt = :c, cancelledBy = :cb",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': 'CANCELLED',
                ':c': datetime.utcnow().isoformat(),
                ':cb': user['sub']
            }
        )
        
        job_type = job.get('jobType', 'MIGRATION')
        log_audit(user['sub'], f'CANCEL_{job_type}', {'jobId': job_id}, 'SUCCESS')
        
        return jsonify(msg=f'{job.get("jobTypeDisplay", "Job")} cancelled successfully'), 200
        
    except Exception as e:
        log_audit(user['sub'], 'CANCEL_JOB', {'jobId': job_id}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error cancelling job: {str(e)}'), 500

@mig_bp.route('/copy-job/<job_id>', methods=['POST'])
@login_required()
def copy_job(job_id):
    """Copy a job configuration to create a new job"""
    user = request.environ['user']
    try:
        # Get original job
        response = jobs_table.get_item(Key={'JobId': job_id})
        original_job = response.get('Item')
        
        if not original_job:
            return jsonify(msg='Job not found'), 404
            
        # Check if user owns the job or has access
        if original_job.get('startedBy') != user['sub']:
            return jsonify(msg='Unauthorized to copy this job'), 403
        
        # Create new job ID
        new_job_id = str(uuid.uuid4())
        job_type = original_job.get('jobType', 'MIGRATION')
        
        # Determine upload path based on job type
        if job_type == 'BULK_DELETION':
            upload_key = f"deletions/{new_job_id}.csv"
        elif job_type == 'AUDIT_SYNC':
            upload_key = f"audits/{new_job_id}.csv"
        else:
            upload_key = f"uploads/{new_job_id}.csv"
        
        # Create presigned URL
        metadata = {
            'jobid': new_job_id,
            'issimulatemode': str(original_job.get('isSimulateMode', False)).lower(),
            'userid': user['sub'],
            'jobtype': job_type.lower().replace('_', '')
        }
        
        if job_type == 'AUDIT_SYNC':
            metadata['syncdirection'] = original_job.get('syncDirection', 'LEGACY_TO_CLOUD')
        
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': upload_key,
                'ContentType': 'text/csv',
                'Metadata': metadata
            },
            ExpiresIn=3600
        )
        
        # Create new job record
        new_job = {
            'JobId': new_job_id,
            'jobType': job_type,
            'status': 'PENDING_UPLOAD',
            'startedBy': user['sub'],
            'startedAt': datetime.utcnow().isoformat(),
            'isSimulateMode': original_job.get('isSimulateMode', False),
            'copiedFrom': job_id
        }
        
        # Add job-type specific fields
        if job_type == 'BULK_DELETION':
            new_job['targetSystem'] = 'CLOUD_ONLY'
        elif job_type == 'AUDIT_SYNC':
            new_job['syncDirection'] = original_job.get('syncDirection', 'LEGACY_TO_CLOUD')
        
        jobs_table.put_item(Item=new_job)
        
        log_audit(user['sub'], f'COPY_{job_type}', {
            'newJobId': new_job_id, 
            'originalJobId': job_id
        }, 'SUCCESS')
        
        return jsonify({
            'jobId': new_job_id,
            'uploadUrl': upload_url,
            'jobType': job_type,
            'msg': f'{original_job.get("jobTypeDisplay", "Job")} copied successfully'
        }), 200
        
    except Exception as e:
        log_audit(user['sub'], 'COPY_JOB', {'jobId': job_id}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error copying job: {str(e)}'), 500

@mig_bp.route('/stats', methods=['GET'])
@login_required()
def get_migration_stats():
    """Get migration statistics for the current user"""
    user = request.environ['user']
    try:
        # Get all jobs for the user
        response = jobs_table.scan(
            FilterExpression=Attr('startedBy').eq(user['sub'])
        )
        jobs = response.get('Items', [])
        
        stats = {
            'totalJobs': len(jobs),
            'completedJobs': len([j for j in jobs if j.get('status') == 'COMPLETED']),
            'failedJobs': len([j for j in jobs if j.get('status') == 'FAILED']),
            'runningJobs': len([j for j in jobs if j.get('status') == 'IN_PROGRESS']),
            'totalRecordsMigrated': sum(j.get('migrated', 0) for j in jobs),
            'totalRecordsDeleted': sum(j.get('deleted', 0) for j in jobs),
            'totalRecordsFailed': sum(j.get('failed', 0) for j in jobs),
            'jobsByType': {}
        }
        
        # Group by job type
        for job in jobs:
            job_type = job.get('jobType', 'MIGRATION')
            if job_type not in stats['jobsByType']:
                stats['jobsByType'][job_type] = {
                    'count': 0,
                    'completed': 0,
                    'failed': 0
                }
            stats['jobsByType'][job_type]['count'] += 1
            if job.get('status') == 'COMPLETED':
                stats['jobsByType'][job_type]['completed'] += 1
            elif job.get('status') == 'FAILED':
                stats['jobsByType'][job_type]['failed'] += 1
        
        return jsonify(stats), 200
        
    except Exception as e:
        return jsonify(msg=f'Error getting migration stats: {str(e)}'), 500
