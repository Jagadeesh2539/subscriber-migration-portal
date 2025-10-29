#!/usr/bin/env python3
"""
Subscriber Migration Portal - API Extensions
Migration, Analytics, Provisioning, Monitoring, File Upload APIs
"""

import os
import json
import logging
import uuid
import io
import csv
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from decimal import Decimal

import boto3
from flask import request, jsonify, g, make_response, send_file
from werkzeug.utils import secure_filename
from botocore.exceptions import ClientError

# This file contains additional API routes to be imported into main app.py

def register_migration_routes(app, tables, s3_client, get_legacy_db_connection, create_response, audit_log, require_auth, CONFIG, logger):
    """Register migration-related API routes."""
    
    @app.route('/api/migration/jobs', methods=['GET'])
    @require_auth(['read'])
    def get_migration_jobs():
        """Get migration jobs with filtering."""
        try:
            limit = min(int(request.args.get('limit', '20')), 100)
            status = request.args.get('status', 'all')
            
            if 'migration_jobs' not in tables:
                return create_response(message="Migration jobs table not available", status_code=503)
            
            if status == 'all':
                response = tables['migration_jobs'].scan(Limit=limit)
            else:
                response = tables['migration_jobs'].scan(
                    FilterExpression='#status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': status},
                    Limit=limit
                )
            
            jobs = response.get('Items', [])
            
            # Convert Decimal types for JSON serialization
            for job in jobs:
                for key, value in job.items():
                    if isinstance(value, Decimal):
                        job[key] = float(value)
            
            # Sort by creation time (newest first)
            jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return create_response(data={
                'jobs': jobs,
                'count': len(jobs),
                'status_filter': status
            })
            
        except Exception as e:
            logger.error(f"Get migration jobs error: {str(e)}")
            return create_response(message="Failed to get migration jobs", status_code=500)
    
    @app.route('/api/migration/jobs', methods=['POST'])
    @require_auth(['write'])
    def create_migration_job():
        """Create a new migration job."""
        try:
            data = request.get_json()
            
            if not data:
                return create_response(message="No data provided", status_code=400)
            
            job_id = str(uuid.uuid4())
            
            job_data = {
                'id': job_id,
                'type': data.get('type', 'csv_upload'),
                'status': 'PENDING',
                'source': data.get('source', 'legacy'),
                'target': data.get('target', 'cloud'),
                'criteria': data.get('criteria', {}),
                'progress': 0,
                'total_records': 0,
                'processed_records': 0,
                'successful_records': 0,
                'failed_records': 0,
                'created_at': datetime.utcnow().isoformat(),
                'created_by': g.current_user['username'],
                'updated_at': datetime.utcnow().isoformat(),
                'estimated_completion': None,
                'error_log': [],
                'metadata': data.get('metadata', {})
            }
            
            if 'migration_jobs' in tables:
                tables['migration_jobs'].put_item(Item=job_data)
            
            audit_log('migration_job_created', 'migration', g.current_user['username'], {
                'job_id': job_id,
                'type': job_data['type'],
                'source': job_data['source'],
                'target': job_data['target']
            })
            
            return create_response(data={
                'job_id': job_id,
                'status': job_data['status'],
                'created_at': job_data['created_at']
            }, message="Migration job created", status_code=201)
            
        except Exception as e:
            logger.error(f"Create migration job error: {str(e)}")
            return create_response(message=f"Failed to create migration job: {str(e)}", status_code=500)
    
    @app.route('/api/migration/jobs/<job_id>/status', methods=['GET'])
    @require_auth(['read'])
    def get_migration_job_status(job_id):
        """Get detailed status of a migration job."""
        try:
            if 'migration_jobs' not in tables:
                return create_response(message="Migration jobs table not available", status_code=503)
            
            response = tables['migration_jobs'].get_item(Key={'id': job_id})
            
            if 'Item' not in response:
                return create_response(message="Migration job not found", status_code=404)
            
            job = response['Item']
            
            # Convert Decimal types
            for key, value in job.items():
                if isinstance(value, Decimal):
                    job[key] = float(value)
            
            # Calculate additional metrics
            if job.get('total_records', 0) > 0:
                job['completion_percentage'] = round((job.get('processed_records', 0) / job['total_records']) * 100, 2)
            else:
                job['completion_percentage'] = 0
            
            job['success_rate'] = 0
            if job.get('processed_records', 0) > 0:
                job['success_rate'] = round((job.get('successful_records', 0) / job['processed_records']) * 100, 2)
            
            return create_response(data=job)
            
        except Exception as e:
            logger.error(f"Get migration job status error: {str(e)}")
            return create_response(message="Failed to get job status", status_code=500)
    
    @app.route('/api/migration/jobs/<job_id>/cancel', methods=['POST'])
    @require_auth(['write'])
    def cancel_migration_job(job_id):
        """Cancel a migration job."""
        try:
            if 'migration_jobs' not in tables:
                return create_response(message="Migration jobs table not available", status_code=503)
            
            tables['migration_jobs'].update_item(
                Key={'id': job_id},
                UpdateExpression="SET #status = :status, updated_at = :updated_at, cancelled_by = :cancelled_by",
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'CANCELLED',
                    ':updated_at': datetime.utcnow().isoformat(),
                    ':cancelled_by': g.current_user['username']
                }
            )
            
            audit_log('migration_job_cancelled', 'migration', g.current_user['username'], {'job_id': job_id})
            
            return create_response(message="Migration job cancelled")
            
        except Exception as e:
            logger.error(f"Cancel migration job error: {str(e)}")
            return create_response(message="Failed to cancel job", status_code=500)
    
    @app.route('/api/migration/upload', methods=['POST'])
    @require_auth(['write'])
    def upload_migration_file():
        """Upload file for migration processing."""
        try:
            if 'file' not in request.files:
                return create_response(message="No file provided", status_code=400)
            
            file = request.files['file']
            if file.filename == '':
                return create_response(message="No file selected", status_code=400)
            
            # Validate file
            if not file.filename.endswith(('.csv', '.json', '.xml')):
                return create_response(message="Invalid file type. Only CSV, JSON, XML allowed", status_code=400)
            
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{filename}"
            
            # Upload to S3
            if s3_client and CONFIG.get('MIGRATION_UPLOAD_BUCKET_NAME'):
                try:
                    s3_client.upload_fileobj(
                        file,
                        CONFIG['MIGRATION_UPLOAD_BUCKET_NAME'],
                        unique_filename,
                        ExtraArgs={
                            'Metadata': {
                                'uploaded_by': g.current_user['username'],
                                'original_filename': filename,
                                'upload_timestamp': datetime.utcnow().isoformat()
                            }
                        }
                    )
                    
                    # Create migration job for uploaded file
                    job_id = str(uuid.uuid4())
                    job_data = {
                        'id': job_id,
                        'type': 'file_upload',
                        'status': 'PENDING_PROCESSING',
                        'source': 'file',
                        'target': request.form.get('target', 'cloud'),
                        'file_info': {
                            'original_filename': filename,
                            's3_key': unique_filename,
                            'bucket': CONFIG['MIGRATION_UPLOAD_BUCKET_NAME'],
                            'file_size': request.content_length
                        },
                        'progress': 0,
                        'created_at': datetime.utcnow().isoformat(),
                        'created_by': g.current_user['username'],
                        'updated_at': datetime.utcnow().isoformat()
                    }
                    
                    if 'migration_jobs' in tables:
                        tables['migration_jobs'].put_item(Item=job_data)
                    
                    audit_log('file_uploaded', 'migration', g.current_user['username'], {
                        'filename': filename,
                        's3_key': unique_filename,
                        'job_id': job_id
                    })
                    
                    return create_response(data={
                        'job_id': job_id,
                        'filename': filename,
                        's3_key': unique_filename,
                        'status': 'uploaded'
                    }, message="File uploaded successfully", status_code=201)
                    
                except Exception as e:
                    logger.error(f"S3 upload error: {str(e)}")
                    return create_response(message=f"Failed to upload file: {str(e)}", status_code=500)
            else:
                return create_response(message="File upload service not available", status_code=503)
            
        except Exception as e:
            logger.error(f"Upload migration file error: {str(e)}")
            return create_response(message="Failed to upload file", status_code=500)


def register_analytics_routes(app, tables, get_legacy_db_connection, create_response, require_auth, logger):
    """Register analytics and reporting routes."""
    
    @app.route('/api/analytics', methods=['GET'])
    @require_auth(['read'])
    def get_analytics_data():
        """Get analytics data for specified time range."""
        try:
            time_range = request.args.get('range', '30d')
            
            # Parse time range
            if time_range == '24h':
                start_time = datetime.utcnow() - timedelta(days=1)
            elif time_range == '7d':
                start_time = datetime.utcnow() - timedelta(days=7)
            elif time_range == '30d':
                start_time = datetime.utcnow() - timedelta(days=30)
            elif time_range == '90d':
                start_time = datetime.utcnow() - timedelta(days=90)
            else:
                start_time = datetime.utcnow() - timedelta(days=30)
            
            analytics_data = {
                'time_range': time_range,
                'start_time': start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'subscriber_metrics': {
                    'total_subscribers': 0,
                    'active_subscribers': 0,
                    'inactive_subscribers': 0,
                    'new_subscribers': 0,
                    'deleted_subscribers': 0
                },
                'migration_metrics': {
                    'total_jobs': 0,
                    'completed_jobs': 0,
                    'failed_jobs': 0,
                    'success_rate': 0,
                    'avg_processing_time': 0
                },
                'system_metrics': {
                    'api_calls': 0,
                    'error_rate': 0,
                    'avg_response_time': 0
                },
                'trends': {
                    'daily_signups': [],
                    'migration_activity': [],
                    'system_usage': []
                }
            }
            
            # Get subscriber metrics
            try:
                if 'subscribers' in tables:
                    # Get all subscribers
                    response = tables['subscribers'].scan()
                    subscribers = response.get('Items', [])
                    
                    analytics_data['subscriber_metrics']['total_subscribers'] = len(subscribers)
                    
                    for sub in subscribers:
                        status = sub.get('status', '').upper()
                        created_at = sub.get('created_at', '')
                        
                        if status == 'ACTIVE':
                            analytics_data['subscriber_metrics']['active_subscribers'] += 1
                        elif status == 'INACTIVE':
                            analytics_data['subscriber_metrics']['inactive_subscribers'] += 1
                        elif status == 'DELETED':
                            analytics_data['subscriber_metrics']['deleted_subscribers'] += 1
                        
                        # Check if created in time range
                        try:
                            if created_at and datetime.fromisoformat(created_at.replace('Z', '+00:00')) >= start_time:
                                analytics_data['subscriber_metrics']['new_subscribers'] += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Subscriber metrics error: {str(e)}")
            
            # Get migration metrics
            try:
                if 'migration_jobs' in tables:
                    response = tables['migration_jobs'].scan()
                    jobs = response.get('Items', [])
                    
                    total_jobs = len(jobs)
                    completed_jobs = 0
                    failed_jobs = 0
                    processing_times = []
                    
                    for job in jobs:
                        status = job.get('status', '').upper()
                        
                        if status == 'COMPLETED':
                            completed_jobs += 1
                        elif status in ['FAILED', 'ERROR']:
                            failed_jobs += 1
                        
                        # Calculate processing time
                        created_at = job.get('created_at')
                        updated_at = job.get('updated_at')
                        if created_at and updated_at and status == 'COMPLETED':
                            try:
                                start = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                end = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                                processing_times.append((end - start).total_seconds())
                            except Exception:
                                pass
                    
                    analytics_data['migration_metrics']['total_jobs'] = total_jobs
                    analytics_data['migration_metrics']['completed_jobs'] = completed_jobs
                    analytics_data['migration_metrics']['failed_jobs'] = failed_jobs
                    
                    if total_jobs > 0:
                        analytics_data['migration_metrics']['success_rate'] = round((completed_jobs / total_jobs) * 100, 2)
                    
                    if processing_times:
                        analytics_data['migration_metrics']['avg_processing_time'] = round(sum(processing_times) / len(processing_times), 2)
            except Exception as e:
                logger.error(f"Migration metrics error: {str(e)}")
            
            # Get audit log metrics for system usage
            try:
                if 'audit_logs' in tables:
                    response = tables['audit_logs'].scan(
                        FilterExpression='#timestamp >= :start_time',
                        ExpressionAttributeNames={'#timestamp': 'timestamp'},
                        ExpressionAttributeValues={':start_time': start_time.isoformat()}
                    )
                    
                    logs = response.get('Items', [])
                    analytics_data['system_metrics']['api_calls'] = len(logs)
                    
                    # Count errors
                    error_actions = ['login_failed', 'error', 'failed']
                    error_count = sum(1 for log in logs if any(error in log.get('action', '').lower() for error in error_actions))
                    
                    if len(logs) > 0:
                        analytics_data['system_metrics']['error_rate'] = round((error_count / len(logs)) * 100, 2)
            except Exception as e:
                logger.error(f"System metrics error: {str(e)}")
            
            return create_response(data=analytics_data)
            
        except Exception as e:
            logger.error(f"Analytics error: {str(e)}")
            return create_response(message="Failed to get analytics data", status_code=500)
    
    @app.route('/api/metrics/system', methods=['GET'])
    @require_auth(['read'])
    def get_system_metrics():
        """Get real-time system metrics."""
        try:
            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'uptime': 'healthy',
                'database_connections': {
                    'dynamodb': bool(tables),
                    'legacy_db': False
                },
                'performance': {
                    'memory_usage': 'normal',
                    'cpu_usage': 'normal',
                    'response_time': 'normal'
                },
                'active_users': 0,
                'current_operations': 0
            }
            
            # Test legacy DB connection
            try:
                connection = get_legacy_db_connection()
                if connection:
                    connection.close()
                    metrics['database_connections']['legacy_db'] = True
            except Exception:
                pass
            
            return create_response(data=metrics)
            
        except Exception as e:
            logger.error(f"System metrics error: {str(e)}")
            return create_response(message="Failed to get system metrics", status_code=500)


def register_provisioning_routes(app, tables, get_legacy_db_connection, create_response, audit_log, require_auth, CONFIG, logger):
    """Register provisioning management routes."""
    
    @app.route('/api/config/provisioning-mode', methods=['GET'])
    @require_auth(['read'])
    def get_provisioning_mode():
        """Get current provisioning mode."""
        return create_response(data={
            'mode': CONFIG['PROV_MODE'],
            'available_modes': ['legacy', 'cloud', 'dual_prov'],
            'description': {
                'legacy': 'All operations target legacy database only',
                'cloud': 'All operations target cloud database only',
                'dual_prov': 'Operations target both legacy and cloud databases'
            }
        })
    
    @app.route('/api/config/provisioning-mode', methods=['POST'])
    @require_auth(['admin'])
    def set_provisioning_mode():
        """Set provisioning mode (admin only)."""
        try:
            data = request.get_json()
            new_mode = data.get('mode')
            
            if new_mode not in ['legacy', 'cloud', 'dual_prov']:
                return create_response(message="Invalid provisioning mode", status_code=400)
            
            # Update configuration (in production, this would update environment variable)
            CONFIG['PROV_MODE'] = new_mode
            
            audit_log('provisioning_mode_changed', 'config', g.current_user['username'], {
                'old_mode': CONFIG.get('PROV_MODE'),
                'new_mode': new_mode
            })
            
            return create_response(data={'mode': new_mode}, message="Provisioning mode updated")
            
        except Exception as e:
            logger.error(f"Set provisioning mode error: {str(e)}")
            return create_response(message="Failed to update provisioning mode", status_code=500)
    
    @app.route('/api/provision/dashboard', methods=['GET'])
    @require_auth(['read'])
    def get_provisioning_dashboard():
        """Get provisioning dashboard data."""
        try:
            dashboard_data = {
                'current_mode': CONFIG['PROV_MODE'],
                'system_status': {
                    'legacy_system': {
                        'status': 'unknown',
                        'subscribers': 0,
                        'last_sync': None
                    },
                    'cloud_system': {
                        'status': 'unknown',
                        'subscribers': 0,
                        'last_sync': None
                    }
                },
                'sync_status': {
                    'in_sync': False,
                    'discrepancies': 0,
                    'last_audit': None
                },
                'recent_operations': []
            }
            
            # Check cloud system
            try:
                if 'subscribers' in tables:
                    response = tables['subscribers'].scan(Select='COUNT')
                    dashboard_data['system_status']['cloud_system']['status'] = 'healthy'
                    dashboard_data['system_status']['cloud_system']['subscribers'] = response.get('Count', 0)
                    dashboard_data['system_status']['cloud_system']['last_sync'] = datetime.utcnow().isoformat()
            except Exception:
                dashboard_data['system_status']['cloud_system']['status'] = 'error'
            
            # Check legacy system
            try:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT COUNT(*) as count FROM subscribers WHERE status != 'DELETED'")
                        result = cursor.fetchone()
                        dashboard_data['system_status']['legacy_system']['status'] = 'healthy'
                        dashboard_data['system_status']['legacy_system']['subscribers'] = result['count'] if result else 0
                        dashboard_data['system_status']['legacy_system']['last_sync'] = datetime.utcnow().isoformat()
                    connection.close()
                else:
                    dashboard_data['system_status']['legacy_system']['status'] = 'disconnected'
            except Exception:
                dashboard_data['system_status']['legacy_system']['status'] = 'error'
            
            # Get recent operations from audit logs
            try:
                if 'audit_logs' in tables:
                    response = tables['audit_logs'].scan(
                        FilterExpression='contains(#action, :prov)',
                        ExpressionAttributeNames={'#action': 'action'},
                        ExpressionAttributeValues={':prov': 'provision'},
                        Limit=10
                    )
                    
                    operations = response.get('Items', [])
                    operations.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                    dashboard_data['recent_operations'] = operations[:5]
            except Exception:
                pass
            
            return create_response(data=dashboard_data)
            
        except Exception as e:
            logger.error(f"Provisioning dashboard error: {str(e)}")
            return create_response(message="Failed to get provisioning dashboard", status_code=500)


def register_export_routes(app, tables, get_legacy_db_connection, create_response, require_auth, logger):
    """Register data export routes."""
    
    @app.route('/api/export/<system>', methods=['GET'])
    @require_auth(['read'])
    def export_data(system):
        """Export data from specified system."""
        try:
            format_type = request.args.get('format', 'csv').lower()
            limit = min(int(request.args.get('limit', '1000')), 10000)
            
            if system not in ['cloud', 'legacy', 'all']:
                return create_response(message="Invalid system. Use 'cloud', 'legacy', or 'all'", status_code=400)
            
            if format_type not in ['csv', 'json']:
                return create_response(message="Invalid format. Use 'csv' or 'json'", status_code=400)
            
            data = []
            
            # Export from cloud
            if system in ['cloud', 'all'] and 'subscribers' in tables:
                response = tables['subscribers'].scan(Limit=limit)
                cloud_data = response.get('Items', [])
                for item in cloud_data:
                    # Convert Decimal types and add source
                    record = {'source': 'cloud'}
                    for key, value in item.items():
                        if isinstance(value, Decimal):
                            record[key] = float(value)
                        else:
                            record[key] = value
                    data.append(record)
            
            # Export from legacy
            if system in ['legacy', 'all']:
                connection = get_legacy_db_connection()
                if connection:
                    with connection.cursor() as cursor:
                        cursor.execute(f"SELECT * FROM subscribers WHERE status != 'DELETED' LIMIT {limit}")
                        legacy_data = cursor.fetchall()
                        for item in legacy_data:
                            item['source'] = 'legacy'
                            data.append(item)
                    connection.close()
            
            if format_type == 'csv':
                # Create CSV
                output = io.StringIO()
                if data:
                    fieldnames = set()
                    for record in data:
                        fieldnames.update(record.keys())
                    fieldnames = sorted(fieldnames)
                    
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    for record in data:
                        writer.writerow(record)
                
                response = make_response(output.getvalue())
                response.headers['Content-Type'] = 'text/csv'
                response.headers['Content-Disposition'] = f'attachment; filename=subscribers_{system}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
                return response
            
            else:  # JSON format
                response = make_response(json.dumps(data, indent=2, default=str))
                response.headers['Content-Type'] = 'application/json'
                response.headers['Content-Disposition'] = f'attachment; filename=subscribers_{system}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
                return response
            
        except Exception as e:
            logger.error(f"Export data error: {str(e)}")
            return create_response(message=f"Failed to export data: {str(e)}", status_code=500)


def register_audit_routes(app, tables, create_response, require_auth, logger):
    """Register audit and logging routes."""
    
    @app.route('/api/audit/logs', methods=['GET'])
    @require_auth(['read'])
    def get_audit_logs():
        """Get audit logs with filtering."""
        try:
            limit = min(int(request.args.get('limit', '50')), 1000)
            action = request.args.get('action')
            user = request.args.get('user')
            resource = request.args.get('resource')
            start_date = request.args.get('start_date')
            
            if 'audit_logs' not in tables:
                return create_response(message="Audit logs not available", status_code=503)
            
            # Build filter expression
            filter_expression = None
            expression_values = {}
            expression_names = {}
            
            conditions = []
            
            if action:
                conditions.append('contains(#action, :action)')
                expression_names['#action'] = 'action'
                expression_values[':action'] = action
            
            if user:
                conditions.append('#user = :user')
                expression_names['#user'] = 'user'
                expression_values[':user'] = user
            
            if resource:
                conditions.append('contains(#resource, :resource)')
                expression_names['#resource'] = 'resource'
                expression_values[':resource'] = resource
            
            if start_date:
                try:
                    # Validate date format
                    datetime.fromisoformat(start_date)
                    conditions.append('#timestamp >= :start_date')
                    expression_names['#timestamp'] = 'timestamp'
                    expression_values[':start_date'] = start_date
                except ValueError:
                    return create_response(message="Invalid start_date format. Use ISO format", status_code=400)
            
            scan_kwargs = {'Limit': limit}
            
            if conditions:
                filter_expression = ' AND '.join(conditions)
                scan_kwargs['FilterExpression'] = filter_expression
                scan_kwargs['ExpressionAttributeNames'] = expression_names
                scan_kwargs['ExpressionAttributeValues'] = expression_values
            
            response = tables['audit_logs'].scan(**scan_kwargs)
            logs = response.get('Items', [])
            
            # Sort by timestamp (newest first)
            logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return create_response(data={
                'logs': logs,
                'count': len(logs),
                'filters': {
                    'action': action,
                    'user': user,
                    'resource': resource,
                    'start_date': start_date
                }
            })
            
        except Exception as e:
            logger.error(f"Get audit logs error: {str(e)}")
            return create_response(message="Failed to get audit logs", status_code=500)