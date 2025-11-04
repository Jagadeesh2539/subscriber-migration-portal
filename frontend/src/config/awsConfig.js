import { CognitoIdentityProviderClient } from '@aws-sdk/client-cognito-identity-provider';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';
import { S3Client } from '@aws-sdk/client-s3';
import { fromCognitoIdentityPool, fromCognitoIdentity } from '@aws-sdk/credential-providers';

// AWS Configuration
export const AWS_CONFIG = {
  region: process.env.REACT_APP_AWS_REGION || 'us-east-1',
  
  // Cognito Configuration
  cognito: {
    userPoolId: process.env.REACT_APP_COGNITO_USER_POOL_ID,
    userPoolClientId: process.env.REACT_APP_COGNITO_CLIENT_ID,
    identityPoolId: process.env.REACT_APP_COGNITO_IDENTITY_POOL_ID,
  },
  
  // DynamoDB Configuration
  dynamodb: {
    subscriberTableName: process.env.REACT_APP_SUBSCRIBER_TABLE_NAME || 'subscribers-table',
    auditLogTableName: process.env.REACT_APP_AUDIT_LOG_TABLE_NAME || 'audit-logs-table',
    migrationJobsTableName: process.env.REACT_APP_MIGRATION_JOBS_TABLE_NAME || 'migration-jobs-table',
  },
  
  // S3 Configuration
  s3: {
    uploadBucketName: process.env.REACT_APP_S3_UPLOAD_BUCKET || 'migration-uploads',
    region: process.env.REACT_APP_AWS_REGION || 'us-east-1',
  },
  
  // API Gateway (for Lambda functions if needed)
  apiGateway: {
    baseUrl: process.env.REACT_APP_API_GATEWAY_URL,
  },
};

// Initialize AWS clients
let dynamoDbClient;
let dynamoDbDocClient;
let s3Client;
let cognitoClient;

// Initialize Cognito client
export const initializeCognitoClient = () => {
  if (!cognitoClient) {
    cognitoClient = new CognitoIdentityProviderClient({
      region: AWS_CONFIG.region,
    });
  }
  return cognitoClient;
};

// Initialize DynamoDB clients with Cognito credentials
export const initializeDynamoDBClients = async (credentials) => {
  if (!dynamoDbClient) {
    dynamoDbClient = new DynamoDBClient({
      region: AWS_CONFIG.region,
      credentials,
    });
    
    dynamoDbDocClient = DynamoDBDocumentClient.from(dynamoDbClient);
  }
  return { dynamoDbClient, dynamoDbDocClient };
};

// Initialize S3 client with Cognito credentials
export const initializeS3Client = async (credentials) => {
  if (!s3Client) {
    s3Client = new S3Client({
      region: AWS_CONFIG.region,
      credentials,
    });
  }
  return s3Client;
};

// Get credentials from Cognito Identity Pool
export const getCognitoCredentials = async (idToken) => {
  try {
    const credentials = fromCognitoIdentityPool({
      identityPoolId: AWS_CONFIG.cognito.identityPoolId,
      logins: {
        [`cognito-idp.${AWS_CONFIG.region}.amazonaws.com/${AWS_CONFIG.cognito.userPoolId}`]: idToken,
      },
      clientConfig: {
        region: AWS_CONFIG.region,
      },
    });
    
    return credentials;
  } catch (error) {
    console.error('Error getting Cognito credentials:', error);
    throw error;
  }
};

// Validate AWS configuration
export const validateAWSConfig = () => {
  const requiredEnvVars = [
    'REACT_APP_AWS_REGION',
    'REACT_APP_COGNITO_USER_POOL_ID',
    'REACT_APP_COGNITO_CLIENT_ID',
    'REACT_APP_COGNITO_IDENTITY_POOL_ID',
    'REACT_APP_SUBSCRIBER_TABLE_NAME',
  ];
  
  const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);
  
  if (missingVars.length > 0) {
    throw new Error(`Missing required environment variables: ${missingVars.join(', ')}`);
  }
  
  return true;
};

// Helper function to handle AWS SDK errors
export const handleAWSError = (error, operation = 'AWS operation') => {
  console.error(`${operation} failed:`, error);
  
  // Map common AWS errors to user-friendly messages
  const errorMessages = {
    'ValidationException': 'Invalid input data provided',
    'ResourceNotFoundException': 'Requested resource not found',
    'ConditionalCheckFailedException': 'Data conflict - please refresh and try again',
    'ProvisionedThroughputExceededException': 'Service temporarily unavailable - please try again',
    'ItemCollectionSizeLimitExceededException': 'Data size limit exceeded',
    'TransactionConflictException': 'Transaction conflict - please try again',
    'AccessDeniedException': 'Access denied - insufficient permissions',
    'UnauthorizedOperation': 'Unauthorized operation',
    'InvalidParameterValueException': 'Invalid parameter value',
    'NetworkingError': 'Network error - please check your connection',
    'TimeoutError': 'Request timeout - please try again',
  };
  
  const userMessage = errorMessages[error.name] || 
                     errorMessages[error.code] || 
                     'An unexpected error occurred';
  
  return {
    name: error.name,
    code: error.code,
    message: error.message,
    userMessage,
    isRetryable: ['ProvisionedThroughputExceededException', 'TimeoutError', 'NetworkingError'].includes(error.name || error.code),
  };
};

// Retry mechanism for AWS operations
export const retryAWSOperation = async (operation, maxRetries = 3, baseDelay = 1000) => {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      const awsError = handleAWSError(error, 'Retry operation');
      
      if (attempt === maxRetries || !awsError.isRetryable) {
        throw error;
      }
      
      // Exponential backoff
      const delay = baseDelay * Math.pow(2, attempt - 1);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
};

export default {
  AWS_CONFIG,
  initializeCognitoClient,
  initializeDynamoDBClients,
  initializeS3Client,
  getCognitoCredentials,
  validateAWSConfig,
  handleAWSError,
  retryAWSOperation,
};