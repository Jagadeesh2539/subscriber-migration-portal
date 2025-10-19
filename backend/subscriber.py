from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import boto3
import os
from datetime import datetime
import legacy_db # Import our new connector

prov_bp = Blueprint('prov', __name__)

# Cloud (DynamoDB) connection
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME) if SUBSCRIBER_TABLE_NAME else None

MODE = os.environ.get('PROV_MODE', 'dual_prov')

# --- NEW: A flexible search endpoint ---
@prov_bp.route('/search', methods=['GET'])
@login_required()
def search_subscriber():
    """
    Searches for a subscriber by UID, IMSI, or MSISDN.
    It checks the cloud (DynamoDB) first, then falls back to the legacy DB (MySQL).
    """
    identifier = request.args.get('identifier')
    if not identifier:
        return jsonify(msg='Identifier query parameter is required'), 400

    try:
        # Check cloud first
        cloud_data = None
        if subscriber_table:
            # Note: A real-world cloud DB would need secondary indexes (GSIs) 
            # on IMSI and MSISDN for this to be efficient. This example only checks the primary key.
            response = subscriber_table.get_item(Key={'subscriberId': identifier})
            cloud_data = response.get('Item')

        if cloud_data:
            # Map subscriberId back to uid for frontend consistency
            cloud_data['uid'] = cloud_data.get('subscriberId')
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier, 'source': 'cloud'}, 'SUCCESS')
            return jsonify(cloud_data), 200
        
        # If not in cloud, check legacy
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier)
        if legacy_data:
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier, 'source': 'legacy'}, 'SUCCESS')
            return jsonify(legacy_data), 200
        
        # If not found in either, return 404
        return jsonify(msg='Subscriber not found'), 404
        
    except Exception as e:
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- NEW: A full-profile create endpoint ---
@prov_bp.route('/subscriber', methods=['POST', 'OPTIONS'])
@login_required()
def add_subscriber():
    """
    Handles creating a new subscriber in both legacy (MySQL) and cloud (DynamoDB) systems.
    """
    user = request.environ['user']
    data = request.json

    try:
        if not data.get('uid'):
             return jsonify(msg='Error: uid is a required field'), 400

        # --- Dual Provisioning: Create in both systems ---
        if MODE in ['legacy', 'dual_prov']:
            legacy_db.create_subscriber_full_profile(data)
        
        if MODE in ['cloud', 'dual_prov'] and subscriber_table:
            # For DynamoDB, we flatten the data for this example.
            # A real system might store complex objects or use DynamoDB Streams.
            cloud_item = data.copy()
            cloud_item['subscriberId'] = data['uid'] # Use 'subscriberId' as the primary key
            subscriber_table.put_item(Item=cloud_item)
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', {'uid': data['uid']}, 'SUCCESS')
        return jsonify(msg='Subscriber created successfully', uid=data['uid']), 201

    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', {'uid': data.get('uid')}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- NEW: A simple delete endpoint ---
@prov_bp.route('/subscriber/<uid>', methods=['DELETE', 'OPTIONS'])
@login_required(role='admin') 
def delete_subscriber(uid):
    """
    Handles deleting a subscriber from both legacy and cloud systems.
    """
    user = request.environ['user']
    
    try:
        # --- Dual Provisioning: Delete from both systems ---
        if MODE in ['legacy', 'dual_prov']:
            legacy_db.delete_subscriber(uid)
        
        if MODE in ['cloud', 'dual_prov'] and subscriber_table:
            subscriber_table.delete_item(Key={'subscriberId': uid})
            
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', {'uid': uid}, 'SUCCESS')
        return jsonify(msg='Subscriber deleted successfully'), 200

    except Exception as e:
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# NOTE: A full PUT/update endpoint would require significant logic to update 
# all 5 tables transactionally and is omitted for brevity, but would follow a similar pattern to create.

