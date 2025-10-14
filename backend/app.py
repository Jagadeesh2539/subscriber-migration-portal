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
CORS(app)
init_jwt(app)

app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(prov_bp, url_prefix='/api/provision')
app.register_blueprint(mig_bp, url_prefix='/api/migration')

@app.route('/api/provision/spml', methods=['POST'])
def provision_spml_endpoint():
    return prov_bp.add_spml_subscriber()

@app.route('/api/health')
def health():
    log_audit('system', 'HEALTH_CHECK', {}, 'SUCCESS')
    return jsonify(status='OK', region=os.getenv('AWS_REGION', 'local')), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
