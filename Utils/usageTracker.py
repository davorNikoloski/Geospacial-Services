# Utils/usageTracker.py
from functools import wraps
from flask import request, g, Response
from datetime import datetime
import time
import json
from Config.Config import app
from Crud.usageCrud import UsageCRUD
import logging
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, get_jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def track_usage(api_id, endpoint_name):
    """
    Decorator to track API usage and create analytics with API-specific data extraction
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()
            request_size = len(request.data) if request.data else 0
            
            # Try to get request body (JSON data)
            request_body = None
            try:
                if request.is_json:
                    request_body = request.get_json()
            except Exception as e:
                logger.warning(f"Error getting request body: {str(e)}")
            
            # Get user info from JWT token
            try:
                verify_jwt_in_request()  # Verifies the token is valid
                jwt_data = get_jwt()
                user_id = get_jwt_identity()
                api_key_id = jwt_data.get("api_key_id")
            except Exception as e:
                logger.warning(f"Error getting JWT info: {str(e)}")
                user_id = None
                api_key_id = None
            
            # Execute the endpoint function
            response = f(*args, **kwargs)
            
            try:
                # Calculate response metrics
                processing_time = time.time() - start_time
                
                # Handle response types to get status code, response size, and response data
                response_data = None
                if isinstance(response, Response):
                    status_code = response.status_code
                    response_size = len(response.data) if response.data else 0
                    try:
                        response_data = json.loads(response.data.decode('utf-8')) if response.data else None
                    except:
                        response_data = None
                elif isinstance(response, tuple) and len(response) >= 2:
                    response_content, status_code = response[0], response[1]
                    if isinstance(response_content, Response):
                        response_size = len(response_content.data) if response_content.data else 0
                        try:
                            response_data = json.loads(response_content.data.decode('utf-8')) if response_content.data else None
                        except:
                            response_data = None
                    else:
                        response_data = response_content
                        response_size = len(json.dumps(response_content)) if response_content else 0
                else:
                    logger.error(f"Unexpected response type: {type(response)}")
                    status_code = 500
                    response_size = 0
                
                # Prepare base usage data
                usage_data = {
                    'user_id': user_id,
                    'api_id': api_id,
                    'api_key_id': api_key_id,
                    'endpoint': endpoint_name,
                    'response_time': processing_time,
                    'status_code': status_code,
                    'ip_address': request.remote_addr,
                    'request_size': request_size,
                    'response_size': response_size,
                    'user_agent': request.headers.get('User-Agent'),
                    'timestamp': datetime.utcnow()
                }
                
                # Only log usage if we have a user_id
                if user_id is not None:
                    try:
                        # Log the usage
                        usage = UsageCRUD.log_api_usage(usage_data)
                        
                        # Extract API-specific analytics data only for successful responses
                        if status_code < 400:
                            analytics_data = _extract_analytics_data(
                                api_id, endpoint_name, request_body, response_data, 
                                usage.id, user_id, api_id
                            )
                            
                            # Create analytics record
                            if analytics_data:
                                UsageCRUD.create_analytics(analytics_data)
                                logger.info(f"Analytics created for API {api_id}, endpoint {endpoint_name}, user {user_id}")
                        else:
                            logger.info(f"Skipping analytics for failed request (status {status_code})")
                            
                    except Exception as e:
                        logger.error(f"Error tracking API usage: {str(e)}", exc_info=True)
                else:
                    logger.warning("Skipping usage tracking - no user_id available")
                
            except Exception as e:
                logger.error(f"Error in usage tracking wrapper: {str(e)}", exc_info=True)
            
            return response
        return decorated_function
    return decorator


def _extract_analytics_data(api_id, endpoint_name, request_body, response_data, usage_id, user_id, api_id_param):
    """
    Extract analytics data based on API type and endpoint
    """
    analytics_data = {
        'usage_id': usage_id,
        'user_id': user_id,
        'api_id': api_id_param,
        'timestamp': datetime.utcnow(),
        'raw_request': json.dumps(request_body) if request_body else None
    }
    
    try:
        # API ID 1: Routing/Directions API
        if api_id == 1:
            analytics_data.update(_extract_routing_data(request_body, response_data, endpoint_name))
        
        # API ID 2: Matrix API
        elif api_id == 2:
            analytics_data.update(_extract_matrix_data(request_body, response_data, endpoint_name))
        
        # API ID 3: Geocoding API
        elif api_id == 3:
            analytics_data.update(_extract_geocoding_data(request_body, response_data, endpoint_name))
        
        # API ID 4: Isochrone API
        elif api_id == 4:
            analytics_data.update(_extract_isochrone_data(request_body, response_data, endpoint_name))
        
        logger.info(f"Extracted analytics data for API {api_id}: {analytics_data}")
        return analytics_data
        
    except Exception as e:
        logger.error(f"Error extracting analytics data for API {api_id}: {str(e)}", exc_info=True)
        return analytics_data  # Return base data even if extraction fails


def _extract_geocoding_data(request_body, response_data, endpoint_name):
    """Extract data specific to Geocoding API"""
    data = {}
    
    if request_body:
        # Forward geocoding (address to coordinates)
        if 'address' in request_body:
            data['address'] = str(request_body['address'])[:500]  # Limit length
        
        # Reverse geocoding (coordinates to address)
        if 'latitude' in request_body and 'longitude' in request_body:
            data['start_latitude'] = float(request_body['latitude'])
            data['start_longitude'] = float(request_body['longitude'])
    
    if response_data and isinstance(response_data, dict):
        # Extract coordinates from the response (primary location)
        if 'latitude' in response_data and 'longitude' in response_data:
            data['start_latitude'] = float(response_data['latitude'])
            data['start_longitude'] = float(response_data['longitude'])
        elif 'lat' in response_data and 'lon' in response_data:
            data['start_latitude'] = float(response_data['lat'])
            data['start_longitude'] = float(response_data['lon'])
        
        # Extract formatted address
        if 'display_name' in response_data:
            data['formatted_address'] = str(response_data['display_name'])[:500]
        elif 'formatted_address' in response_data:
            data['formatted_address'] = str(response_data['formatted_address'])[:500]
        elif 'address' in response_data:
            data['formatted_address'] = str(response_data['address'])[:500]
        
        # Extract place ID from raw data
        if 'raw' in response_data and isinstance(response_data['raw'], dict):
            raw_data = response_data['raw']
            if 'place_id' in raw_data:
                data['place_id'] = str(raw_data['place_id'])[:255]
            elif 'osm_id' in raw_data:
                data['place_id'] = str(raw_data['osm_id'])[:255]
            
            # Extract location type from raw data
            if 'type' in raw_data:
                data['location_type'] = str(raw_data['type'])[:100]
            elif 'class' in raw_data:
                data['location_type'] = str(raw_data['class'])[:100]
            elif 'addresstype' in raw_data:
                data['location_type'] = str(raw_data['addresstype'])[:100]
        
        # Extract coordinates from nested structures if not already set
        if 'start_latitude' not in data and 'coordinates' in response_data:
            coords = response_data['coordinates']
            if isinstance(coords, dict):
                if 'lat' in coords and 'lng' in coords:
                    data['start_latitude'] = float(coords['lat'])
                    data['start_longitude'] = float(coords['lng'])
                elif 'latitude' in coords and 'longitude' in coords:
                    data['start_latitude'] = float(coords['latitude'])
                    data['start_longitude'] = float(coords['longitude'])
        
        # For batch geocoding, take the first result
        if 'results' in response_data and isinstance(response_data['results'], list) and response_data['results']:
            first_result = response_data['results'][0]
            if isinstance(first_result, dict) and 'error' not in first_result:
                # Recursively extract from first result
                first_data = _extract_geocoding_data({}, first_result, endpoint_name)
                data.update(first_data)
    
    return data


def _extract_matrix_data(request_body, response_data, endpoint_name):
    """Extract data specific to Matrix/Routing API"""
    data = {}
    
    if request_body:
        # Extract current location (start point)
        if 'current_location' in request_body:
            current_loc = request_body['current_location']
            if 'latitude' in current_loc and 'longitude' in current_loc:
                data['start_latitude'] = float(current_loc['latitude'])
                data['start_longitude'] = float(current_loc['longitude'])
        
        # Count waypoints/locations
        if 'locations' in request_body and isinstance(request_body['locations'], list):
            data['waypoints_count'] = len(request_body['locations'])
        
        # Determine route type based on PDP mode
        if 'pdp' in request_body:
            data['route_type'] = 'pickup_delivery' if request_body['pdp'] else 'standard'
    
    if response_data and isinstance(response_data, dict):
        # Extract distance from the response - convert km to meters
        if 'minimum_distance_km' in response_data:
            distance_km = float(response_data['minimum_distance_km'])
            data['distance_meters'] = int(distance_km * 1000)  # Convert km to meters
        
        # Extract duration in seconds
        if 'estimated_travel_time_seconds' in response_data:
            data['duration_seconds'] = int(response_data['estimated_travel_time_seconds'])
        
        # Extract end point from optimal_route_coordinates (last coordinate)
        if 'optimal_route_coordinates' in response_data and isinstance(response_data['optimal_route_coordinates'], list):
            coordinates = response_data['optimal_route_coordinates']
            if coordinates:
                last_coord = coordinates[-1]
                if isinstance(last_coord, list) and len(last_coord) >= 2:
                    data['end_latitude'] = float(last_coord[0])
                    data['end_longitude'] = float(last_coord[1])
        
        # Try to extract polyline or route geometry if available
        if 'optimal_route_coordinates' in response_data:
            # Store the route coordinates as a simplified representation
            coords = response_data['optimal_route_coordinates']
            if coords:
                data['polyline'] = json.dumps(coords)[:2000]  # Limit size
        
        # Fallback: try other possible response structures
        if 'distance_meters' not in data:
            # Look for other distance fields
            route_info = None
            if 'optimal_route' in response_data:
                route_info = response_data
            elif 'route' in response_data:
                route_info = response_data['route']
            elif 'solution' in response_data:
                route_info = response_data['solution']
            
            if route_info and isinstance(route_info, dict):
                # Try various distance field names
                for distance_field in ['total_distance', 'distance', 'total_distance_meters']:
                    if distance_field in route_info:
                        data['distance_meters'] = int(route_info[distance_field])
                        break
                
                # Try various duration field names
                if 'duration_seconds' not in data:
                    for duration_field in ['total_duration', 'duration', 'total_time', 'total_duration_seconds']:
                        if duration_field in route_info:
                            data['duration_seconds'] = int(route_info[duration_field])
                            break
    
    return data


def _extract_routing_data(request_body, response_data, endpoint_name):
    """Extract data specific to Routing/Directions API"""
    data = {}
    
    if request_body:
        # Extract waypoints
        if 'waypoints' in request_body and isinstance(request_body['waypoints'], list):
            waypoints = request_body['waypoints']
            data['waypoints_count'] = len(waypoints)
            
            # Extract start point (first waypoint)
            if waypoints:
                start = waypoints[0]
                if 'lat' in start and 'lng' in start:
                    data['start_latitude'] = float(start['lat'])
                    data['start_longitude'] = float(start['lng'])
                elif 'latitude' in start and 'longitude' in start:
                    data['start_latitude'] = float(start['latitude'])
                    data['start_longitude'] = float(start['longitude'])
                
                # Extract end point (last waypoint)
                if len(waypoints) > 1:
                    end = waypoints[-1]
                    if 'lat' in end and 'lng' in end:
                        data['end_latitude'] = float(end['lat'])
                        data['end_longitude'] = float(end['lng'])
                    elif 'latitude' in end and 'longitude' in end:
                        data['end_latitude'] = float(end['latitude'])
                        data['end_longitude'] = float(end['longitude'])
        
        # Extract transport mode
        if 'transport_mode' in request_body:
            data['route_type'] = str(request_body['transport_mode'])[:50]
        elif 'mode' in request_body:
            data['route_type'] = str(request_body['mode'])[:50]
        elif 'profile' in request_body:
            data['route_type'] = str(request_body['profile'])[:50]
    
    if response_data and isinstance(response_data, dict):
        # Extract route information
        routes = None
        if 'routes' in response_data and isinstance(response_data['routes'], list) and response_data['routes']:
            routes = response_data['routes'][0]  # Take first route
        elif 'route' in response_data:
            routes = response_data['route']
        
        if routes:
            # Extract distance
            if 'distance' in routes:
                data['distance_meters'] = int(routes['distance'])
            elif 'total_distance' in routes:
                data['distance_meters'] = int(routes['total_distance'])
            
            # Extract duration
            if 'duration' in routes:
                data['duration_seconds'] = int(routes['duration'])
            elif 'total_duration' in routes:
                data['duration_seconds'] = int(routes['total_duration'])
            
            # Extract polyline
            if 'polyline' in routes:
                data['polyline'] = str(routes['polyline'])[:2000]
            elif 'geometry' in routes:
                data['polyline'] = str(routes['geometry'])[:2000]
    
    return data


def _extract_isochrone_data(request_body, response_data, endpoint_name):
    """Extract data specific to Isochrone API"""
    data = {}
    
    if request_body:
        # Extract center point
        if 'latitude' in request_body and 'longitude' in request_body:
            data['start_latitude'] = float(request_body['latitude'])
            data['start_longitude'] = float(request_body['longitude'])
        elif 'center' in request_body:
            center = request_body['center']
            if isinstance(center, dict):
                if 'latitude' in center and 'longitude' in center:
                    data['start_latitude'] = float(center['latitude'])
                    data['start_longitude'] = float(center['longitude'])
                elif 'lat' in center and 'lng' in center:
                    data['start_latitude'] = float(center['lat'])
                    data['start_longitude'] = float(center['lng'])
        
        # Extract travel times (stored as waypoints_count for analysis)
        if 'travel_times' in request_body and isinstance(request_body['travel_times'], list):
            data['waypoints_count'] = len(request_body['travel_times'])
            # Use the maximum travel time as duration
            if request_body['travel_times']:
                max_time = max(request_body['travel_times'])
                data['duration_seconds'] = int(max_time * 60)  # Convert minutes to seconds
        
        # Extract travel mode
        if 'travel_mode' in request_body:
            data['route_type'] = str(request_body['travel_mode'])[:50]
        elif 'mode' in request_body:
            data['route_type'] = str(request_body['mode'])[:50]
        elif 'profile' in request_body:
            data['route_type'] = str(request_body['profile'])[:50]
    
    if response_data and isinstance(response_data, dict):
        # Extract isochrone polygon information
        if 'features' in response_data and isinstance(response_data['features'], list):
            # GeoJSON format
            feature_count = len(response_data['features'])
            if not data.get('waypoints_count'):  # Only set if not already set
                data['waypoints_count'] = feature_count
            
            # Extract geometry if available
            if feature_count > 0 and 'geometry' in response_data['features'][0]:
                geometry = response_data['features'][0]['geometry']
                if 'coordinates' in geometry:
                    # Store simplified polygon representation
                    data['polyline'] = json.dumps(geometry)[:2000]  # Limit size
        
        elif 'polygon' in response_data:
            # Simple polygon format
            data['polyline'] = str(response_data['polygon'])[:2000]
    
    return data