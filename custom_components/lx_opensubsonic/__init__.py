"""LX OpenSubsonic Home Assistant integration.

Exposes an OpenSubsonic-compatible REST API under:
  /api/lx_opensubsonic/rest/*

- Configurable search source (tx/wy/kg/kw/mg)
- Stream via third-party music source JS URL (no hard-coded paid key)
"""

from __future__ import annotations

import logging

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_MUSIC_SOURCE_JS_URL,
    CONF_PREFERRED_QUALITY,
    CONF_SEARCH_SOURCE,
    DEFAULT_PREFERRED_QUALITY,
    DEFAULT_SEARCH_SOURCE,
    DOMAIN,
)
from .http_views import OpenSubsonicRootView, OpenSubsonicView
from .music_backend import MusicBackend
from .opensubsonic_api import OpenSubsonicAPI

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


def _merged(entry: ConfigEntry) -> dict:
    return {**entry.data, **(entry.options or {})}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session: ClientSession = async_get_clientsession(hass)
    cfg = _merged(entry)
    username = cfg[CONF_USERNAME]
    password = cfg[CONF_PASSWORD]

    search_source = cfg.get(CONF_SEARCH_SOURCE) or DEFAULT_SEARCH_SOURCE
    music_source_js_url = (cfg.get(CONF_MUSIC_SOURCE_JS_URL) or "").strip()
    preferred_quality = cfg.get(CONF_PREFERRED_QUALITY) or DEFAULT_PREFERRED_QUALITY

    backend = MusicBackend(
        session,
        search_source=search_source,
        music_source_js_url=music_source_js_url,
        preferred_quality=preferred_quality,
    )
    api = OpenSubsonicAPI(backend, username=username, password=password)

    hass.data[DOMAIN] = {
        "api": api,
        "backend": backend,
        "username": username,
        "password": password,
        "search_source": search_source,
        "entry_id": entry.entry_id,
    }

    hass.http.register_view(OpenSubsonicRootView)
    hass.http.register_view(OpenSubsonicView)

    mode = "music_source_js" if music_source_js_url else "no_stream"
    hass.async_create_task(
        hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "LX OpenSubsonic 已启动",
                "message": (
                    f"- 搜索源: `{search_source}`\n"
                    f"- 音质: `{preferred_quality}`\n"
                    f"- 播放: `{mode}`\n"
                    f"- REST: `/api/lx_opensubsonic/rest`\n"
                ),
                "notification_id": "lx_opensubsonic_started",
            },
            blocking=False,
        )
    )
    _LOGGER.info("LX OpenSubsonic ready search=%s quality=%s mode=%s", search_source, preferred_quality, mode)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.pop(DOMAIN, None)
    return True
