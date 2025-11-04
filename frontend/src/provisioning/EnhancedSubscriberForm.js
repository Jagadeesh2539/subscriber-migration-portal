import React, { useState, useEffect } from 'react';
import { makeRequest } from '../api';

const EnhancedSubscriberForm = ({ initialData, onSuccess, onCancel, isEdit = false }) => {
  // Comprehensive form state with all industry fields
  const [formData, setFormData] = useState({
    // Core Identity
    uid: '',
    imsi: '',
    msisdn: '',
    
    // Outgoing Call Barring
    odbic: 'ODBIC_STD_RESTRICTIONS',
    odboc: 'ODBOC_STD_RESTRICTIONS',
    
    // Service Configuration
    plan_type: 'STANDARD_PREPAID',
    network_type: '4G_LTE',
    call_forwarding: 'CF_NONE',
    
    // Roaming & Limits
    roaming_enabled: 'NO_ROAMING',
    data_limit_mb: 1000,
    voice_minutes: '100',
    sms_count: '50',
    
    // Status & Billing
    status: 'ACTIVE',
    activation_date: new Date().toISOString().split('T')[0],
    last_recharge: '',
    balance_amount: 0.0,
    service_class: 'CONSUMER_SILVER',
    
    // Network Location
    location_area_code: 'LAC_1000',
    routing_area_code: 'RAC_2000',
    
    // Feature Flags
    gprs_enabled: true,
    volte_enabled: false,
    wifi_calling: false,
    
    // Services
    premium_services: 'VAS_BASIC',
    
    // Advanced Network Features
    hlr_profile: 'HLR_STANDARD_PROFILE',
    auc_profile: 'AUC_BASIC_AUTH',
    eir_status: 'EIR_VERIFIED',
    equipment_identity: '',
    network_access_mode: 'MODE_4G_PREFERRED',
    
    // QoS & Policy
    qos_profile: 'QOS_CLASS_3_BEST_EFFORT',
    apn_profile: 'APN_CONSUMER_INTERNET',
    charging_profile: 'CHARGING_STANDARD',
    fraud_profile: 'FRAUD_BASIC_CHECK',
    
    // Financial Limits
    credit_limit: 5000.00,
    spending_limit: 500.00,
    
    // Roaming Zones
    international_roaming_zone: 'ZONE_NONE',
    domestic_roaming_zone: 'ZONE_HOME_ONLY',
    
    // Supplementary Services
    supplementary_services: 'SS_CLIP:SS_CW',
    value_added_services: 'VAS_BASIC_NEWS',
    
    // Content & Security
    content_filtering: 'CF_ADULT_CONTENT',
    parental_control: 'PC_DISABLED',
    emergency_services: 'ES_BASIC_E911',
    
    // Technical Capabilities
    lte_category: 'LTE_CAT_6',
    nr_category: 'N/A',
    bearer_capability: 'BC_SPEECH:BC_DATA_64K',
    teleservices: 'TS_SPEECH:TS_SMS',
    basic_services: 'BS_BEARER_SPEECH:BS_PACKET_DATA',
    
    // Operator Services
    operator_services: 'OS_STANDARD_SUPPORT',
    network_features: 'NF_BASIC_LTE',
    security_features: 'SF_BASIC_AUTH',
    
    // Management
    mobility_management: 'MM_BASIC',
    session_management: 'SM_BASIC'
  });
  
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [activeTab, setActiveTab] = useState('basic');
  
  // Field options/enums
  const fieldOptions = {
    odbic: [
      'ODBIC_UNRESTRICTED', 'ODBIC_CAT1_BARRED', 'ODBIC_INTL_BARRED',
      'ODBIC_INTL_PREMIUM_ALLOWED', 'ODBIC_STD_RESTRICTIONS', 'ODBIC_MVNO_STANDARD',
      'ODBIC_M2M_RESTRICTED', 'ODBIC_TEST_UNRESTRICTED'
    ],
    odboc: [
      'ODBOC_UNRESTRICTED', 'ODBOC_PREMIUM_RESTRICTED', 'ODBOC_PREMIUM_BARRED',
      'ODBOC_STD_RESTRICTIONS', 'ODBOC_BASIC_BARRING', 'ODBOC_MVNO_RESTRICTED',
      'ODBOC_M2M_DATA_ONLY', 'ODBOC_TEST_MONITORED'
    ],
    plan_type: [
      'CORPORATE_POSTPAID', 'BUSINESS_POSTPAID', 'PREMIUM_PREPAID',
      'STANDARD_PREPAID', 'GOVERNMENT_POSTPAID', 'IOT_POSTPAID',
      'MVNO_POSTPAID', 'TEST_PREPAID'
    ],
    network_type: [
      '5G_SA_NSA', '5G_NSA', '5G_SA_SECURE', '4G_LTE_ADVANCED',
      '4G_LTE', '4G_LTE_M', '5G_TEST'
    ],
    service_class: [
      'ENTERPRISE_PLATINUM', 'BUSINESS_GOLD', 'CONSUMER_PREMIUM',
      'CONSUMER_SILVER', 'GOVERNMENT_SECURE', 'IOT_INDUSTRIAL',
      'MVNO_GOLD', 'TEST_PLATINUM'
    ],
    status: ['ACTIVE', 'SUSPENDED', 'BARRED', 'TERMINATED'],
    roaming_enabled: [
      'GLOBAL_ROAMING', 'GLOBAL_SECURE_ROAMING', 'REGIONAL_ROAMING_PLUS',
      'LIMITED_ROAMING', 'MVNO_ROAMING', 'GLOBAL_M2M_ROAMING',
      'TEST_ROAMING_ENABLED', 'NO_ROAMING'
    ],
    parental_control: [
      'PC_DISABLED', 'PC_ENABLED_BASIC', 'PC_ENABLED_MODERATE', 'PC_ENABLED_STRICT'
    ]
  };
  
  // Load initial data if editing
  useEffect(() => {
    if (initialData) {
      setFormData(prev => ({ ...prev, ...initialData }));
    }
  }, [initialData]);
  
  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: null }));
    }
  };
  
  const validateForm = () => {
    const newErrors = {};
    
    // Required fields validation
    if (!formData.uid.trim()) newErrors.uid = 'UID is required';
    if (!formData.imsi.trim()) newErrors.imsi = 'IMSI is required';
    if (!formData.msisdn.trim()) newErrors.msisdn = 'MSISDN is required';
    
    // Format validation
    if (formData.imsi && formData.imsi.length !== 15) {
      newErrors.imsi = 'IMSI must be 15 digits';
    }
    if (formData.msisdn && !/^\d{10,15}$/.test(formData.msisdn)) {
      newErrors.msisdn = 'MSISDN must be 10-15 digits';
    }
    
    // Numeric field validation
    if (formData.data_limit_mb < 0) {
      newErrors.data_limit_mb = 'Data limit must be positive';
    }
    if (formData.credit_limit < 0) {
      newErrors.credit_limit = 'Credit limit must be positive';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    setLoading(true);
    
    try {
      const endpoint = isEdit ? `/provision/subscriber/${formData.uid}` : '/provision/subscriber';
      const method = isEdit ? 'PUT' : 'POST';
      
      const response = await makeRequest(endpoint, {
        method,
        data: formData
      });
      
      if (response.status === 'success' || response.msg?.includes('successfully')) {
        onSuccess?.(response);
      } else {
        throw new Error(response.msg || 'Operation failed');
      }
      
    } catch (error) {
      console.error('Form submission error:', error);
      setErrors({ submit: error.message || 'An error occurred' });
    } finally {
      setLoading(false);
    }
  };
  
  const renderSelectField = (name, label, options, required = false) => (
    <div className="form-group">
      <label className="form-label">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <select
        className={`form-control ${errors[name] ? 'border-red-500' : ''}`}
        value={formData[name] || ''}
        onChange={(e) => handleInputChange(name, e.target.value)}
        required={required}
      >
        {options.map(option => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
      {errors[name] && <span className="text-red-500 text-sm">{errors[name]}</span>}
    </div>
  );
  
  const renderInputField = (name, label, type = 'text', required = false, placeholder = '') => (
    <div className="form-group">
      <label className="form-label">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        type={type}
        className={`form-control ${errors[name] ? 'border-red-500' : ''}`}
        value={formData[name] || ''}
        onChange={(e) => handleInputChange(name, e.target.value)}
        required={required}
        placeholder={placeholder}
        disabled={isEdit && name === 'uid'}
      />
      {errors[name] && <span className="text-red-500 text-sm">{errors[name]}</span>}
    </div>
  );
  
  const renderCheckboxField = (name, label) => (
    <div className="form-group">
      <label className="flex items-center">
        <input
          type="checkbox"
          className="mr-2"
          checked={formData[name] || false}
          onChange={(e) => handleInputChange(name, e.target.checked)}
        />
        <span className="form-label mb-0">{label}</span>
      </label>
    </div>
  );
  
  const tabs = [
    { id: 'basic', label: 'Basic Info', icon: '📱' },
    { id: 'service', label: 'Service Config', icon: '⚙️' },
    { id: 'network', label: 'Network & QoS', icon: '📡' },
    { id: 'billing', label: 'Billing & Limits', icon: '💰' },
    { id: 'features', label: 'Features & VAS', icon: '✨' },
    { id: 'technical', label: 'Technical', icon: '🔧' }
  ];
  
  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-lg">
        <div className="border-b border-gray-200">
          <div className="px-6 py-4">
            <h2 className="text-2xl font-bold text-gray-900">
              {isEdit ? '✏️ Edit Subscriber' : '➕ Create New Subscriber'}
            </h2>
            <p className="text-gray-600 mt-1">
              {isEdit ? 'Update subscriber information' : 'Configure comprehensive subscriber profile'}
            </p>
          </div>
          
          {/* Tab Navigation */}
          <div className="flex space-x-0 overflow-x-auto">
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600 bg-blue-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6">
          {/* Basic Info Tab */}
          {activeTab === 'basic' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-3">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">📱 Core Identity</h3>
              </div>
              {renderInputField('uid', 'Subscriber ID (UID)', 'text', true, 'e.g., SUB001')}
              {renderInputField('imsi', 'IMSI', 'text', true, '15-digit IMSI (e.g., 404103548762341)')}
              {renderInputField('msisdn', 'MSISDN', 'text', true, 'Phone number (e.g., 919876543210)')}
              {renderSelectField('status', 'Status', fieldOptions.status, true)}
              {renderInputField('activation_date', 'Activation Date', 'date', true)}
              {renderInputField('last_recharge', 'Last Recharge', 'date')}
              {renderInputField('equipment_identity', 'IMEI', 'text', false, '15-digit IMEI')}
            </div>
          )}
          
          {/* Service Configuration Tab */}
          {activeTab === 'service' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-3">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">⚙️ Service Configuration</h3>
              </div>
              {renderSelectField('plan_type', 'Plan Type', fieldOptions.plan_type, true)}
              {renderSelectField('service_class', 'Service Class', fieldOptions.service_class, true)}
              {renderSelectField('network_type', 'Network Type', fieldOptions.network_type, true)}
              {renderSelectField('odbic', 'Outgoing Calls - International', fieldOptions.odbic)}
              {renderSelectField('odboc', 'Outgoing Calls - Other', fieldOptions.odboc)}
              {renderInputField('call_forwarding', 'Call Forwarding', 'text', false, 'CF_CFU:number;CF_CFB:number')}
              {renderSelectField('roaming_enabled', 'Roaming Configuration', fieldOptions.roaming_enabled)}
              {renderInputField('international_roaming_zone', 'International Roaming Zone', 'text')}
              {renderInputField('domestic_roaming_zone', 'Domestic Roaming Zone', 'text')}
            </div>
          )}
          
          {/* Network & QoS Tab */}
          {activeTab === 'network' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-3">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">📡 Network & Quality of Service</h3>
              </div>
              {renderInputField('location_area_code', 'Location Area Code', 'text', false, 'LAC_1000')}
              {renderInputField('routing_area_code', 'Routing Area Code', 'text', false, 'RAC_2000')}
              {renderInputField('hlr_profile', 'HLR Profile', 'text')}
              {renderInputField('auc_profile', 'AUC Profile', 'text')}
              {renderInputField('eir_status', 'EIR Status', 'text')}
              {renderInputField('network_access_mode', 'Network Access Mode', 'text')}
              {renderInputField('qos_profile', 'QoS Profile', 'text')}
              {renderInputField('apn_profile', 'APN Profile', 'text')}
              {renderInputField('lte_category', 'LTE Category', 'text')}
              {renderInputField('nr_category', '5G NR Category', 'text')}
              
              <div className="lg:col-span-3">
                <h4 className="text-md font-semibold text-gray-800 mb-3">📶 Feature Enablement</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {renderCheckboxField('gprs_enabled', 'GPRS Enabled')}
                  {renderCheckboxField('volte_enabled', 'VoLTE Enabled')}
                  {renderCheckboxField('wifi_calling', 'WiFi Calling')}
                </div>
              </div>
            </div>
          )}
          
          {/* Billing & Limits Tab */}
          {activeTab === 'billing' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-3">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">💰 Billing & Usage Limits</h3>
              </div>
              {renderInputField('balance_amount', 'Current Balance', 'number', false, '0.00')}
              {renderInputField('credit_limit', 'Credit Limit', 'number', false, '5000.00')}
              {renderInputField('spending_limit', 'Daily Spending Limit', 'number', false, '500.00')}
              {renderInputField('data_limit_mb', 'Data Limit (MB)', 'number', false, '1000')}
              {renderInputField('voice_minutes', 'Voice Minutes', 'text', false, '100 or UNLIMITED')}
              {renderInputField('sms_count', 'SMS Count', 'text', false, '50 or UNLIMITED')}
              {renderInputField('charging_profile', 'Charging Profile', 'text')}
              {renderInputField('fraud_profile', 'Fraud Profile', 'text')}
            </div>
          )}
          
          {/* Features & VAS Tab */}
          {activeTab === 'features' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-3">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">✨ Features & Value Added Services</h3>
              </div>
              {renderInputField('premium_services', 'Premium Services', 'text', false, 'VAS_BASIC:SERVICE1:SERVICE2')}
              {renderInputField('supplementary_services', 'Supplementary Services', 'text', false, 'SS_CLIP:SS_CW:SS_HOLD')}
              {renderInputField('value_added_services', 'Value Added Services', 'text', false, 'VAS_NEWS:VAS_MUSIC')}
              {renderInputField('operator_services', 'Operator Services', 'text')}
              {renderInputField('content_filtering', 'Content Filtering', 'text')}
              {renderSelectField('parental_control', 'Parental Control', fieldOptions.parental_control)}
              {renderInputField('emergency_services', 'Emergency Services', 'text')}
            </div>
          )}
          
          {/* Technical Tab */}
          {activeTab === 'technical' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-3">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">🔧 Technical Configuration</h3>
              </div>
              {renderInputField('bearer_capability', 'Bearer Capability', 'text', false, 'BC_SPEECH:BC_DATA_64K')}
              {renderInputField('teleservices', 'Teleservices', 'text', false, 'TS_SPEECH:TS_SMS')}
              {renderInputField('basic_services', 'Basic Services', 'text', false, 'BS_BEARER_SPEECH:BS_PACKET_DATA')}
              {renderInputField('network_features', 'Network Features', 'text')}
              {renderInputField('security_features', 'Security Features', 'text')}
              {renderInputField('mobility_management', 'Mobility Management', 'text')}
              {renderInputField('session_management', 'Session Management', 'text')}
            </div>
          )}
          
          {/* Error Display */}
          {errors.submit && (
            <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-700">{errors.submit}</p>
            </div>
          )}
          
          {/* Action Buttons */}
          <div className="mt-8 flex justify-end space-x-3 pt-6 border-t border-gray-200">
            <button
              type="button"
              onClick={onCancel}
              className="px-6 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center">
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Processing...
                </span>
              ) : (
                <span>{isEdit ? '✏️ Update Subscriber' : '➕ Create Subscriber'}</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EnhancedSubscriberForm;