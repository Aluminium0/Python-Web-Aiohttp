from json import JSONDecodeError

from aiohttp import web
from marshmallow import Schema, ValidationError, fields, validate


def not_blank(value):
    if not value.strip():
        raise ValidationError("Must not be blank.")


class UserSchema(Schema):
    email = fields.Email(required=True, validate=validate.Length(max=254))
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))


class AdvertisementSchema(Schema):
    title = fields.String(
        required=True, validate=[validate.Length(max=200), not_blank]
    )
    description = fields.String(
        required=True, validate=[validate.Length(max=10000), not_blank]
    )


async def load_json(request, schema, *, partial=False):
    content_type = request.content_type
    if content_type != "application/json" and not (
        content_type.startswith("application/") and content_type.endswith("+json")
    ):
        raise web.HTTPUnsupportedMediaType(text="Send an application/json body")
    try:
        data = await request.json()
    except (JSONDecodeError, UnicodeDecodeError) as error:
        raise web.HTTPBadRequest(text="Malformed JSON") from error
    return schema.load(data, partial=partial)
