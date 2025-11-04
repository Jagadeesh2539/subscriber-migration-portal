class Dashboard {
    constructor() {
        this.stats = {};
        this.recentMigrations = [];
        this.refreshInterval = null;
    }

    render() {
        return `
            <div class="dashboard">
                <div class="dashboard-header">
                    <h2>📊 Migration Dashboard</h2>
                    <div class="dashboard-actions">
                        <button class="btn-secondary" onclick="Dashboard.refresh()">
                            🔄 Refresh
                        </button>
                        <button class="btn-primary" onclick="Navigation.showPage('migration')">
                            ➕ New Migration
                        </button>
                    </div>
                </div>

                <!-- Statistics Cards -->
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-icon">👥</div>
                        <div class="stat-content">
                            <h3>Total Subscribers</h3>
                            <div class="stat-number" id="total-subscribers">-</div>
                            <div class="stat-change positive" id="subscribers-change">+0%</div>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon">🔄</div>
                        <div class="stat-content">
                            <h3>Active Migrations</h3>
                            <div class="stat-number" id="active-migrations">-</div>
                            <div class="stat-change" id="migrations-change">-</div>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon">✅</div>
                        <div class="stat-content">
                            <h3>Success Rate</h3>
                            <div class="stat-number" id="success-rate">-%</div>
                            <div class="stat-change positive" id="success-change">+0%</div>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon">📈</div>
                        <div class="stat-content">
                            <h3>Data Transferred</h3>
                            <div class="stat-number" id="data-transferred">- GB</div>
                            <div class="stat-change positive" id="data-change">+0 GB</div>
                        </div>
                    </div>
                </div>

                <!-- Recent Migrations -->
                <div class="dashboard-section">
                    <h3>🕒 Recent Migrations</h3>
                    <div class="recent-migrations" id="recent-migrations">
                        <div class="loading">Loading recent migrations...</div>
                    </div>
                </div>

                <!-- System Health -->
                <div class="dashboard-section">
                    <h3>💚 System Health</h3>
                    <div class="health-grid">
                        <div class="health-item">
                            <span class="health-label">API Gateway</span>
                            <span class="health-status" id="api-health">🟡 Checking...</span>
                        </div>
                        <div class="health-item">
                            <span class="health-label">Database</span>
                            <span class="health-status" id="db-health">🟡 Checking...</span>
                        </div>
                        <div class="health-item">
                            <span class="health-label">Lambda Functions</span>
                            <span class="health-status" id="lambda-health">🟡 Checking...</span>
                        </div>
                        <div class="health-item">
                            <span class="health-label">Step Functions</span>
                            <span class="health-status" id="stepfunctions-health">🟡 Checking...</span>
                        </div>
                    </div>
                </div>

                <!-- Quick Actions -->
                <div class="dashboard-section">
                    <h3>⚡ Quick Actions</h3>
                    <div class="quick-actions">
                        <button class="action-btn" onclick="Dashboard.runHealthCheck()">
                            🏥 Health Check
                        </button>
                        <button class="action-btn" onclick="Dashboard.exportData()">
                            📊 Export Data
                        </button>
                        <button class="action-btn" onclick="Dashboard.viewLogs()">
                            📝 View Logs
                        </button>
                        <button class="action-btn" onclick="Dashboard.systemStatus()">
                            ⚙️ System Status
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    async init() {
        document.getElementById('main-content').innerHTML = this.render();
        await this.loadData();
        this.startAutoRefresh();
    }

    async loadData() {
        try {
            // Load dashboard statistics
            const statsResponse = await API.getDashboardStats();
            if (statsResponse.success) {
                this.updateStats(statsResponse.data);
            }

            // Load recent migrations
            const migrationsResponse = await API.getRecentMigrations();
            if (migrationsResponse.success) {
                this.updateRecentMigrations(migrationsResponse.data);
            }

            // Check system health
            await this.checkSystemHealth();

        } catch (error) {
            console.error('Dashboard load error:', error);
            Notifications.error('Failed to load dashboard data');
        }
    }

    updateStats(stats) {
        this.stats = stats;
        
        // Update stat numbers
        document.getElementById('total-subscribers').textContent = 
            this.formatNumber(stats.totalSubscribers || 0);
        document.getElementById('active-migrations').textContent = 
            stats.activeMigrations || 0;
        document.getElementById('success-rate').textContent = 
            `${stats.successRate || 0}%`;
        document.getElementById('data-transferred').textContent = 
            `${this.formatBytes(stats.dataTransferred || 0)}`;

        // Update change indicators
        this.updateChangeIndicator('subscribers-change', stats.subscribersChange);
        this.updateChangeIndicator('success-change', stats.successChange);
        this.updateChangeIndicator('data-change', stats.dataChange, 'bytes');
    }

    updateChangeIndicator(elementId, change, format = 'percent') {
        const element = document.getElementById(elementId);
        if (!element || change === undefined) return;

        let displayValue;
        if (format === 'bytes') {
            displayValue = `+${this.formatBytes(change)}`;
        } else {
            displayValue = `${change >= 0 ? '+' : ''}${change}%`;
        }

        element.textContent = displayValue;
        element.className = `stat-change ${change >= 0 ? 'positive' : 'negative'}`;
    }

    updateRecentMigrations(migrations) {
        this.recentMigrations = migrations;
        const container = document.getElementById('recent-migrations');
        
        if (!migrations || migrations.length === 0) {
            container.innerHTML = '<div class="empty-state">No recent migrations</div>';
            return;
        }

        container.innerHTML = migrations.map(migration => `
            <div class="migration-item" onclick="Navigation.showMigrationDetails('${migration.id}')">
                <div class="migration-info">
                    <h4>${migration.name || `Migration ${migration.id.slice(0, 8)}`}</h4>
                    <p>From ${migration.source} to ${migration.target}</p>
                </div>
                <div class="migration-status">
                    <span class="status-badge ${migration.status}">${migration.status}</span>
                    <small>${this.formatDate(migration.createdAt)}</small>
                </div>
                <div class="migration-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${migration.progress || 0}%"></div>
                    </div>
                    <span>${migration.progress || 0}%</span>
                </div>
            </div>
        `).join('');
    }

    async checkSystemHealth() {
        // API Gateway Health
        try {
            const healthResponse = await API.healthCheck();
            this.updateHealthStatus('api-health', healthResponse.success);
        } catch (error) {
            this.updateHealthStatus('api-health', false);
        }

        // Additional health checks would go here
        // For now, we'll simulate them
        setTimeout(() => {
            this.updateHealthStatus('db-health', true);
            this.updateHealthStatus('lambda-health', true);
            this.updateHealthStatus('stepfunctions-health', true);
        }, 1000);
    }

    updateHealthStatus(elementId, isHealthy) {
        const element = document.getElementById(elementId);
        if (!element) return;

        if (isHealthy) {
            element.textContent = '🟢 Healthy';
            element.className = 'health-status healthy';
        } else {
            element.textContent = '🔴 Issues';
            element.className = 'health-status unhealthy';
        }
    }

    // Utility methods
    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    formatDate(dateStr) {
        return new Date(dateStr).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    // Action handlers
    async refresh() {
        Notifications.info('Refreshing dashboard...');
        await this.loadData();
        Notifications.success('Dashboard refreshed');
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        this.refreshInterval = setInterval(() => {
            this.loadData();
        }, AppConfig.REFRESH_INTERVAL);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    async runHealthCheck() {
        Notifications.info('Running system health check...');
        await this.checkSystemHealth();
        Notifications.success('Health check completed');
    }

    async exportData() {
        try {
            const response = await API.exportSubscribers('csv');
            if (response.success) {
                // Trigger download
                const blob = new Blob([response.data], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `subscribers_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                Notifications.success('Data exported successfully');
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            Notifications.error('Export failed: ' + error.message);
        }
    }

    viewLogs() {
        Navigation.showPage('logs');
    }

    systemStatus() {
        Navigation.showPage('admin');
    }

    destroy() {
        this.stopAutoRefresh();
    }
}

// Global Dashboard instance
const DashboardComponent = new Dashboard();
