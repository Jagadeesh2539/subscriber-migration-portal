import os
import boto3
from flask import Blueprint, request, jsonify
from boto3.dynamodb.conditions import Key, Attr
from auth import login_required
from audit import log_audit
from parse_spml import parse_spml_to_json
from datetime import datetime
import legacy_db 
import json

prov_bp = Blueprint('prov', __name__)

# This is for the CLOUD database (DynamoDB)
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

MODE = os.getenv('PROV_MODE', 'dual_prov')

def dual_provision(data, method='put', uid=None):
    """
    Writes data to both legacy (MySQL) and cloud (DynamoDB) based on the current mode.
    Handles create ('put'), update ('update'), and delete ('delete').
    """
    target_uid = uid if uid else data.get('uid')

    # --- Legacy DB (MySQL) Action ---
    if MODE in ['legacy', 'dual_prov']:
        try:
            if method == 'put':
                legacy_db.create_subscriber_full_profile(data)
            elif method == 'update':
                legacy_db.update_subscriber_full_profile(target_uid, data)
            elif method == 'delete':
                legacy_db.delete_subscriber(target_uid)
        except Exception as e:
            print(f"Error in legacy DB (MySQL) operation: {e}")
            raise e # Re-raise the exception to fail the transaction
            
    # --- Cloud (DynamoDB) Action ---
    if MODE in ['cloud', 'dual_prov']:
        try:
            # DynamoDB uses 'subscriberId' as its primary key
            data_to_write = data.copy()
            data_to_write['subscriberId'] = target_uid
            
            if method == 'put' or method == 'update':
                # Use put_item for full overwrite on create/update
                subscriber_table.put_item(Item=data_to_write)
            elif method == 'delete':
                subscriber_table.delete_item(Key={'subscriberId': target_uid})
        except Exception as e:
            print(f"Error in cloud DB (DynamoDB) operation: {e}")
            raise e 

def check_cloud_duplicates(uid, imsi, msisdn):
    """
    Checks DynamoDB for existing UID, IMSI, or MSISDN. 
    Returns a string detailing the conflict or None if no conflict is found.
    """
    # 1. Check Primary Key (UID/subscriberId)
    response = subscriber_table.get_item(Key={'subscriberId': uid})
    if 'Item' in response:
        return f"UID '{uid}' already exists in Cloud DB."

    # 2. Check IMSI and MSISDN (Uses scan with filter which is NOT production-optimal 
    # without GSIs, but works for the demo environment)
    
    # Check IMSI
    if imsi:
        response = subscriber_table.scan(
            FilterExpression=Attr('imsi').eq(imsi),
            ProjectionExpression='subscriberId'
        )
        if response.get('Items'):
            return f"IMSI '{imsi}' already exists in Cloud DB."

    # Check MSISDN
    if msisdn:
        response = subscriber_table.scan(
            FilterExpression=Attr('msisdn').eq(msisdn),
            ProjectionExpression='subscriberId'
        )
        if response.get('Items'):
            return f"MSISDN '{msisdn}' already exists in Cloud DB."

    return None

# --- COUNT ENDPOINT ---
@prov_bp.route('/count', methods=['GET'])
@login_required()
def get_subscriber_count():
    """Returns the total number of subscribers in the Cloud (DynamoDB)."""
    try:
        # NOTE: table.item_count returns a cached value. For a real-time count,
        # you would need to use a DynamoDB Query on a specific index, or an external metric.
        # We will use the cached value here for simplicity and dashboard use.
        count = subscriber_table.item_count
        return jsonify(count=count), 200
    except Exception as e:
        return jsonify(msg=f'Error fetching count: {str(e)}'), 500

# --- SEARCH ENDPOINT ---
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
        # 1. Check cloud (DynamoDB) first
        cloud_data = subscriber_table.get_item(Key={'subscriberId': identifier}).get('Item')
        if not cloud_data:
            # Check secondary keys (IMSI/MSISDN) in cloud
            response = subscriber_table.scan(
                FilterExpression=Attr('imsi').eq(identifier) | Attr('msisdn').eq(identifier)
            )
            if response.get('Items'):
                cloud_data = response['Items'][0]

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

# --- CREATE ENDPOINT ---
@prov_bp.route('/subscriber', methods=['POST', 'OPTIONS'])
@login_required()
def add_subscriber():
    """
    Handles creating a new subscriber in both legacy and cloud DBs, with full duplicate validation.
    """
    user = request.environ['user']
    data = request.json

    try:
        uid = data.get('uid')
        imsi = data.get('imsi')
        msisdn = data.get('msisdn')
        
        if not uid or not imsi:
             return jsonify(msg='Error: UID and IMSI are required for new subscriber'), 400

        # --- STEP 1: Full Duplicate Validation ---
        
        # Check Cloud DB for UID, IMSI, MSISDN duplicates
        cloud_conflict = check_cloud_duplicates(uid, imsi, msisdn)
        if cloud_conflict:
            log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: DUPLICATE {cloud_conflict}')
            return jsonify(msg=f'Validation Error: {cloud_conflict}'), 400

        # Check Legacy DB for UID, IMSI, MSISDN duplicates (if enabled)
        legacy_conflict = legacy_db.check_for_duplicates(uid, imsi, msisdn)
        if legacy_conflict:
            log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: DUPLICATE {legacy_conflict}')
            return jsonify(msg=f'Validation Error: {legacy_conflict}'), 400

        # --- STEP 2: Dual Provisioning ---
        
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = user['sub']
        
        dual_provision(data, method='put')
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber created successfully', uid=uid), 201
    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- UPDATE ENDPOINT ---
@prov_bp.route('/subscriber/<uid>', methods=['PUT', 'OPTIONS'])
@login_required()
def update_subscriber(uid):
    """
    Handles updating an existing subscriber in both legacy and cloud DBs.
    """
    user = request.environ['user']
    data = request.json

    try:
        data['updated_at'] = datetime.utcnow().isoformat()
        data['updated_by'] = user['sub']
        
        # We pass the UID explicitly for the update operation
        dual_provision(data, method='update', uid=uid)
        
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber updated successfully', uid=uid), 200
    except Exception as e:
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', data, f'FAILED: {str(e)}'), 500

# --- DELETE ENDPOINT ---
@prov_bp.route('/subscriber/<uid>', methods=['DELETE', 'OPTIONS'])
@login_required(role='admin') 
def delete_subscriber(uid):
    user = request.environ['user']
    
    try:
        data_to_delete = {'uid': uid}
        dual_provision(data_to_delete, method='delete', uid=uid)
            
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', data_to_delete, 'SUCCESS')
        return jsonify(msg='Subscriber deleted successfully'), 200
    except Exception as e:
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500
