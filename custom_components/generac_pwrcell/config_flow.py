"""Config flow for Generac PWRcell integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .auth import AuthError, GeneracAuth, InvalidAuth, is_valid_api_base
from .const import CONF_API_BASE, CONF_USER_ID, DEFAULT_API_BASE, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
        vol.Optional(CONF_API_BASE, default=DEFAULT_API_BASE): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)


class GeneracPWRcellConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Generac PWRcell."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            api_base = user_input.get(CONF_API_BASE, DEFAULT_API_BASE) or DEFAULT_API_BASE

            try:
                if not is_valid_api_base(api_base):
                    errors["base"] = "invalid_api_base"
                else:
                    session = aiohttp_client.async_get_clientsession(self.hass)
                    user_id = await GeneracAuth.async_validate(
                        session, email, password, api_base=api_base
                    )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except AuthError as exc:
                _LOGGER.warning("Generac auth failed: %s", exc)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Generac sign-in")
                errors["base"] = "unknown"
            if not errors:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{MANUFACTURER} PWRcell ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_USER_ID: user_id,
                        CONF_API_BASE: api_base,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            errors=errors,
            description_placeholders={
                "app_name": "Generac PWRcell / PWRview"
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start when the coordinator reports the stored credentials no longer work."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the new password and update the existing entry."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                user_id = await GeneracAuth.async_validate(
                    aiohttp_client.async_get_clientsession(self.hass),
                    entry.data[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                    api_base=entry.data.get(CONF_API_BASE) or DEFAULT_API_BASE,
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except AuthError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_mismatch()  # signed in as a different account
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
        )
