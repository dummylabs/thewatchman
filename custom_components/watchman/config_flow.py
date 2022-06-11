"ConfigFlow definition for watchman"
from typing import Dict
import json
from json.decoder import JSONDecodeError
import logging
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector
import voluptuous as vol
from .utils import is_service, get_columns_width, get_report_path

from .const import (
    DOMAIN,
    CONF_IGNORED_FILES,
    CONF_HEADER,
    CONF_REPORT_PATH,
    CONF_IGNORED_ITEMS,
    CONF_SERVICE_NAME,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA2,
    CONF_INCLUDED_FOLDERS,
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_STATES,
    CONF_CHUNK_SIZE,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONF_FRIENDLY_NAMES,
)

DEFAULT_DATA = {
    CONF_SERVICE_NAME: "",
    CONF_SERVICE_DATA2: "{}",
    CONF_INCLUDED_FOLDERS: ["/config"],
    CONF_HEADER: "-== Watchman Report ==-",
    CONF_REPORT_PATH: "",
    CONF_IGNORED_ITEMS: [],
    CONF_IGNORED_STATES: [],
    CONF_CHUNK_SIZE: 3500,
    CONF_IGNORED_FILES: [],
    CONF_CHECK_LOVELACE: False,
    CONF_COLUMNS_WIDTH: [30, 7, 60],
    CONF_STARTUP_DELAY: 0,
    CONF_FRIENDLY_NAMES: False,
}

INCLUDED_FOLDERS_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.string]))
IGNORED_ITEMS_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.string]))
IGNORED_STATES_SCHEMA = vol.Schema(["missing", "unavailable", "unknown"])
IGNORED_FILES_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.string]))
COLUMNS_WIDTH_SCHEMA = vol.Schema(vol.All(cv.ensure_list, [cv.positive_int]))

_LOGGER = logging.getLogger(__name__)


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow"""

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Watchman", data={}, options=DEFAULT_DATA)

    async def async_step_import(self, import_data):
        """Import configuration.yaml settings as OptionsEntry"""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        # change "data" key from configuration.yaml to "service_data" as "data" is reserved by
        # OptionsFlow
        import_data[CONF_SERVICE_DATA2] = import_data.get(CONF_SERVICE_DATA, {})
        if CONF_SERVICE_DATA in import_data:
            import_data.pop(CONF_SERVICE_DATA)
        _LOGGER.info(
            "watchman settings imported successfully and can be removed from "
            "configuration.yaml"
        )
        _LOGGER.debug("configuration.yaml settings successfully imported to UI options")
        return self.async_create_entry(
            title="configuration.yaml", data={}, options=import_data
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    def default(self, key, uinput=None):
        """provide default value for an OptionsFlow field"""
        if uinput and key in uinput:
            # supply last entered value to display an error during form validation
            result = uinput[key]
        else:
            # supply last saved value or default one
            result = self.config_entry.options.get(key, DEFAULT_DATA[key])

        if result == "":
            # some default values cannot be empty
            if DEFAULT_DATA[key]:
                result = DEFAULT_DATA[key]
            elif key == CONF_REPORT_PATH:
                result = get_report_path(self.hass, None)

        if isinstance(result, list):
            return ", ".join([str(i) for i in result])
        if isinstance(result, dict):
            return json.dumps(result)
        if isinstance(result, bool):
            return result
        return str(result)

    def to_list(self, user_input, key):
        """validate user input against list requirements"""
        errors: Dict[str, str] = {}

        if key not in user_input:
            return DEFAULT_DATA[key], errors

        val = user_input[key]
        val = [x.strip() for x in val.split(",") if x.strip()]
        try:
            val = INCLUDED_FOLDERS_SCHEMA(val)
        except vol.Invalid:
            errors[key] = f"invalid_{key}"
        return val, errors

    async def _show_options_form(
        self, uinput=None, errors=None, placehoders=None
    ):  # pylint: disable=unused-argument
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SERVICE_NAME,
                        description={
                            "suggested_value": self.default(CONF_SERVICE_NAME, uinput)
                        },
                    ): cv.string,
                    vol.Optional(
                        CONF_SERVICE_DATA2,
                        description={
                            "suggested_value": self.default(CONF_SERVICE_DATA2, uinput)
                        },
                    ): selector.TemplateSelector(),
                    vol.Optional(
                        CONF_INCLUDED_FOLDERS,
                        description={
                            "suggested_value": self.default(
                                CONF_INCLUDED_FOLDERS, uinput
                            )
                        },
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_HEADER,
                        description={
                            "suggested_value": self.default(CONF_HEADER, uinput)
                        },
                    ): cv.string,
                    vol.Optional(
                        CONF_REPORT_PATH,
                        description={
                            "suggested_value": self.default(CONF_REPORT_PATH, uinput)
                        },
                    ): cv.string,
                    vol.Optional(
                        CONF_IGNORED_ITEMS,
                        description={
                            "suggested_value": self.default(CONF_IGNORED_ITEMS, uinput)
                        },
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_IGNORED_STATES,
                        description={
                            "suggested_value": self.default(CONF_IGNORED_STATES, uinput)
                        },
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_CHUNK_SIZE,
                        description={
                            "suggested_value": self.default(CONF_CHUNK_SIZE, uinput)
                        },
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_IGNORED_FILES,
                        description={
                            "suggested_value": self.default(CONF_IGNORED_FILES, uinput)
                        },
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_COLUMNS_WIDTH,
                        description={
                            "suggested_value": self.default(CONF_COLUMNS_WIDTH, uinput)
                        },
                    ): cv.string,
                    vol.Optional(
                        CONF_STARTUP_DELAY,
                        description={
                            "suggested_value": self.default(CONF_STARTUP_DELAY, uinput)
                        },
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_FRIENDLY_NAMES,
                        description={
                            "suggested_value": self.default(CONF_FRIENDLY_NAMES, uinput)
                        },
                    ): cv.boolean,
                    vol.Optional(
                        CONF_CHECK_LOVELACE,
                        description={
                            "suggested_value": self.default(CONF_CHECK_LOVELACE, uinput)
                        },
                    ): cv.boolean,
                }
            ),
            errors=errors or {},
            description_placeholders=placehoders or {},
        )

    async def async_step_init(self, user_input=None):
        """Manage the options"""
        errors: Dict[str, str] = {}
        placehoders: Dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_INCLUDED_FOLDERS], err = self.to_list(
                user_input, CONF_INCLUDED_FOLDERS
            )
            errors |= err
            user_input[CONF_IGNORED_ITEMS], err = self.to_list(
                user_input, CONF_IGNORED_ITEMS
            )
            errors |= err
            ignored_states, err = self.to_list(user_input, CONF_IGNORED_STATES)
            errors |= err
            try:
                user_input[CONF_IGNORED_STATES] = IGNORED_STATES_SCHEMA(ignored_states)
            except vol.Invalid:
                errors[CONF_IGNORED_STATES] = "wrong_value_ignored_states"

            user_input[CONF_IGNORED_FILES], err = self.to_list(
                user_input, CONF_IGNORED_FILES
            )
            errors |= err

            if CONF_COLUMNS_WIDTH in user_input:
                columns_width = user_input[CONF_COLUMNS_WIDTH]
                try:
                    columns_width = [
                        int(x) for x in columns_width.split(",") if x.strip()
                    ]
                    if len(columns_width) != 3:
                        raise ValueError()
                    columns_width = COLUMNS_WIDTH_SCHEMA(columns_width)
                    user_input[CONF_COLUMNS_WIDTH] = get_columns_width(columns_width)
                except (ValueError, vol.Invalid):
                    errors[CONF_COLUMNS_WIDTH] = "invalid_columns_width"

            if CONF_SERVICE_DATA2 in user_input:
                try:
                    result = json.loads(user_input[CONF_SERVICE_DATA2])
                    if not isinstance(result, dict):
                        errors[CONF_SERVICE_DATA2] = "malformed_json"
                except JSONDecodeError:
                    errors[CONF_SERVICE_DATA2] = "malformed_json"
            if CONF_SERVICE_NAME in user_input:
                if not is_service(self.hass, user_input[CONF_SERVICE_NAME]):
                    errors[CONF_SERVICE_NAME] = "unknown_service"
                    placehoders["service"] = user_input[CONF_SERVICE_NAME]

            if not errors:
                return self.async_create_entry(title="", data=user_input)
            else:
                # provide last entered values to display error
                return await self._show_options_form(user_input, errors, placehoders)
        # provide default values
        return await self._show_options_form()
