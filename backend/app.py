import serverless_wsgi # NEW IMPORT
from flask import Flask, jsonify, request
from flask_cors import CORS
from auth import init_jwt
from users import user_bp
from subscriber import prov_bp
from migration import mig_bp
from audit import log_audit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET', 'devsecret123')

# FIX 1: Allow all origins to resolve CORS issue in API Gateway environment
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

init_jwt(app)

# FIX 2: Register blueprints at the root path (e.g., /users, /provision) 
# The API Gateway handles the /prod/ prefix. We must rely on the full path /users/login being matched.
app.register_blueprint(user_bp, url_prefix='/users')
app.register_blueprint(prov_bp, url_prefix='/provision')
app.register_blueprint(mig_bp, url_prefix='/migration')

# FIX 3: Clean up custom routes by removing the now-redundant /api prefix
@app.route('/provision/spml', methods=['POST'])
def provision_spml_endpoint():
    return prov_bp.add_spml_subscriber()

@app.route('/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

# FIX 4: Add the mandatory handler function for AWS Lambda
def lambda_handler(event, context):
    """Entry point for AWS Lambda."""
    return serverless_wsgi.handle_request(app, event, context)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
