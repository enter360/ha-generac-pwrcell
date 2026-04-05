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

from .auth import AuthError, GeneracAuth
from .const import CONF_USER_ID, DOMAIN, MANUFACTURER

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
    }
)


class GeneracPWRcellConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Generac PWRcell."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            try:
                session = aiohttp_client.async_get_clientsession(self.hass)
                user_id = await GeneracAuth.async_validate(session, email, password)
            except AuthError as exc:
                _LOGGER.warning("Generac auth failed: %s", exc)
                errors["base"] = _classify_error(str(exc))
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Generac sign-in")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{MANUFACTURER} PWRcell ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_USER_ID: user_id,
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


def _classify_error(message: str) -> str:
    msg = message.lower()
    if any(w in msg for w in ("401", "invalid", "unauthorized", "credentials", "password")):
        return "invalid_auth"
    if any(w in msg for w in ("network", "cannot connect", "timeout", "connection")):
        return "cannot_connect"
    return "unknown"
