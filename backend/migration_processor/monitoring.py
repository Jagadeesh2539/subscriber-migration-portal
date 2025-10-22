import boto3
import json
from datetime import datetime

def log_deployment_metrics(stack_name, status, duration=None):
    """Log deployment metrics to CloudWatch"""
    try:
        cloudwatch = boto3.client('cloudwatch')
        cloudwatch.put_metric_data(
            Namespace='SubscriberMigration/Deployment',
            MetricData=[
                {
                    'MetricName': 'DeploymentStatus',
                    'Value': 1 if status == 'SUCCESS' else 0,
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'StackName', 'Value': stack_name}
                    ]
                }
            ]
        )
    except Exception as e:
        print(f"Failed to log metrics: {e}")
