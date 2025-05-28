from flask import Flask, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from urllib.parse import quote_plus
import os
import config_secrets

app = Flask(__name__)

db_password = quote_plus(config_secrets.DB_PASSWORD)
db_user = config_secrets.DB_USER
db_host = config_secrets.DB_HOST
db_port = config_secrets.DB_PORT
db_name = config_secrets.DB_NAME


app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_EXTEND_EXISTING"] = True
app.config["ALLOWED_IMAGE_EXTENSIONS"] = ["PNG", "JPG", "GIF", "JPEG"]
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64 MB
app.config["JWT_SECRET_KEY"] = config_secrets.SECRET_KEY
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, 'static', 'images')
app.config["CACHE_FOLDER"] = os.path.join(app.root_path, 'static', 'cache')
app.config["FRONTEND_URL"] = config_secrets.FRONTEND_URL

# Ensure folders exist
for folder in [app.config["UPLOAD_FOLDER"], app.config["CACHE_FOLDER"]]:
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
            print(f"Created directory: {folder}")
        except Exception as e:
            print(f"Could not create directory: {folder}, Error: {e}")

# Init extensions
CORS(app, resources={r"/*": {"origins": "*"}})
db = SQLAlchemy(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)
