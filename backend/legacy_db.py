#!/usr/bin/env python3
"""
Legacy Database Operations - Single Source of Truth
Consolidated from legacy_db.py and legacy_db_enhanced.py
Secure connection management with proper error handling
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import contextmanager

import boto3
import pymysql
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)

class LegacyDatabase:
    """Consolidated legacy database operations with secure connection management."""
    
    def __init__(self, secret_arn: str, host: str, port: int = 3306, database: str = 'legacydb'):
        self.secret_arn = secret_arn
        self.host = host
        self.port = port
        self.database = database
        self.secrets_client = None
        
        try:
            self.secrets_client = boto3.client('secretsmanager')
        except Exception as e:
            logger.error(f"Failed to initialize secrets client: {str(e)}")
    
    def _get_credentials(self) -> Optional[Dict[str, str]]:
        """Get database credentials from AWS Secrets Manager."""
        if not self.secrets_client or not self.secret_arn:
            logger.error("Secrets client or ARN not configured")
            return None
        
        try:
            response = self.secrets_client.get_secret_value(SecretId=self.secret_arn)
            return json.loads(response['SecretString'])
        except ClientError as e:
            logger.error(f"Failed to get credentials: {e.response['Error']['Code']}: {e.response['Error']['Message']}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid credentials JSON: {str(e)}")
            return None
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with automatic cleanup."""
        connection = None
        try:
            credentials = self._get_credentials()
            if not credentials:
                raise ConnectionError("Unable to retrieve database credentials")
            
            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=credentials['username'],
                password=credentials['password'],
                database=self.database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30,
                autocommit=False  # Explicit transaction control
            )
            
            yield connection
            
        except pymysql.Error as e:
            logger.error(f"Database connection error: {str(e)}")
            if connection:
                connection.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected connection error: {str(e)}")
            if connection:
                connection.rollback()
            raise
        finally:
            if connection:
                connection.close()
    
    def test_connection(self) -> Dict[str, Any]:
        """Test database connection and return status."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 as test")
                    cursor.execute("SELECT COUNT(*) as count FROM subscribers")
                    result = cursor.fetchone()
                    subscriber_count = result['count'] if result else 0
                
                return {
                    'status': 'connected',
                    'host': self.host,
                    'database': self.database,
                    'subscriber_count': subscriber_count,
                    'timestamp': datetime.utcnow().isoformat()
                }
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def get_subscribers(self, limit: int = 50, offset: int = 0, filters: Dict = None) -> List[Dict]:
        """Get subscribers with pagination and filtering."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Build query with filters
                    query = "SELECT * FROM subscribers"
                    params = []
                    
                    if filters:
                        conditions = []
                        if filters.get('status'):
                            conditions.append("status = %s")
                            params.append(filters['status'])
                        if filters.get('plan'):
                            conditions.append("plan = %s")
                            params.append(filters['plan'])
                        if filters.get('search'):
                            conditions.append("(name LIKE %s OR email LIKE %s)")
                            search_term = f"%{filters['search']}%"
                            params.extend([search_term, search_term])
                        
                        if conditions:
                            query += " WHERE " + " AND ".join(conditions)
                    
                    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                    params.extend([limit, offset])
                    
                    cursor.execute(query, params)
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to get subscribers: {str(e)}")
            raise
    
    def get_subscriber_by_id(self, subscriber_id: int) -> Optional[Dict]:
        """Get a specific subscriber by ID."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM subscribers WHERE id = %s", (subscriber_id,))
                    return cursor.fetchone()
        except Exception as e:
            logger.error(f"Failed to get subscriber {subscriber_id}: {str(e)}")
            raise
    
    def get_subscriber_by_email(self, email: str) -> Optional[Dict]:
        """Get a specific subscriber by email."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM subscribers WHERE email = %s", (email,))
                    return cursor.fetchone()
        except Exception as e:
            logger.error(f"Failed to get subscriber by email {email}: {str(e)}")
            raise
    
    def create_subscriber(self, subscriber_data: Dict) -> int:
        """Create a new subscriber and return the ID."""
        required_fields = ['name', 'email', 'phone']
        for field in required_fields:
            if not subscriber_data.get(field):
                raise ValueError(f"Missing required field: {field}")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO subscribers (name, email, phone, plan, status, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    now = datetime.utcnow().isoformat()
                    
                    cursor.execute(query, (
                        subscriber_data['name'],
                        subscriber_data['email'],
                        subscriber_data['phone'],
                        subscriber_data.get('plan', 'basic'),
                        subscriber_data.get('status', 'active'),
                        now,
                        now
                    ))
                    
                    conn.commit()
                    return cursor.lastrowid
        except pymysql.IntegrityError as e:
            logger.error(f"Subscriber creation failed - duplicate entry: {str(e)}")
            raise ValueError("Email already exists")
        except Exception as e:
            logger.error(f"Failed to create subscriber: {str(e)}")
            raise
    
    def update_subscriber(self, subscriber_id: int, updates: Dict) -> bool:
        """Update an existing subscriber."""
        if not updates:
            return True
        
        # Filter out None values and add updated_at
        filtered_updates = {k: v for k, v in updates.items() if v is not None}
        filtered_updates['updated_at'] = datetime.utcnow().isoformat()
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Build dynamic update query
                    set_clauses = [f"{field} = %s" for field in filtered_updates.keys()]
                    query = f"UPDATE subscribers SET {', '.join(set_clauses)} WHERE id = %s"
                    
                    params = list(filtered_updates.values()) + [subscriber_id]
                    
                    cursor.execute(query, params)
                    conn.commit()
                    
                    return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update subscriber {subscriber_id}: {str(e)}")
            raise
    
    def delete_subscriber(self, subscriber_id: int) -> bool:
        """Delete a subscriber (soft delete by setting status to 'deleted')."""
        try:
            return self.update_subscriber(subscriber_id, {
                'status': 'deleted',
                'deleted_at': datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to delete subscriber {subscriber_id}: {str(e)}")
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive database statistics."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    stats = {}
                    
                    # Total subscribers
                    cursor.execute("SELECT COUNT(*) as total FROM subscribers WHERE status != 'deleted'")
                    stats['total_subscribers'] = cursor.fetchone()['total']
                    
                    # By status
                    cursor.execute("""
                        SELECT status, COUNT(*) as count 
                        FROM subscribers 
                        WHERE status != 'deleted'
                        GROUP BY status
                    """)
                    stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
                    
                    # By plan
                    cursor.execute("""
                        SELECT plan, COUNT(*) as count 
                        FROM subscribers 
                        WHERE status != 'deleted'
                        GROUP BY plan
                    """)
                    stats['by_plan'] = {row['plan']: row['count'] for row in cursor.fetchall()}
                    
                    # Recent activity (last 30 days)
                    cursor.execute("""
                        SELECT COUNT(*) as count 
                        FROM subscribers 
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                        AND status != 'deleted'
                    """)
                    stats['new_last_30_days'] = cursor.fetchone()['count']
                    
                    stats['timestamp'] = datetime.utcnow().isoformat()
                    return stats
        except Exception as e:
            logger.error(f"Failed to get statistics: {str(e)}")
            raise
    
    # Legacy compatibility methods (from original legacy_db.py)
    def get_subscriber_by_any_id(self, identifier):
        """Fetches subscriber using UID, IMSI, or MSISDN for legacy compatibility."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Try different identifier types
                    for id_field in ['uid', 'imsi', 'msisdn', 'id', 'email']:
                        cursor.execute(f"SELECT * FROM subscribers WHERE {id_field} = %s", (identifier,))
                        result = cursor.fetchone()
                        if result:
                            return result
                    return None
        except Exception as e:
            logger.error(f"Failed to get subscriber by identifier {identifier}: {str(e)}")
            raise

# Factory function for easy instantiation
def create_legacy_db(secret_arn: str = None, host: str = None, port: int = 3306, database: str = 'legacydb') -> LegacyDatabase:
    """Create a LegacyDatabase instance with environment variable fallbacks."""
    return LegacyDatabase(
        secret_arn=secret_arn or os.getenv('LEGACY_DB_SECRET_ARN'),
        host=host or os.getenv('LEGACY_DB_HOST'),
        port=port or int(os.getenv('LEGACY_DB_PORT', '3306')),
        database=database or os.getenv('LEGACY_DB_NAME', 'legacydb')
    )

# Global instance for backward compatibility
legacy_db = None

def get_legacy_db() -> LegacyDatabase:
    """Get the global legacy database instance."""
    global legacy_db
    if legacy_db is None:
        legacy_db = create_legacy_db()
    return legacy_db

# Backward compatibility functions for existing code
@contextmanager
def get_connection():
    """Legacy compatibility function."""
    db = get_legacy_db()
    with db.get_connection() as conn:
        yield conn

def get_subscriber_by_any_id(identifier):
    """Legacy compatibility function."""
    return get_legacy_db().get_subscriber_by_any_id(identifier)

def delete_subscriber(uid):
    """Legacy compatibility function."""
    return get_legacy_db().delete_subscriber(uid)
