#!/usr/bin/env python3
"""
Get Subscribers Lambda Function
Handles listing and searching subscribers with pagination
"""

import json
import sys
import logging
from typing import Dict, Any, Optional
from boto3.dynamodb.conditions import Key, Attr
import boto3

# Import from Lambda layer
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, parse_lambda_event,
    InputValidator, DynamoDBHelper, AuditLogger, handle_exceptions, 
    ENV_CONFIG, JWTAuth
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

@handle_exceptions
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Get subscribers with pagination and filtering
    
    Args:
        event: API Gateway event
        context: Lambda context
    
    Returns:
        API Gateway response with subscriber list
    """
    
    parsed_event = parse_lambda_event(event)
    origin = parsed_event['headers'].get('origin')
    
    # Extract user context from authorizer
    user_context = event.get('requestContext', {}).get('authorizer', {})
    username = user_context.get('username', 'unknown')
    permissions = json.loads(user_context.get('permissions', '[]'))
    
    # Check read permission
    if 'read' not in permissions and 'admin' not in permissions:
        return create_error_response(
            status_code=403,
            message='Insufficient permissions to read subscribers',
            error_code='PERMISSION_DENIED',
            origin=origin
        )
    
    logger.info(f"Getting subscribers for user: {username}")
    
    try:
        # Parse query parameters
        query_params = parsed_event['query_parameters']
        
        # Pagination parameters
        limit, offset = InputValidator.validate_pagination(
            query_params.get('limit'),
            query_params.get('offset')
        )
        
        # Search parameters
        search_query = query_params.get('search', '').strip()
        status_filter = query_params.get('status', '').strip().upper()
        plan_filter = query_params.get('plan_id', '').strip()
        sort_by = query_params.get('sort_by', 'created_at')
        sort_order = query_params.get('sort_order', 'desc').lower()
        
        # Last evaluated key for pagination
        last_key = None
        if query_params.get('last_key'):
            try:
                last_key = json.loads(query_params['last_key'])
            except (json.JSONDecodeError, ValueError):
                logger.warning("Invalid last_key parameter")
        
        # Get subscribers from DynamoDB
        if search_query:
            # Search across multiple fields
            result = search_subscribers(
                search_query=search_query,
                status_filter=status_filter,
                plan_filter=plan_filter,
                limit=limit,
                last_key=last_key
            )
        else:
            # Regular listing with optional filters
            result = list_subscribers(
                status_filter=status_filter,
                plan_filter=plan_filter,
                limit=limit,
                last_key=last_key,
                sort_by=sort_by,
                sort_order=sort_order
            )
        
        # Format response
        response_data = {
            'subscribers': result['items'],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'count': len(result['items']),
                'total_scanned': result.get('scanned_count', 0),
                'has_more': result['last_key'] is not None,
                'last_key': json.dumps(result['last_key']) if result['last_key'] else None
            },
            'filters': {
                'search': search_query,
                'status': status_filter,
                'plan_id': plan_filter,
                'sort_by': sort_by,
                'sort_order': sort_order
            },
            'timestamp': result.get('timestamp')
        }
        
        # Log the operation
        AuditLogger.log_activity(
            action='subscribers_listed',
            resource='subscribers',
            user=username,
            details={
                'count': len(result['items']),
                'filters': response_data['filters']
            },
            event=event
        )
        
        logger.info(f"Retrieved {len(result['items'])} subscribers for user: {username}")
        
        return create_response(
            status_code=200,
            body=response_data,
            origin=origin
        )
        
    except ValueError as e:
        return create_error_response(
            status_code=400,
            message=str(e),
            error_code='VALIDATION_ERROR',
            origin=origin
        )
    except Exception as e:
        logger.error(f'Error getting subscribers: {str(e)}')
        
        return create_error_response(
            status_code=500,
            message='Failed to retrieve subscribers',
            error_code='RETRIEVAL_ERROR',
            origin=origin
        )

def list_subscribers(
    status_filter: str = None,
    plan_filter: str = None,
    limit: int = 50,
    last_key: Dict = None,
    sort_by: str = 'created_at',
    sort_order: str = 'desc'
) -> Dict[str, Any]:
    """
    List subscribers with optional filters
    
    Args:
        status_filter: Filter by subscriber status
        plan_filter: Filter by plan ID
        limit: Maximum number of items to return
        last_key: Last evaluated key for pagination
        sort_by: Field to sort by
        sort_order: Sort order (asc/desc)
    
    Returns:
        Dictionary with subscribers and pagination info
    """
    table_name = ENV_CONFIG['SUBSCRIBER_TABLE']
    
    # Build filter expression
    filter_expressions = []
    
    if status_filter and status_filter in ['ACTIVE', 'INACTIVE', 'SUSPENDED', 'DELETED']:
        filter_expressions.append(Attr('status').eq(status_filter))
    
    if plan_filter:
        filter_expressions.append(Attr('plan_id').eq(plan_filter))
    
    # Combine filter expressions
    filter_expression = None
    if filter_expressions:
        filter_expression = filter_expressions[0]
        for expr in filter_expressions[1:]:
            filter_expression = filter_expression & expr
    
    # Use index if filtering by status
    index_name = None
    if status_filter and not plan_filter:
        index_name = 'status-index'
        
        # Query using GSI
        result = DynamoDBHelper.query_with_pagination(
            table_name=table_name,
            key_condition_expression=Key('status').eq(status_filter),
            limit=limit,
            last_key=last_key,
            index_name=index_name,
            ScanIndexForward=(sort_order == 'asc')
        )
    else:
        # Full table scan with filter
        result = DynamoDBHelper.scan_with_pagination(
            table_name=table_name,
            limit=limit,
            last_key=last_key,
            filter_expression=filter_expression
        )
    
    # Format subscriber data
    formatted_items = []
    for item in result['items']:
        formatted_items.append(format_subscriber_response(item))
    
    return {
        'items': formatted_items,
        'last_key': result['last_key'],
        'count': result['count'],
        'scanned_count': result.get('scanned_count', 0),
        'timestamp': boto3.client('sts').get_caller_identity().get('Account')
    }

def search_subscribers(
    search_query: str,
    status_filter: str = None,
    plan_filter: str = None,
    limit: int = 50,
    last_key: Dict = None
) -> Dict[str, Any]:
    """
    Search subscribers across multiple fields
    
    Args:
        search_query: Search term
        status_filter: Filter by status
        plan_filter: Filter by plan
        limit: Maximum results
        last_key: Pagination key
    
    Returns:
        Search results with pagination
    """
    table_name = ENV_CONFIG['SUBSCRIBER_TABLE']
    
    # Build search filter expressions
    search_expressions = []
    
    # Search in multiple fields
    search_fields = ['uid', 'msisdn', 'imsi', 'email', 'first_name', 'last_name']
    
    for field in search_fields:
        # Contains search (case-insensitive would require application-level filtering)
        search_expressions.append(Attr(field).contains(search_query))
    
    # Combine search expressions with OR
    search_filter = search_expressions[0]
    for expr in search_expressions[1:]:
        search_filter = search_filter | expr
    
    # Add additional filters
    filter_expressions = [search_filter]
    
    if status_filter and status_filter in ['ACTIVE', 'INACTIVE', 'SUSPENDED', 'DELETED']:
        filter_expressions.append(Attr('status').eq(status_filter))
    
    if plan_filter:
        filter_expressions.append(Attr('plan_id').eq(plan_filter))
    
    # Combine all filters with AND
    final_filter = filter_expressions[0]
    for expr in filter_expressions[1:]:
        final_filter = final_filter & expr
    
    # Perform scan with search filter
    result = DynamoDBHelper.scan_with_pagination(
        table_name=table_name,
        limit=limit * 2,  # Scan more to account for filtering
        last_key=last_key,
        filter_expression=final_filter
    )
    
    # Format and limit results
    formatted_items = []
    for item in result['items'][:limit]:  # Ensure we don't exceed limit
        formatted_items.append(format_subscriber_response(item))
    
    return {
        'items': formatted_items,
        'last_key': result['last_key'] if len(result['items']) > limit else None,
        'count': len(formatted_items),
        'scanned_count': result.get('scanned_count', 0),
        'timestamp': boto3.client('sts').get_caller_identity().get('Account')
    }

def format_subscriber_response(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format subscriber data for API response
    
    Args:
        item: Raw DynamoDB item
    
    Returns:
        Formatted subscriber data
    """
    # Remove sensitive or internal fields
    formatted = {
        'uid': item.get('uid'),
        'msisdn': item.get('msisdn'),
        'imsi': mask_sensitive_data(item.get('imsi')),  # Mask IMSI for security
        'status': item.get('status'),
        'plan_id': item.get('plan_id'),
        'created_at': item.get('created_at'),
        'updated_at': item.get('updated_at'),
        'last_activity': item.get('last_activity')
    }
    
    # Add optional fields if they exist
    optional_fields = ['email', 'first_name', 'last_name', 'date_of_birth', 'address']
    for field in optional_fields:
        if field in item:
            if field == 'email':
                formatted[field] = mask_email(item[field])
            else:
                formatted[field] = item[field]
    
    # Add computed fields
    formatted['is_active'] = item.get('status') == 'ACTIVE'
    formatted['account_age_days'] = calculate_account_age(item.get('created_at'))
    
    return formatted

def mask_sensitive_data(data: str, visible_chars: int = 3) -> str:
    """
    Mask sensitive data for display
    
    Args:
        data: Data to mask
        visible_chars: Number of characters to show
    
    Returns:
        Masked data string
    """
    if not data or len(data) <= visible_chars * 2:
        return '*' * len(data) if data else ''
    
    return data[:visible_chars] + '*' * (len(data) - visible_chars * 2) + data[-visible_chars:]

def mask_email(email: str) -> str:
    """
    Mask email address
    
    Args:
        email: Email address to mask
    
    Returns:
        Masked email address
    """
    if not email or '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    
    if len(local) <= 2:
        masked_local = '*' * len(local)
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
    
    return f"{masked_local}@{domain}"

def calculate_account_age(created_at: str) -> Optional[int]:
    """
    Calculate account age in days
    
    Args:
        created_at: Creation timestamp
    
    Returns:
        Age in days or None if invalid
    """
    try:
        from datetime import datetime
        
        if not created_at:
            return None
        
        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        age = (datetime.now(created_date.tzinfo) - created_date).days
        
        return max(0, age)
        
    except (ValueError, AttributeError):
        return None