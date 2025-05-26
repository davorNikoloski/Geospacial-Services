import re
from flask import url_for, Flask, request, jsonify
#from db import add_location, get_locations_by_name, get_location_by_coordinates
import requests
from Config.Config import app
from geopy.distance import geodesic, distance as geopy_distance
from geopy import Point
from shapely.geometry import LineString, Point as ShapelyPoint
from datetime import datetime
import math
import polyline
import threading

#from ip2geotools.databases.noncommercial import DbIpCity

MAPBOX_API_KEY = app.config["MAPBOX_API_KEY"]

def send_mail():
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def is_valid_email(email):
    # Regular expression to check email format
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email)

def is_password_complex(password):
    # Check if password contains at least one uppercase letter and one number
    return bool(re.search(r"[A-Z]", password)) and bool(re.search(r"\d", password))

def send_verification_email(email, verification_code):
    # Send email logic here
    verification_link = url_for('verify_user', code=verification_code, _external=True)
    send_mail("Email Verification", f"Your verification code is {verification_code}. Click the link to verify: {verification_link}", email)

def is_user_authenticated(user):
    return user.get('u_authenticated', False)

def send_reset_email(email, reset_link):
    subject = "Password Reset Request"
    body = f"Click the link to reset your password: {reset_link}"
    send_mail(subject, body, email)
    
def get_client_ip():
    if 'X-Forwarded-For' in request.headers:
        ip = request.headers['X-Forwarded-For'].split(',')[0].strip()
    else:
        ip = request.remote_addr
    return ip

import requests

def get_country_code(ip_address):
    # Print the IP address for debugging
    print(f"Received IP address: {ip_address}")
    
    # List of known bogon IP addresses (for simplicity, we'll use just localhost here)
    bogon_ips = ['127.0.0.1', '::1']
    
    # Check if the IP address is a bogon IP
    if ip_address in bogon_ips:
        return 'XX'  # Default country code for bogon IPs

    api_key = '6953a9d3c63e4cfbbef6914c78d194f3'
    url = f'https://api.ipgeolocation.io/ipgeo?apiKey={api_key}&ip={ip_address}'

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        
        # Print the response data for debugging
        print(f"API response data: {data}")
        
        # Return the country code, default to 'XX' if not present
        return data.get('country_code2', 'XX')
    
    except requests.RequestException as e:
        # Handle request errors (e.g., network issues, invalid API key)
        print(f"Error in get_country_code with ipgeolocation.io: {e}")
        return 'XX'

def generate_code(package_id=None, country_code='XX'):
    timestamp = datetime.now().strftime("%d%m%Y%H%M%S")
    if package_id:
        return f"{country_code}{timestamp}{package_id}"
    else:
        return f"{country_code}{timestamp}"


