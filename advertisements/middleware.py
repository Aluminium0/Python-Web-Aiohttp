import logging

from aiohttp import web
from marshmallow import ValidationError

logger = logging.getLogger(__name__)


@web.middleware
async def json_errors(request, handler):
    try:
        return await handler(request)
    except ValidationError as error:
        return web.json_response({"error": error.messages}, status=400)
    except web.HTTPException as error:
        headers = {
            key: value
            for key, value in error.headers.items()
            if key.lower() not in {"content-type", "content-length"}
        }
        return web.json_response(
            {"error": error.text}, status=error.status, headers=headers
        )
    except Exception:
        logger.exception("Unexpected request failure")
        return web.json_response({"error": "Internal server error"}, status=500)
