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
    """
    return SubscriberController.create_subscriber()

@subscriber_bp.route('', methods=['GET'])
@require_auth(['read'])
@rate_limit("100 per minute")
def get_subscribers():
    """Get subscribers with filtering and pagination"""
    return SubscriberController.get_subscribers()

@subscriber_bp.route('/<string:subscriber_id>', methods=['GET'])
@require_auth(['read'])
@rate_limit("50 per minute")
def get_subscriber(subscriber_id):
    """Get single subscriber by ID"""
    return SubscriberController.get_subscriber_by_id(subscriber_id)

@subscriber_bp.route('/<string:subscriber_id>', methods=['PUT'])
@require_auth(['write'])
@rate_limit("30 per minute")
def update_subscriber(subscriber_id):
    """Update subscriber"""
    return SubscriberController.update_subscriber(subscriber_id)

@subscriber_bp.route('/<string:subscriber_id>', methods=['DELETE'])
@require_auth(['delete'])
@rate_limit("10 per minute")
def delete_subscriber(subscriber_id):
    """Delete subscriber"""
    return SubscriberController.delete_subscriber(subscriber_id)

# Bulk Operations
@subscriber_bp.route('/bulk', methods=['POST'])
@require_auth(['write'])
@rate_limit("5 per minute")
def bulk_operations():
    """Perform bulk operations on subscribers"""
    return SubscriberController.bulk_operations()

# CSV Upload
@subscriber_bp.route('/upload', methods=['POST'])
@require_auth(['write'])
@rate_limit("2 per minute")
def upload_csv():
    """Upload CSV file for bulk subscriber creation"""
    return SubscriberController.upload_csv()

# Export
@subscriber_bp.route('/export', methods=['GET'])
@require_auth(['read'])
@rate_limit("3 per minute")
def export_subscribers():
    """Export subscribers to CSV/JSON"""
    return SubscriberController.export_subscribers()

# Statistics
@subscriber_bp.route('/stats', methods=['GET'])
@require_auth(['read'])
@rate_limit("30 per minute")
def get_stats():
    """Get subscriber statistics across both systems"""
    return SubscriberController.get_system_stats()

# System Comparison
@subscriber_bp.route('/compare', methods=['POST'])
@require_auth(['read'])
@rate_limit("5 per minute")
def compare_systems():
    """Compare data consistency between legacy and cloud systems"""
    return SubscriberController.compare_systems()

# Provisioning Configuration
@subscriber_bp.route('/provisioning-config', methods=['GET'])
@require_auth(['read'])
@rate_limit("20 per minute")
def get_provisioning_config():
    """Get current provisioning configuration"""
    return SubscriberController.get_provisioning_config()

@subscriber_bp.route('/provisioning-mode', methods=['POST'])
@require_auth(['admin'])
@rate_limit("5 per minute")
def set_provisioning_mode():
    """Set provisioning mode (admin only)"""
    return SubscriberController.set_provisioning_mode()

# Error handlers for this blueprint
@subscriber_bp.errorhandler(400)
def handle_bad_request(error):
    return {
        'status': 'error',
        'message': 'Invalid request data',
        'timestamp': '2025-10-29T13:26:00Z',
    }, 400

@subscriber_bp.errorhandler(404)
def handle_not_found(error):
    return {
        'status': 'error',
        'message': 'Subscriber not found',
        'timestamp': '2025-10-29T13:26:00Z',
    }, 404

@subscriber_bp.errorhandler(409)
def handle_conflict(error):
    return {
        'status': 'error',
        'message': 'Subscriber already exists',
        'timestamp': '2025-10-29T13:26:00Z',
    }, 409

# Export blueprint
subscribers_routes = subscriber_bp
