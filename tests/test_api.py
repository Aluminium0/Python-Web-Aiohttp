import asyncio
from datetime import datetime, timezone

import pytest
from aiohttp import encode_basic_auth
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from werkzeug.security import check_password_hash

from advertisements import create_app
from advertisements.models import Advertisement, User


async def test_index_and_empty_list(client):
    response = await client.get("/")
    assert response.status == 200
    assert (await response.json())["advertisements"] == "/advertisements"
    response = await client.get("/advertisements")
    assert response.status == 200
    assert await response.json() == []


async def test_registration_hashes_password(client, database_engine, credentials):
    response = await client.post("/users", json=credentials)
    assert response.status == 201
    data = await response.json()
    assert set(data) == {"id", "email"}
    assert data["email"] == credentials["email"]
    async with AsyncSession(database_engine) as session:
        user = await session.get(User, data["id"])
        assert user.password_hash != credentials["password"]
        assert await asyncio.to_thread(
            check_password_hash, user.password_hash, credentials["password"]
        )


async def test_duplicate_email_is_case_insensitive(client, owner, credentials):
    response = await client.post(
        "/users", json={**credentials, "email": credentials["email"].upper()}
    )
    assert response.status == 409
    assert "error" in await response.json()


async def test_concurrent_registration_has_one_winner(client, credentials, database_engine):
    responses = await asyncio.gather(
        client.post("/users", json=credentials),
        client.post("/users", json=credentials),
    )
    assert sorted(response.status for response in responses) == [201, 409]
    async with AsyncSession(database_engine) as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"email": "bad", "password": "long-password"},
        {"email": "user@example.com", "password": "short"},
        {"email": "user@example.com", "password": "x" * 129},
        {"email": "user@example.com", "password": None},
        {"email": "user@example.com", "password": 12345678},
        {"email": "user@example.com", "password": "long-password", "id": 1},
        [],
        "not an object",
    ],
)
async def test_invalid_registration(client, data, database_engine):
    response = await client.post("/users", json=data)
    assert response.status == 400
    assert "error" in await response.json()
    async with AsyncSession(database_engine) as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_create_and_public_read(client, auth, owner, ad_data):
    before = datetime.now(timezone.utc)
    response = await client.post("/advertisements", json=ad_data, headers=auth)
    assert response.status == 201
    created = await response.json()
    assert set(created) == {"id", "title", "description", "created_at", "owner"}
    assert created["title"] == ad_data["title"]
    assert created["description"] == ad_data["description"]
    assert created["owner"] == owner["id"]
    assert before <= datetime.fromisoformat(created["created_at"]) <= datetime.now(timezone.utc)
    assert response.headers["Location"] == f"/advertisements/{created['id']}"

    response = await client.get(response.headers["Location"])
    assert response.status == 200
    assert await response.json() == created
    response = await client.get("/advertisements")
    assert response.status == 200
    assert await response.json() == [created]


async def test_public_list_contains_ads_from_multiple_owners(
    client, advertisement, stranger_auth, ad_data
):
    response = await client.post("/advertisements", json=ad_data, headers=stranger_auth)
    assert response.status == 201
    second = await response.json()
    response = await client.get("/advertisements")
    assert response.status == 200
    assert await response.json() == [advertisement, second]


@pytest.mark.parametrize("method,path", [
    ("post", "/advertisements"),
    ("patch", "/advertisements/1"),
    ("delete", "/advertisements/1"),
])
async def test_mutations_require_authentication(client, method, path, ad_data):
    response = await client.request(method, path, json=ad_data)
    assert response.status == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic ")
    assert "error" in await response.json()


@pytest.mark.parametrize("header", [
    "Bearer fake-token",
    "Basic invalid-base64!",
    encode_basic_auth("owner@example.com", "wrong-password"),
    encode_basic_auth("missing@example.com", "homework-password"),
    "Basic /zo=",
])
async def test_bad_credentials(client, owner, ad_data, header):
    response = await client.post(
        "/advertisements", json=ad_data, headers={"Authorization": header}
    )
    assert response.status == 401
    assert "error" in await response.json()


async def test_email_login_is_case_insensitive(client, owner, credentials, ad_data):
    response = await client.post(
        "/advertisements", json=ad_data,
        headers={"Authorization": encode_basic_auth(credentials["email"].upper(), credentials["password"])},
    )
    assert response.status == 201


@pytest.mark.parametrize("data", [
    {},
    {"title": "Desk"},
    {"title": " ", "description": "Good"},
    {"title": "Desk", "description": "\t"},
    {"title": None, "description": "Good"},
    {"title": 1, "description": "Good"},
    {"title": "x" * 201, "description": "Good"},
    {"title": "Desk", "description": "x" * 10001},
    {"title": "Desk", "description": "Good", "owner": 100},
    {"title": "Desk", "description": "Good", "owner_id": 100},
    {"title": "Desk", "description": "Good", "id": 1},
    {"title": "Desk", "description": "Good", "created_at": "2026-01-01"},
    [],
])
async def test_invalid_advertisement(client, auth, data, database_engine):
    response = await client.post("/advertisements", json=data, headers=auth)
    assert response.status == 400
    assert "error" in await response.json()
    async with AsyncSession(database_engine) as session:
        assert await session.scalar(select(func.count()).select_from(Advertisement)) == 0


@pytest.mark.parametrize("changes", [
    {"title": "Updated"},
    {"description": "New description"},
    {"title": "Updated", "description": "New description"},
])
async def test_owner_can_update(client, advertisement, auth, changes):
    url = f"/advertisements/{advertisement['id']}"
    response = await client.patch(url, json=changes, headers=auth)
    assert response.status == 200
    expected = {**advertisement, **changes}
    assert await response.json() == expected
    response = await client.get(url)
    assert response.status == 200
    assert await response.json() == expected


@pytest.mark.parametrize("changes", [
    {}, {"title": ""}, {"description": None}, {"owner": 2},
    {"owner_id": 2}, {"id": 2}, {"created_at": "2026-01-01"},
])
async def test_invalid_update_preserves_ad(client, advertisement, auth, changes):
    url = f"/advertisements/{advertisement['id']}"
    response = await client.patch(url, json=changes, headers=auth)
    assert response.status == 400
    response = await client.get(url)
    assert response.status == 200
    assert await response.json() == advertisement


@pytest.mark.parametrize("method", ["patch", "delete"])
async def test_non_owner_cannot_modify(client, advertisement, stranger_auth, method):
    url = f"/advertisements/{advertisement['id']}"
    response = await client.request(method, url, json={"title": "Hijacked"}, headers=stranger_auth)
    assert response.status == 403
    response = await client.get(url)
    assert response.status == 200
    assert await response.json() == advertisement


async def test_owner_can_delete(client, advertisement, auth, database_engine):
    url = f"/advertisements/{advertisement['id']}"
    response = await client.delete(url, headers=auth)
    assert response.status == 204
    assert await response.read() == b""
    response = await client.get(url)
    assert response.status == 404
    async with AsyncSession(database_engine) as session:
        assert await session.get(Advertisement, advertisement["id"]) is None


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
async def test_missing_advertisement(client, auth, method):
    response = await client.request(method, "/advertisements/999", headers=auth, json={"title": "New"})
    assert response.status == 404
    assert "error" in await response.json()


@pytest.mark.parametrize("value", ["0", "-1", "bad", "2147483648", "9" * 500])
async def test_invalid_ids_are_not_server_errors(client, value):
    response = await client.get(f"/advertisements/{value}")
    assert response.status == 404
    assert "error" in await response.json()


@pytest.mark.parametrize("body,content_type,status", [
    (b"{", "application/json", 400),
    (b"null", "application/json", 400),
    (b"\xff", "application/json", 400),
    (b"{}", "text/plain", 415),
    (b"x" * (64 * 1024 + 1), "application/json", 413),
])
async def test_body_errors_are_json(client, body, content_type, status):
    response = await client.post("/users", data=body, headers={"Content-Type": content_type})
    assert response.status == status
    assert "error" in await response.json()


async def test_json_suffix_media_type(client, credentials):
    response = await client.post(
        "/users", json=credentials, headers={"Content-Type": "application/vnd.api+json"}
    )
    assert response.status == 201


async def test_unknown_route_and_unsupported_method(client):
    response = await client.get("/missing")
    assert response.status == 404
    assert "error" in await response.json()
    response = await client.put("/advertisements/1", json={})
    assert response.status == 405
    assert "PATCH" in response.headers["Allow"]
    assert "error" in await response.json()


async def test_data_survives_app_restart(client, advertisement, database_engine, aiohttp_client):
    await client.close()
    restarted = await aiohttp_client(create_app(engine=database_engine))
    response = await restarted.get(f"/advertisements/{advertisement['id']}")
    assert response.status == 200
    assert await response.json() == advertisement
    await restarted.close()
