#!/bin/bash

STACK_NAME="subscriber-migration-portal-prod"
API_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

echo "🧪 Testing API Health Endpoints"
echo "API Endpoint: $API_ENDPOINT"
echo "================================"

# Test each endpoint
endpoints=("/" "/health" "/status" "/ping")

for endpoint in "${endpoints[@]}"; do
    echo ""
    echo "Testing $endpoint..."
    response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$API_ENDPOINT$endpoint")
    body=$(echo "$response" | head -n -1)
    http_code=$(echo "$response" | tail -n 1 | cut -d: -f2)
    
    if [ "$http_code" = "200" ]; then
        echo "✅ $endpoint - Success (HTTP $http_code)"
        echo "$body" | python -m json.tool 2>/dev/null || echo "$body"
    else
        echo "❌ $endpoint - Failed (HTTP $http_code)"
        echo "$body"
    fi
done

echo ""
echo "✅ Health check verification complete!"
