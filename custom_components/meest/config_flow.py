"""UI setup, reauthentication and options for Meest."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import MeestAuthError, MeestClient, MeestError, MeestRateLimitError
from .const import (
    CONF_ACCOUNT_ID,
    CONF_B2B,
    CONF_EXPIRES_AT,
    CONF_INTERVAL,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN,
    DEFAULT_INTERVAL,
    DOMAIN,
    NAME,
)

CREDENTIALS = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class MeestConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._credentials("user", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._credentials("reauth_confirm", user_input)

    async def _credentials(self, step_id, user_input):
        errors = {}
        if user_input is not None:
            try:
                client = MeestClient(async_get_clientsession(self.hass))
                account, tokens = await client.login(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                data = {
                    CONF_ACCOUNT_ID: account,
                    CONF_TOKEN: tokens.token,
                    CONF_REFRESH_TOKEN: tokens.refresh_token,
                    CONF_EXPIRES_AT: tokens.expires_at,
                }
                if step_id == "reauth_confirm":
                    entry = self._get_reauth_entry()
                    if account != entry.data[CONF_ACCOUNT_ID]:
                        errors["base"] = "wrong_account"
                    else:
                        return self.async_update_reload_and_abort(entry, data_updates=data)
                else:
                    await self.async_set_unique_id(account)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=NAME, data=data)
            except MeestAuthError:
                errors["base"] = "invalid_auth"
            except MeestRateLimitError:
                errors["base"] = "rate_limited"
            except MeestError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id=step_id, data_schema=CREDENTIALS, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MeestOptionsFlow()


class MeestOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INTERVAL,
                        default=self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                    vol.Optional(
                        CONF_B2B, default=self.config_entry.options.get(CONF_B2B, False)
                    ): bool,
                }
            ),
        )
