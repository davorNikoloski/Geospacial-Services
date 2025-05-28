from flask import jsonify, request, g
from flask_jwt_extended import jwt_required, get_jwt_identity
import time
import logging
from Config.Config import app
from flask import Blueprint
from Utils.usageTracker import track_usage

# Import geocoding service functions
from Services.GeocodingServices import (
    geocode_address,
    reverse_geocode,
    batch_geocode,
    get_location_details
)

# === GEOCODING ROUTES ===
geocoding_routes = Blueprint('geocoding', __name__)

# Define API ID (should match what's in your database)
GEOCODING_API_ID = 3  # Change this to your actual API ID

@geocoding_routes.route('/geocode', methods=['POST'])
@jwt_required()
@track_usage(api_id=GEOCODING_API_ID, endpoint_name='geocode')
def geocode():
    """
    Convert an address to coordinates
    Request body: {"address": "1600 Pennsylvania Avenue, Washington DC"}
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        if not data or 'address' not in data:
            return jsonify({
                'error': 'Invalid request format. Required field: address',
                'details': 'Please provide an address in the request body'
            }), 400
            
        address = data['address'].strip()
        if not address:
            return jsonify({
                'error': 'Empty address',
                'details': 'Address cannot be empty'
            }), 400
            
        # Get geocoding result
        result = geocode_address(address)
        
        if 'error' in result:
            return jsonify(result), 404
            
        # Add processing time to response
        result['processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Geocoding API error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@geocoding_routes.route('/reverse', methods=['POST'])
@jwt_required()
@track_usage(api_id=GEOCODING_API_ID, endpoint_name='reverse_geocode')
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
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format',
                'details': 'Required fields: latitude, longitude'
            }), 400
            
        try:
            lat = float(data['latitude'])
            lng = float(data['longitude'])
        except ValueError:
            return jsonify({
                'error': 'Invalid coordinates',
                'details': 'Latitude and longitude must be valid numbers'
            }), 400
            
        # Validate coordinate ranges
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return jsonify({
                'error': 'Invalid coordinates',
                'details': 'Latitude must be between -90 and 90, longitude between -180 and 180'
            }), 400
            
        # Get reverse geocoding result
        result = reverse_geocode(lat, lng)
        
        if 'error' in result:
            return jsonify(result), 404
            
        # Add processing time to response
        result['processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Reverse geocoding API error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@geocoding_routes.route('/batch', methods=['POST'])
@jwt_required()
@track_usage(api_id=GEOCODING_API_ID, endpoint_name='batch_geocode')
def batch():
    """
    Batch geocode multiple addresses
    Request body: {"addresses": ["Address 1", "Address 2", ...]}
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        if not data or 'addresses' not in data or not isinstance(data['addresses'], list):
            return jsonify({
                'error': 'Invalid request format',
                'details': 'Required field: addresses (list)'
            }), 400
            
        addresses = [addr.strip() for addr in data['addresses'] if addr and addr.strip()]
        
        # Validate addresses
        if not addresses:
            return jsonify({
                'error': 'Empty address list',
                'details': 'No valid addresses provided'
            }), 400
            
        # Limit batch size to prevent abuse
        if len(addresses) > 100:
            return jsonify({
                'error': 'Too many addresses',
                'details': 'Maximum batch size is 100'
            }), 400
            
        # Get batch geocoding results
        results = batch_geocode(addresses)
        
        # Add processing time to response
        response = {
            'results': results,
            'processing_time_seconds': time.time() - start_total,
            'total_addresses': len(addresses),
            'successful_results': len([r for r in results if 'error' not in r])
        }
        return jsonify(response), 200
        
    except Exception as e:
        logging.error(f"Batch geocoding API error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@geocoding_routes.route('/details', methods=['POST'])
@jwt_required()
@track_usage(api_id=GEOCODING_API_ID, endpoint_name='location_details')
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
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format',
                'details': 'Required fields: latitude, longitude'
            }), 400
            
        try:
            lat = float(data['latitude'])
            lng = float(data['longitude'])
        except ValueError:
            return jsonify({
                'error': 'Invalid coordinates',
                'details': 'Latitude and longitude must be valid numbers'
            }), 400
            
        # Validate coordinate ranges
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return jsonify({
                'error': 'Invalid coordinates',
                'details': 'Latitude must be between -90 and 90, longitude between -180 and 180'
            }), 400
            
        # Optional detail level parameter
        detail_level = data.get('detail_level', 'basic')
        if detail_level not in ['basic', 'full']:
            detail_level = 'basic'
            
        # Get location details
        result = get_location_details(lat, lng, detail_level)
        
        if 'error' in result:
            return jsonify(result), 404
            
        # Add processing time to response
        result['processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Location details API error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500