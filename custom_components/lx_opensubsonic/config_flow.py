"""Config flow for LX OpenSubsonic."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOW_OBFUSCATED_JS,
    CONF_MUSIC_SOURCE_JS_URL,
    CONF_PREFERRED_QUALITY,
    CONF_SEARCH_SOURCE,
    DEFAULT_ALLOW_OBFUSCATED_JS,
    DEFAULT_MUSIC_SOURCE_JS_URL,
    DEFAULT_PREFERRED_QUALITY,
    DEFAULT_SEARCH_SOURCE,
    DEFAULT_USERNAME,
    DOMAIN,
    QUALITY_SELECT_OPTIONS,
    SEARCH_SOURCE_OPTIONS,
)


def _install_schema(defaults: dict | None = None):
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=d.get(CONF_USERNAME, DEFAULT_USERNAME)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(CONF_PASSWORD, default=d.get(CONF_PASSWORD, "password")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SEARCH_SOURCE, default=d.get(CONF_SEARCH_SOURCE, DEFAULT_SEARCH_SOURCE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=o["value"], label=o["label"]) for o in SEARCH_SOURCE_OPTIONS],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_MUSIC_SOURCE_JS_URL,
                default=d.get(CONF_MUSIC_SOURCE_JS_URL, DEFAULT_MUSIC_SOURCE_JS_URL),
            ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL)),
            vol.Optional(
                CONF_ALLOW_OBFUSCATED_JS,
                default=bool(d.get(CONF_ALLOW_OBFUSCATED_JS, DEFAULT_ALLOW_OBFUSCATED_JS)),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_PREFERRED_QUALITY,
                default=d.get(CONF_PREFERRED_QUALITY, DEFAULT_PREFERRED_QUALITY),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=o["value"], label=o["label"]) for o in QUALITY_SELECT_OPTIONS],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _account_schema(defaults: dict | None = None):
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=d.get(CONF_USERNAME, DEFAULT_USERNAME)): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(CONF_PASSWORD, default=d.get(CONF_PASSWORD, "password")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_MUSIC_SOURCE_JS_URL,
                default=d.get(CONF_MUSIC_SOURCE_JS_URL, DEFAULT_MUSIC_SOURCE_JS_URL),
            ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL)),
            vol.Optional(
                CONF_ALLOW_OBFUSCATED_JS,
                default=bool(d.get(CONF_ALLOW_OBFUSCATED_JS, DEFAULT_ALLOW_OBFUSCATED_JS)),
            ): selector.BooleanSelector(),
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="LX OpenSubsonic", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_install_schema())

    async def async_step_reconfigure(self, user_input: dict | None = None) -> FlowResult:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")
        defaults = {**entry.data, **(entry.options or {})}
        if user_input is not None:
            new_data = {
                **entry.data,
                CONF_USERNAME: user_input.get(CONF_USERNAME, defaults.get(CONF_USERNAME, DEFAULT_USERNAME)),
                CONF_PASSWORD: user_input.get(CONF_PASSWORD, defaults.get(CONF_PASSWORD, "password")),
                CONF_MUSIC_SOURCE_JS_URL: user_input.get(
                    CONF_MUSIC_SOURCE_JS_URL, defaults.get(CONF_MUSIC_SOURCE_JS_URL, "")
                ),
                CONF_ALLOW_OBFUSCATED_JS: bool(
                    user_input.get(CONF_ALLOW_OBFUSCATED_JS, defaults.get(CONF_ALLOW_OBFUSCATED_JS, False))
                ),
            }
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(step_id="reconfigure", data_schema=_account_schema(defaults))
