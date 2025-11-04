// Application Configuration
const AppConfig = {
    // API Configuration
    API_BASE: 'https://bhgplw8pyk.execute-api.us-east-1.amazonaws.com/prod',
    
    // Build Information
    VERSION: 'v3.0.0-prod',
    BUILD_TIME: new Date().toISOString(),
    ENVIRONMENT: 'production',
    
    // AWS Configuration
    AWS_REGION: 'us-east-1',
    STACK_NAME: 'subscriber-migration-portal-prod',
    
    // Application Settings
    PAGINATION_SIZE: 25,
    REFRESH_INTERVAL: 30000, // 30 seconds
    RETRY_ATTEMPTS: 3,
    TIMEOUT: 30000,
    
    // Migration Settings
    MAX_BATCH_SIZE: 1000,
    SUPPORTED_FORMATS: ['csv', 'json', 'xlsx'],
    
    // Status Constants
    MIGRATION_STATUSES: {
        PENDING: 'pending',
        IN_PROGRESS: 'in_progress', 
        COMPLETED: 'completed',
        FAILED: 'failed',
        CANCELLED: 'cancelled'
    },
    
    // Database Types
    SOURCE_DATABASES: ['mysql', 'postgresql', 'mongodb'],
    TARGET_DATABASES: ['dynamodb', 'rds', 's3']
};

// Environment-specific overrides
if (typeof window !== 'undefined') {
    // Read from environment variables if available
    AppConfig.API_BASE = window.REACT_APP_API_URL || AppConfig.API_BASE;
    AppConfig.VERSION = window.REACT_APP_VERSION || AppConfig.VERSION;
    AppConfig.BUILD_TIME = window.REACT_APP_BUILD_TIME || AppConfig.BUILD_TIME;
}
