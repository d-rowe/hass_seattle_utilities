"""The Seattle Utility Energy integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, CONF_BASE_COST, CONF_1ST_BLOCK_COST, CONF_2ND_BLOCK_COST, CONF_MISC_PER_KWH_COST, \
    DEFAULT_BASE_COST, DEFAULT_1ST_BLOCK_COST, DEFAULT_2ND_BLOCK_COST, DEFAULT_MISC_PER_KWH_COST
from .seattle_utility_api import SeattleUtilityClient, Rates

LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Energy component from a config entry."""
    # Store an SrpEnergyClient object for your srp_energy to access
    try:
        energy_rate = Rates(
            base=float(entry.data.get(CONF_BASE_COST, DEFAULT_BASE_COST)),
            first_block=float(entry.data.get(CONF_1ST_BLOCK_COST, DEFAULT_1ST_BLOCK_COST)),
            second_block=float(entry.data.get(CONF_2ND_BLOCK_COST, DEFAULT_2ND_BLOCK_COST)),
            misc_per_kWh=float(entry.data.get(CONF_MISC_PER_KWH_COST, DEFAULT_MISC_PER_KWH_COST)),
        )
        energy_client = SeattleUtilityClient(rates=energy_rate)
        await hass.async_add_executor_job(
            energy_client.login,
            entry.data.get(CONF_USERNAME),
            entry.data.get(CONF_PASSWORD),
        )
        hass.data[DOMAIN] = energy_client
    except Exception as ex:
        LOGGER.error("Unable to connect to Seattle Utility: %s", str(ex))
        raise ConfigEntryNotReady from ex
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # unload srp client
    hass.data[DOMAIN] = None
    # Remove config entry
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
