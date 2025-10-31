-- RDS MySQL Schema Update
-- Mirrors DynamoDB structure for CRUD and migration consistency
-- Created: 2025-10-31
-- Version: 3.0.0

-- =====================================================
-- CORE SUBSCRIBERS TABLE (mirrors DynamoDB attributes)
-- =====================================================

CREATE TABLE IF NOT EXISTS subscribers (
    uid VARCHAR(64) PRIMARY KEY NOT NULL COMMENT 'Unique subscriber identifier (matches DynamoDB key)',
    msisdn VARCHAR(20) UNIQUE NOT NULL COMMENT 'Mobile subscriber number (E.164 format)',
    imsi VARCHAR(20) UNIQUE NOT NULL COMMENT 'International Mobile Subscriber Identity',
    status ENUM('ACTIVE','INACTIVE','SUSPENDED','DELETED') NOT NULL DEFAULT 'ACTIVE' COMMENT 'Subscriber status (matches DynamoDB GSI)',
    plan_id VARCHAR(64) NULL COMMENT 'Service plan identifier (matches DynamoDB GSI)',
    email VARCHAR(120) NULL COMMENT 'Email address',
    first_name VARCHAR(80) NULL COMMENT 'First name',
    last_name VARCHAR(80) NULL COMMENT 'Last name', 
    address TEXT NULL COMMENT 'Physical address',
    date_of_birth DATE NULL COMMENT 'Date of birth (YYYY-MM-DD)',
    last_activity DATETIME NULL COMMENT 'Last activity timestamp',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    INDEX idx_status (status) COMMENT 'Index for status filtering (matches DynamoDB GSI)',
    INDEX idx_plan_id (plan_id) COMMENT 'Index for plan filtering (matches DynamoDB GSI)',
    INDEX idx_msisdn (msisdn) COMMENT 'Index for MSISDN lookups',
    INDEX idx_imsi (imsi) COMMENT 'Index for IMSI lookups',
    INDEX idx_last_activity (last_activity) COMMENT 'Index for activity-based queries',
    INDEX idx_created_at (created_at) COMMENT 'Index for temporal queries',
    INDEX idx_email (email) COMMENT 'Index for email-based searches'
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci 
  COMMENT='Core subscribers table mirroring DynamoDB structure';

-- =====================================================
-- AUDIT LOGS TABLE (for legacy-side auditing)
-- =====================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT 'Unique audit log identifier',
    table_name VARCHAR(64) NOT NULL COMMENT 'Affected table name',
    record_uid VARCHAR(64) NOT NULL COMMENT 'UID of affected record',
    operation ENUM('CREATE','UPDATE','DELETE') NOT NULL COMMENT 'Operation performed',
    old_values JSON NULL COMMENT 'Previous field values (UPDATE/DELETE only)',
    new_values JSON NULL COMMENT 'New field values (CREATE/UPDATE only)',
    changed_fields JSON NULL COMMENT 'List of changed field names',
    user_id VARCHAR(64) NULL COMMENT 'User who performed the operation',
    ip_address VARCHAR(45) NULL COMMENT 'IP address of the client',
    user_agent TEXT NULL COMMENT 'Client user agent string',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Audit timestamp',
    INDEX idx_table_record (table_name, record_uid) COMMENT 'Index for record-specific audit trails',
    INDEX idx_operation (operation) COMMENT 'Index for operation-based queries',
    INDEX idx_created_at (created_at) COMMENT 'Index for temporal audit queries',
    INDEX idx_user_id (user_id) COMMENT 'Index for user-based audit queries'
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci 
  COMMENT='Audit trail for legacy database operations';

-- =====================================================
-- MIGRATION JOBS TRACKING (optional - can use DynamoDB)
-- =====================================================

CREATE TABLE IF NOT EXISTS migration_jobs_legacy (
    job_id VARCHAR(64) PRIMARY KEY NOT NULL COMMENT 'Unique job identifier (matches DynamoDB)',
    job_type ENUM('MIGRATION','BULK_DELETE','AUDIT','EXPORT') NOT NULL COMMENT 'Type of migration job',
    job_status ENUM('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED') NOT NULL DEFAULT 'PENDING' COMMENT 'Current job status',
    source_system ENUM('CLOUD','LEGACY','DUAL') NOT NULL COMMENT 'Source system for the job',
    target_system ENUM('CLOUD','LEGACY','DUAL') NOT NULL COMMENT 'Target system for the job',
    input_file_key VARCHAR(512) NULL COMMENT 'S3 key for input file',
    output_file_key VARCHAR(512) NULL COMMENT 'S3 key for output file',
    processed_records INT UNSIGNED DEFAULT 0 COMMENT 'Number of processed records',
    success_records INT UNSIGNED DEFAULT 0 COMMENT 'Number of successfully processed records',
    failed_records INT UNSIGNED DEFAULT 0 COMMENT 'Number of failed records',
    error_message TEXT NULL COMMENT 'Error message if job failed',
    filters JSON NULL COMMENT 'Job filters and parameters',
    created_by VARCHAR(64) NULL COMMENT 'User who created the job',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Job creation timestamp',
    started_at DATETIME NULL COMMENT 'Job start timestamp',
    finished_at DATETIME NULL COMMENT 'Job completion timestamp',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
    INDEX idx_job_type (job_type) COMMENT 'Index for job type filtering',
    INDEX idx_job_status (job_status) COMMENT 'Index for status-based queries', 
    INDEX idx_created_at (created_at) COMMENT 'Index for temporal job queries',
    INDEX idx_created_by (created_by) COMMENT 'Index for user-based job queries'
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci 
  COMMENT='Migration job tracking (local copy of DynamoDB jobs)';

-- =====================================================
-- STORED PROCEDURES FOR COMMON OPERATIONS
-- =====================================================

-- Procedure to safely insert or update subscriber
DELIMITER //

CREATE PROCEDURE IF NOT EXISTS UpsertSubscriber(
    IN p_uid VARCHAR(64),
    IN p_msisdn VARCHAR(20),
    IN p_imsi VARCHAR(20), 
    IN p_status VARCHAR(20),
    IN p_plan_id VARCHAR(64),
    IN p_email VARCHAR(120),
    IN p_first_name VARCHAR(80),
    IN p_last_name VARCHAR(80),
    IN p_address TEXT,
    IN p_date_of_birth DATE,
    IN p_user_id VARCHAR(64)
)
BEGIN
    DECLARE v_operation VARCHAR(10);
    DECLARE v_old_values JSON DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    
    START TRANSACTION;
    
    -- Check if subscriber exists
    SET v_operation = IF((SELECT COUNT(*) FROM subscribers WHERE uid = p_uid) > 0, 'UPDATE', 'CREATE');
    
    -- Get old values for audit if updating
    IF v_operation = 'UPDATE' THEN
        SELECT JSON_OBJECT(
            'uid', uid,
            'msisdn', msisdn,
            'imsi', imsi,
            'status', status,
            'plan_id', plan_id,
            'email', email,
            'first_name', first_name,
            'last_name', last_name,
            'address', address,
            'date_of_birth', date_of_birth
        ) INTO v_old_values
        FROM subscribers WHERE uid = p_uid;
    END IF;
    
    -- Insert or update
    INSERT INTO subscribers (
        uid, msisdn, imsi, status, plan_id, email, first_name, last_name, address, date_of_birth
    ) VALUES (
        p_uid, p_msisdn, p_imsi, p_status, p_plan_id, p_email, p_first_name, p_last_name, p_address, p_date_of_birth
    )
    ON DUPLICATE KEY UPDATE
        msisdn = VALUES(msisdn),
        imsi = VALUES(imsi), 
        status = VALUES(status),
        plan_id = VALUES(plan_id),
        email = VALUES(email),
        first_name = VALUES(first_name),
        last_name = VALUES(last_name),
        address = VALUES(address),
        date_of_birth = VALUES(date_of_birth),
        updated_at = CURRENT_TIMESTAMP;
    
    -- Log audit trail
    INSERT INTO audit_logs (
        table_name, record_uid, operation, old_values, new_values, 
        changed_fields, user_id, created_at
    ) VALUES (
        'subscribers',
        p_uid,
        v_operation,
        v_old_values,
        JSON_OBJECT(
            'uid', p_uid,
            'msisdn', p_msisdn, 
            'imsi', p_imsi,
            'status', p_status,
            'plan_id', p_plan_id,
            'email', p_email,
            'first_name', p_first_name,
            'last_name', p_last_name,
            'address', p_address,
            'date_of_birth', p_date_of_birth
        ),
        NULL, -- changed_fields will be calculated by audit processor
        p_user_id,
        CURRENT_TIMESTAMP
    );
    
    COMMIT;
END//

DELIMITER ;

-- =====================================================
-- VIEWS FOR REPORTING AND ANALYTICS
-- =====================================================

-- Active subscribers summary view
CREATE OR REPLACE VIEW active_subscribers_summary AS
SELECT 
    status,
    plan_id,
    COUNT(*) as subscriber_count,
    COUNT(DISTINCT plan_id) as unique_plans,
    MIN(created_at) as oldest_subscriber,
    MAX(created_at) as newest_subscriber,
    COUNT(CASE WHEN email IS NOT NULL THEN 1 END) as subscribers_with_email,
    COUNT(CASE WHEN last_activity IS NOT NULL THEN 1 END) as subscribers_with_activity
FROM subscribers 
WHERE status IN ('ACTIVE', 'SUSPENDED')
GROUP BY status, plan_id;

-- Recent audit activity view
CREATE OR REPLACE VIEW recent_audit_activity AS
SELECT 
    DATE(created_at) as audit_date,
    operation,
    table_name,
    COUNT(*) as operation_count,
    COUNT(DISTINCT record_uid) as unique_records,
    COUNT(DISTINCT user_id) as unique_users
FROM audit_logs 
WHERE created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 7 DAY)
GROUP BY DATE(created_at), operation, table_name
ORDER BY audit_date DESC, operation_count DESC;

-- =====================================================
-- INITIAL DATA AND CONFIGURATION
-- =====================================================

-- Insert default configuration if not exists
INSERT IGNORE INTO subscribers (uid, msisdn, imsi, status, plan_id, email, first_name, last_name) VALUES
('SYSTEM_TEST_001', '+1555000001', '310260000000001', 'ACTIVE', 'BASIC', 'test1@example.com', 'Test', 'User1'),
('SYSTEM_TEST_002', '+1555000002', '310260000000002', 'ACTIVE', 'PREMIUM', 'test2@example.com', 'Test', 'User2'),
('SYSTEM_TEST_003', '+1555000003', '310260000000003', 'INACTIVE', 'BASIC', 'test3@example.com', 'Test', 'User3');

-- =====================================================
-- PERFORMANCE OPTIMIZATIONS
-- =====================================================

-- Optimize MySQL settings for better performance
SET SESSION innodb_buffer_pool_size = 134217728; -- 128MB
SET SESSION query_cache_type = ON;
SET SESSION query_cache_size = 67108864; -- 64MB

-- =====================================================
-- DATA VALIDATION AND CONSTRAINTS
-- =====================================================

-- Add triggers for data validation
DELIMITER //

CREATE TRIGGER IF NOT EXISTS validate_subscriber_before_insert
BEFORE INSERT ON subscribers
FOR EACH ROW
BEGIN
    -- Validate MSISDN format (E.164)
    IF NEW.msisdn NOT REGEXP '^\\+[1-9][0-9]{7,14}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid MSISDN format. Must be E.164 format (+1234567890)';
    END IF;
    
    -- Validate IMSI format (15 digits)
    IF NEW.imsi NOT REGEXP '^[0-9]{15}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid IMSI format. Must be exactly 15 digits';
    END IF;
    
    -- Validate email format if provided
    IF NEW.email IS NOT NULL AND NEW.email != '' AND NEW.email NOT REGEXP '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid email format';
    END IF;
END//

CREATE TRIGGER IF NOT EXISTS validate_subscriber_before_update
BEFORE UPDATE ON subscribers
FOR EACH ROW
BEGIN
    -- Same validations as insert
    IF NEW.msisdn NOT REGEXP '^\\+[1-9][0-9]{7,14}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid MSISDN format. Must be E.164 format (+1234567890)';
    END IF;
    
    IF NEW.imsi NOT REGEXP '^[0-9]{15}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid IMSI format. Must be exactly 15 digits';
    END IF;
    
    IF NEW.email IS NOT NULL AND NEW.email != '' AND NEW.email NOT REGEXP '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid email format';
    END IF;
END//

DELIMITER ;

-- =====================================================
-- UTILITY FUNCTIONS
-- =====================================================

-- Function to count subscribers by status
DELIMITER //

CREATE FUNCTION IF NOT EXISTS CountSubscribersByStatus(p_status VARCHAR(20))
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_count INT DEFAULT 0;
    SELECT COUNT(*) INTO v_count FROM subscribers WHERE status = p_status;
    RETURN v_count;
END//

DELIMITER ;

-- =====================================================
-- CLEANUP AND MAINTENANCE
-- =====================================================

-- Event to cleanup old audit logs (keep 90 days)
CREATE EVENT IF NOT EXISTS cleanup_audit_logs
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP
DO
  DELETE FROM audit_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);

-- Enable event scheduler if not already enabled
SET GLOBAL event_scheduler = ON;

-- =====================================================
-- FINAL STATUS MESSAGE
-- =====================================================

SELECT 
    'RDS Schema Update Complete' as status,
    CURRENT_TIMESTAMP as completed_at,
    COUNT(*) as total_subscribers
FROM subscribers;

-- Show table structure for verification
DESCRIBE subscribers;
DESCRIBE audit_logs;

-- Show indexes for performance verification
SHOW INDEX FROM subscribers;

-- Show sample data
SELECT 
    status,
    COUNT(*) as count,
    GROUP_CONCAT(DISTINCT plan_id) as plans
FROM subscribers 
GROUP BY status;

-- Performance analysis
SELECT 
    'Performance Analysis' as info,
    'Indexes created for optimal query performance' as indexes,
    'Triggers added for data validation' as validation,
    'Audit logging enabled for compliance' as auditing,
    'Views created for reporting' as reporting,
    'Cleanup events scheduled' as maintenance;
    
SELECT 'Schema update completed successfully!' as result;