from flask import Blueprint, jsonify
from auth import login_required
import random

net_bp = Blueprint('network', __name__)

@net_bp.route('/health', methods=['GET'])
@login_required()
def network_health():
    return jsonify({
        'overall_health': 'GOOD',
        'services': {
            'database': 'UP',
            'cache': 'UP'
        }
    })
