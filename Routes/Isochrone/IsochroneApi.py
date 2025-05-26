from flask import jsonify, request
from flask_jwt_extended import jwt_required
import time
import logging
from Config.Config import app
from flask import Blueprint
import json

# Import isochrone service functions
from Services.IsochroneServices import (
    calculate_isochrone,
    convert_polygons_to_geojson,
    get_bounding_box,
    get_stats_for_isochrones
)

# === ISOCHRONE ROUTES ===
isochrone_routes = Blueprint('isochrone', __name__)

@isochrone_routes.route('/calculate', methods=['POST'])
#@jwt_required()
def get_isochrones():
    """
    Calculate isochrones (travel time polygons) from a starting point
    
    Example request:
    {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "travel_times": [5, 10, 15],
        "travel_mode": "drive"
    }
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
            
        # Get optional parameters with defaults
        travel_times = data.get('travel_times', [5, 10, 15])
        travel_mode = data.get('travel_mode', 'drive')
        simplify_tolerance = data.get('simplify_tolerance', 20)
        
        # Validate travel mode
        valid_modes = ['drive', 'walk', 'bike']
        if travel_mode not in valid_modes:
            return jsonify({
                'error': f'Invalid travel mode. Must be one of: {", ".join(valid_modes)}'
            }), 400
            
        # Validate travel times
        if not isinstance(travel_times, list) or not travel_times:
            return jsonify({
                'error': 'travel_times must be a non-empty list of minutes'
            }), 400
            
        if any(not isinstance(t, (int, float)) or t <= 0 or t > 60 for t in travel_times):
            return jsonify({
                'error': 'travel_times must contain positive numbers less than or equal to 60'
            }), 400
            
        # Calculate isochrones
        isochrone_result = calculate_isochrone(
            data['latitude'],
            data['longitude'],
            travel_times=travel_times,
            travel_mode=travel_mode,
            simplify_tolerance=simplify_tolerance
        )
        
        if 'error' in isochrone_result:
            return jsonify(isochrone_result), 500
            
        # Add processing time to response if not already added
        if 'processing_time_seconds' not in isochrone_result:
            isochrone_result['processing_time_seconds'] = time.time() - start_total
            
        return jsonify(isochrone_result), 200
        
    except Exception as e:
        logging.error(f"Isochrone API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@isochrone_routes.route('/geojson', methods=['POST'])
#@jwt_required()
def get_isochrones_geojson():
    """
    Calculate isochrones and return as GeoJSON format for mapping
    
    Example request:
    {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "travel_times": [5, 10, 15],
        "travel_mode": "drive"
    }
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
            
        # Get optional parameters with defaults
        travel_times = data.get('travel_times', [5, 10, 15])
        travel_mode = data.get('travel_mode', 'drive')
        simplify_tolerance = data.get('simplify_tolerance', 20)
        
        # Validate travel mode
        valid_modes = ['drive', 'walk', 'bike']
        if travel_mode not in valid_modes:
            return jsonify({
                'error': f'Invalid travel mode. Must be one of: {", ".join(valid_modes)}'
            }), 400
            
        # Calculate isochrones
        isochrone_result = calculate_isochrone(
            data['latitude'],
            data['longitude'],
            travel_times=travel_times,
            travel_mode=travel_mode,
            simplify_tolerance=simplify_tolerance
        )
        
        if 'error' in isochrone_result:
            return jsonify(isochrone_result), 500
            
        # Convert to GeoJSON
        geojson = convert_polygons_to_geojson(isochrone_result)
        
        if not geojson:
            return jsonify({'error': 'Failed to generate GeoJSON'}), 500
            
        # Add processing time and bounds to response
        geojson['processing_time_seconds'] = time.time() - start_total
        geojson['bounds'] = get_bounding_box(isochrone_result)
        geojson['center'] = isochrone_result['center']
        
        return jsonify(geojson), 200
        
    except Exception as e:
        logging.error(f"Isochrone GeoJSON API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@isochrone_routes.route('/compare', methods=['POST'])
#@jwt_required()
def compare_isochrones():
    """
    Compare isochrones for different travel modes
    
    Example request:
    {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "travel_time": 15,
        "travel_modes": ["drive", "walk", "bike"]
    }
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        required_fields = ['latitude', 'longitude', 'travel_time']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format. Required fields: latitude, longitude, travel_time'
            }), 400
            
        # Get travel modes to compare
        travel_modes = data.get('travel_modes', ['drive', 'walk', 'bike'])
        travel_time = data.get('travel_time', 15)
        simplify_tolerance = data.get('simplify_tolerance', 20)
        
        # Validate travel modes
        valid_modes = ['drive', 'walk', 'bike']
        for mode in travel_modes:
            if mode not in valid_modes:
                return jsonify({
                    'error': f'Invalid travel mode: {mode}. Must be one of: {", ".join(valid_modes)}'
                }), 400
        
        # Calculate isochrones for each mode
        comparison = {
            'center': {'latitude': data['latitude'], 'longitude': data['longitude']},
            'travel_time_minutes': travel_time,
            'comparisons': {}
        }
        
        for mode in travel_modes:
            # Convert single travel_time to a list with one element
            isochrone_result = calculate_isochrone(
                data['latitude'],
                data['longitude'],
                travel_times=[travel_time],  # Pass as a list
                travel_mode=mode,
                simplify_tolerance=simplify_tolerance
            )
            
            if 'error' in isochrone_result:
                comparison['comparisons'][mode] = {'error': isochrone_result['error']}
                continue
                
            if isochrone_result['isochrones']:
                iso = isochrone_result['isochrones'][0]
                comparison['comparisons'][mode] = {
                    'area_km2': iso['area_km2'],
                    'polygon_coordinates': iso['polygon_coordinates']
                }
        
        # Add processing time to response
        comparison['processing_time_seconds'] = time.time() - start_total
        
        return jsonify(comparison), 200
        
    except Exception as e:
        logging.error(f"Isochrone comparison API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@isochrone_routes.route('/stats', methods=['POST'])
#@jwt_required()
def get_isochrone_stats():
    """
    Get detailed statistics about isochrones
    
    Example request:
    {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "travel_times": [5, 10, 15],
        "travel_mode": "drive"
    }
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
            
        # Get optional parameters with defaults
        travel_times = data.get('travel_times', [5, 10, 15])
        travel_mode = data.get('travel_mode', 'drive')
        
        # Calculate isochrones
        isochrone_result = calculate_isochrone(
            data['latitude'],
            data['longitude'],
            travel_times=travel_times,
            travel_mode=travel_mode
        )
        
        if 'error' in isochrone_result:
            return jsonify(isochrone_result), 500
            
        # Get statistics
        stats = get_stats_for_isochrones(isochrone_result)
        
        # Create response
        response = {
            'center': isochrone_result['center'],
            'travel_mode': travel_mode,
            'bounds': get_bounding_box(isochrone_result),
            'statistics': stats,
            'processing_time_seconds': time.time() - start_total
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logging.error(f"Isochrone stats API error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500