from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required
from Models.Models import UserApiKey
from Crud.userCrud import UserCRUD
from Crud.apiKeyCrud import ApiKeyCRUD
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_key_api = Blueprint('api_key_api', __name__, url_prefix='/api/users')

# JWT decorators are imported from user_routes
from Routes.userRoutes import jwt_auth_required, admin_required

# ===== API KEY ROUTES =====
@api_key_api.route('/<int:user_id>/keys', methods=['POST'])
@jwt_auth_required
def create_api_key(user_id):
    """Create a new API key for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            logger.warning(f"User {g.current_user.id} attempted to create key for user {user_id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.json
        if not data:
            logger.error("Empty request body")
            return jsonify({'error': 'Request body cannot be empty'}), 400

        name = data.get('name', '')
        expires_in_days = data.get('expires_in_days', None)
        permissions = data.get('permissions', [])

        # Validate name is a string
        if not isinstance(name, str):
            logger.error("Key name must be a string")
            return jsonify({'error': 'Key name must be a string'}), 400

        # Manual validation
        if len(name) > 100:
            logger.error("Key name too long")
            return jsonify({'error': 'Key name must be 100 characters or less'}), 400
        if expires_in_days and (not isinstance(expires_in_days, int) or expires_in_days <= 0):
            logger.error("Invalid expires_in_days")
            return jsonify({'error': 'Expires in days must be a positive integer'}), 400
        if not isinstance(permissions, list) or not all(isinstance(p, int) for p in permissions):
            logger.error("Invalid permissions format")
            return jsonify({'error': 'Permissions must be a list of integers'}), 400

        api_key = ApiKeyCRUD.create_api_key(user_id, name, expires_in_days, permissions)
        if not api_key:
            logger.error("Failed to create API key")
            return jsonify({'error': 'Failed to create API key'}), 500

        response = {
            'id': api_key.id,
            'user_id': api_key.user_id,
            'api_key': api_key.api_key,
            'name': api_key.name,
            'created_at': api_key.created_at.isoformat(),
            'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None,
            'is_active': api_key.is_active,
            'permissions': [{'id': p.id, 'api_id': p.api_id, 'created_at': p.created_at.isoformat()} for p in api_key.permissions]
        }
        logger.info(f"Created API key {api_key.id} for user {user_id}")
        return jsonify(response), 201
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@api_key_api.route('/<int:user_id>/keys', methods=['GET'])
@jwt_auth_required
def get_user_api_keys(user_id):
    """Get all API keys for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            logger.warning(f"User {g.current_user.id} attempted to view keys for user {user_id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        keys = ApiKeyCRUD.get_user_api_keys(user_id)
        response = [{
            'id': key.id,
            'user_id': key.user_id,
            'api_key': key.api_key,
            'name': key.name,
            'created_at': key.created_at.isoformat(),
            'expires_at': key.expires_at.isoformat() if key.expires_at else None,
            'is_active': key.is_active,
            'permissions': [{'id': p.id, 'api_id': p.api_id, 'created_at': p.created_at.isoformat()} for p in key.permissions]
        } for key in keys]
        logger.info(f"Retrieved {len(keys)} API keys for user {user_id}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting API keys for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500