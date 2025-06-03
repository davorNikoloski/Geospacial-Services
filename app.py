from flask import Flask, request, jsonify, g, Blueprint
from flask_sqlalchemy import SQLAlchemy
from Config.Config import db
import logging
import psutil
import time
import threading
import os
import faulthandler
from flask_cors import CORS  # Add this import
from Routes.userRoutes import user_api
from Routes.apiKeyRoutes import api_key_api
from Routes.apiRoutes import api_management_api
from Routes.usageRoutes import usage_api

from Routes.Matrix.MatrixApi import matrix_routes
from Routes.Geocoding.GeocodingApi import geocoding_routes
from Routes.Isochrone.IsochroneApi import isochrone_routes
from Routes.Directions.DirectionsApi import directions_routes
from urllib.parse import quote_plus
import config_secrets
from flask_jwt_extended import JWTManager


# === LOGGING SETUP ===
LOG_DIR = '/tmp'
os.makedirs(LOG_DIR, exist_ok=True)

faulthandler_log_path = os.path.join(LOG_DIR, 'faulthandler.log')
with open(faulthandler_log_path, 'w') as f:
    faulthandler.enable(file=f)

logging.basicConfig(
    level=logging.DEBUG,
    filename=os.path.join(LOG_DIR, 'app.log'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

def create_app():
    app = Flask(__name__)
    
    # Configure CORS - Add this section
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:4200"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    })
    
    # Configure database
    db_password = quote_plus(config_secrets.DB_PASSWORD)
    db_user = config_secrets.DB_USER
    db_host = config_secrets.DB_HOST
    db_port = config_secrets.DB_PORT
    db_name = config_secrets.DB_NAME

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize SQLAlchemy
    db.init_app(app)

    #JWT
    app.config["JWT_SECRET_KEY"] = config_secrets.SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False  # Add this line

    jwt = JWTManager(app)

    # === REQUEST/RESPONSE LOGGING ===
    @app.before_request
    def log_request_info():
        g.start_time = time.time()
        app.logger.info(f"Request: {request.method} {request.url} Headers: {dict(request.headers)}")
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

    @app.after_request
    def log_response_info(response):
        duration = time.time() - g.start_time
        memory_usage = psutil.Process().memory_info().rss / 1024 ** 2
        app.logger.info(f"Response: {request.method} {request.url} Status: {response.status} Duration: {duration:.3f}s Memory: {memory_usage:.2f}MB")
        
        # Add CORS headers to every response
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:4200')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    # === ERROR HANDLING ===
    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
        response = jsonify(error="Internal Server Error")
        response.status_code = 500
        # Add CORS headers to error responses
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:4200')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

    # === PERIODIC MEMORY LOGGER ===
    def log_memory_usage(interval=60):
        process = psutil.Process()
        while True:
            mem = process.memory_info()
            logging.info(f"Memory Usage: RSS={mem.rss / 1024 ** 2:.2f}MB, VMS={mem.vms / 1024 ** 2:.2f}MB")
            time.sleep(interval)

    threading.Thread(target=log_memory_usage, daemon=True).start()

    # Register blueprints
    app.register_blueprint(user_api)
    app.register_blueprint(api_key_api)
    app.register_blueprint(api_management_api)
    app.register_blueprint(usage_api)
    
    app.register_blueprint(matrix_routes, url_prefix='/api/matrix')
    app.register_blueprint(geocoding_routes, url_prefix='/api/geocoding')
    app.register_blueprint(isochrone_routes, url_prefix='/api/isochrone')
    app.register_blueprint(directions_routes, url_prefix='/api/directions')

    # === DATABASE INITIALIZATION ===
    with app.app_context():
        metadata = db.Model.metadata
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()

        defined_tables = metadata.tables.keys()
        missing_tables = [t for t in defined_tables if t not in existing_tables]

        if missing_tables:
            logging.info(f"Missing tables detected: {missing_tables}. Creating missing tables...")
            try:
                db.create_all()
                logging.info("Tables created successfully.")
            except Exception as e:
                logging.error(f"Error creating tables: {e}")
        else:
            logging.info("All tables exist. No creation needed.")

    return app

if __name__ == "__main__":
    logging.info("Application starting up...")
    app = create_app()
    app.run(host='0.0.0.0', port=8000, debug=True)