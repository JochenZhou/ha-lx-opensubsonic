"""LX OpenSubsonic Home Assistant integration."""

from __future__ import annotations

import json
import logging

import voluptuous as vol
from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_MUSIC_SOURCE_JS_URL,
    CONF_PREFERRED_QUALITY,
    CONF_SEARCH_SOURCE,
    DEFAULT_PREFERRED_QUALITY,
    DEFAULT_SEARCH_SOURCE,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import LxOpenSubsonicCoordinator
from .http_views import OpenSubsonicRootView, OpenSubsonicView
from .music_backend import MusicBackend
from .opensubsonic_api import OpenSubsonicAPI
from .playlist_store import PlaylistStore
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
SERVICE_TEST_CONNECTION = "test_connection"


def _integration_version() -> str:
    try:
        manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    return str(manifest.get("version") or "unknown")


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
    store_path = Path(hass.config.path(f".storage/{DOMAIN}_playlists_{entry.entry_id}.json"))
    playlist_store = PlaylistStore(store_path)
    await playlist_store.async_load(hass)
    api = OpenSubsonicAPI(backend, username=username, password=password, playlist_store=playlist_store)
    coordinator = LxOpenSubsonicCoordinator(hass, entry, backend)

    hass.data.setdefault(DOMAIN, {})
    version = _integration_version()
    entry_data = {
        "api": api,
        "backend": backend,
        "coordinator": coordinator,
        "playlist_store": playlist_store,
        "username": username,
        "password": password,
        "entry": entry,
        "version": version,
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data
    hass.data[DOMAIN].update(
        {
            "api": api,
            "backend": backend,
            "playlist_store": playlist_store,
            "username": username,
            "password": password,
            "search_source": search_source,
            "preferred_quality": preferred_quality,
            "music_source_js_url": music_source_js_url,
            "entry_id": entry.entry_id,
            "version": version,
            "coordinator": coordinator,
        }
    )

    hass.http.register_view(OpenSubsonicRootView)
    hass.http.register_view(OpenSubsonicView)

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _notify(title: str, message: str) -> None:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {"title": title, "message": message, "notification_id": "lx_opensubsonic_test"},
            blocking=False,
        )

    async def _test_connection(call: ServiceCall) -> None:
        await coordinator.async_request_refresh()
        data = coordinator.data or {}
        lines = [
            f"总体: {'通过' if data.get('ok') else '未完全通过'}",
            f"搜索: {'✓' if data.get('search_ok') else '✗'}",
            f"封面: {'✓' if data.get('cover_ok') else '✗'}",
            f"播放取链: {'✓' if data.get('stream_ok') else '✗'}",
            f"音源JS: {'✓' if data.get('js_ok') else '✗'}",
        ]
        sample = data.get("sample_song") or {}
        if sample:
            lines.append(f"样例: {sample.get('artist')} - {sample.get('title')}")
        errs = data.get("errors") or []
        if errs:
            lines.append("问题:")
            lines.extend([f"- {e}" for e in errs[:6]])
        await _notify("LX OpenSubsonic 连接测试", "\n".join(lines))

    if not hass.services.has_service(DOMAIN, SERVICE_TEST_CONNECTION):
        hass.services.async_register(DOMAIN, SERVICE_TEST_CONNECTION, _test_connection, schema=vol.Schema({}))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if hass.services.has_service(DOMAIN, SERVICE_TEST_CONNECTION):
        hass.services.async_remove(DOMAIN, SERVICE_TEST_CONNECTION)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        for k in [
            "api",
            "backend",
            "coordinator",
            "playlist_store",
            "username",
            "password",
            "search_source",
            "preferred_quality",
            "music_source_js_url",
            "entry_id",
            "version",
        ]:
            hass.data.get(DOMAIN, {}).pop(k, None)
    return unload_ok
