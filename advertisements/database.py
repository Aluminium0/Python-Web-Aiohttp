from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from .models import Base

DB_ENGINE = web.AppKey("database_engine", AsyncEngine)
DB_SESSION = web.RequestKey("database_session", AsyncSession)


async def database_context(app):
    engine = app[DB_ENGINE]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield
    finally:
        await engine.dispose()


@web.middleware
async def database_session(request, handler):
    async with AsyncSession(request.app[DB_ENGINE], expire_on_commit=False) as session:
        request[DB_SESSION] = session
        return await handler(request)
