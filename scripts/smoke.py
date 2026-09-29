"""Exercise the running API; use unique test users and delete the test advertisement."""

import argparse
import asyncio
from uuid import uuid4

import aiohttp


async def verify(base_url):
    suffix = uuid4().hex
    owner = {"email": f"owner-{suffix}@example.com", "password": "smoke-test-password"}
    stranger = {"email": f"other-{suffix}@example.com", "password": "smoke-test-password"}
    data = {"title": "Docker verification", "description": "Aiohttp CRUD check"}
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(base_url=base_url.rstrip("/"), timeout=timeout) as session:
        async def request(method, path, expected, **kwargs):
            async with session.request(method, path, **kwargs) as response:
                body = await response.text()
                if response.status != expected:
                    raise RuntimeError(f"{method} {path}: expected {expected}, got {response.status}: {body}")
                return await response.json() if body else None

        for user in (owner, stranger):
            await request("POST", "/users", 201, json=user)
        auth = {"Authorization": aiohttp.encode_basic_auth(owner["email"], owner["password"])}
        other_auth = {"Authorization": aiohttp.encode_basic_auth(stranger["email"], stranger["password"])}
        await request("POST", "/advertisements", 401, json=data)
        created = await request("POST", "/advertisements", 201, json=data, headers=auth)
        url = f"/advertisements/{created['id']}"
        try:
            retrieved = await request("GET", url, 200)
            assert retrieved == created
            listed = await request("GET", "/advertisements", 200)
            assert created in listed
            await request("PATCH", url, 403, json={"title": "Not allowed"}, headers=other_auth)
            await request("DELETE", url, 403, headers=other_auth)
            updated = await request("PATCH", url, 200, json={"title": "Updated"}, headers=auth)
            assert updated == {**created, "title": "Updated"}
        finally:
            await request("DELETE", url, 204, headers=auth)
        await request("GET", url, 404)
    print("PASS: registration, public reads, authentication, owner permissions, update and delete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    asyncio.run(verify(parser.parse_args().url))
