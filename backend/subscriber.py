from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
from parse_spml import parse_spml_to_json
import boto3
import os
from datetime import datetime
import json
import requests
import xmltodict

prov_bp = Blueprint('prov', __name__)

# This now correctly reads the table name from the Lambda environment variable
SUBSCRIBER_TABLE_NAME = os.environ.get('SUBSCRIBER_TABLE_NAME')
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE_NAME)

LEGACY_DB = {
    "502122900001234": {"uid": "502122900001234", "imsi": "502122900001234", "msisdn": "60132901234", "plan": "Gold"},
    "502122900001235": {"uid": "502122900001235", "imsi": "502122900001235", "msisdn": "60132901235", "plan": "Silver"}
}
 
MODE = os.getenv('PROV_MODE', 'dual_prov')

# Updated function to handle deletes
def dual_provision(data, method='put'):
    # Use 'subscriberId' as the key to match CloudFormation
    key = data.get('subscriberId')
    if not key:
        key = data.get('uid') # Fallback
        
    if MODE in ['legacy', 'dual_prov']:
        if method == 'put':
            LEGACY_DB[key] = data
        elif method == 'delete':
            LEGACY_DB.pop(key, None)
        
    if MODE in ['cloud', 'dual_prov']:
        if method == 'put':
            subscriber_table.put_item(Item=data)
        elif method == 'delete':
            subscriber_table.delete_item(Key={'subscriberId': key})

# --- FIX ---
@prov_bp.route('/subscriber', methods=['POST', 'OPTIONS'])
@login_required()
def add_subscriber():
    user = request.environ['user']
    data = request.json
    
    try:
        # Use 'subscriberId' to match CloudFormation key
        data['subscriberId'] = data.get('uid') 
        if not data['subscriberId']:
             return jsonify(msg='Error: uid is required'), 400
        
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = user['sub']
        dual_provision(data, method='put')
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber added successfully', uid=data['subscriberId']), 201
    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- FIX (No change needed, GET only) ---
@prov_bp.route('/subscribers', methods=['GET'])
@login_required()
def get_all_subscribers():
    try:
        if MODE in ['cloud', 'dual_prov']:
            response = subscriber_table.scan()
            items = response.get('Items', [])
        else: # Legacy only
            items = list(LEGACY_DB.values())
            
        log_audit('system', 'FETCH_ALL_SUBSCRIBER', {}, 'SUCCESS')
        for item in items:
            item['uid'] = item.get('subscriberId')
        return jsonify(subscribers=items), 200
    except Exception as e:
        log_audit('system', 'FETCH_ALL_SUBSCRIBER', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- FIX (No change needed, GET only) ---
@prov_bp.route('/subscriber/<uid>', methods=['GET'])
@login_required()
def get_subscriber(uid):
    try:
        cloud_data = subscriber_table.get_item(Key={'subscriberId': uid}).get('Item')
        if cloud_data:
            cloud_data['uid'] = cloud_data.get('subscriberId')
            log_audit('system', 'FETCH_SUBSCRIBER', {'uid': uid, 'source': 'cloud'}, 'SUCCESS')
            return jsonify(cloud_data), 200
        
        legacy_data = LEGACY_DB.get(uid)
        if legacy_data:
            log_audit('system', 'FETCH_SUBSCRIBER', {'uid': uid, 'source': 'legacy'}, 'SUCCESS')
            return jsonify(legacy_data), 200
        
        return jsonify(msg='Subscriber not found'), 404
    except Exception as e:
        log_audit('system', 'FETCH_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}'), 500
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- FIX ---
@prov_bp.route('/subscriber/<uid>', methods=['PUT', 'OPTIONS'])
@login_required()
def update_subscriber(uid):
    user = request.environ['user']
    data = request.json
    
    try:
        data['subscriberId'] = uid
        data['uid'] = uid
        data['updated_at'] = datetime.utcnow().isoformat()
        data['updated_by'] = user['sub']
        
        dual_provision(data, method='put')
        
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber updated successfully', data=data), 200
    except Exception as e:
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

# --- FIX ---
@prov_bp.route('/subscriber/<uid>', methods=['DELETE', 'OPTIONS'])
@login_required(role='admin') 
def delete_subscriber(uid):
    user = request.environ['user']
    
    try:
        data_to_delete = {'subscriberId': uid}
        dual_provision(data_to_delete, method='delete')
            
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', data_to_delete, 'SUCCESS')
        return jsonify(msg='Subscriber deleted successfully'), 200
    except Exception as e:
        log_audit(user['sub'], 'DELETE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500
        
# --- FIX ---
@prov_bp.route('/subscriber/spml', methods=['POST', 'OPTIONS'])
@login_required()
def add_spml_subscriber():
    user = request.environ['user']
    try:
        parsed_data = parse_spml_to_json(request.data)
        parsed_data['subscriberId'] = parsed_data.get('uid')
        dual_provision(parsed_data, method='put')
        log_audit(user['sub'], 'ADD_SPML_SUBSCRIBER', parsed_data, 'SUCCESS')
        return jsonify(msg='SPML Subscriber added successfully'), 201
    except Exception as e:
        log_audit(user['sub'], 'ADD_SPML_SUBSCRIBER', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error parsing SPML: {str(e)}'), 400
