#!/bin/bash

# ==============================================
# AWS SAM Deployment Script
# Deploys Subscriber Migration Portal API
# NO FLASK - Pure AWS Services
# ==============================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="subscriber-migration-portal"
REGION="us-east-1"
STAGE="dev"
BUCKET_PREFIX="sam-deployment"
JWT_SECRET_LENGTH=64

# Functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            REGION="$2"
            shift 2
            ;;
        --stage)
            STAGE="$2"
            shift 2
            ;;
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --region REGION        AWS region (default: us-east-1)"
            echo "  --stage STAGE          Deployment stage (default: dev)"
            echo "  --stack-name NAME      CloudFormation stack name (default: subscriber-migration-portal)"
            echo "  --help                 Show this help message"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Validate prerequisites
log "Checking prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    error "AWS CLI is not installed. Please install it first."
fi

# Check SAM CLI
if ! command -v sam &> /dev/null; then
    error "AWS SAM CLI is not installed. Please install it first."
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 is not installed."
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    error "AWS credentials are not configured. Please run 'aws configure'."
fi

success "Prerequisites check passed"

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log "Deploying to AWS Account: $ACCOUNT_ID in region: $REGION"

# Set deployment bucket name
DEPLOYMENT_BUCKET="${BUCKET_PREFIX}-${ACCOUNT_ID}-${REGION}"

# Create S3 bucket for SAM deployment artifacts if it doesn't exist
log "Checking deployment bucket: $DEPLOYMENT_BUCKET"
if ! aws s3api head-bucket --bucket "$DEPLOYMENT_BUCKET" 2>/dev/null; then
    log "Creating deployment bucket..."
    if [ "$REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$DEPLOYMENT_BUCKET"
    else
        aws s3api create-bucket --bucket "$DEPLOYMENT_BUCKET" --create-bucket-configuration LocationConstraint="$REGION"
    fi
    
    # Enable versioning
    aws s3api put-bucket-versioning --bucket "$DEPLOYMENT_BUCKET" --versioning-configuration Status=Enabled
    
    # Block public access
    aws s3api put-public-access-block --bucket "$DEPLOYMENT_BUCKET" --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    
    success "Deployment bucket created: $DEPLOYMENT_BUCKET"
else
    success "Deployment bucket exists: $DEPLOYMENT_BUCKET"
fi

# Generate JWT secret if not provided
if [ -z "$JWT_SECRET" ]; then
    log "Generating JWT secret..."
    JWT_SECRET=$(openssl rand -base64 $JWT_SECRET_LENGTH)
    success "JWT secret generated"
fi

# Build Lambda Layer
log "Building Lambda layer..."
cd layers/common

# Create python directory structure
mkdir -p python
cp common_utils.py python/

# Install dependencies
if [ -f requirements.txt ]; then
    log "Installing layer dependencies..."
    pip3 install -r requirements.txt -t python/
fi

cd ../../
success "Lambda layer built"

# Validate SAM template
log "Validating SAM template..."
if ! sam validate --template template.yaml --region "$REGION"; then
    error "SAM template validation failed"
fi
success "SAM template is valid"

# Build SAM application
log "Building SAM application..."
if ! sam build --template template.yaml; then
    error "SAM build failed"
fi
success "SAM application built"

# Deploy with guided parameters for first deployment
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &>/dev/null; then
    log "Stack exists. Performing update..."
    DEPLOY_MODE="update"
else
    log "Stack does not exist. Performing initial deployment..."
    DEPLOY_MODE="create"
fi

# Prepare deployment parameters
PARAMETERS="Stage=$STAGE JwtSecret='$JWT_SECRET'"

# Set CORS origins based on stage - FIXED TO USE ACTUAL FRONTEND URLs
if [ "$STAGE" = "prod" ]; then
    CORS_ORIGINS="http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com"
elif [ "$STAGE" = "staging" ]; then
    CORS_ORIGINS="http://subscriber-migration-portal-staging-frontend.s3-website-us-east-1.amazonaws.com"
else
    CORS_ORIGINS="https://localhost:3000,http://localhost:3000"
fi

PARAMETERS="$PARAMETERS CorsOrigins='$CORS_ORIGINS'"

log "Using CORS Origins: $CORS_ORIGINS"

# Deploy the application
log "Deploying SAM application..."
if [ "$DEPLOY_MODE" = "create" ]; then
    # Guided deployment for first time
    sam deploy --guided \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --s3-bucket "$DEPLOYMENT_BUCKET" \
        --parameter-overrides $PARAMETERS \
        --capabilities CAPABILITY_IAM \
        --no-fail-on-empty-changeset \
        --confirm-changeset
else
    # Update deployment
    sam deploy \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --s3-bucket "$DEPLOYMENT_BUCKET" \
        --parameter-overrides $PARAMETERS \
        --capabilities CAPABILITY_IAM \
        --no-fail-on-empty-changeset
fi

if [ $? -eq 0 ]; then
    success "SAM deployment completed successfully"
else
    error "SAM deployment failed"
fi

# Get stack outputs
log "Retrieving stack outputs..."
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text)

UPLOAD_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`UploadBucketName`].OutputValue' \
    --output text)

SUBSCRIBER_TABLE=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`SubscribersTableName`].OutputValue' \
    --output text)

# Display deployment information
echo ""
echo "==============================================="
echo "🎉 DEPLOYMENT SUCCESSFUL!"
echo "==============================================="
echo "Stack Name:       $STACK_NAME"
echo "Region:           $REGION"
echo "Stage:            $STAGE"
echo "API Endpoint:     $API_ENDPOINT"
echo "Upload Bucket:    $UPLOAD_BUCKET"
echo "Subscriber Table: $SUBSCRIBER_TABLE"
echo "CORS Origins:     $CORS_ORIGINS"
echo "==============================================="
echo ""

# Test API health endpoint
log "Testing API health endpoint..."
if curl -s "$API_ENDPOINT/health" | grep -q '"status"'; then
    success "API health check passed"
else
    warn "API health check failed or endpoint not ready yet"
fi

# Create environment file for frontend
log "Creating frontend environment file..."
cat > ../frontend/.env.production << EOF
# Production Environment Configuration
# Generated on $(date)

REACT_APP_API_URL=${API_ENDPOINT}
REACT_APP_STAGE=${STAGE}
REACT_APP_DEBUG_MODE=false
REACT_APP_ENABLE_ANALYTICS=true
REACT_APP_ENABLE_MONITORING=true
EOF

success "Frontend environment file created: ../frontend/.env.production"

# Generate deployment summary
log "Generating deployment summary..."
cat > deployment-summary.json << EOF
{
  "deploymentTime": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "stackName": "$STACK_NAME",
  "region": "$REGION",
  "stage": "$STAGE",
  "accountId": "$ACCOUNT_ID",
  "apiEndpoint": "$API_ENDPOINT",
  "uploadBucket": "$UPLOAD_BUCKET",
  "subscriberTable": "$SUBSCRIBER_TABLE",
  "deploymentBucket": "$DEPLOYMENT_BUCKET",
  "corsOrigins": "$CORS_ORIGINS"
}
EOF

success "Deployment summary saved to deployment-summary.json"

echo ""
echo "==============================================="
echo "🚀 NEXT STEPS:"
echo "==============================================="
echo "1. Update your frontend .env file with:"
echo "   REACT_APP_API_URL=$API_ENDPOINT"
echo ""
echo "2. Test your API endpoints:"
echo "   curl $API_ENDPOINT/health"
echo ""
echo "3. Deploy your React frontend to S3/CloudFront"
echo ""
echo "4. Configure user credentials in AWS Secrets Manager"
echo "   Secret Name: ${STACK_NAME}-users"
echo ""
echo "==============================================="

log "Deployment completed successfully! 🎉"