#!/usr/bin/env python3
"""
Modular Express Application Setup
Addresses: Separation of concerns, route modularity, middleware organization
"""

import os
import logging
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import modular components
from config.database import init_database_connections
from config.environment import validate_environment, get_config
from middleware.error_handler import setup_error_handlers
from middleware.security import setup_security_middleware
from middleware.logging import setup_request_logging
from routes import register_routes
from utils.logger import get_logger
from health.health_check import register_health_routes
from health.metrics import register_metrics

# Configure application logger
logger = get_logger(__name__)

def create_app(config_name='production'):
    """
    Application factory pattern.
    Creates and configures Flask application with all middleware and routes.
    """
    
    # Validate environment before starting
    validate_environment()
    config = get_config(config_name)
    
    # Initialize Flask app
    app = Flask(__name__)
    app.config.from_object(config)
    
    # Setup security middleware (CORS, rate limiting, headers)
    setup_security_middleware(app)
    
    # Setup request logging and tracing
    setup_request_logging(app)
    
    # Initialize database connections
    init_database_connections(app)
    
    # Register health and metrics endpoints
    register_health_routes(app)
    register_metrics(app)
    
    # Register all application routes
    register_routes(app)
    
    # Setup comprehensive error handling
    setup_error_handlers(app)
    
    logger.info(f"Application created successfully - Config: {config_name}")
    
    return app

# Create application instance
app = create_app()

if __name__ == '__main__':
    # Development server (not used in Lambda)
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting development server on port {port}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )