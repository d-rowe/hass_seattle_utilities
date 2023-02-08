"""The Seattle Utility Energy sensor."""

import logging
from datetime import timedelta
from typing import Dict, Optional

import async_timeout
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, CURRENCY_DOLLAR, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from requests.exceptions import ConnectionError as ConnectError, HTTPError, Timeout

from .const import (
    ATTRIBUTION,
    ICON_ENERGY,
    ICON_COST,
    DOMAIN,
)
from .seattle_utility_api import SeattleUtilityClient, MeterUsage, Meter

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the SCL Energy Usage sensor."""
    # API object stored here by __init__.py
    energy_client: SeattleUtilityClient = hass.data[DOMAIN]

    async def async_update_data():
        """Fetch data from API endpoint.
        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Fetch Seattle Utility energy data
            if energy_client.is_token_expired:
                LOGGER.info("Client Token has expired, logging in...")
                await hass.async_add_executor_job(
                    energy_client.login,
                    entry.data[CONF_USERNAME],
                    entry.data[CONF_PASSWORD],
                )
            async with async_timeout.timeout(60):
                daily_usage: Dict[str, MeterUsage] = await hass.async_add_executor_job(energy_client.get_latest_usage)
                return daily_usage
        except KeyError as key_err:
            raise UpdateFailed("Unable to locate meter") from key_err
        except TimeoutError as timeout_err:
            raise UpdateFailed("Timeout communicating with API") from timeout_err
        except (ConnectError, HTTPError, Timeout, ValueError, TypeError, ConnectionError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name="sensor",
        update_method=async_update_data,
        update_interval=timedelta(hours=12),
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_refresh()

    meters: Dict[str, Meter] = await hass.async_add_executor_job(energy_client.get_meters)
    for _, meter in meters.items():
        async_add_entities([
            SeattleUtilityEnergyEntity(coordinator=coordinator, meter=meter),
            SeattleUtilityCostEntity(coordinator=coordinator, meter=meter),
        ])


class SeattleUtilityEnergyEntity(SensorEntity):
    """Implementation of a SCL Energy Usage sensor."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY

    def __init__(self, coordinator, meter: Meter):
        """Initialize the SCL Energy Usage Entity class."""
        self.coordinator = coordinator
        self._meter = meter
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.unique_id} SCL Meter"

    @property
    def unique_id(self):
        """Return sensor unique_id."""
        return ".".join([DOMAIN, self._meter.id, "usage"])

    @property
    def native_value(self):
        """Return the state of the device."""
        if self._state:
            return f"{self._state.usage_kWh:.2f}"
        return None

    @property
    def icon(self):
        """Return icon."""
        return ICON_ENERGY

    @property
    def usage(self):
        """Return entity state."""
        if self.meter_data:
            return f"{self.meter_data.usage_kWh:.2f}"
        return None

    @property
    def last_reset(self):
        if self._state:
            return self._state.date
        return None

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def meter_data(self) -> Optional[MeterUsage]:
        if self.coordinator.data:
            return self.coordinator.data.get(self._meter.id, None)
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        if self.coordinator.data:
            self._state = self.coordinator.data.get(self._meter.id, None)

    async def async_update(self) -> None:
        """Update the entity.
        Only used by the generic entity update service.
        """
        await self.coordinator.async_request_refresh()


class SeattleUtilityCostEntity(SensorEntity):
    """Implementation of a SCL Energy Cost sensor."""

    _attr_native_unit_of_measurement = CURRENCY_DOLLAR
    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator, meter: Meter):
        """Initialize the SCL Energy Cost Entity class."""
        self.coordinator = coordinator
        self._meter = meter
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.unique_id} SCL Meter Cost"

    @property
    def unique_id(self):
        """Return sensor unique_id."""
        return ".".join([DOMAIN, self._meter.id, "cost"])

    @property
    def native_value(self):
        """Return the state of the device."""
        if self._state:
            return f"{self._state.cost:.2f}"
        return None

    @property
    def icon(self):
        """Return icon."""
        return ICON_COST

    @property
    def usage(self):
        """Return entity state."""
        if self.meter_data:
            return f"{self.meter_data.cost:.2f}"
        return None

    @property
    def last_reset(self):
        if self._state:
            return self._state.date
        return None

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def meter_data(self) -> Optional[MeterUsage]:
        if self.coordinator.data:
            return self.coordinator.data.get(self._meter.id, None)
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
        if self.coordinator.data:
            self._state = self.coordinator.data.get(self._meter.id, None)

    async def async_update(self) -> None:
        """Update the entity.
        Only used by the generic entity update service.
        """
        await self.coordinator.async_request_refresh()
