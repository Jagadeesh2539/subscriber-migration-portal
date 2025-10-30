import axios from 'axios';
import { toast } from 'react-hot-toast';

// Enhanced API Configuration
const API_CONFIG = {
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:5000/api',
  timeout: 30000, // 30 seconds
  retryAttempts: 3,
  retryDelay: 1000,
};

// Create axios instance with enhanced configuration
const apiClient = axios.create({
  baseURL: API_CONFIG.baseURL,
  timeout: API_CONFIG.timeout,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

// Request interceptor for authentication and logging
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Log API calls in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`🚀 API Request: ${config.method?.toUpperCase()} ${config.url}`, {
        data: config.data,
        params: config.params,
      });
    }
    
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling and token refresh
apiClient.interceptors.response.use(
  (response) => {
    // Log successful responses in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`✅ API Response: ${response.status}`, response.data);
    }
    
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    
    // Handle 401 Unauthorized - Token expired or invalid
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      // Clear auth data and redirect to login
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      
      toast.error('Your session has expired. Please log in again.');
      window.location.href = '/login';
      
      return Promise.reject(error);
    }
    
    // Handle 403 Forbidden
    if (error.response?.status === 403) {
      toast.error('Access denied. You don\'t have permission for this action.');
    }
    
    // Handle 429 Too Many Requests
    if (error.response?.status === 429) {
      toast.error('Too many requests. Please wait before trying again.');
    }
    
    // Handle 500+ Server Errors
    if (error.response?.status >= 500) {
      toast.error('Server error. Our team has been notified.');
    }
    
    // Handle network errors
    if (!error.response) {
      toast.error('Network error. Please check your connection.');
    }
    
    // Log error details in development
    if (process.env.NODE_ENV === 'development') {
      console.error('❌ API Error:', {
        status: error.response?.status,
        message: error.message,
        data: error.response?.data,
        config: error.config,
      });
    }
    
    return Promise.reject(error);
  }
);

// Enhanced API service functions with better error handling
export const apiService = {
  // Authentication
  auth: {
    login: (credentials) => apiClient.post('/auth/login', credentials),
    logout: () => apiClient.post('/auth/logout'),
    refreshToken: () => apiClient.post('/auth/refresh'),
    validateToken: () => apiClient.get('/auth/validate'),
  },
  
  // Dashboard and Statistics
  dashboard: {
    getStats: () => apiClient.get('/dashboard/stats'),
    getSystemHealth: () => apiClient.get('/dashboard/health'),
    getRecentActivity: (limit = 10) => apiClient.get(`/dashboard/activity?limit=${limit}`),
  },
  
  // Subscriber Management
  subscribers: {
    getAll: (params = {}) => apiClient.get('/subscribers', { params }),
    getById: (id) => apiClient.get(`/subscribers/${id}`),
    create: (data) => apiClient.post('/subscribers', data),
    update: (id, data) => apiClient.put(`/subscribers/${id}`, data),
    delete: (id) => apiClient.delete(`/subscribers/${id}`),
    search: (query, filters = {}) => apiClient.get('/subscribers/search', {
      params: { q: query, ...filters }
    }),
    bulkUpdate: (data) => apiClient.post('/subscribers/bulk-update', data),
    export: (format = 'csv', filters = {}) => apiClient.get('/subscribers/export', {
      params: { format, ...filters },
      responseType: 'blob',
    }),
  },
  
  // Migration Operations
  migration: {
    getJobs: (params = {}) => apiClient.get('/migration/jobs', { params }),
    getJobById: (id) => apiClient.get(`/migration/jobs/${id}`),
    createJob: (data) => apiClient.post('/migration/jobs', data),
    updateJob: (id, data) => apiClient.put(`/migration/jobs/${id}`, data),
    cancelJob: (id) => apiClient.post(`/migration/jobs/${id}/cancel`),
    retryJob: (id) => apiClient.post(`/migration/jobs/${id}/retry`),
    uploadFile: (file, onProgress) => {
      const formData = new FormData();
      formData.append('file', file);
      
      return apiClient.post('/migration/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: onProgress,
      });
    },
  },
  
  // Analytics and Reporting
  analytics: {
    getMetrics: (timeRange = '7d') => apiClient.get(`/analytics/metrics?range=${timeRange}`),
    getPerformanceData: (params = {}) => apiClient.get('/analytics/performance', { params }),
    getUsageStats: (params = {}) => apiClient.get('/analytics/usage', { params }),
    generateReport: (type, params = {}) => apiClient.post('/analytics/reports', {
      type,
      ...params
    }),
  },
  
  // System Monitoring
  monitoring: {
    getSystemStatus: () => apiClient.get('/monitoring/status'),
    getAlerts: (params = {}) => apiClient.get('/monitoring/alerts', { params }),
    acknowledgeAlert: (id) => apiClient.post(`/monitoring/alerts/${id}/acknowledge`),
    getMetrics: (metric, timeRange = '1h') => apiClient.get('/monitoring/metrics', {
      params: { metric, range: timeRange }
    }),
  },
  
  // User Management
  users: {
    getAll: (params = {}) => apiClient.get('/users', { params }),
    getById: (id) => apiClient.get(`/users/${id}`),
    create: (data) => apiClient.post('/users', data),
    update: (id, data) => apiClient.put(`/users/${id}`, data),
    delete: (id) => apiClient.delete(`/users/${id}`),
    updateProfile: (data) => apiClient.put('/users/profile', data),
    changePassword: (data) => apiClient.post('/users/change-password', data),
  },
  
  // System Settings
  settings: {
    getAll: () => apiClient.get('/settings'),
    update: (data) => apiClient.put('/settings', data),
    getProvisioningMode: () => apiClient.get('/settings/provisioning-mode'),
    setProvisioningMode: (mode) => apiClient.put('/settings/provisioning-mode', { mode }),
  },
  
  // Audit Logs
  audit: {
    getLogs: (params = {}) => apiClient.get('/audit/logs', { params }),
    getLogById: (id) => apiClient.get(`/audit/logs/${id}`),
    export: (filters = {}) => apiClient.get('/audit/export', {
      params: filters,
      responseType: 'blob',
    }),
  },
};

// Utility functions for handling API responses
export const apiUtils = {
  // Extract error message from API response
  getErrorMessage: (error) => {
    if (error.response?.data?.message) {
      return error.response.data.message;
    }
    if (error.response?.data?.error) {
      return error.response.data.error;
    }
    if (error.message) {
      return error.message;
    }
    return 'An unexpected error occurred';
  },
  
  // Check if error is due to network issues
  isNetworkError: (error) => {
    return !error.response && error.code === 'NETWORK_ERROR';
  },
  
  // Check if error is due to authentication issues
  isAuthError: (error) => {
    return error.response?.status === 401;
  },
  
  // Check if error is due to permission issues
  isPermissionError: (error) => {
    return error.response?.status === 403;
  },
  
  // Format file size for display
  formatFileSize: (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  },
  
  // Download file from blob response
  downloadFile: (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};

// React Query configuration
export const queryConfig = {
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
      retry: (failureCount, error) => {
        // Don't retry on 4xx errors (client errors)
        if (error.response?.status >= 400 && error.response?.status < 500) {
          return false;
        }
        // Retry up to 3 times for other errors
        return failureCount < 3;
      },
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: {
      retry: 1,
      onError: (error) => {
        const message = apiUtils.getErrorMessage(error);
        toast.error(message);
      },
    },
  },
};

export default apiClient;