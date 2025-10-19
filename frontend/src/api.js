import axios from 'axios';

// CRITICAL FIX: Base URL is now taken directly from the environment variable.
const baseURL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const API = axios.create({
  baseURL,
  timeout: 15000, // 15 seconds timeout for safety
});

// Add Authorization header if token exists and log request details
API.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Log request method and URL for debugging
  console.log(`[API Request] ${config.method?.toUpperCase()} → ${config.url}`);
  return config;
});

// Global response interceptor for logging success and handling 401/timeouts
API.interceptors.response.use(
  response => {
    // Log successful response
    console.log(`[API Response] ✅ ${response.config.url}`, response.status);
    return response;
  },
  error => {
    // Handle request timeout specifically
    if (error.code === 'ECONNABORTED') {
      console.warn('⏰ Request timeout');
    }
    
    // Handle 401 Unauthorized errors
    if (error.response?.status === 401) {
      // Clear storage to force a re-login state in the main application component (App.js)
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      
      // The App.js router handles the navigation to /login
    }

    // Log general API error details
    console.error(`[API Error] ❌ ${error.config?.url}`, error.message);
    
    return Promise.reject(error);
  }
);

export default API;
