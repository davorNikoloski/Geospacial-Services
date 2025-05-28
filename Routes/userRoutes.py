from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, create_refresh_token, get_jwt
from Models.Models import User, UserApiKey
from Crud.userCrud import UserCRUD
from functools import wraps
from datetime import datetime, timedelta
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_api = Blueprint('user_api', __name__, url_prefix='/api/users')

# ===== JWT DECORATORS =====
def jwt_auth_required(f):
    """Custom JWT decorator that loads current user"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()
        current_user = UserCRUD.get_user_by_id(current_user_id)
        if not current_user:
            logger.warning(f"User {current_user_id} not found in JWT token")
            return jsonify({'error': 'User not found'}), 401
        g.current_user = current_user
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges (works with JWT)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(g.current_user, 'is_admin', False):
            logger.warning(f"Non-admin user {g.current_user.id} attempted admin action")
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ===== AUTHENTICATION ROUTES =====
@user_api.route('/login', methods=['POST'])
def login():
    """User login endpoint that returns JWT tokens"""
    try:
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.json
        if not data.get('username') or not data.get('password'):
            logger.error("Username or password missing")
            return jsonify({'error': 'Username and password required'}), 400

        # Get user by username or email
        user = UserCRUD.get_user_by_username(data['username'])
        if not user:
            user = UserCRUD.get_user_by_email(data['username'])
        
        if not user:
            logger.warning(f"Login attempt with invalid username: {data['username']}")
            return jsonify({'error': 'Invalid credentials'}), 401

        # Verify password
        if not UserCRUD.verify_password(data['password'], user.password):
            logger.warning(f"Login attempt with invalid password for user: {user.username}")
            return jsonify({'error': 'Invalid credentials'}), 401

        user_api_key = UserApiKey.query.filter_by(user_id=user.id, is_active=True).order_by(UserApiKey.created_at.desc()).first()

        # Create JWT tokens (identity must be a string)
        access_token = create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(hours=1),
        additional_claims={
            "username": user.username,
            "is_admin": user.is_admin,
            "api_key_id": user_api_key.id if user_api_key else None
        }
        )
       
        refresh_token = create_refresh_token(
            identity=str(user.id),
            expires_delta=timedelta(days=30)
        )

        logger.info(f"User {user.username} (ID: {user.id}) logged in successfully")
        
        return jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'firstname': user.firstname,
                'lastname': user.lastname,
                'is_admin': user.is_admin
            }
        }), 200
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@user_api.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh JWT access token"""
    try:
        current_user_id = get_jwt_identity()
        user = UserCRUD.get_user_by_id(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 401

        user_api_key = UserApiKey.query.filter_by(user_id=user.id, is_active=True).order_by(UserApiKey.created_at.desc()).first()
        
        access_token = create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(hours=1),
        additional_claims={
            "username": user.username,
            "is_admin": user.is_admin,
            "api_key_id": user_api_key.id if user_api_key else None
        }
        )

        logger.info(f"Access token refreshed for user {user.username}")
        return jsonify({'access_token': access_token}), 200
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@user_api.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout endpoint (for token blacklisting if implemented)"""
    try:
        jti = get_jwt()['jti']  # JWT ID for blacklisting
        current_user_id = get_jwt_identity()
        
        # Here you would typically add the JTI to a blacklist
        # UserCRUD.blacklist_token(jti)
        
        logger.info(f"User {current_user_id} logged out")
        return jsonify({'message': 'Successfully logged out'}), 200
    except Exception as e:
        logger.error(f"Logout error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

# ===== USER ROUTES =====
@user_api.route('', methods=['POST'])
def create_user():
    """Create a new user (public endpoint)"""
    try:
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.json
        required_fields = ['username', 'email', 'password', 'firstname', 'lastname']
        if not all(field in data for field in required_fields):
            logger.error("Missing required fields")
            return jsonify({'error': 'Missing required fields'}), 400

        # Manual validation
        if not (3 <= len(data['username']) <= 255):
            logger.error("Invalid username length")
            return jsonify({'error': 'Username must be 3-255 characters'}), 400
        if not (1 <= len(data['firstname']) <= 255):
            logger.error("Invalid firstname length")
            return jsonify({'error': 'Firstname must be 1-255 characters'}), 400
        if not (1 <= len(data['lastname']) <= 255):
            logger.error("Invalid lastname length")
            return jsonify({'error': 'Lastname must be 1-255 characters'}), 400
        if len(data['password']) < 8:
            logger.error("Password too short")
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', data['email']):
            logger.error("Invalid email format")
            return jsonify({'error': 'Invalid email format'}), 400
        if 'country' in data and data['country'] and len(data['country']) > 100:
            logger.error("Country name too long")
            return jsonify({'error': 'Country must be 100 characters or less'}), 400

        # Check if username or email already exists
        if UserCRUD.get_user_by_username(data['username']):
            logger.info(f"Username {data['username']} already exists")
            return jsonify({'error': 'Username already exists'}), 409
        if UserCRUD.get_user_by_email(data['email']):
            logger.info(f"Email {data['email']} already exists")
            return jsonify({'error': 'Email already exists'}), 409
        
        # Hash password before storing
        hashed_password = UserCRUD.hash_password(data['password'])
        
        user_data = {
            'username': data['username'],
            'email': data['email'],
            'password': hashed_password,
            'firstname': data['firstname'],
            'lastname': data['lastname'],
            'country': data.get('country')
        }
        user = UserCRUD.create_user(user_data)
        logger.info(f"Created user {user.username} (ID: {user.id})")
        
        response = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'firstname': user.firstname,
            'lastname': user.lastname,
            'country': user.country,
            'created_at': user.created_at.isoformat(),
            'is_admin': user.is_admin
        }
        return jsonify(response), 201
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@user_api.route('/<int:user_id>', methods=['GET'])
@jwt_auth_required
def get_user(user_id):
    """Get user information"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            logger.warning(f"User {g.current_user.id} attempted to access user {user_id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        user = UserCRUD.get_user_by_id(user_id)
        if not user:
            logger.info(f"User {user_id} not found")
            return jsonify({'error': 'User not found'}), 404
        
        response = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'firstname': user.firstname,
            'lastname': user.lastname,
            'country': user.country,
            'created_at': user.created_at.isoformat(),
            'is_admin': user.is_admin
        }
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@user_api.route('/<int:user_id>', methods=['PUT'])
@jwt_auth_required
def update_user(user_id):
    """Update user information"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            logger.warning(f"User {g.current_user.id} attempted to update user {user_id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.json
        allowed_fields = ['username', 'email', 'password', 'firstname', 'lastname', 'country']
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        
        # Manual validation
        if 'username' in update_data and not (3 <= len(update_data['username']) <= 255):
            logger.error("Invalid username length")
            return jsonify({'error': 'Username must be 3-255 characters'}), 400
        if 'firstname' in update_data and not (1 <= len(update_data['firstname']) <= 255):
            logger.error("Invalid firstname length")
            return jsonify({'error': 'Firstname must be 1-255 characters'}), 400
        if 'lastname' in update_data and not (1 <= len(update_data['lastname']) <= 255):
            logger.error("Invalid lastname length")
            return jsonify({'error': 'Lastname must be 1-255 characters'}), 400
        if 'password' in update_data and len(update_data['password']) < 8:
            logger.error("Password too short")
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        if 'email' in update_data and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', update_data['email']):
            logger.error("Invalid email format")
            return jsonify({'error': 'Invalid email format'}), 400
        if 'country' in update_data and update_data['country'] and len(update_data['country']) > 100:
            logger.error("Country name too long")
            return jsonify({'error': 'Country must be 100 characters or less'}), 400

        # Hash password if being updated
        if 'password' in update_data:
            update_data['password'] = UserCRUD.hash_password(update_data['password'])

        # Check for unique constraints (excluding current user)
        if 'username' in update_data:
            existing_user = UserCRUD.get_user_by_username(update_data['username'])
            if existing_user and existing_user.id != user_id:
                logger.info(f"Username {update_data['username']} already exists")
                return jsonify({'error': 'Username already exists'}), 409
        if 'email' in update_data:
            existing_user = UserCRUD.get_user_by_email(update_data['email'])
            if existing_user and existing_user.id != user_id:
                logger.info(f"Email {update_data['email']} already exists")
                return jsonify({'error': 'Email already exists'}), 409
        
        user = UserCRUD.update_user(user_id, update_data)
        if not user:
            logger.info(f"User {user_id} not found")
            return jsonify({'error': 'User not found'}), 404
        
        logger.info(f"Updated user {user_id}")
        response = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'firstname': user.firstname,
            'lastname': user.lastname,
            'country': user.country,
            'created_at': user.created_at.isoformat(),
            'is_admin': user.is_admin
        }
        return jsonify(response)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@user_api.route('/<int:user_id>', methods=['DELETE'])
@jwt_auth_required
@admin_required
def delete_user(user_id):
    """Delete a user (admin only)"""
    try:
        success = UserCRUD.delete_user(user_id)
        if not success:
            logger.info(f"User {user_id} not found")
            return jsonify({'error': 'User not found'}), 404
        
        logger.info(f"Deleted user {user_id}")
        return jsonify({'message': 'User deleted'}), 200
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500