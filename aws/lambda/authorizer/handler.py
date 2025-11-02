import json
import logging
import os
from typing import Dict, Any
from datetime import datetime

try:
    import jwt
except ImportError:
    pass

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    try:
        logger.info(f"Authorizer invoked for method: {event.get('methodArn')}")
        
        token = event.get('authorizationToken', '').replace('Bearer ', '')
        
        if not token:
            logger.warning("No token provided")
            raise Exception('Unauthorized')
        
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            logger.error("JWT_SECRET not configured")
            raise Exception('Unauthorized')
        
        try:
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            
            if payload.get('exp', 0) < datetime.utcnow().timestamp():
                logger.warning("Token expired")
                raise Exception('Unauthorized')
                
            user_context = {
                'username': payload.get('username', 'unknown'),
                'role': payload.get('role', 'guest'),
                'permissions': payload.get('permissions', []),
                'jti': payload.get('jti', ''),
                'exp': payload.get('exp', 0)
            }
            
        except Exception as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            raise Exception('Unauthorized')
        
        method_arn = event['methodArn']
        arn_parts = method_arn.split(':')
        gateway_arn = arn_parts[5].split('/')
        
        api_gateway_arn = f"arn:aws:execute-api:{arn_parts[3]}:{arn_parts[4]}:{gateway_arn[0]}"
        
        effect = "Allow"
        resource = f"{api_gateway_arn}/*/*"
        
        policy = generate_policy(
            principal_id=user_context['username'],
            effect=effect,
            resource=resource,
            context=user_context
        )
        
        logger.info(f"Authorization successful for user: {user_context['username']}")
        return policy
        
    except Exception as e:
        logger.error(f"Authorization failed: {str(e)}")
        raise Exception('Unauthorized')

def generate_policy(principal_id: str, effect: str, resource: str, context: Dict = None) -> Dict[str, Any]:
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
    
    if context:
        auth_response['context'] = {k: str(v) for k, v in context.items()}
    
    return auth_response
