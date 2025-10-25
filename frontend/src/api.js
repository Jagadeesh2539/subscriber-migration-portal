// Single Source of Truth API Configuration
import axios from 'axios';

// Consolidated API Base URL - standardized on REACT_APP_API_BASE_URL
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'https://hsebznxeu6.execute-api.us-east-1.amazonaws.com/prod';

// Create axios instance with consistent configuration
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token management
let authToken = null;

// Request interceptor to add auth token
api.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`;
  }
  return config;
});

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    if (error.response?.status === 401) {
      authToken = null;
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// API Methods - Consolidated from all api_*.js files
const apiService = {
  // Authentication
  async login(credentials) {
    const response = await api.post('/api/auth/login', credentials);
    if (response.data.token) {
      authToken = response.data.token;
      localStorage.setItem('authToken', authToken);
    }
    return response.data;
  },

  async logout() {
    authToken = null;
    localStorage.removeItem('authToken');
    return api.post('/api/auth/logout');
  },

  // System Health
  async getHealth() {
    return api.get('/api/health');
  },

  async getDashboardStats() {
    return api.get('/api/dashboard/stats');
  },

  // Subscriber Management - All Modes (Legacy/Cloud/Dual)
  async getSubscribers(params = {}) {
    const queryParams = new URLSearchParams(params).toString();
    return api.get(`/api/subscribers${queryParams ? `?${queryParams}` : ''}`);
  },

  async createSubscriber(subscriberData) {
    return api.post('/api/subscribers', subscriberData);
  },

  async updateSubscriber(id, subscriberData) {
    return api.put(`/api/subscribers/${id}`, subscriberData);
  },

  async deleteSubscriber(id, mode = 'cloud') {
    return api.delete(`/api/subscribers/${id}?mode=${mode}`);
  },

  // Migration Jobs - Enhanced with Timestamps & Cancel
  async getMigrationJobs(params = {}) {
    const queryParams = new URLSearchParams(params).toString();
    return api.get(`/api/migration/jobs${queryParams ? `?${queryParams}` : ''}`);
  },

  async createMigrationJob(jobData) {
    return api.post('/api/migration/jobs', jobData);
  },

  async cancelMigrationJob(jobId) {
    return api.post(`/api/migration/jobs/${jobId}/cancel`);
  },

  async pauseMigrationJob(jobId) {
    return api.post(`/api/migration/jobs/${jobId}/pause`);
  },

  async resumeMigrationJob(jobId) {
    return api.post(`/api/migration/jobs/${jobId}/resume`);
  },

  async getMigrationJobStatus(jobId) {
    return api.get(`/api/migration/jobs/${jobId}/status`);
  },

  // File Upload for Migration
  async uploadMigrationFile(file, metadata = {}) {
    const formData = new FormData();
    formData.append('file', file);
    Object.keys(metadata).forEach(key => {
      formData.append(key, metadata[key]);
    });
    
    return api.post('/api/migration/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 120000, // 2 minutes for file upload
    });
  },

  // Bulk Operations - Enhanced
  async bulkDelete(criteria) {
    return api.post('/api/subscribers/bulk-delete', criteria);
  },

  async bulkAudit(systems = ['legacy', 'cloud']) {
    return api.post('/api/audit/compare', { systems });
  },

  async exportData(system = 'cloud', format = 'csv') {
    return api.get(`/api/export/${system}?format=${format}`, {
      responseType: 'blob',
    });
  },

  // Legacy Database Operations
  async testLegacyConnection() {
    return api.get('/api/legacy/test');
  },

  async getLegacyStats() {
    return api.get('/api/legacy/stats');
  },

  async migrateLegacyToCloud(criteria = {}) {
    return api.post('/api/migration/legacy-to-cloud', criteria);
  },

  // Provisioning Mode Management
  async setProvisioningMode(mode) {
    return api.post('/api/config/provisioning-mode', { mode });
  },

  async getProvisioningMode() {
    return api.get('/api/config/provisioning-mode');
  },

  // Analytics & Reporting
  async getAnalyticsData(timeRange = '30d') {
    return api.get(`/api/analytics?range=${timeRange}`);
  },

  async getSystemMetrics() {
    return api.get('/api/metrics/system');
  },

  async getMigrationProgress() {
    return api.get('/api/metrics/migration');
  },

  // Audit Logs
  async getAuditLogs(params = {}) {
    const queryParams = new URLSearchParams(params).toString();
    return api.get(`/api/audit/logs${queryParams ? `?${queryParams}` : ''}`);
  },

  // Utility Methods
  setAuthToken(token) {
    authToken = token;
    if (token) {
      localStorage.setItem('authToken', token);
    } else {
      localStorage.removeItem('authToken');
    }
  },

  getAuthToken() {
    if (!authToken) {
      authToken = localStorage.getItem('authToken');
    }
    return authToken;
  },

  isAuthenticated() {
    return !!this.getAuthToken();
  },

  // Initialize token on app startup
  init() {
    const token = localStorage.getItem('authToken');
    if (token) {
      this.setAuthToken(token);
    }
  }
};

// Initialize API service
apiService.init();

export default apiService;
export { API_BASE_URL };

// Backward compatibility exports for existing components
export const {
  login,
  logout,
  getHealth,
  getDashboardStats,
  getSubscribers,
  createSubscriber,
  updateSubscriber,
  deleteSubscriber,
  getMigrationJobs,
  createMigrationJob,
  cancelMigrationJob,
  uploadMigrationFile,
  bulkDelete,
  bulkAudit,
  exportData,
  testLegacyConnection,
  getLegacyStats,
  getAnalyticsData,
  getAuditLogs
} = apiService;

// Legacy export for compatibility with AuthManager
export const AuthManager = {
  getToken: () => apiService.getAuthToken(),
  clearToken: () => apiService.setAuthToken(null),
  isAuthenticated: () => apiService.isAuthenticated()
};
