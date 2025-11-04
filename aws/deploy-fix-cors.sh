#!/bin/bash
set -euo pipefail

# CORS Fix Deployment Script
# This script properly updates the existing stack to fix CORS issues

echo "🔧 CORS Fix Deployment Starting..."
echo "📅 $(date)"
echo "🏷️  Stack: subscriber-migration-portal-prod"
echo "🌍 Region: us-east-1"
echo ""

# Check if stack exists
echo "🔍 Checking if stack exists..."
if aws cloudformation describe-stacks --stack-name subscriber-migration-portal-prod --region us-east-1 >/dev/null 2>&1; then
    echo "✅ Stack exists - will UPDATE"
    STACK_EXISTS=true
else
    echo "❌ Stack does not exist - will CREATE"
    STACK_EXISTS=false
fi
echo ""

# Build SAM application
echo "🏗️  Building SAM application..."
cd "$(dirname "$0")"
sam build --template-file template.yaml
echo "✅ Build complete"
echo ""

# Deploy with correct parameters
echo "🚀 Deploying with CORS fixes..."
if [ "$STACK_EXISTS" = true ]; then
    # Update existing stack
    sam deploy \
        --stack-name subscriber-migration-portal-prod \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameter-overrides \
            Stage=prod \
            JwtSecret="jwt-secret-prod-2024" \
            CorsOrigins="'http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com'" \
            BucketSuffix=20251031 \
            DeploymentHash=20251104-force-api-redeploy \
            VpcId=vpc-0d8f3c123456789ab \
            PrivateSubnetId1=subnet-0123456789abcdef0 \
            PrivateSubnetId2=subnet-0123456789abcdef1 \
        --no-confirm-changeset \
        --force-upload
else
    # Create new stack
    sam deploy --guided
fi

echo ""
echo "✅ Deployment complete!"
echo ""

# Test CORS preflight
echo "🧪 Testing CORS preflight..."
API_ENDPOINT="https://bhgplw8pyk.execute-api.us-east-1.amazonaws.com/prod"
ORIGIN="http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com"

echo "📡 Testing: $API_ENDPOINT/auth/login"
echo "🌐 Origin: $ORIGIN"

curl -X OPTIONS \
    "$API_ENDPOINT/auth/login" \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Authorization,Content-Type" \
    -v

echo ""
echo "🎯 Expected: 200 OK with Access-Control-Allow-Origin header"
echo "🎉 CORS fix deployment complete!"
