#!/usr/bin/env python3
"""
Legacy Database Schema Setup Script
Run this once to initialize the legacy MySQL database schema
"""

import pymysql
import json
import os
import logging
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_credentials():
    """Get database credentials from AWS Secrets Manager"""
    try:
        secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
        secret_arn = 'arn:aws:secretsmanager:us-east-1:144395889420:secret:subscriber-legacy-db-secret-qWXjZz'
        
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret_data = json.loads(response['SecretString'])
        
        return {
            'host': secret_data.get('host', 'subscriber-migration-legacydb.cwd6wssgy4kr.us-east-1.rds.amazonaws.com'),
            'username': secret_data.get('username', 'admin'),
            'password': secret_data.get('password'),
            'port': int(secret_data.get('port', 3306)),
            'database': secret_data.get('dbname', 'legacydb')
        }
    except Exception as e:
        logger.error(f"Error getting credentials: {str(e)}")
        raise

def setup_database_schema():
    """Setup the legacy database schema"""
    try:
        creds = get_db_credentials()
        logger.info(f"Connecting to MySQL at {creds['host']}:{creds['port']}")
        
        # Connect without specifying database first
        connection = pymysql.connect(
            host=creds['host'],
            user=creds['username'],
            password=creds['password'],
            port=creds['port'],
            charset='utf8mb4',
            autocommit=True,
            connect_timeout=30
        )
        
        cursor = connection.cursor()
        
        # Create database if it doesn't exist
        logger.info(f"Creating database '{creds['database']}' if not exists...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{creds['database']}`")
        cursor.execute(f"USE `{creds['database']}`")
        
        # Create subscribers table with comprehensive schema
        logger.info("Creating subscribers table...")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `subscribers` (
            `subscriber_id` VARCHAR(64) NOT NULL PRIMARY KEY,
            `name` VARCHAR(255) NOT NULL,
            `email` VARCHAR(255) NOT NULL,
            `phone` VARCHAR(32) DEFAULT '',
            `plan` VARCHAR(64) DEFAULT 'basic',
            `status` VARCHAR(32) DEFAULT 'active',
            `region` VARCHAR(64) DEFAULT 'us-east-1',
            `created_date` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            
            -- Indexes for better performance
            INDEX `idx_email` (`email`),
            INDEX `idx_status` (`status`),
            INDEX `idx_plan` (`plan`),
            INDEX `idx_region` (`region`),
            INDEX `idx_updated_at` (`updated_at`),
            
            -- Ensure email uniqueness
            UNIQUE KEY `unique_email` (`email`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        cursor.execute(create_table_sql)
        logger.info("✅ Subscribers table created successfully")
        
        # Insert sample data if table is empty
        cursor.execute("SELECT COUNT(*) as count FROM subscribers")
        count_result = cursor.fetchone()
        
        if count_result[0] == 0:
            logger.info("Inserting sample legacy subscribers...")
            
            sample_subscribers = [
                ('LEGACY_001', 'John Legacy User', 'john.legacy@example.com', '+1-555-0001', 'premium', 'active', 'us-east-1'),
                ('LEGACY_002', 'Jane Legacy User', 'jane.legacy@example.com', '+1-555-0002', 'basic', 'active', 'us-west-2'),
                ('LEGACY_003', 'Bob Legacy User', 'bob.legacy@example.com', '+1-555-0003', 'enterprise', 'active', 'eu-west-1'),
                ('LEGACY_004', 'Alice Legacy User', 'alice.legacy@example.com', '+1-555-0004', 'premium', 'inactive', 'ap-southeast-1'),
                ('LEGACY_005', 'Charlie Legacy User', 'charlie.legacy@example.com', '+1-555-0005', 'basic', 'active', 'us-east-1')
            ]
            
            insert_sql = """
            INSERT INTO subscribers (subscriber_id, name, email, phone, plan, status, region)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            for subscriber in sample_subscribers:
                cursor.execute(insert_sql, subscriber)
            
            logger.info(f"✅ Inserted {len(sample_subscribers)} sample subscribers")
        else:
            logger.info(f"Legacy database already has {count_result[0]} subscribers")
        
        # Verify the setup
        cursor.execute("SELECT COUNT(*) as total, status, COUNT(*) as count FROM subscribers GROUP BY status")
        stats = cursor.fetchall()
        
        logger.info("📊 Legacy database statistics:")
        for stat in stats:
            logger.info(f"   {stat[1]}: {stat[2]} subscribers")
        
        # Test a sample query
        cursor.execute("SELECT subscriber_id, name, email, status FROM subscribers LIMIT 3")
        sample_data = cursor.fetchall()
        
        logger.info("📋 Sample data:")
        for row in sample_data:
            logger.info(f"   {row[0]}: {row[1]} ({row[3]})")
        
        connection.close()
        
        logger.info("🎉 Legacy database schema setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up database schema: {str(e)}")
        raise

def aws_lambda_handler(event, context):
    """AWS Lambda handler for database setup"""
    try:
        logger.info("Starting legacy database schema setup via Lambda...")
        
        result = setup_database_schema()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Legacy database schema setup completed successfully',
                'timestamp': datetime.now().isoformat(),
                'success': True
            })
        }
    except Exception as e:
        logger.error(f"Lambda setup error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to setup legacy database schema',
                'message': str(e),
                'timestamp': datetime.now().isoformat(),
                'success': False
            })
        }

if __name__ == '__main__':
    print("🚀 Legacy Database Schema Setup")
    print("================================")
    print("This script will initialize your MySQL legacy database with:")
    print("- Database: legacydb")
    print("- Table: subscribers")
    print("- Sample data: 5 test subscribers")
    print("- Indexes: For optimal performance")
    print("")
    
    confirm = input("Do you want to proceed? (y/N): ")
    if confirm.lower() == 'y':
        try:
            setup_database_schema()
            print("")
            print("✅ Success! Your legacy database is ready.")
            print("")
            print("Next steps:")
            print("1. Configure Lambda VPC settings")
            print("2. Deploy your enhanced backend")
            print("3. Test legacy provisioning mode in the portal")
            print("")
            print("🌐 Portal URL: http://subscriber-migration-stack-prod-frontend.s3-website-us-east-1.amazonaws.com/")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            print("Please check your AWS credentials and network connectivity.")
    else:
        print("❌ Setup cancelled.")