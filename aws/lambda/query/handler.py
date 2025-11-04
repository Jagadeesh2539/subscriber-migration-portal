#!/usr/bin/env python3
"""
Enterprise Migration Portal - SQL Query Handler
Handles POST /query requests with SQL execution and result formatting
"""
import json
import os
import pymysql
import boto3
from datetime import datetime
import logging

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_response(status_code, body, origin=None):
    """Create API Gateway response with CORS headers"""
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': origin or '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS,PATCH',
        'Access-Control-Max-Age': '86400'
    }
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body)
    }

def create_error_response(status_code, message, origin=None):
    """Create error response with CORS headers"""
    return create_response(status_code, {
        'error': message,
        'statusCode': status_code,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }, origin)

def get_db_connection():
    """Get database connection using environment variables"""
    try:
        # Get database configuration from environment
        db_host = os.environ.get('DB_HOST')
        db_user = os.environ.get('DB_USER', 'admin')
        db_password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME', 'subscriber_portal')
        db_port = int(os.environ.get('DB_PORT', 3306))
        
        if not db_host or not db_password:
            raise Exception('Database connection parameters missing')
        
        connection = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=db_port,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30
        )
        
        return connection
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

def execute_sql_query(sql_query):
    """Execute SQL query and return headers and rows"""
    connection = None
    try:
        # Validate query (basic security)
        sql_lower = sql_query.lower().strip()
        
        # Block dangerous operations
        dangerous_keywords = ['drop', 'delete', 'update', 'insert', 'create', 'alter', 'truncate', 'grant', 'revoke']
        if any(keyword in sql_lower for keyword in dangerous_keywords):
            raise Exception('Only SELECT queries are allowed for security reasons')
        
        # Ensure it's a SELECT query
        if not sql_lower.startswith('select'):
            raise Exception('Only SELECT queries are supported')
        
        # Connect to database
        connection = get_db_connection()
        
        with connection.cursor() as cursor:
            logger.info(f"Executing query: {sql_query[:100]}...")
            cursor.execute(sql_query)
            
            # Get column names
            headers = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert rows to list format (frontend expects arrays, not dicts)
            formatted_rows = []
            for row in rows:
                if isinstance(row, dict):
                    formatted_rows.append([str(row.get(header, '')) for header in headers])
                else:
                    formatted_rows.append([str(cell) for cell in row])
            
            logger.info(f"Query returned {len(formatted_rows)} rows with {len(headers)} columns")
            
            return {
                'headers': headers,
                'rows': formatted_rows,
                'row_count': len(formatted_rows),
                'execution_time': datetime.utcnow().isoformat() + 'Z'
            }
            
    except pymysql.Error as e:
        logger.error(f"Database error: {str(e)}")
        error_msg = f"Database error: {str(e)}"
        if 'Unknown column' in str(e):
            error_msg = f"SQL Error: {str(e)}"
        elif 'syntax' in str(e).lower():
            error_msg = f"SQL Syntax Error: {str(e)}"
        raise Exception(error_msg)
    except Exception as e:
        logger.error(f"Query execution error: {str(e)}")
        raise
    finally:
        if connection:
            connection.close()

def lambda_handler(event, context):
    """Handle POST /query requests"""
    try:
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers', {})
        origin = headers.get('origin') or headers.get('Origin') or '*'
        
        logger.info(f"🔍 Query Lambda called: {method} from origin: {origin}")
        
        # Handle CORS preflight
        if method == 'OPTIONS':
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
        
        logger.info(f"Executing SQL query: {sql_query[:200]}...")
        
        # Execute query
        result = execute_sql_query(sql_query)
        
        # Return results in expected format
        response_data = {
            'headers': result['headers'],
            'rows': result['rows'],
            'metadata': {
                'row_count': result['row_count'],
                'execution_time': result['execution_time']
            }
        }
        
        return create_response(200, response_data, origin=origin)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return create_error_response(400, 'Invalid JSON in request body', origin=origin)
    
    except Exception as e:
        logger.error(f"Query handler error: {str(e)}")
        return create_error_response(500, str(e), origin=origin)
