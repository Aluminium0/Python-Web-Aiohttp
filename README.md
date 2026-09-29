# Aiohttp: Advertisements API

[Assignment](https://github.com/netology-code/py-homeworks-web/tree/new/2.3-aiohttp)
| [Tests and Docker verification](https://github.com/Aluminium0/Python-Web-Aiohttp/actions)

Flask homework rewritten with aiohttp, async SQLAlchemy and PostgreSQL (asyncpg).
Includes Docker, registration, password hashing and owner-only editing/deletion.

## Run

```bash
docker compose up --build -d --wait
```

Local API: http://127.0.0.1:8080/advertisements (after starting the containers).
Tables are created automatically; PostgreSQL data is kept in a Docker volume.
Stop: `docker compose down`.

## Check (Python 3.12)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
python scripts/smoke.py
```

Tests use separate PostgreSQL schemas and leave application data untouched.
Manual requests: [requests-examples.http](requests-examples.http).

| Method | Endpoint | Access |
| --- | --- | --- |
| POST | `/users` | Registration: `email`, `password` (8-128 characters) |
| GET | `/advertisements` | Public list |
| GET | `/advertisements/{id}` | Public detail |
| POST | `/advertisements` | Authenticated: `title`, `description` |
| PATCH | `/advertisements/{id}` | Owner: `title` and/or `description` |
| DELETE | `/advertisements/{id}` | Owner only |

Protected requests use HTTP Basic with the registered email/password.
`id`, `created_at` (UTC) and `owner` are assigned by the server.
Docker credentials are for local homework only; use HTTPS and private credentials when deploying.
