import { apiClient } from './apiClient';

/**
 * Dual Provision Service - Cloud + Legacy Synchronized Operations
 * Handles CRUD operations across both Cloud (DynamoDB) and Legacy (RDS MySQL) systems
 */
export const dualService = {
  /**
   * Get paginated list of dual subscribers with sync status
   * @param {Object} params - Query parameters
   * @param {string} [params.status] - Filter by status
   * @param {string} [params.planId] - Filter by plan ID
   * @param {string} [params.search] - Search term across both systems
   * @param {string} [params.syncStatus] - Filter by sync status (SYNCED, OUT_OF_SYNC, CLOUD_ONLY, LEGACY_ONLY, CONFLICT)
   * @param {number} [params.page] - Page number
   * @param {number} [params.limit] - Items per page
   * @returns {Promise<{data: {subscribers: Array, pagination: Object, syncStats: Object}}>}
   */
  async getSubscribers(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.status) queryParams.append('status', params.status);
    if (params.planId) queryParams.append('planId', params.planId);
    if (params.search) queryParams.append('search', params.search);
    if (params.syncStatus) queryParams.append('syncStatus', params.syncStatus);
    if (params.limit) queryParams.append('limit', params.limit.toString());
    if (params.page) queryParams.append('page', params.page.toString());
    
    const url = `/dual/subscribers${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    
    try {
      const response = await apiClient.get(url);
      
      return {
        data: {
          subscribers: response.data?.subscribers || [],
          pagination: response.data?.pagination || {
            count: 0,
            hasMore: false,
            total: 0
          },
          syncStats: response.data?.syncStats || {
            synced: 0,
            outOfSync: 0,
            cloudOnly: 0,
            legacyOnly: 0,
            conflicts: 0
          },
          filters: response.data?.filters || {},
          source: 'dual',
          performance: {
            warning: 'Dual queries are complex and may be slower than single-system queries'
          }
        }
      };
    } catch (error) {
      console.error('Failed to fetch dual subscribers:', error);
      
      // Handle dual-system specific errors
      if (error.response?.status === 503) {
        throw new Error('One or both systems are unavailable - check Cloud and Legacy connectivity');
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to fetch dual subscribers'
      );
    }
  },

  /**
   * Get a specific subscriber from both systems with conflict analysis
   * @param {string} uid - Subscriber unique identifier
   * @returns {Promise<{data: {subscriber: Object, syncStatus: string, conflicts: Array}}>}
   */
  async getSubscriber(uid) {
    try {
      const response = await apiClient.get(`/dual/subscribers/${encodeURIComponent(uid)}`);
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          syncStatus: response.data?.syncStatus,
          conflicts: response.data?.conflicts || [],
          cloudExists: response.data?.cloudExists,
          legacyExists: response.data?.legacyExists,
          comparison: response.data?.comparison,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to fetch dual subscriber ${uid}:`, error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to fetch dual subscriber ${uid}`
      );
    }
  },

  /**
   * Create a subscriber in both Cloud and Legacy systems
   * @param {Object} subscriberData - Subscriber information
   * @returns {Promise<{data: {subscriber: Object, cloudResult: Object, legacyResult: Object, conflicts: Array}}>}
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
      
      const response = await apiClient.post('/dual/subscribers', subscriberData);
      
      // Handle partial success scenarios
      if (response.status === 207) {
        // Multi-status response - some operations failed
        const result = {
          data: {
            subscriber: response.data?.subscriber,
            cloudResult: response.data?.cloudResult,
            legacyResult: response.data?.legacyResult,
            conflicts: response.data?.conflicts || [],
            overallSuccess: response.data?.overallSuccess || false,
            partialSuccess: response.data?.partialSuccess || false,
            source: 'dual',
            timestamp: response.data?.timestamp
          }
        };
        
        // Show warning for partial success
        console.warn('Dual create completed with issues:', result.data.conflicts);
        return result;
      }
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          cloudResult: response.data?.cloudResult,
          legacyResult: response.data?.legacyResult,
          conflicts: response.data?.conflicts || [],
          syncStatus: response.data?.syncStatus,
          message: response.data?.message,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to create dual subscriber:', error);
      
      // Handle dual-system specific errors
      if (error.response?.status === 422) {
        const errorData = error.response.data;
        throw new Error(
          `Dual creation failed: Cloud ${errorData?.cloudResult?.success ? 'succeeded' : 'failed'}, ` +
          `Legacy ${errorData?.legacyResult?.success ? 'succeeded' : 'failed'}`
        );
      }
      
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to create dual subscriber'
      );
    }
  },

  /**
   * Update a subscriber in both systems
   * @param {string} uid - Subscriber UID
   * @param {Object} updateData - Fields to update
   * @returns {Promise<{data: {cloudResult: Object, legacyResult: Object, overallSuccess: boolean}}>}
   */
  async updateSubscriber(uid, updateData) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for update');
      }
      
      const response = await apiClient.put(`/dual/subscribers/${encodeURIComponent(uid)}`, updateData);
      
      return {
        data: {
          cloudResult: response.data?.cloudResult,
          legacyResult: response.data?.legacyResult,
          overallSuccess: response.data?.overallSuccess,
          partialSuccess: response.data?.partialSuccess,
          message: response.data?.message,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to update dual subscriber ${uid}:`, error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to update dual subscriber ${uid}`
      );
    }
  },

  /**
   * Delete a subscriber from both systems
   * @param {string} uid - Subscriber UID to delete
   * @returns {Promise<{data: {cloudResult: Object, legacyResult: Object, overallSuccess: boolean}}>}
   */
  async deleteSubscriber(uid) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for deletion');
      }
      
      const response = await apiClient.delete(`/dual/subscribers/${encodeURIComponent(uid)}`);
      
      return {
        data: {
          cloudResult: response.data?.cloudResult,
          legacyResult: response.data?.legacyResult,
          overallSuccess: response.data?.overallSuccess,
          partialSuccess: response.data?.partialSuccess,
          message: response.data?.message,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to delete dual subscriber ${uid}:`, error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to delete dual subscriber ${uid}`
      );
    }
  },

  /**
   * Get overall synchronization status between Cloud and Legacy
   * @returns {Promise<{data: {syncStats: Object, systemHealth: Object}}>}
   */
  async getSyncStatus() {
    try {
      const response = await apiClient.get('/dual/sync-status');
      
      return {
        data: {
          syncStats: response.data?.syncStats || {
            synced: 0,
            outOfSync: 0,
            cloudOnly: 0,
            legacyOnly: 0,
            conflicts: 0,
            lastSyncTime: null
          },
          systemHealth: response.data?.systemHealth || {
            cloud: { healthy: false, responseTime: 999 },
            legacy: { healthy: false, responseTime: 999 }
          },
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to get sync status:', error);
      
      // Return default data for graceful degradation
      return {
        data: {
          syncStats: {
            synced: 0,
            outOfSync: 0,
            cloudOnly: 0,
            legacyOnly: 0,
            conflicts: 0,
            lastSyncTime: null
          },
          systemHealth: {
            cloud: { healthy: false, responseTime: 999, error: 'Sync status unavailable' },
            legacy: { healthy: false, responseTime: 999, error: 'Sync status unavailable' }
          },
          error: error.message,
          timestamp: new Date().toISOString()
        }
      };
    }
  },

  /**
   * Synchronize a specific subscriber between Cloud and Legacy
   * @param {string} uid - Subscriber UID to sync
   * @param {string} [strategy='cloud_wins'] - Sync strategy (cloud_wins, legacy_wins, manual)
   * @returns {Promise<{data: {message: string, beforeSync: Object, afterSync: Object}}>}
   */
  async syncSubscriber(uid, strategy = 'cloud_wins') {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for sync');
      }
      
      const response = await apiClient.post(
        `/dual/subscribers/${encodeURIComponent(uid)}/sync`,
        { strategy }
      );
      
      return {
        data: {
          message: response.data?.message,
          strategy: response.data?.strategy,
          beforeSync: response.data?.beforeSync,
          afterSync: response.data?.afterSync,
          conflicts: response.data?.conflicts || [],
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to sync subscriber ${uid}:`, error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to sync subscriber ${uid}`
      );
    }
  },

  /**
   * Bulk synchronization across systems
   * @param {Array<string>} uids - Array of subscriber UIDs to sync
   * @param {string} [strategy='cloud_wins'] - Sync strategy
   * @returns {Promise<{data: {jobId: string, status: string, results: Array}}>}
   */
  async bulkSync(uids, strategy = 'cloud_wins') {
    try {
      if (!Array.isArray(uids) || uids.length === 0) {
        throw new Error('UIDs array is required for bulk sync');
      }
      
      const response = await apiClient.post('/dual/sync/bulk', {
        uids,
        strategy
      });
      
      return {
        data: {
          jobId: response.data?.jobId,
          status: response.data?.status,
          results: response.data?.results || [],
          affectedCount: response.data?.affectedCount,
          successCount: response.data?.successCount,
          failureCount: response.data?.failureCount,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to execute bulk sync:', error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to execute bulk sync'
      );
    }
  },

  /**
   * Get health status of both Cloud and Legacy systems
   * @returns {Promise<{data: {cloud: Object, legacy: Object, overall: Object}}>}
   */
  async getSystemHealth() {
    try {
      const response = await apiClient.get('/dual/health');
      
      return {
        data: {
          cloud: response.data?.cloud || { healthy: false, responseTime: 999 },
          legacy: response.data?.legacy || { healthy: false, responseTime: 999 },
          overall: response.data?.overall || {
            healthy: false,
            syncCapable: false,
            lastHealthCheck: new Date().toISOString()
          },
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      // Graceful degradation for health checks
      return {
        data: {
          cloud: { healthy: false, responseTime: 999, error: 'Health check failed' },
          legacy: { healthy: false, responseTime: 999, error: 'Health check failed' },
          overall: {
            healthy: false,
            syncCapable: false,
            lastHealthCheck: new Date().toISOString(),
            error: error.message
          },
          timestamp: new Date().toISOString()
        }
      };
    }
  },

  /**
   * Resolve conflicts for a specific subscriber
   * @param {string} uid - Subscriber UID
   * @param {Object} resolutionData - How to resolve conflicts
   * @param {string} resolutionData.strategy - Resolution strategy
   * @param {Object} [resolutionData.manualData] - Manual resolution data
   * @returns {Promise<{data: {subscriber: Object, resolved: boolean}}>}
   */
  async resolveConflicts(uid, resolutionData) {
    try {
      if (!uid?.trim()) {
        throw new Error('UID is required for conflict resolution');
      }
      
      const response = await apiClient.post(
        `/dual/subscribers/${encodeURIComponent(uid)}/resolve`,
        resolutionData
      );
      
      return {
        data: {
          subscriber: response.data?.subscriber,
          resolved: response.data?.resolved,
          strategy: response.data?.strategy,
          conflictsResolved: response.data?.conflictsResolved || [],
          message: response.data?.message,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error(`Failed to resolve conflicts for ${uid}:`, error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        `Failed to resolve conflicts for ${uid}`
      );
    }
  },

  /**
   * Export comparison data between Cloud and Legacy
   * @param {Object} [filters] - Export filters
   * @returns {Promise<{data: {exportUrl: string, recordCount: number}}>}
   */
  async exportComparison(filters = {}) {
    try {
      const response = await apiClient.post('/dual/export/comparison', { filters });
      
      return {
        data: {
          exportUrl: response.data?.exportUrl,
          recordCount: response.data?.recordCount,
          format: response.data?.format || 'CSV',
          expiresAt: response.data?.expiresAt,
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to export comparison:', error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to export comparison data'
      );
    }
  },

  /**
   * Bulk operations across both systems
   * @param {Object} operation - Bulk operation details
   * @param {string} operation.type - Operation type (UPDATE, DELETE, SYNC)
   * @param {Array<string>} operation.uids - Array of subscriber UIDs
   * @param {Object} [operation.updateData] - Data for bulk update
   * @param {string} [operation.syncStrategy] - Strategy for sync operations
   * @returns {Promise<{data: {jobId: string, status: string, cloudResults: Array, legacyResults: Array}}>}
   */
  async bulkOperation(operation) {
    try {
      if (!operation.type || !Array.isArray(operation.uids)) {
        throw new Error('Operation type and UIDs array are required');
      }
      
      const response = await apiClient.post('/dual/subscribers/bulk', operation);
      
      return {
        data: {
          jobId: response.data?.jobId,
          status: response.data?.status,
          cloudResults: response.data?.cloudResults || [],
          legacyResults: response.data?.legacyResults || [],
          overallSuccess: response.data?.overallSuccess,
          successCount: response.data?.successCount,
          failureCount: response.data?.failureCount,
          conflicts: response.data?.conflicts || [],
          source: 'dual',
          timestamp: response.data?.timestamp
        }
      };
    } catch (error) {
      console.error('Failed to execute dual bulk operation:', error);
      throw new Error(
        error.response?.data?.message || 
        error.response?.data?.error || 
        'Failed to execute dual bulk operation'
      );
    }
  }
};