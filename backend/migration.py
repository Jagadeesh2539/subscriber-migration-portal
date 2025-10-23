from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import os
import boto3
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Attr, Key
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.error(f"Error creating DynamoDB table reference: {e}")
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

# ENHANCED STATUS ENDPOINT - THIS IS THE MAIN FIX
@mig_bp.route('/status/<job_id>', methods=['GET'])
@login_required()
def get_job_status(job_id):
    """Enhanced job status endpoint with comprehensive error handling and logging"""
    try:
        logger.info(f"[Status Request] Job ID: {job_id} from user: {request.environ['user']['sub']}")
        
        if not jobs_table:
            logger.error("[Status Error] Jobs table not initialized")
            return jsonify({
                'error': 'Database not available',
                'JobId': job_id,
                'status': 'ERROR'
            }), 500
        
        # Query DynamoDB for job
        response = jobs_table.get_item(Key={'JobId': job_id})
									 
					  
													
        
        if 'Item' not in response:
            logger.warning(f"[Status Error] Job {job_id} not found in database")
            return jsonify({
                'error': 'Job not found',
                'msg': f'Migration job {job_id} was not found. It may have been deleted or expired.',
                'JobId': job_id,
                'status': 'NOT_FOUND'
            }), 404
        
        job_data = response['Item']
        
        # Check if user has access to this job
        job_owner = job_data.get('startedBy')
        current_user = request.environ['user']['sub']
        if job_owner != current_user:
            logger.warning(f"[Status Error] User {current_user} tried to access job {job_id} owned by {job_owner}")
            return jsonify({
                'error': 'Access denied',
                'msg': 'You do not have permission to view this job.',
                'JobId': job_id,
                'status': 'ACCESS_DENIED'
            }), 403
        
        # Build standardized response
        status_response = {
            'JobId': job_data.get('JobId', job_id),
            'status': job_data.get('status', 'UNKNOWN'),
            'statusMessage': job_data.get('statusMessage', ''),
            'jobType': job_data.get('jobType', 'MIGRATION'),
            'startedBy': job_data.get('startedBy'),
            'startedAt': job_data.get('startedAt'),
            'lastUpdated': job_data.get('lastUpdated'),
            'isSimulateMode': job_data.get('isSimulateMode', False),
            
            # Progress data
            'totalRecords': job_data.get('totalRecords'),
            'migrated': job_data.get('migrated'),
            'failed': job_data.get('failed'), 
            'alreadyPresent': job_data.get('alreadyPresent'),
            'deleted': job_data.get('deleted'),  # For deletion jobs
            'not_found_in_legacy': job_data.get('not_found_in_legacy'),
            'not_found_in_cloud': job_data.get('not_found_in_cloud'),
            
            # Report and error data
            'reportS3Key': job_data.get('reportS3Key'),
            'failureReason': job_data.get('failureReason') or (
                job_data.get('statusMessage') if job_data.get('status') == 'FAILED' else None
            ),
            
            # Additional metadata
            'syncDirection': job_data.get('syncDirection'),  # For audit jobs
            'targetSystem': job_data.get('targetSystem'),    # For deletion jobs
            'copiedFrom': job_data.get('copiedFrom')         # If copied from another job
        }
        
        # Add computed progress percentage
        total = status_response.get('totalRecords', 0)
        if total and total > 0:
            processed = sum(filter(None, [
                status_response.get('migrated', 0),
                status_response.get('failed', 0),
                status_response.get('alreadyPresent', 0),
                status_response.get('deleted', 0),
                status_response.get('not_found_in_legacy', 0),
                status_response.get('not_found_in_cloud', 0)
            ]))
            status_response['progressPercent'] = min(100, int((processed / total) * 100))
        else:
            # Default progress based on status
            if status_response['status'] in ['COMPLETED', 'FAILED', 'CANCELLED']:
                status_response['progressPercent'] = 100
            elif status_response['status'] == 'IN_PROGRESS':
                status_response['progressPercent'] = 50  # Assume 50% if no detailed data
            else:
                status_response['progressPercent'] = 0
        
        logger.info(f"[Status Success] Job {job_id} status: {status_response['status']} "
                   f"({status_response.get('progressPercent', 0)}% complete)")
        
        return jsonify(status_response), 200
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Status Error] Exception for job {job_id}: {error_msg}")
        
        return jsonify({
            'error': 'Internal server error',
            'msg': f'Error retrieving job status: {error_msg}',
            'JobId': job_id,
            'status': 'ERROR'
        }), 500

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
