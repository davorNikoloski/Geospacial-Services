from flask import Blueprint, request, jsonify, g
from Crud.usageCrud import UsageCRUD
from Routes.userRoutes import jwt_auth_required, admin_required
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

usage_api = Blueprint('usage_api', __name__, url_prefix='/api/users')

# ===== USAGE TRACKING ROUTES =====
@usage_api.route('/<int:user_id>/usage', methods=['GET'])
@jwt_auth_required
def get_user_usage(user_id):
    """Get API usage for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            logger.warning(f"User {g.current_user.id} attempted to view usage for user {user_id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        limit = min(int(request.args.get('limit', 100)), 1000)
        usage = UsageCRUD.get_usage_for_user(user_id, limit)
        response = [{
            'id': u.id,
            'user_id': u.user_id,
            'api_id': u.api_id,
            'api_key_id': u.api_key_id,
            'timestamp': u.timestamp.isoformat(),
            'endpoint': u.endpoint,
            'response_time': u.response_time,
            'status_code': u.status_code,
            'ip_address': u.ip_address,
            'request_size': u.request_size,
            'response_size': u.response_size,
            'user_agent': u.user_agent,
            'created_at': u.created_at.isoformat(),
            'modified_at': u.modified_at.isoformat()
        } for u in usage]
        logger.info(f"Retrieved {len(usage)} usage records for user {user_id}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting usage for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@usage_api.route('/<int:user_id>/usage/stats', methods=['GET'])
@jwt_auth_required
def get_user_usage_stats(user_id):
    """Get usage statistics for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        time_period = request.args.get('period', 'day')
        if time_period not in ['hour', 'day', 'month']:
            time_period = 'day'

        stats = UsageCRUD.get_usage_stats(user_id=user_id, time_period=time_period)
        
        response = [{
            'time_period': stat.time_period.isoformat() if hasattr(stat.time_period, 'isoformat') else stat.time_period,
            'count': stat.count,
            'avg_response_time': float(stat.avg_response_time) if stat.avg_response_time else 0,
            'total_request_size': stat.total_request_size or 0,
            'total_response_size': stat.total_response_size or 0
        } for stat in stats]

        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting usage stats for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@usage_api.route('/<int:user_id>/usage/summary', methods=['GET'])
@jwt_auth_required
def get_user_usage_summary(user_id):
    """Get usage summary for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        summary = UsageCRUD.get_user_usage_summary(user_id)
        
        response = [{
            'api_id': item.api_id,
            'total_requests': item.total_requests,
            'avg_response_time': float(item.avg_response_time) if item.avg_response_time else 0,
            'first_used': item.first_used.isoformat() if item.first_used else None,
            'last_used': item.last_used.isoformat() if item.last_used else None
        } for item in summary]

        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting usage summary for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

# ===== NEW ANALYTICS ROUTES =====
@usage_api.route('/<int:user_id>/analytics/routes', methods=['GET'])
@jwt_auth_required
def get_user_route_analytics(user_id):
    """Get route analytics data for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        api_id = request.args.get('api_id', type=int)
        days = request.args.get('days', type=int, default=30)
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        time_range = (start_date, end_date)

        routes = UsageCRUD.get_route_analytics(
            user_id=user_id,
            api_id=api_id,
            time_range=time_range
        )

        response = [{
            'id': r.id,
            'user_id': r.user_id,
            'api_id': r.api_id,
            'start_point': {
                'latitude': float(r.start_latitude) if r.start_latitude else None,
                'longitude': float(r.start_longitude) if r.start_longitude else None
            },
            'end_point': {
                'latitude': float(r.end_latitude) if r.end_latitude else None,
                'longitude': float(r.end_longitude) if r.end_longitude else None
            },
            'distance_meters': r.distance_meters,
            'duration_seconds': r.duration_seconds,
            'route_type': r.route_type,
            'timestamp': r.timestamp.isoformat()
        } for r in routes]

        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting route analytics for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@usage_api.route('/<int:user_id>/analytics/geocoding', methods=['GET'])
@jwt_auth_required
def get_user_geocoding_analytics(user_id):
    """Get geocoding analytics data for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        api_id = request.args.get('api_id', type=int)
        limit = min(request.args.get('limit', 100, type=int), 1000)

        geocoding_data = UsageCRUD.get_geocoding_analytics(
            user_id=user_id,
            api_id=api_id,
            limit=limit
        )

        response = [{
            'id': g.id,
            'user_id': g.user_id,
            'api_id': g.api_id,
            'address': g.address,
            'formatted_address': g.formatted_address,
            'place_id': g.place_id,
            'location_type': g.location_type,
            'timestamp': g.timestamp.isoformat()
        } for g in geocoding_data]

        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting geocoding analytics for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@usage_api.route('/<int:user_id>/analytics/summary', methods=['GET'])
@jwt_auth_required
def get_user_analytics_summary(user_id):
    """Get analytics summary for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        api_id = request.args.get('api_id', type=int)

        summary = UsageCRUD.get_usage_analytics_summary(
            user_id=user_id,
            api_id=api_id
        )

        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error getting analytics summary for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@usage_api.route('/<int:user_id>/analytics/route-types', methods=['GET'])
@jwt_auth_required
def get_user_route_type_distribution(user_id):
    """Get route type distribution for a user"""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        api_id = request.args.get('api_id', type=int)

        distribution = UsageCRUD.get_route_type_distribution(
            user_id=user_id,
            api_id=api_id
        )

        response = [{
            'route_type': d.route_type or 'unknown',
            'count': d.count
        } for d in distribution]

        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting route type distribution for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500
    
@usage_api.route('/<int:user_id>/analytics/api-usage-summary', methods=['GET'])
@jwt_auth_required
def get_user_api_usage_summary(user_id):
    """Return how many APIs exist, how many were used by the user, and which ones."""
    try:
        if not g.current_user.is_admin and g.current_user.id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        summary = UsageCRUD.get_user_api_usage_summary(user_id)

        return jsonify(summary)

    except Exception as e:
        logger.error(f"Error getting API usage summary for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500
