#!/usr/bin/env python3
"""
Subscriber Routes - API Endpoints for Subscriber Management
Handles all subscriber-related HTTP routes with dual database support
"""

from flask import Blueprint
from middleware.auth import require_auth
from middleware.rate_limiter import rate_limit
from controllers.subscribers.controller import SubscriberController

# Create blueprint
subscriber_bp = Blueprint('subscribers', __name__, url_prefix='/api/subscribers')

# CRUD Operations
@subscriber_bp.route('', methods=['POST'])
@require_auth(['write'])
@rate_limit("20 per minute")
def create_subscriber():
    """
    Create new subscriber
    POST /api/subscribers
    
    Body:
    {
        "uid": "USER001",
        "imsi": "123456789012345",
        "msisdn": "+1234567890",
        "status": "ACTIVE",
        "provisioning_mode": "dual",
        "apn": "internet",
        "service_profile": "premium",
        "roaming_allowed": true,
        "data_limit": 10000
    }
    """
    return SubscriberController.create_subscriber()

@subscriber_bp.route('', methods=['GET'])
@require_auth(['read'])
@rate_limit("100 per minute")
def get_subscribers():
    """
    Get subscribers with filtering and pagination
    GET /api/subscribers?search=&status=&source=&limit=&offset=&sort=&order=
    
    Query Parameters:
    - search: Search term for UID/IMSI/MSISDN
    - status: Filter by status (all, ACTIVE, INACTIVE, SUSPENDED, DELETED)
    - source: Filter by source (all, cloud, legacy)
    - limit: Number of results (max 100, default 50)
    - offset: Pagination offset (default 0)
    - sort: Sort field (created_at, updated_at, status, uid)
    - order: Sort order (asc, desc)
    """
    return SubscriberController.get_subscribers()

@subscriber_bp.route('/<string:subscriber_id>', methods=['GET'])
@require_auth(['read'])
@rate_limit("50 per minute")
def get_subscriber(subscriber_id):
    """
    Get single subscriber by ID
    GET /api/subscribers/{subscriber_id}
    """
    return SubscriberController.get_subscriber_by_id(subscriber_id)

@subscriber_bp.route('/<string:subscriber_id>', methods=['PUT'])
@require_auth(['write'])
@rate_limit("30 per minute")
def update_subscriber(subscriber_id):
    """
    Update subscriber
    PUT /api/subscribers/{subscriber_id}
    
    Body:
    {
        "status": "INACTIVE",
        "msisdn": "+1234567891",
        "apn": "internet2",
        "provisioning_mode": "dual"
    }
    """
    return SubscriberController.update_subscriber(subscriber_id)

@subscriber_bp.route('/<string:subscriber_id>', methods=['DELETE'])
@require_auth(['delete'])
@rate_limit("10 per minute")
def delete_subscriber(subscriber_id):
    """
    Delete subscriber
    DELETE /api/subscribers/{subscriber_id}?soft=true&mode=dual
    
    Query Parameters:
    - soft: Soft delete (true) or hard delete (false)
    - mode: Provisioning mode (legacy, cloud, dual)
    """
    return SubscriberController.delete_subscriber(subscriber_id)

# Bulk Operations
@subscriber_bp.route('/bulk', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def bulk_operations():
    """
    Perform bulk operations on subscribers
    POST /api/subscribers/bulk
    
    Body:
    {
        "operation": "delete",  // delete, activate, deactivate, suspend
        "subscriber_ids": ["USER001", "USER002", "USER003"],
        "provisioning_mode": "dual",
        "soft_delete": true  // only for delete operation
    }
    """
    return SubscriberController.bulk_operations()

# CSV Upload
@subscriber_bp.route('/upload', methods=['POST'])
@require_auth(['write'])
@rate_limit("2 per minute")
def upload_csv():
    """
    Upload CSV file for bulk subscriber creation
    POST /api/subscribers/upload
    
    Form Data:
    - file: CSV file with subscriber data
    - provisioning_mode: Target system (legacy, cloud, dual)
    
    CSV Format:
    uid,imsi,msisdn,status,apn,service_profile
    USER001,123456789012345,+1234567890,ACTIVE,internet,premium
    """
    return SubscriberController.upload_csv()

# Export
@subscriber_bp.route('/export', methods=['GET'])
@require_auth(['read'])
@rate_limit("3 per minute")
def export_subscribers():
    """
    Export subscribers to CSV/JSON
    GET /api/subscribers/export?system=all&format=csv&status=all&limit=10000
    
    Query Parameters:
    - system: Source system (all, cloud, legacy)
    - format: Export format (csv, json)
    - status: Status filter (all, ACTIVE, INACTIVE, etc.)
    - limit: Maximum records (max 50000)
    """
    return SubscriberController.export_subscribers()

# Statistics
@subscriber_bp.route('/stats', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_stats():
    """
    Get subscriber statistics across both systems
    GET /api/subscribers/stats
    
    Response:
    {
        "cloud": {"total": 1500, "active": 1200, "inactive": 300},
        "legacy": {"total": 800, "active": 600, "inactive": 200},
        "combined": {"total": 2300, "active": 1800, "inactive": 500}
    }
    """
    return SubscriberController.get_system_stats()

# System Comparison
@subscriber_bp.route('/compare', methods=['POST'])
@require_auth(['read'])
@rate_limit("5 per minute")
def compare_systems():
    """
    Compare data consistency between legacy and cloud systems
    POST /api/subscribers/compare
    
    Body:
    {
        "sample_size": 1000  // Number of records to compare (max 10000)
    }
    
    Response:
    {
        "total_compared": 1000,
        "matches": 950,
        "discrepancies": 50,
        "accuracy": 95.0,
        "discrepancies_detail": [...]
    }
    """
    return SubscriberController.compare_systems()

# Provisioning Configuration
@subscriber_bp.route('/provisioning-config', methods=['GET'])
@require_auth(['read'])
@rate_limit("20 per minute")
def get_provisioning_config():
    """
    Get current provisioning configuration
    GET /api/subscribers/provisioning-config
    
    Response:
    {
        "current_mode": "dual",
        "available_modes": ["legacy", "cloud", "dual"],
        "mode_descriptions": {...},
        "system_status": {...}
    }
    """
    return SubscriberController.get_provisioning_config()

@subscriber_bp.route('/provisioning-mode', methods=['POST'])
@require_auth(['admin'])
@rate_limit("5 per minute")
def set_provisioning_mode():
    """
    Set provisioning mode (admin only)
    POST /api/subscribers/provisioning-mode
    
    Body:
    {
        "mode": "dual"  // legacy, cloud, dual
    }
    """
    return SubscriberController.set_provisioning_mode()

# Error handlers for this blueprint
@subscriber_bp.errorhandler(400)
def handle_bad_request(error):
    return {
        'status': 'error',
        'message': 'Invalid request data',
        'timestamp': '2025-10-29T13:26:00Z'
    }, 400

@subscriber_bp.errorhandler(404)
def handle_not_found(error):
    return {
        'status': 'error',
        'message': 'Subscriber not found',
        'timestamp': '2025-10-29T13:26:00Z'
    }, 404

@subscriber_bp.errorhandler(409)
def handle_conflict(error):
    return {
        'status': 'error',
        'message': 'Subscriber already exists',
        'timestamp': '2025-10-29T13:26:00Z'
    }, 409

# Export blueprint
subscribers_routes = subscriber_bp