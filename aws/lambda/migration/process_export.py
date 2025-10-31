#!/usr/bin/env python3
import json
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import csv
from io import StringIO
import uuid
time

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import (
    create_response, create_error_response, InputValidator,
    format_subscriber_for_api, SubscriberStatus
)

try:
    # AWS service clients
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    
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
    subscribers_table = None
    jobs_table = None


def lambda_handler(event, context):
    """Process export job with data extraction and formatting"""
    try:
        job_id = event.get('jobId')
        source = event.get('source', 'cloud')  # cloud, legacy, or dual
        export_scope = event.get('exportScope', 'BOTH_SYSTEMS')
        format_type = event.get('format', 'CSV')
        filters = event.get('filters', {})
        mask_pii = event.get('maskPii', True)
        temp_export = event.get('tempExport', False)
        
        print(f"Processing export job {job_id}: {export_scope} in {format_type} format")
        
        if export_scope == 'CLOUD_ONLY' or source == 'cloud':
            return process_cloud_export(job_id, format_type, filters, mask_pii, temp_export)
        elif export_scope == 'LEGACY_ONLY' or source == 'legacy':
            return process_legacy_export(job_id, format_type, filters, mask_pii, temp_export)
        elif export_scope == 'BOTH_SYSTEMS':
            return process_merged_export(job_id, format_type, filters, mask_pii)
        elif export_scope == 'COMPARISON':
            return process_comparison_export(job_id, format_type, filters, mask_pii)
        else:
            return {
                'statusCode': 400,
                'error': f'Unsupported export scope: {export_scope}',
                'exportedRecords': 0
            }
    
    except Exception as e:
        print(f"Export processing error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'exportedRecords': 0
        }


def process_cloud_export(job_id, format_type, filters, mask_pii, temp_export=False):
    """Export data from Cloud (DynamoDB) system"""
    try:
        # Get data from DynamoDB
        data = get_cloud_subscribers(filters)
        
        if not data:
            return {
                'statusCode': 200,
                'exportedRecords': 0,
                'message': 'No records found matching filters',
                'outputFileKey': None
            }
        
        # Format data for export
        export_data = []
        for item in data:
            formatted_item = format_subscriber_for_api(item, mask_pii=mask_pii)
            if not temp_export:  # Add system source for final export
                formatted_item['dataSource'] = 'cloud'
            export_data.append(formatted_item)
        
        # Generate export file
        if temp_export:
            # Return data for merging (don't upload to S3 yet)
            return {
                'statusCode': 200,
                'exportedRecords': len(export_data),
                'data': export_data,
                'source': 'cloud'
            }
        else:
            # Upload final export to S3
            output_file_key = upload_export_file(job_id, export_data, format_type, 'cloud')
            download_url = generate_download_url(output_file_key) if output_file_key else None
            
            return {
                'statusCode': 200,
                'exportedRecords': len(export_data),
                'outputFileKey': output_file_key,
                'downloadUrl': download_url
            }
    
    except Exception as e:
        print(f"Cloud export failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'exportedRecords': 0
        }


def process_legacy_export(job_id, format_type, filters, mask_pii, temp_export=False):
    """Export data from Legacy (RDS) system"""
    try:
        # Get data from RDS (placeholder - implement with pymysql)
        data = get_legacy_subscribers(filters)
        
        if not data:
            return {
                'statusCode': 200,
                'exportedRecords': 0,
                'message': 'No records found in legacy system',
                'outputFileKey': None
            }
        
        # Format data for export
        export_data = []
        for item in data:
            formatted_item = format_subscriber_for_api(item, mask_pii=mask_pii)
            if not temp_export:
                formatted_item['dataSource'] = 'legacy'
            export_data.append(formatted_item)
        
        if temp_export:
            return {
                'statusCode': 200,
                'exportedRecords': len(export_data),
                'data': export_data,
                'source': 'legacy'
            }
        else:
            output_file_key = upload_export_file(job_id, export_data, format_type, 'legacy')
            download_url = generate_download_url(output_file_key) if output_file_key else None
            
            return {
                'statusCode': 200,
                'exportedRecords': len(export_data),
                'outputFileKey': output_file_key,
                'downloadUrl': download_url
            }
    
    except Exception as e:
        print(f"Legacy export failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'exportedRecords': 0
        }


def process_merged_export(job_id, format_type, filters, mask_pii):
    """Export merged data from both Cloud and Legacy systems"""
    try:
        # Get data from both systems
        cloud_data = get_cloud_subscribers(filters)
        legacy_data = get_legacy_subscribers(filters)
        
        # Merge and deduplicate
        merged_data = merge_subscriber_data(cloud_data, legacy_data, mask_pii)
        
        if not merged_data:
            return {
                'statusCode': 200,
                'exportedRecords': 0,
                'message': 'No records found in either system',
                'outputFileKey': None
            }
        
        # Upload merged export
        output_file_key = upload_export_file(job_id, merged_data, format_type, 'merged')
        download_url = generate_download_url(output_file_key) if output_file_key else None
        
        return {
            'statusCode': 200,
            'exportedRecords': len(merged_data),
            'cloudRecords': len(cloud_data),
            'legacyRecords': len(legacy_data),
            'outputFileKey': output_file_key,
            'downloadUrl': download_url
        }
    
    except Exception as e:
        print(f"Merged export failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'exportedRecords': 0
        }


def process_comparison_export(job_id, format_type, filters, mask_pii):
    """Export comparison data showing differences between systems"""
    try:
        # Get data from both systems
        cloud_data = get_cloud_subscribers(filters)
        legacy_data = get_legacy_subscribers(filters)
        
        # Generate comparison report
        comparison_data = generate_comparison_data(cloud_data, legacy_data, mask_pii)
        
        if not comparison_data:
            return {
                'statusCode': 200,
                'exportedRecords': 0,
                'message': 'No comparison data available',
                'outputFileKey': None
            }
        
        # Upload comparison export
        output_file_key = upload_export_file(job_id, comparison_data, format_type, 'comparison')
        download_url = generate_download_url(output_file_key) if output_file_key else None
        
        return {
            'statusCode': 200,
            'exportedRecords': len(comparison_data),
            'outputFileKey': output_file_key,
            'downloadUrl': download_url
        }
    
    except Exception as e:
        print(f"Comparison export failed: {e}")
        return {
            'statusCode': 500,
            'error': str(e),
            'exportedRecords': 0
        }


def get_cloud_subscribers(filters):
    """Get subscribers from DynamoDB with filters"""
    if not subscribers_table:
        return []
    
    try:
        scan_kwargs = {'Limit': 1000}
        
        # Apply filters
        filter_expressions = []
        expression_values = {}
        expression_names = {}
        
        if filters.get('status'):
            filter_expressions.append('#status = :status')
            expression_names['#status'] = 'status'
            expression_values[':status'] = filters['status']
        
        if filters.get('planId'):
            filter_expressions.append('plan_id = :plan_id')
            expression_values[':plan_id'] = filters['planId']
        
        if filter_expressions:
            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
            scan_kwargs['ExpressionAttributeValues'] = expression_values
            if expression_names:
                scan_kwargs['ExpressionAttributeNames'] = expression_names
        
        # Scan table
        response = subscribers_table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        # Continue scanning for more items
        while response.get('LastEvaluatedKey'):
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = subscribers_table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))
        
        print(f"Retrieved {len(items)} records from Cloud system")
        return items
    
    except Exception as e:
        print(f"Failed to get cloud subscribers: {e}")
        return []


def get_legacy_subscribers(filters):
    """Get subscribers from RDS MySQL with filters (placeholder)"""
    # Placeholder for RDS implementation
    # In production, implement with pymysql or similar
    print(f"Legacy database export not implemented in this demo (filters: {filters})")
    return []


def merge_subscriber_data(cloud_data, legacy_data, mask_pii):
    """Merge data from Cloud and Legacy systems with deduplication"""
    merged = {}
    
    # Add cloud data
    for item in cloud_data:
        formatted = format_subscriber_for_api(item, mask_pii=mask_pii)
        formatted['dataSource'] = 'cloud'
        formatted['syncStatus'] = 'cloud_only'
        merged[item['uid']] = formatted
    
    # Add legacy data and check for conflicts
    for item in legacy_data:
        uid = item['uid']
        formatted = format_subscriber_for_api(item, mask_pii=mask_pii)
        formatted['dataSource'] = 'legacy'
        
        if uid in merged:
            # Record exists in both systems
            cloud_item = merged[uid]
            
            # Check for conflicts
            conflicts = find_data_conflicts(cloud_item, formatted)
            if conflicts:
                merged[uid]['syncStatus'] = 'conflict'
                merged[uid]['conflicts'] = conflicts
                merged[uid]['dataSource'] = 'both_conflict'
            else:
                merged[uid]['syncStatus'] = 'synced'
                merged[uid]['dataSource'] = 'both_synced'
        else:
            # Legacy only
            formatted['syncStatus'] = 'legacy_only'
            merged[uid] = formatted
    
    # Convert to list and sort by UID
    result = list(merged.values())
    result.sort(key=lambda x: x.get('uid', ''))
    
    return result


def generate_comparison_data(cloud_data, legacy_data, mask_pii):
    """Generate comparison data showing differences between systems"""
    comparison_results = []
    
    # Create lookup maps
    cloud_map = {item['uid']: item for item in cloud_data}
    legacy_map = {item['uid']: item for item in legacy_data}
    
    all_uids = set(cloud_map.keys()) | set(legacy_map.keys())
    
    for uid in sorted(all_uids):
        cloud_record = cloud_map.get(uid)
        legacy_record = legacy_map.get(uid)
        
        comparison_record = {
            'uid': uid,
            'comparisonType': '',
            'cloudData': None,
            'legacyData': None,
            'conflicts': [],
            'syncStatus': ''
        }
        
        if cloud_record and legacy_record:
            # Both systems have the record
            comparison_record['comparisonType'] = 'both_systems'
            comparison_record['cloudData'] = format_subscriber_for_api(cloud_record, mask_pii=mask_pii)
            comparison_record['legacyData'] = format_subscriber_for_api(legacy_record, mask_pii=mask_pii)
            
            # Find conflicts
            conflicts = find_data_conflicts(comparison_record['cloudData'], comparison_record['legacyData'])
            comparison_record['conflicts'] = conflicts
            comparison_record['syncStatus'] = 'conflict' if conflicts else 'synced'
        
        elif cloud_record:
            # Cloud only
            comparison_record['comparisonType'] = 'cloud_only'
            comparison_record['cloudData'] = format_subscriber_for_api(cloud_record, mask_pii=mask_pii)
            comparison_record['syncStatus'] = 'cloud_only'
        
        elif legacy_record:
            # Legacy only
            comparison_record['comparisonType'] = 'legacy_only'
            comparison_record['legacyData'] = format_subscriber_for_api(legacy_record, mask_pii=mask_pii)
            comparison_record['syncStatus'] = 'legacy_only'
        
        comparison_results.append(comparison_record)
    
    return comparison_results


def find_data_conflicts(cloud_data, legacy_data):
    """Find conflicts between Cloud and Legacy data"""
    conflicts = []
    
    # Fields to compare
    compare_fields = ['msisdn', 'imsi', 'status', 'planId', 'email', 'firstName', 'lastName']
    
    for field in compare_fields:
        cloud_value = str(cloud_data.get(field, '')).strip()
        legacy_value = str(legacy_data.get(field, '')).strip()
        
        if cloud_value != legacy_value:
            conflicts.append({
                'field': field,
                'cloudValue': cloud_value,
                'legacyValue': legacy_value
            })
    
    return conflicts


def upload_export_file(job_id, data, format_type, source_suffix):
    """Upload export file to S3"""
    if not s3_client or not UPLOADS_BUCKET:
        print("S3 client or bucket not available")
        return None
    
    try:
        # Generate file content based on format
        if format_type.upper() == 'JSON':
            content = json.dumps(data, indent=2, default=str)
            content_type = 'application/json'
            file_extension = 'json'
        
        elif format_type.upper() == 'XML':
            content = convert_to_xml(data)
            content_type = 'application/xml'
            file_extension = 'xml'
        
        else:  # Default to CSV
            content = convert_to_csv(data)
            content_type = 'text/csv'
            file_extension = 'csv'
        
        # Generate file key
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_key = f"exports/{job_id}/export_{source_suffix}_{timestamp}.{file_extension}"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=UPLOADS_BUCKET,
            Key=file_key,
            Body=content,
            ContentType=content_type,
            Metadata={
                'job-id': job_id,
                'export-type': source_suffix,
                'format': format_type,
                'record-count': str(len(data)),
                'generated-at': datetime.utcnow().isoformat()
            }
        )
        
        print(f"Export file uploaded: {file_key}")
        return file_key
    
    except Exception as e:
        print(f"Failed to upload export file: {e}")
        return None


def convert_to_csv(data):
    """Convert data to CSV format"""
    if not data:
        return "No data available\n"
    
    output = StringIO()
    
    # Get all possible field names from the data
    fieldnames = set()
    for record in data:
        fieldnames.update(record.keys())
    
    fieldnames = sorted(list(fieldnames))
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for record in data:
        # Ensure all fields are strings
        row = {}
        for field in fieldnames:
            value = record.get(field, '')
            if isinstance(value, (dict, list)):
                row[field] = json.dumps(value)
            else:
                row[field] = str(value) if value is not None else ''
        writer.writerow(row)
    
    return output.getvalue()


def convert_to_xml(data):
    """Convert data to XML format"""
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<subscribers>\n'
    
    for record in data:
        xml_content += '  <subscriber>\n'
        for key, value in record.items():
            if value is not None:
                # Escape XML special characters
                escaped_value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                xml_content += f'    <{key}>{escaped_value}</{key}>\n'
        xml_content += '  </subscriber>\n'
    
    xml_content += '</subscribers>\n'
    return xml_content


def generate_download_url(file_key):
    """Generate pre-signed download URL for export file"""
    if not s3_client or not file_key:
        return None
    
    try:
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': UPLOADS_BUCKET,
                'Key': file_key
            },
            ExpiresIn=3600 * 24  # 24 hours
        )
        
        return download_url
    
    except Exception as e:
        print(f"Failed to generate download URL: {e}")
        return None