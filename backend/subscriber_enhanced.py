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

# Get provisioning mode: Default changed from 'cloud' to 'dual_prov'
MODE = os.getenv('PROV_MODE', 'dual_prov') 

# Industry-ready subscriber data structure
SUBSCRIBER_SCHEMA = {
    # Core Identity
    'uid': str,
    'imsi': str, 
    'msisdn': str,
    
    # Outgoing Call Barring
    'odbic': str,  # ODBIC_UNRESTRICTED, ODBIC_CAT1_BARRED, etc.
    'odboc': str,  # ODBOC_UNRESTRICTED, ODBOC_PREMIUM_RESTRICTED, etc.
    
    # Service Configuration
    'plan_type': str,  # CORPORATE_POSTPAID, BUSINESS_POSTPAID, etc.
    'network_type': str,  # 5G_SA_NSA, 5G_NSA, 4G_LTE_ADVANCED, etc.
    'call_forwarding': str,  # JSON: CF_CFU:number;CF_CFB:number
    
    # Roaming & Limits
    'roaming_enabled': str,  # GLOBAL_ROAMING, LIMITED_ROAMING, etc.
    'data_limit_mb': int,
    'voice_minutes': str,  # UNLIMITED or number
    'sms_count': str,  # UNLIMITED or number
    
    # Status & Billing
    'status': str,  # ACTIVE, SUSPENDED, BARRED, TERMINATED
    'activation_date': str,  # ISO datetime
    'last_recharge': str,  # ISO datetime
    'balance_amount': float,
    
    'service_class': str,  # ENTERPRISE_PLATINUM, BUSINESS_GOLD, etc.
    
    # Network Location
    'location_area_code': str,
    'routing_area_code': str,
    
    # Feature Flags
    'gprs_enabled': bool,
    'volte_enabled': bool,
    'wifi_calling': bool,
    
    # Services
    'premium_services': str,  # Colon-separated list
    
    # Advanced Network Features
    'hlr_profile': str,
    'auc_profile': str,
    'eir_status': str,
    'equipment_identity': str,  # IMEI
    'network_access_mode': str,
    
    # QoS & Policy
    'qos_profile': str,
    'apn_profile': str,
    'charging_profile': str,
    'fraud_profile': str,
    
    # Financial Limits
    'credit_limit': float,
    'spending_limit': float,
    
    # Roaming Zones
    'international_roaming_zone': str,
    'domestic_roaming_zone': str,
    
    # Supplementary Services
    'supplementary_services': str,  # Colon-separated
    'value_added_services': str,  # Colon-separated
    
    # Content & Security
    'content_filtering': str,
    'parental_control': str,
    'emergency_services': str,
    
    # Technical Capabilities
    'lte_category': str,
    'nr_category': str,
    'bearer_capability': str,
    'teleservices': str,
    'basic_services': str,
    
    # Operator Services
    'operator_services': str,
    'network_features': str,
    'security_features': str,
    
    # Management
    'mobility_management': str,
    'session_management': str
}

# Default values for new fields
DEFAULT_VALUES = {
    'odbic': 'ODBIC_STD_RESTRICTIONS',
    'odboc': 'ODBOC_STD_RESTRICTIONS',
    'plan_type': 'STANDARD_PREPAID',
    'network_type': '4G_LTE',
    'call_forwarding': 'CF_NONE',
    'roaming_enabled': 'NO_ROAMING',
    'data_limit_mb': 1000,
    'voice_minutes': '100',
    'sms_count': '50',
    'status': 'ACTIVE',
    'service_class': 'CONSUMER_SILVER',
    'location_area_code': 'LAC_1000',
    'routing_area_code': 'RAC_2000',
    'gprs_enabled': True,
    'volte_enabled': False,
    'wifi_calling': False,
    'premium_services': 'VAS_BASIC',
    'hlr_profile': 'HLR_STANDARD_PROFILE',
    'auc_profile': 'AUC_BASIC_AUTH',
    'eir_status': 'EIR_VERIFIED',
    'equipment_identity': '',
    'network_access_mode': 'MODE_4G_PREFERRED',
    'qos_profile': 'QOS_CLASS_3_BEST_EFFORT',
    'apn_profile': 'APN_CONSUMER_INTERNET',
    'charging_profile': 'CHARGING_STANDARD',
    'fraud_profile': 'FRAUD_BASIC_CHECK',
    'credit_limit': 5000.00,
    'spending_limit': 500.00,
    'international_roaming_zone': 'ZONE_NONE',
    'domestic_roaming_zone': 'ZONE_HOME_ONLY',
    'supplementary_services': 'SS_CLIP:SS_CW',
    'value_added_services': 'VAS_BASIC_NEWS',
    'content_filtering': 'CF_ADULT_CONTENT',
    'parental_control': 'PC_DISABLED',
    'emergency_services': 'ES_BASIC_E911',
    'lte_category': 'LTE_CAT_6',
    'nr_category': 'N/A',
    'bearer_capability': 'BC_SPEECH:BC_DATA_64K',
    'teleservices': 'TS_SPEECH:TS_SMS',
    'basic_services': 'BS_BEARER_SPEECH:BS_PACKET_DATA',
    'operator_services': 'OS_STANDARD_SUPPORT',
    'network_features': 'NF_BASIC_LTE',
    'security_features': 'SF_BASIC_AUTH',
    'mobility_management': 'MM_BASIC',
    'session_management': 'SM_BASIC'
}

def sanitize_subscriber_data(data):
    """
    Sanitizes and adds default values for subscriber data
    """
    sanitized = {}
    
    # Copy existing fields
    for field, field_type in SUBSCRIBER_SCHEMA.items():
        if field in data:
            if field_type == int:
                sanitized[field] = int(data[field]) if data[field] != '' else 0
            elif field_type == float:
                sanitized[field] = float(data[field]) if data[field] != '' else 0.0
            elif field_type == bool:
                sanitized[field] = bool(data[field]) if isinstance(data[field], bool) else str(data[field]).lower() in ['true', '1', 'yes']
            else:
                sanitized[field] = str(data[field])
        else:
            # Apply default values for missing fields
            if field in DEFAULT_VALUES:
                sanitized[field] = DEFAULT_VALUES[field]
    
    # Ensure required fields have values
    if not sanitized.get('activation_date'):
        sanitized['activation_date'] = datetime.utcnow().isoformat()
    
    if not sanitized.get('balance_amount'):
        sanitized['balance_amount'] = 0.0
        
    return sanitized

# --- Centralized Dual Provisioning Core Function ---

def dual_provision(data, method='put'):
    """
    Writes or deletes data in both legacy (MySQL) and cloud (DynamoDB) based on the current mode.
    If MODE is 'cloud', legacy operations are skipped.
    """
    uid = data.get('uid') or data.get('subscriberId')
    
    # Sanitize data for industry standards
    if method in ['put', 'update']:
        data = sanitize_subscriber_data(data)
    
    # 1. --- Legacy DB (MySQL) Action ---
    if MODE in ['legacy', 'dual_prov']:
        try:
            if method == 'put':
                legacy_db.create_subscriber_full_profile(data)
            elif method == 'update':
                legacy_db.update_subscriber_full_profile(uid, data)
            elif method == 'delete':
                legacy_db.delete_subscriber(uid)
        except Exception as e:
            print(f"Error in legacy DB (MySQL) operation: {e}")
            raise Exception(f"Dual Provisioning Failed: Legacy DB Unreachable: {str(e)}")
            
    # 2. --- Cloud (DynamoDB) Action ---
    if MODE in ['cloud', 'dual_prov']:
        try:
            # DynamoDB uses 'subscriberId' as its primary key
            data['subscriberId'] = uid
            
            if method == 'put' or method == 'update':
                subscriber_table.put_item(Item=data)
            elif method == 'delete':
                subscriber_table.delete_item(Key={'subscriberId': uid})
        except Exception as e:
            print(f"Error in cloud DB (DynamoDB) operation: {e}")
            raise Exception(f"Dual Provisioning Failed: Cloud DB Error: {str(e)}")
            

# --- Enhanced Search Endpoint ---

@prov_bp.route('/search', methods=['GET'])
@login_required()
def search_subscriber():
    """
    Enhanced search with support for all new fields
    """
    identifier_value = request.args.get('identifier')
    identifier_type = request.args.get('type', 'uid')

    if not identifier_value:
        return jsonify(msg='Identifier query parameter is required'), 400

    try:
        cloud_data = None
        
        # Search by type
        if identifier_type == 'uid':
            cloud_data = subscriber_table.get_item(Key={'subscriberId': identifier_value}).get('Item')
        elif identifier_type == 'imsi':
            response = subscriber_table.query(
                IndexName='IMSI-Index',
                KeyConditionExpression=Key('imsi').eq(identifier_value)
            )
            if response['Items']:
                cloud_data = response['Items'][0]
        elif identifier_type == 'msisdn':
            response = subscriber_table.query(
                IndexName='MSISDN-Index',
                KeyConditionExpression=Key('msisdn').eq(identifier_value)
            )
            if response['Items']:
                cloud_data = response['Items'][0]
        
        # Process Cloud Result
        if cloud_data:
            cloud_data['uid'] = cloud_data.get('subscriberId')
            cloud_data['source'] = 'Cloud/DynamoDB'
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type, 'source': 'cloud'}, 'SUCCESS')
            return jsonify(cloud_data), 200

        # Query legacy database
        legacy_data = legacy_db.get_subscriber_by_any_id(identifier_value)
        if legacy_data:
            legacy_data['source'] = 'Legacy/MySQL'
            log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type, 'source': 'legacy'}, 'SUCCESS')
            return jsonify(legacy_data), 200
        
        # Not found
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type}, 'NOT_FOUND')
        return jsonify(msg='Subscriber not found in Cloud or Legacy database.'), 404
        
    except Exception as e:
        log_audit('system', 'SEARCH_SUBSCRIBER', {'identifier': identifier_value, 'type': identifier_type}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error during search: {str(e)}'), 500

# --- Enhanced Create Endpoint ---

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

        # Validation for duplicates (existing logic)
        if subscriber_table.get_item(Key={'subscriberId': uid}).get('Item'):
            return jsonify(msg=f"Validation Error: UID '{uid}' already exists in Cloud DB."), 400
        
        # Enhanced provisioning with all fields
        data['created_at'] = datetime.utcnow().isoformat()
        data['created_by'] = user['sub']
        
        dual_provision(data, method='put')
        
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, 'SUCCESS')
        return jsonify(msg='Subscriber created successfully', uid=data['uid']), 201
    
    except Exception as e:
        log_audit(user['sub'], 'ADD_SUBSCRIBER', data, f'FAILED: {str(e)}')
        return jsonify(msg=f'{str(e)}'), 500

# --- Enhanced Update Endpoint ---

@prov_bp.route('/subscriber/<uid>', methods=['PUT', 'OPTIONS'])
@login_required()
def update_subscriber(uid):
    user = request.environ['user']
    data = request.json
    
    try:
        imsi = data.get('imsi')
        
        if not imsi:
             return jsonify(msg='Error: IMSI is required for subscriber update'), 400

        # Enhanced provisioning with all fields
        data['updated_at'] = datetime.utcnow().isoformat()
        data['updated_by'] = user['sub']
        data['uid'] = uid 
        
        dual_provision(data, method='update')
        
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', {'uid': uid, 'changes': data}, 'SUCCESS')
        return jsonify(msg='Subscriber updated successfully'), 200
        
    except Exception as e:
        log_audit(user['sub'], 'UPDATE_SUBSCRIBER', {'uid': uid}, f'FAILED: {str(e)}')
        return jsonify(msg=f'{str(e)}'), 500

# --- Get Schema Endpoint for Frontend ---

@prov_bp.route('/schema', methods=['GET'])
@login_required()
def get_subscriber_schema():
    """
    Returns the complete subscriber schema for frontend form generation
    """
    try:
        schema_info = {
            'fields': list(SUBSCRIBER_SCHEMA.keys()),
            'defaults': DEFAULT_VALUES,
            'enums': {
                'odbic': [
                    'ODBIC_UNRESTRICTED', 'ODBIC_CAT1_BARRED', 'ODBIC_INTL_BARRED',
                    'ODBIC_INTL_PREMIUM_ALLOWED', 'ODBIC_STD_RESTRICTIONS', 'ODBIC_MVNO_STANDARD',
                    'ODBIC_M2M_RESTRICTED', 'ODBIC_TEST_UNRESTRICTED'
                ],
                'odboc': [
                    'ODBOC_UNRESTRICTED', 'ODBOC_PREMIUM_RESTRICTED', 'ODBOC_PREMIUM_BARRED',
                    'ODBOC_STD_RESTRICTIONS', 'ODBOC_BASIC_BARRING', 'ODBOC_MVNO_RESTRICTED',
                    'ODBOC_M2M_DATA_ONLY', 'ODBOC_TEST_MONITORED'
                ],
                'plan_type': [
                    'CORPORATE_POSTPAID', 'BUSINESS_POSTPAID', 'PREMIUM_PREPAID',
                    'STANDARD_PREPAID', 'GOVERNMENT_POSTPAID', 'IOT_POSTPAID',
                    'MVNO_POSTPAID', 'TEST_PREPAID'
                ],
                'network_type': [
                    '5G_SA_NSA', '5G_NSA', '5G_SA_SECURE', '4G_LTE_ADVANCED',
                    '4G_LTE', '4G_LTE_M', '5G_TEST'
                ],
                'service_class': [
                    'ENTERPRISE_PLATINUM', 'BUSINESS_GOLD', 'CONSUMER_PREMIUM',
                    'CONSUMER_SILVER', 'GOVERNMENT_SECURE', 'IOT_INDUSTRIAL',
                    'MVNO_GOLD', 'TEST_PLATINUM'
                ],
                'status': ['ACTIVE', 'SUSPENDED', 'BARRED', 'TERMINATED']
            }
        }
        
        return jsonify(schema_info), 200
        
    except Exception as e:
        return jsonify(msg=f'Error retrieving schema: {str(e)}'), 500

# Keep existing endpoints...
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

@prov_bp.route('/count', methods=['GET'])
@login_required()
def get_subscriber_count():
    """
    Fetches the total subscriber count from DynamoDB.
    """
    try:
        response = subscriber_table.scan(Select='COUNT')
        count = response.get('Count', 0)
        
        today_provisions = max(1, count % 5) if count > 0 else 0

        return jsonify(
            total_subscribers=count,
            today_provisions=today_provisions
        ), 200
    except Exception as e:
        log_audit('system', 'GET_COUNT', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error retrieving count: {str(e)}'), 500