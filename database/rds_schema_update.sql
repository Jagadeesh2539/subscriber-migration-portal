-- ==============================================================================
-- RDS MySQL Schema Update for Comprehensive Industry-Ready Subscriber Data
-- ==============================================================================

-- Create enhanced subscribers table if it doesn't exist
CREATE TABLE IF NOT EXISTS subscribers_enhanced (
    -- Core Identity
    uid VARCHAR(50) PRIMARY KEY,
    imsi VARCHAR(15) UNIQUE NOT NULL,
    msisdn VARCHAR(15) UNIQUE NOT NULL,
    
    -- Outgoing Call Barring
    odbic ENUM(
        'ODBIC_UNRESTRICTED', 'ODBIC_CAT1_BARRED', 'ODBIC_INTL_BARRED', 
        'ODBIC_INTL_PREMIUM_ALLOWED', 'ODBIC_STD_RESTRICTIONS', 'ODBIC_MVNO_STANDARD',
        'ODBIC_M2M_RESTRICTED', 'ODBIC_TEST_UNRESTRICTED'
    ) DEFAULT 'ODBIC_STD_RESTRICTIONS',
    
    odboc ENUM(
        'ODBOC_UNRESTRICTED', 'ODBOC_PREMIUM_RESTRICTED', 'ODBOC_PREMIUM_BARRED',
        'ODBOC_STD_RESTRICTIONS', 'ODBOC_BASIC_BARRING', 'ODBOC_MVNO_RESTRICTED',
        'ODBOC_M2M_DATA_ONLY', 'ODBOC_TEST_MONITORED'
    ) DEFAULT 'ODBOC_STD_RESTRICTIONS',
    
    -- Service Configuration
    plan_type ENUM(
        'CORPORATE_POSTPAID', 'BUSINESS_POSTPAID', 'PREMIUM_PREPAID', 
        'STANDARD_PREPAID', 'GOVERNMENT_POSTPAID', 'IOT_POSTPAID',
        'MVNO_POSTPAID', 'TEST_PREPAID'
    ) NOT NULL,
    
    network_type ENUM(
        '5G_SA_NSA', '5G_NSA', '5G_SA_SECURE', '4G_LTE_ADVANCED',
        '4G_LTE', '4G_LTE_M', '5G_TEST'
    ) NOT NULL,
    
    -- Call Forwarding (JSON format: CF_CFU:number;CF_CFB:number)
    call_forwarding TEXT,
    
    -- Roaming & Limits
    roaming_enabled ENUM(
        'GLOBAL_ROAMING', 'GLOBAL_SECURE_ROAMING', 'REGIONAL_ROAMING_PLUS',
        'LIMITED_ROAMING', 'MVNO_ROAMING', 'GLOBAL_M2M_ROAMING',
        'TEST_ROAMING_ENABLED', 'NO_ROAMING'
    ) DEFAULT 'NO_ROAMING',
    
    data_limit_mb INT DEFAULT 0,
    voice_minutes VARCHAR(20) DEFAULT '0', -- 0 = unlimited
    sms_count VARCHAR(20) DEFAULT '0', -- 0 = unlimited
    
    -- Status & Billing
    status ENUM('ACTIVE', 'SUSPENDED', 'BARRED', 'TERMINATED') DEFAULT 'ACTIVE',
    activation_date DATETIME NOT NULL,
    last_recharge DATETIME,
    balance_amount DECIMAL(10,2) DEFAULT 0.00,
    
    service_class ENUM(
        'ENTERPRISE_PLATINUM', 'BUSINESS_GOLD', 'CONSUMER_PREMIUM',
        'CONSUMER_SILVER', 'GOVERNMENT_SECURE', 'IOT_INDUSTRIAL',
        'MVNO_GOLD', 'TEST_PLATINUM'
    ) NOT NULL,
    
    -- Network Location
    location_area_code VARCHAR(10),
    routing_area_code VARCHAR(10),
    
    -- Feature Flags
    gprs_enabled BOOLEAN DEFAULT TRUE,
    volte_enabled BOOLEAN DEFAULT FALSE,
    wifi_calling BOOLEAN DEFAULT FALSE,
    
    -- Services (Colon-separated lists)
    premium_services TEXT,
    
    -- Advanced Network Features
    hlr_profile VARCHAR(50),
    auc_profile VARCHAR(50),
    eir_status ENUM('WHITELISTED', 'VERIFIED', 'CERTIFIED', 'APPROVED') DEFAULT 'VERIFIED',
    equipment_identity VARCHAR(20), -- IMEI
    
    network_access_mode ENUM(
        'DUAL_MODE_AUTO', 'MODE_5G_PREFERRED', 'MODE_4G_PREFERRED',
        'MODE_4G_ONLY', 'MODE_LTE_M_ONLY', 'MODE_ALL_TECHNOLOGIES',
        'MODE_SECURE_5G'
    ) DEFAULT 'MODE_4G_PREFERRED',
    
    -- QoS & Policy
    qos_profile ENUM(
        'QOS_CLASS_0_EMERGENCY', 'QOS_CLASS_1_GUARANTEED', 'QOS_CLASS_2_PRIORITY',
        'QOS_CLASS_3_BEST_EFFORT', 'QOS_CLASS_4_BACKGROUND', 'QOS_CLASS_5_IOT',
        'QOS_ALL_CLASSES'
    ) DEFAULT 'QOS_CLASS_3_BEST_EFFORT',
    
    apn_profile VARCHAR(100),
    charging_profile VARCHAR(100),
    fraud_profile VARCHAR(100),
    
    -- Financial Limits
    credit_limit DECIMAL(15,2) DEFAULT 0.00,
    spending_limit DECIMAL(10,2) DEFAULT 0.00,
    
    -- Roaming Zones
    international_roaming_zone VARCHAR(100),
    domestic_roaming_zone VARCHAR(100),
    
    -- Supplementary Services (Colon-separated)
    supplementary_services TEXT,
    value_added_services TEXT,
    
    -- Content & Security
    content_filtering TEXT,
    parental_control ENUM('DISABLED', 'ENABLED_BASIC', 'ENABLED_MODERATE', 'ENABLED_STRICT') DEFAULT 'DISABLED',
    emergency_services TEXT,
    
    -- Technical Capabilities
    lte_category ENUM('LTE_CAT_6', 'LTE_CAT_9', 'LTE_CAT_12', 'LTE_CAT_16', 'LTE_CAT_20', 'LTE_CAT_M1', 'LTE_CAT_ALL'),
    nr_category ENUM('NR_CAT_1', 'NR_CAT_2', 'NR_CAT_ALL'),
    bearer_capability TEXT,
    teleservices TEXT,
    basic_services TEXT,
    
    -- Operator Services
    operator_services TEXT,
    network_features TEXT,
    security_features TEXT,
    
    -- Management
    mobility_management TEXT,
    session_management TEXT,
    
    -- Audit Fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(50) DEFAULT 'system',
    updated_by VARCHAR(50) DEFAULT 'system',
    
    -- Indexes for Performance
    INDEX idx_imsi (imsi),
    INDEX idx_msisdn (msisdn),
    INDEX idx_status (status),
    INDEX idx_plan_type (plan_type),
    INDEX idx_network_type (network_type),
    INDEX idx_service_class (service_class),
    INDEX idx_activation_date (activation_date),
    INDEX idx_created_at (created_at)
);

-- ==============================================================================
-- Migrate Existing Data (if old subscribers table exists)
-- ==============================================================================

-- Check if old subscribers table exists and migrate data
INSERT INTO subscribers_enhanced (
    uid, imsi, msisdn, 
    plan_type, network_type, status, 
    activation_date, service_class,
    balance_amount, created_at, updated_at
)
SELECT 
    uid, 
    imsi, 
    msisdn, 
    COALESCE(plan_type, 'STANDARD_PREPAID'),
    COALESCE(network_type, '4G_LTE'),
    COALESCE(status, 'ACTIVE'),
    COALESCE(activation_date, NOW()),
    COALESCE(service_class, 'CONSUMER_SILVER'),
    COALESCE(balance_amount, 0.00),
    COALESCE(created_at, NOW()),
    COALESCE(updated_at, NOW())
FROM subscribers 
WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'subscribers')
AND NOT EXISTS (SELECT 1 FROM subscribers_enhanced WHERE subscribers_enhanced.uid = subscribers.uid);

-- ==============================================================================
-- Insert Sample Industry-Ready Data
-- ==============================================================================

-- Insert comprehensive industry-ready sample data
INSERT INTO subscribers_enhanced (
    uid, imsi, msisdn, odbic, odboc, plan_type, network_type, call_forwarding,
    roaming_enabled, data_limit_mb, voice_minutes, sms_count, status,
    activation_date, last_recharge, balance_amount, service_class,
    location_area_code, routing_area_code, gprs_enabled, volte_enabled,
    wifi_calling, premium_services, hlr_profile, auc_profile, eir_status,
    equipment_identity, network_access_mode, qos_profile, apn_profile,
    charging_profile, fraud_profile, credit_limit, spending_limit,
    international_roaming_zone, domestic_roaming_zone, supplementary_services,
    value_added_services, content_filtering, parental_control, emergency_services
) VALUES 
(
    'ENT001', '404103548762341', '919876543210', 'ODBIC_CAT1_BARRED', 'ODBOC_PREMIUM_RESTRICTED',
    'CORPORATE_POSTPAID', '5G_SA_NSA', 'CF_CFU:919999888777;CF_CFB:919999888778;CF_CFNRY:919999888779',
    'GLOBAL_ROAMING', 999999, 'UNLIMITED', 'UNLIMITED', 'ACTIVE',
    '2023-01-15 10:30:00', '2024-10-24 15:45:00', 15750.50, 'ENTERPRISE_PLATINUM',
    'LAC_1001', 'RAC_2001', TRUE, TRUE, TRUE,
    'VAS_ENTERPRISE_SUITE:CLOUD_PBX:VIDEO_CONF:SECURITY_SUITE:IOT_PLATFORM:AI_ANALYTICS',
    'HLR_ENT_PROFILE_A', 'AUC_STRONG_AUTH', 'WHITELISTED', '356789012345671',
    'DUAL_MODE_AUTO', 'QOS_CLASS_1_GUARANTEED', 'APN_ENTERPRISE_SECURE',
    'CHARGING_CORPORATE_FLAT', 'FRAUD_ENTERPRISE_MONITORING', 500000.00, 25000.00,
    'ZONE_GLOBAL_PREMIUM', 'ZONE_NATIONAL_UNLIMITED',
    'SS_CLIP:SS_CLIR:SS_CW:SS_HOLD:SS_MPTY:SS_ECT:SS_CCBS:SS_UUS',
    'VAS_MOBILE_OFFICE:VAS_FLEET_MGMT:VAS_EXPENSE_MGMT:VAS_SECURITY_DASHBOARD',
    'CF_ADULT_CONTENT:CF_GAMBLING:CF_VIOLENCE', 'ENABLED_STRICT',
    'ES_ENHANCED_E911:ES_LOCATION_SERVICES'
),
(
    'BIZ002', '404586321458963', '918765432109', 'ODBIC_INTL_PREMIUM_ALLOWED', 'ODBOC_STD_RESTRICTIONS',
    'BUSINESS_POSTPAID', '5G_NSA', 'CF_CFB:918888777666;CF_CFNRY:918888777667',
    'REGIONAL_ROAMING_PLUS', 100000, '5000', '2000', 'ACTIVE',
    '2023-06-20 14:15:00', '2024-10-24 12:30:00', 8950.25, 'BUSINESS_GOLD',
    'LAC_1002', 'RAC_2002', TRUE, TRUE, TRUE,
    'VAS_BUSINESS_PACK:MOBILE_BANKING:PUSH_EMAIL:VPN_ACCESS:CONFERENCE_BRIDGE',
    'HLR_BIZ_PROFILE_B', 'AUC_STANDARD_AUTH', 'VERIFIED', '356789012345672',
    'MODE_5G_PREFERRED', 'QOS_CLASS_2_PRIORITY', 'APN_BUSINESS_STANDARD',
    'CHARGING_BUSINESS_TIER', 'FRAUD_STANDARD_MONITORING', 100000.00, 5000.00,
    'ZONE_REGIONAL_BUSINESS', 'ZONE_NATIONAL_STANDARD',
    'SS_CLIP:SS_CW:SS_HOLD:SS_MPTY:SS_CCBS',
    'VAS_EXPENSE_TRACKING:VAS_BILL_MGMT:VAS_USAGE_ALERTS',
    'CF_ADULT_CONTENT', 'ENABLED_MODERATE', 'ES_STANDARD_E911'
),
(
    'PRE003', '404203698741258', '917654321098', 'ODBIC_INTL_BARRED', 'ODBOC_PREMIUM_BARRED',
    'PREMIUM_PREPAID', '4G_LTE_ADVANCED', 'CF_CFU:917777666555',
    'LIMITED_ROAMING', 50000, '1500', '500', 'ACTIVE',
    '2024-02-10 09:45:00', '2024-10-23 18:20:00', 1250.75, 'CONSUMER_PREMIUM',
    'LAC_1003', 'RAC_2003', TRUE, TRUE, FALSE,
    'VAS_ENTERTAINMENT:MUSIC_STREAMING:VIDEO_STREAMING:GAMING_PACK:SOCIAL_MEDIA_PACK',
    'HLR_CONSUMER_PROFILE_A', 'AUC_BASIC_AUTH', 'VERIFIED', '356789012345673',
    'MODE_4G_PREFERRED', 'QOS_CLASS_3_BEST_EFFORT', 'APN_CONSUMER_INTERNET',
    'CHARGING_PREPAID_STANDARD', 'FRAUD_BASIC_MONITORING', 10000.00, 500.00,
    'ZONE_LIMITED_INTL', 'ZONE_NATIONAL_STANDARD',
    'SS_CLIP:SS_CW:SS_HOLD',
    'VAS_MUSIC_DISCOVERY:VAS_VIDEO_LIBRARY:VAS_GAME_PORTAL',
    'CF_ADULT_CONTENT:CF_VIOLENCE', 'ENABLED_BASIC', 'ES_BASIC_E911'
),
(
    'GOV005', '404094785632147', '916543210987', 'ODBIC_UNRESTRICTED', 'ODBOC_UNRESTRICTED',
    'GOVERNMENT_POSTPAID', '5G_SA_SECURE', 'CF_CFU:916666555444;CF_CFB:916666555445;CF_CFNRY:916666555446',
    'GLOBAL_SECURE_ROAMING', 999999, 'UNLIMITED', 'UNLIMITED', 'ACTIVE',
    '2022-12-01 08:00:00', '2024-10-24 20:00:00', 25000.00, 'GOVERNMENT_SECURE',
    'LAC_1004', 'RAC_2004', TRUE, TRUE, TRUE,
    'VAS_GOVERNMENT:SECURE_MESSAGING:ENCRYPTED_VOICE:PRIORITY_ACCESS:EMERGENCY_BROADCAST',
    'HLR_GOV_SECURE_PROFILE', 'AUC_GOVERNMENT_AUTH', 'APPROVED', '356789012345675',
    'MODE_SECURE_5G', 'QOS_CLASS_0_EMERGENCY', 'APN_GOVERNMENT_SECURE',
    'CHARGING_GOVERNMENT_UNLIMITED', 'FRAUD_GOVERNMENT_EXEMPT', 999999.00, 999999.00,
    'ZONE_GOVERNMENT_GLOBAL', 'ZONE_GOVERNMENT_NATIONAL',
    'SS_ALL_SUPPLEMENTARY',
    'VAS_SECURE_SUITE:VAS_PRIORITY_ROUTING:VAS_EMERGENCY_SERVICES',
    'CF_DISABLED', 'DISABLED', 'ES_ENHANCED_GOVERNMENT'
),
(
    'IOT006', '405863214589635', 'M2M765432112', 'ODBIC_M2M_RESTRICTED', 'ODBOC_M2M_DATA_ONLY',
    'IOT_POSTPAID', '4G_LTE_M', 'CF_NONE',
    'GLOBAL_M2M_ROAMING', 1000, '0', '100', 'ACTIVE',
    '2024-01-12 12:00:00', '2024-10-24 06:00:00', 500.00, 'IOT_INDUSTRIAL',
    'LAC_1002', 'RAC_2002', TRUE, FALSE, FALSE,
    'VAS_IOT:DEVICE_MGMT:REMOTE_MONITORING:DATA_ANALYTICS:PREDICTIVE_MAINTENANCE',
    'HLR_IOT_PROFILE', 'AUC_M2M_AUTH', 'CERTIFIED', '356789012345676',
    'MODE_LTE_M_ONLY', 'QOS_CLASS_5_IOT', 'APN_IOT_INDUSTRIAL',
    'CHARGING_IOT_DATA_ONLY', 'FRAUD_IOT_MONITORING', 50000.00, 1000.00,
    'ZONE_M2M_GLOBAL', 'ZONE_M2M_NATIONAL',
    'SS_NONE',
    'VAS_IOT_PLATFORM:VAS_DEVICE_LIFECYCLE:VAS_SECURITY_IOT',
    'CF_DISABLED', 'DISABLED', 'ES_IOT_EMERGENCY'
)
ON DUPLICATE KEY UPDATE
    updated_at = CURRENT_TIMESTAMP;

-- ==============================================================================
-- Create Views for Easy Querying
-- ==============================================================================

-- Create view for basic subscriber info
CREATE OR REPLACE VIEW subscriber_basic_view AS
SELECT 
    uid, imsi, msisdn, status, plan_type, network_type, 
    service_class, activation_date, balance_amount,
    roaming_enabled, data_limit_mb, voice_minutes, sms_count
FROM subscribers_enhanced
WHERE status != 'TERMINATED';

-- Create view for enterprise subscribers
CREATE OR REPLACE VIEW enterprise_subscribers_view AS
SELECT 
    uid, imsi, msisdn, plan_type, network_type, service_class,
    premium_services, credit_limit, spending_limit,
    international_roaming_zone, odbic, odboc
FROM subscribers_enhanced
WHERE plan_type IN ('CORPORATE_POSTPAID', 'BUSINESS_POSTPAID', 'GOVERNMENT_POSTPAID')
AND status = 'ACTIVE';

-- Create view for network analytics
CREATE OR REPLACE VIEW network_analytics_view AS
SELECT 
    network_type,
    service_class,
    COUNT(*) as subscriber_count,
    AVG(data_limit_mb) as avg_data_limit,
    AVG(balance_amount) as avg_balance
FROM subscribers_enhanced
WHERE status = 'ACTIVE'
GROUP BY network_type, service_class;

-- ==============================================================================
-- Create Stored Procedures for Common Operations
-- ==============================================================================

DELIMITER //

-- Procedure to get subscriber summary
CREATE PROCEDURE GetSubscriberSummary(IN subscriber_uid VARCHAR(50))
BEGIN
    SELECT 
        uid, imsi, msisdn, status, plan_type, network_type,
        service_class, balance_amount, data_limit_mb,
        premium_services, roaming_enabled,
        created_at, updated_at
    FROM subscribers_enhanced
    WHERE uid = subscriber_uid;
END //

-- Procedure to update subscriber balance
CREATE PROCEDURE UpdateSubscriberBalance(IN subscriber_uid VARCHAR(50), IN new_balance DECIMAL(10,2))
BEGIN
    UPDATE subscribers_enhanced 
    SET balance_amount = new_balance,
        last_recharge = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE uid = subscriber_uid;
END //

-- Procedure to get subscribers by service class
CREATE PROCEDURE GetSubscribersByServiceClass(IN svc_class VARCHAR(50))
BEGIN
    SELECT uid, imsi, msisdn, plan_type, network_type, balance_amount
    FROM subscribers_enhanced
    WHERE service_class = svc_class
    AND status = 'ACTIVE'
    ORDER BY activation_date DESC;
END //

DELIMITER ;

-- ==============================================================================
-- Grant Permissions (Adjust as needed for your setup)
-- ==============================================================================

-- Grant permissions to application user
-- GRANT SELECT, INSERT, UPDATE, DELETE ON subscribers_enhanced TO 'app_user'@'%';
-- GRANT SELECT ON subscriber_basic_view TO 'app_user'@'%';
-- GRANT SELECT ON enterprise_subscribers_view TO 'app_user'@'%';
-- GRANT EXECUTE ON PROCEDURE GetSubscriberSummary TO 'app_user'@'%';
-- GRANT EXECUTE ON PROCEDURE UpdateSubscriberBalance TO 'app_user'@'%';
-- GRANT EXECUTE ON PROCEDURE GetSubscribersByServiceClass TO 'app_user'@'%';

-- ==============================================================================
-- Success Message
-- ==============================================================================

SELECT 'RDS Schema Update Completed Successfully! ✅' as Status,
       COUNT(*) as Total_Records 
FROM subscribers_enhanced;