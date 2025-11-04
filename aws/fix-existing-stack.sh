#!/bin/bash
set -euo pipefail

# Fix Existing Stack Deployment Issues
echo "🔧 Fixing existing subscriber-migration-portal-prod stack..."
echo "📅 $(date)"
echo ""

# Step 1: Check current stack status
echo "🔍 Step 1: Checking current stack status..."
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name subscriber-migration-portal-prod \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

echo "Current stack status: $STACK_STATUS"
echo ""

# Step 2: Handle different stack states
case $STACK_STATUS in
    "ROLLBACK_COMPLETE"|"CREATE_FAILED"|"UPDATE_ROLLBACK_COMPLETE")
        echo "⚠️  Stack is in failed state: $STACK_STATUS"
        echo "🗑️  Deleting failed stack..."
        aws cloudformation delete-stack --stack-name subscriber-migration-portal-prod
        echo "⏳ Waiting for stack deletion..."
        aws cloudformation wait stack-delete-complete --stack-name subscriber-migration-portal-prod
        echo "✅ Stack deleted successfully"
        STACK_STATUS="DOES_NOT_EXIST"
        ;;
    "UPDATE_IN_PROGRESS"|"CREATE_IN_PROGRESS")
        echo "⚠️  Stack operation in progress. Waiting..."
        aws cloudformation wait stack-create-complete --stack-name subscriber-migration-portal-prod 2>/dev/null || \
        aws cloudformation wait stack-update-complete --stack-name subscriber-migration-portal-prod 2>/dev/null || \
        echo "Stack operation may have failed"
        ;;
    "CREATE_COMPLETE"|"UPDATE_COMPLETE")
        echo "✅ Stack is in good state: $STACK_STATUS"
        ;;
esac

echo ""

# Step 3: Get actual VPC and subnet IDs from AWS
echo "🌐 Step 2: Getting VPC information from your AWS account..."

# Get default VPC
VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=is-default,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text 2>/dev/null || \
    aws ec2 describe-vpcs \
    --query 'Vpcs[0].VpcId' \
    --output text)

echo "Found VPC: $VPC_ID"

# Get first 2 subnets from this VPC
SUBNETS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[0:2].SubnetId' \
    --output text)

SUBNET1=$(echo $SUBNETS | cut -d' ' -f1)
SUBNET2=$(echo $SUBNETS | cut -d' ' -f2)

echo "Found Subnet 1: $SUBNET1"
echo "Found Subnet 2: $SUBNET2"
echo ""

# Step 4: Build and deploy
echo "🏗️  Step 3: Building SAM application..."
cd "$(dirname "$0")"
sam build --template-file template.yaml
echo "✅ Build complete"
echo ""

echo "🚀 Step 4: Deploying with CORS fixes..."
if [ "$STACK_STATUS" = "DOES_NOT_EXIST" ]; then
    echo "Creating new stack..."
    sam deploy \
        --stack-name subscriber-migration-portal-prod \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameter-overrides \
            Stage=prod \
            JwtSecret="jwt-secret-prod-2024" \
            CorsOrigins="'http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com'" \
            VpcId="$VPC_ID" \
            PrivateSubnetId1="$SUBNET1" \
            PrivateSubnetId2="$SUBNET2" \
            DeploymentHash="20251104-force-api-redeploy" \
        --confirm-changeset
else
    echo "Updating existing stack..."
    sam deploy \
        --stack-name subscriber-migration-portal-prod \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameter-overrides \
            Stage=prod \
            JwtSecret="jwt-secret-prod-2024" \
            CorsOrigins="'http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com'" \
            VpcId="$VPC_ID" \
            PrivateSubnetId1="$SUBNET1" \
            PrivateSubnetId2="$SUBNET2" \
            DeploymentHash="20251104-force-api-redeploy" \
        --no-confirm-changeset \
        --force-upload
fi

echo ""
echo "✅ Deployment complete!"
echo ""

# Step 5: Test CORS
echo "🧪 Step 5: Testing CORS preflight..."
API_ENDPOINT="https://bhgplw8pyk.execute-api.us-east-1.amazonaws.com/prod"
ORIGIN="http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com"

echo "Testing: $API_ENDPOINT/auth/login"
curl -X OPTIONS \
    "$API_ENDPOINT/auth/login" \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Authorization,Content-Type" \
    -s -w "\nHTTP Status: %{http_code}\n" \
    -o /dev/null

echo ""
echo "🎉 CORS fix complete! Your site should work now."
