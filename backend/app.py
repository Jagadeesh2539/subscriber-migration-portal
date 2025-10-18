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

# FIX: Configure CORS to explicitly allow the S3 static website origin.
# IMPORTANT: Replace the placeholder below with your *exact* S3 website URL.
# Note: Since the S3 URL uses HTTP, we must include it here.
CORS(app, resources={r"/api/*": {"origins": [
    "http://subscriber-portal-144395889420-us-east-1.s3-website-us-east-1.amazonaws.com",
    "http://localhost:3000" # Keep for local development
]}})

init_jwt(app)

app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(prov_bp, url_prefix='/api/provision')
app.register_blueprint(mig_bp, url_prefix='/api/migration')

@app.route('/api/provision/spml', methods=['POST'])
def provision_spml_endpoint():
    # This function needs login_required decorator to work, but let's leave it for now
    return prov_bp.add_spml_subscriber() 

@app.route('/api/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
