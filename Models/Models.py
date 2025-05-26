from Config.Config import db
from datetime import datetime
from sqlalchemy import Numeric  # FIX: Import Numeric for decimal columns

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column('id', db.Integer, primary_key=True)
    username = db.Column('username', db.String(255), unique=True, nullable=False)
    firstname = db.Column('firstname', db.String(255), nullable=False)
    lastname = db.Column('lastname', db.String(255), nullable=False)
    email = db.Column('email', db.String(255), unique=True, nullable=False)
    password = db.Column('password', db.String(255), nullable=False)
    country = db.Column('country', db.String(100), nullable=True)
    created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    modified_at = db.Column('modified_at', db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    api_keys = db.relationship('UserApiKey', backref='user', lazy=True)
    api_usages = db.relationship('ApiUsage', backref='user', lazy=True)
    analytics = db.relationship('ApiAnalytics', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'


class Api(db.Model):
    __tablename__ = 'apis'

    id = db.Column('id', db.Integer, primary_key=True)
    name = db.Column('name', db.String(100), unique=True, nullable=False)
    description = db.Column('description', db.Text, nullable=True)
    created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)

    # Relationships
    api_keys = db.relationship('UserApiKeyPermission', backref='api', lazy=True)
    api_usages = db.relationship('ApiUsage', backref='api', lazy=True)
    analytics = db.relationship('ApiAnalytics', backref='api', lazy=True)

    def __repr__(self):
        return f'<Api {self.name}>'


class UserApiKey(db.Model):
    __tablename__ = 'user_api_keys'

    id = db.Column('id', db.Integer, primary_key=True)
    user_id = db.Column('user_id', db.Integer, db.ForeignKey('users.id'), nullable=False)
    api_key = db.Column('api_key', db.String(255), unique=True, nullable=False)
    name = db.Column('name', db.String(100), nullable=True)
    created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    expires_at = db.Column('expires_at', db.DateTime, nullable=True)
    is_active = db.Column('is_active', db.Boolean, default=True)

    # Relationships
    permissions = db.relationship('UserApiKeyPermission', backref='api_key', lazy=True, cascade="all, delete-orphan")
    usages = db.relationship('ApiUsage', backref='api_key', lazy=True)

    def __repr__(self):
        return f'<UserApiKey {self.api_key[:8]}...>'


class UserApiKeyPermission(db.Model):
    __tablename__ = 'user_api_key_permissions'

    id = db.Column('id', db.Integer, primary_key=True)
    api_key_id = db.Column('api_key_id', db.Integer, db.ForeignKey('user_api_keys.id'), nullable=False)
    api_id = db.Column('api_id', db.Integer, db.ForeignKey('apis.id'), nullable=False)
    created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<UserApiKeyPermission {self.api_key_id}:{self.api_id}>'


class ApiUsage(db.Model):
    __tablename__ = 'api_usage'

    id = db.Column('id', db.Integer, primary_key=True)
    user_id = db.Column('user_id', db.Integer, db.ForeignKey('users.id'), nullable=False)
    api_id = db.Column('api_id', db.Integer, db.ForeignKey('apis.id'), nullable=False)
    api_key_id = db.Column('api_key_id', db.Integer, db.ForeignKey('user_api_keys.id'), nullable=False)
    timestamp = db.Column('timestamp', db.DateTime, default=datetime.utcnow)
    endpoint = db.Column('endpoint', db.String(255), nullable=True)
    response_time = db.Column('response_time', db.Float, nullable=True)
    status_code = db.Column('status_code', db.Integer, nullable=True)
    ip_address = db.Column('ip_address', db.String(50), nullable=True)
    request_size = db.Column('request_size', db.Integer, nullable=True)
    response_size = db.Column('response_size', db.Integer, nullable=True)
    user_agent = db.Column('user_agent', db.String(500), nullable=True)
    created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    modified_at = db.Column('modified_at', db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    analytics = db.relationship('ApiAnalytics', backref='usage', lazy=True)

    def __repr__(self):
        return f'<ApiUsage {self.user_id}:{self.api_id} at {self.timestamp}>'


class ApiAnalytics(db.Model):
    __tablename__ = 'api_analytics'

    id = db.Column('id', db.Integer, primary_key=True)
    usage_id = db.Column('usage_id', db.Integer, db.ForeignKey('api_usage.id'), nullable=False)
    user_id = db.Column('user_id', db.Integer, db.ForeignKey('users.id'), nullable=False)
    api_id = db.Column('api_id', db.Integer, db.ForeignKey('apis.id'), nullable=False)

    # Polyline and geographic data
    polyline = db.Column('polyline', db.Text, nullable=True)
    start_latitude = db.Column('start_latitude', Numeric(10, 8), nullable=True)
    start_longitude = db.Column('start_longitude', Numeric(11, 8), nullable=True)
    end_latitude = db.Column('end_latitude', Numeric(10, 8), nullable=True)
    end_longitude = db.Column('end_longitude', Numeric(11, 8), nullable=True)

    # Distance and duration data
    distance_meters = db.Column('distance_meters', db.Integer, nullable=True)
    duration_seconds = db.Column('duration_seconds', db.Integer, nullable=True)

    # Additional analytics data
    waypoints_count = db.Column('waypoints_count', db.Integer, nullable=True)
    route_type = db.Column('route_type', db.String(50), nullable=True)

    # Geocoding specific data
    address = db.Column('address', db.String(500), nullable=True)
    formatted_address = db.Column('formatted_address', db.String(500), nullable=True)
    place_id = db.Column('place_id', db.String(255), nullable=True)
    location_type = db.Column('location_type', db.String(100), nullable=True)

    # Metadata
    raw_request = db.Column('raw_request', db.Text, nullable=True)

    # Standard tracking columns
    timestamp = db.Column('timestamp', db.DateTime, default=datetime.utcnow)
    created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    modified_at = db.Column('modified_at', db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = db.Column('is_archived', db.Boolean, default=False)

    def __repr__(self):
        return f'<ApiAnalytics {self.usage_id} for user {self.user_id}>'
