import pymysql
import json
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class LegacyDBClient:
    """
    Enhanced Legacy MySQL Database Client
    Handles all legacy database operations with connection pooling and error handling
    """
    
    def __init__(self):
        self.connection_config = None
        self.connection = None
        self.secrets_client = boto3.client('secretsmanager')
        self.secret_arn = os.environ.get('LEGACY_DB_SECRET_ARN')
        self.db_host = os.environ.get('LEGACY_DB_HOST', 'subscriber-migration-legacydb.cwd6wssgy4kr.us-east-1.rds.amazonaws.com')
        self.db_port = int(os.environ.get('LEGACY_DB_PORT', '3306'))
        self.db_name = os.environ.get('LEGACY_DB_NAME', 'legacydb')
        
        logger.info(f"Initialized LegacyDBClient with host: {self.db_host}, port: {self.db_port}, database: {self.db_name}")
    
    def _get_db_credentials(self):
        """Retrieve database credentials from AWS Secrets Manager"""
        try:
            if not self.secret_arn:
                logger.warning("No secret ARN provided, using environment variables")
                return {
                    'username': os.environ.get('LEGACY_DB_USER', 'admin'),
                    'password': os.environ.get('LEGACY_DB_PASSWORD', ''),
                    'host': self.db_host,
                    'port': self.db_port,
                    'dbname': self.db_name
                }
            
            response = self.secrets_client.get_secret_value(SecretId=self.secret_arn)
            secret_data = json.loads(response['SecretString'])
            
            return {
                'username': secret_data.get('username', 'admin'),
                'password': secret_data.get('password', ''),
                'host': secret_data.get('host', self.db_host),
                'port': secret_data.get('port', self.db_port),
                'dbname': secret_data.get('dbname', self.db_name)
            }
        except ClientError as e:
            logger.error(f"Error retrieving secret: {str(e)}")
            raise Exception(f"Failed to retrieve database credentials: {str(e)}")
        except Exception as e:
            logger.error(f"Error parsing secret: {str(e)}")
            raise Exception(f"Failed to parse database credentials: {str(e)}")
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with automatic cleanup"""
        connection = None
        try:
            if not self.connection_config:
                self.connection_config = self._get_db_credentials()
            
            connection = pymysql.connect(
                host=self.connection_config['host'],
                user=self.connection_config['username'],
                password=self.connection_config['password'],
                database=self.connection_config['dbname'],
                port=self.connection_config['port'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30
            )
            
            logger.info(f"Connected to legacy database: {self.connection_config['host']}:{self.connection_config['port']}")
            yield connection
            
        except pymysql.Error as e:
            logger.error(f"MySQL error: {str(e)}")
            raise Exception(f"Database connection error: {str(e)}")
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            raise
        finally:
            if connection:
                connection.close()
                logger.debug("Database connection closed")
    
    def initialize_database(self):
        """Initialize database schema if not exists"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create database if not exists
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.db_name}`")
                cursor.execute(f"USE `{self.db_name}`")
                
                # Create subscribers table
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS `subscribers` (
                    `subscriber_id` VARCHAR(64) PRIMARY KEY,
                    `name` VARCHAR(255) NOT NULL,
                    `email` VARCHAR(255) NOT NULL,
                    `phone` VARCHAR(32) DEFAULT '',
                    `plan` VARCHAR(64) DEFAULT 'basic',
                    `status` VARCHAR(32) DEFAULT 'active',
                    `region` VARCHAR(64) DEFAULT 'us-east-1',
                    `created_date` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX `idx_email` (`email`),
                    INDEX `idx_status` (`status`),
                    INDEX `idx_plan` (`plan`),
                    INDEX `idx_region` (`region`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
                
                cursor.execute(create_table_sql)
                logger.info("Legacy database schema initialized successfully")
                
                return True
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise
    
    def get_subscriber(self, subscriber_id: str) -> Optional[Dict[str, Any]]:
        """Get a single subscriber by ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM subscribers WHERE subscriber_id = %s",
                    (subscriber_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    # Convert datetime objects to ISO strings
                    for key, value in result.items():
                        if isinstance(value, datetime):
                            result[key] = value.isoformat()
                
                logger.debug(f"Retrieved subscriber: {subscriber_id}")
                return result
        except Exception as e:
            logger.error(f"Error getting subscriber {subscriber_id}: {str(e)}")
            raise
    
    def get_subscribers(self, filters: Optional[Dict[str, Any]] = None, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Get multiple subscribers with optional filtering and pagination"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build query with filters
                where_clauses = []
                params = []
                
                if filters:
                    if filters.get('status') and filters['status'] != 'all':
                        where_clauses.append("status = %s")
                        params.append(filters['status'])
                    
                    if filters.get('plan') and filters['plan'] != 'all':
                        where_clauses.append("plan = %s")
                        params.append(filters['plan'])
                    
                    if filters.get('region') and filters['region'] != 'all':
                        where_clauses.append("region = %s")
                        params.append(filters['region'])
                    
                    if filters.get('search'):
                        where_clauses.append("(name LIKE %s OR email LIKE %s OR subscriber_id LIKE %s)")
                        search_term = f"%{filters['search']}%"
                        params.extend([search_term, search_term, search_term])
                
                where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
                
                # Get total count
                count_query = f"SELECT COUNT(*) as total FROM subscribers{where_clause}"
                cursor.execute(count_query, params)
                total_count = cursor.fetchone()['total']
                
                # Get paginated results
                offset = (page - 1) * limit
                query = f"SELECT * FROM subscribers{where_clause} ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                cursor.execute(query, params + [limit, offset])
                results = cursor.fetchall()
                
                # Convert datetime objects to ISO strings
                for result in results:
                    for key, value in result.items():
                        if isinstance(value, datetime):
                            result[key] = value.isoformat()
                
                logger.info(f"Retrieved {len(results)} subscribers (page {page}, total: {total_count})")
                
                return {
                    'subscribers': results,
                    'total': total_count,
                    'page': page,
                    'limit': limit
                }
        except Exception as e:
            logger.error(f"Error getting subscribers: {str(e)}")
            raise
    
    def create_subscriber(self, subscriber_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new subscriber in legacy database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Prepare data with current timestamp
                data = {
                    'subscriber_id': subscriber_data['subscriber_id'],
                    'name': subscriber_data['name'],
                    'email': subscriber_data['email'],
                    'phone': subscriber_data.get('phone', ''),
                    'plan': subscriber_data.get('plan', 'basic'),
                    'status': subscriber_data.get('status', 'active'),
                    'region': subscriber_data.get('region', 'us-east-1'),
                    'created_date': datetime.now()
                }
                
                # Insert subscriber
                insert_query = """
                INSERT INTO subscribers (
                    subscriber_id, name, email, phone, plan, status, region, created_date
                ) VALUES (
                    %(subscriber_id)s, %(name)s, %(email)s, %(phone)s, 
                    %(plan)s, %(status)s, %(region)s, %(created_date)s
                )
                """
                
                cursor.execute(insert_query, data)
                logger.info(f"Created subscriber in legacy DB: {subscriber_data['subscriber_id']}")
                
                # Return the created subscriber
                return self.get_subscriber(subscriber_data['subscriber_id'])
        except pymysql.IntegrityError as e:
            if "Duplicate entry" in str(e):
                raise Exception(f"Subscriber ID {subscriber_data['subscriber_id']} already exists in legacy database")
            raise Exception(f"Database integrity error: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating subscriber: {str(e)}")
            raise
    
    def update_subscriber(self, subscriber_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing subscriber in legacy database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if subscriber exists
                existing = self.get_subscriber(subscriber_id)
                if not existing:
                    return None
                
                # Prepare update fields
                update_fields = []
                params = []
                
                updatable_fields = ['name', 'email', 'phone', 'plan', 'status', 'region']
                for field in updatable_fields:
                    if field in updates:
                        update_fields.append(f"{field} = %s")
                        params.append(updates[field])
                
                if not update_fields:
                    return existing  # No updates to make
                
                # Add updated_at timestamp
                update_fields.append("updated_at = %s")
                params.append(datetime.now())
                params.append(subscriber_id)
                
                # Execute update
                update_query = f"UPDATE subscribers SET {', '.join(update_fields)} WHERE subscriber_id = %s"
                cursor.execute(update_query, params)
                
                logger.info(f"Updated subscriber in legacy DB: {subscriber_id}")
                
                # Return updated subscriber
                return self.get_subscriber(subscriber_id)
        except Exception as e:
            logger.error(f"Error updating subscriber {subscriber_id}: {str(e)}")
            raise
    
    def delete_subscriber(self, subscriber_id: str) -> bool:
        """Delete a subscriber from legacy database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if subscriber exists
                existing = self.get_subscriber(subscriber_id)
                if not existing:
                    return False
                
                # Delete subscriber
                cursor.execute(
                    "DELETE FROM subscribers WHERE subscriber_id = %s",
                    (subscriber_id,)
                )
                
                deleted_count = cursor.rowcount
                logger.info(f"Deleted subscriber from legacy DB: {subscriber_id} (rows affected: {deleted_count})")
                
                return deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting subscriber {subscriber_id}: {str(e)}")
            raise
    
    def bulk_get_subscribers(self, subscriber_ids: List[str]) -> List[Dict[str, Any]]:
        """Get multiple subscribers by IDs for bulk operations"""
        try:
            if not subscriber_ids:
                return []
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create placeholders for IN clause
                placeholders = ', '.join(['%s'] * len(subscriber_ids))
                query = f"SELECT * FROM subscribers WHERE subscriber_id IN ({placeholders})"
                
                cursor.execute(query, subscriber_ids)
                results = cursor.fetchall()
                
                # Convert datetime objects to ISO strings
                for result in results:
                    for key, value in result.items():
                        if isinstance(value, datetime):
                            result[key] = value.isoformat()
                
                logger.info(f"Retrieved {len(results)} subscribers from legacy DB for bulk operation")
                return results
        except Exception as e:
            logger.error(f"Error bulk getting subscribers: {str(e)}")
            raise
    
    def bulk_delete_subscribers(self, subscriber_ids: List[str]) -> Dict[str, Any]:
        """Bulk delete subscribers from legacy database"""
        try:
            if not subscriber_ids:
                return {'deleted': 0, 'errors': []}
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete in batches for performance
                batch_size = 100
                total_deleted = 0
                errors = []
                
                for i in range(0, len(subscriber_ids), batch_size):
                    batch = subscriber_ids[i:i + batch_size]
                    placeholders = ', '.join(['%s'] * len(batch))
                    
                    try:
                        cursor.execute(
                            f"DELETE FROM subscribers WHERE subscriber_id IN ({placeholders})",
                            batch
                        )
                        total_deleted += cursor.rowcount
                    except Exception as e:
                        errors.append(f"Batch {i//batch_size + 1}: {str(e)}")
                
                logger.info(f"Bulk deleted {total_deleted} subscribers from legacy DB")
                
                return {
                    'deleted': total_deleted,
                    'errors': errors,
                    'processed': len(subscriber_ids)
                }
        except Exception as e:
            logger.error(f"Error bulk deleting subscribers: {str(e)}")
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get legacy database statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                stats = {}
                
                # Total count
                cursor.execute("SELECT COUNT(*) as total FROM subscribers")
                stats['total'] = cursor.fetchone()['total']
                
                # Status distribution
                cursor.execute("SELECT status, COUNT(*) as count FROM subscribers GROUP BY status")
                stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # Plan distribution
                cursor.execute("SELECT plan, COUNT(*) as count FROM subscribers GROUP BY plan")
                stats['by_plan'] = {row['plan']: row['count'] for row in cursor.fetchall()}
                
                # Region distribution
                cursor.execute("SELECT region, COUNT(*) as count FROM subscribers GROUP BY region")
                stats['by_region'] = {row['region']: row['count'] for row in cursor.fetchall()}
                
                # Recent activity
                cursor.execute("""
                    SELECT DATE(updated_at) as date, COUNT(*) as count 
                    FROM subscribers 
                    WHERE updated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                    GROUP BY DATE(updated_at)
                    ORDER BY date DESC
                """)
                stats['recent_activity'] = [{'date': row['date'].isoformat(), 'count': row['count']} for row in cursor.fetchall()]
                
                logger.info(f"Retrieved legacy DB statistics: {stats['total']} total subscribers")
                return stats
        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            raise
    
    def test_connection(self) -> Dict[str, Any]:
        """Test database connection and return connection info"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Test basic connectivity
                cursor.execute("SELECT 1 as test")
                test_result = cursor.fetchone()
                
                # Get server info
                cursor.execute("SELECT VERSION() as version")
                version_info = cursor.fetchone()
                
                # Get database info
                cursor.execute("SELECT DATABASE() as current_db")
                db_info = cursor.fetchone()
                
                return {
                    'status': 'connected',
                    'test_query': test_result['test'] == 1,
                    'server_version': version_info['version'],
                    'current_database': db_info['current_db'],
                    'host': self.db_host,
                    'port': self.db_port,
                    'timestamp': datetime.now().isoformat()
                }
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def compare_with_cloud(self, cloud_subscribers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare legacy database with cloud data for audit purposes"""
        try:
            # Get all legacy subscribers
            legacy_data = self.get_subscribers(limit=10000)  # Get all for comparison
            legacy_subscribers = {sub['subscriber_id']: sub for sub in legacy_data['subscribers']}
            cloud_subscribers_dict = {sub['subscriber_id']: sub for sub in cloud_subscribers}
            
            # Find differences
            only_in_legacy = []
            only_in_cloud = []
            differences = []
            
            # Check subscribers only in legacy
            for sub_id, legacy_sub in legacy_subscribers.items():
                if sub_id not in cloud_subscribers_dict:
                    only_in_legacy.append(legacy_sub)
            
            # Check subscribers only in cloud
            for sub_id, cloud_sub in cloud_subscribers_dict.items():
                if sub_id not in legacy_subscribers:
                    only_in_cloud.append(cloud_sub)
                else:
                    # Compare data between legacy and cloud
                    legacy_sub = legacy_subscribers[sub_id]
                    diff_fields = []
                    
                    comparable_fields = ['name', 'email', 'phone', 'plan', 'status', 'region']
                    for field in comparable_fields:
                        legacy_value = legacy_sub.get(field, '')
                        cloud_value = cloud_sub.get(field, '')
                        if str(legacy_value) != str(cloud_value):
                            diff_fields.append({
                                'field': field,
                                'legacy_value': legacy_value,
                                'cloud_value': cloud_value
                            })
                    
                    if diff_fields:
                        differences.append({
                            'subscriber_id': sub_id,
                            'differences': diff_fields
                        })
            
            audit_result = {
                'timestamp': datetime.now().isoformat(),
                'legacy_total': len(legacy_subscribers),
                'cloud_total': len(cloud_subscribers_dict),
                'only_in_legacy': len(only_in_legacy),
                'only_in_cloud': len(only_in_cloud),
                'data_differences': len(differences),
                'only_in_legacy_records': only_in_legacy[:100],  # Limit for response size
                'only_in_cloud_records': only_in_cloud[:100],
                'difference_records': differences[:100]
            }
            
            logger.info(f"Audit comparison completed: {audit_result['legacy_total']} legacy vs {audit_result['cloud_total']} cloud")
            return audit_result
            
        except Exception as e:
            logger.error(f"Error comparing legacy with cloud: {str(e)}")
            raise

# Global instance for use across the application
legacy_db_client = None

def get_legacy_db_client() -> LegacyDBClient:
    """Get singleton legacy database client"""
    global legacy_db_client
    if legacy_db_client is None:
        legacy_db_client = LegacyDBClient()
        try:
            legacy_db_client.initialize_database()
        except Exception as e:
            logger.warning(f"Failed to initialize legacy database schema: {str(e)}")
    return legacy_db_client

# Health check function for legacy database
def legacy_health_check() -> Dict[str, Any]:
    """Perform health check on legacy database"""
    try:
        client = get_legacy_db_client()
        return client.test_connection()
    except Exception as e:
        logger.error(f"Legacy health check failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }