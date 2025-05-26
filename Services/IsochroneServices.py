import os
import logging
import time
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon, mapping
import numpy as np
from functools import lru_cache
import json
from shapely.ops import unary_union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global graph cache to avoid repeated network downloads
graph_cache = {}

def get_graph(latitude, longitude, distance=2000, network_type='drive'):
    """
    Get or download OSM graph around a point
    
    Args:
        latitude (float): Center latitude
        longitude (float): Center longitude
        distance (int): Buffer distance in meters around center point
        network_type (str): Type of network - 'drive', 'walk', 'bike'
        
    Returns:
        networkx.MultiDiGraph: Street network graph
    """
    # Create cache key based on parameters
    cache_key = f"{latitude:.4f}_{longitude:.4f}_{distance}_{network_type}"
    
    # Check if graph is in cache
    if cache_key in graph_cache:
        logger.info(f"Using cached graph for {cache_key}")
        return graph_cache[cache_key]
    
    # Download new graph if not in cache
    try:
        logger.info(f"Downloading OSM graph for {latitude}, {longitude}")
        start_time = time.time()
        
        # Download the street network
        G = ox.graph_from_point(
            (latitude, longitude), 
            dist=distance, 
            network_type=network_type,
            simplify=True
        )
        
        # Add travel time in seconds as edge weight
        # For driving, assume average speed based on road type
        if network_type == 'drive':
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)
        # For walking, assume 5 km/h
        elif network_type == 'walk':
            for u, v, k, data in G.edges(keys=True, data=True):
                data['speed_kph'] = 5.0
                if 'length' in data:
                    data['travel_time'] = data['length'] / (5.0 * 1000 / 60 / 60)  # seconds
        # For biking, assume 15 km/h
        elif network_type == 'bike':
            for u, v, k, data in G.edges(keys=True, data=True):
                data['speed_kph'] = 15.0
                if 'length' in data:
                    data['travel_time'] = data['length'] / (15.0 * 1000 / 60 / 60)  # seconds
                    
        duration = time.time() - start_time
        logger.info(f"Graph download completed in {duration:.2f} seconds")
        
        # Cache the graph
        graph_cache[cache_key] = G
        
        return G
        
    except Exception as e:
        logger.error(f"Graph download error: {str(e)}", exc_info=True)
        raise

def find_nearest_node(G, latitude, longitude):
    """Find the nearest node in the graph to the given coordinates"""
    return ox.distance.nearest_nodes(G, X=[longitude], Y=[latitude])[0]

# Modified the lru_cache to use a tuple of travel times instead of a list
@lru_cache(maxsize=100)
def calculate_isochrone_cached(
    latitude, 
    longitude, 
    travel_times_tuple,  # Tuple instead of list to make it hashable
    travel_mode='drive',
    simplify_tolerance=20  # in meters
):
    """
    Calculate isochrone polygons for given travel times from a center point (cached version)
    
    Args:
        latitude (float): Starting point latitude
        longitude (float): Starting point longitude
        travel_times_tuple (tuple): Tuple of travel time thresholds in minutes
        travel_mode (str): Mode of travel - 'drive', 'walk', 'bike'
        simplify_tolerance (int): Tolerance for polygon simplification in meters
        
    Returns:
        dict: Dictionary of isochrone data including polygons and stats
    """
    try:
        logger.info(f"Calculating isochrones for {latitude}, {longitude}")
        start_time = time.time()
        
        # Convert tuple back to list for processing
        travel_times = list(travel_times_tuple)
        
        # Get the graph for the specified location and travel mode
        max_travel_time = max(travel_times)
        # Download a larger area for longer travel times
        buffer_distance = max(2000, max_travel_time * 60 * 25)  # rough estimate based on travel time
        G = get_graph(latitude, longitude, distance=buffer_distance, network_type=travel_mode)
        
        # Find the nearest node to the starting point
        origin_node = find_nearest_node(G, latitude, longitude)
        
        # Calculate shortest path travel time from origin to all nodes
        travel_times_seconds = [t * 60 for t in travel_times]  # convert to seconds
        
        # Calculate shortest paths
        subgraph = nx.ego_graph(
            G, 
            origin_node, 
            radius=max(travel_times_seconds), 
            distance='travel_time'
        )
        
        # Use Dijkstra's algorithm to get travel times to all nodes
        times = nx.single_source_dijkstra_path_length(
            G, 
            origin_node, 
            weight='travel_time', 
            cutoff=max(travel_times_seconds)
        )
        
        # Create a list to store isochrone polygons
        isochrones = []
        
        for time_threshold in sorted(travel_times_seconds):
            # Get nodes reachable within this time threshold
            reachable_nodes = [node for node, time in times.items() if time <= time_threshold]
            
            if not reachable_nodes:
                continue
                
            # Get node coordinates
            node_points = [Point(G.nodes[node]['x'], G.nodes[node]['y']) for node in reachable_nodes]
            
            # Create a GeoDataFrame of node points
            gdf_nodes = gpd.GeoDataFrame({'id': reachable_nodes, 'geometry': node_points})
            gdf_nodes.crs = "EPSG:4326"  # Set CRS
            
            # Create a convex hull around the nodes
            convex_hull = gdf_nodes.unary_union.convex_hull
            
            # Simplify the polygon if needed
            if simplify_tolerance > 0:
                convex_hull = convex_hull.simplify(simplify_tolerance / 111320)  # convert meters to degrees
                
            # Convert to GeoJSON-compatible format
            polygon_coords = []
            if isinstance(convex_hull, Polygon):
                # Extract exterior coordinates
                x, y = convex_hull.exterior.xy
                coords = list(zip(x.tolist(), y.tolist()))
                polygon_coords = [coords]
            
            # Calculate area in square kilometers
            area_km2 = convex_hull.area * 111.32 * 111.32  # rough conversion to km²
            
            # Add to results
            isochrones.append({
                'travel_time_minutes': time_threshold / 60,
                'area_km2': round(area_km2, 2),
                'polygon_coordinates': polygon_coords
            })
        
        duration = time.time() - start_time
        logger.info(f"Isochrone calculation completed in {duration:.2f} seconds")
        
        return {
            'center': {'latitude': latitude, 'longitude': longitude},
            'travel_mode': travel_mode,
            'isochrones': isochrones,
            'processing_time_seconds': duration
        }
        
    except Exception as e:
        logger.error(f"Isochrone calculation error: {str(e)}", exc_info=True)
        return {'error': str(e)}

def calculate_isochrone(
    latitude, 
    longitude, 
    travel_times=[5, 10, 15],
    travel_mode='drive',
    simplify_tolerance=20
):
    """
    Non-cached wrapper for calculate_isochrone_cached that converts list to tuple for caching
    
    Args:
        latitude (float): Starting point latitude
        longitude (float): Starting point longitude
        travel_times (list): List of travel time thresholds in minutes
        travel_mode (str): Mode of travel - 'drive', 'walk', 'bike'
        simplify_tolerance (int): Tolerance for polygon simplification in meters
        
    Returns:
        dict: Dictionary of isochrone data including polygons and stats
    """
    # Convert travel_times list to tuple for caching
    travel_times_tuple = tuple(sorted(travel_times))
    
    # Call the cached function
    return calculate_isochrone_cached(
        latitude, 
        longitude, 
        travel_times_tuple, 
        travel_mode, 
        simplify_tolerance
    )

def optimize_polygon(polygon, simplify_tolerance=20):
    """Simplify polygon to reduce point count while preserving shape"""
    if simplify_tolerance > 0:
        return polygon.simplify(simplify_tolerance / 111320)  # convert meters to degrees
    return polygon

def convert_polygons_to_geojson(isochrone_result):
    """Convert isochrone polygons to GeoJSON format"""
    features = []
    
    if 'isochrones' not in isochrone_result:
        return None
        
    for iso in isochrone_result['isochrones']:
        if not iso['polygon_coordinates']:
            continue
            
        # Create GeoJSON feature
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Polygon',
                'coordinates': iso['polygon_coordinates']
            },
            'properties': {
                'travel_time_minutes': iso['travel_time_minutes'],
                'area_km2': iso['area_km2']
            }
        }
        features.append(feature)
    
    # Create FeatureCollection
    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }
    
    return geojson

def get_bounding_box(isochrone_result):
    """Calculate the bounding box for the isochrone polygons"""
    polygons = []
    
    for iso in isochrone_result.get('isochrones', []):
        coords = iso.get('polygon_coordinates', [])
        if coords:
            polygons.append(Polygon(coords[0]))
    
    if not polygons:
        return None
        
    # Combine all polygons
    all_polygons = unary_union(polygons)
    
    # Get bounds
    minx, miny, maxx, maxy = all_polygons.bounds
    
    return {
        'southwest': {'latitude': miny, 'longitude': minx},
        'northeast': {'latitude': maxy, 'longitude': maxx}
    }

def get_stats_for_isochrones(isochrone_result):
    """Get statistics for the calculated isochrones"""
    stats = []
    
    for iso in isochrone_result.get('isochrones', []):
        stats.append({
            'travel_time_minutes': iso['travel_time_minutes'],
            'area_km2': iso['area_km2'],
            'vertex_count': len(iso.get('polygon_coordinates', [[]])[0]),
        })
    
    return stats