from marshmallow import fields, validate
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from Models.Models import Api
from Schemas import ma

class ApiSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Api
        load_instance = True
        include_fk = True
        sqla_session = None
    
    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100)
    )
    description = fields.Str(allow_none=True)

class ApiCreateSchema(ApiSchema):
    class Meta(ApiSchema.Meta):
        exclude = ['id', 'created_at']

class ApiUpdateSchema(ApiSchema):
    class Meta(ApiSchema.Meta):
        exclude = ['id', 'created_at']
        partial = True