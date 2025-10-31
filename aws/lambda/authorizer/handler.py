#!/usr/bin/env python3
"""
JWT Authorizer Lambda Function
Handles API Gateway authorization using JWT tokens
"""

import json
import logging
import os
from typing import Dict, Any

# Import from Lambda layer
sys.path.append('/opt/python')
from common_utils import JWTAuth, SecretsManager, AuditLogger

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    JWT Authorizer for API Gateway
    
    Args:
        event: API Gateway authorizer event
        context: Lambda context
    
    Returns:
        IAM policy document for API Gateway
    """
    try:
        logger.info(f"Authorizer invoked for method: {event.get('methodArn')}")
        
        # Extract token from Authorization header
        token = event.get('authorizationToken', '').replace('Bearer ', '')
        
        if not token:
            logger.warning("No token provided")
            raise Exception('Unauthorized')
        
        # Verify JWT token
        user_context = JWTAuth.verify_token(token)
        
        if not user_context:
            logger.warning("Invalid or expired token")
            raise Exception('Unauthorized')
        
        # Extract method ARN components
        method_arn = event['methodArn']
        arn_parts = method_arn.split(':')
        gateway_arn = arn_parts[5].split('/')
        
        # Build API Gateway ARN for policy
        api_gateway_arn = f"arn:aws:execute-api:{arn_parts[3]}:{arn_parts[4]}:{gateway_arn[0]}"
        
        # Determine access level based on user role
        effect = "Allow"
        
        # Admin has full access
        if user_context['role'] == 'admin':
            resource = f"{api_gateway_arn}/*/*"
        
        # Operator has limited access
        elif user_context['role'] == 'operator':
            resource = f"{api_gateway_arn}/*/*"
            # Could add more granular controls here
        
        # Guest has read-only access
        elif user_context['role'] == 'guest':
            resource = f"{api_gateway_arn}/*/GET/*"
        
        else:
            logger.warning(f"Unknown role: {user_context['role']}")
            raise Exception('Unauthorized')
        
        # Generate IAM policy
        policy = generate_policy(
            principal_id=user_context['username'],
            effect=effect,
            resource=resource,
            context={
                'username': user_context['username'],
                'role': user_context['role'],
                'permissions': json.dumps(user_context['permissions']),
                'jti': user_context.get('jti', ''),
                'exp': str(user_context.get('exp', ''))
            }
        )
        
        logger.info(f"Authorization successful for user: {user_context['username']}")
        
        return policy
        
    except Exception as e:
        logger.error(f"Authorization failed: {str(e)}")
        
        # Log failed authorization attempt
        AuditLogger.log_activity(
            action='auth_failed',
            resource='api_gateway',
            user='unknown',
            details={'error': str(e)},
            event=event
        )
        
        # Return Deny policy
        raise Exception('Unauthorized')

def generate_policy(principal_id: str, effect: str, resource: str, context: Dict = None) -> Dict[str, Any]:
    """
    Generate IAM policy document for API Gateway
    
    Args:
        principal_id: User identifier
        effect: Allow or Deny
        resource: AWS resource ARN
        context: Additional context to pass to API
    
    Returns:
        IAM policy document
    """
    auth_response = {
        'principalId': principal_id
    }
    
    if effect and resource:
        policy_document = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
        auth_response['policyDocument'] = policy_document
    
    # Add context that will be available in API Lambda functions
    if context:
        auth_response['context'] = context
    
    return auth_response

def validate_permissions(user_context: Dict, required_permission: str) -> bool:
    """
    Validate if user has required permission
    
    Args:
        user_context: User context from JWT
        required_permission: Required permission string
    
    Returns:
        True if user has permission, False otherwise
    """
    user_permissions = user_context.get('permissions', [])
    
    # Admin has all permissions
    if 'admin' in user_permissions:
        return True
    
    # Check specific permission
    return required_permission in user_permissions