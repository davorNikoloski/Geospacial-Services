from flask import jsonify, request
from flask_jwt_extended import jwt_required
import time
import logging
from Config.Config import app
from flask import Blueprint

# Import geocoding service functions
from Services.GeocodingServices import (
    geocode_address,
    reverse_geocode,
    batch_geocode,
    get_location_details
)

# === GEOCODING ROUTES ===
geocoding_routes = Blueprint('geocoding', __name__)

@geocoding_routes.route('/geocode', methods=['POST'])
#@jwt_required()
def geocode():
    """
    Convert an address to coordinates
    Request body: {"address": "1600 Pennsylvania Avenue, Washington DC"}
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        if 'address' not in data:
            return jsonify({
                'error': 'Invalid request format. Required field: address'
            }), 400
            
        address = data['address']
        
        # Get geocoding result
        result = geocode_address(address)
        
        if 'error' in result:
            return jsonify(result), 404
            
        # Add processing time to response
        result['processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Geocoding API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@geocoding_routes.route('/reverse', methods=['POST'])
#@jwt_required()
def reverse():
    """
    Convert coordinates to an address
    Request body: {"latitude": 38.8977, "longitude": -77.0365}
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        required_fields = ['latitude', 'longitude']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format. Required fields: latitude, longitude'
            }), 400
            
        # Get reverse geocoding result
        result = reverse_geocode(data['latitude'], data['longitude'])
        
        if 'error' in result:
            return jsonify(result), 404
            
        # Add processing time to response
        result['processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Reverse geocoding API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@geocoding_routes.route('/batch', methods=['POST'])
#@jwt_required()
def batch():
    """
    Batch geocode multiple addresses
    Request body: {"addresses": ["Address 1", "Address 2", ...]}
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        if 'addresses' not in data or not isinstance(data['addresses'], list):
            return jsonify({
                'error': 'Invalid request format. Required field: addresses (list)'
            }), 400
            
        addresses = data['addresses']
        
        # Limit batch size to prevent abuse
        if len(addresses) > 100:
            return jsonify({
                'error': 'Too many addresses. Maximum batch size is 100.'
            }), 400
            
        # Get batch geocoding results
        results = batch_geocode(addresses)
        
        # Add processing time to response
        response = {
            'results': results,
            'processing_time_seconds': time.time() - start_total
        }
        return jsonify(response), 200
        
    except Exception as e:
        logging.error(f"Batch geocoding API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@geocoding_routes.route('/details', methods=['POST'])
#@jwt_required()
def location_details():
    """
    Get detailed location information for coordinates
    Request body: {"latitude": 38.8977, "longitude": -77.0365, "detail_level": "basic"}
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        required_fields = ['latitude', 'longitude']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format. Required fields: latitude, longitude'
            }), 400
            
        # Optional detail level parameter
        detail_level = data.get('detail_level', 'basic')
        if detail_level not in ['basic', 'full']:
            detail_level = 'basic'
            
        # Get location details
        result = get_location_details(data['latitude'], data['longitude'], detail_level)
        
        if 'error' in result:
            return jsonify(result), 404
            
        # Add processing time to response
        result['processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Location details API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500