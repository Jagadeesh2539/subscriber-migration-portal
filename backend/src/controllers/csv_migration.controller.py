#!/usr/bin/env python3
"""
CSV Migration Controller - Handles CSV Upload with Migration ID
Implements exact requirements from specification
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import request, jsonify, g, make_response

from services.csv_migration.service import CSVMigrationService
from services.audit.service import AuditService
from utils.validation import InputValidator, ValidationError
from utils.response import create_response, create_error_response
from utils.logger import get_logger

logger = get_logger(__name__)
csv_migration_service = CSVMigrationService()
audit_service = AuditService()

class CSVMigrationController:
    """Controller for CSV-based migration with Migration ID tracking"""
    
    @staticmethod
    def upload_csv_migration():
        """
        Upload CSV file for migration with automatic identifier detection
        POST /api/migration/csv-upload
        
        Form Data:
        - file: CSV file (imsi.csv, uid.csv, or msisdn.csv)
        - migration_id: Mandatory Migration ID for tracking
        - cloud_migration_enabled: true/false (optional, default: true)
        - description: Optional description for this migration batch
        
        CSV Format Examples:
        
        IMSI CSV:
        imsi
        111
        1122
        1233
        
        UID CSV:
        uid
        32
        23
        11
        
        MSISDN CSV:
        msisdn
        2232
        322
        1111
        """
        try:
            # Validate file upload
            if 'file' not in request.files:
                return create_error_response("No CSV file uploaded", 400)
            
            file = request.files['file']
            if file.filename == '':
                return create_error_response("No file selected", 400)
            
            if not file.filename.lower().endswith('.csv'):
                return create_error_response("Only CSV files are supported", 400)
            
            # Get Migration ID (mandatory)
            migration_id = request.form.get('migration_id', '').strip()
            if not migration_id:
                return create_error_response("Migration ID is mandatory", 400)
            
            # Validate Migration ID format
            validator = InputValidator()
            clean_migration_id = validator.sanitize_string(migration_id, 100)
            if len(clean_migration_id) < 3:
                return create_error_response("Migration ID must be at least 3 characters", 400)
            
            # Check if Migration ID already exists
            existing_migration = csv_migration_service.get_migration_summary(clean_migration_id)
            if existing_migration:
                return create_error_response(
                    f"Migration ID '{clean_migration_id}' already exists. Please use a unique Migration ID.", 
                    409
                )
            
            # Get optional parameters
            cloud_migration_enabled = request.form.get('cloud_migration_enabled', 'true').lower() == 'true'
            description = validator.sanitize_string(request.form.get('description', ''), 500)
            
            # Log migration start
            audit_service.log_action(
                action='csv_migration_started',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'migration_id': clean_migration_id,
                    'filename': file.filename,
                    'cloud_migration_enabled': cloud_migration_enabled,
                    'description': description
                }
            )
            
            # Process CSV migration
            migration_summary = csv_migration_service.process_csv_migration(
                file, 
                clean_migration_id, 
                cloud_migration_enabled
            )
            
            # Generate response with summary
            response_data = {
                'migration_id': migration_summary.migration_id,
                'identifier_type': migration_summary.identifier_type,
                'cloud_migration_enabled': migration_summary.cloud_migration_enabled,
                'summary': {
                    'total_processed': migration_summary.total_processed,
                    'migrated_successfully': migration_summary.migrated_successfully,
                    'already_present': migration_summary.already_present,
                    'not_found_in_legacy': migration_summary.not_found_in_legacy,
                    'failed': migration_summary.failed
                },
                'timing': {
                    'started_at': migration_summary.started_at,
                    'completed_at': migration_summary.completed_at
                },
                'success_rate': round(
                    (migration_summary.migrated_successfully / migration_summary.total_processed * 100) 
                    if migration_summary.total_processed > 0 else 0, 2
                )
            }
            
            return create_response(
                data=response_data,
                message=f"CSV migration completed for Migration ID '{clean_migration_id}'"
            )
            
        except ValidationError as e:
            return create_error_response(str(e), 400)
        except ValueError as e:
            return create_error_response(str(e), 400)
        except Exception as e:
            logger.error(f"Error processing CSV migration: {str(e)}")
            return create_error_response("Failed to process CSV migration", 500)
    
    @staticmethod
    def get_migration_summary(migration_id: str):
        """
        Get migration summary by Migration ID
        GET /api/migration/csv-summary/{migration_id}
        """
        try:
            validator = InputValidator()
            clean_migration_id = validator.sanitize_string(migration_id, 100)
            
            summary = csv_migration_service.get_migration_summary(clean_migration_id)
            if not summary:
                return create_error_response("Migration ID not found", 404)
            
            return create_response(data=summary)
            
        except Exception as e:
            logger.error(f"Error getting migration summary {migration_id}: {str(e)}")
            return create_error_response("Failed to get migration summary", 500)
    
    @staticmethod
    def download_migration_report(migration_id: str):
        """
        Download migration report (CSV or Excel format)
        GET /api/migration/csv-report/{migration_id}?format=csv
        
        Query Parameters:
        - format: csv or json (default: csv)
        
        Returns downloadable file with detailed migration results
        """
        try:
            validator = InputValidator()
            clean_migration_id = validator.sanitize_string(migration_id, 100)
            format_type = request.args.get('format', 'csv').lower()
            
            if format_type not in ['csv', 'json']:
                return create_error_response("Invalid format. Use 'csv' or 'json'", 400)
            
            # Get migration summary
            summary_data = csv_migration_service.get_migration_summary(clean_migration_id)
            if not summary_data:
                return create_error_response("Migration ID not found", 404)
            
            # For CSV report, we need to reconstruct the MigrationSummary object
            # This is a simplified version - in production you'd store full details
            from services.csv_migration.service import MigrationSummary, MigrationRecord
            
            summary = MigrationSummary(
                migration_id=clean_migration_id,
                total_processed=int(summary_data.get('stats', {}).get('total_processed', 0)),
                migrated_successfully=int(summary_data.get('stats', {}).get('migrated_successfully', 0)),
                already_present=int(summary_data.get('stats', {}).get('already_present', 0)),
                not_found_in_legacy=int(summary_data.get('stats', {}).get('not_found_in_legacy', 0)),
                failed=int(summary_data.get('stats', {}).get('failed', 0)),
                identifier_type=summary_data.get('identifier_type', 'unknown'),
                cloud_migration_enabled=summary_data.get('cloud_migration_enabled', True),
                started_at=summary_data.get('started_at', ''),
                completed_at=summary_data.get('completed_at', ''),
                records=[]  # Detailed records would be stored separately in production
            )
            
            # Generate report content
            report_content = csv_migration_service.generate_migration_report(summary, format_type)
            
            # Create file response
            response = make_response(report_content)
            
            if format_type == 'csv':
                response.headers['Content-Type'] = 'text/csv; charset=utf-8'
                response.headers['Content-Disposition'] = f'attachment; filename=migration_report_{clean_migration_id}.csv'
            else:
                response.headers['Content-Type'] = 'application/json'
                response.headers['Content-Disposition'] = f'attachment; filename=migration_report_{clean_migration_id}.json'
            
            # Log report download
            audit_service.log_action(
                action='migration_report_downloaded',
                resource='migration',
                user=g.current_user.get('username', 'system'),
                details={
                    'migration_id': clean_migration_id,
                    'format': format_type
                }
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error downloading migration report {migration_id}: {str(e)}")
            return create_error_response("Failed to generate migration report", 500)
    
    @staticmethod
    def list_migration_summaries():
        """
        List all CSV migration summaries
        GET /api/migration/csv-summaries?limit=20&status=COMPLETED
        
        Query Parameters:
        - limit: Number of results (default: 20, max: 100)
        - status: Filter by status (optional)
        """
        try:
            limit = min(int(request.args.get('limit', 20)), 100)
            status = request.args.get('status')
            
            summaries = csv_migration_service.list_migration_summaries(limit, status)
            
            return create_response(
                data={
                    'summaries': summaries,
                    'count': len(summaries),
                    'limit': limit,
                    'status_filter': status
                }
            )
            
        except Exception as e:
            logger.error(f"Error listing migration summaries: {str(e)}")
            return create_error_response("Failed to list migration summaries", 500)
    
    @staticmethod
    def validate_csv_format():
        """
        Validate CSV format without processing
        POST /api/migration/csv-validate
        
        Form Data:
        - file: CSV file to validate
        
        Returns:
        - Detected identifier type
        - Row count
        - Sample data
        - Validation issues
        """
        try:
            if 'file' not in request.files:
                return create_error_response("No CSV file uploaded", 400)
            
            file = request.files['file']
            if not file.filename.lower().endswith('.csv'):
                return create_error_response("Only CSV files are supported", 400)
            
            # Read CSV for validation
            import csv
            import io
            
            csv_content = file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            # Get headers
            headers = csv_reader.fieldnames
            if not headers:
                return create_error_response("CSV file must have headers", 400)
            
            # Detect identifier type
            identifier_type = csv_migration_service._detect_identifier_type(headers)
            if not identifier_type:
                return create_error_response(
                    f"No valid identifier found in headers: {headers}. Expected: imsi, msisdn, or uid", 
                    400
                )
            
            # Count rows and get sample
            rows = list(csv_reader)
            row_count = len(rows)
            sample_data = rows[:5]  # First 5 rows as sample
            
            # Basic validation
            issues = []
            empty_rows = 0
            
            for i, row in enumerate(rows[:100]):  # Check first 100 rows
                identifier_value = row.get(identifier_type, '').strip()
                if not identifier_value:
                    empty_rows += 1
            
            if empty_rows > 0:
                issues.append(f"{empty_rows} rows have empty {identifier_type} values")
            
            if row_count == 0:
                issues.append("CSV file contains no data rows")
            
            validation_result = {
                'valid': len(issues) == 0,
                'identifier_type': identifier_type,
                'headers': headers,
                'row_count': row_count,
                'sample_data': sample_data,
                'issues': issues,
                'estimated_processing_time': f"{max(1, row_count // 100)} minutes" if row_count > 0 else "0 minutes"
            }
            
            return create_response(
                data=validation_result,
                message=f"CSV validation completed - detected {identifier_type} format with {row_count} rows"
            )
            
        except Exception as e:
            logger.error(f"Error validating CSV: {str(e)}")
            return create_error_response(f"Failed to validate CSV: {str(e)}", 500)
    
    @staticmethod
    def get_migration_dashboard():
        """
        Get CSV migration dashboard data
        GET /api/migration/csv-dashboard
        
        Returns:
        - Recent migrations
        - Success rate statistics
        - Processing volumes
        - Error analysis
        """
        try:
            # Get recent migrations
            recent_migrations = csv_migration_service.list_migration_summaries(10)
            
            # Calculate overall statistics
            total_migrations = len(recent_migrations)
            total_processed = sum(m.get('stats', {}).get('total_processed', 0) for m in recent_migrations)
            total_successful = sum(m.get('stats', {}).get('migrated_successfully', 0) for m in recent_migrations)
            
            overall_success_rate = (total_successful / total_processed * 100) if total_processed > 0 else 0
            
            # Group by identifier type
            identifier_stats = {}
            for migration in recent_migrations:
                id_type = migration.get('identifier_type', 'unknown')
                if id_type not in identifier_stats:
                    identifier_stats[id_type] = {'count': 0, 'total_records': 0}
                identifier_stats[id_type]['count'] += 1
                identifier_stats[id_type]['total_records'] += migration.get('stats', {}).get('total_processed', 0)
            
            dashboard_data = {
                'overview': {
                    'total_migrations': total_migrations,
                    'total_records_processed': total_processed,
                    'overall_success_rate': round(overall_success_rate, 2),
                    'last_updated': datetime.utcnow().isoformat()
                },
                'recent_migrations': recent_migrations,
                'identifier_type_breakdown': identifier_stats,
                'supported_formats': {
                    'imsi': 'International Mobile Subscriber Identity',
                    'uid': 'User Identifier',
                    'msisdn': 'Mobile Station International Subscriber Directory Number'
                }
            }
            
            return create_response(data=dashboard_data)
            
        except Exception as e:
            logger.error(f"Error getting migration dashboard: {str(e)}")
            return create_error_response("Failed to get migration dashboard", 500)

# Export controller instance
csv_migration_controller = CSVMigrationController()