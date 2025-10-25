import axios from 'axios';

// Enhanced API configuration for enterprise features
const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod';

console.log('[API] Enterprise API Base URL:', API_BASE_URL);

// Create enhanced axios instance
const API = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout for enterprise operations
  headers: {
    'Content-Type': 'application/json',
  },
});

// Enhanced token management
const getToken = () => {
  const token = localStorage.getItem('token');
  if (!token) {
    console.log('[Auth] No token found in localStorage');
    return null;
  }
  
  try {
    // Check if token has expiry information
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    if (user.tokenExpiry) {
      const expiry = new Date(user.tokenExpiry);
      if (expiry <= new Date()) {
        console.log('[Auth] Token expired, clearing storage');
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return null;
      }
    }
    
    console.log('[Auth] Valid token found, expires at:', user.tokenExpiry || 'no expiry');
    return token;
  } catch (error) {
    console.error('[Auth] Token validation error:', error);
    return token;
  }
};

// Enhanced request interceptor
API.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    console.log(`[API Request] ${config.method?.toUpperCase()} → ${config.url}`);
    return config;
  },
  (error) => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

// Enhanced response interceptor
API.interceptors.response.use(
  (response) => {
    const method = response.config.method?.toUpperCase();
    const url = response.config.url;
    const status = response.status;
    
    console.log(`[API Success] ✅ ${method} ${url} - ${status}`);
    
    // Log response data for debugging (truncated)
    if (response.data) {
      const dataStr = JSON.stringify(response.data).substring(0, 100);
      console.log(`[API Data] ${dataStr}${dataStr.length === 100 ? '...' : ''}`);
    }
    
    return response;
  },
  (error) => {
    const method = error.config?.method?.toUpperCase() || 'UNKNOWN';
    const url = error.config?.url || 'unknown';
    const status = error.response?.status || 'network';
    
    console.error(`[API Error] ❌ ${method} ${url} - ${status}`);
    
    // Handle specific error cases
    if (error.response?.status === 401) {
      console.warn('[Auth] Authentication failed - redirecting to login');
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    
    if (error.response?.status === 403) {
      console.warn('[Auth] Access forbidden - insufficient permissions');
    }
    
    if (error.response?.status >= 500) {
      console.error('[API] Server error - backend may be down');
    }
    
    return Promise.reject(error);
  }
);

// Enhanced API methods for enterprise features
const EnhancedAPI = {
  // ============ JOB MANAGEMENT ============
  
  // Get all jobs with filtering
  getJobs: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.type) params.append('type', filters.type);
    if (filters.status) params.append('status', filters.status);
    if (filters.requestedBy) params.append('requestedBy', filters.requestedBy);
    if (filters.limit) params.append('limit', filters.limit);
    
    return API.get(`/jobs?${params.toString()}`);
  },
  
  // Get single job status
  getJobStatus: (jobId) => {
    return API.get(`/jobs/${jobId}`);
  },
  
  // Cancel job
  cancelJob: (jobId) => {
    return API.post(`/jobs/${jobId}/cancel`);
  },
  
  // Copy job
  copyJob: (jobId) => {
    return API.post(`/jobs/${jobId}/copy`);
  },
  
  // Get job report
  getJobReport: (jobId) => {
    return API.get(`/jobs/${jobId}/report`);
  },
  
  // ============ BULK OPERATIONS ============
  
  // Create bulk migration job
  createMigrationJob: (options = {}) => {
    return API.post('/migration/bulk', {
      isSimulateMode: options.isSimulateMode || false,
      mode: options.mode || 'CLOUD'
    });
  },
  
  // Create bulk deletion job
  createDeletionJob: (options = {}) => {
    return API.post('/operations/bulk-delete', {
      isSimulateMode: options.isSimulateMode || false,
      mode: options.mode || 'CLOUD'
    });
  },
  
  // Create bulk audit job
  createAuditJob: (options = {}) => {
    return API.post('/operations/bulk-audit', {
      auditScope: options.auditScope || 'FULL',
      mode: 'DUAL_PROV'
    });
  },
  
  // Create data export job
  createDataExportJob: (options = {}) => {
    return API.post('/operations/data-export', {
      scope: options.scope || 'CLOUD',
      filters: options.filters || {}
    });
  },
  
  // ============ PROVISIONING ============
  
  // Single provision request
  createProvisionRequest: (provisionData) => {
    return API.post('/provision/request', provisionData);
  },
  
  // Get provisioning dashboard
  getProvisionDashboard: () => {
    return API.get('/provision/dashboard');
  },
  
  // Get provision history
  getProvisionHistory: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.mode) params.append('mode', filters.mode);
    if (filters.operation) params.append('operation', filters.operation);
    if (filters.status) params.append('status', filters.status);
    
    return API.get(`/provision/requests?${params.toString()}`);
  },
  
  // ============ MONITORING ============
  
  // Get system monitoring dashboard
  getMonitoringDashboard: () => {
    return API.get('/monitoring/dashboard');
  },
  
  // Get system health
  getSystemHealth: () => {
    return API.get('/health');
  },
  
  // ============ LEGACY COMPATIBILITY ============
  
  // Legacy migration endpoints (for backward compatibility)
  getMigrationJobs: (limit = 20) => {
    return API.get(`/migration/jobs?limit=${limit}`);
  },
  
  getMigrationJobStatus: (jobId) => {
    return API.get(`/migration/status/${jobId}`);
  },
  
  // Legacy provision endpoints
  getProvisionCount: () => {
    return API.get('/provision/count');
  },
  
  searchSubscriber: (identifier) => {
    return API.get(`/provision/search?identifier=${encodeURIComponent(identifier)}`);
  },
  
  createSubscriber: (subscriberData) => {
    return API.post('/provision/subscriber', subscriberData);
  },
  
  // ============ UTILITY METHODS ============
  
  // Upload file to S3 with progress
  uploadFileToS3: async (file, uploadUrl, onProgress = null) => {
    try {
      console.log(`[S3 Upload] Starting upload: ${file.name} (${file.size} bytes)`);
      
      const config = {
        headers: { 'Content-Type': 'text/csv' },
        ...(onProgress && {
          onUploadProgress: (progressEvent) => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(percentCompleted);
          }
        })
      };
      
      const response = await axios.put(uploadUrl, file, config);
      
      console.log(`[S3 Upload] ✅ Upload completed: ${response.status}`);
      return response;
    } catch (error) {
      console.error('[S3 Upload] ❌ Upload failed:', error);
      throw error;
    }
  },
  
  // Test API connectivity
  testConnection: async () => {
    try {
      const response = await API.get('/health');
      return {
        success: true,
        status: response.data.status,
        backend: response.data.backend || 'standard',
        features: response.data.features || []
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        status: 'disconnected'
      };
    }
  },
  
  // Bulk status check for multiple jobs
  getBulkJobStatus: async (jobIds = []) => {
    try {
      const statusPromises = jobIds.map(id => 
        EnhancedAPI.getJobStatus(id).catch(err => ({
          JobId: id,
          status: 'ERROR',
          error: err.message
        }))
      );
      
      const results = await Promise.all(statusPromises);
      return results.map(result => result.data || result);
    } catch (error) {
      console.error('[Bulk Status] Error:', error);
      return [];
    }
  }
};

// Export both the basic axios instance and enhanced API
export default API;
export { EnhancedAPI, API_BASE_URL };

// Export specific method groups for organized imports
export const JobAPI = {
  getJobs: EnhancedAPI.getJobs,
  getJobStatus: EnhancedAPI.getJobStatus,
  cancelJob: EnhancedAPI.cancelJob,
  copyJob: EnhancedAPI.copyJob,
  getJobReport: EnhancedAPI.getJobReport,
  getBulkJobStatus: EnhancedAPI.getBulkJobStatus
};

export const OperationsAPI = {
  createMigrationJob: EnhancedAPI.createMigrationJob,
  createDeletionJob: EnhancedAPI.createDeletionJob,
  createAuditJob: EnhancedAPI.createAuditJob,
  createDataExportJob: EnhancedAPI.createDataExportJob,
  uploadFileToS3: EnhancedAPI.uploadFileToS3
};

export const ProvisionAPI = {
  createProvisionRequest: EnhancedAPI.createProvisionRequest,
  getProvisionDashboard: EnhancedAPI.getProvisionDashboard,
  getProvisionHistory: EnhancedAPI.getProvisionHistory,
  getProvisionCount: EnhancedAPI.getProvisionCount,
  searchSubscriber: EnhancedAPI.searchSubscriber,
  createSubscriber: EnhancedAPI.createSubscriber
};

export const MonitoringAPI = {
  getMonitoringDashboard: EnhancedAPI.getMonitoringDashboard,
  getSystemHealth: EnhancedAPI.getSystemHealth,
  testConnection: EnhancedAPI.testConnection
};

// Enhanced error handling utilities
export const APIUtils = {
  handleError: (error, defaultMessage = 'An error occurred') => {
    if (error.response?.data?.error) {
      return error.response.data.error;
    }
    if (error.response?.data?.message) {
      return error.response.data.message;
    }
    if (error.message) {
      return error.message;
    }
    return defaultMessage;
  },
  
  isNetworkError: (error) => {
    return !error.response && error.code === 'NETWORK_ERROR';
  },
  
  isAuthError: (error) => {
    return error.response?.status === 401 || error.response?.status === 403;
  },
  
  isServerError: (error) => {
    return error.response?.status >= 500;
  },
  
  formatJobId: (jobId) => {
    if (!jobId || typeof jobId !== 'string') return 'unknown';
    return jobId.substring(0, 8) + '...';
  },
  
  formatTimestamp: (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      return new Date(timestamp).toLocaleString();
    } catch (error) {
      return timestamp;
    }
  },
  
  formatDuration: (startTime, endTime) => {
    if (!startTime) return 'N/A';
    
    const start = new Date(startTime);
    const end = endTime ? new Date(endTime) : new Date();
    const diffMs = end - start;
    
    if (diffMs < 60000) {
      return `${Math.floor(diffMs / 1000)}s`;
    } else if (diffMs < 3600000) {
      return `${Math.floor(diffMs / 60000)}m ${Math.floor((diffMs % 60000) / 1000)}s`;
    } else {
      const hours = Math.floor(diffMs / 3600000);
      const minutes = Math.floor((diffMs % 3600000) / 60000);
      return `${hours}h ${minutes}m`;
    }
  }
};

// Job status polling utility
export class JobStatusPoller {
  constructor(jobIds = [], onUpdate = null, options = {}) {
    this.jobIds = Array.isArray(jobIds) ? jobIds : [jobIds];
    this.onUpdate = onUpdate;
    this.options = {
      interval: 5000, // 5 seconds
      maxAttempts: 240, // 20 minutes total
      maxConsecutiveErrors: 3,
      ...options
    };
    
    this.isPolling = false;
    this.pollCount = 0;
    this.consecutiveErrors = 0;
    this.intervalId = null;
  }
  
  start() {
    if (this.isPolling || this.jobIds.length === 0) return;
    
    this.isPolling = true;
    this.pollCount = 0;
    this.consecutiveErrors = 0;
    
    console.log(`[Polling] Starting enhanced polling for ${this.jobIds.length} jobs`);
    
    this.intervalId = setInterval(() => this.poll(), this.options.interval);
    this.poll(); // Initial poll
  }
  
  stop() {
    if (!this.isPolling) return;
    
    this.isPolling = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    
    console.log(`[Polling] Stopped polling for ${this.jobIds.length} jobs`);
  }
  
  async poll() {
    this.pollCount++;
    
    if (this.pollCount > this.options.maxAttempts) {
      console.warn(`[Polling] Maximum attempts reached (${this.options.maxAttempts}), stopping`);
      this.stop();
      return;
    }
    
    try {
      const statuses = await EnhancedAPI.getBulkJobStatus(this.jobIds);
      
      // Reset error counter on success
      this.consecutiveErrors = 0;
      
      // Filter out completed/failed/canceled jobs
      const activeJobs = statuses.filter(job => 
        job.status && ['PENDING_UPLOAD', 'IN_PROGRESS'].includes(job.status)
      );
      
      // Update job IDs to only poll active jobs
      this.jobIds = activeJobs.map(job => job.JobId).filter(id => id);
      
      // Stop polling if no active jobs
      if (this.jobIds.length === 0) {
        console.log('[Polling] No active jobs remaining, stopping');
        this.stop();
        return;
      }
      
      // Call update callback
      if (this.onUpdate && typeof this.onUpdate === 'function') {
        this.onUpdate(statuses);
      }
      
    } catch (error) {
      this.consecutiveErrors++;
      console.error(`[Polling] Error #${this.consecutiveErrors}:`, error.message);
      
      // Stop polling on too many consecutive errors
      if (this.consecutiveErrors >= this.options.maxConsecutiveErrors) {
        console.error('[Polling] Too many consecutive errors, stopping');
        this.stop();
        
        if (this.onUpdate) {
          this.onUpdate([]);
        }
      }
    }
  }
  
  updateJobIds(newJobIds) {
    this.jobIds = Array.isArray(newJobIds) ? newJobIds : [newJobIds];
    console.log(`[Polling] Updated job IDs: ${this.jobIds.length} jobs`);
  }
}

// Export utility functions
export { 
  EnhancedAPI,
  APIUtils,
  JobStatusPoller
};