from flask import Blueprint, request, jsonify
from auth import create_token
import hashlib

user_bp = Blueprint('users', __name__)

USERS = {
    'admin': {'password': hashlib.sha256('Admin@123'.encode()).hexdigest(), 'role': 'admin'},
    'operator': {'password': hashlib.sha256('Operator@123'.encode()).hexdigest(), 'role': 'operator'},
    'guest': {'password': hashlib.sha256('Guest@123'.encode()).hexdigest(), 'role': 'guest'}
}

@user_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username in USERS:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        if USERS[username]['password'] == pwd_hash:
            token = create_token(username, USERS[username]['role'])
            return jsonify(
                token=token,
                user={'username': username, 'role': USERS[username]['role']}
            ), 200
    
    return jsonify(msg='Invalid credentials'), 401
