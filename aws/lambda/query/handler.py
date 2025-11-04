#!/usr/bin/env python3
"""
Enterprise Migration Portal - Enhanced SQL Query Handler
Handles POST /query requests with robust security, error handling, and database connectivity
"""
import json
import os
import boto3
from datetime import datetime
import logging
import re

# Conditional import for database connectivity
try:
    import pymysql
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("PyMySQL not available - will return sample data")

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_response(status_code, body, origin=None):
    """Create API Gateway response with CORS headers"""
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': origin or 'http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS,PATCH',
        'Access-Control-Max-Age': '86400'
    }
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body) if isinstance(body, dict) else body
    }

def create_error_response(status_code, message, origin=None):
    """Create error response with CORS headers"""
    return create_response(status_code, {
        'error': message,
        'statusCode': status_code,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }, origin)

def get_db_credentials():
    """Get database credentials from Secrets Manager or environment variables"""
    try:
        # Try to get from Secrets Manager first
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if secret_arn:
            secrets_client = boto3.client('secretsmanager')
            response = secrets_client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response['SecretString'])
            return {
                'host': secret.get('host'),
                'user': secret.get('username'),
                'password': secret.get('password'),
                'database': secret.get('dbname', 'subscriber_portal'),
                'port': int(secret.get('port', 3306))
            }
    except Exception as e:
        logger.warning(f"Could not get credentials from Secrets Manager: {e}")
    
    # Fallback to environment variables
    return {
        'host': os.environ.get('DB_HOST'),
        'user': os.environ.get('DB_USER', 'admin'),
        'password': os.environ.get('DB_PASSWORD'),
        'database': os.environ.get('DB_NAME', 'subscriber_portal'),
        'port': int(os.environ.get('DB_PORT', 3306))
    }

def get_db_connection():
    """Get database connection using credentials"""
    if not DB_AVAILABLE:
        raise Exception('Database connectivity not available - PyMySQL not installed')
    
    try:
        creds = get_db_credentials()
        
        if not creds['host'] or not creds['password']:
            raise Exception('Database connection parameters missing')
        
        connection = pymysql.connect(
            host=creds['host'],
            user=creds['user'],
            password=creds['password'],
            database=creds['database'],
            port=creds['port'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
            autocommit=True
        )
        
        logger.info(f"Connected to database: {creds['host']}:{creds['port']}")
        return connection
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise Exception(f"Database connection failed: {str(e)}")

def validate_sql_query(sql_query):
    """Validate SQL query for security - only allow SELECT statements"""
    sql_lower = sql_query.lower().strip()
    
    # Remove comments and normalize whitespace
    sql_clean = re.sub(r'--.*?$', '', sql_query, flags=re.MULTILINE)
    sql_clean = re.sub(r'/\*.*?\*/', '', sql_clean, flags=re.DOTALL)
    sql_clean = re.sub(r'\s+', ' ', sql_clean).strip().lower()
    
    # Block dangerous operations
    dangerous_keywords = [
        'drop', 'delete', 'update', 'insert', 'create', 'alter', 
        'truncate', 'grant', 'revoke', 'exec', 'execute', 'xp_',
        'sp_', 'into outfile', 'load_file', 'union', 'information_schema'
    ]
    
    for keyword in dangerous_keywords:
        if keyword in sql_clean:
            raise Exception(f'Forbidden keyword detected: {keyword}. Only SELECT queries are allowed.')
    
    # Ensure it's a SELECT query
    if not sql_clean.startswith('select'):
        raise Exception('Only SELECT queries are supported for security reasons')
    
    # Additional security checks
    if len(sql_query) > 2000:
        raise Exception('Query too long - maximum 2000 characters allowed')
    
    # Check for suspicious patterns
    suspicious_patterns = ['@@', 'char(', 'cast(', 'convert(', 'concat(']
    for pattern in suspicious_patterns:
        if pattern in sql_clean:
            raise Exception(f'Potentially unsafe pattern detected: {pattern}')
    
    return True

def execute_sql_query(sql_query):
    """Execute SQL query and return headers and rows"""
    connection = None
    start_time = datetime.utcnow()
    
    try:
        # Validate query first
        validate_sql_query(sql_query)
        
        # If database not available, return sample data
        if not DB_AVAILABLE:
            logger.warning("Database not available, returning sample data")
            return {
                'headers': ['uid', 'email', 'plan_id', 'status', 'created_at'],
                'rows': [
                    ['SUB_001', 'user1@example.com', 'PREMIUM', 'active', '2024-10-01 10:00:00'],
                    ['SUB_002', 'user2@example.com', 'BASIC', 'active', '2024-10-02 11:30:00'],
                    ['SUB_003', 'user3@example.com', 'PREMIUM', 'inactive', '2024-10-03 09:15:00'],
                    ['SUB_004', 'user4@example.com', 'BASIC', 'pending', '2024-10-04 14:20:00'],
                    ['SUB_005', 'user5@example.com', 'ENTERPRISE', 'active', '2024-10-05 16:45:00']
                ],
                'row_count': 5,
                'execution_time': (datetime.utcnow() - start_time).total_seconds(),
                'sample_data': True
            }
        
        # Connect to database
        connection = get_db_connection()
        
        with connection.cursor() as cursor:
            logger.info(f"Executing query: {sql_query[:200]}...")
            cursor.execute(sql_query)
            
            # Get column names
            headers = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to list format (frontend expects arrays, not dicts)
            formatted_rows = []
            for row in rows:
                if isinstance(row, dict):
                    # Convert dict to list based on headers order
                    formatted_rows.append([str(row.get(header, '')) if row.get(header) is not None else '' for header in headers])
                else:
                    # Already a list/tuple
                    formatted_rows.append([str(cell) if cell is not None else '' for cell in row])
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(f"Query returned {len(formatted_rows)} rows with {len(headers)} columns in {execution_time:.3f}s")
            
            return {
                'headers': headers,
                'rows': formatted_rows,
                'row_count': len(formatted_rows),
                'execution_time': execution_time,
                'sample_data': False
            }
            
    except pymysql.Error as e:
        logger.error(f"Database error: {str(e)}")
        error_msg = f"Database error: {str(e)}"
        if 'Unknown column' in str(e):
            error_msg = f"SQL Error: Unknown column in query. {str(e)}"
        elif 'syntax' in str(e).lower():
            error_msg = f"SQL Syntax Error: {str(e)}"
        elif 'access denied' in str(e).lower():
            error_msg = "Database access denied. Check your permissions."
        raise Exception(error_msg)
    except Exception as e:
        logger.error(f"Query execution error: {str(e)}")
        raise Exception(str(e))
    finally:
        if connection:
            connection.close()
            logger.debug("Database connection closed")

def lambda_handler(event, context):
    """Handle POST /query requests with enhanced security and error handling"""
    try:
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers', {})
        origin = headers.get('origin') or headers.get('Origin') or 'http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com'
        
        logger.info(f"🔍 Query Lambda called: {method} from origin: {origin}")
        
        # Handle CORS preflight
        if method == 'OPTIONS':
            logger.info("Handling CORS preflight request")
            return create_response(200, {'message': 'CORS preflight handled'}, origin=origin)
        
        # Only allow POST requests
        if method != 'POST':
            return create_error_response(405, 'Only POST method allowed', origin=origin)
        
        # Parse request body
        body_str = event.get('body', '{}')
        if isinstance(body_str, str):
            body = json.loads(body_str)
        else:
            body = body_str
        
        # Extract SQL query
        sql_query = body.get('sql_query', '').strip()
        if not sql_query:
            return create_error_response(400, 'sql_query is required in request body', origin=origin)
        
        logger.info(f"Executing SQL query: {sql_query[:200]}{'...' if len(sql_query) > 200 else ''}")
        
        # Execute query
        try:
            result = execute_sql_query(sql_query)
        except Exception as e:
            error_msg = str(e)
            if 'Database connection failed' in error_msg:
                logger.error(f"Database connectivity issue: {error_msg}")
                return create_error_response(503, f'Database service unavailable: {error_msg}', origin=origin)
            else:
                logger.error(f"Query execution failed: {error_msg}")
                return create_error_response(400, error_msg, origin=origin)
        
        # Return results in expected format
        response_data = {
            'headers': result['headers'],
            'rows': result['rows'],
            'metadata': {
                'row_count': result['row_count'],
                'execution_time': f"{result['execution_time']:.3f}s",
                'sample_data': result.get('sample_data', False),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        }
        
        logger.info(f"Query successful: {result['row_count']} rows returned")
        return create_response(200, response_data, origin=origin)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return create_error_response(400, 'Invalid JSON in request body', origin=origin)
    
    except Exception as e:
        logger.error(f"Query handler error: {str(e)}")
        return create_error_response(500, f'Internal server error: {str(e)}', origin=origin)

# For local testing
if __name__ == "__main__":
    # Test the query handler locally
    test_event = {
        'httpMethod': 'POST',
        'headers': {'origin': 'http://localhost:3000'},
        'body': json.dumps({
            'sql_query': 'SELECT * FROM subscribers LIMIT 5'
        })
    }
    
    result = lambda_handler(test_event, {})
    print(json.dumps(result, indent=2))
