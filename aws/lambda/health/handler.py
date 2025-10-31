#!/usr/bin/env python3
import json
import os
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import time

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import create_response, create_error_response

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    rds_client = boto3.client('rds')
    sfn_client = boto3.client('stepfunctions')
    
    # Environment variables
    SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE')
    SETTINGS_TABLE = os.environ.get('SETTINGS_TABLE')
    MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE')
    LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')
    
    subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE) if SUBSCRIBERS_TABLE else None
    settings_table = dynamodb.Table(SETTINGS_TABLE) if SETTINGS_TABLE else None
    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE) if MIGRATION_JOBS_TABLE else None
    
except Exception as e:
    print(f"AWS services initialization error: {e}")
    dynamodb = None
    rds_client = None
    sfn_client = None
    subscribers_table = None
    settings_table = None
    jobs_table = None


def lambda_handler(event, context):
    """Health check endpoint with comprehensive system validation"""
    method = event.get('httpMethod', 'GET')
    headers = event.get('headers', {})
    origin = headers.get('origin')
    
    if method != 'GET':
        return create_error_response(405, 'Method not allowed', origin=origin)
    
    start_time = time.time()
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'Subscriber Migration Portal',
        'version': '3.0.0',
        'environment': os.environ.get('STAGE', 'unknown'),
        'region': os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
        'components': {}
    }
    
    overall_healthy = True
    
    try:
        # Test DynamoDB connectivity
        dynamodb_health = test_dynamodb_health()
        health_data['components']['dynamodb'] = dynamodb_health
        if not dynamodb_health['healthy']:
            overall_healthy = False
        
        # Test RDS connectivity
        rds_health = test_rds_health()
        health_data['components']['rds'] = rds_health
        if not rds_health['healthy']:
            overall_healthy = False
        
        # Test Step Functions
        stepfunctions_health = test_stepfunctions_health()
        health_data['components']['stepfunctions'] = stepfunctions_health
        if not stepfunctions_health['healthy']:
            overall_healthy = False
        
        # Overall status
        health_data['status'] = 'healthy' if overall_healthy else 'degraded'
        health_data['responseTime'] = round((time.time() - start_time) * 1000, 2)  # ms
        
        status_code = 200 if overall_healthy else 503
        return create_response(status_code, health_data, origin=origin)
    
    except Exception as e:
        health_data['status'] = 'unhealthy'
        health_data['error'] = str(e)
        health_data['responseTime'] = round((time.time() - start_time) * 1000, 2)
        
        return create_response(503, health_data, origin=origin)


def test_dynamodb_health():
    """Test DynamoDB table connectivity and health"""
    start_time = time.time()
    
    try:
        if not subscribers_table:
            return {
                'healthy': False,
                'error': 'Subscribers table not configured',
                'responseTime': 0
            }
        
        # Test table access with describe_table
        table_response = subscribers_table.meta.client.describe_table(
            TableName=subscribers_table.table_name
        )
        
        table_status = table_response['Table']['TableStatus']
        item_count = table_response['Table'].get('ItemCount', 0)
        
        # Test read operation with limit
        scan_response = subscribers_table.scan(
            Limit=1,
            Select='COUNT'
        )
        
        response_time = round((time.time() - start_time) * 1000, 2)
        
        return {
            'healthy': table_status == 'ACTIVE',
            'status': table_status,
            'itemCount': item_count,
            'scannedCount': scan_response.get('ScannedCount', 0),
            'responseTime': response_time,
            'tables': {
                'subscribers': table_status,
                'settings': 'CONFIGURED' if settings_table else 'NOT_CONFIGURED',
                'migrationJobs': 'CONFIGURED' if jobs_table else 'NOT_CONFIGURED'
            }
        }
    
    except ClientError as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        error_code = e.response['Error']['Code']
        
        return {
            'healthy': False,
            'error': f'DynamoDB error: {error_code}',
            'errorMessage': str(e),
            'responseTime': response_time
        }
    
    except Exception as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        
        return {
            'healthy': False,
            'error': f'DynamoDB connection failed: {str(e)}',
            'responseTime': response_time
        }


def test_rds_health():
    """Test RDS connectivity and status"""
    start_time = time.time()
    
    try:
        if not LEGACY_DB_HOST or not rds_client:
            return {
                'healthy': False,
                'error': 'Legacy RDS not configured',
                'responseTime': 0
            }
        
        # Get RDS instance status
        db_instances = rds_client.describe_db_instances()
        
        legacy_instance = None
        for instance in db_instances['DBInstances']:
            if LEGACY_DB_HOST in instance['Endpoint']['Address']:
                legacy_instance = instance
                break
        
        if not legacy_instance:
            return {
                'healthy': False,
                'error': 'Legacy RDS instance not found',
                'responseTime': round((time.time() - start_time) * 1000, 2)
            }
        
        db_status = legacy_instance['DBInstanceStatus']
        response_time = round((time.time() - start_time) * 1000, 2)
        
        return {
            'healthy': db_status == 'available',
            'status': db_status,
            'engine': legacy_instance['Engine'],
            'engineVersion': legacy_instance['EngineVersion'],
            'instanceClass': legacy_instance['DBInstanceClass'],
            'allocatedStorage': legacy_instance['AllocatedStorage'],
            'multiAZ': legacy_instance['MultiAZ'],
            'endpoint': legacy_instance['Endpoint']['Address'],
            'responseTime': response_time
        }
    
    except ClientError as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        error_code = e.response['Error']['Code']
        
        return {
            'healthy': False,
            'error': f'RDS error: {error_code}',
            'errorMessage': str(e),
            'responseTime': response_time
        }
    
    except Exception as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        
        return {
            'healthy': False,
            'error': f'RDS connection failed: {str(e)}',
            'responseTime': response_time
        }


def test_stepfunctions_health():
    """Test Step Functions deployment and status"""
    start_time = time.time()
    
    try:
        if not sfn_client:
            return {
                'healthy': False,
                'error': 'Step Functions client not available',
                'responseTime': 0
            }
        
        # List state machines for this stack
        response = sfn_client.list_state_machines()
        stack_name = os.environ.get('AWS_STACK_NAME', 'subscriber-migration-portal-prod')
        
        stack_workflows = []
        workflow_status = {}
        
        for sm in response.get('stateMachines', []):
            if stack_name in sm['name']:
                stack_workflows.append(sm['name'])
                
                # Get detailed status
                try:
                    detail_response = sfn_client.describe_state_machine(
                        stateMachineArn=sm['stateMachineArn']
                    )
                    workflow_status[sm['name']] = {
                        'status': detail_response['status'],
                        'arn': sm['stateMachineArn'],
                        'type': detail_response['type'],
                        'creationDate': detail_response['creationDate'].isoformat()
                    }
                except Exception as e:
                    workflow_status[sm['name']] = {
                        'status': 'ERROR',
                        'error': str(e)
                    }
        
        response_time = round((time.time() - start_time) * 1000, 2)
        
        # Count active workflows
        active_workflows = sum(1 for status in workflow_status.values() 
                             if status.get('status') == 'ACTIVE')
        
        expected_workflows = ['migration-workflow', 'audit-workflow', 'export-workflow']
        
        return {
            'healthy': active_workflows >= 3,
            'deployedWorkflows': len(stack_workflows),
            'activeWorkflows': active_workflows,
            'expectedWorkflows': len(expected_workflows),
            'workflows': workflow_status,
            'responseTime': response_time
        }
    
    except ClientError as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        error_code = e.response['Error']['Code']
        
        return {
            'healthy': False,
            'error': f'Step Functions error: {error_code}',
            'errorMessage': str(e),
            'responseTime': response_time
        }
    
    except Exception as e:
        response_time = round((time.time() - start_time) * 1000, 2)
        
        return {
            'healthy': False,
            'error': f'Step Functions health check failed: {str(e)}',
            'responseTime': response_time
        }