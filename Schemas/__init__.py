from flask_marshmallow import Marshmallow
from marshmallow import fields, validate, ValidationError
from datetime import datetime

ma = Marshmallow()

class BaseSchema:
    """Base schema with common field configurations"""
    
    # Common field validators
    required_string = fields.Str(required=True, validate=validate.Length(min=1))
    optional_string = fields.Str(allow_none=True)
    email_field = fields.Email(required=True)
    
    # Common timestamp fields
    created_at = fields.DateTime(dump_only=True)
    modified_at = fields.DateTime(dump_only=True)