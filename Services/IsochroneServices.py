import os
import logging
import time
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon
import numpy as np
from functools import lru_cache
import pickle
import hashlib
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Union
from geopy.distance import geodesic
from shapely.ops import unary_union
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GraphCache:
    """Enhanced graph caching system with intelligent region management"""
    
    def __init__(self, cache_folder="cache", max_memory_graphs=5):
        self.cache_folder = cache_folder
        self.max_memory_graphs = max_memory_graphs
        self.memory_cache = {}
        self.cache_access_times = {}
        self.download_queue = queue.Queue()
        self.download_in_progress = set()
        self.lock = threading.RLock()
        self._create_cache_folder()
        self._start_background_downloader()
        
    def _create_cache_folder(self):
        """Create cache folder if it doesn't exist"""
        if not os.path.exists(self.cache_folder):
            os.makedirs(self.cache_folder, exist_ok=True)
            
    def _start_background_downloader(self):
        """Start background thread for downloading graphs"""
        def background_downloader():
            while True:
                try:
                    task = self.download_queue.get(timeout=60)
                    if task is None:  # Shutdown signal
                        break
                    self._download_graph_background(task)
                    self.download_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Background downloader error: {e}")
                    
        self.download_thread = threading.Thread(target=background_downloader, daemon=True)
        self.download_thread.start()
        
    def _generate_cache_key(self, lat, lon, distance, network_type, precision=3):
        """Generate cache key for graph region"""
        # Round coordinates to reduce cache fragmentation
        lat_rounded = round(lat, precision)
        lon_rounded = round(lon, precision)
        # Use distance in km for cleaner keys
        distance_km = distance // 1000
        return f"{lat_rounded}_{lon_rounded}_{distance_km}km_{network_type}"
        
    def _generate_region_key(self, lat, lon, distance, network_type):
        """Generate broader region key for larger area caching"""
        # Create larger regions (e.g., 20km x 20km blocks)
        region_size = 0.2  # degrees (roughly 20km)
        region_lat = round(lat / region_size) * region_size
        region_lon = round(lon / region_size) * region_size
        return f"region_{region_lat}_{region_lon}_{network_type}"
        
    def _get_cache_file_path(self, cache_key):
        """Get file path for cached graph"""
        safe_key = cache_key.replace(".", "_").replace("-", "neg")
        return os.path.join(self.cache_folder, f"{safe_key}.graphml")
        
    def _load_from_disk(self, cache_key):
        """Load graph from disk cache"""
        cache_file = self._get_cache_file_path(cache_key)
        if os.path.exists(cache_file):
            try:
                logger.info(f"Loading graph from disk: {cache_key}")
                graph = ox.load_graphml(cache_file)
                # Add travel time weights if missing
                self._ensure_travel_times(graph, cache_key.split('_')[-1])
                return graph
            except Exception as e:
                logger.warning(f"Error loading cached graph {cache_key}: {e}")
                os.remove(cache_file)  # Remove corrupted cache
        return None
        
    def _save_to_disk(self, graph, cache_key):
        """Save graph to disk cache"""
        try:
            cache_file = self._get_cache_file_path(cache_key)
            ox.save_graphml(graph, cache_file)
            logger.info(f"Saved graph to disk: {cache_key}")
        except Exception as e:
            logger.error(f"Error saving graph to disk {cache_key}: {e}")
            
    def _ensure_travel_times(self, graph, network_type):
        """Ensure graph has travel time weights"""
        sample_edge = next(iter(graph.edges(data=True)), None)
        if sample_edge and 'travel_time' not in sample_edge[2]:
            if network_type == 'drive':
                graph = ox.add_edge_speeds(graph)
                graph = ox.add_edge_travel_times(graph)
            elif network_type == 'walk':
                for u, v, k, data in graph.edges(keys=True, data=True):
                    data['speed_kph'] = 5.0
                    if 'length' in data:
                        data['travel_time'] = data['length'] / (5.0 * 1000 / 3600)
            elif network_type == 'bike':
                for u, v, k, data in graph.edges(keys=True, data=True):
                    data['speed_kph'] = 15.0
                    if 'length' in data:
                        data['travel_time'] = data['length'] / (15.0 * 1000 / 3600)
        return graph
        
    def _manage_memory_cache(self):
        """Remove least recently used graphs from memory"""
        with self.lock:
            if len(self.memory_cache) >= self.max_memory_graphs:
                # Remove least recently used
                oldest_key = min(self.cache_access_times.keys(), 
                               key=lambda k: self.cache_access_times[k])
                del self.memory_cache[oldest_key]
                del self.cache_access_times[oldest_key]
                logger.info(f"Removed {oldest_key} from memory cache")
                
    def _download_graph_background(self, task):
        """Download graph in background"""
        cache_key, lat, lon, distance, network_type = task
        
        with self.lock:
            if cache_key in self.download_in_progress:
                return
            self.download_in_progress.add(cache_key)
            
        try:
            logger.info(f"Background downloading: {cache_key}")
            graph = ox.graph_from_point(
                (lat, lon), 
                dist=distance, 
                network_type=network_type,
                simplify=True
            )
            
            # Add travel times
            graph = self._ensure_travel_times(graph, network_type)
            
            # Save to disk
            self._save_to_disk(graph, cache_key)
            
            # Add to memory cache if there's space
            with self.lock:
                if len(self.memory_cache) < self.max_memory_graphs:
                    self.memory_cache[cache_key] = graph
                    self.cache_access_times[cache_key] = time.time()
                    
        except Exception as e:
            logger.error(f"Background download failed for {cache_key}: {e}")
        finally:
            with self.lock:
                self.download_in_progress.discard(cache_key)
                
    def get_graph(self, latitude, longitude, distance=2000, network_type='drive'):
        """Get graph with intelligent caching"""
        cache_key = self._generate_cache_key(latitude, longitude, distance, network_type)
        
        with self.lock:
            # Check memory cache first
            if cache_key in self.memory_cache:
                self.cache_access_times[cache_key] = time.time()
                logger.info(f"Using memory cached graph: {cache_key}")
                return self.memory_cache[cache_key]
                
        # Check disk cache
        graph = self._load_from_disk(cache_key)
        if graph is not None:
            with self.lock:
                self._manage_memory_cache()
                self.memory_cache[cache_key] = graph
                self.cache_access_times[cache_key] = time.time()
            return graph
            
        # Check if download is in progress
        with self.lock:
            if cache_key in self.download_in_progress:
                logger.info(f"Download in progress for {cache_key}, using fallback")
                # Try to get a nearby cached graph as fallback
                return self._get_nearby_graph(latitude, longitude, distance, network_type)
                
        # Download immediately for first request
        try:
            logger.info(f"Downloading new graph: {cache_key}")
            start_time = time.time()
            
            graph = ox.graph_from_point(
                (latitude, longitude), 
                dist=distance, 
                network_type=network_type,
                simplify=True
            )
            
            # Add travel times
            graph = self._ensure_travel_times(graph, network_type)
            
            duration = time.time() - start_time
            logger.info(f"Graph download completed in {duration:.2f} seconds")
            
            # Save to disk
            self._save_to_disk(graph, cache_key)
            
            # Add to memory cache
            with self.lock:
                self._manage_memory_cache()
                self.memory_cache[cache_key] = graph
                self.cache_access_times[cache_key] = time.time()
                
            # Queue nearby areas for background download
            self._queue_nearby_downloads(latitude, longitude, distance, network_type)
            
            return graph
            
        except Exception as e:
            logger.error(f"Graph download error: {str(e)}")
            raise
            
    def _get_nearby_graph(self, lat, lon, distance, network_type):
        """Get a nearby cached graph as fallback"""
        with self.lock:
            best_graph = None
            min_distance = float('inf')
            
            for cached_key, graph in self.memory_cache.items():
                if network_type not in cached_key:
                    continue
                    
                # Extract coordinates from cache key
                parts = cached_key.split('_')
                if len(parts) >= 2:
                    try:
                        cached_lat = float(parts[0])
                        cached_lon = float(parts[1])
                        dist = geodesic((lat, lon), (cached_lat, cached_lon)).kilometers
                        
                        if dist < min_distance and dist < 50:  # Within 50km
                            min_distance = dist
                            best_graph = graph
                    except ValueError:
                        continue
                        
            return best_graph
            
    def _queue_nearby_downloads(self, lat, lon, distance, network_type):
        """Queue nearby areas for background download"""
        # Download surrounding areas
        offsets = [
            (0.02, 0), (-0.02, 0), (0, 0.02), (0, -0.02),  # Adjacent areas
            (0.02, 0.02), (0.02, -0.02), (-0.02, 0.02), (-0.02, -0.02)  # Diagonal areas
        ]
        
        for lat_offset, lon_offset in offsets:
            nearby_lat = lat + lat_offset
            nearby_lon = lon + lon_offset
            nearby_key = self._generate_cache_key(nearby_lat, nearby_lon, distance, network_type)
            
            # Only queue if not already cached or downloading
            if (nearby_key not in self.memory_cache and 
                not os.path.exists(self._get_cache_file_path(nearby_key)) and
                nearby_key not in self.download_in_progress):
                
                task = (nearby_key, nearby_lat, nearby_lon, distance, network_type)
                try:
                    self.download_queue.put_nowait(task)
                except queue.Full:
                    break  # Queue is full, skip remaining

# Global graph cache instance
graph_cache = GraphCache()

def find_nearest_node(G, latitude, longitude):
    """Find the nearest node in the graph to the given coordinates"""
    return ox.distance.nearest_nodes(G, X=[longitude], Y=[latitude])[0]

@lru_cache(maxsize=200)
def calculate_isochrone_cached(
    latitude, 
    longitude, 
    travel_times_tuple,
    travel_mode='drive',
    simplify_tolerance=20
):
    """Calculate isochrone polygons with enhanced caching"""
    try:
        logger.info(f"Calculating isochrones for {latitude}, {longitude}")
        start_time = time.time()
        
        travel_times = list(travel_times_tuple)
        max_travel_time = max(travel_times)
        
        # Use adaptive buffer distance based on travel time and mode
        if travel_mode == 'drive':
            speed_factor = 60  # km/h average
        elif travel_mode == 'bike':
            speed_factor = 15
        else:  # walk
            speed_factor = 5
            
        # Calculate buffer with some padding
        buffer_distance = max(2000, int(max_travel_time * speed_factor * 1000 / 60 * 1.5))
        
        # Get the graph using our enhanced cache
        G = graph_cache.get_graph(latitude, longitude, distance=buffer_distance, network_type=travel_mode)
        
        if G is None:
            raise Exception("Unable to obtain street network graph")
            
        # Find the nearest node to the starting point
        origin_node = find_nearest_node(G, latitude, longitude)
        
        # Calculate shortest path travel times
        travel_times_seconds = [t * 60 for t in travel_times]
        
        # Use more efficient algorithm for large graphs
        if len(G.nodes) > 10000:
            # For large graphs, use single-source shortest path with cutoff
            times = nx.single_source_dijkstra_path_length(
                G, 
                origin_node, 
                weight='travel_time', 
                cutoff=max(travel_times_seconds)
            )
        else:
            # For smaller graphs, use ego graph first
            subgraph = nx.ego_graph(
                G, 
                origin_node, 
                radius=max(travel_times_seconds), 
                distance='travel_time'
            )
            times = nx.single_source_dijkstra_path_length(
                subgraph, 
                origin_node, 
                weight='travel_time'
            )
        
        # Create isochrone polygons
        isochrones = []
        
        for time_threshold in sorted(travel_times_seconds):
            reachable_nodes = [node for node, time in times.items() if time <= time_threshold]
            
            if len(reachable_nodes) < 3:  # Need at least 3 points for a polygon
                continue
                
            # Get node coordinates
            node_points = []
            for node in reachable_nodes:
                if node in G.nodes:
                    node_data = G.nodes[node]
                    node_points.append(Point(node_data['x'], node_data['y']))
            
            if len(node_points) < 3:
                continue
                
            # Create GeoDataFrame
            gdf_nodes = gpd.GeoDataFrame({'geometry': node_points})
            gdf_nodes.crs = "EPSG:4326"
            
            # Create convex hull
            try:
                convex_hull = gdf_nodes.unary_union.convex_hull
                
                # Simplify polygon
                if simplify_tolerance > 0:
                    convex_hull = convex_hull.simplify(simplify_tolerance / 111320)
                    
                # Extract coordinates
                polygon_coords = []
                if isinstance(convex_hull, Polygon) and not convex_hull.is_empty:
                    x, y = convex_hull.exterior.xy
                    coords = list(zip(x.tolist(), y.tolist()))
                    polygon_coords = [coords]
                    
                    # Calculate area
                    area_km2 = convex_hull.area * 111.32 * 111.32
                    
                    isochrones.append({
                        'travel_time_minutes': time_threshold / 60,
                        'area_km2': round(area_km2, 2),
                        'polygon_coordinates': polygon_coords,
                        'reachable_nodes': len(reachable_nodes)
                    })
                    
            except Exception as e:
                logger.warning(f"Error creating polygon for {time_threshold/60}min: {e}")
                continue
        
        duration = time.time() - start_time
        logger.info(f"Isochrone calculation completed in {duration:.2f} seconds")
        
        return {
            'center': {'latitude': latitude, 'longitude': longitude},
            'travel_mode': travel_mode,
            'isochrones': isochrones,
            'processing_time_seconds': duration,
            'graph_nodes': len(G.nodes),
            'graph_edges': len(G.edges)
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
    """Non-cached wrapper for calculate_isochrone_cached"""
    travel_times_tuple = tuple(sorted(travel_times))
    
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
        return polygon.simplify(simplify_tolerance / 111320)
    return polygon

def convert_polygons_to_geojson(isochrone_result):
    """Convert isochrone polygons to GeoJSON format"""
    features = []
    
    if 'isochrones' not in isochrone_result:
        return None
        
    for iso in isochrone_result['isochrones']:
        if not iso['polygon_coordinates']:
            continue
            
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Polygon',
                'coordinates': iso['polygon_coordinates']
            },
            'properties': {
                'travel_time_minutes': iso['travel_time_minutes'],
                'area_km2': iso['area_km2'],
                'reachable_nodes': iso.get('reachable_nodes', 0)
            }
        }
        features.append(feature)
    
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
        
    all_polygons = unary_union(polygons)
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
            'vertex_count': len(iso.get('polygon_coordinates', [[]])[0]) if iso.get('polygon_coordinates') else 0,
            'reachable_nodes': iso.get('reachable_nodes', 0)
        })
    
    return stats

def preload_popular_areas():
    """Preload graphs for popular areas (call this on startup)"""
    popular_cities = [
        (40.7128, -74.0060),  # New York
        (34.0522, -118.2437), # Los Angeles
        (41.8781, -87.6298),  # Chicago
        (29.7604, -95.3698),  # Houston
        (33.4484, -112.0740), # Phoenix
    ]
    
    def preload_city(lat, lon):
        try:
            for network_type in ['drive', 'walk', 'bike']:
                graph_cache.get_graph(lat, lon, distance=5000, network_type=network_type)
        except Exception as e:
            logger.error(f"Error preloading {lat}, {lon}: {e}")
    
    # Use thread pool for parallel preloading
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(preload_city, lat, lon) for lat, lon in popular_cities]
        for future in as_completed(futures, timeout=300):  # 5 minute timeout
            try:
                future.result()
            except Exception as e:
                logger.error(f"Preload task failed: {e}")

# Utility function to clear old cache files
def cleanup_old_cache(max_age_days=30):
    """Remove cache files older than max_age_days"""
    cache_folder = graph_cache.cache_folder
    cutoff_time = time.time() - (max_age_days * 24 * 3600)
    
    for filename in os.listdir(cache_folder):
        filepath = os.path.join(cache_folder, filename)
        if os.path.getmtime(filepath) < cutoff_time:
            try:
                os.remove(filepath)
                logger.info(f"Removed old cache file: {filename}")
            except Exception as e:
                logger.error(f"Error removing {filename}: {e}")