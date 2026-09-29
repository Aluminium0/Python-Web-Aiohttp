import asyncio
import threading
from unittest.mock import AsyncMock

import pytest
from aiohttp import encode_basic_auth, web
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from advertisements import auth, create_app, views
from advertisements.database import DB_ENGINE, DB_SESSION
from advertisements.models import User


async def test_password_work_runs_outside_event_loop(client, credentials, ad_data, monkeypatch):
    loop_thread = threading.get_ident()
    real_hash = views.generate_password_hash
    real_check = auth.check_password_hash
    calls = []

    def checked_hash(password):
        assert threading.get_ident() != loop_thread
        calls.append("hash")
        return real_hash(password)

    def checked_password(password_hash, password):
        assert threading.get_ident() != loop_thread
        calls.append("check")
        return real_check(password_hash, password)

    monkeypatch.setattr(views, "generate_password_hash", checked_hash)
    monkeypatch.setattr(auth, "check_password_hash", checked_password)
    response = await client.post("/users", json=credentials)
    assert response.status == 201
    response = await client.post(
        "/advertisements", json=ad_data,
        headers={"Authorization": encode_basic_auth(credentials["email"], credentials["password"])},
    )
    assert response.status == 201
    assert calls == ["hash", "check"]


async def test_parallel_requests_get_separate_sessions(database_engine, aiohttp_client):
    app = create_app(engine=database_engine)
    sessions = []
    both_started = asyncio.Event()

    async def inspect_session(request):
        sessions.append(request[DB_SESSION])
        if len(sessions) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=5)
        assert await request[DB_SESSION].scalar(select(1)) == 1
        return web.json_response({"ok": True})

    app.router.add_get("/inspect", inspect_session)
    client = await aiohttp_client(app)
    responses = await asyncio.gather(client.get("/inspect"), client.get("/inspect"))
    assert [response.status for response in responses] == [200, 200]
    assert sessions[0] is not sessions[1]
    await client.close()


async def test_failure_rolls_back_and_hides_internal_details(database_engine, aiohttp_client):
    app = create_app(engine=database_engine)

    async def broken_handler(request):
        request[DB_SESSION].add(User(email="rollback@example.com", password_hash="test"))
        await request[DB_SESSION].flush()
        raise RuntimeError("private internal details")

    app.router.add_post("/broken", broken_handler)
    client = await aiohttp_client(app)
    response = await client.post("/broken")
    assert response.status == 500
    assert await response.json() == {"error": "Internal server error"}
    async with AsyncSession(database_engine) as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0
    await client.close()


async def test_database_engine_is_disposed_on_shutdown(database_engine, aiohttp_client, monkeypatch):
    dispose = AsyncMock(wraps=database_engine.dispose)
    monkeypatch.setattr(type(database_engine), "dispose", dispose)
    client = await aiohttp_client(create_app(engine=database_engine))
    response = await client.get("/advertisements")
    assert response.status == 200
    await client.close()
    dispose.assert_awaited_once_with()


async def test_database_url_from_environment(monkeypatch):
    url = "postgresql+asyncpg://example:example@localhost:5432/example"
    monkeypatch.setenv("DATABASE_URL", url)
    app = create_app()
    assert app[DB_ENGINE].url.render_as_string(hide_password=False) == url
    await app[DB_ENGINE].dispose()


@pytest.mark.parametrize("args,host,port", [
    ([], "127.0.0.1", 8080),
    (["--host", "0.0.0.0", "--port", "8081"], "0.0.0.0", 8081),
])
def test_cli_options(monkeypatch, args, host, port):
    from advertisements import __main__ as cli

    application = object()
    calls = []
    monkeypatch.setattr("sys.argv", ["advertisements", *args])
    monkeypatch.setattr(cli, "create_app", lambda: application)
    monkeypatch.setattr(cli.web, "run_app", lambda app, **kwargs: calls.append((app, kwargs)))
    cli.main()
    assert calls == [(application, {"host": host, "port": port})]
