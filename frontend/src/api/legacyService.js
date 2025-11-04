import { apiClient } from './apiClient';

/**
 * Legacy Subscribers Service - RDS MySQL Operations
 * Handles CRUD operations for subscribers in the Legacy (RDS MySQL) system
 */
export const legacyService = {
  /**
   * Get paginated list of legacy subscribers with filtering
   * @param {Object} params - Query parameters
   * @param {string} [params.status] - Filter by status (ACTIVE, INACTIVE, SUSPENDED, DELETED)
   * @param {string} [params.planId] - Filter by plan ID
   * @param {string} [params.search] - Search term (uses MySQL LIKE queries)
   * @param {number} [params.page] - Page number (0-based)
   * @param {number} [params.limit] - Items per page (max 100)
   * @param {number} [params.offset] - MySQL offset for pagination
   * @returns {Promise<{data: {subscribers: Array, pagination: Object}}>}
   */
  async getSubscribers(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.status) queryParams.append('status', params.status);
    if (params.planId) queryParams.append('planId', params.planId);
    if (params.search) queryParams.append('search', params.search);
    if (params.limit) queryParams.append('limit', params.limit.toString());
    
    // Convert page to offset for MySQL
    const offset = (params.page || 0) * (params.limit || 25);
    if (offset > 0) queryParams.append('offset', offset.toString());
    
    const url = `/legacy/subscribers${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    
    try {
      const response = await apiClient.get(url);
      
      // Transform response for frontend compatibility
      const pagination = response.data?.pagination || {};
      
      return {
        data: {
          subscribers: response.data?.subscribers || [],
          pagination: {
            count: pagination.count || 0,
            total: pagination.total || 0,
            hasMore: pagination.hasMore || false,
            offset: pagination.offset || 0,
            nextOffset: pagination.nextOffset,
            page: Math.floor((pagination.offset || 0) / (params.limit || 25)),
            limit: pagination.limit || 25
          },
          filters: response.data?.filters || {},
          source: 'legacy',
          performance: {
            warning: pagination.total > 1000 ? 'Large dataset - consider using filters' : null
          }
        }
      };
    } catch (error) {
      console.error('Failed to fetch legacy subscribers:', error);
      
      // Handle specific RDS/MySQL errors
      if (error.response?.status === 503) {
        throw new Error('Legacy database is unavailable - check RDS connectivity');
      }
      if (error.response?.status === 408 || error.message?.includes('timeout')) {
        throw new Error('Legacy database query timed out - try using more specific filters');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to fetch legacy subscribers'
      );
    }
  },

  /**
   * Get a specific legacy subscriber by UID
   * @param {string} uid - Subscriber unique identifier
   * @returns {Promise<{data: {subscriber: Object}}>}
   */
  async getSubscriber(uid) {
    try {
      const response = await apiClient.get(`/legacy/subscribers/${encodeURIComponent(uid)}`);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          source: 'legacy',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to fetch legacy subscriber ${uid}:`, error);
      
      if (error.response?.status === 503) {
        throw new Error('Legacy database is unavailable');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to fetch legacy subscriber ${uid}`
      );
    }
  },

  /**
   * Create a new subscriber in Legacy (RDS MySQL)
   * @param {Object} subscriberData - Subscriber information (same structure as cloud)
   * @returns {Promise<{data: {subscriber: Object}}>}
   */
  async createSubscriber(subscriberData) {
    try {
      // Client-side validation
      if (!subscriberData.uid?.trim()) {
        throw new Error('UID is required');
      }
      if (!subscriberData.msisdn?.trim()) {
        throw new Error('MSISDN is required');
      }
      if (!subscriberData.imsi?.trim()) {
        throw new Error('IMSI is required');
      }
      
      const response = await apiClient.post('/legacy/subscribers', subscriberData);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          message: response.data?.message,
          source: 'legacy',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to create legacy subscriber:', error);
      
      // Handle MySQL-specific errors
      if (error.response?.status === 409) {
        throw new Error('Subscriber with this UID/MSISDN/IMSI already exists in Legacy');
      }
      if (error.response?.status === 503) {
        throw new Error('Legacy database is unavailable');
      }
      if (error.message?.includes('Duplicate entry')) {
        throw new Error('Duplicate key constraint violation in Legacy database');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to create legacy subscriber'
      );
    }
  },

  /**
   * Update an existing legacy subscriber
   * @param {string} uid - Subscriber UID to update
   * @param {Object} updateData - Fields to update
   * @returns {Promise<{data: {subscriber: Object}}>}
   */
  async updateSubscriber(uid, updateData) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for update');
      }
      
      const response = await apiClient.put(`/legacy/subscribers/${encodeURIComponent(uid)}`, updateData);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          message: response.data?.message,
          source: 'legacy',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to update legacy subscriber ${uid}:`, error);
      
      if (error.response?.status === 404) {
        throw new Error(`Subscriber ${uid} not found in Legacy`);
      }
      if (error.response?.status === 503) {
        throw new Error('Legacy database is unavailable');
      }
      if (error.response?.status === 409) {
        throw new Error('Update would violate unique constraint in Legacy');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to update legacy subscriber ${uid}`
      );
    }
  },

  /**
   * Delete a legacy subscriber
   * @param {string} uid - Subscriber UID to delete
   * @returns {Promise<{data: {message: string}}>}
   */
  async deleteSubscriber(uid) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for deletion');
      }
      
      const response = await apiClient.delete(`/legacy/subscribers/${encodeURIComponent(uid)}`);
      
      return {
        data: {
          message: response.data?.message,
          source: 'legacy',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to delete legacy subscriber ${uid}:`, error);
      
      if (error.response?.status === 404) {
        throw new Error(`Subscriber ${uid} not found in Legacy`);
      }
      if (error.response?.status === 503) {
        throw new Error('Legacy database is unavailable');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to delete legacy subscriber ${uid}`
      );
    }
  },

  /**
   * Get legacy system health and performance metrics
   * @returns {Promise<{data: {healthy: boolean, responseTime: number, recordCount: number}}>}
   */
  async getHealth() {
    try {
      // TODO: Implement /legacy/health endpoint
      const startTime = performance.now();
      const response = await apiClient.get('/legacy/health');
      const responseTime = Math.round(performance.now() - startTime);
      
      return {
        data: {
          healthy: response.data?.healthy ?? true,
          responseTime: response.data?.responseTime ?? responseTime,
          recordCount: response.data?.recordCount ?? 0,
          system: 'legacy',
          connectionPool: response.data?.connectionPool,
          timestamp: new Date().toISOString()
        }
      };
    } catch (error) {
      // Return mock data for now
      return {
        data: {
          healthy: false,
          responseTime: 999,
          recordCount: 0,
          system: 'legacy',
          error: error.message,
          timestamp: new Date().toISOString()
        }
      };
    }
  },

  /**
   * Execute SQL query for advanced legacy operations
   * @param {string} query - SQL query to execute
   * @param {Array} [params] - Query parameters
   * @returns {Promise<{data: {results: Array, rowCount: number}}>}
   */
  async executeQuery(query, params = []) {
    try {
      // TODO: Implement /legacy/query endpoint (admin-only)
      const response = await apiClient.post('/legacy/query', { query, params });
      
      return {
        data: {
          results: response.data?.results || [],
          rowCount: response.data?.rowCount || 0,
          executionTime: response.data?.executionTime,
          source: 'legacy',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to execute legacy query:', error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to execute legacy query'
      );
    }
  }
};