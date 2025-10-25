from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import uuid
import json
import csv
import io
import os
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-jwt-secret-here')

# In-memory storage (replace with actual database in production)
class InMemoryStorage:
    def __init__(self):
        self.subscribers = {}
        self.migration_jobs = {}
        self.bulk_operations = {}
        self.audit_logs = []
        self.system_metrics = []
        self.alerts = []
        self.users = {
            'admin': {'password': 'Admin@123', 'role': 'admin'},
            'operator': {'password': 'Operator@123', 'role': 'operator'},
            'guest': {'password': 'Guest@123', 'role': 'guest'}
        }
        
        # Initialize with sample data
        self._initialize_sample_data()
    
    def _initialize_sample_data(self):
        """Initialize with sample subscribers and jobs"""
        # Sample subscribers
        regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1']
        plans = ['basic', 'premium', 'enterprise']
        statuses = ['active', 'inactive', 'suspended']
        
        for i in range(500):
            subscriber_id = f"SUB_{str(i+1).zfill(6)}"
            self.subscribers[subscriber_id] = {
                'subscriber_id': subscriber_id,
                'name': f'User {i+1}',
                'email': f'user{i+1}@example.com',
                'phone': f'+1-555-{str(i+1).zfill(4)}',
                'plan': random.choice(plans),
                'status': random.choice(statuses),
                'region': random.choice(regions),
                'system': random.choice(['cloud', 'legacy']),
                'created_date': (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
                'last_updated': (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat()
            }
        
        # Sample migration jobs
        job_statuses = ['completed', 'running', 'pending', 'failed']
        priorities = ['low', 'medium', 'high', 'critical']
        
        for i in range(20):
            job_id = str(uuid.uuid4())
            created_time = datetime.now() - timedelta(days=random.randint(1, 30))
            
            self.migration_jobs[job_id] = {
                'job_id': job_id,
                'name': f'Migration Job {i+1}',
                'description': f'Bulk migration of subscriber batch {i+1}',
                'status': random.choice(job_statuses),
                'priority': random.choice(priorities),
                'progress': random.randint(0, 100),
                'source': 'legacy',
                'destination': 'cloud',
                'created_timestamp': created_time.isoformat(),
                'created_by': random.choice(['admin', 'operator']),
                'total_records': random.randint(100, 10000),
                'processed_records': random.randint(0, 10000),
                'successful_records': random.randint(0, 9500),
                'failed_records': random.randint(0, 500),
                'batch_size': 100,
                'retry_attempts': 3
            }

storage = InMemoryStorage()

# Data Models
@dataclass
class Subscriber:
    subscriber_id: str
    name: str
    email: str
    phone: str = ''
    plan: str = 'basic'
    status: str = 'active'
    region: str = 'us-east-1'
    system: str = 'cloud'
    created_date: str = ''
    last_updated: str = ''

@dataclass
class MigrationJob:
    job_id: str
    name: str
    description: str = ''
    status: str = 'pending'
    priority: str = 'medium'
    progress: int = 0
    source: str = 'legacy'
    destination: str = 'cloud'
    created_timestamp: str = ''
    created_by: str = ''
    total_records: int = 0
    processed_records: int = 0
    successful_records: int = 0
    failed_records: int = 0
    batch_size: int = 100
    retry_attempts: int = 3

# Utility functions
def generate_id(prefix='ID'):
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"

def validate_required_fields(data, required_fields):
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

def paginate_results(items, page=1, per_page=10):
    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = items[start:end]
    
    return {
        'items': paginated_items,
        'total': len(items),
        'page': page,
        'per_page': per_page,
        'pages': (len(items) + per_page - 1) // per_page
    }

# Authentication endpoints
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'operator')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        user = storage.users.get(username)
        if not user or user['password'] != password:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Generate a simple token (use proper JWT in production)
        token = f"token_{username}_{uuid.uuid4().hex[:16]}"
        
        return jsonify({
            'token': token,
            'user': {
                'username': username,
                'role': user['role']
            }
        })
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    # Simple token validation (implement proper JWT validation in production)
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401
    
    token = auth_header.split(' ')[1]
    if not token.startswith('token_'):
        return jsonify({'error': 'Invalid token'}), 401
    
    username = token.split('_')[1]
    user = storage.users.get(username)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'username': username,
        'role': user['role']
    })

# Dashboard endpoints
@app.route('/api/dashboard/stats', methods=['GET'])
def get_global_stats():
    try:
        active_migrations = sum(1 for job in storage.migration_jobs.values() if job['status'] == 'running')
        total_subscribers = len(storage.subscribers)
        completed_today = sum(1 for job in storage.migration_jobs.values() 
                            if job['status'] == 'completed' and 
                            datetime.fromisoformat(job['created_timestamp']).date() == datetime.now().date())
        
        return jsonify({
            'totalSubscribers': total_subscribers,
            'migrationJobs': len(storage.migration_jobs),
            'provisioningOperations': random.randint(50, 200),
            'systemHealth': random.randint(95, 100),
            'activeMigrations': active_migrations,
            'completedToday': completed_today,
            'successRate': random.randint(95, 100)
        })
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        return jsonify({'error': 'Failed to load stats'}), 500

@app.route('/api/dashboard/overview', methods=['GET'])
def get_dashboard_overview():
    try:
        return jsonify({
            'totalSubscribers': len(storage.subscribers),
            'activeMigrations': sum(1 for job in storage.migration_jobs.values() if job['status'] == 'running'),
            'completedMigrations': sum(1 for job in storage.migration_jobs.values() if job['status'] == 'completed'),
            'systemHealth': random.randint(95, 100)
        })
    except Exception as e:
        logger.error(f"Dashboard overview error: {str(e)}")
        return jsonify({'error': 'Failed to load dashboard overview'}), 500

@app.route('/api/dashboard/activity', methods=['GET'])
def get_recent_activity():
    try:
        # Generate recent activity based on migration jobs
        activities = []
        for job in list(storage.migration_jobs.values())[-10:]:
            activities.append({
                'type': 'migration',
                'title': job['name'],
                'description': f"Processed {job.get('processed_records', 0)} records",
                'status': job['status'],
                'timestamp': job['created_timestamp']
            })
        
        return jsonify(activities)
    except Exception as e:
        logger.error(f"Activity error: {str(e)}")
        return jsonify([])

@app.route('/api/dashboard/trends', methods=['GET'])
def get_migration_trends():
    try:
        time_range = request.args.get('range', '30d')
        days = 30 if time_range == '30d' else 7
        
        trends = []
        for i in range(days, -1, -1):
            date = datetime.now() - timedelta(days=i)
            trends.append({
                'date': date.strftime('%Y-%m-%d'),
                'migrations': random.randint(10, 50),
                'successful': random.randint(85, 99),
                'failed': random.randint(1, 15)
            })
        
        return jsonify(trends)
    except Exception as e:
        logger.error(f"Trends error: {str(e)}")
        return jsonify([])

@app.route('/api/dashboard/system-stats', methods=['GET'])
def get_system_statistics():
    try:
        return jsonify([
            {'name': 'Cloud System', 'value': len([s for s in storage.subscribers.values() if s.get('system') == 'cloud'])},
            {'name': 'Legacy System', 'value': len([s for s in storage.subscribers.values() if s.get('system') == 'legacy'])},
            {'name': 'Active', 'value': len([s for s in storage.subscribers.values() if s.get('status') == 'active'])},
            {'name': 'Inactive', 'value': len([s for s in storage.subscribers.values() if s.get('status') != 'active'])}
        ])
    except Exception as e:
        logger.error(f"System stats error: {str(e)}")
        return jsonify([])

# Subscriber management endpoints
@app.route('/api/subscribers', methods=['GET'])
def get_subscribers():
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        search = request.args.get('search', '')
        status = request.args.get('status', 'all')
        plan = request.args.get('plan', 'all')
        region = request.args.get('region', 'all')
        provisioning_mode = request.args.get('provisioning_mode', 'cloud')
        
        # Filter subscribers
        filtered_subscribers = list(storage.subscribers.values())
        
        if search:
            filtered_subscribers = [
                s for s in filtered_subscribers 
                if search.lower() in s['name'].lower() or 
                   search.lower() in s['email'].lower() or 
                   search.lower() in s['subscriber_id'].lower()
            ]
        
        if status != 'all':
            filtered_subscribers = [s for s in filtered_subscribers if s['status'] == status]
        
        if plan != 'all':
            filtered_subscribers = [s for s in filtered_subscribers if s['plan'] == plan]
        
        if region != 'all':
            filtered_subscribers = [s for s in filtered_subscribers if s['region'] == region]
        
        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_subscribers = filtered_subscribers[start_idx:end_idx]
        
        return jsonify({
            'subscribers': paginated_subscribers,
            'total': len(filtered_subscribers),
            'page': page,
            'limit': limit
        })
    
    except Exception as e:
        logger.error(f"Get subscribers error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve subscribers'}), 500

@app.route('/api/subscribers', methods=['POST'])
def create_subscriber():
    try:
        data = request.get_json()
        validate_required_fields(data, ['subscriber_id', 'name', 'email'])
        
        subscriber_id = data['subscriber_id']
        if subscriber_id in storage.subscribers:
            return jsonify({'error': 'Subscriber ID already exists'}), 400
        
        subscriber_data = {
            'subscriber_id': subscriber_id,
            'name': data['name'],
            'email': data['email'],
            'phone': data.get('phone', ''),
            'plan': data.get('plan', 'basic'),
            'status': data.get('status', 'active'),
            'region': data.get('region', 'us-east-1'),
            'system': data.get('provisioning_mode', 'cloud'),
            'created_date': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        storage.subscribers[subscriber_id] = subscriber_data
        
        return jsonify({
            'message': 'Subscriber created successfully',
            'subscriber': subscriber_data
        }), 201
    
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Create subscriber error: {str(e)}")
        return jsonify({'error': 'Failed to create subscriber'}), 500

@app.route('/api/subscribers/<subscriber_id>', methods=['PUT'])
def update_subscriber(subscriber_id):
    try:
        if subscriber_id not in storage.subscribers:
            return jsonify({'error': 'Subscriber not found'}), 404
        
        data = request.get_json()
        subscriber = storage.subscribers[subscriber_id]
        
        # Update allowed fields
        updatable_fields = ['name', 'email', 'phone', 'plan', 'status', 'region']
        for field in updatable_fields:
            if field in data:
                subscriber[field] = data[field]
        
        subscriber['last_updated'] = datetime.now().isoformat()
        
        return jsonify({
            'message': 'Subscriber updated successfully',
            'subscriber': subscriber
        })
    
    except Exception as e:
        logger.error(f"Update subscriber error: {str(e)}")
        return jsonify({'error': 'Failed to update subscriber'}), 500

@app.route('/api/subscribers/<subscriber_id>', methods=['DELETE'])
def delete_subscriber(subscriber_id):
    try:
        if subscriber_id not in storage.subscribers:
            return jsonify({'error': 'Subscriber not found'}), 404
        
        del storage.subscribers[subscriber_id]
        
        return jsonify({'message': 'Subscriber deleted successfully'})
    
    except Exception as e:
        logger.error(f"Delete subscriber error: {str(e)}")
        return jsonify({'error': 'Failed to delete subscriber'}), 500

@app.route('/api/subscribers/export', methods=['GET'])
def export_subscribers():
    try:
        # Apply same filtering as GET /subscribers
        search = request.args.get('search', '')
        status = request.args.get('status', 'all')
        plan = request.args.get('plan', 'all')
        provisioning_mode = request.args.get('provisioning_mode', 'all')
        
        filtered_subscribers = list(storage.subscribers.values())
        
        if search:
            filtered_subscribers = [
                s for s in filtered_subscribers 
                if search.lower() in s['name'].lower() or search.lower() in s['email'].lower()
            ]
        
        if status != 'all':
            filtered_subscribers = [s for s in filtered_subscribers if s['status'] == status]
        
        if plan != 'all':
            filtered_subscribers = [s for s in filtered_subscribers if s['plan'] == plan]
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Subscriber ID', 'Name', 'Email', 'Phone', 'Plan', 'Status', 'Region', 'System'])
        
        # Write data
        for subscriber in filtered_subscribers:
            writer.writerow([
                subscriber['subscriber_id'],
                subscriber['name'],
                subscriber['email'],
                subscriber.get('phone', ''),
                subscriber['plan'],
                subscriber['status'],
                subscriber['region'],
                subscriber.get('system', 'cloud')
            ])
        
        # Return CSV as response
        csv_data = output.getvalue()
        response = app.response_class(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=subscribers.csv'}
        )
        return response
    
    except Exception as e:
        logger.error(f"Export subscribers error: {str(e)}")
        return jsonify({'error': 'Failed to export subscribers'}), 500

# Migration management endpoints
@app.route('/api/migration/jobs', methods=['GET'])
def get_migration_jobs():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        status = request.args.get('status', 'all')
        priority = request.args.get('priority', 'all')
        
        filtered_jobs = list(storage.migration_jobs.values())
        
        if status != 'all':
            filtered_jobs = [job for job in filtered_jobs if job['status'] == status]
        
        if priority != 'all':
            filtered_jobs = [job for job in filtered_jobs if job['priority'] == priority]
        
        # Sort by creation time (newest first)
        filtered_jobs.sort(key=lambda x: x['created_timestamp'], reverse=True)
        
        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_jobs = filtered_jobs[start_idx:end_idx]
        
        return jsonify({
            'jobs': paginated_jobs,
            'total': len(filtered_jobs)
        })
    
    except Exception as e:
        logger.error(f"Get migration jobs error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve migration jobs'}), 500

@app.route('/api/migration/jobs', methods=['POST'])
def create_migration_job():
    try:
        # Handle file upload
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        config = json.loads(request.form.get('config', '{}'))
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Process CSV file
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'Only CSV files are supported'}), 400
        
        # Create migration job
        job_id = str(uuid.uuid4())
        job_data = {
            'job_id': job_id,
            'name': config.get('name', f'Migration Job {len(storage.migration_jobs) + 1}'),
            'description': config.get('description', ''),
            'status': 'pending',
            'priority': config.get('priority', 'medium'),
            'progress': 0,
            'source': config.get('source', 'legacy'),
            'destination': config.get('destination', 'cloud'),
            'created_timestamp': datetime.now().isoformat(),
            'created_by': config.get('created_by', 'system'),
            'total_records': 0,
            'processed_records': 0,
            'successful_records': 0,
            'failed_records': 0,
            'batch_size': config.get('batchSize', 100),
            'retry_attempts': config.get('retryAttempts', 3)
        }
        
        # Read CSV and count records
        try:
            csv_content = file.read().decode('utf-8')
            csv_reader = csv.reader(io.StringIO(csv_content))
            rows = list(csv_reader)
            job_data['total_records'] = len(rows) - 1  # Exclude header
        except Exception as e:
            logger.error(f"CSV processing error: {str(e)}")
            job_data['total_records'] = 100  # Default estimate
        
        storage.migration_jobs[job_id] = job_data
        
        # Start background processing
        threading.Thread(target=simulate_migration_processing, args=(job_id,)).start()
        
        return jsonify({
            'job_id': job_id,
            'message': 'Migration job created successfully',
            'job': job_data
        }), 201
    
    except Exception as e:
        logger.error(f"Create migration job error: {str(e)}")
        return jsonify({'error': 'Failed to create migration job'}), 500

def simulate_migration_processing(job_id):
    """Simulate migration job processing in background"""
    try:
        job = storage.migration_jobs.get(job_id)
        if not job:
            return
        
        # Update status to running
        job['status'] = 'running'
        
        total_records = job['total_records']
        batch_size = job['batch_size']
        
        processed = 0
        successful = 0
        failed = 0
        
        while processed < total_records:
            # Simulate processing time
            time.sleep(random.uniform(0.5, 2.0))
            
            # Process a batch
            batch_processed = min(batch_size, total_records - processed)
            batch_successful = random.randint(int(batch_processed * 0.8), batch_processed)
            batch_failed = batch_processed - batch_successful
            
            processed += batch_processed
            successful += batch_successful
            failed += batch_failed
            
            # Update progress
            progress = int((processed / total_records) * 100)
            job['progress'] = progress
            job['processed_records'] = processed
            job['successful_records'] = successful
            job['failed_records'] = failed
            
            logger.info(f"Job {job_id} progress: {progress}%")
        
        # Mark as completed
        job['status'] = 'completed' if failed < total_records * 0.1 else 'failed'
        logger.info(f"Job {job_id} completed with status: {job['status']}")
        
    except Exception as e:
        logger.error(f"Migration processing error for job {job_id}: {str(e)}")
        if job_id in storage.migration_jobs:
            storage.migration_jobs[job_id]['status'] = 'failed'

@app.route('/api/migration/jobs/<job_id>/details', methods=['GET'])
def get_migration_job_details(job_id):
    try:
        if job_id not in storage.migration_jobs:
            return jsonify({'error': 'Job not found'}), 404
        
        job = storage.migration_jobs[job_id]
        return jsonify(job)
    
    except Exception as e:
        logger.error(f"Get job details error: {str(e)}")
        return jsonify({'error': 'Failed to get job details'}), 500

@app.route('/api/migration/jobs/<job_id>/<action>', methods=['POST'])
def control_migration_job(job_id, action):
    try:
        if job_id not in storage.migration_jobs:
            return jsonify({'error': 'Job not found'}), 404
        
        job = storage.migration_jobs[job_id]
        
        if action == 'pause':
            if job['status'] == 'running':
                job['status'] = 'paused'
        elif action == 'resume':
            if job['status'] == 'paused':
                job['status'] = 'running'
        elif action == 'stop':
            if job['status'] in ['running', 'paused', 'pending']:
                job['status'] = 'cancelled'
        else:
            return jsonify({'error': 'Invalid action'}), 400
        
        return jsonify({'message': f'Job {action} successful', 'job': job})
    
    except Exception as e:
        logger.error(f"Control job error: {str(e)}")
        return jsonify({'error': f'Failed to {action} job'}), 500

@app.route('/api/migration/stats', methods=['GET'])
def get_migration_stats():
    try:
        jobs = list(storage.migration_jobs.values())
        
        return jsonify({
            'activeMigrations': len([j for j in jobs if j['status'] == 'running']),
            'completedToday': len([j for j in jobs if j['status'] == 'completed']),
            'totalRecords': sum(j.get('total_records', 0) for j in jobs),
            'successRate': random.randint(95, 100)
        })
    
    except Exception as e:
        logger.error(f"Migration stats error: {str(e)}")
        return jsonify({
            'activeMigrations': 0,
            'completedToday': 0,
            'totalRecords': 0,
            'successRate': 0
        })

# Bulk operations endpoints
@app.route('/api/bulk/operations', methods=['GET'])
def get_bulk_operations():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        
        # Generate some sample bulk operations
        operations = []
        for i in range(10):
            operation_id = str(uuid.uuid4())
            operations.append({
                'operation_id': operation_id,
                'name': f'Bulk Operation {i+1}',
                'operation_type': random.choice(['bulk_delete', 'bulk_audit']),
                'status': random.choice(['pending', 'running', 'completed', 'failed']),
                'progress': random.randint(0, 100),
                'created_timestamp': (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
                'total_records': random.randint(100, 5000),
                'processed_records': random.randint(0, 5000),
                'successful_records': random.randint(0, 4500),
                'failed_records': random.randint(0, 500)
            })
        
        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_operations = operations[start_idx:end_idx]
        
        return jsonify({
            'operations': paginated_operations,
            'total': len(operations)
        })
    
    except Exception as e:
        logger.error(f"Get bulk operations error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve bulk operations'}), 500

@app.route('/api/bulk/operations', methods=['POST'])
def create_bulk_operation():
    try:
        # Handle file upload for bulk delete
        if 'file' in request.files:
            file = request.files['file']
            config = json.loads(request.form.get('config', '{}'))
            
            operation_id = str(uuid.uuid4())
            operation_data = {
                'operation_id': operation_id,
                'name': config.get('name', 'Bulk Delete Operation'),
                'operation_type': 'bulk_delete',
                'status': 'pending',
                'progress': 0,
                'created_timestamp': datetime.now().isoformat(),
                'system': config.get('system', 'cloud')
            }
            
            storage.bulk_operations[operation_id] = operation_data
            
            return jsonify({
                'operation_id': operation_id,
                'message': 'Bulk delete operation created successfully'
            }), 201
        
        return jsonify({'error': 'No file provided'}), 400
    
    except Exception as e:
        logger.error(f"Create bulk operation error: {str(e)}")
        return jsonify({'error': 'Failed to create bulk operation'}), 500

@app.route('/api/bulk/audit', methods=['POST'])
def create_bulk_audit():
    try:
        data = request.get_json()
        
        operation_id = str(uuid.uuid4())
        audit_data = {
            'operation_id': operation_id,
            'name': data.get('name', 'Bulk Audit Operation'),
            'operation_type': 'bulk_audit',
            'status': 'pending',
            'progress': 0,
            'created_timestamp': datetime.now().isoformat(),
            'audit_type': data.get('auditType', 'full_comparison')
        }
        
        storage.bulk_operations[operation_id] = audit_data
        
        # Start background audit processing
        threading.Thread(target=simulate_audit_processing, args=(operation_id,)).start()
        
        return jsonify({
            'operation_id': operation_id,
            'message': 'Bulk audit operation created successfully'
        }), 201
    
    except Exception as e:
        logger.error(f"Create bulk audit error: {str(e)}")
        return jsonify({'error': 'Failed to create bulk audit operation'}), 500

def simulate_audit_processing(operation_id):
    """Simulate audit processing in background"""
    try:
        operation = storage.bulk_operations.get(operation_id)
        if not operation:
            return
        
        operation['status'] = 'running'
        
        # Simulate audit processing
        for progress in range(0, 101, 10):
            time.sleep(random.uniform(0.5, 1.5))
            operation['progress'] = progress
        
        operation['status'] = 'completed'
        logger.info(f"Audit operation {operation_id} completed")
        
    except Exception as e:
        logger.error(f"Audit processing error for operation {operation_id}: {str(e)}")
        if operation_id in storage.bulk_operations:
            storage.bulk_operations[operation_id]['status'] = 'failed'

# Data query endpoints
@app.route('/api/data/query', methods=['POST'])
def query_subscribers():
    try:
        data = request.get_json()
        page = data.get('page', 1)
        limit = data.get('limit', 25)
        system = data.get('system', 'cloud')
        search_term = data.get('searchTerm', '')
        
        filtered_subscribers = list(storage.subscribers.values())
        
        # Apply system filter
        if system != 'both':
            filtered_subscribers = [s for s in filtered_subscribers if s.get('system') == system]
        
        # Apply search filter
        if search_term:
            filtered_subscribers = [
                s for s in filtered_subscribers 
                if search_term.lower() in s['name'].lower() or 
                   search_term.lower() in s['email'].lower() or
                   search_term.lower() in s['subscriber_id'].lower()
            ]
        
        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_subscribers = filtered_subscribers[start_idx:end_idx]
        
        return jsonify({
            'subscribers': paginated_subscribers,
            'total': len(filtered_subscribers)
        })
    
    except Exception as e:
        logger.error(f"Query subscribers error: {str(e)}")
        return jsonify({'error': 'Failed to query subscribers'}), 500

@app.route('/api/data/system-stats', methods=['GET'])
def get_system_stats():
    try:
        cloud_subscribers = [s for s in storage.subscribers.values() if s.get('system') == 'cloud']
        legacy_subscribers = [s for s in storage.subscribers.values() if s.get('system') == 'legacy']
        
        return jsonify({
            'cloud': {
                'total': len(cloud_subscribers),
                'active': len([s for s in cloud_subscribers if s['status'] == 'active']),
                'inactive': len([s for s in cloud_subscribers if s['status'] != 'active'])
            },
            'legacy': {
                'total': len(legacy_subscribers),
                'active': len([s for s in legacy_subscribers if s['status'] == 'active']),
                'inactive': len([s for s in legacy_subscribers if s['status'] != 'active'])
            }
        })
    
    except Exception as e:
        logger.error(f"System stats error: {str(e)}")
        return jsonify({'error': 'Failed to get system stats'}), 500

@app.route('/api/data/export', methods=['POST'])
def export_subscriber_data():
    try:
        data = request.get_json()
        system = data.get('system', 'cloud')
        format_type = data.get('format', 'csv')
        fields = data.get('fields', [])
        
        filtered_subscribers = list(storage.subscribers.values())
        if system != 'both':
            filtered_subscribers = [s for s in filtered_subscribers if s.get('system') == system]
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            header = [field for field in fields if field in ['subscriber_id', 'name', 'email', 'phone', 'plan', 'status', 'region']]
            writer.writerow(header)
            
            # Write data
            for subscriber in filtered_subscribers:
                row = [subscriber.get(field, '') for field in header]
                writer.writerow(row)
            
            csv_data = output.getvalue()
            response = app.response_class(
                csv_data,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=subscribers_{system}.csv'}
            )
            return response
        
        return jsonify({'error': 'Unsupported export format'}), 400
    
    except Exception as e:
        logger.error(f"Export data error: {str(e)}")
        return jsonify({'error': 'Failed to export data'}), 500

# Monitoring endpoints
@app.route('/api/monitoring/alerts', methods=['GET'])
def get_system_alerts():
    try:
        # Generate sample alerts
        alerts = [
            {
                'title': 'High Memory Usage',
                'message': 'System memory usage is above 85%',
                'severity': 'warning',
                'timestamp': (datetime.now() - timedelta(minutes=15)).isoformat()
            },
            {
                'title': 'Migration Job Failed',
                'message': 'Migration job #12345 failed due to connection timeout',
                'severity': 'high',
                'timestamp': (datetime.now() - timedelta(hours=2)).isoformat()
            }
        ]
        return jsonify(alerts)
    
    except Exception as e:
        logger.error(f"System alerts error: {str(e)}")
        return jsonify([])

@app.route('/api/monitoring/performance', methods=['GET'])
def get_performance_metrics():
    try:
        time_range = request.args.get('range', '24h')
        hours = 24 if time_range == '24h' else 1
        
        metrics = []
        for i in range(hours * 4):  # Every 15 minutes
            timestamp = datetime.now() - timedelta(minutes=i * 15)
            metrics.append({
                'timestamp': timestamp.isoformat(),
                'cpu': random.randint(20, 80),
                'memory': random.randint(30, 90),
                'network': random.randint(10, 60),
                'response_time': random.randint(100, 800),
                'throughput': random.randint(200, 1000)
            })
        
        return jsonify(metrics)
    
    except Exception as e:
        logger.error(f"Performance metrics error: {str(e)}")
        return jsonify([])

@app.route('/api/monitoring/resources', methods=['GET'])
def get_resource_utilization():
    try:
        return jsonify({
            'cpu': random.randint(30, 80),
            'memory': random.randint(40, 85),
            'storage': random.randint(50, 90),
            'network': random.randint(10, 50)
        })
    
    except Exception as e:
        logger.error(f"Resource utilization error: {str(e)}")
        return jsonify({})

@app.route('/api/monitoring/services', methods=['GET'])
def get_service_status():
    try:
        services = [
            {'name': 'Cloud API', 'status': 'healthy', 'health': random.randint(95, 100), 'lastCheck': datetime.now().isoformat()},
            {'name': 'Legacy Database', 'status': 'healthy', 'health': random.randint(90, 98), 'lastCheck': datetime.now().isoformat()},
            {'name': 'Migration Service', 'status': 'healthy', 'health': random.randint(92, 99), 'lastCheck': datetime.now().isoformat()},
            {'name': 'Audit Service', 'status': 'healthy', 'health': random.randint(88, 96), 'lastCheck': datetime.now().isoformat()}
        ]
        return jsonify(services)
    
    except Exception as e:
        logger.error(f"Service status error: {str(e)}")
        return jsonify([])

# Analytics endpoints
@app.route('/api/analytics/overview', methods=['GET'])
def get_analytics_overview():
    try:
        time_range = request.args.get('range', '30d')
        
        return jsonify({
            'totalMigrations': len(storage.migration_jobs),
            'successRate': random.randint(92, 98),
            'avgProcessingTime': round(random.uniform(1.5, 3.5), 1),
            'dataTransferred': random.randint(500, 2000),
            'trends': {
                'migrationsChange': random.uniform(-5, 15),
                'successRateChange': random.uniform(-2, 5),
                'performanceChange': random.uniform(-10, 8)
            }
        })
    
    except Exception as e:
        logger.error(f"Analytics overview error: {str(e)}")
        return jsonify({})

@app.route('/api/analytics/regions', methods=['GET'])
def get_region_distribution():
    try:
        regions = {}
        for subscriber in storage.subscribers.values():
            region = subscriber['region']
            regions[region] = regions.get(region, 0) + 1
        
        return jsonify([
            {'name': region, 'value': count}
            for region, count in regions.items()
        ])
    
    except Exception as e:
        logger.error(f"Region distribution error: {str(e)}")
        return jsonify([])

@app.route('/api/analytics/plans', methods=['GET'])
def get_plan_distribution():
    try:
        plans = {}
        for subscriber in storage.subscribers.values():
            plan = subscriber['plan']
            plans[plan] = plans.get(plan, 0) + 1
        
        return jsonify([
            {'plan': plan, 'count': count}
            for plan, count in plans.items()
        ])
    
    except Exception as e:
        logger.error(f"Plan distribution error: {str(e)}")
        return jsonify([])

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

# CORS preflight handler
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    logger.info(f"Starting Enhanced Subscriber Migration Portal API on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)