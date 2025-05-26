import os
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
import time
import pickle
from Config.Config import app
from geopy.geocoders import Nominatim
import logging
from typing import List, Dict, Tuple, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import asyncio
import threading
import queue
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for background tasks
background_tasks = set()
download_queue = queue.Queue()
download_in_progress = {}

def create_cache_folder():
    cache_folder = app.config["CACHE_FOLDER"]
    if not os.path.exists(cache_folder):
        os.makedirs(cache_folder, exist_ok=True)
    return cache_folder

def load_country_graph(country_name="United States"):
    """Load or download a full country graph"""
    cache_folder = create_cache_folder()
    cache_file_path = os.path.join(cache_folder, f"{country_name.replace(' ', '_')}.graphml")
    
    if os.path.exists(cache_file_path):
        try:
            logger.info(f"Loading country graph from cache: {country_name}")
            return ox.load_graphml(cache_file_path)
        except Exception as e:
            logger.warning(f"Error loading cached country graph {country_name}: {e}")
            os.remove(cache_file_path)  # Remove corrupted cache
    
    return None

def download_country_graph(country_name="United States"):
    """Download country graph and save to cache"""
    try:
        cache_folder = create_cache_folder()
        cache_file_path = os.path.join(cache_folder, f"{country_name.replace(' ', '_')}.graphml")
        
        logger.info(f"Downloading country graph for {country_name}")
        # Use custom filter to reduce graph size (main roads only)
        custom_filter = '["highway"~"motorway|trunk|primary|secondary|tertiary"]'
        graph = ox.graph_from_place(
            country_name, 
            network_type="drive",
            simplify=True,
            retain_all=False,  # Only keep connected graph
            custom_filter=custom_filter
        )
        
        # Save to cache
        logger.info(f"Saving country graph to cache: {country_name}")
        ox.save_graphml(graph, cache_file_path)
        return graph
    except Exception as e:
        logger.error(f"Error downloading country graph: {e}")
        return None

def start_background_download(country_name):
    """Start background download of country graph if not already in progress"""
    if country_name not in download_in_progress or not download_in_progress[country_name]:
        logger.info(f"Starting background download for {country_name}")
        download_in_progress[country_name] = True
        
        def download_task():
            try:
                download_country_graph(country_name)
            finally:
                download_in_progress[country_name] = False
        
        # Start the download in a separate thread
        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()

def generate_bbox_cache_key(bbox):
    """Generate a unique key for the bounding box"""
    # Convert bbox to string with reasonable precision
    bbox_str = "_".join([f"{coord:.5f}" for coord in bbox])
    # Create a hash to avoid filesystem issues with special characters
    hash_key = hashlib.md5(bbox_str.encode()).hexdigest()[:10]
    return f"bbox_{hash_key}"

def load_bbox_graph(bbox, buffer_km=10):
    """Load a cached bbox graph if available"""
    cache_folder = create_cache_folder()
    cache_key = generate_bbox_cache_key(bbox)
    cache_file_path = os.path.join(cache_folder, f"{cache_key}.graphml")
    
    if os.path.exists(cache_file_path):
        try:
            logger.info(f"Loading bbox graph from cache: {cache_key}")
            return ox.load_graphml(cache_file_path)
        except Exception as e:
            logger.warning(f"Error loading cached bbox graph {cache_key}: {e}")
            os.remove(cache_file_path)  # Remove corrupted cache
    
    return None

def get_bbox_graph(locations, buffer_km=10):
    """Create a graph covering the bounding box of all locations with caching"""
    try:
        lats = [lat for lat, _ in locations]
        lngs = [lng for _, lng in locations]
        
        north, south = max(lats), min(lats)
        east, west = max(lngs), min(lngs)
        
        # Convert buffer from km to degrees (approximate)
        buffer_deg = buffer_km / 111
        bbox = (north + buffer_deg, south - buffer_deg, 
                east + buffer_deg, west - buffer_deg)
        
        # Try to load from cache first
        cached_graph = load_bbox_graph(bbox)
        if cached_graph:
            logger.info(f"Using cached bbox graph for area {bbox}")
            return cached_graph
        
        # If not in cache, download and cache
        logger.info(f"Downloading graph for bounding box: {bbox}")
        custom_filter = '["highway"~"motorway|trunk|primary|secondary|tertiary"]'
        graph = ox.graph_from_bbox(
            *bbox,
            network_type="drive",
            simplify=True,
            retain_all=False,
            custom_filter=custom_filter
        )
        
        # Save to cache
        cache_folder = create_cache_folder()
        cache_key = generate_bbox_cache_key(bbox)
        cache_file_path = os.path.join(cache_folder, f"{cache_key}.graphml")
        
        logger.info(f"Saving bbox graph to cache: {cache_key}")
        ox.save_graphml(graph, cache_file_path)
        
        logger.info(f"Bounding box graph created with {len(graph.nodes)} nodes")
        return graph
    except Exception as e:
        logger.error(f"Error creating bounding box graph: {e}")
        return None

def extract_subgraph(full_graph, locations, buffer_km=10):
    """Extract a subgraph from the full country graph"""
    lats = [lat for lat, _ in locations]
    lngs = [lng for _, lng in locations]
    
    north, south = max(lats), min(lats)
    east, west = max(lngs), min(lngs)
    
    # Convert buffer from km to degrees (approximate)
    buffer_deg = buffer_km / 111
    bbox = (north + buffer_deg, south - buffer_deg, 
            east + buffer_deg, west - buffer_deg)
    
    # Get nodes within the bounding box
    nodes = []
    for node, data in full_graph.nodes(data=True):
        if 'x' in data and 'y' in data:
            if (west - buffer_deg <= data['x'] <= east + buffer_deg and 
                south - buffer_deg <= data['y'] <= north + buffer_deg):
                nodes.append(node)
    
    # Extract the subgraph
    if nodes:
        subgraph = full_graph.subgraph(nodes).copy()
        return subgraph
    return None


def calculate_realistic_travel_time(graph, path):
    if not path or len(path) < 2:
        return 0

    total_time = 0
    total_distance = 0
    intersection_penalty = 15  # seconds
    num_intersections = len(path) - 2
    intersection_time = max(0, num_intersections * intersection_penalty)

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        try:
            edge_data = graph.get_edge_data(u, v, 0)
            if edge_data:
                edge_length = edge_data.get('length', 0)
                total_distance += edge_length

                # 1. Check if there's a maxspeed
                maxspeed = edge_data.get("maxspeed")
                if isinstance(maxspeed, list):
                    maxspeed = maxspeed[0]
                if isinstance(maxspeed, str):
                    if maxspeed.endswith(" mph"):
                        speed_kph = float(maxspeed.split()[0]) * 1.60934
                    else:
                        speed_kph = float(maxspeed.split()[0])
                elif isinstance(maxspeed, (int, float)):
                    speed_kph = float(maxspeed)
                else:
                    # 2. Fall back to road type
                    highway = edge_data.get("highway", "")
                    speed_kph = get_speed_by_road_type(highway)

                speed_ms = speed_kph * 1000 / 3600
                segment_time = edge_length / speed_ms
                total_time += segment_time
        except Exception as e:
            # Handle errors
            if 'edge_length' in locals():
                total_time += edge_length / (30 * 1000 / 3600)

    if total_time == 0 and total_distance > 0:
        total_time = total_distance / (25 * 1000 / 3600)

    congestion_factor = 1.4
    total_time *= congestion_factor
    total_time += intersection_time + 20  # add delays
    return total_time



def get_speed_by_road_type(highway_type):
    """
    Get estimated speed based on road type, tuned for Macedonia/European context

    Args:
        highway_type: OSM highway tag value

    Returns:
        speed_kph: Estimated speed in km/h
    """
    speed_map = {
        'motorway': 120,       # Autopats / highways
        'trunk': 100,          # Major roads
        'primary': 90,         # National roads
        'secondary': 80,
        'tertiary': 60,
        'residential': 40,
        'service': 30,
        'living_street': 20,
        'pedestrian': 5,
        'track': 30,
        'unclassified': 50
    }

    if isinstance(highway_type, list) and highway_type:
        highway_type = highway_type[0]

    if isinstance(highway_type, str):
        for road_type, speed in speed_map.items():
            if road_type in highway_type:
                return speed

    return 50  # Default: reasonable urban/rural default



def precompute_distance_matrix(graph, nodes):
    """
    Compute a matrix of shortest paths and distances between all nodes
    with improved time estimation
    
    Args:
        graph: NetworkX graph
        nodes: List of node IDs
        
    Returns:
        distance_matrix: 2D array of shortest distances
        paths_matrix: 2D array of shortest paths
        time_matrix: 2D array of estimated travel times
    """
    from geopy.distance import geodesic
    import numpy as np
    
    n = len(nodes)
    distance_matrix = np.full((n, n), float('inf'))
    time_matrix = np.full((n, n), float('inf'))  # Added time matrix
    paths_matrix = [[[] for _ in range(n)] for _ in range(n)]
    
    # Try using NetworkX's shortest_path function for all-pairs
    try:
        for i, source in enumerate(nodes):
            # Use NetworkX's built-in shortest path functions
            try:
                # Get shortest paths and lengths to all other nodes
                paths = nx.single_source_dijkstra(graph, source, weight='length')
                lengths, routes = paths
                
                for j, target in enumerate(nodes):
                    if target in lengths:
                        distance_matrix[i][j] = lengths[target]
                        paths_matrix[i][j] = routes[target]
                        
                        # Calculate realistic travel time
                        path = routes[target]
                        time_matrix[i][j] = calculate_realistic_travel_time(graph, path)
            except Exception as e:
                print(f"Error computing paths from node {source}: {e}")
                # Fallback to computing individual paths
                for j, target in enumerate(nodes):
                    if i != j:  # Skip self
                        try:
                            path = nx.shortest_path(graph, source, target, weight='length')
                            length = nx.shortest_path_length(graph, source, target, weight='length')
                            distance_matrix[i][j] = length
                            paths_matrix[i][j] = path
                            # Calculate realistic travel time
                            time_matrix[i][j] = calculate_realistic_travel_time(graph, path)
                        except nx.NetworkXNoPath:
                            # No path exists, use straight-line distance as fallback
                            try:
                                source_lat, source_lon = graph.nodes[source].get('y'), graph.nodes[source].get('x')
                                target_lat, target_lon = graph.nodes[target].get('y'), graph.nodes[target].get('x')
                                if source_lat and source_lon and target_lat and target_lon:
                                    straight_distance = geodesic((source_lat, source_lon), (target_lat, target_lon)).meters
                                    distance_matrix[i][j] = straight_distance
                                    # Use more conservative speed estimate for straight-line (urban areas)
                                    time_matrix[i][j] = straight_distance / (25 * 1000 / 3600)  # 25 km/h for urban areas
                            except Exception:
                                # Keep as infinity if calculation fails
                                pass
    except Exception as e:
        print(f"Error during batch path computation: {e}")
        # Fallback to individual path computation
        for i in range(n):
            for j in range(n):
                if i != j:
                    source, target = nodes[i], nodes[j]
                    try:
                        path = nx.shortest_path(graph, source, target, weight='length')
                        length = nx.shortest_path_length(graph, source, target, weight='length')
                        distance_matrix[i][j] = length
                        paths_matrix[i][j] = path
                        # Calculate realistic travel time
                        time_matrix[i][j] = calculate_realistic_travel_time(graph, path)
                    except (nx.NetworkXNoPath, Exception) as e:
                        # No path exists or error occurred
                        try:
                            # Try to use straight-line distance as fallback
                            source_lat, source_lon = graph.nodes[source].get('y'), graph.nodes[source].get('x')
                            target_lat, target_lon = graph.nodes[target].get('y'), graph.nodes[target].get('x')
                            if source_lat and source_lon and target_lat and target_lon:
                                straight_distance = geodesic((source_lat, source_lon), (target_lat, target_lon)).meters
                                distance_matrix[i][j] = straight_distance
                                # Use more conservative speed estimate
                                time_matrix[i][j] = straight_distance / (25 * 1000 / 3600)  # 25 km/h for urban areas
                        except Exception:
                            # Keep as infinity if calculation fails
                            pass
    
    # Set diagonal to 0 (distance to self)
    for i in range(n):
        distance_matrix[i][i] = 0
        time_matrix[i][i] = 0
    
    return distance_matrix, paths_matrix, time_matrix

def get_combined_graph(data):
    """
    Create a graph covering all locations in the data.
    Used as a fallback when country graph approach fails.
    """
    logger.info("Creating combined graph from all locations")
    try:
        # Extract coordinates from all locations
        locations = [(item['lat'], item['lng']) for item in data if 'lat' in item and 'lng' in item]
        
        if not locations:
            logger.error("No valid locations found in data")
            return None
        
        # Calculate center point
        center_lat = sum(lat for lat, _ in locations) / len(locations)
        center_lng = sum(lng for _, lng in locations) / len(locations)
        
        # Find maximum distance to determine appropriate radius
        max_distance_km = 0
        for lat, lng in locations:
            dist = geodesic((center_lat, center_lng), (lat, lng)).kilometers
            max_distance_km = max(max_distance_km, dist)
        
        # Add buffer to ensure all locations are covered
        radius_km = max_distance_km + 5  # 5km buffer
        
        logger.info(f"Creating graph with center ({center_lat}, {center_lng}) and radius {radius_km}km")
        
        # Check if we have a cached bbox for this region
        bbox = (
            center_lat + radius_km/111,  # north
            center_lat - radius_km/111,  # south
            center_lng + radius_km/(111 * np.cos(np.radians(center_lat))),  # east
            center_lng - radius_km/(111 * np.cos(np.radians(center_lat)))   # west
        )
        
        cached_graph = load_bbox_graph(bbox)
        if cached_graph:
            logger.info(f"Using cached graph for combined area")
            return cached_graph
        
        # Download graph from OSM around the center point
        custom_filter = '["highway"~"motorway|trunk|primary|secondary|tertiary"]'
        graph = ox.graph_from_point(
            (center_lat, center_lng),
            dist=radius_km * 1000,  # Convert to meters
            network_type="drive",
            simplify=True,
            retain_all=False,
            custom_filter=custom_filter
        )
        
        # Cache this graph
        cache_folder = create_cache_folder()
        cache_key = generate_bbox_cache_key(bbox)
        cache_file_path = os.path.join(cache_folder, f"{cache_key}.graphml")
        
        logger.info(f"Saving combined graph to cache: {cache_key}")
        ox.save_graphml(graph, cache_file_path)
        
        logger.info(f"Combined graph created with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
        return graph
    
    except Exception as e:
        logger.error(f"Error creating combined graph: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Last resort fallback - try to get a small graph from first location
        try:
            if locations:
                first_lat, first_lng = locations[0]
                logger.info(f"Attempting fallback graph from first location ({first_lat}, {first_lng})")
                graph = ox.graph_from_point(
                    (first_lat, first_lng),
                    dist=2000,  # 2km radius
                    network_type="drive",
                    simplify=True
                )
                return graph
        except Exception as fallback_error:
            logger.error(f"Fallback graph creation failed: {fallback_error}")
        
        return None
    
    
def solve_pdp_optimized(graph, data):
    """Solve pickup-delivery problem with optimized algorithm and improved time estimates"""
    print("\n=== Starting Optimized Route Calculation ===")
    start_time = time.time()
    
    try:
        # Extract nodes and locations
        current_location = next((item['lat'], item['lng']) for item in data if item['type'] == 'current')
        pickups = [(item['lat'], item['lng'], item['package_id']) for item in data if item['type'] == 'pickup']
        deliveries = [(item['lat'], item['lng'], item['package_id']) for item in data if item['type'] == 'delivery']
        
        print(f"Current location: {current_location}")
        print(f"Number of pickups: {len(pickups)}")
        print(f"Number of deliveries: {len(deliveries)}")
        
        # Find nearest nodes on the graph (all at once to enable batching)
        print("Finding nearest nodes on the graph...")
        all_points = [(current_location[0], current_location[1])] + [(lat, lng) for lat, lng, _ in pickups] + [(lat, lng) for lat, lng, _ in deliveries]
        
        # Batch process nearest nodes finding
        def find_nearest_nodes_batch(points_batch):
            return [ox.distance.nearest_nodes(graph, lng, lat) for lat, lng in points_batch]
        
        # Process in batches of 10 to reduce overhead
        batch_size = 10
        all_nearest_nodes = []
        for i in range(0, len(all_points), batch_size):
            batch = all_points[i:i+batch_size]
            all_nearest_nodes.extend(find_nearest_nodes_batch(batch))
        
        # Map results back
        start_node = all_nearest_nodes[0]
        pickup_nodes = {pickups[i][2]: all_nearest_nodes[i+1] for i in range(len(pickups))}
        delivery_nodes = {deliveries[i][2]: all_nearest_nodes[i+1+len(pickups)] for i in range(len(deliveries))}
        
        print("Nearest nodes found successfully.")
        
        # Create array of nodes and their names
        nodes = [start_node] + list(pickup_nodes.values()) + list(delivery_nodes.values())
        node_names = ['Start'] + [f'Pickup_{pkg_id}' for pkg_id in pickup_nodes.keys()] + [f'Delivery_{pkg_id}' for pkg_id in delivery_nodes.keys()]
        
        # Pre-compute distance matrix and paths with improved time matrix
        print("Pre-computing distance matrix...")
        matrix_time_start = time.time()
        distance_matrix, paths_matrix, time_matrix = precompute_distance_matrix(graph, nodes)
        print(f"Distance matrix computed in {time.time() - matrix_time_start:.2f} seconds")
        
        # Optimize route using the pre-computed matrix
        print("Optimizing route...")
        unvisited = set(range(1, len(nodes)))
        visited_pickups = set()
        current_node_idx = 0
        route = [0]
        total_distance = 0
        total_time = 0
        route_segments = []
        
        # Create a mapping from package_id to its index in the node_names list
        pkg_id_to_index = {}
        for i, name in enumerate(node_names):
            if '_' in name:  # Skip 'Start'
                node_type, pkg_id = name.split('_', 1)  # Split on first underscore only
                if node_type == 'Pickup':
                    pkg_id_to_index[pkg_id] = i
        
        while unvisited:
            next_node_idx = None
            min_distance = float('inf')
            
            for node_idx in unvisited:
                node_name = node_names[node_idx]
                # Ensure delivery comes after pickup
                if 'Delivery' in node_name:
                    pkg_id = node_name.split('_', 1)[1]  # Split on first underscore only
                    # Check if the corresponding pickup has been visited
                    if pkg_id not in visited_pickups:
                        continue
                
                # Use the precomputed distance
                segment_distance = distance_matrix[current_node_idx][node_idx]
                if segment_distance < min_distance:
                    min_distance = segment_distance
                    next_node_idx = node_idx
            
            if next_node_idx is not None:
                route.append(next_node_idx)
                segment_distance = distance_matrix[current_node_idx][next_node_idx]
                segment_path = paths_matrix[current_node_idx][next_node_idx]
                segment_time = time_matrix[current_node_idx][next_node_idx]  # Use precomputed time
                
                # Store segment details
                route_segments.append({
                    'from_node': current_node_idx,
                    'to_node': next_node_idx,
                    'distance': segment_distance,
                    'time': segment_time,
                    'path': segment_path
                })
                
                print(f"Next best node: {node_names[next_node_idx]} (Distance: {segment_distance:.2f} meters, Time: {segment_time:.2f} seconds)")
                
                current_node_idx = next_node_idx
                unvisited.remove(next_node_idx)
                
                # Mark pickups as visited
                if 'Pickup' in node_names[next_node_idx]:
                    pkg_id = node_names[next_node_idx].split('_', 1)[1]  # Split on first underscore only
                    visited_pickups.add(pkg_id)
                
                # Accumulate totals
                total_distance += segment_distance
                total_time += segment_time
            else:
                print("No valid next node found. Trying fallback method...")
                if unvisited:
                    # Force selection of the first unvisited node
                    next_node_idx = min(unvisited)
                    print(f"Forcing selection of node: {node_names[next_node_idx]}")
                    route.append(next_node_idx)
                    
                    # Use Euclidean distance as fallback
                    # Extract coordinates from data
                    from_coords = None
                    to_coords = None
                    
                    if current_node_idx == 0:
                        from_coords = current_location
                    else:
                        node_info = node_names[current_node_idx].split('_', 1)  # Split on first underscore only
                        if len(node_info) > 1:
                            node_type, pkg_id = node_info[0].lower(), node_info[1]
                            for item in data:
                                if item['type'] == node_type and item.get('package_id') == pkg_id:
                                    from_coords = (item['lat'], item['lng'])
                                    break
                    
                    node_info = node_names[next_node_idx].split('_', 1)  # Split on first underscore only
                    if len(node_info) > 1:
                        node_type, pkg_id = node_info[0].lower(), node_info[1]
                        for item in data:
                            if item['type'] == node_type and item.get('package_id') == pkg_id:
                                to_coords = (item['lat'], item['lng'])
                                break
                    
                    if from_coords and to_coords:
                        segment_distance = geodesic(from_coords, to_coords).meters
                        print(f"Using straight-line distance: {segment_distance:.2f} meters")
                    else:
                        segment_distance = 1000  # Default 1km
                    
                    # Use a more conservative time estimate for urban areas (20 km/h + traffic factor)
                    segment_time = segment_distance / (20 * 1000 / 3600) * 1.4  # with traffic factor
                    
                    route_segments.append({
                        'from_node': current_node_idx,
                        'to_node': next_node_idx,
                        'distance': segment_distance,
                        'time': segment_time,
                        'path': []
                    })
                    
                    total_distance += segment_distance
                    total_time += segment_time
                    
                    current_node_idx = next_node_idx
                    unvisited.remove(next_node_idx)
                    if 'Pickup' in node_names[next_node_idx]:
                        pkg_id = node_names[next_node_idx].split('_', 1)[1]  # Split on first underscore only
                        visited_pickups.add(pkg_id)
                else:
                    print("Still no valid node found. Aborting route calculation.")
                    return None
        
        # Generate final route information
        optimal_route = [node_names[i] for i in route]
        print(f"Final optimized route: {optimal_route}")
        
        # Extract coordinates for each node in the route
        optimal_route_coords = []
        for node in optimal_route:
            if node == 'Start':  # Starting position
                for item in data:
                    if item['type'] == 'current':
                        optimal_route_coords.append((item['lat'], item['lng']))
                        break
            else:  # Pickup or delivery
                node_info = node.split('_', 1)  # Split on first underscore only
                node_type, package_id = node_info[0].lower(), node_info[1]
                for item in data:
                    if item['type'] == node_type and item.get('package_id') == package_id:
                        optimal_route_coords.append((item['lat'], item['lng']))
                        break
        
        # Format time
        hours = int(total_time / 3600)
        minutes = int((total_time % 3600) / 60)
        seconds = int(total_time % 60)
        time_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
        
        print(f"Total distance: {round(total_distance / 1000, 2)} km")
        print(f"Estimated travel time: {time_str}")
        print(f"Total execution time: {round(time.time() - start_time, 2)} seconds")
        
        # Prepare detailed segment breakdown
        segment_details = []
        for i, segment in enumerate(route_segments):
            from_name = node_names[segment['from_node']]
            to_name = node_names[segment['to_node']]
            package_id = None
            
            # Identify the package_id for each segment
            if 'Pickup' in to_name or 'Delivery' in to_name:  # Assign package_id from the to_name
                package_id = to_name.split('_', 1)[1]  # Split on first underscore only
            
            # Calculate duration_segment
            segment_duration_seconds = segment['time']
            segment_hours = int(segment_duration_seconds // 3600)
            segment_minutes = int((segment_duration_seconds % 3600) // 60)
            segment_seconds = int(segment_duration_seconds % 60)
            duration_segment = f"{segment_hours}h {segment_minutes}m" if segment_hours > 0 else f"{segment_minutes}m {segment_seconds}s"
            
            segment_details.append({
                'package_id': package_id,
                'distance_km': round(segment['distance'] / 1000, 2),
                'segment': f"{from_name} → {to_name}",
                'duration_segment': duration_segment
            })
        
        return {
            'optimal_route': optimal_route,
            'minimum_distance_km': round(total_distance / 1000, 2),
            'estimated_travel_time_seconds': int(total_time),
            'estimated_travel_time': time_str,
            'optimal_route_coordinates': optimal_route_coords,
            'segment_details': segment_details
        }
    
    except Exception as e:
        logger.error(f"Error in route calculation: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'error': str(e),
            'optimal_route': [],
            'minimum_distance_km': 0,
            'estimated_travel_time_seconds': 0,
            'estimated_travel_time': '0s',
            'optimal_route_coordinates': []
        }


def solve_tsp_optimized(graph, data):
    """Solve simple TSP problem (non-PDP) with optimized algorithm"""
    print("\n=== Starting TSP Route Calculation ===")
    start_time = time.time()
    
    try:
        # Extract nodes and locations with their IDs
        locations = []
        for idx, item in enumerate(data):
            if 'lat' in item and 'lng' in item:
                loc_id = item.get('id', f"loc_{idx}")
                locations.append((item['lat'], item['lng'], loc_id))
        
        if not locations:
            return {'error': 'No valid locations provided'}
        
        print(f"Number of locations: {len(locations)}")
        
        # Find nearest nodes on the graph (batch processing)
        print("Finding nearest nodes on the graph...")
        all_points = [(lat, lng) for lat, lng, _ in locations]
        
        # Batch process nearest nodes finding
        def find_nearest_nodes_batch(points_batch):
            return [ox.distance.nearest_nodes(graph, lng, lat) for lat, lng in points_batch]
        
        # Process in batches of 10 to reduce overhead
        batch_size = 10
        all_nearest_nodes = []
        for i in range(0, len(all_points), batch_size):
            batch = all_points[i:i+batch_size]
            all_nearest_nodes.extend(find_nearest_nodes_batch(batch))
        
        # Create array of nodes and their names
        nodes = all_nearest_nodes
        node_names = [loc_id for _, _, loc_id in locations]
        
        # Pre-compute distance matrix and paths
        print("Pre-computing distance matrix...")
        matrix_time_start = time.time()
        distance_matrix, paths_matrix = precompute_distance_matrix(graph, nodes)
        print(f"Distance matrix computed in {time.time() - matrix_time_start:.2f} seconds")
        
        # Solve TSP using the pre-computed matrix
        print("Solving TSP...")
        num_nodes = len(nodes)
        unvisited = set(range(1, num_nodes))
        current_node_idx = 0
        route = [0]
        total_distance = 0
        total_time = 0
        route_segments = []
        
        while unvisited:
            next_node_idx = None
            min_distance = float('inf')
            
            for node_idx in unvisited:
                segment_distance = distance_matrix[current_node_idx][node_idx]
                if segment_distance < min_distance:
                    min_distance = segment_distance
                    next_node_idx = node_idx
            
            if next_node_idx is not None:
                route.append(next_node_idx)
                segment_distance = distance_matrix[current_node_idx][next_node_idx]
                segment_path = paths_matrix[current_node_idx][next_node_idx]
                
                # Store segment details
                route_segments.append({
                    'from_node': current_node_idx,
                    'to_node': next_node_idx,
                    'distance': segment_distance,
                    'path': segment_path
                })
                
                print(f"Next best node: {node_names[next_node_idx]} (Distance: {segment_distance:.2f} meters)")
                
                # Calculate time based on path
                segment_time = 0
                if segment_path and len(segment_path) > 1:
                    for i in range(len(segment_path) - 1):
                        u, v = segment_path[i], segment_path[i + 1]
                        try:
                            edge_data = graph.get_edge_data(u, v, 0)
                            if edge_data:
                                edge_length = edge_data.get('length', 0)
                                speed_ms = (edge_data.get('speed_kph', 50) * 1000 / 3600)  # Default 50 km/h
                                segment_time += edge_length / speed_ms
                        except Exception:
                            # Fallback if edge data is missing
                            segment_time += segment_distance / (50 * 1000 / 3600)
                else:
                    # Estimate time if no path data
                    segment_time = segment_distance / (50 * 1000 / 3600)  # 50 km/h
                
                current_node_idx = next_node_idx
                unvisited.remove(next_node_idx)
                
                # Accumulate totals
                total_distance += segment_distance
                total_time += segment_time
            else:
                print("No valid next node found. Aborting route calculation.")
                break
        
        # Generate final route information
        optimal_route = [node_names[i] for i in route]
        print(f"Final optimized route: {optimal_route}")
        
        # Extract coordinates for each node in the route - FIXED VERSION
        optimal_route_coords = []
        for node_idx in route:
            node_name = node_names[node_idx]
            
            # Find the matching location in the original data
            for item in data:
                # Handle current location
                if node_name == 'current' and item.get('type') == 'current':
                    optimal_route_coords.append([item['lng'], item['lat']])  # Note: lon,lat for GeoJSON
                    break
                # Handle waypoints
                elif item.get('id') == node_name or (isinstance(node_name, str) and 
                                                  node_name.startswith('loc_') and 
                                                  'lat' in item and 'lng' in item and
                                                  item.get('id', f"loc_{data.index(item)}") == node_name):
                    optimal_route_coords.append([item['lng'], item['lat']])  # Note: lon,lat for GeoJSON
                    break
        
        # Format time
        hours = int(total_time / 3600)
        minutes = int((total_time % 3600) / 60)
        seconds = int(total_time % 60)
        time_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
        
        print(f"Total distance: {round(total_distance / 1000, 2)} km")
        print(f"Estimated travel time: {time_str}")
        print(f"Total execution time: {round(time.time() - start_time, 2)} seconds")
        
        # Prepare detailed segment breakdown
        segment_details = []
        for i, segment in enumerate(route_segments):
            from_name = node_names[segment['from_node']]
            to_name = node_names[segment['to_node']]
            
            # Calculate duration_segment
            segment_duration_seconds = segment['distance'] / (50 * 1000 / 3600)  # 50 km/h
            segment_hours = int(segment_duration_seconds // 3600)
            segment_minutes = int((segment_duration_seconds % 3600) // 60)
            segment_seconds = int(segment_duration_seconds % 60)
            duration_segment = f"{segment_hours}h {segment_minutes}m" if segment_hours > 0 else f"{segment_minutes}m {segment_seconds}s"
            
            segment_details.append({
                'distance_km': round(segment['distance'] / 1000, 2),
                'segment': f"{from_name} → {to_name}",
                'duration_segment': duration_segment
            })
        
        return {
            'optimal_route': optimal_route,
            'minimum_distance_km': round(total_distance / 1000, 2),
            'estimated_travel_time_seconds': int(total_time),
            'estimated_travel_time': time_str,
            'optimal_route_coordinates': optimal_route_coords,
            'segment_details': segment_details
        }
    
    except Exception as e:
        logger.error(f"Error in TSP calculation: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'error': str(e),
            'optimal_route': [],
            'minimum_distance_km': 0,
            'estimated_travel_time_seconds': 0,
            'estimated_travel_time': '0s',
            'optimal_route_coordinates': []
        }
        
        
def get_country_from_coordinates(lat, lng):
    """Get country name from coordinates"""
    geolocator = Nominatim(user_agent="route_optimizer", timeout=10)
    try:
        location = geolocator.reverse((lat, lng), exactly_one=True)
        if location and "address" in location.raw:
            address = location.raw["address"]
            country = address.get("country", "United States")  # Default to US
            print(f"Country found from coordinates: {country}")
            return country
    except Exception as e:
        logger.warning(f"Geocoding error for ({lat}, {lng}): {e}")
    return "United States"  # Default fallback

def calculate_optimal_route(data):
    """Main entry point that handles both PDP and non-PDP cases"""
    print("\n=== Starting Optimal Route Calculation ===")
    start_time = time.time()
    
    try:
        # Determine if this is a PDP problem by checking for types in the data
        is_pdp = any(item.get('type') in ['pickup', 'delivery'] for item in data)
        
        # Extract all location coordinates
        locations = [(item['lat'], item['lng']) for item in data if 'lat' in item and 'lng' in item]
        
        if not locations:
            logger.error("No valid locations found in data")
            return {'error': 'No valid locations found in data'}
        
        # Get country name from coordinates
        sample_location = locations[0]
        country_name = get_country_from_coordinates(sample_location[0], sample_location[1])
        
        # Try to load cached country graph first (highest priority)
        country_graph = load_country_graph(country_name)
        
        if country_graph:
            logger.info(f"Using cached country graph for {country_name}")
            
            # Extract a subgraph covering all locations
            subgraph = extract_subgraph(country_graph, locations, buffer_km=15)
            
            if subgraph:
                logger.info("Using subgraph from country graph")
                graph_to_use = subgraph
            else:
                logger.info("Subgraph extraction failed, using full country graph")
                graph_to_use = country_graph
        else:
            logger.info(f"No cached country graph found for {country_name}")
            
            # Start background download of country graph for future use
            start_background_download(country_name)
            
            # Calculate bounding box
            lats = [lat for lat, _ in locations]
            lngs = [lng for _, lng in locations]
            north, south = max(lats), min(lats)
            east, west = max(lngs), min(lngs)
            buffer_deg = 10 / 111  # 10km buffer
            bbox = (north + buffer_deg, south - buffer_deg, 
                    east + buffer_deg, west - buffer_deg)
            
            # Try to load cached bbox graph (second priority)
            bbox_graph = load_bbox_graph(bbox)
            
            if bbox_graph:
                logger.info("Using cached bounding box graph")
                graph_to_use = bbox_graph
            else:
                logger.info("No cached bbox graph found, downloading new one")
                # Download and cache a new bbox graph
                graph_to_use = get_bbox_graph(locations)
                
                if not graph_to_use:
                    # Final fallback to combined graph approach
                    logger.info("Falling back to combined graph approach")
                    graph_to_use = get_combined_graph(data)
                    if not graph_to_use:
                        return {
                            'error': 'Failed to create any valid graph',
                            'optimal_route': [],
                            'minimum_distance_km': 0,
                            'estimated_travel_time_seconds': 0,
                            'estimated_travel_time': '0s',
                            'optimal_route_coordinates': []
                        }
        
        # Route calculation based on problem type
        if is_pdp:
            return solve_pdp_optimized(graph_to_use, data)
        else:
            return solve_tsp_optimized(graph_to_use, data)
            
    except Exception as e:
        logger.error(f"Error in route calculation: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'error': str(e),
            'optimal_route': [],
            'minimum_distance_km': 0,
            'estimated_travel_time_seconds': 0,
            'estimated_travel_time': '0s',
            'optimal_route_coordinates': []
        }