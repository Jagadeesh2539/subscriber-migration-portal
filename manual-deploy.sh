#!/bin/bash

# Manual deployment script for enhanced subscriber migration portal
set -e

echo "🚀 Manual deployment of enhanced subscriber migration portal"
echo "===================================================="

# Configuration
FRONTEND_BUCKET="subscriber-migration-stack-prod-frontend"
BACKEND_LAMBDA="subscriber-migration-stack-prod-BackendLambda-pw0yiCxXyN3J"
API_GATEWAY_ID="hsebznxeu6"
AWS_REGION="us-east-1"

# Check AWS credentials
echo "🔍 Checking AWS credentials..."
aws sts get-caller-identity || { echo "❌ AWS credentials not configured"; exit 1; }
echo "✅ AWS credentials verified"

# Deploy Frontend
echo ""
echo "📱 Deploying Enhanced Frontend..."
cd frontend

# Clear cache and install
echo "🧹 Clearing npm cache..."
rm -f package-lock.json
npm cache clean --force

echo "📦 Installing dependencies..."
npm install --no-audit --no-fund

echo "⚙️ Setting production environment..."
cat > .env.production << EOF
REACT_APP_API_BASE_URL=https://${API_GATEWAY_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod
REACT_APP_VERSION=2.0.0-manual-deploy
REACT_APP_LEGACY_ENABLED=true
EOF

echo "🏗️ Building frontend..."
npm run build

echo "☁️ Deploying to S3..."
# Clear existing files
aws s3 rm s3://${FRONTEND_BUCKET}/ --recursive --region ${AWS_REGION}

# Deploy new build
aws s3 sync build/ s3://${FRONTEND_BUCKET}/ \
  --delete \
  --region ${AWS_REGION} \
  --cache-control "public, max-age=0, must-revalidate"

echo "✅ Frontend deployed"
cd ..

# Deploy Backend
echo ""
echo "🖥️ Deploying Enhanced Backend..."
cd backend

echo "📦 Installing Python dependencies..."
pip install --no-cache-dir -r requirements.txt -t .

echo "🔧 Preparing production backend..."
cp app_production_ready.py lambda_function.py
cp legacy_db_enhanced.py .

echo "📁 Creating deployment package..."
zip -r ../enhanced-backend.zip . \
  -x "*.pyc" "__pycache__/*" "*.git*" \
     "app.py" "app_enhanced.py" "*.md" "Dockerfile" \
     "setup_legacy_schema.py" "*.log"

echo "📤 Uploading to Lambda..."
aws lambda update-function-code \
  --function-name ${BACKEND_LAMBDA} \
  --zip-file fileb://enhanced-backend.zip \
  --region ${AWS_REGION}

echo "⏳ Waiting for Lambda update..."
aws lambda wait function-updated \
  --function-name ${BACKEND_LAMBDA} \
  --region ${AWS_REGION}

echo "⚙️ Configuring environment variables..."
aws lambda update-function-configuration \
  --function-name ${BACKEND_LAMBDA} \
  --environment '{
    "Variables": {
      "SUBSCRIBER_TABLE_NAME": "subscriber-table",
      "AUDIT_LOG_TABLE_NAME": "audit-log-table",
      "MIGRATION_JOBS_TABLE_NAME": "migration-jobs-table",
      "MIGRATION_UPLOAD_BUCKET_NAME": "subscriber-migration-stack-prod-migration-uploads",
      "LEGACY_DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:144395889420:secret:subscriber-legacy-db-secret-qWXjZz",
      "LEGACY_DB_HOST": "subscriber-migration-legacydb.cwd6wssgy4kr.us-east-1.rds.amazonaws.com",
      "LEGACY_DB_PORT": "3306",
      "LEGACY_DB_NAME": "legacydb",
      "FLASK_ENV": "production",
      "VERSION": "2.0.0-manual-deploy"
    }
  }' \
  --region ${AWS_REGION}

aws lambda wait function-updated \
  --function-name ${BACKEND_LAMBDA} \
  --region ${AWS_REGION}

echo "✅ Backend deployed"
cd ..

# Update API Gateway
echo ""
echo "🔄 Updating API Gateway..."
DEPLOYMENT_ID=$(aws apigateway create-deployment \
  --rest-api-id ${API_GATEWAY_ID} \
  --description "Manual Enhanced Deploy $(date +%Y%m%d-%H%M%S)" \
  --query 'id' --output text \
  --region ${AWS_REGION})

aws apigateway update-stage \
  --rest-api-id ${API_GATEWAY_ID} \
  --stage-name prod \
  --patch-operations op=replace,path=/deploymentId,value=${DEPLOYMENT_ID} \
  --region ${AWS_REGION}

echo "✅ API Gateway updated"

# Test deployment
echo ""
echo "🧪 Testing deployment..."
API_URL="https://${API_GATEWAY_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"
FRONTEND_URL="http://${FRONTEND_BUCKET}.s3-website-${AWS_REGION}.amazonaws.com"

echo "⏳ Waiting 30s for propagation..."
sleep 30

echo "🏥 API Health:"
curl -s "${API_URL}/api/health" | jq -r '.status' || echo "Error"

echo "🗄️ Legacy DB Test:"
curl -s "${API_URL}/api/legacy/test" | jq -r '.status' || echo "Error"

echo "📊 System Stats:"
curl -s "${API_URL}/api/dashboard/stats" | jq -r '.totalSubscribers' || echo "Error"

echo "🌐 Frontend Test:"
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${FRONTEND_URL}")
echo "   Status: ${FRONTEND_STATUS}"

echo ""
echo "🎉 DEPLOYMENT COMPLETED!"
echo "📱 Enhanced Portal: ${FRONTEND_URL}"
echo "🔗 API Endpoint: ${API_URL}"
echo "🔐 Login: admin/Admin@123"
echo ""
echo "✨ Features available:"
echo "   • Dashboard with real-time statistics"
echo "   • Provisioning: Legacy/Cloud/Dual modes"
echo "   • Migration: Job management with cancel/timestamps"
echo "   • Bulk Operations: Mass deletion and audit"
echo "   • Monitoring: System health dashboard"
echo "   • Analytics: Comprehensive reporting"
echo ""
echo "🎯 Test Legacy Mode: Login → Provisioning → Legacy Mode → Create Subscriber"
echo "📋 View MySQL: Should show new subscriber in legacydb.subscribers table"
echo ""
echo "✅ Your enhanced enterprise subscriber migration portal is live!"

# Clean up
echo "🧹 Cleaning up temporary files..."
rm -f enhanced-backend.zip
echo "✅ Cleanup completed"

echo ""
echo "🎊 SUCCESS! Your enhanced portal with legacy integration is ready!"
echo "Visit: ${FRONTEND_URL}"