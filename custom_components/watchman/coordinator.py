"""Data update coordinator for Watchman"""

import logging
import time
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import DOMAIN
from .utils import check_entitites, check_services, get_entity_state, fill


_LOGGER = logging.getLogger(__name__)


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
        self.hass.data[DOMAIN]["check_duration"] = time.time() - start_time
        self.hass.data[DOMAIN]["entities_missing"] = entities_missing
        self.hass.data[DOMAIN]["services_missing"] = services_missing

        # build entity attributes map for missing_entities sensor
        entity_attrs = []
        entity_list = self.hass.data[DOMAIN]["entity_list"]
        for entity in entities_missing:
            state, name = get_entity_state(self.hass, entity, friendly_names=True)
            entity_attrs.append(
                {
                    "id": entity,
                    "state": state,
                    "friendly_name": name or "",
                    "occurrences": fill(entity_list[entity], 0),
                }
            )

        # build service attributes map for missing_services sensor
        service_attrs = []
        service_list = self.hass.data[DOMAIN]["service_list"]
        for service in services_missing:
            service_attrs.append(
                {"id": service, "occurrences": fill(service_list[service], 0)}
            )

        self.data = {
            "entities_missing": len(entities_missing),
            "services_missing": len(services_missing),
            "last_update": dt_util.now(),
            "service_attrs": service_attrs,
            "entity_attrs": entity_attrs,
        }

        _LOGGER.debug("Watchman sensors updated")
        _LOGGER.debug("entities missing: %s", len(entities_missing))
        _LOGGER.debug("services missing: %s", len(services_missing))

        return self.data
