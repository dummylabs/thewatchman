"""Data update coordinator for Watchman."""

import time
import asyncio
from token import INDENT
from typing import Any
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .utils.report import fill
from .utils.parser import parse_config
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
from .utils.utils import (
    renew_missing_entities_list,
    renew_missing_actions_list,
    get_entity_state,
    get_entry,
)
from .utils.logger import _LOGGER

parser_lock = asyncio.Lock()


class WatchmanCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, logger, name):
        """Initialize watchmman coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,  # Name of the data. For logging purposes.
            always_update=False,
        )

        self.hass = hass
        self.data = {
            COORD_DATA_MISSING_ENTITIES: 0,
            COORD_DATA_MISSING_SERVICES: 0,
            COORD_DATA_LAST_UPDATE: dt_util.now(),
            COORD_DATA_SERVICE_ATTRS: "",
            COORD_DATA_ENTITY_ATTRS: "",
        }

    async def _async_setup(self) -> None:
        """Do initialization logic."""
        _LOGGER.debug("::coordinator._async_setup::")
        if self.hass.is_running:
            # integration reloaded or options changed via UI
            _LOGGER.debug(f"{INDENT} hass up and running, try to parse config")
            await parse_config(self.hass, reason="changes in watchman configuration")
        else:
            _LOGGER.debug(f"{INDENT} hass is still loading, do nothing yet")
            # first run, home assistant still loading
            # parse_config will be scheduled once HA is fully loaded

    async def _async_update_data(self) -> dict[str, Any]:
        """Update Watchman sensors.

        Update will trigger parsing of configuration files if entry.runtime_data.force_parsing is set
        """

        if not parser_lock.locked():
            async with parser_lock:
                entry = get_entry(self.hass)
                _LOGGER.debug(
                    f"::coordinator._async_update_data:: force_parsing {entry.runtime_data.force_parsing}, parse_reason: {entry.runtime_data.parse_reason}"
                )

                if self.hass.is_running:
                    if entry.runtime_data.force_parsing:
                        await parse_config(
                            self.hass, reason=entry.runtime_data.parse_reason
                        )
                        entry.runtime_data.force_parsing = False
                    start_time = time.time()
                    services_missing = renew_missing_actions_list(self.hass)
                    entities_missing = renew_missing_entities_list(self.hass)
                    self.hass.data[DOMAIN][HASS_DATA_CHECK_DURATION] = (
                        time.time() - start_time
                    )
                    self.hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES] = (
                        entities_missing
                    )
                    self.hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES] = (
                        services_missing
                    )

                    # build entity attributes map for missing_entities sensor
                    entity_attrs = []
                    parsed_entity_list = self.hass.data[DOMAIN][
                        HASS_DATA_PARSED_ENTITY_LIST
                    ]
                    for entity in entities_missing:
                        state, name = get_entity_state(
                            self.hass, entity, friendly_names=True
                        )
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
                    parsed_service_list = self.hass.data[DOMAIN][
                        HASS_DATA_PARSED_SERVICE_LIST
                    ]
                    for service in services_missing:
                        service_attrs.append(
                            {
                                "id": service,
                                "occurrences": fill(parsed_service_list[service], 0),
                            }
                        )

                    self.data = {
                        COORD_DATA_MISSING_ENTITIES: len(entities_missing),
                        COORD_DATA_MISSING_SERVICES: len(services_missing),
                        COORD_DATA_LAST_UPDATE: dt_util.now(),
                        COORD_DATA_SERVICE_ATTRS: service_attrs,
                        COORD_DATA_ENTITY_ATTRS: entity_attrs,
                    }
                    _LOGGER.debug(
                        f"::coordinator:: Watchman sensors updated, actions: {self.data[COORD_DATA_MISSING_SERVICES]}, entities: {self.data[COORD_DATA_MISSING_ENTITIES]}"
                    )

                    return self.data
        return {}
