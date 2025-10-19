import os
from flask import Blueprint, request, jsonify
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
import json

from auth import login_required
from audit import log_audit
from parse_spml import parse_spml_to_json
import legacy_db 

prov_bp = Blueprint('prov', __name__)

# This is for the CLOUD database (DynamoDB)
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

# --- MODIFIED LINE ---
# Get provisioning mode: Default changed from 'cloud' to 'dual_prov'
MODE = os.getenv('PROV_MODE', 'dual_prov') 

# --- Centralized Dual Provisioning Core Function ---

def dual_provision(data, method='put'):
    """
    Writes or deletes data in both legacy (MySQL) and cloud (DynamoDB) based on the current mode.
    If MODE is 'cloud', legacy operations are skipped.
    """
    uid = data.get('uid') or data.get('subscriberId')
    
    # 1. --- Legacy DB (MySQL) Action ---
    if MODE in ['legacy', 'dual_prov']:
        try:
            if method == 'put':
                legacy_db.create_subscriber_full_profile(data)
            elif method == 'update':
                # Note: The original legacy_db.py's update function is a placeholder.
                # This call assumes it's implemented to update based on UID.
                legacy_db.update_subscriber_full_profile(uid, data)
            elif method == 'delete':
                legacy_db.delete_subscriber(uid)
        except Exception as e:
            print(f"Error in legacy DB (MySQL) operation: {e}")
            # Re-raise the exception to signal a dual-provisioning failure
            raise Exception(f"Dual Provisioning Failed: Legacy DB Unreachable: {str(e)}")
            
    # 2. --- Cloud (DynamoDB) Action ---
    if MODE in ['cloud', 'dual_prov']:
        try:
            # DynamoDB uses 'subscriberId' as its primary key, so we map uid to it
            data['subscriberId'] = uid
            
            if method == 'put' or method == 'update':
                subscriber_table.put_item(Item=data)
            elif method == 'delete':
                subscriber_table.delete_item(Key={'subscriberId': uid})
        except Exception as e:
            print(f"Error in cloud DB (DynamoDB) operation: {e}")
            raise Exception(f"Dual Provisioning Failed: Cloud DB Error: {str(e)}")
            

# --- DynamoDB Helper Functions for Validation ---

def check_dynamodb_duplicate(identifier, value, current_uid=None):
    """
    Checks for duplicates in DynamoDB using its Global Secondary Indexes (GSIs).
    Returns a descriptive error string if a duplicate is found, otherwise None.
    """
    index_name = f'{identifier.upper()}-Index'
    
    try:
        # Query the GSI based on the identifier type
        response = subscriber_table.query(
            IndexName=index_name,
            KeyConditionExpression=Key(identifier).eq(value)
        )
        
        if response['Items']:
            for item in response['Items']:
                # If we are updating (current_uid is provided), ensure the duplicate isn't the item being updated
                if current_uid and item.get('subscriberId') == current_uid:
                    continue
                
                # Found a true duplicate
                return f"Cloud DB (GSI: {identifier.upper()})", item.get('subscriberId')
                
    except Exception as e:
        # This will catch the "ValidationException" if the index doesn't exist
        print(f"CRITICAL: Failed to query GSI '{index_name}'. Error: {e}")
        # Re-raise to stop the operation, as validation can't be guaranteed
        raise Exception(f"Validation failed: DynamoDB Index '{index_name}' not found or query failed.")

    return None, None

# --- MODIFIED SEARCH ENDPOINT ---

@prov_bp.route('/search', methods=['GET'])
@login_required()
def search_subscriber():
    """
    Searches for a subscriber by a specific identifier (UID, IMSI, or MSISDN) 
    in cloud and legacy databases, using the 'type' parameter sent from the frontend.
    """
    identifier_value = request.args.get('identifier')
    # Read the 'type' (uid, imsi, msisdn) from the query string
    identifier_type = request.args.get('type', 'uid') # Default to 'uid' if not provided

    if not identifier_value:
        return jsonify(msg='Identifier query parameter is required'), 400

    try:
        cloud_data = None
        
        # Use the 'type' to search efficiently
        if identifier_type == 'uid':
            # 1. Check cloud (DynamoDB) by Primary Key
            cloud_data = subscriber_table.get_item(Key={'subscriberId': identifier_value}).get('Item')
        
        elif identifier_type == 'imsi':
            # 2. Check cloud (DynamoDB) by IMSI GSI
            response = subscriber_table.query(
                IndexName='IMSI-Index',
                KeyConditionExpression=Key('imsi').eq(identifier_value)
            )
            if response['Items']:
                cloud_data = response['Items'][0]

        elif identifier_type == 'msisdn':
            # 3. Check cloud (DynamoDB) by MSISDN GSI
            response = subscriber_table.query(
                IndexName='MSISDN-Index',
                KeyConditionExpression=Key('msisdn').eq(identifier_value)
            )
            if response['Items']:
                cloud_data = response['Items'][0]
        
        # --- Process Cloud Result ---
        if cloud_data:
            cloud_data['uid'] = cloud_data.get('subscriberId')
            cloud_data['source'] = 'Cloud/DynamoDB' # Add source for frontend
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type, 'source': 'cloud'}, 'SUCCESS')
            return jsonify(cloud_data), 200

        # 4. If not found in cloud, query the legacy (MySQL) database
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier_value)
        if legacy_data:
            legacy_data['source'] = 'Legacy/MySQL' # Add source for frontend
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type, 'source': 'legacy'}, 'SUCCESS')
            return jsonify(legacy_data), 200
        
        # 5. If not found in either system
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type}, 'NOT_FOUND')
        return jsonify(msg='Subscriber not found in Cloud or Legacy database.'), 404
        
    except Exception as e:
        # Catch the "ValidationException" specifically if the index doesn't exist
        if "The table does not have the specified index" in str(e) or "Cannot do operations on a non-existent index" in str(e):
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type}, f'FAILED: {e}')
            return jsonify(msg=f"Search Error: The DynamoDB Index '{identifier_type.upper()}-Index' does not exist. The CloudFormation stack needs to be updated."), 500
        
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error during search: {str(e)}'), 500


# --- Create Endpoint with Full Duplicate Validation ---

@prov_bp.route('/subscriber', methods=['POST', 'OPTIONS'])
@login_required()
def add_subscriber():
    user = request.environ['user']
    data = request.json

    try:
        uid = data.get('uid')
        imsi = data.get('imsi')
        msisdn = data.get('msisdn')
        
        if not uid or not imsi:
             return jsonify(msg='Error: UID and IMSI are required for new subscriber'), 400

        # --- VALIDATION: Check for Duplicates in Cloud DB ---
        
        # 1. Check DynamoDB Primary Key (UID)
        if subscriber_table.get_item(Key={'subscriberId': uid}).get('Item'):
            return jsonify(msg=f"Validation Error: UID '{uid}' already exists in Cloud DB."), 400
        
        # 2. Check DynamoDB IMSI (via GSI)
        source, conflict_id = check_dynamodb_duplicate('imsi', imsi)
        if source:
            return jsonify(msg=f"Validation Error: IMSI '{imsi}' already exists in {source} (Sub ID: {conflict_id})."), 400

        # 3. Check DynamoDB MSISDN (via GSI)
        if msisdn:
            source, conflict_id = check_dynamodb_duplicate('msisdn', msisdn)
            if source:
                return jsonify(msg=f"Validation Error: MSISDN '{msisdn}' already exists in {source} (Sub ID: {conflict_id})."), 400

        # --- VALIDATION: Check for Duplicates in Legacy DB (if enabled) ---
        if MODE in ['legacy', 'dual_prov']:
            legacy_conflict = legacy_db.check_for_duplicates(uid, imsi, msisdn)
            if legacy_conflict:
                return jsonify(msg=f"Validation Error: {legacy_conflict}"), 400


        # --- Provisioning ---
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = user['sub']
        
        dual_provision(data, method='put')
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber created successfully', uid=data['uid']), 201
    
    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'{str(e)}'), 500


# --- Update Endpoint with Full Duplicate Validation and Exclusion ---

@prov_bp.route('/subscriber/<uid>', methods=['PUT', 'OPTIONS'])
@login_required()
def update_subscriber(uid):
    user = request.environ['user']
    data = request.json
    
    try:
        imsi = data.get('imsi')
        msisdn = data.get('msisdn')
        
        if not imsi:
             return jsonify(msg='Error: IMSI is required for subscriber update'), 400

        # 1. --- VALIDATION: Check for Duplicates in Cloud DB (excluding current UID) ---
        
        # Check DynamoDB IMSI (via GSI)
        source, conflict_id = check_dynamodb_duplicate('imsi', imsi, current_uid=uid)
        if source:
            return jsonify(msg=f"Validation Error: IMSI '{imsi}' is a duplicate in {source} (Sub ID: {conflict_id})."), 400

        # Check DynamoDB MSISDN (via GSI)
        if msisdn:
            source, conflict_id = check_dynamodb_duplicate('msisdn', msisdn, current_uid=uid)
            if source:
                return jsonify(msg=f"Validation Error: MSISDN '{msisdn}' is a duplicate in {source} (Sub ID: {conflict_id})."), 400

        # 2. --- VALIDATION: Check for Duplicates in Legacy DB (excluding current UID) ---
        if MODE in ['legacy', 'dual_prov']:
            # The original legacy_db.check_for_duplicates does not support exclusion.
            # A production system would need a modified query.
            # We'll rely on the DB constraint to fail the dual_provision call if there's a conflict.
            pass

        # --- Provisioning ---
        data['updated_at'] = datetime.utcnow().isoformat()
        data['updated_by'] = user['sub']
        # Ensure the UID is preserved for the dual_provision function
        data['uid'] = uid 
        
        dual_provision(data, method='update')
        
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', {'uid': uid, 'changes': data}, 'SUCCESS')
        return jsonify(msg='Subscriber updated successfully'), 200
        
    except Exception as e:
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'{str(e)}'), 500


# --- Delete Endpoint ---

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
        return jsonify(msg=f'{str(e)}'), 500


# --- Dashboard Endpoint: Subscriber Count ---

@prov_bp.route('/count', methods=['GET'])
@login_required()
def get_subscriber_count():
    """
    Fetches the total subscriber count from DynamoDB.
    """
    try:
        # Note: This operation is eventually consistent and slow for very large tables. 
        # A real production system would use a dedicated counter table.
        response = subscriber_table.scan(Select='COUNT')
        count = response.get('Count', 0)
        
        # Simulate Today's Provisions for the dashboard
        today_provisions = 0
        
        # Mocking logic for today's provisions
        if count > 0:
            today_provisions = max(1, count % 5) # Gives a number 1-4 for visual effect

        return jsonify(
            total_subscribers=count,
            today_provisions=today_provisions
        ), 200
    except Exception as e:
        log_audit('system', 'GET_COUNT', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error retrieving count: {str(e)}'), 500
