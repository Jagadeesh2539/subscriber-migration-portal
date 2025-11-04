#!/usr/bin/env python3
import json
import os
import boto3
from botocore.exceptions import ClientError
import csv
from io import StringIO

# Lambda Layer imports
import sys
sys.path.append('/opt/python')
from common_utils import InputValidator, SubscriberStatus, JobType

try:
    s3_client = boto3.client('s3')
except Exception as e:
    print(f"AWS S3 client initialization error: {e}")
    s3_client = None


def lambda_handler(event, context):
    """Validate migration job before processing"""
    try:
        job_id = event.get('jobId')
        input_file_key = event.get('inputFileKey')
        job_type = event.get('jobType')
        filters = event.get('filters', {})
        
        print(f"Validating job {job_id}: {job_type} with file {input_file_key}")
        
        validation_result = {
            'jobId': job_id,
            'valid': False,
            'error': None,
            'warnings': [],
            'metadata': {}
        }
        
        # Validate job parameters
        validator = InputValidator()
        validator.require('jobId', job_id)
        validator.require('jobType', job_type)
        validator.validate_enum('jobType', job_type, JobType.ALL, required=True)
        
        if job_type in [JobType.MIGRATION, JobType.BULK_DELETE]:
            validator.require('inputFileKey', input_file_key)
        
        errors = validator.get_errors()
        if errors:
            validation_result['error'] = f"Parameter validation failed: {'; '.join(errors)}"
            return validation_result
        
        # Validate file if required
        if input_file_key:
            file_validation = validate_input_file(input_file_key, job_type)
            validation_result['metadata'].update(file_validation['metadata'])
            validation_result['warnings'].extend(file_validation.get('warnings', []))
            
            if not file_validation['valid']:
                validation_result['error'] = file_validation['error']
                return validation_result
        
        # Job-specific validations
        if job_type == JobType.AUDIT:
            audit_validation = validate_audit_job(filters)
            if not audit_validation['valid']:
                validation_result['error'] = audit_validation['error']
                return validation_result
            validation_result['warnings'].extend(audit_validation.get('warnings', []))
        
        elif job_type == JobType.EXPORT:
            export_validation = validate_export_job(filters)
            if not export_validation['valid']:
                validation_result['error'] = export_validation['error']
                return validation_result
            validation_result['warnings'].extend(export_validation.get('warnings', []))
        
        # All validations passed
        validation_result['valid'] = True
        
        print(f"Job {job_id} validation completed successfully")
        return validation_result
    
    except Exception as e:
        print(f"Job validation error: {str(e)}")
        return {
            'jobId': event.get('jobId', 'unknown'),
            'valid': False,
            'error': f'Validation service error: {str(e)}',
            'warnings': [],
            'metadata': {}
        }


def validate_input_file(file_key, job_type):
    """Validate input file from S3"""
    if not s3_client:
        return {
            'valid': False,
            'error': 'S3 client not available',
            'metadata': {}
        }
    
    try:
        bucket = os.environ.get('UPLOADS_BUCKET')
        if not bucket:
            return {
                'valid': False,
                'error': 'Uploads bucket not configured',
                'metadata': {}
            }
        
        # Check if file exists and get metadata
        try:
            response = s3_client.head_object(Bucket=bucket, Key=file_key)
            file_size = response['ContentLength']
            content_type = response.get('ContentType', '')
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return {
                    'valid': False,
                    'error': f'File not found: {file_key}',
                    'metadata': {}
                }
            else:
                raise e
        
        # Validate file size (max 100MB)
        max_size = 100 * 1024 * 1024  # 100MB
        if file_size > max_size:
            return {
                'valid': False,
                'error': f'File too large: {file_size / (1024*1024):.1f}MB (max: {max_size / (1024*1024)}MB)',
                'metadata': {'fileSize': file_size}
            }
        
        # Validate content type
        allowed_types = ['text/csv', 'application/csv', 'text/plain']
        if content_type not in allowed_types:
            return {
                'valid': False,
                'error': f'Invalid file type: {content_type}. Allowed: {allowed_types}',
                'metadata': {'fileSize': file_size, 'contentType': content_type}
            }
        
        # Read and validate CSV structure
        csv_validation = validate_csv_structure(bucket, file_key, job_type)
        
        result = {
            'valid': csv_validation['valid'],
            'error': csv_validation.get('error'),
            'warnings': csv_validation.get('warnings', []),
            'metadata': {
                'fileSize': file_size,
                'contentType': content_type,
                'recordCount': csv_validation['metadata'].get('recordCount', 0),
                'columns': csv_validation['metadata'].get('columns', [])
            }
        }
        
        # Add performance warnings
        if file_size > 10 * 1024 * 1024:  # 10MB
            result['warnings'].append(f'Large file detected ({file_size / (1024*1024):.1f}MB) - processing may take several minutes')
        
        if csv_validation['metadata'].get('recordCount', 0) > 10000:
            result['warnings'].append(f'Large dataset detected ({csv_validation["metadata"]["recordCount"]} records) - consider breaking into smaller batches')
        
        return result
    
    except Exception as e:
        return {
            'valid': False,
            'error': f'File validation failed: {str(e)}',
            'metadata': {}
        }


def validate_csv_structure(bucket, file_key, job_type):
    """Validate CSV file structure and content"""
    try:
        # Download first few KB to check structure
        response = s3_client.get_object(
            Bucket=bucket, 
            Key=file_key,
            Range='bytes=0-8192'  # First 8KB
        )
        
        content = response['Body'].read().decode('utf-8')
        
        # Parse CSV header
        csv_reader = csv.reader(StringIO(content))
        header = next(csv_reader, [])
        
        if not header:
            return {
                'valid': False,
                'error': 'CSV file is empty or has no header',
                'metadata': {'columns': []}
            }
        
        # Validate required columns based on job type
        required_columns = get_required_columns(job_type)
        missing_columns = [col for col in required_columns if col not in header]
        
        if missing_columns:
            return {
                'valid': False,
                'error': f'Missing required columns: {missing_columns}',
                'metadata': {'columns': header, 'missingColumns': missing_columns}
            }
        
        # Count approximate records (estimate from first chunk)
        lines = content.count('\n')
        estimated_records = max(0, lines - 1)  # Subtract header
        
        # Validate sample records
        sample_validation = validate_sample_records(csv_reader, header, job_type)
        
        return {
            'valid': sample_validation['valid'],
            'error': sample_validation.get('error'),
            'warnings': sample_validation.get('warnings', []),
            'metadata': {
                'columns': header,
                'recordCount': estimated_records,
                'sampleSize': sample_validation['metadata'].get('sampleSize', 0)
            }
        }
    
    except Exception as e:
        return {
            'valid': False,
            'error': f'CSV validation failed: {str(e)}',
            'metadata': {}
        }


def get_required_columns(job_type):
    """Get required columns for each job type"""
    base_columns = ['uid', 'msisdn', 'imsi']
    
    if job_type == JobType.MIGRATION:
        return base_columns + ['status']  # Migration needs at least uid, msisdn, imsi, status
    elif job_type == JobType.BULK_DELETE:
        return ['uid']  # Delete only needs uid
    else:
        return base_columns


def validate_sample_records(csv_reader, header, job_type):
    """Validate sample records from CSV"""
    sample_size = 0
    validation_errors = []
    warnings = []
    
    try:
        # Check first few records
        for i, row in enumerate(csv_reader):
            if i >= 5:  # Check max 5 sample records
                break
            
            sample_size += 1
            
            if len(row) != len(header):
                validation_errors.append(f'Row {i+2}: Column count mismatch (expected {len(header)}, got {len(row)})')
                continue
            
            # Create record dict
            record = dict(zip(header, row))
            
            # Validate record fields
            validator = InputValidator()
            
            if 'uid' in record:
                validator.require('uid', record['uid'])
                validator.validate_length('uid', record['uid'], min_length=1, max_length=64)
            
            if 'msisdn' in record and record['msisdn']:
                validator.validate_msisdn('msisdn', record['msisdn'], required=False)
            
            if 'imsi' in record and record['imsi']:
                validator.validate_imsi('imsi', record['imsi'], required=False)
            
            if 'status' in record and record['status']:
                validator.validate_enum('status', record['status'], SubscriberStatus.ALL, required=False)
            
            if 'email' in record and record['email']:
                validator.validate_email('email', record['email'], required=False)
            
            record_errors = validator.get_errors()
            if record_errors:
                validation_errors.extend([f'Row {i+2}: {error}' for error in record_errors[:3]])  # Limit errors per row
        
        # Limit total errors reported
        if len(validation_errors) > 10:
            validation_errors = validation_errors[:10]
            warnings.append(f'More than 10 validation errors found in sample - showing first 10 only')
        
        return {
            'valid': len(validation_errors) == 0,
            'error': f'Sample record validation failed: {validation_errors[0]}' if validation_errors else None,
            'warnings': warnings + ([f'Sample validation found {len(validation_errors)} errors'] if validation_errors else []),
            'metadata': {
                'sampleSize': sample_size,
                'validationErrors': validation_errors
            }
        }
    
    except Exception as e:
        return {
            'valid': False,
            'error': f'Sample validation failed: {str(e)}',
            'metadata': {'sampleSize': sample_size}
        }


def validate_audit_job(filters):
    """Validate audit job parameters"""
    warnings = []
    
    # Check if filters are too broad (could impact performance)
    if not filters or len(filters) == 0:
        warnings.append('No filters specified - audit will process all records (may be slow)')
    
    # Validate filter values
    validator = InputValidator()
    
    if filters.get('status'):
        validator.validate_enum('status', filters['status'], SubscriberStatus.ALL, required=False)
    
    if filters.get('dateFrom'):
        validator.validate_date('dateFrom', filters['dateFrom'], required=False)
    
    if filters.get('dateTo'):
        validator.validate_date('dateTo', filters['dateTo'], required=False)
    
    errors = validator.get_errors()
    if errors:
        return {
            'valid': False,
            'error': f'Audit filter validation failed: {"; ".join(errors)}'
        }
    
    return {
        'valid': True,
        'warnings': warnings
    }


def validate_export_job(filters):
    """Validate export job parameters"""
    warnings = []
    
    # Validate export scope
    export_scope = filters.get('exportScope', 'BOTH_SYSTEMS')
    allowed_scopes = ['CLOUD_ONLY', 'LEGACY_ONLY', 'BOTH_SYSTEMS', 'COMPARISON']
    
    validator = InputValidator()
    validator.validate_enum('exportScope', export_scope, allowed_scopes, required=False)
    
    # Validate format
    export_format = filters.get('format', 'CSV')
    allowed_formats = ['CSV', 'JSON', 'XML']
    validator.validate_enum('format', export_format, allowed_formats, required=False)
    
    # Validate other filters
    if filters.get('status'):
        validator.validate_enum('status', filters['status'], SubscriberStatus.ALL, required=False)
    
    if filters.get('dateFrom'):
        validator.validate_date('dateFrom', filters['dateFrom'], required=False)
    
    if filters.get('dateTo'):
        validator.validate_date('dateTo', filters['dateTo'], required=False)
    
    errors = validator.get_errors()
    if errors:
        return {
            'valid': False,
            'error': f'Export parameter validation failed: {"; ".join(errors)}'
        }
    
    # Check for performance warnings
    if not filters or len([k for k, v in filters.items() if v]) <= 1:
        warnings.append('Minimal filters specified - export may include large dataset and take time')
    
    if export_scope == 'BOTH_SYSTEMS':
        warnings.append('Export from both systems may take longer due to data merging requirements')
    
    return {
        'valid': True,
        'warnings': warnings
    }