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

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
subscriber_table = dynamodb.Table('SubscriberTable')

LEGACY_DB = {
    "502122900001234": {"uid": "502122900001234", "imsi": "502122900001234", "msisdn": "60132901234", "plan": "Gold"},
    "502122900001235": {"uid": "502122900001235", "imsi": "502122900001235", "msisdn": "60132901235", "plan": "Silver"}
}
 
MODE = os.getenv('PROV_MODE', 'dual_prov')

def dual_provision(data):
    if MODE in ['legacy', 'dual_prov']:
        LEGACY_DB[data['uid']] = data
        
    if MODE in ['cloud', 'dual_prov']:
        subscriber_table.put_item(Item=data)

@prov_bp.route('/subscriber', methods=['POST'])
@login_required()
def add_subscriber():
    user = request.environ['user']
    data = request.json
    
    try:
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = user['sub']
        dual_provision(data)
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber added successfully', uid=data['uid']), 201
    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error: {str(e)}'), 500

@prov_bp.route('/subscriber/<uid>', methods=['GET'])
@login_required()
def get_subscriber(uid):
    try:
        cloud_data = subscriber_table.get_item(Key={'uid': uid}).get('Item')
        if cloud_data:
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
        
@prov_bp.route('/subscriber/spml', methods=['POST'])
@login_required()
def add_spml_subscriber():
    user = request.environ['user']
    try:
        parsed_data = parse_spml_to_json(request.data)
        dual_provision(parsed_data)
        log_audit(user['sub'], 'ADD_SPML_SUBSCRIBER', parsed_data, 'SUCCESS')
        return jsonify(msg='SPML Subscriber added successfully'), 201
    except Exception as e:
        log_audit(user['sub'], 'ADD_SPML_SUBSCRIBER', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error parsing SPML: {str(e)}'), 400
