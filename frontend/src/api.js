import axios from 'axios';

const baseURL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';
console.log('[API] Base URL configured as:', baseURL);

const API = axios.create({
  baseURL,
  timeout: 30000, // 30 seconds for file uploads
});

// Enhanced authentication manager
class AuthManager {
  static getToken() {
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.warn('[Auth] No token found in localStorage');
        return null;
      }
      
      // Validate JWT structure
      const parts = token.split('.');
      if (parts.length !== 3) {
        console.error('[Auth] Invalid JWT format - expecting 3 parts, got:', parts.length);
        this.clearToken();
        return null;
      }
      
      // Decode and check expiration
      const payload = JSON.parse(atob(parts[1]));
      const currentTime = Math.floor(Date.now() / 1000);
      const bufferTime = 60; // 60 seconds buffer
      
      if (payload.exp && (payload.exp - bufferTime) <= currentTime) {
        console.warn('[Auth] Token expired or expiring soon');
        this.clearToken();
        return null;
      }
      
      console.log('[Auth] Valid token found, expires at:', new Date(payload.exp * 1000).toISOString());
      return token;
      
    } catch (error) {
      console.error('[Auth] Token validation error:', error);
      this.clearToken();
      return null;
    }
  }
  
  static clearToken() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    console.log('[Auth] Cleared all authentication data');
  }
  
  static isAuthenticated() {
    return this.getToken() !== null;
  }
}

// Request interceptor - adds authentication header
API.interceptors.request.use(
  config => {
    const token = AuthManager.getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    } else {
      console.warn('[API Request] No valid token available for request:', config.url);
    }
    
    console.log(`[API Request] ${config.method?.toUpperCase()} → ${config.url}`);
    return config;
  },
  error => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

// Response interceptor - handles authentication errors
API.interceptors.response.use(
  response => {
    console.log(`[API Success] ✅ ${response.config.method?.toUpperCase()} ${response.config.url} - ${response.status}`);
    return response;
  },
  async error => {
    const originalRequest = error.config;
    const errorStatus = error.response?.status;
    const errorMessage = error.response?.data?.msg || error.message;
    
    console.error(`[API Error] ❌ ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url} - ${errorStatus}: ${errorMessage}`);
    
    // Handle timeout
    if (error.code === 'ECONNABORTED') {
      console.warn('[API] Request timeout - consider increasing timeout or checking network');
      return Promise.reject(new Error('Request timeout. Please check your connection and try again.'));
    }
    
    // Handle 401 Unauthorized
    if (errorStatus === 401) {
      console.warn('[API] 401 Unauthorized - clearing auth data and redirecting');
      AuthManager.clearToken();
      
      // Redirect to login if we're in browser environment
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        alert('Your session has expired. Please log in again.');
        window.location.href = '/login';
      }
      
      return Promise.reject(new Error('Authentication required. Redirecting to login...'));
    }
    
    // Handle 403 Forbidden
    if (errorStatus === 403) {
      return Promise.reject(new Error('You do not have permission to perform this action.'));
    }
    
    // Handle 404 Not Found
    if (errorStatus === 404) {
      return Promise.reject(new Error(errorMessage || 'Resource not found.'));
    }
    
    // Handle 500 Internal Server Error
    if (errorStatus === 500) {
      return Promise.reject(new Error('Server error. Please try again later or contact support.'));
    }
    
    return Promise.reject(error);
  }
);

export default API;
export { AuthManager };
