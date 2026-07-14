"""HTTP views for OpenSubsonic endpoints under Home Assistant."""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN
from .opensubsonic_api import OpenSubsonicAPI

_LOGGER = logging.getLogger(__name__)


def _method_from_path(path: str) -> str:
    parts = path.rstrip("/").split("/")
    return parts[-1] if parts else ""


class OpenSubsonicView(HomeAssistantView):
    url = "/api/lx_opensubsonic/rest/{method:.*}"
    name = "api:lx_opensubsonic:rest"
    requires_auth = False

    async def _handle(self, request: web.Request, method: str) -> web.StreamResponse:
        hass = request.app["hass"]
        data = hass.data.get(DOMAIN)
        if not data or not data.get("api"):
            return web.json_response(
                {
                    "subsonic-response": {
                        "status": "failed",
                        "version": "1.16.1",
                        "error": {"code": 0, "message": "Integration not loaded"},
                    }
                },
                status=503,
            )

        api: OpenSubsonicAPI = data["api"]
        query = {k: v for k, v in request.rel_url.query.items()}
        body = None
        if request.can_read_body:
            body = await request.text()
        params = api.merge_params(query, body, request.headers.get("Content-Type"))
        method_name = method or _method_from_path(str(request.rel_url.path))
        method_name = method_name.split("?")[0].rstrip("/")

        try:
            result = await api.handle(method_name, params)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("OpenSubsonic handler error: %s", err)
            return web.json_response(api.fail(0, "Internal server error"))

        if isinstance(result, tuple) and result and result[0] == "cover":
            img = await data["backend"].fetch_cover_bytes(result[1])
            if not img:
                return web.Response(status=204)
            content, ctype = img
            return web.Response(body=content, content_type=ctype, headers={"Cache-Control": "public, max-age=86400"})

        if isinstance(result, tuple) and result and result[0] == "stream":
            song_id = result[1]
            if not song_id:
                return web.json_response(api.fail(10, "Required parameter is missing: id"))
            url = await data["backend"].resolve_stream_url(song_id)
            if url:
                raise web.HTTPFound(location=url)
            return web.json_response(api.fail(0, "No stream URL. Configure an authorized custom music source service."))

        return web.json_response(result)

    async def get(self, request: web.Request, method: str = "") -> web.StreamResponse:
        return await self._handle(request, method)

    async def post(self, request: web.Request, method: str = "") -> web.StreamResponse:
        return await self._handle(request, method)


class OpenSubsonicRootView(HomeAssistantView):
    url = "/api/lx_opensubsonic"
    name = "api:lx_opensubsonic:root"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        data = hass.data.get(DOMAIN) or {}
        backend = data.get("backend")
        return web.json_response(
            {
                "name": "LX OpenSubsonic",
                "version": data.get("version", "unknown"),
                "rest_base": f"{request.scheme}://{request.host}/api/lx_opensubsonic/rest",
                "configured": bool(data.get("api")),
                "search_source": getattr(backend, "search_source", None) if backend else None,
                "preferred_quality": getattr(backend, "preferred_quality", None) if backend else None,
                "music_source_js": bool(getattr(backend, "music_source_js_url", "") if backend else ""),
                "entities": {
                    "search_source": "select.lx_opensubsonic_default_search_source_or_similar",
                    "quality": "select....",
                    "health": "sensor....",
                    "test": "button....",
                },
                "usage": {
                    "music_assistant": {
                        "base_url": f"{request.scheme}://{request.host}/api/lx_opensubsonic",
                        "path": "/rest",
                    },
                    "test_service": "lx_opensubsonic.test_connection",
                },
            }
        )
