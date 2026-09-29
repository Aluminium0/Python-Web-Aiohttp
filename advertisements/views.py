import asyncio

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .auth import authenticate
from .database import DB_SESSION
from .models import Advertisement, User
from .schemas import AdvertisementSchema, UserSchema, load_json

routes = web.RouteTableDef()
user_schema = UserSchema()
advertisement_schema = AdvertisementSchema()


@routes.get("/")
async def index(request):
    return web.json_response(
        {
            "name": "Aiohttp Advertisements API",
            "advertisements": "/advertisements",
            "registration": "/users",
        }
    )


@routes.post("/users")
async def register_user(request):
    data = await load_json(request, user_schema)
    user = User(
        email=data["email"].lower(),
        password_hash=await asyncio.to_thread(generate_password_hash, data["password"]),
    )
    session = request[DB_SESSION]
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise web.HTTPConflict(text="This email is already registered") from error
    return web.json_response({"id": user.id, "email": user.email}, status=201)


@routes.get("/advertisements")
async def list_advertisements(request):
    advertisements = await request[DB_SESSION].scalars(
        select(Advertisement).order_by(Advertisement.id)
    )
    return web.json_response([advertisement.to_dict() for advertisement in advertisements])


async def find_advertisement(request):
    value = request.match_info["advertisement_id"]
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise web.HTTPNotFound(text="Advertisement not found")
    advertisement_id = int(value)
    if not 0 < advertisement_id <= 2147483647:
        raise web.HTTPNotFound(text="Advertisement not found")
    advertisement = await request[DB_SESSION].get(Advertisement, advertisement_id)
    if advertisement is None:
        raise web.HTTPNotFound(text="Advertisement not found")
    return advertisement


async def owned_advertisement(request, user):
    advertisement = await find_advertisement(request)
    if advertisement.owner_id != user.id:
        raise web.HTTPForbidden(text="Only the owner may modify this advertisement")
    return advertisement


@routes.get("/advertisements/{advertisement_id}", name="advertisement-detail")
async def get_advertisement(request):
    advertisement = await find_advertisement(request)
    return web.json_response(advertisement.to_dict())


@routes.post("/advertisements")
async def create_advertisement(request):
    user = await authenticate(request)
    data = await load_json(request, advertisement_schema)
    advertisement = Advertisement(**data, owner_id=user.id)
    session = request[DB_SESSION]
    session.add(advertisement)
    await session.commit()
    location = request.app.router["advertisement-detail"].url_for(
        advertisement_id=str(advertisement.id)
    )
    return web.json_response(
        advertisement.to_dict(), status=201, headers={"Location": str(location)}
    )


@routes.patch("/advertisements/{advertisement_id}")
async def update_advertisement(request):
    user = await authenticate(request)
    advertisement = await owned_advertisement(request, user)
    data = await load_json(request, advertisement_schema, partial=True)
    if not data:
        raise web.HTTPBadRequest(text="Provide title or description to update")
    for field, value in data.items():
        setattr(advertisement, field, value)
    await request[DB_SESSION].commit()
    return web.json_response(advertisement.to_dict())


@routes.delete("/advertisements/{advertisement_id}")
async def delete_advertisement(request):
    user = await authenticate(request)
    advertisement = await owned_advertisement(request, user)
    session = request[DB_SESSION]
    await session.delete(advertisement)
    await session.commit()
    return web.Response(status=204)
