"""Data update coordinator for Watchman"""

import logging
import time
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import (
    COORD_DATA_ENTITY_ATTRS,
    COORD_DATA_LAST_UPDATE,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_MISSING_SERVICES,
    COORD_DATA_SERVICE_ATTRS,
    DOMAIN,
    HASS_DATA_CHECK_DURATION,
    HASS_DATA_MISSING_ENTITIES,
    HASS_DATA_MISSING_SERVICES,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
)
from .utils.utils import check_entitites, check_services, get_entity_state, fill
from .utils.logger import _LOGGER


class WatchmanCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, logger, name):
        """Initialize watchmman coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,  # Name of the data. For logging purposes.
        )
        self.hass = hass
        self.data = {}

    async def _async_update_data(self) -> None:
        """Fetch data from API endpoint."""
        start_time = time.time()
        services_missing = check_services(self.hass)
        entities_missing = check_entitites(self.hass)
        self.hass.data[DOMAIN][HASS_DATA_CHECK_DURATION] = time.time() - start_time
        self.hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES] = entities_missing
        self.hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES] = services_missing

        # build entity attributes map for missing_entities sensor
        entity_attrs = []
        parsed_entity_list = self.hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST]
        for entity in entities_missing:
            state, name = get_entity_state(self.hass, entity, friendly_names=True)
            entity_attrs.append(
                {
                    "id": entity,
                    "state": state,
                    "friendly_name": name or "",
                    "occurrences": fill(parsed_entity_list[entity], 0),
                }
            )

        # build service attributes map for missing_services sensor
        service_attrs = []
        parsed_service_list = self.hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST]
        for service in services_missing:
            service_attrs.append(
                {"id": service, "occurrences": fill(parsed_service_list[service], 0)}
            )

        self.data = {
            COORD_DATA_MISSING_ENTITIES: len(entities_missing),
            COORD_DATA_MISSING_SERVICES: len(services_missing),
            COORD_DATA_LAST_UPDATE: dt_util.now(),
            COORD_DATA_SERVICE_ATTRS: service_attrs,
            COORD_DATA_ENTITY_ATTRS: entity_attrs,
        }

        _LOGGER.debug(
            f"::coordinator:: Watchman sensors updated, actions: {len(services_missing)}, entities: {len(entities_missing)}"
        )
        return self.data
