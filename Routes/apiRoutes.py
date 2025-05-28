from flask import Blueprint, request, jsonify
from Crud.apiCrud import ApiCRUD
from Routes.userRoutes import jwt_auth_required, admin_required
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_management_api = Blueprint('api_management_api', __name__, url_prefix='/api/apis')

# ===== API MANAGEMENT ROUTES (ADMIN ONLY) =====
@api_management_api.route('', methods=['POST'])
@jwt_auth_required
@admin_required
def create_api():
    """Create a new API (admin only)"""
    try:
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.json
        if 'name' not in data or not isinstance(data['name'], str) or not (1 <= len(data['name']) <= 100):
            logger.error("Invalid or missing API name")
            return jsonify({'error': 'Name must be a string between 1 and 100 characters'}), 400
        
        api_data = {
            'name': data['name'],
            'description': data.get('description')
        }
        if api_data['description'] and len(api_data['description']) > 1000:
            logger.error("Description too long")
            return jsonify({'error': 'Description must be 1000 characters or less'}), 400
        
        api = ApiCRUD.create_api(api_data)
        logger.info(f"Created API {api.name} (ID: {api.id})")
        response = {
            'id': api.id,
            'name': api.name,
            'description': api.description,
            'created_at': api.created_at.isoformat()
        }
        return jsonify(response), 201
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@api_management_api.route('', methods=['GET'])
@jwt_auth_required
def get_apis():
    """Get all APIs"""
    try:
        apis = ApiCRUD.get_all_apis()
        response = [{
            'id': api.id,
            'name': api.name,
            'description': api.description,
            'created_at': api.created_at.isoformat()
        } for api in apis]
        logger.info(f"Retrieved {len(apis)} APIs")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting APIs: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500