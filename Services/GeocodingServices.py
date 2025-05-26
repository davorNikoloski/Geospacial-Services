import os
import logging
import requests
import time
from geopy.geocoders import Nominatim
from functools import lru_cache

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Nominatim geocoder with your app name
# This follows OSM usage policy by identifying your application
geocoder = Nominatim(user_agent="your_app_name")

# Cache for geocoding results to reduce API calls and improve performance
@lru_cache(maxsize=1000)
def geocode_address(address):
    """
    Convert an address to geographic coordinates (latitude, longitude)
    
    Args:
        address (str): The address to geocode
        
    Returns:
        dict: Dictionary containing location data or error message
    """
    try:
        logger.info(f"Geocoding address: {address}")
        start_time = time.time()
        
        # Perform geocoding
        location = geocoder.geocode(address, exactly_one=True, addressdetails=True)
        
        duration = time.time() - start_time
        logger.info(f"Geocoding completed in {duration:.2f} seconds")
        
        if location:
            result = {
                'latitude': location.latitude,
                'longitude': location.longitude,
                'display_name': location.address,
                'raw': location.raw
            }
            return result
        else:
            return {'error': 'Location not found'}
            
    except Exception as e:
        logger.error(f"Geocoding error: {str(e)}", exc_info=True)
        return {'error': str(e)}

# Cache for reverse geocoding results
@lru_cache(maxsize=1000)
def reverse_geocode(latitude, longitude):
    """
    Convert geographic coordinates to an address
    
    Args:
        latitude (float): Latitude coordinate
        longitude (float): Longitude coordinate
        
    Returns:
        dict: Dictionary containing address data or error message
    """
    try:
        logger.info(f"Reverse geocoding coordinates: {latitude}, {longitude}")
        start_time = time.time()
        
        # Perform reverse geocoding
        location = geocoder.reverse((latitude, longitude), exactly_one=True, language='en')
        
        duration = time.time() - start_time
        logger.info(f"Reverse geocoding completed in {duration:.2f} seconds")
        
        if location:
            result = {
                'address': location.address,
                'raw': location.raw
            }
            return result
        else:
            return {'error': 'Address not found for these coordinates'}
            
    except Exception as e:
        logger.error(f"Reverse geocoding error: {str(e)}", exc_info=True)
        return {'error': str(e)}

def batch_geocode(addresses):
    """
    Batch geocode multiple addresses
    
    Args:
        addresses (list): List of address strings
        
    Returns:
        dict: Dictionary of results for each address
    """
    results = {}
    for address in addresses:
        results[address] = geocode_address(address)
    return results

def get_location_details(latitude, longitude, detail_level='basic'):
    """
    Get additional location details like administrative boundaries
    
    Args:
        latitude (float): Latitude coordinate
        longitude (float): Longitude coordinate
        detail_level (str): Level of detail - 'basic' or 'full'
        
    Returns:
        dict: Dictionary with location details
    """
    try:
        reverse_result = reverse_geocode(latitude, longitude)
        
        if 'error' in reverse_result:
            return reverse_result
            
        # Extract basic location details from the raw response
        address_data = reverse_result.get('raw', {}).get('address', {})
        
        if detail_level == 'basic':
            return {
                'country': address_data.get('country'),
                'state': address_data.get('state'),
                'county': address_data.get('county'),
                'city': address_data.get('city') or address_data.get('town') or address_data.get('village'),
                'postcode': address_data.get('postcode'),
                'road': address_data.get('road')
            }
        else:
            # Return all available address components
            return {
                'address_components': address_data,
                'display_name': reverse_result.get('address')
            }
            
    except Exception as e:
        logger.error(f"Get location details error: {str(e)}", exc_info=True)
        return {'error': str(e)}