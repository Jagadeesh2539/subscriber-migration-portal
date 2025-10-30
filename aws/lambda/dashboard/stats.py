#!/usr/bin/env python3
"""
Dashboard Stats Lambda Function
Provides system statistics and metrics for the dashboard
"""

import json
import sys
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
import boto3
from boto3.dynamodb.conditions import Key

# Import from Lambda layer
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, parse_lambda_event,
    DynamoDBHelper, MetricsHelper, handle_exceptions, ENV_CONFIG
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

@handle_exceptions
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Get dashboard statistics
    
    Args:
        event: API Gateway event
        context: Lambda context
    
    Returns:
        API Gateway response with dashboard stats
    """
    
    parsed_event = parse_lambda_event(event)
    origin = parsed_event['headers'].get('origin')
    
    # Extract user context from authorizer
    user_context = event.get('requestContext', {}).get('authorizer', {})
    username = user_context.get('username', 'unknown')
    
    logger.info(f"Getting dashboard stats for user: {username}")
    
    try:
        # Get statistics from various sources
        stats = {
            'timestamp': datetime.utcnow().isoformat(),
            'totalSubscribers': 0,
            'cloudSubscribers': 0,
            'legacySubscribers': 0,
            'activeSubscribers': 0,
            'inactiveSubscribers': 0,
            'recentMigrations': 0,
            'systemHealth': 'healthy',
            'provisioningMode': 'cloud',  # Default
            'lastUpdated': datetime.utcnow().isoformat()
        }
        
        # Get subscriber statistics from DynamoDB
        subscriber_stats = get_subscriber_statistics()
        stats.update(subscriber_stats)
        
        # Get migration job statistics
        migration_stats = get_migration_statistics()
        stats.update(migration_stats)
        
        # Check system health
        health_status = check_system_health()
        stats['systemHealth'] = health_status
        
        # Get provisioning mode from environment or settings
        stats['provisioningMode'] = get_provisioning_mode()
        
        # Calculate additional metrics
        stats['activePercentage'] = calculate_percentage(
            stats['activeSubscribers'], 
            stats['totalSubscribers']
        )
        
        # Put custom metrics to CloudWatch
        put_dashboard_metrics(stats)
        
        logger.info(f"Dashboard stats retrieved successfully: {stats['totalSubscribers']} subscribers")
        
        return create_response(
            status_code=200,
            body=stats,
            origin=origin
        )
        
    except Exception as e:
        logger.error(f'Dashboard stats error: {str(e)}')
        
        return create_error_response(
            status_code=500,
            message='Failed to retrieve dashboard statistics',
            error_code='STATS_ERROR',
            origin=origin
        )

def get_subscriber_statistics() -> Dict[str, int]:
    """
    Get subscriber statistics from DynamoDB
    
    Returns:
        Dictionary with subscriber counts
    """
    try:
        table_name = ENV_CONFIG['SUBSCRIBER_TABLE']
        if not table_name:
            logger.warning("Subscriber table not configured")
            return {}
        
        # Get total count
        total_response = DynamoDBHelper.scan_with_pagination(
            table_name=table_name,
            limit=1000,  # Reasonable limit for counting
            filter_expression=None
        )
        
        total_count = total_response['count']
        
        # Get counts by status
        active_response = DynamoDBHelper.scan_with_pagination(
            table_name=table_name,
            limit=1000,
            filter_expression=Key('status').eq('ACTIVE')
        )
        
        inactive_response = DynamoDBHelper.scan_with_pagination(
            table_name=table_name,
            limit=1000,
            filter_expression=Key('status').eq('INACTIVE')
        )
        
        return {
            'totalSubscribers': total_count,
            'cloudSubscribers': total_count,  # All DynamoDB subscribers are cloud
            'activeSubscribers': active_response['count'],
            'inactiveSubscribers': inactive_response['count']
        }
        
    except Exception as e:
        logger.error(f'Error getting subscriber statistics: {str(e)}')
        return {}

def get_migration_statistics() -> Dict[str, int]:
    """
    Get migration job statistics
    
    Returns:
        Dictionary with migration counts
    """
    try:
        table_name = ENV_CONFIG['MIGRATION_JOBS_TABLE']
        if not table_name:
            return {'recentMigrations': 0}
        
        # Get jobs from last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        yesterday_iso = yesterday.isoformat()
        
        # Scan for recent jobs
        response = DynamoDBHelper.scan_with_pagination(
            table_name=table_name,
            limit=100,
            filter_expression=Key('created_at').gte(yesterday_iso)
        )
        
        return {
            'recentMigrations': response['count'],
            'totalMigrationJobs': response['count']  # Could be expanded
        }
        
    except Exception as e:
        logger.error(f'Error getting migration statistics: {str(e)}')
        return {'recentMigrations': 0}

def check_system_health() -> str:
    """
    Check overall system health
    
    Returns:
        Health status string ('healthy', 'degraded', 'unhealthy')
    """
    try:
        health_checks = {
            'dynamodb': check_dynamodb_health(),
            's3': check_s3_health(),
            'secrets_manager': check_secrets_health()
        }
        
        # Determine overall health
        if all(health_checks.values()):
            return 'healthy'
        elif any(health_checks.values()):
            return 'degraded'
        else:
            return 'unhealthy'
            
    except Exception as e:
        logger.error(f'Health check error: {str(e)}')
        return 'degraded'

def check_dynamodb_health() -> bool:
    """
    Check DynamoDB health by performing a simple query
    
    Returns:
        True if healthy, False otherwise
    """
    try:
        table_name = ENV_CONFIG['SUBSCRIBER_TABLE']
        if not table_name:
            return False
        
        # Simple scan with limit 1
        DynamoDBHelper.scan_with_pagination(
            table_name=table_name,
            limit=1
        )
        
        return True
        
    except Exception as e:
        logger.error(f'DynamoDB health check failed: {str(e)}')
        return False

def check_s3_health() -> bool:
    """
    Check S3 health by listing bucket
    
    Returns:
        True if healthy, False otherwise
    """
    try:
        bucket_name = ENV_CONFIG['UPLOAD_BUCKET']
        if not bucket_name:
            return False
        
        s3_client = boto3.client('s3')
        s3_client.head_bucket(Bucket=bucket_name)
        
        return True
        
    except Exception as e:
        logger.error(f'S3 health check failed: {str(e)}')
        return False

def check_secrets_health() -> bool:
    """
    Check Secrets Manager health
    
    Returns:
        True if healthy, False otherwise
    """
    try:
        users_secret_arn = ENV_CONFIG['USERS_SECRET_ARN']
        if not users_secret_arn:
            return False
        
        secrets_client = boto3.client('secretsmanager')
        secrets_client.describe_secret(SecretId=users_secret_arn)
        
        return True
        
    except Exception as e:
        logger.error(f'Secrets Manager health check failed: {str(e)}')
        return False

def get_provisioning_mode() -> str:
    """
    Get current provisioning mode
    
    Returns:
        Provisioning mode string
    """
    # Could be extended to read from settings table
    # For now, return from environment or default
    return ENV_CONFIG.get('PROV_MODE', 'cloud')

def calculate_percentage(part: int, total: int) -> float:
    """
    Calculate percentage safely
    
    Args:
        part: Part value
        total: Total value
    
    Returns:
        Percentage as float (0-100)
    """
    if total == 0:
        return 0.0
    
    return round((part / total) * 100, 2)

def put_dashboard_metrics(stats: Dict[str, Any]):
    """
    Put dashboard metrics to CloudWatch
    
    Args:
        stats: Statistics dictionary
    """
    try:
        # Put subscriber count metrics
        MetricsHelper.put_metric(
            metric_name='TotalSubscribers',
            value=float(stats.get('totalSubscribers', 0)),
            unit='Count',
            dimensions={'Environment': ENV_CONFIG['STAGE']}
        )
        
        MetricsHelper.put_metric(
            metric_name='ActiveSubscribers',
            value=float(stats.get('activeSubscribers', 0)),
            unit='Count',
            dimensions={'Environment': ENV_CONFIG['STAGE']}
        )
        
        MetricsHelper.put_metric(
            metric_name='RecentMigrations',
            value=float(stats.get('recentMigrations', 0)),
            unit='Count',
            dimensions={'Environment': ENV_CONFIG['STAGE']}
        )
        
        # Put health metric (1 for healthy, 0.5 for degraded, 0 for unhealthy)
        health_value = {
            'healthy': 1.0,
            'degraded': 0.5,
            'unhealthy': 0.0
        }.get(stats.get('systemHealth'), 0.0)
        
        MetricsHelper.put_metric(
            metric_name='SystemHealth',
            value=health_value,
            unit='None',
            dimensions={'Environment': ENV_CONFIG['STAGE']}
        )
        
        logger.info('Dashboard metrics sent to CloudWatch successfully')
        
    except Exception as e:
        # Don't fail the main function if metrics fail
        logger.error(f'Failed to put CloudWatch metrics: {str(e)}')

def get_performance_metrics() -> Dict[str, Any]:
    """
    Get additional performance metrics
    
    Returns:
        Performance metrics dictionary
    """
    try:
        # This could be expanded to include:
        # - API response times
        # - Error rates
        # - Database performance
        # - Queue depths
        
        return {
            'apiResponseTime': 150,  # ms (mock data)
            'errorRate': 0.01,       # 1% (mock data)
            'dbQueryTime': 25        # ms (mock data)
        }
        
    except Exception as e:
        logger.error(f'Error getting performance metrics: {str(e)}')
        return {}