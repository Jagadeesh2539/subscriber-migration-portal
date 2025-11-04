#!/usr/bin/env python3
import json
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import uuid
import time

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, InputValidator,
    get_db_connection_params, SubscriberStatus
)

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    secrets_client = boto3.client('secretsmanager')
    
    # Environment variables
    SUBSCRIBERS_TABLE = os.environ.get('SUBSCRIBERS_TABLE')
    MIGRATION_JOBS_TABLE = os.environ.get('MIGRATION_JOBS_TABLE')
    UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')
    LEGACY_DB_SECRET_ARN = os.environ.get('LEGACY_DB_SECRET_ARN')
    LEGACY_DB_HOST = os.environ.get('LEGACY_DB_HOST')
    
    subscribers_table = dynamodb.Table(SUBSCRIBERS_TABLE) if SUBSCRIBERS_TABLE else None
    jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE) if MIGRATION_JOBS_TABLE else None
    
except Exception as e:
    print(f"AWS services initialization error: {e}")
    dynamodb = None
    s3_client = None
    secrets_client = None
    subscribers_table = None
    jobs_table = None


def lambda_handler(event, context):
    """Process audit job with consistency checks and validation"""
    try:
        job_id = event.get('jobId')
        source = event.get('source', 'dual')  # cloud, legacy, or dual
        audit_type = event.get('auditType', 'CONSISTENCY_CHECK')
        filters = event.get('filters', {})
        
        print(f"Processing audit job {job_id}: {audit_type} for {source}")
        
        if audit_type == 'CONSISTENCY_CHECK':
            return process_consistency_audit(job_id, source, filters)
        elif audit_type == 'DATA_VALIDATION':
            return process_data_validation_audit(job_id, source, filters)
        elif audit_type == 'FULL_AUDIT':
            return process_full_audit(job_id, source, filters)
        else:
            return {
                'statusCode': 400,
                'error': f'Unsupported audit type: {audit_type}',
                'auditedRecords': 0
            }
    
    except Exception as e:
        print(f"Audit processing error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'auditedRecords': 0
        }


def process_consistency_audit(job_id, source, filters):
    """Process consistency check between Cloud and Legacy systems"""
    start_time = time.time()
    
    try:
        audit_results = {
            'jobId': job_id,
            'auditType': 'CONSISTENCY_CHECK',
            'source': source,
            'startTime': datetime.utcnow().isoformat(),
            'metrics': {},
            'issues': [],
            'summary': {}
        }
        
        if source == 'cloud' or source == 'dual':
            cloud_data = get_cloud_subscribers(filters)
            audit_results['metrics']['cloudRecords'] = len(cloud_data)
        else:
            cloud_data = []
        
        if source == 'legacy' or source == 'dual':
            legacy_data = get_legacy_subscribers(filters)
            audit_results['metrics']['legacyRecords'] = len(legacy_data)
        else:
            legacy_data = []
        
        if source == 'dual':
            # Compare both systems
            comparison_result = compare_systems(cloud_data, legacy_data)
            audit_results['issues'].extend(comparison_result['issues'])
            audit_results['metrics'].update(comparison_result['metrics'])
        
        # Generate summary
        audit_results['summary'] = {
            'totalIssues': len(audit_results['issues']),
            'auditedRecords': audit_results['metrics'].get('cloudRecords', 0) + audit_results['metrics'].get('legacyRecords', 0),
            'processingTime': round(time.time() - start_time, 2),
            'status': 'COMPLETED'
        }
        
        # Upload report to S3
        report_key = upload_audit_report(job_id, audit_results)
        
        return {
            'statusCode': 200,
            'auditedRecords': audit_results['summary']['auditedRecords'],
            'totalIssues': audit_results['summary']['totalIssues'],
            'reportFileKey': report_key,
            'summary': audit_results['summary']
        }
    
    except Exception as e:
        print(f"Consistency audit failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'auditedRecords': 0
        }


def process_data_validation_audit(job_id, source, filters):
    """Process data validation audit"""
    start_time = time.time()
    
    try:
        validation_rules = filters.get('validationRules', [
            {'field': 'msisdn', 'rule': 'unique', 'pattern': r'^\+[0-9]{10,15}$'},
            {'field': 'imsi', 'rule': 'unique', 'pattern': r'^[0-9]{15}$'},
            {'field': 'email', 'rule': 'format', 'pattern': r'^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$'},
            {'field': 'status', 'rule': 'enum', 'values': SubscriberStatus.ALL}
        ])
        
        audit_results = {
            'jobId': job_id,
            'auditType': 'DATA_VALIDATION',
            'source': source,
            'startTime': datetime.utcnow().isoformat(),
            'validationRules': validation_rules,
            'issues': [],
            'metrics': {}
        }
        
        # Get data based on source
        if source == 'cloud':
            data = get_cloud_subscribers(filters)
        elif source == 'legacy':
            data = get_legacy_subscribers(filters)
        else:
            # For dual, validate both systems
            cloud_data = get_cloud_subscribers(filters)
            legacy_data = get_legacy_subscribers(filters)
            data = cloud_data + legacy_data
        
        audit_results['metrics']['totalRecords'] = len(data)
        
        # Apply validation rules
        validation_issues = apply_validation_rules(data, validation_rules)
        audit_results['issues'] = validation_issues
        audit_results['metrics']['validationIssues'] = len(validation_issues)
        
        # Generate summary
        audit_results['summary'] = {
            'totalIssues': len(validation_issues),
            'auditedRecords': len(data),
            'validRecords': len(data) - len(validation_issues),
            'processingTime': round(time.time() - start_time, 2),
            'status': 'COMPLETED'
        }
        
        # Upload report
        report_key = upload_audit_report(job_id, audit_results)
        
        return {
            'statusCode': 200,
            'auditedRecords': len(data),
            'totalIssues': len(validation_issues),
            'reportFileKey': report_key,
            'summary': audit_results['summary']
        }
    
    except Exception as e:
        print(f"Data validation audit failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'auditedRecords': 0
        }


def process_full_audit(job_id, source, filters):
    """Process comprehensive audit combining all audit types"""
    try:
        # Run consistency check
        consistency_result = process_consistency_audit(job_id, source, filters)
        
        # Run data validation
        validation_result = process_data_validation_audit(job_id, source, filters)
        
        # Combine results
        combined_results = {
            'statusCode': 200,
            'auditedRecords': consistency_result.get('auditedRecords', 0) + validation_result.get('auditedRecords', 0),
            'consistencyIssues': consistency_result.get('totalIssues', 0),
            'validationIssues': validation_result.get('totalIssues', 0),
            'totalIssues': consistency_result.get('totalIssues', 0) + validation_result.get('totalIssues', 0),
            'reports': {
                'consistencyReport': consistency_result.get('reportFileKey'),
                'validationReport': validation_result.get('reportFileKey')
            },
            'summary': {
                'auditType': 'FULL_AUDIT',
                'completedAt': datetime.utcnow().isoformat(),
                'status': 'COMPLETED'
            }
        }
        
        return combined_results
    
    except Exception as e:
        print(f"Full audit failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'auditedRecords': 0
        }


def get_cloud_subscribers(filters):
    """Get subscribers from DynamoDB (Cloud system)"""
    if not subscribers_table:
        return []
    
    try:
        # Build scan parameters
        scan_kwargs = {'Limit': 1000}  # Process in chunks
        
        # Apply filters
        if filters.get('status'):
            scan_kwargs['FilterExpression'] = '#status = :status'
            scan_kwargs['ExpressionAttributeNames'] = {'#status': 'status'}
            scan_kwargs['ExpressionAttributeValues'] = {':status': filters['status']}
        
        # Scan table
        response = subscribers_table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        # Continue scanning if more items
        while response.get('LastEvaluatedKey'):
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = subscribers_table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))
        
        return items
    
    except Exception as e:
        print(f"Failed to get cloud subscribers: {e}")
        return []


def get_legacy_subscribers(filters):
    """Get subscribers from RDS MySQL (Legacy system)"""
    if not LEGACY_DB_SECRET_ARN or not LEGACY_DB_HOST:
        return []
    
    try:
        # This would require pymysql or similar
        # For now, return empty list - in production, implement RDS query
        print("Legacy database query not implemented in this demo")
        return []
    
    except Exception as e:
        print(f"Failed to get legacy subscribers: {e}")
        return []


def compare_systems(cloud_data, legacy_data):
    """Compare data between Cloud and Legacy systems"""
    issues = []
    metrics = {
        'cloudOnly': 0,
        'legacyOnly': 0,
        'conflicts': 0,
        'matches': 0
    }
    
    # Create lookup maps
    cloud_map = {item['uid']: item for item in cloud_data}
    legacy_map = {item['uid']: item for item in legacy_data}
    
    all_uids = set(cloud_map.keys()) | set(legacy_map.keys())
    
    for uid in all_uids:
        cloud_record = cloud_map.get(uid)
        legacy_record = legacy_map.get(uid)
        
        if cloud_record and not legacy_record:
            metrics['cloudOnly'] += 1
            issues.append({
                'type': 'CLOUD_ONLY',
                'uid': uid,
                'message': 'Record exists in Cloud but not in Legacy'
            })
        
        elif legacy_record and not cloud_record:
            metrics['legacyOnly'] += 1
            issues.append({
                'type': 'LEGACY_ONLY',
                'uid': uid,
                'message': 'Record exists in Legacy but not in Cloud'
            })
        
        elif cloud_record and legacy_record:
            # Check for conflicts
            conflicts = find_field_conflicts(cloud_record, legacy_record)
            if conflicts:
                metrics['conflicts'] += 1
                issues.append({
                    'type': 'CONFLICT',
                    'uid': uid,
                    'message': f'Field conflicts: {conflicts}',
                    'conflicts': conflicts
                })
            else:
                metrics['matches'] += 1
    
    return {
        'issues': issues,
        'metrics': metrics
    }


def find_field_conflicts(cloud_record, legacy_record):
    """Find conflicts between Cloud and Legacy records"""
    conflicts = []
    
    # Fields to compare (map DynamoDB to RDS field names)
    field_mappings = {
        'msisdn': 'msisdn',
        'imsi': 'imsi',
        'status': 'status',
        'plan_id': 'plan_id',
        'email': 'email',
        'first_name': 'first_name',
        'last_name': 'last_name'
    }
    
    for cloud_field, legacy_field in field_mappings.items():
        cloud_value = str(cloud_record.get(cloud_field, '')).strip()
        legacy_value = str(legacy_record.get(legacy_field, '')).strip()
        
        if cloud_value != legacy_value:
            conflicts.append({
                'field': cloud_field,
                'cloudValue': cloud_value,
                'legacyValue': legacy_value
            })
    
    return conflicts


def apply_validation_rules(data, validation_rules):
    """Apply validation rules to data and return issues"""
    issues = []
    field_values = {}  # For uniqueness checks
    
    for rule in validation_rules:
        field = rule['field']
        rule_type = rule['rule']
        
        if rule_type == 'unique':
            field_values[field] = []
    
    # Process each record
    for record in data:
        uid = record.get('uid', 'unknown')
        
        for rule in validation_rules:
            field = rule['field']
            rule_type = rule['rule']
            value = record.get(field)
            
            if not value:  # Skip empty values
                continue
            
            if rule_type == 'unique':
                if value in field_values[field]:
                    issues.append({
                        'type': 'DUPLICATE',
                        'uid': uid,
                        'field': field,
                        'value': value,
                        'message': f'Duplicate {field}: {value}'
                    })
                else:
                    field_values[field].append(value)
            
            elif rule_type == 'format':
                import re
                pattern = rule['pattern']
                if not re.match(pattern, str(value)):
                    issues.append({
                        'type': 'FORMAT_ERROR',
                        'uid': uid,
                        'field': field,
                        'value': value,
                        'pattern': pattern,
                        'message': f'Invalid {field} format: {value}'
                    })
            
            elif rule_type == 'enum':
                allowed_values = rule['values']
                if value not in allowed_values:
                    issues.append({
                        'type': 'ENUM_ERROR',
                        'uid': uid,
                        'field': field,
                        'value': value,
                        'allowedValues': allowed_values,
                        'message': f'Invalid {field} value: {value} (allowed: {allowed_values})'
                    })
    
    return issues


def upload_audit_report(job_id, audit_results):
    """Upload audit report to S3"""
    if not s3_client or not UPLOADS_BUCKET:
        print("S3 client or bucket not available for report upload")
        return None
    
    try:
        # Generate report content
        report_content = json.dumps(audit_results, indent=2, default=str)
        
        # Upload to S3
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        report_key = f"reports/{job_id}/audit_{timestamp}.json"
        
        s3_client.put_object(
            Bucket=UPLOADS_BUCKET,
            Key=report_key,
            Body=report_content,
            ContentType='application/json',
            Metadata={
                'job-id': job_id,
                'report-type': 'audit',
                'audit-type': audit_results.get('auditType', 'unknown'),
                'total-issues': str(len(audit_results.get('issues', [])))
            }
        )
        
        print(f"Audit report uploaded: {report_key}")
        return report_key
    
    except Exception as e:
        print(f"Failed to upload audit report: {e}")
        return None


# Placeholder function for future RDS integration
def query_legacy_database(query, params=None):
    """Query legacy RDS database (placeholder for future implementation)"""
    print(f"Legacy database query: {query}")
    # In production, implement with pymysql or similar
    return []