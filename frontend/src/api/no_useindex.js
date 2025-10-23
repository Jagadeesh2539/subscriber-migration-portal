import axios from 'axios';

// CRITICAL FIX: Base URL is now taken directly from the environment variable.
// This assumes REACT_APP_API_URL ends in the API Gateway stage name (e.g., .../prod).
const baseURL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const API = axios.create({
  baseURL: baseURL
});

// Add Authorization header if token exists
API.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Global 401 handler
API.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default API;
