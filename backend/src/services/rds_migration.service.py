#!/usr/bin/env python3
"""
RDS to DynamoDB Migration Service
Handles data migration from legacy MySQL RDS to modern DynamoDB architecture
"""

import json
import uuid
import boto3
import pymysql
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
from dataclasses import dataclass, asdict

from utils.logger import get_logger
from config.database import get_legacy_db_connection, get_dynamodb_table
from utils.pagination import PaginationHelper
from utils.retry import retry_with_backoff

logger = get_logger(__name__)

# AWS Clients
step_functions = boto3.client('stepfunctions')
sqs = boto3.client('sqs')
cloudwatch = boto3.client('cloudwatch')

@dataclass
class MigrationJob:
    """Migration job data structure"""
    id: str
    status: str  # PENDING, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED
    source: str
    target: str
    filters: Dict[str, Any]
    cursor: Dict[str, Any]  # last_id, last_timestamp, offset
    stats: Dict[str, int]   # total, processed, succeeded, failed
    error_log: List[str]
    created_at: str
    updated_at: str
    estimated_completion: Optional[str] = None
    batch_size: int = 100
    
    def to_dynamodb_item(self):
        """Convert to DynamoDB item format"""
        item = asdict(self)
        # Convert int values to Decimal for DynamoDB
        for key in ['batch_size']:
            if key in item:
                item[key] = Decimal(str(item[key]))
        
        # Convert nested dicts
        if 'stats' in item:
            item['stats'] = {k: Decimal(str(v)) for k, v in item['stats'].items()}
        
        return item

class RDSMigrationService:
    """Service for migrating data from RDS to DynamoDB"""
    
    def __init__(self):
        self.migration_jobs_table = get_dynamodb_table('MIGRATION_JOBS_TABLE_NAME')
        self.subscribers_table = get_dynamodb_table('SUBSCRIBER_TABLE_NAME')
        self.audit_table = get_dynamodb_table('AUDIT_LOG_TABLE_NAME')
        
        # Step Functions state machine ARN (set via environment)
        self.state_machine_arn = os.environ.get('MIGRATION_STATE_MACHINE_ARN')
        
        # SQS queue for batch processing
        self.batch_queue_url = os.environ.get('MIGRATION_BATCH_QUEUE_URL')
    
    def create_migration_job(self, filters: Dict[str, Any] = None, 
                           batch_size: int = 100) -> MigrationJob:
        """Create a new migration job"""
        
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        # Estimate total records
        total_records = self._count_rds_records(filters or {})
        
        job = MigrationJob(
            id=job_id,
            status='PENDING',
            source='rds_mysql',
            target='dynamodb',
            filters=filters or {},
            cursor={'last_id': 0, 'last_timestamp': None, 'offset': 0},
            stats={'total': total_records, 'processed': 0, 'succeeded': 0, 'failed': 0},
            error_log=[],
            created_at=now,
            updated_at=now,
            batch_size=batch_size
        )
        
        # Save to DynamoDB
        self.migration_jobs_table.put_item(Item=job.to_dynamodb_item())
        
        # Log audit trail
        self._log_audit('migration_job_created', 'migration', 'system', {
            'job_id': job_id,
            'total_records': total_records,
            'filters': filters
        })
        
        logger.info(f"Migration job created: {job_id} - {total_records} records to migrate")
        return job
    
    def start_migration_job(self, job_id: str) -> Dict[str, Any]:
        """Start migration job using Step Functions"""
        
        # Get job details
        job = self._get_migration_job(job_id)
        if not job:
            raise ValueError(f"Migration job not found: {job_id}")
        
        if job['status'] not in ['PENDING', 'PAUSED']:
            raise ValueError(f"Job cannot be started. Current status: {job['status']}")
        
        # Update job status
        self._update_job_status(job_id, 'RUNNING')
        
        # Start Step Functions execution
        execution_name = f"migration-{job_id}-{int(datetime.utcnow().timestamp())}"
        
        input_data = {
            'job_id': job_id,
            'batch_size': int(job.get('batch_size', 100)),
            'filters': job.get('filters', {}),
            'cursor': job.get('cursor', {'last_id': 0})
        }
        
        response = step_functions.start_execution(
            stateMachineArn=self.state_machine_arn,
            name=execution_name,
            input=json.dumps(input_data)
        )
        
        # Store execution ARN for tracking
        self._update_job_metadata(job_id, {
            'execution_arn': response['executionArn'],
            'execution_name': execution_name
        })
        
        logger.info(f"Migration job started: {job_id} - Execution: {execution_name}")
        
        return {
            'job_id': job_id,
            'execution_arn': response['executionArn'],
            'status': 'RUNNING'
        }
    
    def pause_migration_job(self, job_id: str) -> Dict[str, Any]:
        """Pause a running migration job"""
        
        job = self._get_migration_job(job_id)
        if not job or job['status'] != 'RUNNING':
            raise ValueError(f"Job cannot be paused. Current status: {job.get('status', 'NOT_FOUND')}")
        
        # Stop Step Functions execution
        if 'execution_arn' in job:
            try:
                step_functions.stop_execution(
                    executionArn=job['execution_arn'],
                    cause='User requested pause'
                )
            except Exception as e:
                logger.warning(f"Failed to stop Step Functions execution: {e}")
        
        # Update job status
        self._update_job_status(job_id, 'PAUSED')
        
        logger.info(f"Migration job paused: {job_id}")
        
        return {'job_id': job_id, 'status': 'PAUSED'}
    
    def resume_migration_job(self, job_id: str) -> Dict[str, Any]:
        """Resume a paused migration job"""
        
        job = self._get_migration_job(job_id)
        if not job or job['status'] != 'PAUSED':
            raise ValueError(f"Job cannot be resumed. Current status: {job.get('status', 'NOT_FOUND')}")
        
        # Restart from current cursor position
        return self.start_migration_job(job_id)
    
    def cancel_migration_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a migration job"""
        
        job = self._get_migration_job(job_id)
        if not job:
            raise ValueError(f"Migration job not found: {job_id}")
        
        if job['status'] in ['COMPLETED', 'CANCELLED']:
            return {'job_id': job_id, 'status': job['status']}
        
        # Stop Step Functions execution
        if 'execution_arn' in job:
            try:
                step_functions.stop_execution(
                    executionArn=job['execution_arn'],
                    cause='User requested cancellation'
                )
            except Exception as e:
                logger.warning(f"Failed to stop Step Functions execution: {e}")
        
        # Update job status
        self._update_job_status(job_id, 'CANCELLED')
        
        logger.info(f"Migration job cancelled: {job_id}")
        
        return {'job_id': job_id, 'status': 'CANCELLED'}
    
    def get_migration_status(self, job_id: str) -> Dict[str, Any]:
        """Get detailed migration job status"""
        
        job = self._get_migration_job(job_id)
        if not job:
            raise ValueError(f"Migration job not found: {job_id}")
        
        # Calculate progress percentage
        stats = job.get('stats', {})
        total = int(stats.get('total', 0))
        processed = int(stats.get('processed', 0))
        progress = (processed / total * 100) if total > 0 else 0
        
        # Estimate completion time
        completion_estimate = self._estimate_completion(job)
        
        # Get Step Functions execution status if available
        execution_status = None
        if 'execution_arn' in job:
            try:
                response = step_functions.describe_execution(
                    executionArn=job['execution_arn']
                )
                execution_status = response['status']
            except Exception as e:
                logger.warning(f"Failed to get execution status: {e}")
        
        return {
            'job_id': job_id,
            'status': job['status'],
            'progress': {
                'total': total,
                'processed': processed,
                'succeeded': int(stats.get('succeeded', 0)),
                'failed': int(stats.get('failed', 0)),
                'percentage': round(progress, 2)
            },
            'timing': {
                'created_at': job['created_at'],
                'updated_at': job['updated_at'],
                'estimated_completion': completion_estimate
            },
            'execution_status': execution_status,
            'error_summary': job.get('error_log', [])[-5:],  # Last 5 errors
            'filters': job.get('filters', {}),
            'cursor': job.get('cursor', {})
        }
    
    @retry_with_backoff(max_retries=3)
    def extract_rds_batch(self, cursor: Dict[str, Any], batch_size: int, 
                         filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract a batch of records from RDS"""
        
        connection = get_legacy_db_connection()
        if not connection:
            raise RuntimeError("Failed to connect to legacy database")
        
        try:
            with connection.cursor() as cursor_db:
                # Build query with filters and pagination
                query, params = self._build_extraction_query(cursor, batch_size, filters)
                
                cursor_db.execute(query, params)
                rows = cursor_db.fetchall()
                
                logger.info(f"Extracted {len(rows)} records from RDS")
                return rows
                
        finally:
            connection.close()
    
    @retry_with_backoff(max_retries=3)
    def load_dynamodb_batch(self, records: List[Dict[str, Any]], 
                           job_id: str) -> Dict[str, int]:
        """Load a batch of records into DynamoDB"""
        
        if not records:
            return {'succeeded': 0, 'failed': 0}
        
        succeeded = 0
        failed = 0
        errors = []
        
        # Process in chunks of 25 (DynamoDB batch write limit)
        for chunk in self._chunk_list(records, 25):
            try:
                # Transform records for DynamoDB
                items = [self._transform_record(record) for record in chunk]
                
                # Batch write to DynamoDB
                with self.subscribers_table.batch_writer() as batch:
                    for item in items:
                        batch.put_item(Item=item)
                
                succeeded += len(chunk)
                
            except Exception as e:
                failed += len(chunk)
                error_msg = f"Batch write failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Update job statistics
        self._update_job_stats(job_id, succeeded, failed)
        
        # Log errors if any
        if errors:
            self._add_job_errors(job_id, errors)
        
        return {'succeeded': succeeded, 'failed': failed}
    
    def run_migration_audit(self, job_id: str, sample_size: int = 1000) -> Dict[str, Any]:
        """Run audit comparison between RDS and DynamoDB after migration"""
        
        job = self._get_migration_job(job_id)
        if not job or job['status'] != 'COMPLETED':
            raise ValueError(f"Audit can only be run on completed jobs")
        
        # Sample records from both systems
        rds_sample = self._sample_rds_records(sample_size, job.get('filters', {}))
        
        discrepancies = []
        matches = 0
        missing_in_dynamo = 0
        
        for rds_record in rds_sample:
            try:
                # Get corresponding DynamoDB record
                dynamo_record = self.subscribers_table.get_item(
                    Key={'subscriberId': rds_record['uid']}
                ).get('Item')
                
                if not dynamo_record:
                    missing_in_dynamo += 1
                    discrepancies.append({
                        'type': 'missing_in_dynamo',
                        'uid': rds_record['uid'],
                        'rds_record': self._sanitize_for_audit(rds_record)
                    })
                else:
                    # Compare key fields
                    diff = self._compare_records(rds_record, dynamo_record)
                    if diff:
                        discrepancies.append({
                            'type': 'field_mismatch',
                            'uid': rds_record['uid'],
                            'differences': diff
                        })
                    else:
                        matches += 1
                        
            except Exception as e:
                logger.error(f"Audit comparison failed for {rds_record.get('uid')}: {e}")
        
        # Store audit results
        audit_result = {
            'job_id': job_id,
            'audit_timestamp': datetime.utcnow().isoformat(),
            'sample_size': len(rds_sample),
            'results': {
                'matches': matches,
                'discrepancies': len(discrepancies),
                'missing_in_dynamo': missing_in_dynamo,
                'accuracy_percentage': (matches / len(rds_sample) * 100) if rds_sample else 100
            },
            'discrepancies': discrepancies[:50]  # Limit to first 50 discrepancies
        }
        
        # Log audit results
        self._log_audit('migration_audit_completed', 'migration', 'system', audit_result)
        
        logger.info(f"Migration audit completed for job {job_id}: {matches} matches, {len(discrepancies)} discrepancies")
        
        return audit_result
    
    # Private helper methods
    
    def _get_migration_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get migration job from DynamoDB"""
        try:
            response = self.migration_jobs_table.get_item(Key={'id': job_id})
            return response.get('Item')
        except Exception as e:
            logger.error(f"Failed to get migration job {job_id}: {e}")
            return None
    
    def _update_job_status(self, job_id: str, status: str):
        """Update job status in DynamoDB"""
        self.migration_jobs_table.update_item(
            Key={'id': job_id},
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': status,
                ':updated_at': datetime.utcnow().isoformat()
            }
        )
    
    def _update_job_stats(self, job_id: str, succeeded: int, failed: int):
        """Update job statistics atomically"""
        self.migration_jobs_table.update_item(
            Key={'id': job_id},
            UpdateExpression='ADD stats.processed :processed, stats.succeeded :succeeded, stats.failed :failed SET updated_at = :updated_at',
            ExpressionAttributeValues={
                ':processed': Decimal(str(succeeded + failed)),
                ':succeeded': Decimal(str(succeeded)),
                ':failed': Decimal(str(failed)),
                ':updated_at': datetime.utcnow().isoformat()
            }
        )
    
    def _count_rds_records(self, filters: Dict[str, Any]) -> int:
        """Count total records in RDS matching filters"""
        connection = get_legacy_db_connection()
        if not connection:
            return 0
        
        try:
            with connection.cursor() as cursor:
                query, params = self._build_count_query(filters)
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result['count'] if result else 0
        finally:
            connection.close()
    
    def _build_extraction_query(self, cursor: Dict[str, Any], batch_size: int, 
                               filters: Dict[str, Any]) -> tuple:
        """Build SQL query for batch extraction"""
        
        base_query = """
        SELECT id, uid, imsi, msisdn, status, created_at, updated_at
        FROM subscribers
        WHERE id > %s
        """
        
        params = [cursor.get('last_id', 0)]
        
        # Add filters
        if filters.get('status'):
            base_query += " AND status = %s"
            params.append(filters['status'])
        
        if filters.get('date_from'):
            base_query += " AND created_at >= %s"
            params.append(filters['date_from'])
        
        if filters.get('date_to'):
            base_query += " AND created_at <= %s"
            params.append(filters['date_to'])
        
        base_query += " ORDER BY id ASC LIMIT %s"
        params.append(batch_size)
        
        return base_query, params
    
    def _build_count_query(self, filters: Dict[str, Any]) -> tuple:
        """Build SQL count query"""
        
        base_query = "SELECT COUNT(*) as count FROM subscribers WHERE 1=1"
        params = []
        
        if filters.get('status'):
            base_query += " AND status = %s"
            params.append(filters['status'])
        
        if filters.get('date_from'):
            base_query += " AND created_at >= %s"
            params.append(filters['date_from'])
        
        if filters.get('date_to'):
            base_query += " AND created_at <= %s"
            params.append(filters['date_to'])
        
        return base_query, params
    
    def _transform_record(self, rds_record: Dict[str, Any]) -> Dict[str, Any]:
        """Transform RDS record to DynamoDB format"""
        
        return {
            'subscriberId': rds_record['uid'],
            'imsi': rds_record['imsi'],
            'msisdn': rds_record['msisdn'],
            'status': rds_record['status'],
            'created_at': rds_record['created_at'].isoformat() if rds_record.get('created_at') else None,
            'updated_at': rds_record['updated_at'].isoformat() if rds_record.get('updated_at') else None,
            'migrated_from': 'rds_mysql',
            'migrated_at': datetime.utcnow().isoformat()
        }
    
    def _chunk_list(self, lst: List, chunk_size: int) -> List[List]:
        """Split list into chunks"""
        for i in range(0, len(lst), chunk_size):
            yield lst[i:i + chunk_size]
    
    def _estimate_completion(self, job: Dict[str, Any]) -> Optional[str]:
        """Estimate job completion time based on current progress"""
        
        stats = job.get('stats', {})
        total = int(stats.get('total', 0))
        processed = int(stats.get('processed', 0))
        
        if processed == 0 or total == 0:
            return None
        
        # Calculate time elapsed and rate
        created_at = datetime.fromisoformat(job['created_at'].replace('Z', '+00:00'))
        elapsed = datetime.utcnow() - created_at.replace(tzinfo=None)
        
        if elapsed.total_seconds() == 0:
            return None
        
        rate = processed / elapsed.total_seconds()  # records per second
        remaining = total - processed
        
        if rate > 0:
            eta_seconds = remaining / rate
            completion_time = datetime.utcnow() + timedelta(seconds=eta_seconds)
            return completion_time.isoformat()
        
        return None
    
    def _log_audit(self, action: str, resource: str, user: str, details: Dict[str, Any]):
        """Log audit event"""
        try:
            audit_entry = {
                'id': f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{action}",
                'timestamp': datetime.utcnow().isoformat(),
                'action': action,
                'resource': resource,
                'user': user,
                'details': details,
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())
            }
            
            self.audit_table.put_item(Item=audit_entry)
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

# Export service instance
migration_service = RDSMigrationService()