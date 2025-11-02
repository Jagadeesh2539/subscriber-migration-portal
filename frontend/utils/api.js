class APIService {
    constructor() {
        this.baseURL = AppConfig.API_BASE;
        this.retryAttempts = AppConfig.RETRY_ATTEMPTS;
        this.timeout = AppConfig.TIMEOUT;
    }

    // Core HTTP method
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                ...options.headers
            },
            timeout: this.timeout,
            ...options
        };

        // Add request body if provided
        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        let lastError;
        
        // Retry logic
        for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
            try {
                console.log(`🔄 API Request (${attempt}/${this.retryAttempts}):`, config.method, url);
                
                const response = await this.fetchWithTimeout(url, config);
                const data = await response.json();
                
                if (response.ok) {
                    console.log('✅ API Success:', data);
                    return { success: true, data, status: response.status };
                } else {
                    throw new Error(`HTTP ${response.status}: ${data.message || 'Request failed'}`);
                }
            } catch (error) {
                lastError = error;
                console.warn(`⚠️ API Attempt ${attempt} failed:`, error.message);
                
                if (attempt < this.retryAttempts) {
                    await this.delay(1000 * attempt); // Exponential backoff
                }
            }
        }

        console.error('❌ API Request Failed:', lastError.message);
        return { success: false, error: lastError.message };
    }

    // Fetch with timeout
    async fetchWithTimeout(url, config) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);
        
        try {
            const response = await fetch(url, {
                ...config,
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            return response;
        } catch (error) {
            clearTimeout(timeoutId);
            throw error;
        }
    }

    // Utility delay function
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Health Check
    async healthCheck() {
        return this.request('/health');
    }

    // Dashboard APIs
    async getDashboardStats() {
        return this.request('/dashboard/stats');
    }

    async getRecentMigrations() {
        return this.request('/dashboard/recent-migrations');
    }

    // Migration APIs
    async getMigrations(page = 1, limit = AppConfig.PAGINATION_SIZE) {
        return this.request(`/migrations?page=${page}&limit=${limit}`);
    }

    async getMigration(migrationId) {
        return this.request(`/migrations/${migrationId}`);
    }

    async createMigration(migrationData) {
        return this.request('/migrations', {
            method: 'POST',
            body: migrationData
        });
    }

    async startMigration(migrationId) {
        return this.request(`/migrations/${migrationId}/start`, {
            method: 'POST'
        });
    }

    async pauseMigration(migrationId) {
        return this.request(`/migrations/${migrationId}/pause`, {
            method: 'POST'
        });
    }

    async cancelMigration(migrationId) {
        return this.request(`/migrations/${migrationId}/cancel`, {
            method: 'POST'
        });
    }

    // Subscriber APIs
    async getSubscribers(page = 1, limit = AppConfig.PAGINATION_SIZE, filters = {}) {
        const queryParams = new URLSearchParams({
            page: page.toString(),
            limit: limit.toString(),
            ...filters
        });
        return this.request(`/subscribers?${queryParams}`);
    }

    async getSubscriber(subscriberId) {
        return this.request(`/subscribers/${subscriberId}`);
    }

    async createSubscriber(subscriberData) {
        return this.request('/subscribers', {
            method: 'POST',
            body: subscriberData
        });
    }

    async updateSubscriber(subscriberId, subscriberData) {
        return this.request(`/subscribers/${subscriberId}`, {
            method: 'PUT',
            body: subscriberData
        });
    }

    async deleteSubscriber(subscriberId) {
        return this.request(`/subscribers/${subscriberId}`, {
            method: 'DELETE'
        });
    }

    // Bulk Operations
    async bulkImportSubscribers(fileData) {
        const formData = new FormData();
        formData.append('file', fileData);
        
        return this.request('/subscribers/bulk-import', {
            method: 'POST',
            body: formData,
            headers: {} // Remove Content-Type to let browser set boundary
        });
    }

    async exportSubscribers(format = 'csv', filters = {}) {
        const queryParams = new URLSearchParams({
            format,
            ...filters
        });
        return this.request(`/subscribers/export?${queryParams}`);
    }

    // Analytics APIs
    async getAnalytics(timeRange = '30d') {
        return this.request(`/analytics?timeRange=${timeRange}`);
    }

    async getMigrationAnalytics(migrationId) {
        return this.request(`/analytics/migrations/${migrationId}`);
    }

    // Logs APIs
    async getLogs(page = 1, limit = AppConfig.PAGINATION_SIZE, level = 'all') {
        return this.request(`/logs?page=${page}&limit=${limit}&level=${level}`);
    }

    async getLogDetails(logId) {
        return this.request(`/logs/${logId}`);
    }

    // Admin APIs
    async getSystemStatus() {
        return this.request('/admin/system-status');
    }

    async getConfiguration() {
        return this.request('/admin/configuration');
    }

    async updateConfiguration(config) {
        return this.request('/admin/configuration', {
            method: 'PUT',
            body: config
        });
    }

    // Database Operations
    async validateConnection(connectionData) {
        return this.request('/admin/validate-connection', {
            method: 'POST',
            body: connectionData
        });
    }

    async testMigration(testData) {
        return this.request('/admin/test-migration', {
            method: 'POST',
            body: testData
        });
    }
}

// Global API instance
const API = new APIService();
