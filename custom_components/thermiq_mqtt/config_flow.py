"""Config flow"""

import logging
import re
import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant.exceptions import HomeAssistantError
from homeassistant import config_entries
from homeassistant.const import __version__ as HAVERSION
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.components.mqtt import valid_subscribe_topic

from .const import (
    DOMAIN,
    CONF_ID,
    CONF_MQTT_NODE,
    CONF_MQTT_HEX,
    CONF_MQTT_DBG,
    CONF_LANGUAGE,
    CONF_MIGRATE_DATA,
    AVAILABLE_LANGUAGES,
)

_LOGGER = logging.getLogger(__name__)

# ToDo:
#   check ID to be spaceless+[a-z/A-Z/0-9]


class DomainConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Component config flow."""

    VERSION = 2

    # FIXME: DOES NOT ACTUALLY VALIDATE ANYTHING! WE NEED THIS! =)
    async def validate_input(self, data):
        """Validate input in step user"""
        return data

    async def async_step_user(self, user_input=None):

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_ID, default="vp1"): cv.string,
                vol.Required(CONF_MQTT_NODE, default="ThermIQ/ThermIQ-mqtt"): cv.string,
                vol.Required(CONF_LANGUAGE, default="en"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["en", "se", "fi", "no", "de"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(CONF_MQTT_HEX, default=False): cv.boolean,
                vol.Required(CONF_MQTT_DBG, default=False): cv.boolean,
                vol.Required(CONF_MIGRATE_DATA, default=False): cv.boolean,
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
        else:

            error_schema = vol.Schema(
                {
                    vol.Required(CONF_ID, default=user_input[CONF_ID]): cv.string,
                    vol.Required(
                        CONF_MQTT_NODE, default=user_input[CONF_MQTT_NODE]
                    ): cv.string,
                    vol.Required(
                        CONF_LANGUAGE, default=user_input[CONF_LANGUAGE]
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["en", "se", "fi", "no", "de"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Required(
                        CONF_MQTT_HEX, default=user_input[CONF_MQTT_HEX]
                    ): cv.boolean,
                    vol.Required(
                        CONF_MQTT_DBG, default=user_input[CONF_MQTT_DBG]
                    ): cv.boolean,
                    vol.Required(
                        CONF_MIGRATE_DATA, default=user_input[CONF_MIGRATE_DATA]
                    ): cv.boolean,
                }
            )

            id_name = user_input[CONF_ID].strip()
            # id_name is embedded verbatim in entity_ids (e.g.
            # number.thermiq_mqtt_<id>_...), so it must be slug-safe
            if not re.fullmatch(r"[a-z0-9_]+", id_name):
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "creation_id"},
                )
            unique_id = f"{DOMAIN}_{id_name}"
            # AbortFlow must propagate so a duplicate ID aborts with
            # "already_configured" instead of a misleading form error
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                prefix = user_input[CONF_MQTT_NODE]
                if prefix.endswith("/#"):
                    prefix = prefix[:-2]
                elif prefix.endswith("/"):
                    prefix = prefix[:-1]
                valid_subscribe_topic(f"{prefix}/#")
            except (vol.Invalid, HomeAssistantError):
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "invalid_nodename"},
                )

            if user_input[CONF_LANGUAGE] not in AVAILABLE_LANGUAGES:
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "invalid_language"},
                )

            return self.async_create_entry(
                title=unique_id,
                data={
                    CONF_ID: id_name,
                    CONF_MQTT_NODE: prefix,
                    CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    CONF_MQTT_HEX: user_input[CONF_MQTT_HEX],
                    CONF_MQTT_DBG: user_input[CONF_MQTT_DBG],
                    CONF_MIGRATE_DATA: user_input[CONF_MIGRATE_DATA],
                },
                options={},
            )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """HASL config flow options handler."""

    def __init__(self, config_entry):
        """Initialize HASL options flow."""
        if AwesomeVersion(HAVERSION) < "2024.11.99":
            self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user(user_input)

    async def validate_input(self, data):
        """Validate input in step user"""
        # FIXME: DOES NOT ACTUALLY VALIDATE ANYTHING! WE NEED THIS! =)
        return data

    async def async_step_user(self, user_input=None):
        s = self.config_entry.data.get(CONF_LANGUAGE)

        DATA_SCHEMA = vol.Schema(
            {
                vol.Required(
                    CONF_MQTT_NODE, default=self.config_entry.data.get(CONF_MQTT_NODE)
                ): cv.string,
                vol.Required(
                    CONF_LANGUAGE,
                    default=self.config_entry.data.get(CONF_LANGUAGE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["en", "se", "fi", "no", "de"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(
                    CONF_MQTT_HEX, default=self.config_entry.data.get(CONF_MQTT_HEX)
                ): cv.boolean,
                vol.Required(
                    CONF_MQTT_DBG, default=self.config_entry.data.get(CONF_MQTT_DBG)
                ): cv.boolean,
                vol.Required(
                    CONF_MIGRATE_DATA,
                    default=self.config_entry.data.get(CONF_MIGRATE_DATA, False),
                ): cv.boolean,
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
        else:
            error_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_MQTT_NODE, default=user_input[CONF_MQTT_NODE]
                    ): cv.string,
                    vol.Required(
                        CONF_LANGUAGE, default=user_input[CONF_LANGUAGE]
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["en", "se", "fi", "no", "de"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                    vol.Required(
                        CONF_MQTT_HEX, default=user_input[CONF_MQTT_HEX]
                    ): cv.boolean,
                    vol.Required(
                        CONF_MQTT_DBG, default=user_input[CONF_MQTT_DBG]
                    ): cv.boolean,
                    vol.Required(
                        CONF_MIGRATE_DATA, default=user_input[CONF_MIGRATE_DATA]
                    ): cv.boolean,
                }
            )

            id_name = self.config_entry.data[CONF_ID]

            try:
                prefix = user_input[CONF_MQTT_NODE]
                if prefix.endswith("/#"):
                    prefix = prefix[:-2]
                elif prefix.endswith("/"):
                    prefix = prefix[:-1]
                valid_subscribe_topic(f"{prefix}/#")

            except (vol.Invalid, HomeAssistantError):
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "invalid_nodename"},
                )

            if user_input[CONF_LANGUAGE] not in AVAILABLE_LANGUAGES:
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "invalid_language"},
                )

            data = {
                CONF_ID: id_name,
                CONF_MQTT_NODE: prefix,
                CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                CONF_MQTT_HEX: user_input[CONF_MQTT_HEX],
                CONF_MQTT_DBG: user_input[CONF_MQTT_DBG],
                CONF_MIGRATE_DATA: user_input[CONF_MIGRATE_DATA],
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=data,
                options={},
            )

            # This is the options entry, keep it empty
            return self.async_create_entry(title="", data={})
