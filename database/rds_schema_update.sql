-- =====================================================
-- Subscriber Migration Portal - Legacy RDS Schema
-- MySQL 5.7 compatible schema for subscriber data
-- =====================================================

-- Enable foreign key checks and set charset
SET foreign_key_checks = 1;
SET names utf8mb4;
-- MySQL 5.7 compatible sql_mode (NO_AUTO_CREATE_USER removed)
SET sql_mode = 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- =====================================================
-- SUBSCRIBERS TABLE (Main subscriber data)
-- =====================================================
CREATE TABLE IF NOT EXISTS subscribers (
    uid VARCHAR(50) PRIMARY KEY COMMENT 'Unique subscriber identifier',
    msisdn VARCHAR(20) NOT NULL UNIQUE COMMENT 'Mobile number',
    imsi VARCHAR(20) UNIQUE COMMENT 'International Mobile Subscriber Identity',
    plan_id VARCHAR(50) NOT NULL COMMENT 'Subscription plan identifier',
    status ENUM('ACTIVE', 'INACTIVE', 'SUSPENDED', 'TERMINATED') DEFAULT 'ACTIVE' COMMENT 'Subscriber status',
    barring_flags JSON COMMENT 'Barring configuration as JSON object',
    addons JSON COMMENT 'Additional services as JSON array',
    services JSON COMMENT 'Provisioned services as JSON array',
    provisioning_mode ENUM('LEGACY', 'CLOUD', 'DUAL') DEFAULT 'LEGACY' COMMENT 'Current provisioning system',
    activation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Account activation date',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last modification timestamp',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    sync_status ENUM('SYNCED', 'PENDING_SYNC', 'SYNC_FAILED', 'NOT_SYNCED') DEFAULT 'NOT_SYNCED' COMMENT 'Cloud sync status',
    last_sync_at TIMESTAMP NULL COMMENT 'Last successful sync timestamp',
    cloud_uid VARCHAR(50) NULL COMMENT 'Corresponding UID in cloud system',
    notes TEXT COMMENT 'Administrative notes'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Main subscriber data table';

-- Indexes for subscribers table (MySQL 5.7 compatible)
CREATE INDEX idx_subscribers_msisdn ON subscribers (msisdn);
CREATE INDEX idx_subscribers_imsi ON subscribers (imsi);
CREATE INDEX idx_subscribers_plan_id ON subscribers (plan_id);
CREATE INDEX idx_subscribers_status ON subscribers (status);
CREATE INDEX idx_subscribers_provisioning_mode ON subscribers (provisioning_mode);
CREATE INDEX idx_subscribers_sync_status ON subscribers (sync_status);
CREATE INDEX idx_subscribers_activation_date ON subscribers (activation_date);
CREATE INDEX idx_subscribers_last_updated ON subscribers (last_updated);

-- =====================================================
-- MIGRATION JOBS TABLE (Job tracking)
-- =====================================================
CREATE TABLE IF NOT EXISTS migration_jobs (
    job_id VARCHAR(36) PRIMARY KEY COMMENT 'UUID for migration job',
    job_type ENUM('MIGRATION', 'BULK_DELETE', 'AUDIT', 'EXPORT') NOT NULL COMMENT 'Type of job',
    job_status ENUM('PENDING', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED') DEFAULT 'PENDING' COMMENT 'Current job status',
    source_system ENUM('LEGACY', 'CLOUD', 'DUAL') NOT NULL COMMENT 'Source data system',
    target_system ENUM('LEGACY', 'CLOUD', 'DUAL') NOT NULL COMMENT 'Target data system',
    input_file_key VARCHAR(500) COMMENT 'S3 key for input file',
    output_file_key VARCHAR(500) COMMENT 'S3 key for output/result file',
    filters JSON COMMENT 'Job filters and parameters as JSON',
    total_records INT DEFAULT 0 COMMENT 'Total records to process',
    processed_records INT DEFAULT 0 COMMENT 'Records processed so far',
    success_records INT DEFAULT 0 COMMENT 'Successfully processed records',
    failed_records INT DEFAULT 0 COMMENT 'Failed record count',
    error_message TEXT COMMENT 'Error details if job failed',
    execution_arn VARCHAR(500) COMMENT 'Step Functions execution ARN',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Job creation timestamp',
    started_at TIMESTAMP NULL COMMENT 'Job start timestamp',
    finished_at TIMESTAMP NULL COMMENT 'Job completion timestamp',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    created_by VARCHAR(100) DEFAULT 'system' COMMENT 'User who created the job'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Migration job tracking table';

-- Indexes for migration_jobs table
CREATE INDEX idx_migration_jobs_type ON migration_jobs (job_type);
CREATE INDEX idx_migration_jobs_status ON migration_jobs (job_status);
CREATE INDEX idx_migration_jobs_created_at ON migration_jobs (created_at);
CREATE INDEX idx_migration_jobs_source_system ON migration_jobs (source_system);
CREATE INDEX idx_migration_jobs_execution_arn ON migration_jobs (execution_arn);
CREATE INDEX idx_migration_jobs_created_by ON migration_jobs (created_by);

-- =====================================================
-- SETTINGS TABLE (System configuration)
-- =====================================================
CREATE TABLE IF NOT EXISTS settings (
    sk VARCHAR(100) PRIMARY KEY COMMENT 'Setting key identifier',
    setting_value TEXT COMMENT 'Setting value (JSON or text)',
    setting_type ENUM('STRING', 'NUMBER', 'BOOLEAN', 'JSON', 'ARRAY') DEFAULT 'STRING' COMMENT 'Value data type',
    description TEXT COMMENT 'Setting description',
    is_encrypted BOOLEAN DEFAULT FALSE COMMENT 'Whether value is encrypted',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last modification timestamp',
    updated_by VARCHAR(100) DEFAULT 'system' COMMENT 'User who last updated'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='System settings and configuration';

-- Default settings
INSERT IGNORE INTO settings (sk, setting_value, setting_type, description) VALUES 
('provisioning_mode', 'LEGACY', 'STRING', 'Current provisioning mode: LEGACY, CLOUD, or DUAL'),
('migration_batch_size', '100', 'NUMBER', 'Default batch size for migration jobs'),
('audit_frequency', '24', 'NUMBER', 'Hours between automatic consistency audits'),
('max_concurrent_jobs', '5', 'NUMBER', 'Maximum concurrent migration jobs'),
('retention_days', '90', 'NUMBER', 'Data retention period in days'),
('enable_dual_write', 'false', 'BOOLEAN', 'Enable writes to both systems in DUAL mode'),
('sync_tolerance_minutes', '30', 'NUMBER', 'Acceptable sync delay in minutes');

-- =====================================================
-- AUDIT LOG TABLE (Change tracking)
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_log (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-incrementing log ID',
    entity_type ENUM('SUBSCRIBER', 'JOB', 'SETTING', 'USER') NOT NULL COMMENT 'Type of entity changed',
    entity_id VARCHAR(100) NOT NULL COMMENT 'ID of the changed entity',
    action ENUM('CREATE', 'UPDATE', 'DELETE', 'SYNC', 'MIGRATE') NOT NULL COMMENT 'Action performed',
    old_values JSON COMMENT 'Previous values as JSON',
    new_values JSON COMMENT 'New values as JSON',
    changed_fields JSON COMMENT 'List of changed field names',
    user_id VARCHAR(100) COMMENT 'User who made the change',
    source_system ENUM('LEGACY', 'CLOUD', 'API', 'MIGRATION', 'SYSTEM') DEFAULT 'API' COMMENT 'Source of the change',
    ip_address VARCHAR(45) COMMENT 'Client IP address',
    user_agent TEXT COMMENT 'Client user agent',
    session_id VARCHAR(100) COMMENT 'User session identifier',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Change timestamp'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Audit trail for all data changes';

-- Indexes for audit_log table
CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id);
CREATE INDEX idx_audit_action ON audit_log (action);
CREATE INDEX idx_audit_user ON audit_log (user_id);
CREATE INDEX idx_audit_created_at ON audit_log (created_at);
CREATE INDEX idx_audit_source_system ON audit_log (source_system);

-- =====================================================
-- USER MANAGEMENT TABLE (Authentication)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(36) PRIMARY KEY COMMENT 'UUID for user',
    username VARCHAR(100) NOT NULL UNIQUE COMMENT 'Login username',
    email VARCHAR(255) NOT NULL UNIQUE COMMENT 'User email address',
    password_hash VARCHAR(255) NOT NULL COMMENT 'Bcrypt password hash',
    full_name VARCHAR(200) COMMENT 'User full name',
    role ENUM('ADMIN', 'OPERATOR', 'VIEWER', 'AUDITOR') DEFAULT 'VIEWER' COMMENT 'User role and permissions',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Whether user account is active',
    last_login TIMESTAMP NULL COMMENT 'Last successful login timestamp',
    failed_login_attempts INT DEFAULT 0 COMMENT 'Consecutive failed login count',
    account_locked_until TIMESTAMP NULL COMMENT 'Account lock expiry timestamp',
    password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Last password change timestamp',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Account creation timestamp',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last account update timestamp'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User accounts and authentication';

-- Indexes for users table
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_role ON users (role);
CREATE INDEX idx_users_is_active ON users (is_active);
CREATE INDEX idx_users_last_login ON users (last_login);

-- Default admin user (password: 'SecureAdmin123!' - change immediately!)
INSERT IGNORE INTO users (user_id, username, email, password_hash, full_name, role) VALUES 
('00000000-0000-0000-0000-000000000001', 'admin', 'admin@company.com', 
 '$2b$12$rWZtQqNzQ5fPz7VaUKwxz.Hl8d7HZ9ZJjYnZ0a5F8l2JvZ1Yq3qLO', 
 'System Administrator', 'ADMIN');

-- =====================================================
-- SESSION MANAGEMENT TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id VARCHAR(36) PRIMARY KEY COMMENT 'UUID for session',
    user_id VARCHAR(36) NOT NULL COMMENT 'Reference to users.user_id',
    jwt_token_hash VARCHAR(255) NOT NULL COMMENT 'Hashed JWT token for validation',
    ip_address VARCHAR(45) COMMENT 'Client IP address',
    user_agent TEXT COMMENT 'Client user agent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Session creation timestamp',
    expires_at TIMESTAMP NOT NULL COMMENT 'Session expiry timestamp',
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last activity timestamp',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Whether session is active',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Active user sessions tracking';

-- Indexes for user_sessions table
CREATE INDEX idx_sessions_user_id ON user_sessions (user_id);
CREATE INDEX idx_sessions_expires_at ON user_sessions (expires_at);
CREATE INDEX idx_sessions_is_active ON user_sessions (is_active);
CREATE INDEX idx_sessions_last_activity ON user_sessions (last_activity);

-- =====================================================
-- PLAN DEFINITIONS TABLE (Subscription plans)
-- =====================================================
CREATE TABLE IF NOT EXISTS plan_definitions (
    plan_id VARCHAR(50) PRIMARY KEY COMMENT 'Unique plan identifier',
    plan_name VARCHAR(200) NOT NULL COMMENT 'Human-readable plan name',
    plan_type ENUM('PREPAID', 'POSTPAID', 'HYBRID') NOT NULL COMMENT 'Billing type',
    data_allowance_mb BIGINT DEFAULT 0 COMMENT 'Monthly data allowance in MB',
    voice_minutes INT DEFAULT 0 COMMENT 'Monthly voice minutes',
    sms_count INT DEFAULT 0 COMMENT 'Monthly SMS count',
    price_monthly DECIMAL(10,2) DEFAULT 0.00 COMMENT 'Monthly price in local currency',
    validity_days INT DEFAULT 30 COMMENT 'Plan validity in days',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Whether plan is currently available',
    features JSON COMMENT 'Plan features and limits as JSON',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Plan creation timestamp',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last plan update timestamp'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Subscription plan definitions';

-- Indexes for plan_definitions table
CREATE INDEX idx_plans_name ON plan_definitions (plan_name);
CREATE INDEX idx_plans_type ON plan_definitions (plan_type);
CREATE INDEX idx_plans_is_active ON plan_definitions (is_active);

-- Default plans
INSERT IGNORE INTO plan_definitions (plan_id, plan_name, plan_type, data_allowance_mb, voice_minutes, sms_count, price_monthly, features) VALUES 
('BASIC_PREPAID', 'Basic Prepaid', 'PREPAID', 1024, 100, 100, 10.00, '{"roaming": false, "hotspot": false}'),
('STANDARD_PREPAID', 'Standard Prepaid', 'PREPAID', 5120, 500, 500, 25.00, '{"roaming": true, "hotspot": true}'),
('PREMIUM_POSTPAID', 'Premium Postpaid', 'POSTPAID', 51200, 2000, 1000, 75.00, '{"roaming": true, "hotspot": true, "priority": true}'),
('UNLIMITED_POSTPAID', 'Unlimited Postpaid', 'POSTPAID', -1, -1, -1, 99.00, '{"unlimited": true, "roaming": true, "hotspot": true, "priority": true}');

-- =====================================================
-- SYNC CONFLICTS TABLE (Data consistency tracking)
-- =====================================================
CREATE TABLE IF NOT EXISTS sync_conflicts (
    conflict_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-incrementing conflict ID',
    subscriber_uid VARCHAR(50) NOT NULL COMMENT 'Subscriber UID with conflict',
    conflict_type ENUM('DATA_MISMATCH', 'MISSING_LEGACY', 'MISSING_CLOUD', 'TIMESTAMP_CONFLICT', 'STATUS_CONFLICT') NOT NULL COMMENT 'Type of sync conflict',
    field_name VARCHAR(100) COMMENT 'Specific field with conflict',
    legacy_value TEXT COMMENT 'Value in legacy system',
    cloud_value TEXT COMMENT 'Value in cloud system',
    resolution_status ENUM('PENDING', 'RESOLVED', 'IGNORED', 'MANUAL_REVIEW') DEFAULT 'PENDING' COMMENT 'Conflict resolution status',
    resolution_action TEXT COMMENT 'Action taken to resolve conflict',
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When conflict was detected',
    resolved_at TIMESTAMP NULL COMMENT 'When conflict was resolved',
    resolved_by VARCHAR(100) COMMENT 'User who resolved the conflict',
    INDEX idx_conflicts_subscriber_uid (subscriber_uid),
    INDEX idx_conflicts_type (conflict_type),
    INDEX idx_conflicts_status (resolution_status),
    INDEX idx_conflicts_detected_at (detected_at),
    FOREIGN KEY (subscriber_uid) REFERENCES subscribers(uid) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Data synchronization conflicts tracking';

-- =====================================================
-- MIGRATION BATCH TABLE (Batch processing tracking)
-- =====================================================
CREATE TABLE IF NOT EXISTS migration_batches (
    batch_id VARCHAR(36) PRIMARY KEY COMMENT 'UUID for batch',
    job_id VARCHAR(36) NOT NULL COMMENT 'Parent migration job ID',
    batch_number INT NOT NULL COMMENT 'Batch sequence number within job',
    batch_status ENUM('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'RETRYING') DEFAULT 'PENDING' COMMENT 'Batch processing status',
    input_records JSON COMMENT 'Input records for this batch as JSON array',
    processed_count INT DEFAULT 0 COMMENT 'Records processed in this batch',
    success_count INT DEFAULT 0 COMMENT 'Successful records in batch',
    error_count INT DEFAULT 0 COMMENT 'Failed records in batch',
    error_details JSON COMMENT 'Error details per failed record',
    started_at TIMESTAMP NULL COMMENT 'Batch processing start time',
    completed_at TIMESTAMP NULL COMMENT 'Batch completion time',
    retry_count INT DEFAULT 0 COMMENT 'Number of retry attempts',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Batch creation timestamp',
    INDEX idx_batches_job_id (job_id),
    INDEX idx_batches_status (batch_status),
    INDEX idx_batches_batch_number (job_id, batch_number),
    FOREIGN KEY (job_id) REFERENCES migration_jobs(job_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Migration batch processing tracking';

-- =====================================================
-- PERFORMANCE AND MAINTENANCE
-- =====================================================

-- Enable event scheduler
SET GLOBAL event_scheduler = ON;

-- Event to clean up old completed migration jobs (retain for 90 days)
DROP EVENT IF EXISTS cleanup_old_migration_jobs;
CREATE EVENT cleanup_old_migration_jobs
ON SCHEDULE EVERY 1 DAY
DO
  DELETE FROM migration_jobs 
  WHERE job_status IN ('COMPLETED', 'FAILED', 'CANCELLED') 
  AND created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);

-- Event to clean up expired user sessions
DROP EVENT IF EXISTS cleanup_expired_sessions;
CREATE EVENT cleanup_expired_sessions
ON SCHEDULE EVERY 1 HOUR
DO
  DELETE FROM user_sessions 
  WHERE expires_at < NOW() OR (is_active = FALSE AND last_activity < DATE_SUB(NOW(), INTERVAL 24 HOUR));

-- Event to reset failed login attempts daily
DROP EVENT IF EXISTS reset_failed_login_attempts;
CREATE EVENT reset_failed_login_attempts
ON SCHEDULE EVERY 1 DAY
DO
  UPDATE users 
  SET failed_login_attempts = 0, account_locked_until = NULL 
  WHERE account_locked_until < NOW();

-- =====================================================
-- SAMPLE DATA (Optional - for testing)
-- =====================================================

-- Sample subscribers for testing
INSERT IGNORE INTO subscribers (uid, msisdn, imsi, plan_id, status, barring_flags, addons, services) VALUES
('SUB001', '+1234567890', '310410123456789', 'BASIC_PREPAID', 'ACTIVE', 
 '{"outgoing_calls": false, "incoming_calls": false, "data": false, "sms": false}',
 '["CALLER_ID", "VOICEMAIL"]', 
 '["VOICE", "DATA", "SMS"]'),
('SUB002', '+1234567891', '310410123456790', 'STANDARD_PREPAID', 'ACTIVE',
 '{"outgoing_calls": false, "incoming_calls": false, "data": false, "sms": false}',
 '["INTERNATIONAL_ROAMING", "HOTSPOT"]',
 '["VOICE", "DATA", "SMS", "ROAMING"]'),
('SUB003', '+1234567892', '310410123456791', 'PREMIUM_POSTPAID', 'SUSPENDED',
 '{"outgoing_calls": true, "incoming_calls": false, "data": true, "sms": false}',
 '["PREMIUM_SUPPORT", "DEVICE_INSURANCE"]',
 '["VOICE", "DATA", "SMS", "ROAMING", "PRIORITY"]');

-- =====================================================
-- SUMMARY
-- =====================================================
-- Schema created successfully with:
-- - subscribers: main subscriber data with sync tracking
-- - migration_jobs: Step Functions job tracking
-- - settings: system configuration
-- - audit_log: change tracking and compliance
-- - user_sessions: JWT session management
-- - plan_definitions: subscription plan catalog
-- - sync_conflicts: data consistency issue tracking
-- - migration_batches: batch processing details
-- - Automated cleanup events for data retention
-- - Comprehensive indexes for performance
-- - Foreign key constraints for data integrity
-- - Sample data for testing
-- - MySQL 5.7 compatible syntax