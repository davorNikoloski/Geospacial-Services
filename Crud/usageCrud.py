from Models.Models import ApiUsage, ApiAnalytics, Api
from Config.Config import db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, extract, and_
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UsageCRUD:
    
    @staticmethod
    def log_api_usage(usage_data):
        """Log an API usage event"""
        try:
            # Ensure required fields are present
            if 'api_id' not in usage_data or ('user_id' not in usage_data and 'api_key_id' not in usage_data):
                logger.error("Missing required fields in usage data")
                return None
                
            usage = ApiUsage(**usage_data)
            db.session.add(usage)
            db.session.commit()
            logger.info(f"Logged API usage for API {usage_data.get('api_id')}")
            return usage
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error logging API usage: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_usage_for_user(user_id, limit=100):
        """Get API usage for a user"""
        return (
            ApiUsage.query
            .filter_by(user_id=user_id)
            .order_by(ApiUsage.timestamp.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_usage_for_api(api_id, limit=100):
        """Get API usage for an API"""
        return (
            ApiUsage.query
            .filter_by(api_id=api_id)
            .order_by(ApiUsage.timestamp.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_usage_for_api_key(api_key_id, limit=100):
        """Get API usage for an API key"""
        return (
            ApiUsage.query
            .filter_by(api_key_id=api_key_id)
            .order_by(ApiUsage.timestamp.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def create_analytics(analytics_data):
        """Create analytics data for an API usage"""
        try:
            analytics = ApiAnalytics(**analytics_data)
            db.session.add(analytics)
            db.session.commit()
            logger.info(f"Created analytics record for usage {analytics_data.get('usage_id')}")
            return analytics
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error creating analytics: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_analytics_for_usage(usage_id):
        """Get analytics for a specific API usage"""
        return ApiAnalytics.query.filter_by(usage_id=usage_id).first()

    @staticmethod
    def get_analytics_for_user(user_id, limit=100):
        """Get analytics for a user"""
        return (
            ApiAnalytics.query
            .filter_by(user_id=user_id)
            .order_by(ApiAnalytics.timestamp.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_analytics_for_api(api_id, limit=100):
        """Get analytics for an API"""
        return (
            ApiAnalytics.query
            .filter_by(api_id=api_id)
            .order_by(ApiAnalytics.timestamp.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_usage_stats(user_id=None, api_id=None, time_period='day'):
        """
        Get usage statistics grouped by time period
        :param user_id: Optional user ID to filter by
        :param api_id: Optional API ID to filter by
        :param time_period: 'day', 'hour', or 'month'
        :return: Query results with counts grouped by time period
        """
        filters = {}
        if user_id:
            filters['user_id'] = user_id
        if api_id:
            filters['api_id'] = api_id

        if time_period == 'hour':
            time_group = extract('hour', ApiUsage.timestamp)
        elif time_period == 'month':
            time_group = extract('month', ApiUsage.timestamp)
        else:  # default to day
            time_group = func.date(ApiUsage.timestamp)

        return (
            db.session.query(
                time_group.label('time_period'),
                func.count().label('count'),
                func.avg(ApiUsage.response_time).label('avg_response_time'),
                func.sum(ApiUsage.request_size).label('total_request_size'),
                func.sum(ApiUsage.response_size).label('total_response_size')
            )
            .filter_by(**filters)
            .group_by(time_group)
            .order_by(time_group)
            .all()
        )

    @staticmethod
    def get_recent_activity(limit=10):
        """Get recent API activity across all users"""
        return (
            ApiUsage.query
            .order_by(ApiUsage.timestamp.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_user_usage_summary(user_id):
        """Get summary of API usage for a user"""
        return (
            db.session.query(
                ApiUsage.api_id,
                func.count().label('total_requests'),
                func.avg(ApiUsage.response_time).label('avg_response_time'),
                func.min(ApiUsage.timestamp).label('first_used'),
                func.max(ApiUsage.timestamp).label('last_used')
            )
            .filter_by(user_id=user_id)
            .group_by(ApiUsage.api_id)
            .all()
        )

    # ===== NEW ANALYTICS METHODS =====
    @staticmethod
    def get_route_analytics(user_id=None, api_id=None, time_range=None):
        """Get route analytics with geographic data"""
        try:
            query = db.session.query(
                ApiAnalytics.id,
                ApiAnalytics.user_id,
                ApiAnalytics.api_id,
                ApiAnalytics.start_latitude,
                ApiAnalytics.start_longitude,
                ApiAnalytics.end_latitude,
                ApiAnalytics.end_longitude,
                ApiAnalytics.distance_meters,
                ApiAnalytics.duration_seconds,
                ApiAnalytics.route_type,
                ApiAnalytics.timestamp
            )

            # Apply filters
            filters = []
            if user_id:
                filters.append(ApiAnalytics.user_id == user_id)
            if api_id:
                filters.append(ApiAnalytics.api_id == api_id)
            if time_range:
                start_date, end_date = time_range
                filters.append(ApiAnalytics.timestamp.between(start_date, end_date))

            if filters:
                query = query.filter(and_(*filters))

            return query.order_by(ApiAnalytics.timestamp.desc()).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting route analytics: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_geocoding_analytics(user_id=None, api_id=None, limit=100):
        """Get geocoding analytics data"""
        try:
            query = db.session.query(
                ApiAnalytics.id,
                ApiAnalytics.user_id,
                ApiAnalytics.api_id,
                ApiAnalytics.address,
                ApiAnalytics.formatted_address,
                ApiAnalytics.place_id,
                ApiAnalytics.location_type,
                ApiAnalytics.timestamp
            )

            if user_id:
                query = query.filter_by(user_id=user_id)
            if api_id:
                query = query.filter_by(api_id=api_id)

            return query.order_by(ApiAnalytics.timestamp.desc()).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting geocoding analytics: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_usage_analytics_summary(user_id=None, api_id=None):
        """Get summary statistics for analytics data"""
        try:
            query = db.session.query(
                func.count(ApiAnalytics.id).label('total_requests'),
                func.avg(ApiAnalytics.distance_meters).label('avg_distance'),
                func.avg(ApiAnalytics.duration_seconds).label('avg_duration'),
                func.max(ApiAnalytics.distance_meters).label('max_distance'),
                func.max(ApiAnalytics.duration_seconds).label('max_duration')
            )

            if user_id:
                query = query.filter_by(user_id=user_id)
            if api_id:
                query = query.filter_by(api_id=api_id)

            result = query.first()
            return {
                'total_requests': result.total_requests or 0,
                'avg_distance': float(result.avg_distance) if result.avg_distance else 0,
                'avg_duration': float(result.avg_duration) if result.avg_duration else 0,
                'max_distance': result.max_distance or 0,
                'max_duration': result.max_duration or 0
            }
        except SQLAlchemyError as e:
            logger.error(f"Error getting analytics summary: {str(e)}", exc_info=True)
            raise


    @staticmethod
    def get_user_api_usage_summary(user_id):
        """
        Get total number of APIs, how many were used by the user, and their names.
        """
        try:
            total_apis = db.session.query(func.count(Api.id)).scalar()

            used_apis = (
                db.session.query(Api.id, Api.name)
                .join(ApiUsage, Api.id == ApiUsage.api_id)
                .filter(ApiUsage.user_id == user_id)
                .distinct()
                .all()
            )

            return {
                'total_apis': total_apis,
                'used_apis_count': len(used_apis),
                'used_apis': [{'id': a.id, 'name': a.name} for a in used_apis]
            }

        except SQLAlchemyError as e:
            logger.error(f"Error getting API usage summary for user {user_id}: {str(e)}", exc_info=True)
            raise
        
    @staticmethod
    def get_route_type_distribution(user_id=None, api_id=None):
        """Get distribution of route types"""
        try:
            query = db.session.query(
                ApiAnalytics.route_type,
                func.count(ApiAnalytics.id).label('count')
            ).group_by(ApiAnalytics.route_type)

            if user_id:
                query = query.filter_by(user_id=user_id)
            if api_id:
                query = query.filter_by(api_id=api_id)

            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"Error getting route type distribution: {str(e)}", exc_info=True)
            raise