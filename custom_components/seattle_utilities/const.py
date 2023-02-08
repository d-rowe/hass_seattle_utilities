import logging
from typing import Final

"""Constants for seattle_utilities."""
# Base component constants
NAME: Final = "Seattle Utilities"
DOMAIN: Final = "seattle_utilities"
LOGGER = logging.getLogger(__package__)
DOMAIN_DATA: Final = f"{DOMAIN}_data"
VERSION = "0.0.2"
ATTRIBUTION = "Data provided by Seattle Utilities"
ISSUE_URL = "https://github.com/jrjparks/hass_seattle_utilities/issues"

# Icons
ICON_ENERGY = "mdi:power-plug"
ICON_COST = "mdi:currency-usd"

# Platforms
SENSOR = "sensor"
PLATFORMS = [SENSOR]

# Configuration and options
CONF_BASE_COST = "base_cost"
CONF_1ST_BLOCK_COST = "first_block_cost"
CONF_2ND_BLOCK_COST = "second_block_cost"
CONF_MISC_PER_KWH_COST = "misc_per_kWh_cost"

# Defaults
# Pulled 2023-02-07 from https://seattle.gov/city-light/residential-services/billing-information/rates
# Defaults are for Seattle
DEFAULT_BASE_COST = 0.2301
DEFAULT_1ST_BLOCK_COST = 0.1132
DEFAULT_2ND_BLOCK_COST = 0.1307
DEFAULT_MISC_PER_KWH_COST = 0.0

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration for Seattle Utilities!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
