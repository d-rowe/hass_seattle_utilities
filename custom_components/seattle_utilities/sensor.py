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
                _ = await hass.async_add_executor_job(
                    energy_client.login,
                    entry.data[CONF_USERNAME],
                    entry.data[CONF_PASSWORD],
                )
            LOGGER.info("Requesting latest data...")
            async with async_timeout.timeout(30):
                daily_usage: Dict[str, MeterUsage] = await hass.async_add_executor_job(energy_client.get_latest_usage)
                LOGGER.info(f"Got latest data: {daily_usage}")
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
    _ = await coordinator.async_refresh()

    meters: Dict[str, Meter] = await hass.async_add_executor_job(energy_client.get_meters)
    for _, meter in meters.items():
        async_add_entities([
            SeattleUtilityEnergyEntity(coordinator=coordinator, meter=meter),
            SeattleUtilityCostEntity(coordinator=coordinator, meter=meter),
        ])


class SeattleUtilityEnergyEntity(SensorEntity):
    """Implementation of a SCL Energy Usage sensor."""

    _attr_icon = ICON_ENERGY
    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_precision = 2
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_native_value = None
    _attr_last_reset = None

    def __init__(self, coordinator, meter: Meter):
        """Initialize the SCL Energy Usage Entity class."""
        self.coordinator = coordinator
        self._meter = meter

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"[{self._meter.id}] SCL Meter Usage"

    @property
    def unique_id(self):
        """Return sensor unique_id."""
        return ".".join([DOMAIN, self._meter.id, "usage"])

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
        await super().async_added_to_hass()
        self._update_from_meter()
        self.async_on_remove(self.coordinator.async_add_listener(self._update_from_meter))

    async def async_update(self) -> None:
        """Update the entity.
        Only used by the generic entity update service.
        """
        await self.coordinator.async_request_refresh()

    def _update_from_meter(self) -> None:
        if self.meter_data is not None:
            self._attr_native_value = self.meter_data.usage_kWh
            self._attr_last_reset = self.meter_data.date
        self.async_write_ha_state()


class SeattleUtilityCostEntity(SensorEntity):
    """Implementation of a SCL Energy Cost sensor."""

    _attr_icon = ICON_COST
    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.TOTAL
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_precision = 2
    _attr_native_unit_of_measurement = CURRENCY_DOLLAR
    _attr_native_value = None
    _attr_last_reset = None

    def __init__(self, coordinator, meter: Meter):
        """Initialize the SCL Energy Cost Entity class."""
        self.coordinator = coordinator
        self._meter = meter
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"[{self._meter.id}] SCL Meter Cost"

    @property
    def unique_id(self):
        """Return sensor unique_id."""
        return ".".join([DOMAIN, self._meter.id, "cost"])

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
        await super().async_added_to_hass()
        self._update_from_meter()
        self.async_on_remove(self.coordinator.async_add_listener(self._update_from_meter))

    async def async_update(self) -> None:
        """Update the entity.
        Only used by the generic entity update service.
        """
        await self.coordinator.async_request_refresh()

    def _update_from_meter(self) -> None:
        if self.meter_data is not None:
            self._attr_native_value = self.meter_data.cost
            self._attr_last_reset = self.meter_data.date
        self.async_write_ha_state()
