from flask import Flask, jsonify, request
from auth import init_jwt
from users import user_bp
from subscriber import prov_bp, add_subscriber_from_spml
from network import net_bp
from migration import mig_bp
from monitoring import mon_bp
from reporting import rep_bp
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET','dev-secret')
init_jwt(app)

app.register_blueprint(user_bp, url_prefix='/users')
app.register_blueprint(prov_bp, url_prefix='/provision')
# ... (register other blueprints) ...

@app.route('/provision/subscriber/spml', methods=['POST'])
def provision_spml():
    try:
        result = add_subscriber_from_spml(request.data, 'admin')
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/health')
def health(): return jsonify(status='OK'), 200

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)
