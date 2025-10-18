from flask import Flask, jsonify, request
from flask_cors import CORS
from auth import init_jwt
from users import user_bp
from subscriber import prov_bp
from migration import mig_bp
from audit import log_audit
import os
import serverless_wsgi # <--- NEW IMPORT

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'devsecret123')

# FIX: Set CORS to allow all origins and credentials to fix browser block
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

init_jwt(app)

# FIX: Blueprint registration paths are set relative to the root '/'
# The API Gateway will handle the '/prod' stage prefix.
# The URL will be /prod/api/users/login
app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(prov_bp, url_prefix='/api/provision')
app.register_blueprint(mig_bp, url_prefix='/api/migration')

# FIX: Custom routes also need the correct /api prefix
@app.route('/api/provision/spml', methods=['POST'])
def provision_spml_endpoint():
    return prov_bp.add_spml_subscriber()

@app.route('/api/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

# FIX: Add the mandatory Lambda Handler entry point
def lambda_handler(event, context):
    """Entry point for AWS Lambda via serverless_wsgi"""
    return serverless_wsgi.handle_request(app, event, context)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
