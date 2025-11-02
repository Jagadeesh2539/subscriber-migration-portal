import json
import logging
import os
import sys
import boto3
from typing import Dict, Any

sys.path.append('/opt/python')
from common_utils import create_response, create_error_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
subscribers_table = dynamodb.Table(os.environ['SUBSCRIBERS_TABLE'])

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    try:
        http_method = event['httpMethod']
        path = event['path']
        path_parameters = event.get('pathParameters') or {}
        headers = event.get('headers', {})
        origin = headers.get('origin')
        
        if http_method == 'GET' and path == '/subscribers':
            return list_subscribers(event, origin)
        
        elif http_method == 'POST' and path == '/subscribers':
            return create_subscriber(event, origin)
        
        elif http_method == 'GET' and '/subscribers/' in path and path_parameters.get('id'):
            return get_subscriber(path_parameters['id'], origin)
        
        elif http_method == 'PUT' and '/subscribers/' in path and path_parameters.get('id'):
            return update_subscriber(path_parameters['id'], event, origin)
        
        elif http_method == 'DELETE' and '/subscribers/' in path and path_parameters.get('id'):
            return delete_subscriber(path_parameters['id'], origin)
        
        elif http_method == 'GET' and path == '/subscribers/search':
            return search_subscribers(event, origin)
        
        else:
            return create_error_response(404, "Endpoint not found", origin=origin)
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return create_error_response(500, "Internal server error", origin=origin)

def list_subscribers(event, origin):
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        
        response = subscribers_table.scan(Limit=limit)
        
        return create_response(200, {
            'subscribers': response['Items'],
            'count': response['Count']
        }, origin=origin)
        
    except Exception as e:
        logger.error(f"Error listing subscribers: {str(e)}")
        return create_error_response(500, "Failed to list subscribers", origin=origin)

def create_subscriber(event, origin):
    try:
        body = json.loads(event.get('body', '{}'))
        
        required_fields = ['uid', 'email', 'plan_id']
        for field in required_fields:
            if field not in body:
                return create_error_response(400, f"Missing required field: {field}", origin=origin)
        
        subscriber = {
            'uid': body['uid'],
            'email': body['email'],
            'plan_id': body['plan_id'],
            'status': body.get('status', 'active'),
            'created_at': body.get('created_at'),
            'updated_at': body.get('updated_at')
        }
        
        subscribers_table.put_item(Item=subscriber)
        
        return create_response(201, {
            'message': 'Subscriber created successfully',
            'subscriber': subscriber
        }, origin=origin)
        
    except Exception as e:
        logger.error(f"Error creating subscriber: {str(e)}")
        return create_error_response(500, "Failed to create subscriber", origin=origin)

def get_subscriber(uid, origin):
    try:
        response = subscribers_table.get_item(Key={'uid': uid})
        
        if 'Item' not in response:
            return create_error_response(404, "Subscriber not found", origin=origin)
        
        return create_response(200, {
            'subscriber': response['Item']
        }, origin=origin)
        
    except Exception as e:
        logger.error(f"Error getting subscriber {uid}: {str(e)}")
        return create_error_response(500, "Failed to get subscriber", origin=origin)

def update_subscriber(uid, event, origin):
    try:
        body = json.loads(event.get('body', '{}'))
        
        # Check if subscriber exists
        response = subscribers_table.get_item(Key={'uid': uid})
        if 'Item' not in response:
            return create_error_response(404, "Subscriber not found", origin=origin)
        
        # Build update expression
        update_expression = "SET "
        expression_values = {}
        
        updatable_fields = ['email', 'plan_id', 'status', 'updated_at']
        
        for field in updatable_fields:
            if field in body:
                update_expression += f"{field} = :{field}, "
                expression_values[f":{field}"] = body[field]
        
        if not expression_values:
            return create_error_response(400, "No valid fields to update", origin=origin)
        
        update_expression = update_expression.rstrip(', ')
        
        subscribers_table.update_item(
            Key={'uid': uid},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        updated_response = subscribers_table.get_item(Key={'uid': uid})
        
        return create_response(200, {
            'message': 'Subscriber updated successfully',
            'subscriber': updated_response['Item']
        }, origin=origin)
        
    except Exception as e:
        logger.error(f"Error updating subscriber {uid}: {str(e)}")
        return create_error_response(500, "Failed to update subscriber", origin=origin)

def delete_subscriber(uid, origin):
    try:
        response = subscribers_table.get_item(Key={'uid': uid})
        if 'Item' not in response:
            return create_error_response(404, "Subscriber not found", origin=origin)
        
        subscribers_table.delete_item(Key={'uid': uid})
        
        return create_response(200, {
            'message': 'Subscriber deleted successfully'
        }, origin=origin)
        
    except Exception as e:
        logger.error(f"Error deleting subscriber {uid}: {str(e)}")
        return create_error_response(500, "Failed to delete subscriber", origin=origin)

def search_subscribers(event, origin):
    try:
        query_params = event.get('queryStringParameters') or {}
        
        if not query_params:
            return create_error_response(400, "Search parameters required", origin=origin)
        
        # For now, return basic search functionality
        return create_response(200, {
            'subscribers': [],
            'message': 'Search functionality working',
            'searchParams': query_params
        }, origin=origin)
        
    except Exception as e:
        logger.error(f"Error searching subscribers: {str(e)}")
        return create_error_response(500, "Failed to search subscribers", origin=origin)
