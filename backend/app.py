from flask import Flask, jsonify, request
from flask_cors import CORS
from auth import init_jwt
from users import user_bp
from subscriber import prov_bp
from migration import mig_bp
from audit import log_audit
import os
import serverless_wsgi

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'devsecret123')

# We rely on the @app.after_request hook below for robust CORS,
# but we keep this standard CORS initialization for blueprint integration.
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

init_jwt(app)

app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(prov_bp, url_prefix='/api/provision')
app.register_blueprint(mig_bp, url_prefix='/api/migration')

# FIX: Custom routes with /api prefix
@app.route('/api/provision/spml', methods=['POST'])
def provision_spml_endpoint():
    return prov_bp.add_spml_subscriber()

@app.route('/api/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

# === ULTIMATE CORS FIX: Force headers onto every response ===
@app.after_request
def add_cors_headers(response):
    # This ensures the browser receives the required header, bypassing API Gateway quirks
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# === MANDATORY LAMBDA HANDLER ===
def lambda_handler(event, context):
    """Entry point for AWS Lambda via serverless_wsgi"""
    return serverless_wsgi.handle_request(app, event, context)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
