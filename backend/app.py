# flask_cors is not imported here as CORS headers are handled by the after_request hook
from flask import Flask, jsonify, request, current_app
from users import user_bp
from subscriber import prov_bp
from migration import mig_bp
from audit import log_audit
from auth import init_jwt  # <-- 1. IMPORT THE FUNCTION
import os
import serverless_wsgi

# --- Configuration Constants (Must match frontend URL) ---
FRONTEND_ORIGIN = os.getenv('FRONTEND_DOMAIN_URL')
# -----------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'devsecret123')

init_jwt(app)  # <-- 2. INITIALIZE THE JWT HOOK

# --- CORS & OPTIONS Preflight Fixes ---

# 1. Function to attach ALL necessary CORS headers (used by both hooks)
def add_cors_headers(response):
    if FRONTEND_ORIGIN:
        response.headers['Access-Control-Allow-Origin'] = FRONTEND_ORIGIN
        
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# 2. BEFORE REQUEST hook to explicitly handle the browser's OPTIONS preflight check
@app.before_request
def handle_options_requests():
    if request.method == 'OPTIONS':
        response = current_app.make_default_options_response()
        return add_cors_headers(response)

# 3. AFTER REQUEST hook to ensure all regular responses (GET/POST) also have headers
@app.after_request
def after_request_func(response):
    return add_cors_headers(response)

# --- Blueprint Registration (Corrected Pathing) ---
app.register_blueprint(user_bp, url_prefix='/users')
app.register_blueprint(prov_bp, url_prefix='/provision')
app.register_blueprint(mig_bp, url_prefix='/migration')

# --- Other App Routes (Corrected Pathing) ---
@app.route('/provision/spml', methods=['POST', 'OPTIONS'])
def provision_spml_endpoint():
    # This calls the method from the provision blueprint, ensuring it runs through the blueprint logic
    return prov_bp.add_spml_subscriber()

@app.route('/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

# --- Lambda Handler (Entry Point Fix) ---
def lambda_handler(event, context):
    """Entry point for AWS Lambda."""
    return serverless_wsgi.handle_request(app, event, context)

if __name__ == '__main__':
    # Local development entry point
    app.run(host='0.0.0.0', port=5000, debug=True)
