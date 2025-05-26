from marshmallow import fields, validate, pre_dump
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from Models.Models import UserApiKey, UserApiKeyPermission
from Schemas import ma

class UserApiKeySchema(SQLAlchemyAutoSchema):
    class Meta:
        model = UserApiKey
        load_instance = True
        include_fk = True
        sqla_session = None
    
    api_key = fields.Str(dump_only=True)  # Never accept API key in input
    name = fields.Str(
        allow_none=True,
        validate=validate.Length(max=100)
    )
    expires_at = fields.DateTime(allow_none=True)
    is_active = fields.Bool(missing=True)
    
    # Nested permissions
    permissions = fields.Nested('UserApiKeyPermissionSchema', many=True, dump_only=True)
    
    @pre_dump
    def mask_api_key(self, obj, **kwargs):
        """Mask the API key for security"""
        if hasattr(obj, 'api_key') and obj.api_key:
            # Show only first 8 characters
            obj.api_key = f"{obj.api_key[:8]}{'*' * 24}"
        return obj

class UserApiKeyCreateSchema(UserApiKeySchema):
    class Meta(UserApiKeySchema.Meta):
        exclude = ['id', 'api_key', 'created_at']

class UserApiKeyPermissionSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = UserApiKeyPermission
        load_instance = True
        include_fk = True
        sqla_session = None
    
    api = fields.Nested('ApiSchema', dump_only=True, only=['id', 'name'])

class ApiKeyPermissionCreateSchema(UserApiKeyPermissionSchema):
    class Meta(UserApiKeyPermissionSchema.Meta):
        exclude = ['id', 'created_at']