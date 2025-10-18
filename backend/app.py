# flask_cors is not imported here as CORS headers are handled by the after_request hook
from flask import Flask, jsonify, request, current_app
from users import user_bp
from subscriber import prov_bp
from migration import mig_bp
from audit import log_audit
import os
import serverless_wsgi

# --- Configuration Constants (Must match frontend URL) ---
# NOTE: This must be the HTTP (non-secure) origin since your S3 bucket uses HTTP website hosting.
FRONTEND_ORIGIN = 'http://subscriber-portal-144395889420-us-east-1.s3-website-us-east-1.amazonaws.com'
# -----------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'devsecret123')

# --- CORS & OPTIONS Preflight Fixes ---

# 1. Function to attach ALL necessary CORS headers (used by both hooks)
def add_cors_headers(response):
    # Set explicit origin (required because Access-Control-Allow-Credentials is true)
    response.headers['Access-Control-Allow-Origin'] = FRONTEND_ORIGIN
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# 2. BEFORE REQUEST hook to explicitly handle the browser's OPTIONS preflight check
@app.before_request
def handle_options_requests():
    if request.method == 'OPTIONS':
        # Create a default 200 response and apply the necessary headers
        response = current_app.make_default_options_response()
        return add_cors_headers(response)

# 3. AFTER REQUEST hook to ensure all regular responses (GET/POST) also have headers
@app.after_request
def after_request_func(response):
    return add_cors_headers(response)

# --- Blueprint Registration (Fixed Pathing) ---
# NOTE: Removed the redundant '/api' prefix from all blueprints to align with API Gateway's proxy path.
app.register_blueprint(user_bp, url_prefix='/users')
app.register_blueprint(prov_bp, url_prefix='/provision')
app.register_blueprint(mig_bp, url_prefix='/migration')

# --- Other App Routes (Fixed Pathing) ---
# Also fixed the route for the SPML endpoint.
@app.route('/provision/spml', methods=['POST'])
def provision_spml_endpoint():
    # This calls the method from the provision blueprint, ensuring it runs through the blueprint logic
    return prov_bp.add_spml_subscriber()

@app.route('/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

# --- Lambda Handler (Entry Point Fix) ---
# This is the function AWS Lambda executes (Handler: app.lambda_handler)
def lambda_handler(event, context):
    """Entry point for AWS Lambda."""
    # Use serverless_wsgi to wrap the Flask app in the API Gateway environment
    return serverless_wsgi.handle_request(app, event, context)

if __name__ == '__main__':
    # Local development entry point
    app.run(host='0.0.0.0', port=5000, debug=True)
