#!/usr/bin/env python3
import json
import os
from datetime import datetime
import uuid

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response, InputValidator

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    dynamodb = boto3.resource('dynamodb')
    
    TABLE_NAME = os.environ.get('SUBSCRIBERS_TABLE')
    table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None
except Exception as e:
    dynamodb = None
    table = None
    print(f"DynamoDB initialization error: {e}")


def lambda_handler(event, context):
    method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    headers = event.get('headers') or {}
    origin = headers.get('origin')
    
    # Extract UID from path if present
    uid = path_params.get('uid')
    
    try:
        if method == 'GET' and uid:
            return get_subscriber(uid, origin)
        elif method == 'GET':
            return list_subscribers(query_params, origin)
        elif method == 'POST':
            body = event.get('body') or '{}'
            data = json.loads(body)
            return create_subscriber(data, origin)
        elif method == 'PUT' and uid:
            body = event.get('body') or '{}'
            data = json.loads(body)
            return update_subscriber(uid, data, origin)
        elif method == 'DELETE' and uid:
            return delete_subscriber(uid, origin)
        else:
            return create_error_response(405, 'Method not allowed', origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Internal server error: {str(e)}', origin=origin)


def get_subscriber(uid, origin=None):
    """Get a single subscriber by UID from DynamoDB"""
    if not table:
        return create_error_response(503, 'DynamoDB not available', origin=origin)
    
    try:
        response = table.get_item(Key={'uid': uid})
        item = response.get('Item')
        
        if not item:
            return create_error_response(404, f'Subscriber {uid} not found in Cloud', origin=origin)
        
        # Mask PII in response
        masked_item = mask_pii(item)
        
        return create_response(200, {
            'subscriber': masked_item,
            'source': 'cloud',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to get subscriber: {str(e)}', origin=origin)


def list_subscribers(query_params, origin=None):
    """List subscribers with filtering and pagination"""
    if not table:
        return create_error_response(503, 'DynamoDB not available', origin=origin)
    
    try:
        # Parse query parameters
        status_filter = query_params.get('status')
        plan_filter = query_params.get('planId')
        search_term = query_params.get('search', '').strip()
        limit = min(int(query_params.get('limit', 25)), 100)
        last_key = query_params.get('lastKey')
        
        # Build scan/query parameters
        scan_kwargs = {
            'Limit': limit,
        }
        
        if last_key:
            try:
                scan_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            except:
                pass  # Invalid last key, ignore
        
        # Use GSI for status filtering if available
        if status_filter and not search_term and not plan_filter:
            try:
                # Use status-index GSI if it exists
                response = table.query(
                    IndexName='status-index',
                    KeyConditionExpression=Key('status').eq(status_filter),
                    **{k: v for k, v in scan_kwargs.items() if k != 'FilterExpression'}
                )
            except:
                # Fall back to scan with filter
                scan_kwargs['FilterExpression'] = Attr('status').eq(status_filter)
                response = table.scan(**scan_kwargs)
        else:
            # Build filter expressions
            filter_expressions = []
            
            if status_filter:
                filter_expressions.append(Attr('status').eq(status_filter))
            
            if plan_filter:
                filter_expressions.append(Attr('plan_id').eq(plan_filter))
            
            if search_term:
                # Search across multiple fields
                search_filter = (
                    Attr('uid').contains(search_term) |
                    Attr('msisdn').contains(search_term) |
                    Attr('imsi').contains(search_term) |
                    Attr('email').contains(search_term) |
                    Attr('first_name').contains(search_term) |
                    Attr('last_name').contains(search_term)
                )
                filter_expressions.append(search_filter)
            
            # Combine filters
            if filter_expressions:
                combined_filter = filter_expressions[0]
                for expr in filter_expressions[1:]:
                    combined_filter = combined_filter & expr
                scan_kwargs['FilterExpression'] = combined_filter
            
            response = table.scan(**scan_kwargs)
        
        items = response.get('Items', [])
        last_evaluated_key = response.get('LastEvaluatedKey')
        
        # Mask PII in all items
        masked_items = [mask_pii(item) for item in items]
        
        # Sort by created_at descending
        masked_items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return create_response(200, {
            'subscribers': masked_items,
            'pagination': {
                'count': len(masked_items),
                'hasMore': bool(last_evaluated_key),
                'lastKey': json.dumps(last_evaluated_key) if last_evaluated_key else None
            },
            'filters': {
                'status': status_filter,
                'planId': plan_filter,
                'search': search_term
            },
            'source': 'cloud',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to list subscribers: {str(e)}', origin=origin)


def create_subscriber(data, origin=None):
    """Create a new subscriber in DynamoDB"""
    if not table:
        return create_error_response(503, 'DynamoDB not available', origin=origin)
    
    try:
        # Validate required fields
        validator = InputValidator()
        validator.require('uid', data.get('uid'))
        validator.require('msisdn', data.get('msisdn'))
        validator.require('imsi', data.get('imsi'))
        validator.validate_status(data.get('status', 'ACTIVE'))
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Build subscriber record
        now = datetime.utcnow().isoformat()
        subscriber = {
            'uid': data['uid'].strip(),
            'msisdn': data['msisdn'].strip(),
            'imsi': data['imsi'].strip(),
            'status': data.get('status', 'ACTIVE').upper(),
            'plan_id': data.get('planId', '').strip() or None,
            'email': data.get('email', '').strip() or None,
            'first_name': data.get('firstName', '').strip() or None,
            'last_name': data.get('lastName', '').strip() or None,
            'address': data.get('address', '').strip() or None,
            'date_of_birth': data.get('dateOfBirth') or None,
            'created_at': now,
            'updated_at': now,
            'last_activity': None,
        }
        
        # Check for duplicates
        existing = None
        try:
            existing_response = table.get_item(Key={'uid': subscriber['uid']})
            existing = existing_response.get('Item')
        except:
            pass
        
        if existing:
            return create_error_response(409, f'Subscriber with UID {subscriber["uid"]} already exists in Cloud', origin=origin)
        
        # Create subscriber
        table.put_item(Item=subscriber)
        
        # Mask PII in response
        masked_subscriber = mask_pii(subscriber)
        
        return create_response(201, {
            'subscriber': masked_subscriber,
            'message': 'Subscriber created successfully in Cloud',
            'source': 'cloud',
            'timestamp': now
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to create subscriber: {str(e)}', origin=origin)


def update_subscriber(uid, data, origin=None):
    """Update an existing subscriber in DynamoDB"""
    if not table:
        return create_error_response(503, 'DynamoDB not available', origin=origin)
    
    try:
        # Check if subscriber exists
        response = table.get_item(Key={'uid': uid})
        existing = response.get('Item')
        
        if not existing:
            return create_error_response(404, f'Subscriber {uid} not found in Cloud', origin=origin)
        
        # Validate update data
        validator = InputValidator()
        if 'status' in data:
            validator.validate_status(data['status'])
        
        errors = validator.get_errors()
        if errors:
            return create_error_response(400, f'Validation errors: {"; ".join(errors)}', origin=origin)
        
        # Build update expression
        update_expression = "SET updated_at = :updated_at"
        expression_values = {':updated_at': datetime.utcnow().isoformat()}
        
        # Add fields to update
        updatable_fields = ['msisdn', 'imsi', 'status', 'plan_id', 'email', 'first_name', 'last_name', 'address', 'date_of_birth']
        field_mapping = {
            'planId': 'plan_id',
            'firstName': 'first_name',
            'lastName': 'last_name',
            'dateOfBirth': 'date_of_birth'
        }
        
        for api_field, db_field in field_mapping.items():
            if api_field in data and data[api_field] is not None:
                update_expression += f", {db_field} = :{db_field}"
                expression_values[f':{db_field}'] = data[api_field].strip() if isinstance(data[api_field], str) else data[api_field]
        
        # Handle direct field names
        for field in updatable_fields:
            if field in data and data[field] is not None:
                update_expression += f", {field} = :{field}"
                expression_values[f':{field}'] = data[field].strip() if isinstance(data[field], str) else data[field]
        
        # Update item
        table.update_item(
            Key={'uid': uid},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ReturnValues='ALL_NEW'
        )
        
        # Get updated item
        updated_response = table.get_item(Key={'uid': uid})
        updated_item = updated_response.get('Item')
        
        # Mask PII in response
        masked_item = mask_pii(updated_item)
        
        return create_response(200, {
            'subscriber': masked_item,
            'message': 'Subscriber updated successfully in Cloud',
            'source': 'cloud',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to update subscriber: {str(e)}', origin=origin)


def delete_subscriber(uid, origin=None):
    """Delete a subscriber from DynamoDB"""
    if not table:
        return create_error_response(503, 'DynamoDB not available', origin=origin)
    
    try:
        # Check if subscriber exists
        response = table.get_item(Key={'uid': uid})
        existing = response.get('Item')
        
        if not existing:
            return create_error_response(404, f'Subscriber {uid} not found in Cloud', origin=origin)
        
        # Delete subscriber
        table.delete_item(Key={'uid': uid})
        
        return create_response(200, {
            'message': f'Subscriber {uid} deleted successfully from Cloud',
            'source': 'cloud',
            'timestamp': datetime.utcnow().isoformat()
        }, origin=origin)
    
    except Exception as e:
        return create_error_response(500, f'Failed to delete subscriber: {str(e)}', origin=origin)


def mask_pii(item):
    """Mask personally identifiable information in subscriber data"""
    if not item:
        return item
    
    masked = dict(item)
    
    # Mask IMSI (show only first 6 digits)
    if 'imsi' in masked and len(str(masked['imsi'])) > 6:
        imsi_str = str(masked['imsi'])
        masked['imsi'] = imsi_str[:6] + '*' * (len(imsi_str) - 6)
    
    # Mask email (show only domain)
    if 'email' in masked and '@' in str(masked['email']):
        email_parts = str(masked['email']).split('@')
        if len(email_parts) == 2:
            masked['email'] = f"***@{email_parts[1]}"
    
    return masked