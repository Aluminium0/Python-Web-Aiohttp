import os
from uuid import uuid4

import pytest
import pytest_asyncio
from aiohttp import encode_basic_auth
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from advertisements import DEFAULT_DATABASE_URL, create_app


@pytest_asyncio.fixture
async def database_engine():
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    schema = f"test_{uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    async with admin_engine.begin() as connection:
        await connection.execute(CreateSchema(schema))
    # Isolate every test without deleting tables or rows in the real application.
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def client(aiohttp_client, database_engine):
    client = await aiohttp_client(create_app(engine=database_engine))
    yield client
    await client.close()


@pytest.fixture
def credentials():
    return {"email": "owner@example.com", "password": "homework-password"}


@pytest_asyncio.fixture
async def owner(client, credentials):
    response = await client.post("/users", json=credentials)
    assert response.status == 201
    return await response.json()


@pytest.fixture
def auth(owner, credentials):
    return {"Authorization": encode_basic_auth(credentials["email"], credentials["password"])}


@pytest_asyncio.fixture
async def stranger_auth(client):
    response = await client.post(
        "/users", json={"email": "other@example.com", "password": "another-password"}
    )
    assert response.status == 201
    return {"Authorization": encode_basic_auth("other@example.com", "another-password")}


@pytest.fixture
def ad_data():
    return {"title": "Desk for sale", "description": "Good condition"}


@pytest_asyncio.fixture
async def advertisement(client, auth, ad_data):
    response = await client.post("/advertisements", json=ad_data, headers=auth)
    assert response.status == 201
    return await response.json()
