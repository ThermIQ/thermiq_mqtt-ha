"""Config flow"""
import logging
import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv


from .const import (
    DOMAIN,
    CONF_ID,
    CONF_MQTT_NODE,
    CONF_MQTT_HEX,
    CONF_MQTT_DBG,
    CONF_MQTT_LANGUAGE,
    AVAILABLE_LANGUAGES,
)

_LOGGER = logging.getLogger(__name__)


class InvalidPostalCode(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidDomainName(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class DomainConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Component config flow."""

    VERSION = 1

    # FIXME: DOES NOT ACTUALLY VALIDATE ANYTHING! WE NEED THIS! =)
    async def validate_input(self, data):
        """Validate input in step user"""
        return data

    async def async_step_user(self, user_input=None):

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ID, default="vp1"): cv.string,
                vol.Required(CONF_MQTT_NODE, default="ThermIQ/ThermIQ-mqtt"): cv.string,
                vol.Optional(CONF_MQTT_LANGUAGE, default="en"): cv.string,
                vol.Required(CONF_MQTT_HEX, default=False): cv.boolean,
                vol.Required(CONF_MQTT_DBG, default=False): cv.boolean,
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=data_schema)
        else:

            error_schema = vol.Schema(
                {
                    vol.Required(CONF_ID, default=user_input[CONF_ID]): cv.string,
                    vol.Required(
                        CONF_MQTT_NODE, default=user_input[CONF_MQTT_NODE]
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_LANGUAGE, default=user_input[CONF_MQTT_LANGUAGE]
                    ): cv.string,
                    vol.Required(
                        CONF_MQTT_HEX, default=user_input[CONF_MQTT_HEX]
                    ): cv.boolean,
                    vol.Required(
                        CONF_MQTT_DBG, default=user_input[CONF_MQTT_DBG]
                    ): cv.boolean,
                }
            )

            try:
                id_name = user_input[CONF_ID]
            except:
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "invalid_nodename"},
                )

            try:
                lang = AVAILABLE_LANGUAGES.index(user_input[CONF_MQTT_LANGUAGE])

            except:
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "invalid_language"},
                )

            try:

                unique_id = f"{DOMAIN}_{id_name}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                _LOGGER.error(f"[cfg_flow async_step_user] Title[{unique_id}]")
                _LOGGER.error(f"ID[{id_name}]")

                _LOGGER.error(f"mqtt_node: [{user_input[CONF_MQTT_NODE]}]")

                _LOGGER.error(f"Language[{user_input[CONF_MQTT_LANGUAGE]}]")
                if user_input[CONF_MQTT_DBG] is True:
                    _LOGGER.error("MQTT Debug write enabled")
                else:
                    _LOGGER.error("MQTT Debug write disabled")

                if user_input[CONF_MQTT_HEX] == True:
                    _LOGGER.error("Using HEX format")
                else:
                    _LOGGER.error("Using Dec format")

                return self.async_create_entry(
                    title=unique_id,
                    data={
                        CONF_ID: id_name,
                        CONF_MQTT_NODE: user_input[CONF_MQTT_NODE],
                        CONF_MQTT_LANGUAGE: user_input[CONF_MQTT_LANGUAGE],
                        CONF_MQTT_HEX: user_input[CONF_MQTT_HEX],
                        CONF_MQTT_DBG: user_input[CONF_MQTT_DBG],
                    },
                    options={},
                )
            except:
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "creation_error"},
                )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """HASL config flow options handler."""

    def __init__(self, config_entry):
        """Initialize HASL options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user(user_input)

    async def validate_input(self, data):
        """Validate input in step user"""
        # FIXME: DOES NOT ACTUALLY VALIDATE ANYTHING! WE NEED THIS! =)
        return data

    async def async_step_user(self, user_input=None):

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_MQTT_NODE, default=self.config_entry.data.get(CONF_MQTT_NODE)
                ): cv.string,
                vol.Optional(
                    CONF_MQTT_LANGUAGE,
                    default=self.config_entry.data.get(CONF_MQTT_LANGUAGE),
                ): cv.string,
                vol.Required(
                    CONF_MQTT_HEX, default=self.config_entry.data.get(CONF_MQTT_HEX)
                ): cv.boolean,
                vol.Required(
                    CONF_MQTT_DBG, default=self.config_entry.data.get(CONF_MQTT_DBG)
                ): cv.boolean,
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=data_schema)
        else:
            error_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_MQTT_NODE, default=user_input[CONF_MQTT_NODE]
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_LANGUAGE, default=user_input[CONF_MQTT_LANGUAGE]
                    ): cv.string,
                    vol.Required(
                        CONF_MQTT_HEX, default=user_input[CONF_MQTT_HEX]
                    ): cv.boolean,
                    vol.Required(
                        CONF_MQTT_DBG, default=user_input[CONF_MQTT_DBG]
                    ): cv.boolean,
                }
            )

            try:
                entryTitle = self.config_entry.title
                id_name = self.config_entry.data[CONF_ID]
                lang = AVAILABLE_LANGUAGES.index(user_input[CONF_MQTT_LANGUAGE])
                _LOGGER.error(
                    f"[opt_flow async_step_user] unique[{self.config_entry.unique_id}]"
                )
                _LOGGER.error(f"Title[{entryTitle}]")
                _LOGGER.error(f"ID[{id_name}]")

                _LOGGER.error(f"mqtt_node: [{user_input[CONF_MQTT_NODE]}]")

                _LOGGER.error(f"Language[{user_input[CONF_MQTT_LANGUAGE]}]")
                if user_input[CONF_MQTT_DBG] is True:
                    _LOGGER.error("MQTT Debug write enabled")
                else:
                    _LOGGER.error("MQTT Debug write disabled")

                if user_input[CONF_MQTT_HEX] == True:
                    _LOGGER.error("Using HEX format")
                else:
                    _LOGGER.error("Using Dec format")
                data = {
                    CONF_ID: id_name,
                    CONF_MQTT_NODE: user_input[CONF_MQTT_NODE],
                    CONF_MQTT_LANGUAGE: user_input[CONF_MQTT_LANGUAGE],
                    CONF_MQTT_HEX: user_input[CONF_MQTT_HEX],
                    CONF_MQTT_DBG: user_input[CONF_MQTT_DBG],
                }
                _LOGGER.error(f"Title:{entryTitle} Data:{str(data)}")
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=data,
                    options={},
                )

                # This is the options entry, jeep it empty
                return self.async_create_entry(title="", data={})

            except:
                return self.async_show_form(
                    step_id="user",
                    data_schema=error_schema,
                    errors={"base": "update_error"},
                )
