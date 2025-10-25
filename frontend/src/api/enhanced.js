const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5000/api';

class EnhancedAPI {
  constructor() {
    this.baseURL = API_BASE_URL;
  }

  // Helper method to make HTTP requests
  async makeRequest(endpoint, options = {}) {
    const token = localStorage.getItem('authToken');
    const url = `${this.baseURL}${endpoint}`;
    
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers
      },
      ...options
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('authToken');
          window.location.href = '/login';
          throw new Error('Unauthorized');
        }
        
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.message || `HTTP ${response.status}`);
      }

      // Handle different content types
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await response.json();
      } else if (contentType && (contentType.includes('text/csv') || contentType.includes('application/pdf'))) {
        return await response.text();
      } else {
        return await response.text();
      }
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  // Authentication
  async login(credentials) {
    return await this.makeRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials)
    });
  }

  async logout() {
    return await this.makeRequest('/auth/logout', { method: 'POST' });
  }

  async getCurrentUser() {
    return await this.makeRequest('/auth/me');
  }

  // Dashboard and Global Stats
  async getGlobalStats() {
    return await this.makeRequest('/dashboard/stats');
  }

  async getDashboardOverview() {
    return await this.makeRequest('/dashboard/overview');
  }

  async getRecentActivity() {
    return await this.makeRequest('/dashboard/activity');
  }

  async getMigrationTrends(timeRange = '30d') {
    return await this.makeRequest(`/dashboard/trends?range=${timeRange}`);
  }

  async getSystemStatistics() {
    return await this.makeRequest('/dashboard/system-stats');
  }

  async getSystemAlerts() {
    return await this.makeRequest('/monitoring/alerts');
  }

  // Subscriber Management (Provisioning)
  async getSubscribers(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return await this.makeRequest(`/subscribers?${queryString}`);
  }

  async getSubscriber(subscriberId) {
    return await this.makeRequest(`/subscribers/${subscriberId}`);
  }

  async createSubscriber(subscriberData) {
    return await this.makeRequest('/subscribers', {
      method: 'POST',
      body: JSON.stringify(subscriberData)
    });
  }

  async updateSubscriber(subscriberId, subscriberData) {
    return await this.makeRequest(`/subscribers/${subscriberId}`, {
      method: 'PUT',
      body: JSON.stringify(subscriberData)
    });
  }

  async deleteSubscriber(subscriberId, options = {}) {
    return await this.makeRequest(`/subscribers/${subscriberId}`, {
      method: 'DELETE',
      body: JSON.stringify(options)
    });
  }

  async exportSubscribers(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return await this.makeRequest(`/subscribers/export?${queryString}`);
  }

  // Migration Management
  async getMigrationJobs(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return await this.makeRequest(`/migration/jobs?${queryString}`);
  }

  async getMigrationJob(jobId) {
    return await this.makeRequest(`/migration/jobs/${jobId}`);
  }

  async getMigrationJobDetails(jobId) {
    return await this.makeRequest(`/migration/jobs/${jobId}/details`);
  }

  async submitMigrationJob(formData) {
    return await this.makeRequest('/migration/jobs', {
      method: 'POST',
      body: formData,
      headers: {} // Remove Content-Type to let browser set it for FormData
    });
  }

  async controlMigrationJob(jobId, action) {
    return await this.makeRequest(`/migration/jobs/${jobId}/${action}`, {
      method: 'POST'
    });
  }

  async getMigrationStats() {
    return await this.makeRequest('/migration/stats');
  }

  async getMigrationMonitoring() {
    return await this.makeRequest('/migration/monitoring');
  }

  // Bulk Operations
  async getBulkOperations(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return await this.makeRequest(`/bulk/operations?${queryString}`);
  }

  async getBulkOperationDetails(operationId) {
    return await this.makeRequest(`/bulk/operations/${operationId}/details`);
  }

  async submitBulkOperation(formData) {
    return await this.makeRequest('/bulk/operations', {
      method: 'POST',
      body: formData,
      headers: {}
    });
  }

  async submitBulkAudit(config) {
    return await this.makeRequest('/bulk/audit', {
      method: 'POST',
      body: JSON.stringify(config)
    });
  }

  async getOperationProgress(operationId) {
    return await this.makeRequest(`/bulk/operations/${operationId}/progress`);
  }

  async getAuditResults(operationId) {
    return await this.makeRequest(`/bulk/operations/${operationId}/audit-results`);
  }

  async downloadOperationResults(operationId) {
    return await this.makeRequest(`/bulk/operations/${operationId}/download`);
  }

  // Data Query and Export
  async querySubscribers(params = {}) {
    return await this.makeRequest('/data/query', {
      method: 'POST',
      body: JSON.stringify(params)
    });
  }

  async getSystemStats() {
    return await this.makeRequest('/data/system-stats');
  }

  async exportSubscriberData(params = {}) {
    return await this.makeRequest('/data/export', {
      method: 'POST',
      body: JSON.stringify(params)
    });
  }

  // Monitoring
  async getPerformanceMetrics(timeRange = '24h') {
    return await this.makeRequest(`/monitoring/performance?range=${timeRange}`);
  }

  async getResourceUtilization() {
    return await this.makeRequest('/monitoring/resources');
  }

  async getServiceStatus() {
    return await this.makeRequest('/monitoring/services');
  }

  // Analytics
  async getAnalyticsOverview(timeRange = '30d') {
    return await this.makeRequest(`/analytics/overview?range=${timeRange}`);
  }

  async getSystemPerformanceAnalytics(timeRange = '30d') {
    return await this.makeRequest(`/analytics/performance?range=${timeRange}`);
  }

  async getErrorAnalysis(timeRange = '30d') {
    return await this.makeRequest(`/analytics/errors?range=${timeRange}`);
  }

  async getRegionDistribution(timeRange = '30d') {
    return await this.makeRequest(`/analytics/regions?range=${timeRange}`);
  }

  async getPlanDistribution(timeRange = '30d') {
    return await this.makeRequest(`/analytics/plans?range=${timeRange}`);
  }

  async getTimeBasedAnalytics(timeRange = '30d') {
    return await this.makeRequest(`/analytics/time-based?range=${timeRange}`);
  }

  async getTopErrors(timeRange = '30d') {
    return await this.makeRequest(`/analytics/top-errors?range=${timeRange}`);
  }

  async getAnalyticsRecommendations(timeRange = '30d') {
    return await this.makeRequest(`/analytics/recommendations?range=${timeRange}`);
  }

  async exportAnalyticsReport(params = {}) {
    return await this.makeRequest('/analytics/export', {
      method: 'POST',
      body: JSON.stringify(params)
    });
  }

  // Mock data methods for development/demo
  generateMockTrends(days = 30) {
    const trends = [];
    for (let i = days; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      trends.push({
        date: date.toISOString().split('T')[0],
        migrations: Math.floor(Math.random() * 100) + 50,
        successful: Math.floor(Math.random() * 95) + 85,
        failed: Math.floor(Math.random() * 10) + 2
      });
    }
    return trends;
  }

  generateMockPerformance(hours = 24) {
    const performance = [];
    for (let i = hours; i >= 0; i--) {
      const timestamp = new Date();
      timestamp.setHours(timestamp.getHours() - i);
      performance.push({
        timestamp: timestamp.toISOString(),
        cpu: Math.floor(Math.random() * 60) + 20,
        memory: Math.floor(Math.random() * 70) + 30,
        network: Math.floor(Math.random() * 40) + 10,
        response_time: Math.floor(Math.random() * 500) + 100,
        throughput: Math.floor(Math.random() * 1000) + 200
      });
    }
    return performance;
  }

  generateMockActivity(count = 10) {
    const activities = [];
    const types = ['migration', 'provisioning', 'audit', 'system'];
    const statuses = ['completed', 'running', 'failed'];
    
    for (let i = 0; i < count; i++) {
      const timestamp = new Date();
      timestamp.setMinutes(timestamp.getMinutes() - (i * 15));
      
      activities.push({
        type: types[Math.floor(Math.random() * types.length)],
        title: `Migration Job #${1000 + i}`,
        description: `Processed ${Math.floor(Math.random() * 1000) + 100} records`,
        status: statuses[Math.floor(Math.random() * statuses.length)],
        timestamp: timestamp.toISOString()
      });
    }
    return activities;
  }

  // Development/Demo mode fallbacks
  async makeRequestWithFallback(endpoint, options = {}, mockData = null) {
    try {
      return await this.makeRequest(endpoint, options);
    } catch (error) {
      console.warn(`API call failed for ${endpoint}, using mock data:`, error.message);
      
      // Return mock data or generate it based on endpoint
      if (mockData) {
        return mockData;
      }
      
      // Generate mock data based on endpoint pattern
      if (endpoint.includes('/trends')) {
        return this.generateMockTrends();
      } else if (endpoint.includes('/performance')) {
        return this.generateMockPerformance();
      } else if (endpoint.includes('/activity')) {
        return this.generateMockActivity();
      } else if (endpoint.includes('/stats')) {
        return {
          totalSubscribers: 125430,
          migrationJobs: 234,
          provisioningOperations: 1567,
          systemHealth: 98
        };
      }
      
      // Default empty response
      return {};
    }
  }

  // Override methods to include fallbacks in development
  async getDashboardOverviewWithFallback() {
    return await this.makeRequestWithFallback('/dashboard/overview', {}, {
      totalSubscribers: 125430,
      activeMigrations: 5,
      completedMigrations: 12,
      systemHealth: 98
    });
  }

  async getMigrationTrendsWithFallback(timeRange = '30d') {
    return await this.makeRequestWithFallback(`/dashboard/trends?range=${timeRange}`, {}, 
      this.generateMockTrends(timeRange === '7d' ? 7 : 30)
    );
  }

  async getRecentActivityWithFallback() {
    return await this.makeRequestWithFallback('/dashboard/activity', {}, 
      this.generateMockActivity()
    );
  }
}

export const api = new EnhancedAPI();
export default api;