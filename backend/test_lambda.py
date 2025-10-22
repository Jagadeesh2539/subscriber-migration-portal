import json
from app import lambda_handler

# Test payload
test_event = {
    "httpMethod": "GET",
    "path": "/health",
    "headers": {},
    "queryStringParameters": None,
    "body": None
}

# Test context (minimal)
class TestContext:
    def __init__(self):
        self.function_name = "test"
        self.aws_request_id = "test-123"

try:
    response = lambda_handler(test_event, TestContext())
    print("Lambda Response:", json.dumps(response, indent=2))
except Exception as e:
    print(f"Lambda Error: {e}")
