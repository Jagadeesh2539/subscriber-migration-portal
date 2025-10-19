from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import boto3
import os
from datetime import datetime

# --- NEW: Import our new legacy DB connector ---
import legacy_db

prov_bp = Blueprint('prov', __name__)

# Cloud (DynamoDB) connection remains the same
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

# --- REMOVED: The old LEGACY_DB dictionary is gone ---

MODE = os.environ.get('PROV_MODE', 'dual_prov')

def dual_provision(data, method='put'):
    """
    Writes data to both legacy and cloud based on the current mode.
    This now calls functions from our legacy_db connector.
    """
    uid = data.get('uid') or data.get('subscriberId')

    # --- Legacy DB Action ---
    if MODE in ['legacy', 'dual_prov']:
        try:
            if method == 'put':
                # We will implement this function in a later step
                legacy_db.create_subscriber(data)
            elif method == 'delete':
                legacy_db.delete_subscriber(uid)
        except Exception as e:
            print(f"Error in legacy DB operation: {e}")
            
    # --- Cloud (DynamoDB) Action ---
    if MODE in ['cloud', 'dual_prov']:
        try:
            if method == 'put':
                data['subscriberId'] = uid
                subscriber_table.put_item(Item=data)
            elif method == 'delete':
                subscriber_table.delete_item(Key={'subscriberId': uid})
        except Exception as e:
            print(f"Error in DynamoDB operation: {e}")


# --- NEW: A powerful search endpoint that replaces the old get_subscriber ---
@prov_bp.route('/search', methods=['GET'])
@login_required()
def search_subscriber():
    """
    Searches for a subscriber by any identifier (uid, imsi, msisdn).
    Checks cloud (DynamoDB) first, then falls back to legacy (MySQL).
    """
    identifier = request.args.get('identifier')
    if not identifier:
        return jsonify(msg='Identifier query parameter is required'), 400

    try:
        # 1. Check Cloud DB first
        # Note: DynamoDB only allows efficient lookups on its primary key (subscriberId).
        # We assume the identifier might be a UID/subscriberId for this check.
        cloud_data = subscriber_table.get_item(Key={'subscriberId': identifier}).get('Item')
        
        if cloud_data:
            # If found in cloud, we might still want to enrich it with legacy data if needed,
            # but for now, we'll just return it.
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier, 'source': 'cloud'}, 'SUCCESS')
            # Map subscriberId back to uid for frontend consistency
            cloud_data['uid'] = cloud_data.get('subscriberId')
            return jsonify(cloud_data), 200

        # 2. If not in cloud, check Legacy DB using our powerful new function
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier)
        if legacy_data:
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier, 'source': 'legacy'}, 'SUCCESS')
            return jsonify(legacy_data), 200
        
        # 3. If not found anywhere
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier}, 'NOT_FOUND')
        return jsonify(msg='Subscriber not found'), 404

    except Exception as e:
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- The rest of the functions (POST, PUT, DELETE) will be updated later ---
# --- They still use the placeholder logic for now ---

@prov_bp.route('/subscriber', methods=['POST', 'OPTIONS'])
@login_required()
def add_subscriber():
    # This function will be enhanced later to handle the multi-table schema
    return jsonify(msg="Add subscriber endpoint needs to be updated."), 501


@prov_bp.route('/subscriber/<uid>', methods=['PUT', 'OPTIONS'])
@login_required()
def update_subscriber(uid):
    return jsonify(msg="Update subscriber endpoint needs to be updated."), 501


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
        log_audit('user', 'DELETE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

