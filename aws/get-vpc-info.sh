#!/bin/bash
set -euo pipefail

# Get VPC and Subnet Information for SAM Deployment
echo "🌐 Getting VPC and Subnet information..."
echo ""

# Get default VPC
echo "📋 Available VPCs:"
aws ec2 describe-vpcs \
    --query 'Vpcs[*].{VpcId:VpcId,IsDefault:IsDefault,CidrBlock:CidrBlock,State:State}' \
    --output table

# Get VPC ID (prefer default VPC)
VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=is-default,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text 2>/dev/null || \
    aws ec2 describe-vpcs \
    --query 'Vpcs[0].VpcId' \
    --output text)

echo ""
echo "✅ Using VPC: $VPC_ID"
echo ""

# Get subnets for this VPC
echo "📋 Available Subnets in VPC $VPC_ID:"
aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].{SubnetId:SubnetId,AZ:AvailabilityZone,CidrBlock:CidrBlock,Type:Tags[?Key==`Name`].Value|[0]}' \
    --output table

# Get private subnets (or any 2 subnets if no private ones)
PRIVATE_SUBNETS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].SubnetId' \
    --output text | tr '\t' '\n' | head -2)

SUBNET1=$(echo "$PRIVATE_SUBNETS" | head -1)
SUBNET2=$(echo "$PRIVATE_SUBNETS" | tail -1)

echo ""
echo "✅ Selected Subnets:"
echo "   Subnet 1: $SUBNET1"
echo "   Subnet 2: $SUBNET2"
echo ""

# Generate deployment command
echo "🚀 DEPLOYMENT COMMAND:"
echo ""
echo "sam deploy \\"
echo "    --stack-name subscriber-migration-portal-prod \\"
echo "    --capabilities CAPABILITY_NAMED_IAM \\"
echo "    --parameter-overrides \\"
echo "        Stage=prod \\"
echo "        JwtSecret=jwt-secret-prod-2024 \\"
echo "        CorsOrigins=\"'http://subscriber-migration-portal-prod-frontend.s3-website-us-east-1.amazonaws.com'\" \\"
echo "        VpcId=$VPC_ID \\"
echo "        PrivateSubnetId1=$SUBNET1 \\"
echo "        PrivateSubnetId2=$SUBNET2 \\"
echo "        DeploymentHash=20251104-force-api-redeploy \\"
echo "    --no-confirm-changeset \\"
echo "    --force-upload"
echo ""
echo "💡 Copy-paste this command to deploy with correct VPC settings!"
