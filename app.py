from Config.Config import app, db
from Models.Models import User 

from Routes.Matrix.MatrixApi import matrix_routes
from Routes.Geocoding.GeocodingApi import geocoding_routes
from Routes.Isochrone.IsochroneApi import isochrone_routes
from Routes.Directions.DirectionsApi import directions_routes

import logging
import psutil
import time
import threading
import os
import faulthandler
from flask import request, jsonify, g, Blueprint

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

# === REQUEST/RESPONSE LOGGING ===
@app.before_request
def log_request_info():
    g.start_time = time.time()
    app.logger.info(f"Request: {request.method} {request.url} Headers: {dict(request.headers)}")

@app.after_request
def log_response_info(response):
    duration = time.time() - g.start_time
    memory_usage = psutil.Process().memory_info().rss / 1024 ** 2
    app.logger.info(f"Response: {request.method} {request.url} Status: {response.status} Duration: {duration:.3f}s Memory: {memory_usage:.2f}MB")
    return response

# === ERROR HANDLING ===
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
    return jsonify(error="Internal Server Error"), 500

# === PERIODIC MEMORY LOGGER ===
def log_memory_usage(interval=60):
    process = psutil.Process()
    while True:
        mem = process.memory_info()
        logging.info(f"Memory Usage: RSS={mem.rss / 1024 ** 2:.2f}MB, VMS={mem.vms / 1024 ** 2:.2f}MB")
        time.sleep(interval)

threading.Thread(target=log_memory_usage, daemon=True).start()

# === ROUTES ===
user_routes = Blueprint('users', __name__)

@user_routes.route('/login', methods=['POST'])
def login():
    return jsonify(message="Login route working"), 200

app.register_blueprint(user_routes)
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


# === RUN APP ===
if __name__ == "__main__":
    logging.info("Application starting up...")
    app.run(host='0.0.0.0', port=8000, debug=True)
