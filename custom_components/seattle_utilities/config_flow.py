"""The Seattle Utility Energy integration."""
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import NAME, DOMAIN, CONF_BASE_COST, CONF_1ST_BLOCK_COST, CONF_2ND_BLOCK_COST, CONF_MISC_PER_KWH_COST, \
    DEFAULT_BASE_COST, DEFAULT_1ST_BLOCK_COST, DEFAULT_2ND_BLOCK_COST, DEFAULT_MISC_PER_KWH_COST
from .seattle_utility_api import SeattleUtilityClient, Rates

LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seattle Utility Energy."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    config = {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_BASE_COST, default=DEFAULT_BASE_COST): float,
        vol.Required(CONF_1ST_BLOCK_COST, default=DEFAULT_1ST_BLOCK_COST): float,
        vol.Required(CONF_2ND_BLOCK_COST, default=DEFAULT_2ND_BLOCK_COST): float,
        vol.Optional(CONF_MISC_PER_KWH_COST): float,
    }

    async def async_step_user(self, user_input: dict[str, Any] = None) -> data_entry_flow.FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            try:
                energy_rate = Rates(
                    base=float(user_input.get(CONF_BASE_COST, DEFAULT_BASE_COST)),
                    first_block=float(user_input.get(CONF_1ST_BLOCK_COST, DEFAULT_1ST_BLOCK_COST)),
                    second_block=float(user_input.get(CONF_2ND_BLOCK_COST, DEFAULT_2ND_BLOCK_COST)),
                    misc_per_kWh=float(user_input.get(CONF_MISC_PER_KWH_COST, DEFAULT_MISC_PER_KWH_COST)),
                )
                energy_client = SeattleUtilityClient(rates=energy_rate)
                await self.hass.async_add_executor_job(
                    energy_client.login,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
                meters = await self.hass.async_add_executor_job(energy_client.get_meters)
                if meters:
                    return self.async_create_entry(
                        title=NAME, data=user_input
                    )
                errors["base"] = "invalid_meter"
            except ConnectionRefusedError:
                errors["base"] = "invalid_auth"
            except ValueError:
                errors["base"] = "invalid_account"
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(self.config), errors=errors
        )

    async def async_step_import(self, import_config: dict[str, Any]):
        """Import from config."""
        # Validate config values
        return await self.async_step_user(user_input=import_config)
