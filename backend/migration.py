from flask import Blueprint, request, jsonify
from auth import login_required
from bulk_ops import start_migration_job, get_job_status
from audit import log_audit
import os

mig_bp = Blueprint('migration', __name__)

# --- FIX ---
@mig_bp.route('/bulk', methods=['POST', 'OPTIONS'])
@login_required()
def bulk_migration():
    user = request.environ['user']
    
    try:
        if 'file' not in request.files:
            return jsonify(msg='No file uploaded'), 400
        
        file = request.files['file']
        job_id = start_migration_job(file, user['sub'])
        
        log_audit(user['sub'], 'START_MIGRATION', {'job_id': job_id}, 'SUCCESS')
        return jsonify(jobId=job_id, msg='Migration started'), 202
    except Exception as e:
        log_audit(user['sub'], 'START_MIGRATION', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- FIX (No change needed, GET only) ---
@mig_bp.route('/status/<job_id>', methods=['GET'])
@login_required()
def migration_status(job_id):
    try:
        status = get_job_status(job_id)
        return jsonify(status)
    except Exception as e:
        return jsonify(msg=f'Error: {str(e)}'), 500
