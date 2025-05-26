from marshmallow import fields, validate, post_load, validates_schema, ValidationError
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from Models.Models import User
from Schemas import ma

class UserSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = User
        load_instance = True
        include_fk = True
        sqla_session = None  # Will be set in app factory
    
    # Override specific fields with validation
    username = fields.Str(
        required=True, 
        validate=validate.Length(min=3, max=255)
    )
    email = fields.Email(required=True)
    password = fields.Str(
        required=True, 
        validate=validate.Length(min=8),
        load_only=True  # Never serialize password
    )
    firstname = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255)
    )
    lastname = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255)
    )
    country = fields.Str(
        allow_none=True,
        validate=validate.Length(max=100)
    )
    
    # Nested relationships (optional)
    api_keys = fields.Nested('UserApiKeySchema', many=True, dump_only=True, exclude=['user'])
    
    @validates_schema
    def validate_user_data(self, data, **kwargs):
        """Custom validation for user data"""
        if 'username' in data and ' ' in data['username']:
            raise ValidationError('Username cannot contain spaces', 'username')

# Different schemas for different use cases
class UserCreateSchema(UserSchema):
    """Schema for user creation"""
    class Meta(UserSchema.Meta):
        exclude = ['id', 'created_at', 'modified_at']

class UserUpdateSchema(UserSchema):
    """Schema for user updates"""
    class Meta(UserSchema.Meta):
        exclude = ['id', 'created_at', 'modified_at', 'username']  # Username shouldn't be updatable
        partial = True  # Allow partial updates

class UserPublicSchema(UserSchema):
    """Public user schema (no sensitive data)"""
    class Meta(UserSchema.Meta):
        exclude = ['password', 'email']