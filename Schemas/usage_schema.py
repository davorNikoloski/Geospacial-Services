from marshmallow import fields, validate
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from Models.Models import ApiUsage, ApiAnalytics
from Schemas import ma

class ApiUsageSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = ApiUsage
        load_instance = True
        include_fk = True
        sqla_session = None
    
    endpoint = fields.Str(allow_none=True, validate=validate.Length(max=255))
    response_time = fields.Float(allow_none=True, validate=validate.Range(min=0))
    status_code = fields.Int(allow_none=True, validate=validate.Range(min=100, max=599))
    ip_address = fields.Str(allow_none=True, validate=validate.Length(max=50))
    user_agent = fields.Str(allow_none=True, validate=validate.Length(max=500))
    
    # Nested relationships
    user = fields.Nested('UserPublicSchema', dump_only=True, only=['id', 'username'])
    api = fields.Nested('ApiSchema', dump_only=True, only=['id', 'name'])

class ApiAnalyticsSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = ApiAnalytics
        load_instance = True
        include_fk = True
        sqla_session = None
    
    # Geographic fields with validation
    start_latitude = fields.Decimal(
        allow_none=True,
        validate=validate.Range(min=-90, max=90)
    )
    start_longitude = fields.Decimal(
        allow_none=True,
        validate=validate.Range(min=-180, max=180)
    )
    end_latitude = fields.Decimal(
        allow_none=True,
        validate=validate.Range(min=-90, max=90)
    )
    end_longitude = fields.Decimal(
        allow_none=True,
        validate=validate.Range(min=-180, max=180)
    )
    
    # Validated fields
    distance_meters = fields.Int(allow_none=True, validate=validate.Range(min=0))
    duration_seconds = fields.Int(allow_none=True, validate=validate.Range(min=0))
    waypoints_count = fields.Int(allow_none=True, validate=validate.Range(min=0))
    route_type = fields.Str(
        allow_none=True,
        validate=validate.OneOf(['driving', 'walking', 'cycling', 'transit'])
    )

class UsageCreateSchema(ApiUsageSchema):
    class Meta(ApiUsageSchema.Meta):
        exclude = ['id', 'created_at', 'modified_at']

class AnalyticsCreateSchema(ApiAnalyticsSchema):
    class Meta(ApiAnalyticsSchema.Meta):
        exclude = ['id', 'created_at', 'modified_at']