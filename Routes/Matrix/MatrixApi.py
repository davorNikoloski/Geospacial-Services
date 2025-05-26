from flask import jsonify, request
from flask_jwt_extended import jwt_required
import time
import logging
from Config.Config import app
from flask import Blueprint

# Import all required functions from matrix.py
from Services.MatrixServices import (

    calculate_optimal_route
)

# === MATRIX CALCULATION ROUTES ===
matrix_routes = Blueprint('matrix', __name__)

@matrix_routes.route('/calculate', methods=['POST'])
#@jwt_required()
def calculate_matrix():
    try:
        start_total = time.time()
        data = request.get_json()

        # Validate request structure
        required_fields = ['locations', 'pdp', 'current_location']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format. Required fields: locations, pdp, current_location'
            }), 400

        pdp_mode = data['pdp']
        locations = data['locations']
        current_location = data['current_location']

        # Validate current_location
        if 'latitude' not in current_location or 'longitude' not in current_location:
            return jsonify({
                'error': 'current_location must contain latitude and longitude'
            }), 400

        # Process locations including current_location
        processed_locations = [{
            'id': 'current',
            'lat': current_location['latitude'],
            'lng': current_location['longitude'],
            'type': 'current'
        }]

        if pdp_mode:
            # PDP mode - locations should have type and location_id
            for loc in locations:
                if not all(k in loc for k in ['latitude', 'longitude', 'type', 'location_id']):
                    return jsonify({
                        'error': 'In PDP mode, each location must have latitude, longitude, type, and location_id'
                    }), 400
                
                processed_locations.append({
                    'id': loc['location_id'],
                    'lat': loc['latitude'],
                    'lng': loc['longitude'],
                    'type': loc['type'],
                    'package_id': loc.get('package_id')  # Optional
                })
        else:
            # Non-PDP mode - simple coordinates
            for idx, loc in enumerate(locations):
                if 'latitude' not in loc or 'longitude' not in loc:
                    return jsonify({
                        'error': 'Each location must have latitude and longitude'
                    }), 400
                
                processed_locations.append({
                    'id': f"loc_{idx}",
                    'lat': loc['latitude'],
                    'lng': loc['longitude'],
                    'type': 'waypoint'  # Mark all as waypoints in non-PDP mode
                })

        # Calculate optimal route
        optimal_result = calculate_optimal_route(processed_locations)
        if not optimal_result or 'error' in optimal_result:
            return jsonify({
                'error': optimal_result.get('error', 'Failed to calculate optimal route.')
            }), 500

        # Add processing time to response
        optimal_result['processing_time_seconds'] = time.time() - start_total
        return jsonify(optimal_result), 200

    except Exception as e:
        logging.error(f"Matrix calculation error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

 