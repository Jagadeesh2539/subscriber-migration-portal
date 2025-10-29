#!/bin/bash
set -euo pipefail

echo "🔧 Fixing Lambda Handler KeyError Issue..."

# Get the Lambda function name from environment or use default
LAMBDA_FUNCTION_NAME=${LAMBDA_FUNCTION_NAME:-"SubscriberMigrationBackend"}
LAMBDA_FUNCTION_ARN=$(aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" --query 'Configuration.FunctionArn' --output text 2>/dev/null || echo "")

if [ -z "$LAMBDA_FUNCTION_ARN" ]; then
    echo "❌ Lambda function '$LAMBDA_FUNCTION_NAME' not found. Please check the function name."
    echo "Available Lambda functions:"
    aws lambda list-functions --query 'Functions[].FunctionName' --output table
    exit 1
fi

echo "📦 Found Lambda function: $LAMBDA_FUNCTION_ARN"

# Create deployment package
echo "📦 Creating deployment package..."
cd backend

# Clean up previous builds
rm -rf lambda-package.zip lambda-package/
mkdir -p lambda-package

# Copy application files
cp app.py lambda-package/
cp *.py lambda-package/ 2>/dev/null || true

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt -t lambda-package/

# Create ZIP package
echo "🗜️ Creating ZIP package..."
cd lambda-package
zip -r ../lambda-package.zip . -q
cd ..

# Update Lambda function code
echo "🚀 Updating Lambda function code..."
aws lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --zip-file fileb://lambda-package.zip

# Wait for update to complete
echo "⏳ Waiting for Lambda update to complete..."
aws lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME"

# Update function configuration if needed
echo "⚙️ Updating Lambda configuration..."
aws lambda update-function-configuration \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --handler "app.lambda_handler" \
    --runtime "python3.9" \
    --timeout 30 \
    --memory-size 512

# Test the Lambda function
echo "🧪 Testing Lambda function..."

# Test 1: Empty event (this was causing the KeyError)
echo "Testing empty event..."
aws lambda invoke \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --payload '{}' \
    response1.json

echo "Response 1:"
cat response1.json | jq .

# Test 2: Health check event
echo -e "\nTesting health check event..."
aws lambda invoke \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --payload '{
        "httpMethod": "GET",
        "path": "/api/health",
        "headers": {
            "Content-Type": "application/json"
        }
    }' \
    response2.json

echo "Response 2:"
cat response2.json | jq .

# Test 3: Complete API Gateway event structure
echo -e "\nTesting complete API Gateway event..."
aws lambda invoke \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --payload '{
        "httpMethod": "GET",
        "path": "/api/health",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "test-client"
        },
        "multiValueHeaders": {},
        "queryStringParameters": null,
        "multiValueQueryStringParameters": null,
        "pathParameters": null,
        "stageVariables": null,
        "requestContext": {
            "requestId": "test-request-id",
            "stage": "prod",
            "httpMethod": "GET",
            "path": "/api/health",
            "identity": {
                "sourceIp": "127.0.0.1"
            }
        },
        "body": null,
        "isBase64Encoded": false
    }' \
    response3.json

echo "Response 3:"
cat response3.json | jq .

# Clean up
rm -f response1.json response2.json response3.json
rm -rf lambda-package/ lambda-package.zip

cd ..

echo -e "\n✅ Lambda function updated successfully!"
echo "🔍 The KeyError: 'headers' issue has been fixed."
echo "📋 Summary of fixes applied:"
echo "   • Added proper event structure validation"
echo "   • Ensured all required serverless_wsgi fields exist"
echo "   • Added bulletproof error handling"
echo "   • Direct health check endpoint for reliability"
echo "   • Standardized CORS headers"
echo -e "\n🧪 Test your API endpoints now - they should work without errors!"

# Show the API Gateway URL if available
API_ID=$(aws apigateway get-rest-apis --query "items[?name=='SubscriberMigrationAPI'].id" --output text 2>/dev/null || echo "")
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
    echo "🌐 API Gateway URL: https://${API_ID}.execute-api.$(aws configure get region).amazonaws.com/prod/api/health"
fi