import os

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .database import DB_ENGINE, database_context, database_session
from .middleware import json_errors
from .views import routes

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://ads_user:ads_pass@127.0.0.1:54330/ads"
)


def create_app(database_url: str | None = None, *, engine: AsyncEngine | None = None):
    app = web.Application(
        middlewares=[json_errors, database_session], client_max_size=64 * 1024
    )
    app[DB_ENGINE] = engine if engine is not None else create_async_engine(
        database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        pool_pre_ping=True,
    )
    app.cleanup_ctx.append(database_context)
    app.add_routes(routes)
    return app
