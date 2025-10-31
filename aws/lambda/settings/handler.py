#!/usr/bin/env python3
import json
import os
from datetime import datetime

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response

SETTINGS_KEY = 'provisioning-mode'

# Simple in-function store fallback if table/env not available (for first deploys)
TABLE_NAME = os.environ.get('SETTINGS_TABLE')

try:
    import boto3
    ddb = boto3.resource('dynamodb') if TABLE_NAME else None
    table = ddb.Table(TABLE_NAME) if TABLE_NAME else None
except Exception:
    ddb = None
    table = None


def lambda_handler(event, context):
    method = event.get('httpMethod', 'GET')
    headers = event.get('headers') or {}
    origin = headers.get('origin')

    if method == 'GET':
        return get_mode(origin)
    elif method == 'PUT':
        try:
            body = event.get('body') or '{}'
            data = json.loads(body)
            mode = (data.get('mode') or '').upper()
            if mode not in ('CLOUD', 'LEGACY', 'DUAL_PROV'):
                return create_error_response(400, 'Invalid mode. Use CLOUD | LEGACY | DUAL_PROV', origin=origin)
            return set_mode(mode, origin)
        except Exception as e:
            return create_error_response(400, f'Bad request: {e}', origin=origin)
    else:
        return create_error_response(405, 'Method not allowed', origin=origin)


def get_mode(origin=None):
    # Default CLOUD
    mode = 'CLOUD'
    if table:
        try:
            resp = table.get_item(Key={'sk': SETTINGS_KEY})
            item = resp.get('Item')
            if item and item.get('mode'):
                mode = item['mode']
        except Exception as e:
            return create_error_response(500, f'Failed to read settings: {e}', origin=origin)
    return create_response(200, {'mode': mode, 'timestamp': datetime.utcnow().isoformat()}, origin=origin)


def set_mode(mode, origin=None):
    if table:
        try:
            table.put_item(Item={'sk': SETTINGS_KEY, 'mode': mode, 'updated_at': datetime.utcnow().isoformat()})
        except Exception as e:
            return create_error_response(500, f'Failed to write settings: {e}', origin=origin)
    return create_response(200, {'mode': mode}, origin=origin)
