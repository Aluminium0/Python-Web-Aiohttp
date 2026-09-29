import asyncio

from aiohttp import web
from sqlalchemy import select
from werkzeug.datastructures import Authorization
from werkzeug.security import check_password_hash

from .database import DB_SESSION
from .models import User


def unauthorized():
    return web.HTTPUnauthorized(
        text="Valid email and password required",
        headers={"WWW-Authenticate": 'Basic realm="advertisements", charset="UTF-8"'},
    )


async def authenticate(request):
    credentials = Authorization.from_header(request.headers.get("Authorization"))
    if credentials is None or credentials.type != "basic":
        raise unauthorized()
    user = await request[DB_SESSION].scalar(
        select(User).where(User.email == credentials.username.lower())
    )
    # Password hashing is CPU-bound; keep it off the event loop.
    if user is None or not await asyncio.to_thread(
        check_password_hash, user.password_hash, credentials.password
    ):
        raise unauthorized()
    return user
