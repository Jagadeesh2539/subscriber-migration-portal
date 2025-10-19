from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
from parse_spml import parse_spml_to_json
import boto3
import os
from datetime import datetime
import json
import legacy_db # <-- NEW: Import our powerful new connector

prov_bp = Blueprint('prov', __name__)

# This is for the CLOUD database (DynamoDB)
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

# REMOVED the old hardcoded LEGACY_DB dictionary
 
MODE = os.getenv('PROV_MODE', 'dual_prov')

def dual_provision(data, method='put'):
    """
    Writes data to both legacy (MySQL) and cloud (DynamoDB) based on the current mode.
    """
    uid = data.get('uid')
    if not uid:
        # For delete operations, the uid might be passed differently
        uid = data.get('subscriberId')

    # --- Legacy DB (MySQL) Action ---
    if MODE in ['legacy', 'dual_prov']:
        try:
            if method == 'put':
                legacy_db.create_subscriber_full_profile(data)
            elif method == 'delete':
                legacy_db.delete_subscriber(uid)
        except Exception as e:
            print(f"Error in legacy DB (MySQL) operation: {e}")
            # In a real system, this failure would be queued for a retry attempt
            raise e # Re-raise the exception to fail the transaction
            
    # --- Cloud (DynamoDB) Action ---
    if MODE in ['cloud', 'dual_prov']:
        try:
            if method == 'put':
                # DynamoDB uses 'subscriberId' as its primary key, so we map uid to it
                data['subscriberId'] = uid
                subscriber_table.put_item(Item=data)
            elif method == 'delete':
                subscriber_table.delete_item(Key={'subscriberId': uid})
        except Exception as e:
            print(f"Error in cloud DB (DynamoDB) operation: {e}")
            # In a real system, this failure would be queued for a retry attempt
            raise e # Re-raise the exception to fail the transaction

# --- NEW: Powerful Search Endpoint ---
@prov_bp.route('/search', methods=['GET'])
@login_required()
def search_subscriber():
    """
    Searches for a subscriber by any identifier in cloud and legacy databases.
    """
    identifier = request.args.get('identifier')
    if not identifier:
        return jsonify(msg='Identifier query parameter is required'), 400

    try:
        # 1. Check cloud (DynamoDB) first for speed, as it's the target system
        cloud_data = subscriber_table.get_item(Key={'subscriberId': identifier}).get('Item')
        if cloud_data:
            cloud_data['uid'] = cloud_data.get('subscriberId') # Normalize for frontend consistency
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier, 'source': 'cloud'}, 'SUCCESS')
            return jsonify(cloud_data), 200
        
        # 2. If not found in cloud, query the legacy (MySQL) database
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier)
        if legacy_data:
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier, 'source': 'legacy'}, 'SUCCESS')
            return jsonify(legacy_data), 200
        
        # 3. If not found in either system
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier}, 'NOT_FOUND')
        return jsonify(msg='Subscriber not found'), 404
        
    except Exception as e:
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- NEW: Create Endpoint for Full Subscriber Profile ---
@prov_bp.route('/subscriber', methods=['POST', 'OPTIONS'])
@login_required()
def add_subscriber():
    """
    Handles creating a new subscriber in both legacy and cloud DBs.
    """
    user = request.environ['user']
    data = request.json

    try:
        if not data.get('uid'):
             return jsonify(msg='Error: uid is required for new subscriber'), 400
        
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = user['sub']
        
        dual_provision(data, method='put')
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber created successfully', uid=data['uid']), 201
    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- NEW: Delete Endpoint ---
@prov_bp.route('/subscriber/<uid>', methods=['DELETE', 'OPTIONS'])
@login_required(role='admin') 
def delete_subscriber(uid):
    user = request.environ['user']
    
    try:
        data_to_delete = {'uid': uid}
        dual_provision(data_to_delete, method='delete')
            
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', data_to_delete, 'SUCCESS')
        return jsonify(msg='Subscriber deleted successfully'), 200
    except Exception as e:
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

