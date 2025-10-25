-- Subscriber Migration Portal - Enhanced Legacy Schema (MySQL)
-- Idempotent schema alignment for comprehensive telecom profile

-- 1) Create enhanced table if not exists
CREATE TABLE IF NOT EXISTS subscribers_enhanced (
  uid VARCHAR(64) NOT NULL,
  imsi VARCHAR(32) NULL,
  msisdn VARCHAR(32) NULL,
  odbic VARCHAR(64) NOT NULL DEFAULT 'ODBIC_STD_RESTRICTIONS',
  odboc VARCHAR(64) NOT NULL DEFAULT 'ODBOC_STD_RESTRICTIONS',
  plan_type VARCHAR(64) NOT NULL DEFAULT 'STANDARD_PREPAID',
  network_type VARCHAR(64) NOT NULL DEFAULT '4G_LTE',
  call_forwarding VARCHAR(512) NOT NULL DEFAULT 'CF_NONE',
  roaming_enabled VARCHAR(64) NOT NULL DEFAULT 'NO_ROAMING',
  data_limit_mb INT NOT NULL DEFAULT 1000,
  voice_minutes VARCHAR(32) NOT NULL DEFAULT '100',
  sms_count VARCHAR(32) NOT NULL DEFAULT '50',
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  activation_date DATETIME NULL,
  last_recharge DATETIME NULL,
  balance_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  service_class VARCHAR(64) NOT NULL DEFAULT 'CONSUMER_SILVER',
  location_area_code VARCHAR(64) NULL,
  routing_area_code VARCHAR(64) NULL,
  gprs_enabled TINYINT(1) NOT NULL DEFAULT 1,
  volte_enabled TINYINT(1) NOT NULL DEFAULT 0,
  wifi_calling TINYINT(1) NOT NULL DEFAULT 0,
  premium_services VARCHAR(512) NULL,
  hlr_profile VARCHAR(128) NULL,
  auc_profile VARCHAR(128) NULL,
  eir_status VARCHAR(64) NULL,
  equipment_identity VARCHAR(64) NULL,
  network_access_mode VARCHAR(64) NULL,
  qos_profile VARCHAR(128) NULL,
  apn_profile VARCHAR(128) NULL,
  charging_profile VARCHAR(128) NULL,
  fraud_profile VARCHAR(128) NULL,
  credit_limit DECIMAL(12,2) NOT NULL DEFAULT 5000.00,
  spending_limit DECIMAL(12,2) NOT NULL DEFAULT 500.00,
  international_roaming_zone VARCHAR(64) NULL,
  domestic_roaming_zone VARCHAR(64) NULL,
  supplementary_services VARCHAR(512) NULL,
  value_added_services VARCHAR(512) NULL,
  content_filtering VARCHAR(64) NULL,
  parental_control VARCHAR(64) NULL,
  emergency_services VARCHAR(64) NULL,
  lte_category VARCHAR(32) NULL,
  nr_category VARCHAR(32) NULL,
  bearer_capability VARCHAR(128) NULL,
  teleservices VARCHAR(128) NULL,
  basic_services VARCHAR(128) NULL,
  operator_services VARCHAR(128) NULL,
  network_features VARCHAR(128) NULL,
  security_features VARCHAR(128) NULL,
  mobility_management VARCHAR(128) NULL,
  session_management VARCHAR(128) NULL,
  created_at DATETIME NULL,
  updated_at DATETIME NULL,
  PRIMARY KEY (uid),
  KEY idx_imsi (imsi),
  KEY idx_msisdn (msisdn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) Ensure columns exist (MySQL 8.0+: IF NOT EXISTS supported for some DDL; fallback pattern used)
-- This section uses conditional checks via INFORMATION_SCHEMA to be safe across versions

DELIMITER $$
CREATE PROCEDURE ensure_column(IN tbl VARCHAR(64), IN col VARCHAR(64), IN ddl TEXT)
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl AND COLUMN_NAME = col
  ) THEN
    SET @s = ddl;
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL ensure_column('subscribers_enhanced','odbic','ALTER TABLE subscribers_enhanced ADD COLUMN odbic VARCHAR(64) NOT NULL DEFAULT "ODBIC_STD_RESTRICTIONS"');
CALL ensure_column('subscribers_enhanced','odboc','ALTER TABLE subscribers_enhanced ADD COLUMN odboc VARCHAR(64) NOT NULL DEFAULT "ODBOC_STD_RESTRICTIONS"');
CALL ensure_column('subscribers_enhanced','plan_type','ALTER TABLE subscribers_enhanced ADD COLUMN plan_type VARCHAR(64) NOT NULL DEFAULT "STANDARD_PREPAID"');
CALL ensure_column('subscribers_enhanced','network_type','ALTER TABLE subscribers_enhanced ADD COLUMN network_type VARCHAR(64) NOT NULL DEFAULT "4G_LTE"');
-- (Add calls for all remaining columns if running on older MySQL without IF NOT EXISTS)

-- 3) Create indexes if missing
DELIMITER $$
CREATE PROCEDURE ensure_index(IN tbl VARCHAR(64), IN idx VARCHAR(64), IN ddl TEXT)
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl AND INDEX_NAME = idx
  ) THEN
    SET @s = ddl;
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL ensure_index('subscribers_enhanced','idx_imsi','CREATE INDEX idx_imsi ON subscribers_enhanced (imsi)');
CALL ensure_index('subscribers_enhanced','idx_msisdn','CREATE INDEX idx_msisdn ON subscribers_enhanced (msisdn)');

-- 4) Clean up helper procedures (optional)
DROP PROCEDURE IF EXISTS ensure_column;
DROP PROCEDURE IF EXISTS ensure_index;
