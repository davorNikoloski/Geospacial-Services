from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import time
import logging
from Config.Config import app
from flask import Blueprint
from Utils.usageTracker import track_usage

# Import directions service functions
from Services.DirectionsServices import (
    get_route_directions,
    get_simple_route,
    validate_transport_mode
)

# Import matrix service functions for PDP
from Services.MatrixServices import calculate_optimal_route

# === DIRECTIONS ROUTES ===
directions_routes = Blueprint('directions', __name__)

# Define API ID (should match what's in your database)
DIRECTIONS_API_ID = 1  # Change this to your actual API ID

@directions_routes.route('/route', methods=['POST'])
@jwt_required()
@track_usage(api_id=DIRECTIONS_API_ID, endpoint_name='calculate_route')
def calculate_route():
    """
    Calculate route with multiple waypoints and optional optimization
    Request body: {
        "waypoints": [
            {"lat": 41.1230977, "lng": 20.8016481},
            {"lat": 41.9981, "lng": 21.4325},
            {"lat": 41.9981, "lng": 21.4654}
        ],
        "transport_mode": "driving",  // Optional: driving, foot, bike (default: driving)
        "optimize_route": false,      // Optional: whether to optimize waypoint order
        "use_osmnx_fallback": false,  // Optional: use OSMnx if OSRM fails
        "route_type": "shortest"      // Optional: for optimization
    }
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        if not data or 'waypoints' not in data:
            return jsonify({
                'error': 'Invalid request format. Required field: waypoints',
                'example': {
                    'waypoints': [
                        {'lat': 41.123, 'lng': 20.801},
                        {'lat': 41.234, 'lng': 20.902}
                    ],
                    'transport_mode': 'driving'  # Optional: driving, foot, bike
                }
            }), 400
            
        waypoints = data['waypoints']
        transport_mode = data.get('transport_mode', 'driving')
        
        # Validate waypoints
        if not waypoints or len(waypoints) < 2:
            return jsonify({
                'error': 'At least 2 waypoints are required'
            }), 400
            
        # Validate waypoint structure
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, dict) or 'lat' not in wp or 'lng' not in wp:
                return jsonify({
                    'error': f'Waypoint {i} must have "lat" and "lng" fields',
                    'received': wp
                }), 400
            
            # Validate coordinate values
            try:
                lat = float(wp['lat'])
                lng = float(wp['lng'])
                if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                    return jsonify({
                        'error': f'Waypoint {i} has invalid coordinates. Lat: [-90,90], Lng: [-180,180]',
                        'received': {'lat': lat, 'lng': lng}
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'error': f'Waypoint {i} coordinates must be numeric',
                    'received': wp
                }), 400
        
        # Validate transport mode
        try:
            validated_mode = validate_transport_mode(transport_mode)
            data['transport_mode'] = validated_mode
        except ValueError as e:
            return jsonify({
                'error': str(e),
                'supported_modes': ['driving', 'foot', 'bike'],
                'aliases': {
                    'driving': ['car', 'drive', 'auto'],
                    'foot': ['walk', 'walking', 'pedestrian'],
                    'bike': ['cycle', 'cycling', 'bicycle']
                }
            }), 400
        
        # Get route calculation result
        result = get_route_directions(data)
        
        if result.get('status') == 'error':
            return jsonify(result), 400
            
        # Add API processing time to response
        result['api_processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Directions API error: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}',
            'api_processing_time_seconds': time.time() - start_total
        }), 500

@directions_routes.route('/route_pdp', methods=['POST'])
@jwt_required()
@track_usage(api_id=DIRECTIONS_API_ID, endpoint_name='calculate_route_pdp')
def calculate_route_pdp():
    """
    Calculate route for Pickup Delivery Problem (PDP)
    Request body: {
        "current_location": {
            "latitude": 41.1230977,
            "longitude": 20.8016481
        },
        "locations": [
            {
                "latitude": 41.9981,
                "longitude": 21.4325,
                "type": "pickup",
                "location_id": "pickup_1",
                "package_id": "pkg_001"  // Optional
            },
            {
                "latitude": 41.9981,
                "longitude": 21.4654,
                "type": "delivery",
                "location_id": "delivery_1",
                "package_id": "pkg_001"  // Optional
            }
        ],
        "transport_mode": "driving"  // Optional: driving, foot, bike (default: driving)
    }
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request structure
        required_fields = ['current_location', 'locations']
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format. Required fields: current_location, locations',
                'example': {
                    'current_location': {'latitude': 41.123, 'longitude': 20.801},
                    'locations': [
                        {
                            'latitude': 41.234,
                            'longitude': 20.902,
                            'type': 'pickup',
                            'location_id': 'pickup_1',
                            'package_id': 'pkg_001'
                        },
                        {
                            'latitude': 41.345,
                            'longitude': 21.003,
                            'type': 'delivery',
                            'location_id': 'delivery_1',
                            'package_id': 'pkg_001'
                        }
                    ],
                    'transport_mode': 'driving'
                }
            }), 400

        current_location = data['current_location']
        locations = data['locations']
        transport_mode = data.get('transport_mode', 'driving')

        # Validate current_location
        if not isinstance(current_location, dict) or 'latitude' not in current_location or 'longitude' not in current_location:
            return jsonify({
                'error': 'current_location must contain latitude and longitude fields',
                'received': current_location
            }), 400

        # Validate current_location coordinates
        try:
            curr_lat = float(current_location['latitude'])
            curr_lng = float(current_location['longitude'])
            if not (-90 <= curr_lat <= 90) or not (-180 <= curr_lng <= 180):
                return jsonify({
                    'error': 'current_location has invalid coordinates. Lat: [-90,90], Lng: [-180,180]',
                    'received': {'latitude': curr_lat, 'longitude': curr_lng}
                }), 400
        except (ValueError, TypeError):
            return jsonify({
                'error': 'current_location coordinates must be numeric',
                'received': current_location
            }), 400

        # Validate locations array
        if not locations or len(locations) < 2:
            return jsonify({
                'error': 'At least 2 locations (pickup and delivery pairs) are required for PDP'
            }), 400

        # Validate each location in PDP mode
        valid_types = ['pickup', 'delivery']
        for i, loc in enumerate(locations):
            # Check required fields
            required_loc_fields = ['latitude', 'longitude', 'type', 'location_id']
            if not all(field in loc for field in required_loc_fields):
                return jsonify({
                    'error': f'Location {i} must contain: latitude, longitude, type, location_id',
                    'received': loc,
                    'missing_fields': [field for field in required_loc_fields if field not in loc]
                }), 400
            
            # Validate coordinates
            try:
                lat = float(loc['latitude'])
                lng = float(loc['longitude'])
                if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                    return jsonify({
                        'error': f'Location {i} has invalid coordinates. Lat: [-90,90], Lng: [-180,180]',
                        'received': {'latitude': lat, 'longitude': lng}
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'error': f'Location {i} coordinates must be numeric',
                    'received': {'latitude': loc.get('latitude'), 'longitude': loc.get('longitude')}
                }), 400
            
            # Validate type
            if loc['type'] not in valid_types:
                return jsonify({
                    'error': f'Location {i} has invalid type. Must be one of: {valid_types}',
                    'received': loc['type']
                }), 400
            
            # Validate location_id
            if not isinstance(loc['location_id'], (str, int)) or not str(loc['location_id']).strip():
                return jsonify({
                    'error': f'Location {i} must have valid location_id (non-empty string or number)',
                    'received': loc.get('location_id')
                }), 400

        # Validate transport mode
        try:
            validated_mode = validate_transport_mode(transport_mode)
        except ValueError as e:
            return jsonify({
                'error': str(e),
                'supported_modes': ['driving', 'foot', 'bike'],
                'aliases': {
                    'driving': ['car', 'drive', 'auto'],
                    'foot': ['walk', 'walking', 'pedestrian'],
                    'bike': ['cycle', 'cycling', 'bicycle']
                }
            }), 400

        # Check for pickup-delivery pairs (basic validation)
        pickup_count = sum(1 for loc in locations if loc['type'] == 'pickup')
        delivery_count = sum(1 for loc in locations if loc['type'] == 'delivery')
        
        if pickup_count == 0:
            return jsonify({
                'error': 'At least one pickup location is required for PDP'
            }), 400
        
        if delivery_count == 0:
            return jsonify({
                'error': 'At least one delivery location is required for PDP'
            }), 400

        # Prepare data for matrix calculation
        matrix_request_data = {
            'locations': locations,
            'pdp': True,  # Enable PDP mode
            'current_location': current_location
        }

        # Prepare locations for matrix calculation (including current location)
        matrix_locations = []
        
        # Add current location
        matrix_locations.append({
            'id': 'current',
            'lat': current_location['latitude'],
            'lng': current_location['longitude'],
            'type': 'current'
        })
        
        # Add all other locations
        for loc in locations:
            matrix_locations.append({
                'id': loc['location_id'],
                'lat': loc['latitude'],
                'lng': loc['longitude'],
                'type': loc['type'],
                'package_id': loc.get('package_id')
            })

        # Step 1: Calculate optimal route order using matrix calculation
        optimal_result = calculate_optimal_route(matrix_locations)

        if not optimal_result or 'error' in optimal_result:
            return jsonify({
                'status': 'error',
                'message': optimal_result.get('error', 'Failed to calculate optimal PDP route'),
                'transport_mode': validated_mode,
                'api_processing_time_seconds': time.time() - start_total
            }), 500

        # Step 2: Extract optimized waypoints for directions calculation
        optimized_coordinates = optimal_result.get('optimal_route_coordinates', [])
        
        if not optimized_coordinates:
            return jsonify({
                'status': 'error',
                'message': 'No optimized route coordinates returned from matrix calculation',
                'transport_mode': validated_mode,
                'api_processing_time_seconds': time.time() - start_total
            }), 500

        # Convert coordinates to waypoints format for directions API
        waypoints = [{'lat': coord[0], 'lng': coord[1]} for coord in optimized_coordinates]
        
        # Prepare directions request data
        directions_data = {
            'waypoints': waypoints,
            'transport_mode': validated_mode,
            'optimize_route': False,  # Already optimized by matrix calculation
            'use_osmnx_fallback': True  # Enable fallback for better reliability
        }

        # Step 3: Get detailed route directions
        directions_result = get_route_directions(directions_data)
        
        if directions_result.get('status') == 'error':
            # If directions fail, still return the matrix optimization result
            enhanced_result = {
                'status': 'partial_success',
                'route_type': 'pdp',
                'transport_mode': validated_mode,
                'current_location': current_location,
                'pickup_count': pickup_count,
                'delivery_count': delivery_count,
                'total_locations': len(locations),
                'matrix_calculation': optimal_result,
                'directions_error': directions_result.get('message', 'Directions calculation failed'),
                'waypoints': waypoints,
                'api_processing_time_seconds': time.time() - start_total
            }
        else:
            # Combine matrix optimization with detailed directions
            enhanced_result = {
                'status': 'success',
                'route_type': 'pdp',
                'transport_mode': validated_mode,
                'current_location': current_location,
                'pickup_count': pickup_count,
                'delivery_count': delivery_count,
                'total_locations': len(locations),
                
                # Matrix calculation results (optimization)
                'optimization': {
                    'optimal_route': optimal_result.get('optimal_route', []),
                    'optimal_route_coordinates': optimal_result.get('optimal_route_coordinates', []),
                    'minimum_distance_km': optimal_result.get('minimum_distance_km', 0),
                    'estimated_travel_time_seconds': optimal_result.get('estimated_travel_time_seconds', 0),
                    'estimated_travel_time': optimal_result.get('estimated_travel_time', '0s')
                },
                
                # Detailed directions results
                'directions': {
                    'source': directions_result.get('source', 'unknown'),
                    'distance': directions_result.get('distance', 0),
                    'duration': directions_result.get('duration', 0),
                    'duration_str': directions_result.get('duration_str', '0s'),
                    'steps': directions_result.get('steps', []),
                    'geometry': directions_result.get('geometry', []),
                    'decoded_polyline': directions_result.get('decoded_polyline', []),
                    'polyline': directions_result.get('polyline', ''),
                    'waypoints': directions_result.get('waypoints', []),
                    'metadata': directions_result.get('metadata', {})
                },
                
                'api_processing_time_seconds': time.time() - start_total
            }

        return jsonify(enhanced_result), 200

    except Exception as e:
        logging.error(f"PDP Directions API error: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}',
            'route_type': 'pdp',
            'transport_mode': data.get('transport_mode', 'unknown'),
            'api_processing_time_seconds': time.time() - start_total
        }), 500

@directions_routes.route('/simple', methods=['POST'])
@jwt_required()
@track_usage(api_id=DIRECTIONS_API_ID, endpoint_name='calculate_simple_route')
def calculate_simple_route():
    """
    Calculate a simple route between origin and destination
    Request body: {
        "origin": {"lat": 41.1230977, "lng": 20.8016481},
        "destination": {"lat": 41.9981, "lng": 21.4325},
        "transport_mode": "driving",  // Optional: driving, foot, bike (default: driving)
        "alternatives": false         // Optional: return alternative routes
    }
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        # Validate request
        required_fields = ['origin', 'destination']
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Invalid request format. Required fields: origin, destination',
                'example': {
                    'origin': {'lat': 41.123, 'lng': 20.801},
                    'destination': {'lat': 41.234, 'lng': 20.902},
                    'transport_mode': 'driving'  # Optional: driving, foot, bike
                }
            }), 400
        
        origin = data['origin']
        destination = data['destination']
        transport_mode = data.get('transport_mode', 'driving')
        alternatives = data.get('alternatives', False)
        
        # Validate origin and destination structure
        for field_name, location in [('origin', origin), ('destination', destination)]:
            if not isinstance(location, dict) or 'lat' not in location or 'lng' not in location:
                return jsonify({
                    'error': f'{field_name} must have "lat" and "lng" fields',
                    'received': location
                }), 400
            
            # Validate coordinate values
            try:
                lat = float(location['lat'])
                lng = float(location['lng'])
                if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                    return jsonify({
                        'error': f'{field_name} has invalid coordinates. Lat: [-90,90], Lng: [-180,180]',
                        'received': {'lat': lat, 'lng': lng}
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'error': f'{field_name} coordinates must be numeric',
                    'received': location
                }), 400
        
        # Validate transport mode
        try:
            validated_mode = validate_transport_mode(transport_mode)
        except ValueError as e:
            return jsonify({
                'error': str(e),
                'supported_modes': ['driving', 'foot', 'bike'],
                'aliases': {
                    'driving': ['car', 'drive', 'auto'],
                    'foot': ['walk', 'walking', 'pedestrian'],
                    'bike': ['cycle', 'cycling', 'bicycle']
                }
            }), 400
        
        # Get simple route calculation result
        result = get_simple_route(origin, destination, validated_mode, alternatives)
        
        if result.get('status') == 'error':
            return jsonify(result), 400
            
        # Add API processing time to response
        result['api_processing_time_seconds'] = time.time() - start_total
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Simple directions API error: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}',
            'api_processing_time_seconds': time.time() - start_total
        }), 500

@directions_routes.route('/modes', methods=['GET'])
@jwt_required()
@track_usage(api_id=DIRECTIONS_API_ID, endpoint_name='get_transport_modes')
def get_transport_modes():
    """
    Get supported transport modes and their configurations
    """
    try:
        from Services.DirectionsServices import OSRM_SERVERS, DEFAULT_SPEEDS_KPH, OSMNX_NETWORK_TYPES
        
        return jsonify({
            'status': 'success',
            'supported_modes': list(OSRM_SERVERS.keys()),
            'mode_details': {
                mode: {
                    'osrm_server': server,
                    'default_speed_kph': DEFAULT_SPEEDS_KPH.get(mode, 0),
                    'osmnx_network_type': OSMNX_NETWORK_TYPES.get(mode, 'unknown')
                }
                for mode, server in OSRM_SERVERS.items()
            },
            'aliases': {
                'driving': ['car', 'drive', 'auto'],
                'foot': ['walk', 'walking', 'pedestrian'],
                'bike': ['cycle', 'cycling', 'bicycle']
            }
        }), 200
    except Exception as e:
        logging.error(f"Transport modes endpoint error: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500

@directions_routes.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for directions service
    """
    try:
        return jsonify({
            'status': 'healthy',
            'service': 'directions',
            'timestamp': time.time(),
            'endpoints': {
                'POST /route': 'Calculate route with multiple waypoints',
                'POST /route_pdp': 'Calculate optimized route for Pickup Delivery Problem',
                'POST /simple': 'Calculate simple route between two points',
                'GET /modes': 'Get supported transport modes',
                'GET /health': 'Health check'
            }
        }), 200
    except Exception as e:
        logging.error(f"Directions health check error: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500