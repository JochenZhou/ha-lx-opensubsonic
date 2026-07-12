"""Config flow + options for LX OpenSubsonic."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_MUSIC_SOURCE_JS_URL,
    CONF_PLAYLIST_SONG_VIRTUAL_ALBUM,
    CONF_PREFERRED_QUALITY,
    CONF_SEARCH_SOURCE,
    DEFAULT_MUSIC_SOURCE_JS_URL,
    DEFAULT_PLAYLIST_SONG_VIRTUAL_ALBUM,
    DEFAULT_PREFERRED_QUALITY,
    DEFAULT_SEARCH_SOURCE,
    DEFAULT_USERNAME,
    DOMAIN,
    QUALITY_OPTIONS,
    SEARCH_SOURCES,
)


def _schema(defaults: dict | None = None, *, include_auth: bool = True) -> vol.Schema:
    d = defaults or {}
    fields: dict = {}
    if include_auth:
        fields[vol.Required(CONF_USERNAME, default=d.get(CONF_USERNAME, DEFAULT_USERNAME))] = str
        fields[vol.Required(CONF_PASSWORD, default=d.get(CONF_PASSWORD, "password"))] = str

    fields[vol.Required(CONF_SEARCH_SOURCE, default=d.get(CONF_SEARCH_SOURCE, DEFAULT_SEARCH_SOURCE))] = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(options=SEARCH_SOURCES, mode=selector.SelectSelectorMode.DROPDOWN)
        )
    )
    fields[
        vol.Optional(
            CONF_MUSIC_SOURCE_JS_URL,
            default=d.get(CONF_MUSIC_SOURCE_JS_URL, DEFAULT_MUSIC_SOURCE_JS_URL),
        )
    ] = str
    fields[
        vol.Optional(
            CONF_PREFERRED_QUALITY,
            default=d.get(CONF_PREFERRED_QUALITY, DEFAULT_PREFERRED_QUALITY),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(options=QUALITY_OPTIONS, mode=selector.SelectSelectorMode.DROPDOWN)
    )
    fields[
        vol.Optional(
            CONF_PLAYLIST_SONG_VIRTUAL_ALBUM,
            default=d.get(CONF_PLAYLIST_SONG_VIRTUAL_ALBUM, DEFAULT_PLAYLIST_SONG_VIRTUAL_ALBUM),
        )
    ] = bool
    return vol.Schema(fields)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="LX OpenSubsonic", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Hot-switch search source / quality / music source JS without reinstall."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            new_data = {
                CONF_USERNAME: self._config_entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
                CONF_PASSWORD: self._config_entry.data.get(CONF_PASSWORD, "password"),
                **user_input,
            }
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data, options=user_input)
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self._config_entry.data, **(self._config_entry.options or {})}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults, include_auth=False))
