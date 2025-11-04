import { apiClient } from './apiClient';

/**
 * Cloud Subscribers Service - DynamoDB Operations
 * Handles CRUD operations for subscribers in the Cloud (DynamoDB) system
 */
export const cloudService = {
  /**
   * Get paginated list of cloud subscribers with filtering
   * @param {Object} params - Query parameters
   * @param {string} [params.status] - Filter by status (ACTIVE, INACTIVE, SUSPENDED, DELETED)
   * @param {string} [params.planId] - Filter by plan ID
   * @param {string} [params.search] - Search term for UID, MSISDN, IMSI, email, names
   * @param {number} [params.page] - Page number (0-based)
   * @param {number} [params.limit] - Items per page (max 100)
   * @param {string} [params.lastKey] - Pagination cursor for DynamoDB
   * @returns {Promise<{data: {subscribers: Array, pagination: Object}}>}
   */
  async getSubscribers(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.status) queryParams.append('status', params.status);
    if (params.planId) queryParams.append('planId', params.planId);
    if (params.search) queryParams.append('search', params.search);
    if (params.limit) queryParams.append('limit', params.limit.toString());
    if (params.lastKey) queryParams.append('lastKey', params.lastKey);
    
    const url = `/cloud/subscribers${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    
    try {
      const response = await apiClient.get(url);
      
      // Transform response to match frontend expectations
      return {
        data: {
          subscribers: response.data?.subscribers || [],
          pagination: {
            count: response.data?.pagination?.count || 0,
            hasMore: response.data?.pagination?.hasMore || false,
            lastKey: response.data?.pagination?.lastKey,
            total: response.data?.pagination?.total || response.data?.pagination?.count || 0
          },
          filters: response.data?.filters || {},
          source: 'cloud'
        }
      };
    } catch (error) {
      console.error('Failed to fetch cloud subscribers:', error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to fetch cloud subscribers'
      );
    }
  },

  /**
   * Get a specific cloud subscriber by UID
   * @param {string} uid - Subscriber unique identifier
   * @returns {Promise<{data: {subscriber: Object}}>}
   */
  async getSubscriber(uid) {
    try {
      const response = await apiClient.get(`/cloud/subscribers/${encodeURIComponent(uid)}`);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          source: 'cloud',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to fetch cloud subscriber ${uid}:`, error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to fetch subscriber ${uid}`
      );
    }
  },

  /**
   * Create a new subscriber in Cloud (DynamoDB)
   * @param {Object} subscriberData - Subscriber information
   * @param {string} subscriberData.uid - Unique identifier (required)
   * @param {string} subscriberData.msisdn - Mobile number (required)
   * @param {string} subscriberData.imsi - SIM identifier (required) 
   * @param {string} [subscriberData.status='ACTIVE'] - Subscriber status
   * @param {string} [subscriberData.planId] - Service plan ID
   * @param {string} [subscriberData.email] - Email address
   * @param {string} [subscriberData.firstName] - First name
   * @param {string} [subscriberData.lastName] - Last name
   * @param {string} [subscriberData.address] - Physical address
   * @param {string} [subscriberData.dateOfBirth] - Date of birth (YYYY-MM-DD)
   * @returns {Promise<{data: {subscriber: Object}}>}
   */
  async createSubscriber(subscriberData) {
    try {
      // Validate required fields client-side
      if (!subscriberData.uid?.trim()) {
        throw new Error('UID is required');
      }
      if (!subscriberData.msisdn?.trim()) {
        throw new Error('MSISDN is required');
      }
      if (!subscriberData.imsi?.trim()) {
        throw new Error('IMSI is required');
      }
      
      const response = await apiClient.post('/cloud/subscribers', subscriberData);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          message: response.data?.message,
          source: 'cloud',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to create cloud subscriber:', error);
      
      // Handle specific error cases
      if (error.response?.status === 409) {
        throw new Error('Subscriber with this UID already exists in Cloud');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to create cloud subscriber'
      );
    }
  },

  /**
   * Update an existing cloud subscriber
   * @param {string} uid - Subscriber UID to update
   * @param {Object} updateData - Fields to update
   * @returns {Promise<{data: {subscriber: Object}}>}
   */
  async updateSubscriber(uid, updateData) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for update');
      }
      
      const response = await apiClient.put(`/cloud/subscribers/${encodeURIComponent(uid)}`, updateData);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          message: response.data?.message,
          source: 'cloud',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to update cloud subscriber ${uid}:`, error);
      
      if (error.response?.status === 404) {
        throw new Error(`Subscriber ${uid} not found in Cloud`);
      }
      if (error.response?.status === 409) {
        throw new Error('Update would create duplicate MSISDN or IMSI');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to update subscriber ${uid}`
      );
    }
  },

  /**
   * Delete a cloud subscriber
   * @param {string} uid - Subscriber UID to delete
   * @returns {Promise<{data: {message: string}}>}
   */
  async deleteSubscriber(uid) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for deletion');
      }
      
      const response = await apiClient.delete(`/cloud/subscribers/${encodeURIComponent(uid)}`);
      
      return {
        data: {
          message: response.data?.message,
          source: 'cloud',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to delete cloud subscriber ${uid}:`, error);
      
      if (error.response?.status === 404) {
        throw new Error(`Subscriber ${uid} not found in Cloud`);
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to delete subscriber ${uid}`
      );
    }
  },

  /**
   * Get cloud system health and performance metrics
   * @returns {Promise<{data: {healthy: boolean, responseTime: number, recordCount: number}}>}
   */
  async getHealth() {
    try {
      // TODO: Implement /cloud/health endpoint
      const startTime = performance.now();
      const response = await apiClient.get('/cloud/health');
      const responseTime = Math.round(performance.now() - startTime);
      
      return {
        data: {
          healthy: response.data?.healthy ?? true,
          responseTime: response.data?.responseTime ?? responseTime,
          recordCount: response.data?.recordCount ?? 0,
          system: 'cloud',
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
          system: 'cloud',
          error: error.message,
          timestamp: new Date().toISOString()
        }
      };
    }
  },

  /**
   * Bulk operations for cloud subscribers
   * @param {Object} operation - Bulk operation details
   * @param {string} operation.type - Operation type (UPDATE, DELETE, EXPORT)
   * @param {Array<string>} operation.uids - Array of subscriber UIDs
   * @param {Object} [operation.updateData] - Data for bulk update
   * @returns {Promise<{data: {jobId: string, status: string}}>}
   */
  async bulkOperation(operation) {
    try {
      // TODO: Implement bulk operations endpoint
      const response = await apiClient.post('/cloud/subscribers/bulk', operation);
      
      return {
        data: {
          jobId: response.data?.jobId,
          status: response.data?.status,
          affectedCount: response.data?.affectedCount,
          source: 'cloud',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to execute bulk operation:', error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to execute bulk operation'
      );
    }
  }
};