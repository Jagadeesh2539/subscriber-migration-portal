import jwt
import datetime
from flask import request, _request_ctx_stack, current_app, jsonify
from functools import wraps

def init_jwt(app):
    @app.before_request
    def load_user():
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if token:
            try:
                payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
                _request_ctx_stack.top.user = payload
            except jwt.ExpiredSignatureError:
                pass
            except jwt.InvalidTokenError:
                pass

def create_token(username, role):
    payload = {
        'sub': username,
        'role': role,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(_request_ctx_stack.top, 'user', None)
            if not user:
                return jsonify(msg='Authentication required'), 401
            if role and user.get('role') != role:
                return jsonify(msg='Insufficient permissions'), 403
            request.environ['user'] = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator
