#!/usr/bin/env python3
import os
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import time
import polyline
import requests
from typing import List, Dict, Tuple, Optional
from Services.MatrixServices import calculate_optimal_route
from flask import Flask
from Config.Config import app

# Configuration
DEFAULT_SPEEDS_KPH = {
    'driving': 50,  # Average driving speed in km/h
    'foot': 5,      # Average walking speed in km/h
    'bike': 15      # Average cycling speed in km/h
}

# OSRM server configuration
OSRM_SERVERS = {
    'driving': "http://localhost:5000",
    'foot': "http://localhost:5001", 
    'bike': "http://localhost:5002"
}

# OSMnx network types mapping
OSMNX_NETWORK_TYPES = {
    'driving': 'drive',
    'foot': 'walk',
    'bike': 'bike'
}

CACHE_FOLDER = "graph_cache"
os.makedirs(CACHE_FOLDER, exist_ok=True)

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

def validate_transport_mode(mode: str) -> str:
    """
    Validate and normalize transport mode
    Args:
        mode: Transport mode string
    Returns:
        Normalized mode string
    Raises:
        ValueError: If mode is invalid
    """
    if not mode:
        return 'driving'  # Default mode
    
    mode = mode.lower().strip()
    
    # Handle alternative names
    mode_aliases = {
        'car': 'driving',
        'drive': 'driving',
        'auto': 'driving',
        'walk': 'foot',
        'walking': 'foot',
        'pedestrian': 'foot',
        'cycle': 'bike',
        'cycling': 'bike',
        'bicycle': 'bike'
    }
    
    normalized_mode = mode_aliases.get(mode, mode)
    
    if normalized_mode not in OSRM_SERVERS:
        raise ValueError(f"Invalid transport mode: '{mode}'. Supported modes: driving, foot, bike")
    
    return normalized_mode

def call_osrm_route(waypoints: List[Tuple[float, float]], transport_mode: str = 'driving', 
                   overview: str = "full", geometries: str = "geojson") -> Dict:
    """
    Call OSRM route service with waypoints
    Args:
        waypoints: List of (lat, lng) coordinates
        transport_mode: Transportation mode (driving, foot, bike)
        overview: OSRM overview parameter (full, simplified, false)
        geometries: OSRM geometries parameter (geojson, polyline, polyline6)
    Returns:
        OSRM route response or error dict
    """
    try:
        # Validate and normalize transport mode
        transport_mode = validate_transport_mode(transport_mode)
        
        # Get the appropriate OSRM server URL
        base_url = OSRM_SERVERS[transport_mode]
        
        # Format waypoints as "lng,lat;lng,lat;..."
        coordinates_str = ";".join([f"{lng},{lat}" for lat, lng in waypoints])
        
        # Build OSRM URL
        url = f"{base_url}/route/v1/{transport_mode}/{coordinates_str}"
        params = {
            "overview": overview,
            "geometries": geometries,
            "steps": "true",
            "annotations": "true"
        }
        
        print(f"OSRM Request URL: {url}")
        print(f"OSRM Parameters: {params}")
        print(f"Transport Mode: {transport_mode}")
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    except requests.RequestException as e:
        print(f"OSRM API error: {e}")
        return {"error": f"OSRM API error: {str(e)}"}
    except Exception as e:
        print(f"Error calling OSRM: {e}")
        return {"error": f"Error calling OSRM: {str(e)}"}

def get_full_route_geometry(graph, optimal_route_coords: List[Tuple[float, float]], 
                          transport_mode: str = 'driving') -> Dict:
    """
    Calculate the complete route geometry between all points in optimal route using OSMnx
    Args:
        graph: The road network graph
        optimal_route_coords: List of (lat, lng) coordinates from matrix calculation
        transport_mode: Transportation mode for speed calculation
    Returns:
        Dictionary containing route geometry and statistics
    """
    full_geometry = []
    steps = []
    total_distance = 0
    total_duration = 0
    
    # Get speed based on transport mode
    speed_kph = DEFAULT_SPEEDS_KPH.get(transport_mode, DEFAULT_SPEEDS_KPH['driving'])
    
    # Find nearest nodes for all points in the optimal route
    nodes = [ox.distance.nearest_nodes(graph, coord[1], coord[0]) for coord in optimal_route_coords]
    
    for i in range(len(nodes) - 1):
        origin_node = nodes[i]
        dest_node = nodes[i + 1]
        origin_coord = optimal_route_coords[i]
        dest_coord = optimal_route_coords[i + 1]
        
        try:
            # Get the precise path between nodes
            path = nx.shortest_path(graph, origin_node, dest_node, weight='length')
            
            # Calculate path statistics
            path_length = sum(graph.edges[u, v, 0].get('length', 0) 
                           for u, v in zip(path[:-1], path[1:]))
            path_duration = path_length / (speed_kph * 1000 / 3600)
            
            # Extract detailed geometry for this segment
            segment_geometry = []
            for u, v in zip(path[:-1], path[1:]):
                edge_data = graph.edges[u, v, 0]
                if 'geometry' in edge_data:
                    segment_geometry.extend(list(edge_data['geometry'].coords))
                else:
                    # If no geometry, use straight line between nodes
                    u_coords = (graph.nodes[u]['x'], graph.nodes[u]['y'])
                    v_coords = (graph.nodes[v]['x'], graph.nodes[v]['y'])
                    segment_geometry.extend([u_coords, v_coords])
            
            # Add to full geometry
            full_geometry.extend(segment_geometry)
            
            # Create step information
            step = {
                'instruction': f"Route segment {i+1} ({transport_mode})",
                'distance': path_length,
                'duration': path_duration,
                'start_location': {'lat': origin_coord[0], 'lng': origin_coord[1]},
                'end_location': {'lat': dest_coord[0], 'lng': dest_coord[1]},
                'path': [(y, x) for x, y in segment_geometry],  # Convert to (lat,lng)
                'transport_mode': transport_mode
            }
            steps.append(step)
            
            # Update totals
            total_distance += path_length
            total_duration += path_duration
            
        except Exception as e:
            print(f"Error calculating path between points {i} and {i+1}: {e}")
            # Fallback to straight line distance
            straight_distance = geodesic(origin_coord, dest_coord).meters
            straight_duration = straight_distance / (speed_kph * 1000 / 3600)
            
            step = {
                'instruction': f"Direct path from point {i} to point {i+1} ({transport_mode})",
                'distance': straight_distance,
                'duration': straight_duration,
                'start_location': {'lat': origin_coord[0], 'lng': origin_coord[1]},
                'end_location': {'lat': dest_coord[0], 'lng': dest_coord[1]},
                'path': [origin_coord, dest_coord],
                'transport_mode': transport_mode
            }
            steps.append(step)
            
            total_distance += straight_distance
            total_duration += straight_duration
            full_geometry.extend([(origin_coord[1], origin_coord[0]), 
                                 (dest_coord[1], dest_coord[0])])
    
    return {
        'full_geometry': full_geometry,
        'steps': steps,
        'total_distance': total_distance,
        'total_duration': total_duration
    }

def get_route_directions(data: Dict) -> Dict:
    """
    Calculate route using OSRM with optional route optimization
    Args:
        data: Dictionary containing route request data with structure:
        {
            "waypoints": [
                {"lat": 41.123, "lng": 20.801},
                {"lat": 41.234, "lng": 20.902},
                ...
            ],
            "transport_mode": "driving",  # Optional: driving, foot, bike
            "optimize_route": false,      # Optional, default false
            "use_osmnx_fallback": false,  # Optional, default false
            "route_type": "shortest"      # Optional for optimization
        }
    Returns:
        Dictionary with complete route information
    """
    print("\n=== Starting Route Calculation ===")
    start_total = time.time()

    try:
        # Validate input data
        if not data or 'waypoints' not in data:
            raise ValueError("Invalid request format. 'waypoints' field is required.")

        waypoints = data['waypoints']
        transport_mode = validate_transport_mode(data.get('transport_mode', 'driving'))
        optimize_route = data.get('optimize_route', False)
        use_osmnx_fallback = data.get('use_osmnx_fallback', False)
        
        if not waypoints or len(waypoints) < 2:
            raise ValueError("At least 2 waypoints are required.")

        # Validate waypoint format
        route_coords = []
        for i, wp in enumerate(waypoints):
            if 'lat' not in wp or 'lng' not in wp:
                raise ValueError(f"Waypoint {i} missing 'lat' or 'lng' field")
            route_coords.append((wp['lat'], wp['lng']))

        print(f"Processing {len(route_coords)} waypoints with transport mode: {transport_mode}")

        # Optionally optimize route order
        if optimize_route:
            print("\n[1/3] Optimizing route order...")
            # Prepare location data for optimal route calculation
            location_data = []
            for i, (lat, lng) in enumerate(route_coords):
                location_data.append({
                    'id': f'waypoint_{i}',
                    'lat': lat,
                    'lng': lng,
                    'type': 'waypoint'
                })

            optimal_result = calculate_optimal_route(location_data, transport_mode)
            if optimal_result and 'optimal_route_coordinates' in optimal_result:
                route_coords = optimal_result['optimal_route_coordinates']
                print(f"Route optimized: {len(route_coords)} points")
            else:
                print("Route optimization failed, using original order")

        # Try OSRM first
        print(f"\n[2/3] Calling OSRM route service for {transport_mode}...")
        osrm_result = call_osrm_route(route_coords, transport_mode)
        
        if 'error' not in osrm_result and 'routes' in osrm_result and osrm_result['routes']:
            # Process OSRM response
            route = osrm_result['routes'][0]
            
            # Extract geometry
            geometry = route.get('geometry', {})
            if geometry.get('type') == 'LineString':
                coordinates = geometry.get('coordinates', [])
                # OSRM returns [lng, lat], convert to [(lat, lng)]
                decoded_polyline = [(lat, lng) for lng, lat in coordinates]
                polyline_encoded = polyline.encode(decoded_polyline)
            else:
                decoded_polyline = route_coords
                polyline_encoded = polyline.encode(decoded_polyline)
            
            # Extract steps
            steps = []
            if 'legs' in route:
                step_counter = 1
                for leg in route['legs']:
                    if 'steps' in leg:
                        for step in leg['steps']:
                            maneuver = step.get('maneuver', {})
                            step_data = {
                                'instruction': maneuver.get('instruction', f"Step {step_counter}"),
                                'distance': step.get('distance', 0),
                                'duration': step.get('duration', 0),
                                'start_location': {
                                    'lat': maneuver.get('location', [0, 0])[1],
                                    'lng': maneuver.get('location', [0, 0])[0]
                                },
                                'maneuver': {
                                    'type': maneuver.get('type', 'unknown'),
                                    'modifier': maneuver.get('modifier', ''),
                                    'bearing_before': maneuver.get('bearing_before', 0),
                                    'bearing_after': maneuver.get('bearing_after', 0)
                                },
                                'transport_mode': transport_mode
                            }
                            
                            # Extract step geometry if available
                            step_geometry = step.get('geometry', {})
                            if step_geometry.get('type') == 'LineString':
                                step_coords = step_geometry.get('coordinates', [])
                                step_data['path'] = [(lat, lng) for lng, lat in step_coords]
                            
                            steps.append(step_data)
                            step_counter += 1

            result = {
                'status': 'success',
                'source': 'osrm',
                'transport_mode': transport_mode,
                'distance': route.get('distance', 0) / 1000,  # Convert to km
                'duration': route.get('duration', 0),  # seconds
                'duration_str': format_duration(route.get('duration', 0)),
                'steps': steps,
                'geometry': coordinates,  # (lng, lat) points from OSRM
                'decoded_polyline': decoded_polyline,  # (lat, lng) points
                'polyline': polyline_encoded,
                'waypoints': route_coords,
                'metadata': {
                    'execution_time': round(time.time() - start_total, 2),
                    'optimized': optimize_route,
                    'total_waypoints': len(route_coords),
                    'total_steps': len(steps),
                    'osrm_server': OSRM_SERVERS[transport_mode]
                }
            }

            print(f"\n=== OSRM Route Calculation Complete ===")
            print(f"Transport mode: {transport_mode}")
            print(f"Total distance: {result['distance']:.2f} km")
            print(f"Total duration: {result['duration_str']}")
            print(f"Steps: {len(steps)}")
            print(f"Geometry points: {len(coordinates)}")

            return result

        elif use_osmnx_fallback:
            # Fallback to OSMnx if OSRM fails and fallback is enabled
            print(f"\n[3/3] OSRM failed, using OSMnx fallback for {transport_mode}...")
            
            # Get the road network graph covering all locations
            center_lat = sum(coord[0] for coord in route_coords) / len(route_coords)
            center_lng = sum(coord[1] for coord in route_coords) / len(route_coords)
            
            # Get appropriate network type for OSMnx
            network_type = OSMNX_NETWORK_TYPES.get(transport_mode, 'drive')
            
            graph = ox.graph_from_point(
                (center_lat, center_lng),
                dist=15000,  # 15km radius
                network_type=network_type,
                simplify=True
            )

            # Calculate complete route geometry between all points
            route_data = get_full_route_geometry(graph, route_coords, transport_mode)
            
            # Generate polyline
            polyline_coords = [(y, x) for x, y in route_data['full_geometry']]  # Convert to (lat,lng)
            polyline_encoded = polyline.encode(polyline_coords)
            
            result = {
                'status': 'success',
                'source': 'osmnx_fallback',
                'transport_mode': transport_mode,
                'distance': route_data['total_distance'] / 1000,  # km
                'duration': route_data['total_duration'],  # seconds
                'duration_str': format_duration(route_data['total_duration']),
                'steps': route_data['steps'],
                'geometry': route_data['full_geometry'],  # (lng,lat) points
                'decoded_polyline': polyline_coords,  # (lat,lng) points
                'polyline': polyline_encoded,
                'waypoints': route_coords,
                'metadata': {
                    'graph_nodes': len(graph.nodes),
                    'graph_edges': len(graph.edges),
                    'execution_time': round(time.time() - start_total, 2),
                    'optimized': optimize_route,
                    'total_waypoints': len(route_coords),
                    'network_type': network_type,
                    'speed_kph': DEFAULT_SPEEDS_KPH[transport_mode]
                }
            }

            print(f"\n=== OSMnx Fallback Route Complete ===")
            print(f"Transport mode: {transport_mode}")
            print(f"Network type: {network_type}")
            print(f"Total distance: {result['distance']:.2f} km")
            print(f"Total duration: {result['duration_str']}")
            print(f"Geometry points: {len(route_data['full_geometry'])}")

            return result
        else:
            error_msg = osrm_result.get('message', osrm_result.get('error', 'Unknown error'))
            raise RuntimeError(f"OSRM route calculation failed for {transport_mode}: {error_msg}")

    except Exception as e:
        print(f"\n!!! Route Calculation Failed: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'transport_mode': data.get('transport_mode', 'unknown'),
            'execution_time': round(time.time() - start_total, 2)
        }

def get_simple_route(origin: Dict, destination: Dict, transport_mode: str = 'driving', 
                    alternatives: bool = False) -> Dict:
    """
    Calculate a simple route between two points
    Args:
        origin: Dict with 'lat' and 'lng' keys
        destination: Dict with 'lat' and 'lng' keys
        transport_mode: Transportation mode (driving, foot, bike)
        alternatives: Whether to return alternative routes
    Returns:
        Dictionary with route information
    """
    waypoints = [origin, destination]
    data = {
        'waypoints': waypoints,
        'transport_mode': transport_mode,
        'optimize_route': False,
        'use_osmnx_fallback': True,
        'alternatives': alternatives
    }
    
    return get_route_directions(data)