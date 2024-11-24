"ConfigFlow definition for watchman"

import os
from types import MappingProxyType
from typing import Any, Dict
from homeassistant.config_entries import (
    ConfigFlow,
    OptionsFlow,
    ConfigEntry,
    ConfigFlowResult,
)
from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, selector
import voluptuous as vol
import anyio
from .utils.utils import async_get_report_path, get_val

from .utils.logger import _LOGGER

from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    CONF_IGNORED_FILES,
    CONF_HEADER,
    CONF_REPORT_PATH,
    CONF_IGNORED_ITEMS,
    CONF_INCLUDED_FOLDERS,
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_STATES,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONF_FRIENDLY_NAMES,
    CONF_SECTION_APPEARANCE_LOCATION,
    MONITORED_STATES,
    DEFAULT_OPTIONS,
)


INCLUDED_FOLDERS_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.string]))
IGNORED_ITEMS_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.string]))
IGNORED_STATES_SCHEMA = vol.Schema(MONITORED_STATES)
IGNORED_FILES_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.string]))
COLUMNS_WIDTH_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.positive_int]))


def _get_data_schema() -> vol.Schema:
    select = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
    return vol.Schema(
        {
            vol.Required(
                CONF_INCLUDED_FOLDERS,
            ): select,
            vol.Optional(
                CONF_IGNORED_ITEMS,
            ): select,
            vol.Optional(
                CONF_IGNORED_STATES,
            ): cv.multi_select(MONITORED_STATES),
            vol.Optional(
                CONF_IGNORED_FILES,
            ): select,
            vol.Required(
                CONF_STARTUP_DELAY,
            ): cv.positive_int,
            vol.Optional(
                CONF_CHECK_LOVELACE,
            ): cv.boolean,
            vol.Required(CONF_SECTION_APPEARANCE_LOCATION): data_entry_flow.section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_REPORT_PATH,
                        ): cv.string,
                        vol.Required(
                            CONF_HEADER,
                        ): cv.string,
                        vol.Required(
                            CONF_COLUMNS_WIDTH,
                        ): cv.string,
                        vol.Optional(
                            CONF_FRIENDLY_NAMES,
                        ): cv.boolean,
                    }
                ),
                {"collapsed": True},
            ),
        }
    )


async def _async_validate_input(
    hass: HomeAssistant,
    user_input: dict[str, Any] | None = None,
) -> tuple[MappingProxyType[str, str], MappingProxyType[str, str]]:
    errors: Dict[str, str] = {}
    placeholders: Dict[str, str] = {}
    # check user supplied folders
    if CONF_INCLUDED_FOLDERS in user_input:
        included_folders_list = [
            x.strip() for x in user_input[CONF_INCLUDED_FOLDERS].split(",") if x.strip()
        ]
        for path in included_folders_list:
            if not await anyio.Path(path).exists():
                errors |= {
                    CONF_INCLUDED_FOLDERS: "{} is not a valid path ".format(path)
                }
                placeholders["path"] = path
                break

    columns_width = get_val(
        user_input, CONF_COLUMNS_WIDTH, CONF_SECTION_APPEARANCE_LOCATION
    )
    if columns_width:
        try:
            columns_width = [int(x) for x in columns_width.split(",") if x.strip()]
            if len(columns_width) != 3:
                raise ValueError()
            columns_width = COLUMNS_WIDTH_SCHEMA(columns_width)
            # user_input[CONF_COLUMNS_WIDTH] = get_columns_width(columns_width)
        except (ValueError, vol.Invalid):
            errors["base"] = "invalid_columns_width"

    report_path = get_val(
        user_input, CONF_REPORT_PATH, CONF_SECTION_APPEARANCE_LOCATION
    )
    if report_path:
        folder, _ = os.path.split(report_path)
        if not await anyio.Path(folder).exists():
            errors["base"] = "invalid_report_path"

    return (
        MappingProxyType[str, str](errors),
        MappingProxyType[str, str](placeholders),
    )


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """
    Config flow used to set up new instance of integration
    """

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        _LOGGER.debug("::async_step_user::")
        options = DEFAULT_OPTIONS
        options[CONF_SECTION_APPEARANCE_LOCATION][
            CONF_REPORT_PATH
        ] = await async_get_report_path(self.hass, None)
        options[CONF_INCLUDED_FOLDERS] = self.hass.config.path()
        options[CONF_IGNORED_FILES] = DEFAULT_OPTIONS[CONF_IGNORED_FILES]
        return self.async_create_entry(title="Watchman", data=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """
    Options flow used to change configuration (options) of existing instance of integration
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        _LOGGER.debug("::OptionsFlowHandler.__init::")
        self.config_entry = config_entry

    async def async_get_key_in_section(self, data, key, section=None):
        if section:
            if section in data:
                return section[data].get(key, None)
        else:
            return data.get(key, None)
        return None

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """
        Manage the options form. This method is invoked twice:
        1. To populate form with default values (user_input=None)
        2. To validate values entered by user (user_imput = {user_data})
           If no errors found, it should return creates_entry
        """

        _LOGGER.debug(
            f"-======::OptionsFlowHandler.async_step_init::======- \nuser_input= {user_input},\nentry_data={self.config_entry.data}"
        )

        if user_input is not None:  # we asked to validate values entered by user
            errors, placeholders = await _async_validate_input(self.hass, user_input)
            if not errors:
                # if user cleared up `ignored files` or `ignored items` form fields
                # user_input dict dict will not contain these keys, so we add them explicitly
                if (
                    CONF_IGNORED_FILES in self.config_entry.data
                    and CONF_IGNORED_FILES not in user_input
                ):
                    user_input[CONF_IGNORED_FILES] = ""

                if (
                    CONF_IGNORED_ITEMS in self.config_entry.data
                    and CONF_IGNORED_ITEMS not in user_input
                ):
                    user_input[CONF_IGNORED_ITEMS] = ""

                # see met.no code, without update_entry the EXISTING entry
                # will not be updated with user input, but entry.options will do
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data={**self.config_entry.data, **user_input}
                )
                # await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})
            else:
                # in case of errors in user_input, display them in the form
                # use previous user input as suggested values
                _LOGGER.debug(
                    "::OptionsFlowHandler.async_step_init:: validation results errors:[%s] placehoders:[%s]",
                    errors,
                    placeholders,
                )
                return self.async_show_form(
                    step_id="init",
                    data_schema=self.add_suggested_values_to_schema(
                        _get_data_schema(),
                        user_input,
                    ),
                    errors=dict(errors),
                    description_placeholders=dict(placeholders),
                )
        # we asked to provide default values for the form
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _get_data_schema(),
                self.config_entry.data,
            ),
        )
