#!/usr/bin/env python3
"""
Subscriber Controller - CRUD Operations with Dual Database Support
Handles: Create, Read, Update, Delete operations across Cloud (DynamoDB) and Legacy (MySQL RDS)
"""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from flask import g, jsonify, make_response, request
from services.audit.service import AuditService
from services.subscribers.service import SubscriberService
from utils.logger import get_logger
from utils.pagination import paginate_results
from utils.response import create_error_response, create_response
from utils.validation import InputValidator, ValidationError

logger = get_logger(__name__)
subscriber_service = SubscriberService()
audit_service = AuditService()

class SubscriberController:
    """Enhanced subscriber management with dual database support"""
    
    @staticmethod
    def create_subscriber():
        """
        Create subscriber in configured provisioning mode(s)
        POST /api/subscribers
        """
        try:
            data = request.get_json()
            if not data:
                return create_error_response("Request body is required", 400)
            
            # Validate required fields
            validator = InputValidator()
            validated_data = validator.validate_subscriber_data(data)
            
            # Get provisioning mode from request or use system default
            prov_mode = validated_data.get('provisioning_mode', g.get('prov_mode', 'dual'))
            
            # Create subscriber based on provisioning mode
            result = subscriber_service.create_subscriber(validated_data, prov_mode)
            
            # Log audit trail
            audit_service.log_action(
                action='subscriber_created',
                resource='subscriber',
                user=g.current_user.get('username', 'system'),
                details={
                    'uid': validated_data['uid'],
                    'provisioning_mode': prov_mode,
                    'result': result['summary']
                }
            )
            
            return create_response(
                data=result,
                message=f"Subscriber created successfully in {prov_mode} mode"
            )
            
        except ValidationError as e:
            logger.warning(f"Validation error in create_subscriber: {str(e)}")
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error creating subscriber: {str(e)}")
            return create_error_response("Failed to create subscriber", 500)
    
    @staticmethod
    def get_subscribers():
        """
        Get subscribers with filtering, pagination, and search
        GET /api/subscribers?search=&status=&source=&limit=&offset=
        """
        try:
            # Parse query parameters
            search = request.args.get('search', '').strip()
            status = request.args.get('status', 'all')
            source = request.args.get('source', 'all')  # all, cloud, legacy
            limit = min(int(request.args.get('limit', 50)), 100)
            offset = int(request.args.get('offset', 0))
            sort_by = request.args.get('sort', 'created_at')
            sort_order = request.args.get('order', 'desc')
            
            # Validate parameters
            if status not in ['all', 'ACTIVE', 'INACTIVE', 'SUSPENDED', 'DELETED']:
                return create_error_response("Invalid status filter", 400)
            
            if source not in ['all', 'cloud', 'legacy']:\n                return create_error_response("Invalid source filter", 400)
            
            # Build search criteria
            search_criteria = {
                'search': search,
                'status': status if status != 'all' else None,
                'source': source,
                'limit': limit,
                'offset': offset,
                'sort_by': sort_by,
                'sort_order': sort_order
            }
            
            # Get subscribers from service
            result = subscriber_service.get_subscribers(search_criteria)
            
            # Add pagination metadata
            total_count = result.get('total_count', 0)
            pagination = paginate_results(offset, limit, total_count)
            
            response_data = {
                'subscribers': result['subscribers'],
                'pagination': pagination,
                'filters': {
                    'search': search,
                    'status': status,
                    'source': source,
                    'sort_by': sort_by,
                    'sort_order': sort_order
                },
                'summary': {
                    'total_found': total_count,
                    'returned': len(result['subscribers']),
                    'cloud_count': result.get('cloud_count', 0),
                    'legacy_count': result.get('legacy_count', 0)
                }
            }
            
            return create_response(data=response_data)
            
        except Exception as e:
            logger.error(f"Error getting subscribers: {str(e)}")
            return create_error_response("Failed to retrieve subscribers", 500)
    
    @staticmethod
    def get_subscriber_by_id(subscriber_id: str):
        """
        Get single subscriber by ID from all configured systems
        GET /api/subscribers/{subscriber_id}
        """
        try:
            # Validate subscriber ID
            validator = InputValidator()
            clean_id = validator.sanitize_string(subscriber_id, 50)
            
            if not clean_id:
                return create_error_response("Invalid subscriber ID", 400)
            
            # Get subscriber from service
            result = subscriber_service.get_subscriber_by_id(clean_id)
            
            if not result:
                return create_error_response("Subscriber not found", 404)
            
            return create_response(data=result)
            
        except Exception as e:
            logger.error(f"Error getting subscriber {subscriber_id}: {str(e)}")
            return create_error_response("Failed to retrieve subscriber", 500)
    
    @staticmethod
    def update_subscriber(subscriber_id: str):
        """
        Update subscriber in configured provisioning mode(s)
        PUT /api/subscribers/{subscriber_id}
        """
        try:
            data = request.get_json()
            if not data:
                return create_error_response("Request body is required", 400)
            
            # Validate subscriber ID and data
            validator = InputValidator()
            clean_id = validator.sanitize_string(subscriber_id, 50)
            validated_data = validator.validate_subscriber_update_data(data)
            
            # Get provisioning mode
            prov_mode = validated_data.get('provisioning_mode', g.get('prov_mode', 'dual'))
            
            # Update subscriber
            result = subscriber_service.update_subscriber(clean_id, validated_data, prov_mode)
            
            if not result['found']:
                return create_error_response("Subscriber not found", 404)
            
            # Log audit trail
            audit_service.log_action(
                action='subscriber_updated',
                resource='subscriber',
                user=g.current_user.get('username', 'system'),
                details={
                    'uid': clean_id,
                    'provisioning_mode': prov_mode,
                    'updated_fields': list(validated_data.keys()),
                    'result': result['summary']
                }
            )
            
            return create_response(
                data=result,
                message=f"Subscriber updated successfully in {prov_mode} mode"
            )
            
        except ValidationError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error updating subscriber {subscriber_id}: {str(e)}")
            return create_error_response("Failed to update subscriber", 500)
    
    @staticmethod
    def delete_subscriber(subscriber_id: str):
        """
        Delete subscriber from configured provisioning mode(s)
        DELETE /api/subscribers/{subscriber_id}
        """
        try:
            # Validate subscriber ID
            validator = InputValidator()
            clean_id = validator.sanitize_string(subscriber_id, 50)
            
            # Parse query parameters
            soft_delete = request.args.get('soft', 'true').lower() == 'true'
            prov_mode = request.args.get('mode', g.get('prov_mode', 'dual'))
            
            # Delete subscriber
            result = subscriber_service.delete_subscriber(clean_id, soft_delete, prov_mode)
            
            if not result['found']:
                return create_error_response("Subscriber not found", 404)
            
            # Log audit trail
            audit_service.log_action(
                action='subscriber_deleted',
                resource='subscriber',
                user=g.current_user.get('username', 'system'),
                details={
                    'uid': clean_id,
                    'soft_delete': soft_delete,
                    'provisioning_mode': prov_mode,
                    'result': result['summary']
                }
            )
            
            delete_type = "soft deleted" if soft_delete else "permanently deleted"
            return create_response(
                data=result,
                message=f"Subscriber {delete_type} successfully from {prov_mode} mode"
            )
            
        except Exception as e:
            logger.error(f"Error deleting subscriber {subscriber_id}: {str(e)}")
            return create_error_response("Failed to delete subscriber", 500)
    
    @staticmethod
    def bulk_operations():
        """
        Perform bulk operations on subscribers
        POST /api/subscribers/bulk
        """
        try:
            data = request.get_json()
            if not data:
                return create_error_response("Request body is required", 400)
            
            operation = data.get('operation')
            subscriber_ids = data.get('subscriber_ids', [])
            prov_mode = data.get('provisioning_mode', g.get('prov_mode', 'dual'))
            
            # Validate operation type
            if operation not in ['delete', 'activate', 'deactivate', 'suspend']:
                return create_error_response("Invalid operation type", 400)
            
            # Validate subscriber IDs
            if not subscriber_ids or len(subscriber_ids) > 1000:
                return create_error_response("Invalid subscriber IDs (max 1000)", 400)
            
            # Perform bulk operation
            if operation == 'delete':
                soft_delete = data.get('soft_delete', True)
                result = subscriber_service.bulk_delete(subscriber_ids, soft_delete, prov_mode)
            else:
                result = subscriber_service.bulk_status_update(subscriber_ids, operation.upper(), prov_mode)
            
            # Log audit trail
            audit_service.log_action(
                action=f'bulk_{operation}',
                resource='subscriber',
                user=g.current_user.get('username', 'system'),
                details={
                    'operation': operation,
                    'count': len(subscriber_ids),
                    'provisioning_mode': prov_mode,
                    'result': result['summary']
                }
            )
            
            return create_response(
                data=result,
                message=f"Bulk {operation} completed: {result['summary']['successful']} successful, {result['summary']['failed']} failed"
            )
            
        except Exception as e:
            logger.error(f"Error in bulk operations: {str(e)}")
            return create_error_response("Failed to perform bulk operation", 500)
    
    @staticmethod
    def get_provisioning_config():
        """
        Get current provisioning configuration
        GET /api/subscribers/provisioning-config
        """
        try:
            config = subscriber_service.get_provisioning_config()
            return create_response(data=config)
            
        except Exception as e:
            logger.error(f"Error getting provisioning config: {str(e)}")
            return create_error_response("Failed to get provisioning configuration", 500)
    
    @staticmethod
    def set_provisioning_mode():
        """
        Set provisioning mode (admin only)
        POST /api/subscribers/provisioning-mode
        """
        try:
            data = request.get_json()
            new_mode = data.get('mode')
            
            if new_mode not in ['legacy', 'cloud', 'dual']:
                return create_error_response("Invalid provisioning mode", 400)
            
            # Check admin permissions
            if 'admin' not in g.current_user.get('permissions', []):
                return create_error_response("Admin permissions required", 403)
            
            # Update provisioning mode
            result = subscriber_service.set_provisioning_mode(new_mode)
            
            # Log audit trail
            audit_service.log_action(
                action='provisioning_mode_changed',
                resource='configuration',
                user=g.current_user.get('username'),
                details={
                    'old_mode': result['previous_mode'],
                    'new_mode': new_mode
                }
            )
            
            return create_response(
                data=result,
                message=f"Provisioning mode updated to {new_mode}"
            )
            
        except Exception as e:
            logger.error(f"Error setting provisioning mode: {str(e)}")
            return create_error_response("Failed to update provisioning mode", 500)
    
    @staticmethod
    def get_system_stats():
        """
        Get subscriber statistics across both systems
        GET /api/subscribers/stats
        """
        try:
            stats = subscriber_service.get_system_statistics()
            return create_response(data=stats)
            
        except Exception as e:
            logger.error(f"Error getting system stats: {str(e)}")
            return create_error_response("Failed to get system statistics", 500)
    
    @staticmethod
    def compare_systems():
        """
        Compare data consistency between legacy and cloud systems
        POST /api/subscribers/compare
        """
        try:
            data = request.get_json() or {}
            sample_size = min(data.get('sample_size', 100), 1000)
            
            # Run comparison
            result = subscriber_service.compare_systems(sample_size)
            
            # Log audit trail
            audit_service.log_action(
                action='system_comparison',
                resource='subscriber',
                user=g.current_user.get('username', 'system'),
                details={
                    'sample_size': sample_size,
                    'matches': result['summary']['matches'],
                    'discrepancies': result['summary']['discrepancies']
                }
            )
            
            return create_response(
                data=result,
                message=f"System comparison completed - {result['summary']['accuracy']}% accuracy"
            )
            
        except Exception as e:
            logger.error(f"Error comparing systems: {str(e)}")
            return create_error_response("Failed to compare systems", 500)
    
    @staticmethod
    def export_subscribers():
        """
        Export subscribers from specified system(s)
        GET /api/subscribers/export?system=&format=&filters=
        """
        try:
            # Parse parameters
            system = request.args.get('system', 'all')  # all, cloud, legacy
            format_type = request.args.get('format', 'csv')  # csv, json
            status_filter = request.args.get('status', 'all')
            limit = min(int(request.args.get('limit', 10000)), 50000)
            
            # Validate parameters
            if system not in ['all', 'cloud', 'legacy']:
                return create_error_response("Invalid system parameter", 400)
            
            if format_type not in ['csv', 'json']:
                return create_error_response("Invalid format parameter", 400)
            
            # Build export criteria
            export_criteria = {
                'system': system,
                'format': format_type,
                'status': status_filter if status_filter != 'all' else None,
                'limit': limit
            }
            
            # Generate export
            export_result = subscriber_service.export_subscribers(export_criteria)
            
            # Log audit trail
            audit_service.log_action(
                action='subscribers_exported',
                resource='subscriber',
                user=g.current_user.get('username', 'system'),
                details={
                    'system': system,
                    'format': format_type,
                    'count': export_result['count'],
                    'criteria': export_criteria
                }
            )
            
            # Return file response
            from flask import make_response
            
            response = make_response(export_result['content'])
            
            if format_type == 'csv':
                response.headers['Content-Type'] = 'text/csv; charset=utf-8'\n                response.headers['Content-Disposition'] = f'attachment; filename=subscribers_{system}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'\n            else:\n                response.headers['Content-Type'] = 'application/json'\n                response.headers['Content-Disposition'] = f'attachment; filename=subscribers_{system}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'\n            \n            return response\n            
        except Exception as e:\n            logger.error(f"Error exporting subscribers: {str(e)}")\n            return create_error_response("Failed to export subscribers", 500)\n    \n    @staticmethod\n    def upload_csv():\n        \"\"\"\n        Upload CSV file for bulk subscriber creation\n        POST /api/subscribers/upload\n        \"\"\"\n        try:\n            # Check if file was uploaded\n            if 'file' not in request.files:\n                return create_error_response("No file uploaded", 400)\n            \n            file = request.files['file']\n            if file.filename == '':\n                return create_error_response("No file selected", 400)\n            \n            # Validate file type\n            if not file.filename.lower().endswith('.csv'):\n                return create_error_response("Only CSV files are supported", 400)\n            \n            # Get provisioning mode from form data\n            prov_mode = request.form.get('provisioning_mode', g.get('prov_mode', 'dual'))\n            \n            # Process CSV upload\n            result = subscriber_service.process_csv_upload(file, prov_mode)\n            \n            # Log audit trail\n            audit_service.log_action(\n                action='csv_uploaded',\n                resource='subscriber',\n                user=g.current_user.get('username', 'system'),\n                details={\n                    'filename': file.filename,\n                    'provisioning_mode': prov_mode,\n                    'total_rows': result['summary']['total'],\n                    'successful': result['summary']['successful'],\n                    'failed': result['summary']['failed']\n                }\n            )\n            \n            return create_response(\n                data=result,\n                message=f"CSV processed: {result['summary']['successful']} successful, {result['summary']['failed']} failed"\n            )\n            \n        except Exception as e:\n            logger.error(f"Error processing CSV upload: {str(e)}")\n            return create_error_response("Failed to process CSV upload", 500)

# Export controller instance
subscriber_controller = SubscriberController()