from flask import jsonify, request
from flask_jwt_extended import jwt_required
import time
import logging
from Config.Config import app
from flask import Blueprint
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
from functools import wraps
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import optimized isochrone service functions
from Services.IsochroneServices import (
    calculate_isochrone,
    convert_polygons_to_geojson,
    get_bounding_box,
    get_stats_for_isochrones,
    preload_popular_areas,
    cleanup_old_cache,
    graph_cache
)

# Initialize routes blueprint
isochrone_routes = Blueprint('isochrone', __name__)

# Thread pool for parallel processing
executor = ThreadPoolExecutor(max_workers=4)

def async_route(f):
    """Decorator to make route handler async-capable"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def validate_coordinates(lat, lon):
    """Validate latitude and longitude values"""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False, "Coordinates must be numbers"
    if not -90 <= lat <= 90:
        return False, "Latitude must be between -90 and 90"
    if not -180 <= lon <= 180:
        return False, "Longitude must be between -180 and 180"
    return True, ""

def validate_travel_times(travel_times):
    """Validate travel times array"""
    if not isinstance(travel_times, list) or not travel_times:
        return False, "travel_times must be a non-empty list"
    if len(travel_times) > 10:
        return False, "Maximum 10 travel times allowed"
    if any(not isinstance(t, (int, float)) or t <= 0 or t > 120 for t in travel_times):
        return False, "Travel times must be positive numbers ≤ 120 minutes"
    return True, ""

@isochrone_routes.route('/calculate', methods=['POST'])
#@jwt_required()
@async_route
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
        
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate required fields
        required_fields = ['latitude', 'longitude']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
            
        # Extract and validate coordinates
        latitude = data['latitude']
        longitude = data['longitude']
        valid, error_msg = validate_coordinates(latitude, longitude)
        if not valid:
            return jsonify({'error': error_msg}), 400
            
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
        valid, error_msg = validate_travel_times(travel_times)
        if not valid:
            return jsonify({'error': error_msg}), 400
            
        # Validate simplify tolerance
        if not isinstance(simplify_tolerance, (int, float)) or simplify_tolerance < 0:
            return jsonify({'error': 'simplify_tolerance must be a non-negative number'}), 400
            
        # Calculate isochrones
        isochrone_result = calculate_isochrone(
            latitude,
            longitude,
            travel_times=travel_times,
            travel_mode=travel_mode,
            simplify_tolerance=simplify_tolerance
        )
        
        if 'error' in isochrone_result:
            return jsonify(isochrone_result), 500
            
        # Add total processing time
        total_time = time.time() - start_total
        isochrone_result['total_processing_time_seconds'] = round(total_time, 3)
        
        # Add cache info
        isochrone_result['cache_info'] = {
            'memory_graphs': len(graph_cache.memory_cache),
            'cache_hits': 'N/A'  # Could implement hit counter
        }
        
        return jsonify(isochrone_result), 200
        
    except Exception as e:
        logging.error(f"Isochrone API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/geojson', methods=['POST'])
#@jwt_required()
@async_route
def get_isochrones_geojson():
    """
    Calculate isochrones and return as GeoJSON format for mapping
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate required fields
        required_fields = ['latitude', 'longitude']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
            
        # Extract and validate coordinates
        latitude = data['latitude']
        longitude = data['longitude']
        valid, error_msg = validate_coordinates(latitude, longitude)
        if not valid:
            return jsonify({'error': error_msg}), 400
            
        # Get optional parameters with defaults
        travel_times = data.get('travel_times', [5, 10, 15])
        travel_mode = data.get('travel_mode', 'drive')
        simplify_tolerance = data.get('simplify_tolerance', 20)
        
        # Validate parameters
        valid_modes = ['drive', 'walk', 'bike']
        if travel_mode not in valid_modes:
            return jsonify({
                'error': f'Invalid travel mode. Must be one of: {", ".join(valid_modes)}'
            }), 400
            
        valid, error_msg = validate_travel_times(travel_times)
        if not valid:
            return jsonify({'error': error_msg}), 400
            
        # Calculate isochrones
        isochrone_result = calculate_isochrone(
            latitude,
            longitude,
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
            
        # Add metadata
        geojson['processing_time_seconds'] = round(time.time() - start_total, 3)
        geojson['bounds'] = get_bounding_box(isochrone_result)
        geojson['center'] = isochrone_result['center']
        geojson['travel_mode'] = travel_mode
        geojson['graph_info'] = {
            'nodes': isochrone_result.get('graph_nodes', 0),
            'edges': isochrone_result.get('graph_edges', 0)
        }
        
        return jsonify(geojson), 200
        
    except Exception as e:
        logging.error(f"Isochrone GeoJSON API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/compare', methods=['POST'])
#@jwt_required()
@async_route
def compare_isochrones():
    """
    Compare isochrones for different travel modes using parallel processing
    
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
        
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate required fields
        required_fields = ['latitude', 'longitude', 'travel_time']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
            
        # Extract and validate coordinates
        latitude = data['latitude']
        longitude = data['longitude']
        valid, error_msg = validate_coordinates(latitude, longitude)
        if not valid:
            return jsonify({'error': error_msg}), 400
            
        # Get travel modes and time
        travel_modes = data.get('travel_modes', ['drive', 'walk', 'bike'])
        travel_time = data.get('travel_time', 15)
        simplify_tolerance = data.get('simplify_tolerance', 20)
        
        # Validate travel time
        if not isinstance(travel_time, (int, float)) or travel_time <= 0 or travel_time > 120:
            return jsonify({'error': 'travel_time must be a positive number ≤ 120 minutes'}), 400
        
        # Validate travel modes
        valid_modes = ['drive', 'walk', 'bike']
        invalid_modes = [mode for mode in travel_modes if mode not in valid_modes]
        if invalid_modes:
            return jsonify({
                'error': f'Invalid travel modes: {", ".join(invalid_modes)}. Must be: {", ".join(valid_modes)}'
            }), 400
        
        if len(travel_modes) > 3:
            return jsonify({'error': 'Maximum 3 travel modes allowed'}), 400
        
        # Calculate isochrones for each mode in parallel
        def calculate_for_mode(mode):
            return mode, calculate_isochrone(
                latitude,
                longitude,
                travel_times=[travel_time],
                travel_mode=mode,
                simplify_tolerance=simplify_tolerance
            )
        
        # Use thread pool for parallel calculation
        comparison = {
            'center': {'latitude': latitude, 'longitude': longitude},
            'travel_time_minutes': travel_time,
            'comparisons': {},
            'summary': {}
        }
        
        # Execute calculations in parallel
        future_to_mode = {
            executor.submit(calculate_for_mode, mode): mode 
            for mode in travel_modes
        }
        
        for future in as_completed(future_to_mode, timeout=60):
            try:
                mode, isochrone_result = future.result()
                
                if 'error' in isochrone_result:
                    comparison['comparisons'][mode] = {'error': isochrone_result['error']}
                    continue
                    
                if isochrone_result['isochrones']:
                    iso = isochrone_result['isochrones'][0]
                    comparison['comparisons'][mode] = {
                        'area_km2': iso['area_km2'],
                        'polygon_coordinates': iso['polygon_coordinates'],
                        'reachable_nodes': iso.get('reachable_nodes', 0),
                        'processing_time_seconds': isochrone_result.get('processing_time_seconds', 0)
                    }
                else:
                    comparison['comparisons'][mode] = {'error': 'No isochrone generated'}
                    
            except Exception as e:
                mode = future_to_mode[future]
                comparison['comparisons'][mode] = {'error': str(e)}
        
        # Calculate summary statistics
        areas = []
        for mode, data in comparison['comparisons'].items():
            if 'area_km2' in data:
                areas.append((mode, data['area_km2']))
        
        if areas:
            areas.sort(key=lambda x: x[1], reverse=True)
            comparison['summary'] = {
                'largest_area': {'mode': areas[0][0], 'area_km2': areas[0][1]},
                'smallest_area': {'mode': areas[-1][0], 'area_km2': areas[-1][1]},
                'area_ratio_largest_to_smallest': round(areas[0][1] / areas[-1][1], 2) if areas[-1][1] > 0 else None
            }
        
        # Add processing time
        comparison['total_processing_time_seconds'] = round(time.time() - start_total, 3)
        
        return jsonify(comparison), 200
        
    except Exception as e:
        logging.error(f"Isochrone comparison API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/stats', methods=['POST'])
#@jwt_required()
@async_route
def get_isochrone_stats():
    """
    Get detailed statistics about isochrones
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate required fields
        required_fields = ['latitude', 'longitude']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
            
        # Extract and validate coordinates
        latitude = data['latitude']
        longitude = data['longitude']
        valid, error_msg = validate_coordinates(latitude, longitude)
        if not valid:
            return jsonify({'error': error_msg}), 400
            
        # Get optional parameters
        travel_times = data.get('travel_times', [5, 10, 15])
        travel_mode = data.get('travel_mode', 'drive')
        
        # Validate parameters
        valid_modes = ['drive', 'walk', 'bike']
        if travel_mode not in valid_modes:
            return jsonify({
                'error': f'Invalid travel mode. Must be one of: {", ".join(valid_modes)}'
            }), 400
            
        valid, error_msg = validate_travel_times(travel_times)
        if not valid:
            return jsonify({'error': error_msg}), 400
        
        # Calculate isochrones
        isochrone_result = calculate_isochrone(
            latitude,
            longitude,
            travel_times=travel_times,
            travel_mode=travel_mode
        )
        
        if 'error' in isochrone_result:
            return jsonify(isochrone_result), 500
            
        # Get statistics
        stats = get_stats_for_isochrones(isochrone_result)
        
        # Create enhanced response
        response = {
            'center': isochrone_result['center'],
            'travel_mode': travel_mode,
            'bounds': get_bounding_box(isochrone_result),
            'statistics': stats,
            'graph_info': {
                'total_nodes': isochrone_result.get('graph_nodes', 0),
                'total_edges': isochrone_result.get('graph_edges', 0),
                'network_density': round(
                    isochrone_result.get('graph_edges', 0) / max(isochrone_result.get('graph_nodes', 1), 1), 
                    3
                )
            },
            'processing_info': {
                'calculation_time_seconds': isochrone_result.get('processing_time_seconds', 0),
                'total_time_seconds': round(time.time() - start_total, 3)
            }
        }
        
        # Add area growth analysis
        if len(stats) > 1:
            area_growth = []
            for i in range(1, len(stats)):
                prev_area = stats[i-1]['area_km2']
                curr_area = stats[i]['area_km2']
                growth_rate = ((curr_area - prev_area) / prev_area * 100) if prev_area > 0 else 0
                area_growth.append({
                    'from_minutes': stats[i-1]['travel_time_minutes'],
                    'to_minutes': stats[i]['travel_time_minutes'],
                    'area_increase_km2': round(curr_area - prev_area, 2),
                    'growth_rate_percent': round(growth_rate, 1)
                })
            response['area_growth_analysis'] = area_growth
        
        return jsonify(response), 200
        
    except Exception as e:
        logging.error(f"Isochrone stats API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/batch', methods=['POST'])
#@jwt_required()
@async_route
def batch_isochrones():
    """
    Calculate isochrones for multiple locations in parallel
    
    Example request:
    {
        "locations": [
            {"latitude": 40.7128, "longitude": -74.0060, "name": "NYC"},
            {"latitude": 34.0522, "longitude": -118.2437, "name": "LA"}
        ],
        "travel_times": [10, 20],
        "travel_mode": "drive"
    }
    """
    try:
        start_total = time.time()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate locations
        locations = data.get('locations', [])
        if not isinstance(locations, list) or not locations:
            return jsonify({'error': 'locations must be a non-empty list'}), 400
        
        if len(locations) > 10:
            return jsonify({'error': 'Maximum 10 locations allowed'}), 400
        
        # Validate each location
        for i, loc in enumerate(locations):
            if not isinstance(loc, dict):
                return jsonify({'error': f'Location {i} must be an object'}), 400
            if 'latitude' not in loc or 'longitude' not in loc:
                return jsonify({'error': f'Location {i} missing latitude or longitude'}), 400
            
            valid, error_msg = validate_coordinates(loc['latitude'], loc['longitude'])
            if not valid:
                return jsonify({'error': f'Location {i}: {error_msg}'}), 400
        
        # Get common parameters
        travel_times = data.get('travel_times', [5, 10, 15])
        travel_mode = data.get('travel_mode', 'drive')
        
        # Validate parameters
        valid_modes = ['drive', 'walk', 'bike']
        if travel_mode not in valid_modes:
            return jsonify({
                'error': f'Invalid travel mode. Must be one of: {", ".join(valid_modes)}'
            }), 400
            
        valid, error_msg = validate_travel_times(travel_times)
        if not valid:
            return jsonify({'error': error_msg}), 400
        
        # Calculate isochrones for each location in parallel
        def calculate_for_location(loc, index):
            try:
                result = calculate_isochrone(
                    loc['latitude'],
                    loc['longitude'],
                    travel_times=travel_times,
                    travel_mode=travel_mode
                )
                result['location_index'] = index
                result['location_name'] = loc.get('name', f'Location {index}')
                return result
            except Exception as e:
                return {
                    'location_index': index,
                    'location_name': loc.get('name', f'Location {index}'),
                    'error': str(e)
                }
        
        # Execute calculations in parallel
        future_to_location = {
            executor.submit(calculate_for_location, loc, i): i 
            for i, loc in enumerate(locations)
        }
        
        results = []
        for future in as_completed(future_to_location, timeout=120):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                location_index = future_to_location[future]
                results.append({
                    'location_index': location_index,
                    'location_name': locations[location_index].get('name', f'Location {location_index}'),
                    'error': str(e)
                })
        
        # Sort results by location index
        results.sort(key=lambda x: x['location_index'])
        
        # Create response
        response = {
            'travel_mode': travel_mode,
            'travel_times': travel_times,
            'total_locations': len(locations),
            'results': results,
            'total_processing_time_seconds': round(time.time() - start_total, 3)
        }
        
        # Add summary statistics
        successful_results = [r for r in results if 'error' not in r]
        response['summary'] = {
            'successful_calculations': len(successful_results),
            'failed_calculations': len(results) - len(successful_results),
            'average_processing_time': round(
                sum(r.get('processing_time_seconds', 0) for r in successful_results) / max(len(successful_results), 1),
                3
            )
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logging.error(f"Batch isochrone API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/cache/status', methods=['GET'])
#@jwt_required()
def get_cache_status():
    """Get current cache status and statistics"""
    try:
        cache_stats = {
            'memory_cache': {
                'current_graphs': len(graph_cache.memory_cache),
                'max_graphs': graph_cache.max_memory_graphs,
                'cached_keys': list(graph_cache.memory_cache.keys())
            },
            'disk_cache': {
                'cache_folder': graph_cache.cache_folder,
                'cached_files': []
            },
            'background_downloads': {
                'queue_size': graph_cache.download_queue.qsize(),
                'downloads_in_progress': len(graph_cache.download_in_progress)
            }
        }
        
        # Get disk cache info
        try:
            if os.path.exists(graph_cache.cache_folder):
                cache_files = [f for f in os.listdir(graph_cache.cache_folder) if f.endswith('.graphml')]
                cache_stats['disk_cache']['cached_files'] = cache_files
                cache_stats['disk_cache']['total_files'] = len(cache_files)
        except Exception as e:
            cache_stats['disk_cache']['error'] = str(e)
        
        return jsonify(cache_stats), 200
        
    except Exception as e:
        logging.error(f"Cache status API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/cache/clear', methods=['POST'])
#@jwt_required()
def clear_cache():
    """Clear cache (memory and/or disk)"""
    try:
        data = request.get_json() or {}
        clear_memory = data.get('clear_memory', True)
        clear_disk = data.get('clear_disk', False)
        
        result = {'cleared': []}
        
        if clear_memory:
            with graph_cache.lock:
                cleared_count = len(graph_cache.memory_cache)
                graph_cache.memory_cache.clear()
                graph_cache.cache_access_times.clear()
                result['cleared'].append(f'Memory cache ({cleared_count} graphs)')
        
        if clear_disk:
            try:
                cache_files = [f for f in os.listdir(graph_cache.cache_folder) if f.endswith('.graphml')]
                for cache_file in cache_files:
                    os.remove(os.path.join(graph_cache.cache_folder, cache_file))
                result['cleared'].append(f'Disk cache ({len(cache_files)} files)')
            except Exception as e:
                result['disk_clear_error'] = str(e)
        
        return jsonify(result), 200
        
    except Exception as e:
        logging.error(f"Clear cache API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@isochrone_routes.route('/preload', methods=['POST'])
#@jwt_required()
def preload_graphs():
    """Preload graphs for specified locations"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        locations = data.get('locations', [])
        if not locations:
            return jsonify({'error': 'No locations specified'}), 400
        
        if len(locations) > 20:
            return jsonify({'error': 'Maximum 20 locations allowed for preloading'}), 400
        
        travel_modes = data.get('travel_modes', ['drive'])
        distances = data.get('distances', [2000, 5000])  # meters
        
        def preload_location(loc):
            try:
                lat, lon = loc['latitude'], loc['longitude']
                name = loc.get('name', f'{lat},{lon}')
                
                for mode in travel_modes:
                    for distance in distances:
                        graph_cache.get_graph(lat, lon, distance=distance, network_type=mode)
                
                return {'location': name, 'status': 'success'}
            except Exception as e:
                return {'location': name, 'status': 'error', 'error': str(e)}
        
        # Execute preloading in parallel
        future_to_location = {
            executor.submit(preload_location, loc): loc 
            for loc in locations
        }
        
        results = []
        for future in as_completed(future_to_location, timeout=300):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                loc = future_to_location[future]
                results.append({
                    'location': loc.get('name', f"{loc['latitude']},{loc['longitude']}"),
                    'status': 'error',
                    'error': str(e)
                })
        
        return jsonify({
            'preload_results': results,
            'successful': len([r for r in results if r['status'] == 'success']),
            'failed': len([r for r in results if r['status'] == 'error'])
        }), 200
        
    except Exception as e:
        logging.error(f"Preload API error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

# Initialize preloading on startup (call this when your app starts)
def initialize_cache():
    """Initialize cache with popular locations"""
    try:
        preload_popular_areas()
        cleanup_old_cache(max_age_days=30)
        logger.info("Cache initialization completed")
    except Exception as e:
        logger.error(f"Cache initialization error: {e}")

# Call this in your main app initialization
# initialize_cache()