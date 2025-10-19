from flask import Blueprint, request, jsonify, current_app
from auth import create_token
import hashlib
import os

user_bp = Blueprint('users', __name__)

USERS = {
    # Hashed passwords for test accounts
    'admin': {'password': hashlib.sha256('Admin@123'.encode()).hexdigest(), 'role': 'admin'},
    'operator': {'password': hashlib.sha256('Operator@123'.encode()).hexdigest(), 'role': 'operator'},
    'guest': {'password': hashlib.sha256('Guest@123'.encode()).hexdigest(), 'role': 'guest'}
}

# --- FIX ---
# Added 'OPTIONS' to the methods list
@user_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    # Check if the environment is a development or testing environment
    is_prod = os.getenv('FLASK_ENV', 'development') == 'production'

    if username in USERS:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # --- DEBUG LOGGING ADDED ---
        # This will show up in AWS CloudWatch logs for the Lambda function.
        # It helps verify that the password hashing is working as expected.
        # DO NOT keep this in production permanently.
        if not is_prod: # Only log sensitive data outside of a full production environment check
             print(f"Login attempt: User={username}, Input Hash={pwd_hash}")
             print(f"Stored Hash for {username}: {USERS[username]['password']}")
        # ---------------------------

        if USERS[username]['password'] == pwd_hash:
            token = create_token(username, USERS[username]['role'])
            return jsonify(
                token=token,
                user={'username': username, 'role': USERS[username]['role']}
            ), 200
    
    return jsonify(msg='Invalid credentials'), 401
