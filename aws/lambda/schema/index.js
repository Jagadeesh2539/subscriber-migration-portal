const mysql = require('mysql2/promise');
const AWS = require('aws-sdk');
const fs = require('fs').promises;

const secretsManager = new AWS.SecretsManager();

exports.handler = async (event) => {
    console.log('🗄️ Starting schema initialization...');
    
    try {
        // Get database credentials from Secrets Manager
        const secretArn = process.env.LEGACY_DB_SECRET_ARN;
        const dbHost = process.env.LEGACY_DB_HOST;
        
        if (!secretArn || !dbHost) {
            throw new Error('Missing required environment variables: LEGACY_DB_SECRET_ARN, LEGACY_DB_HOST');
        }
        
        console.log('📋 Retrieving database credentials...');
        const secretValue = await secretsManager.getSecretValue({ SecretId: secretArn }).promise();
        const secret = JSON.parse(secretValue.SecretString);
        
        const dbConfig = {
            host: dbHost,
            user: secret.username || secret.user,
            password: secret.password || secret.pass,
            database: secret.dbname || secret.database || '',
            connectTimeout: 30000,
            acquireTimeout: 30000,
            timeout: 30000
        };
        
        // Connect to MySQL
        console.log(`🔌 Connecting to MySQL at ${dbHost}...`);
        const connection = await mysql.createConnection(dbConfig);
        
        // Read SQL schema file
        const sqlFile = '/opt/rds_schema_update.sql';
        let sqlContent;
        
        try {
            sqlContent = await fs.readFile(sqlFile, 'utf8');
            console.log(`📄 Loaded SQL file: ${sqlFile}`);
        } catch (error) {
            console.log('📄 SQL file not found in Lambda, using embedded schema...');
            
            // Embedded schema as fallback
            sqlContent = `
CREATE DATABASE IF NOT EXISTS subscriber_migration;
USE subscriber_migration;

CREATE TABLE IF NOT EXISTS subscribers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    subscriber_id VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    status ENUM('ACTIVE', 'INACTIVE', 'PENDING', 'SUSPENDED') DEFAULT 'ACTIVE',
    subscription_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    migrated_at TIMESTAMP NULL,
    migration_status ENUM('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED') DEFAULT 'PENDING',
    
    INDEX idx_subscriber_id (subscriber_id),
    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_migration_status (migration_status),
    INDEX idx_created_at (created_at)
);

CREATE TABLE IF NOT EXISTS migration_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(100) UNIQUE NOT NULL,
    status ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED') DEFAULT 'PENDING',
    total_records INT DEFAULT 0,
    processed_records INT DEFAULT 0,
    failed_records INT DEFAULT 0,
    error_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    
    INDEX idx_job_id (job_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    action ENUM('CREATE', 'UPDATE', 'DELETE', 'MIGRATE') NOT NULL,
    old_values JSON,
    new_values JSON,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_action (action),
    INDEX idx_changed_at (changed_at)
);
`;
        }
        
        // Execute SQL statements
        const statements = sqlContent
            .split(';')
            .map(stmt => stmt.trim())
            .filter(stmt => stmt && !stmt.startsWith('--'));
            
        console.log(`📊 Executing ${statements.length} SQL statements...`);
        
        let executedCount = 0;
        let skippedCount = 0;
        
        for (const statement of statements) {
            if (!statement) continue;
            
            try {
                await connection.execute(statement);
                console.log(`✅ Executed: ${statement.substring(0, 50)}...`);
                executedCount++;
            } catch (error) {
                if (error.message.includes('already exists')) {
                    console.log(`⚠️ Skipped (exists): ${statement.substring(0, 50)}...`);
                    skippedCount++;
                } else {
                    console.error(`❌ Failed: ${statement.substring(0, 50)}...`);
                    console.error(`Error: ${error.message}`);
                    throw error;
                }
            }
        }
        
        await connection.end();
        
        const result = {
            statusCode: 200,
            body: {
                message: '✅ Schema initialization completed successfully',
                stats: {
                    executed: executedCount,
                    skipped: skippedCount,
                    total: statements.length
                }
            }
        };
        
        console.log('🎉 Schema initialization completed:', result.body);
        return result;
        
    } catch (error) {
        console.error('❌ Schema initialization failed:', error);
        
        return {
            statusCode: 500,
            body: {
                error: 'Schema initialization failed',
                message: error.message,
                stack: error.stack
            }
        };
    }
};