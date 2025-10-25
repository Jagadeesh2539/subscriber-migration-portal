import json
import os
import logging
from datetime import datetime, timedelta
import uuid
import random
import boto3
from botocore.exceptions import ClientError
import serverless_wsgi
from app_enhanced import app

# Configure logging for AWS Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS services initialization
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
s3 = boto3.client('s3')

# Environment variables from Lambda configuration
SUBSCRIBER_TABLE = os.environ.get('SUBSCRIBER_TABLE_NAME', 'subscriber-table')
AUDIT_TABLE = os.environ.get('AUDIT_LOG_TABLE_NAME', 'audit-log-table')
MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE_NAME', 'migration-jobs-table')
MIGRATION_UPLOAD_BUCKET = os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME', 'subscriber-migration-stack-prod-migration-uploads')
LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')
STACK_NAME = os.environ.get('STACK_NAME', 'subscriber-migration-stack-prod')

class AWSIntegratedStorage:
    """Enhanced storage class that integrates with AWS services"""
    
    def __init__(self):
        try:
            # Initialize DynamoDB tables
            self.subscriber_table = dynamodb.Table(SUBSCRIBER_TABLE)
            self.audit_table = dynamodb.Table(AUDIT_TABLE)
            self.migration_jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE)
            
            logger.info(f"Initialized AWS integrated storage with tables: {SUBSCRIBER_TABLE}, {AUDIT_TABLE}, {MIGRATION_JOBS_TABLE}")
            
            # Cache for frequently accessed data
            self.cache = {
                'subscribers': {},
                'last_cache_update': datetime.min
            }
            
        except Exception as e:
            logger.error(f"Error initializing AWS storage: {str(e)}")
            # Fallback to in-memory storage for development
            self.use_fallback = True
            self._init_fallback_storage()
    
    def _init_fallback_storage(self):
        """Initialize fallback in-memory storage"""
        logger.warning("Using fallback in-memory storage")
        self.subscribers = {}
        self.migration_jobs = {}
        self.bulk_operations = {}
        self.users = {
            'admin': {'password': 'Admin@123', 'role': 'admin'},
            'operator': {'password': 'Operator@123', 'role': 'operator'},
            'guest': {'password': 'Guest@123', 'role': 'guest'}
        }
        
        # Initialize with sample data
        self._generate_sample_data()
    
    def _generate_sample_data(self):
        """Generate sample data for development/demo"""
        regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1']
        plans = ['basic', 'premium', 'enterprise']
        statuses = ['active', 'inactive', 'suspended']
        
        for i in range(100):  # Reduced for Lambda cold start performance
            subscriber_id = f"SUB_{str(i+1).zfill(6)}"
            self.subscribers[subscriber_id] = {
                'subscriber_id': subscriber_id,
                'name': f'User {i+1}',
                'email': f'user{i+1}@example.com',
                'phone': f'+1-555-{str(i+1).zfill(4)}',
                'plan': random.choice(plans),
                'status': random.choice(statuses),
                'region': random.choice(regions),
                'system': random.choice(['cloud', 'legacy']),
                'created_date': (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
                'last_updated': (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat()
            }
    
    def get_subscribers(self, filters=None):
        """Get subscribers with optional filtering"""
        try:
            if hasattr(self, 'use_fallback'):
                return list(self.subscribers.values())
            
            # Use DynamoDB scan with filters
            response = self.subscriber_table.scan()
            return response.get('Items', [])
            
        except Exception as e:
            logger.error(f"Error getting subscribers: {str(e)}")
            return []
    
    def create_subscriber(self, subscriber_data):
        """Create new subscriber"""
        try:
            if hasattr(self, 'use_fallback'):
                self.subscribers[subscriber_data['subscriber_id']] = subscriber_data
                return subscriber_data
            
            # Store in DynamoDB
            self.subscriber_table.put_item(Item=subscriber_data)
            return subscriber_data
            
        except Exception as e:
            logger.error(f"Error creating subscriber: {str(e)}")
            raise
    
    def update_subscriber(self, subscriber_id, updates):
        """Update existing subscriber"""
        try:
            if hasattr(self, 'use_fallback'):
                if subscriber_id in self.subscribers:
                    self.subscribers[subscriber_id].update(updates)
                    return self.subscribers[subscriber_id]
                return None
            
            # Update in DynamoDB
            response = self.subscriber_table.update_item(
                Key={'subscriber_id': subscriber_id},
                UpdateExpression='SET ' + ', '.join([f'{k} = :{k}' for k in updates.keys()]),
                ExpressionAttributeValues={f':{k}': v for k, v in updates.items()},
                ReturnValues='ALL_NEW'
            )
            return response.get('Attributes')
            
        except Exception as e:
            logger.error(f"Error updating subscriber: {str(e)}")
            raise
    
    def delete_subscriber(self, subscriber_id):
        """Delete subscriber"""
        try:
            if hasattr(self, 'use_fallback'):
                return self.subscribers.pop(subscriber_id, None)
            
            # Delete from DynamoDB
            response = self.subscriber_table.delete_item(
                Key={'subscriber_id': subscriber_id},
                ReturnValues='ALL_OLD'
            )
            return response.get('Attributes')
            
        except Exception as e:
            logger.error(f"Error deleting subscriber: {str(e)}")
            raise
    
    def get_migration_jobs(self, filters=None):
        """Get migration jobs"""
        try:
            if hasattr(self, 'use_fallback'):
                if not hasattr(self, 'migration_jobs'):
                    self.migration_jobs = {}
                return list(self.migration_jobs.values())
            
            # Get from DynamoDB
            response = self.migration_jobs_table.scan()
            return response.get('Items', [])
            
        except Exception as e:
            logger.error(f"Error getting migration jobs: {str(e)}")
            return []
    
    def create_migration_job(self, job_data):
        """Create migration job"""
        try:
            if hasattr(self, 'use_fallback'):
                if not hasattr(self, 'migration_jobs'):
                    self.migration_jobs = {}
                self.migration_jobs[job_data['job_id']] = job_data
                return job_data
            
            # Store in DynamoDB
            self.migration_jobs_table.put_item(Item=job_data)
            return job_data
            
        except Exception as e:
            logger.error(f"Error creating migration job: {str(e)}")
            raise
    
    def update_migration_job(self, job_id, updates):
        """Update migration job"""
        try:
            if hasattr(self, 'use_fallback'):
                if hasattr(self, 'migration_jobs') and job_id in self.migration_jobs:
                    self.migration_jobs[job_id].update(updates)
                    return self.migration_jobs[job_id]
                return None
            
            # Update in DynamoDB
            response = self.migration_jobs_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression='SET ' + ', '.join([f'{k} = :{k}' for k in updates.keys()]),
                ExpressionAttributeValues={f':{k}': v for k, v in updates.items()},
                ReturnValues='ALL_NEW'
            )
            return response.get('Attributes')
            
        except Exception as e:
            logger.error(f"Error updating migration job: {str(e)}")
            raise

# Initialize AWS-integrated storage
aws_storage = AWSIntegratedStorage()

# Override the app's storage with AWS-integrated version
app.config['storage'] = aws_storage

def lambda_handler(event, context):
    """
    AWS Lambda handler for the enhanced subscriber migration portal
    """
    try:
        logger.info(f"Processing request: {event.get('httpMethod', 'UNKNOWN')} {event.get('path', 'UNKNOWN')}")
        
        # Add CORS headers for all responses
        def add_cors_headers(response):
            if 'headers' not in response:
                response['headers'] = {}
            response['headers'].update({
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
                'Access-Control-Allow-Credentials': 'false'
            })
            return response
        
        # Handle OPTIONS requests for CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return add_cors_headers({
                'statusCode': 200,
                'body': ''
            })
        
        # Process the request through serverless WSGI
        response = serverless_wsgi.handle_request(app, event, context)
        
        # Add CORS headers to the response
        response = add_cors_headers(response)
        
        logger.info(f"Request processed successfully: {response.get('statusCode', 'UNKNOWN')}")
        return response
        
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        return add_cors_headers({
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            })
        })

# Health check specifically for Lambda
def lambda_health_check():
    """Health check for AWS Lambda environment"""
    try:
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0-enhanced',
            'environment': 'aws-lambda',
            'tables': {
                'subscriber_table': SUBSCRIBER_TABLE,
                'audit_table': AUDIT_TABLE,
                'migration_jobs_table': MIGRATION_JOBS_TABLE
            },
            'buckets': {
                'migration_upload_bucket': MIGRATION_UPLOAD_BUCKET
            }
        }
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }