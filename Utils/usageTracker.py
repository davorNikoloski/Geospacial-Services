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
    Decorator to track API usage and create analytics
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
                
                # Handle response types to get status code and response size
                if isinstance(response, Response):
                    status_code = response.status_code
                    response_size = len(response.data) if response.data else 0
                elif isinstance(response, tuple) and len(response) >= 2:
                    response_data, status_code = response[0], response[1]
                    if isinstance(response_data, Response):
                        response_size = len(response_data.data) if response_data.data else 0
                    else:
                        response_size = len(json.dumps(response_data)) if response_data else 0
                else:
                    logger.error(f"Unexpected response type: {type(response)}")
                    status_code = 500
                    response_size = 0
                
                # Prepare usage data
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
                        
                        # Prepare analytics data with request body
                        analytics_data = {
                            'usage_id': usage.id,
                            'user_id': user_id,
                            'api_id': api_id,
                            'timestamp': datetime.utcnow(),
                            'raw_request': str(request_body)  # Add the request body here
                        }
                        
                        # Create analytics record
                        UsageCRUD.create_analytics(analytics_data)
                    except Exception as e:
                        logger.error(f"Error tracking API usage: {str(e)}", exc_info=True)
                else:
                    logger.warning("Skipping usage tracking - no user_id available")
                
            except Exception as e:
                logger.error(f"Error in usage tracking wrapper: {str(e)}", exc_info=True)
            
            return response
        return decorated_function
    return decorator