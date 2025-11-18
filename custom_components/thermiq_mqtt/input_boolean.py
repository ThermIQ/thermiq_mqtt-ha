"""Input boolean used for settings."""
import logging
from typing import List, Any
import voluptuous as vol


from contextlib import suppress
from homeassistant.core import HomeAssistant
from homeassistant.components.input_boolean import (
    CONF_INITIAL,
    STATE_ON,
    InputBoolean,

)



from homeassistant.const import (
    CONF_ICON,
    CONF_ID,
    CONF_NAME,

)

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import EntityPlatform

from .heatpump import HeatPump
from .heatpump.thermiq_regs import (
    FIELD_BITMASK,
    FIELD_MAXVALUE,
    FIELD_MINVALUE,
    FIELD_REGNUM,
    FIELD_REGTYPE,
    FIELD_UNIT,
    id_names,
    reg_id,
)

from .const import CONF_ENTITY_PLATFORM, PLATFORM_INPUT_BOOLEAN

_LOGGER = logging.getLogger(__name__)


PLATFORM = PLATFORM_INPUT_BOOLEAN
SERVICE_SET_VALUE = "async_set_value"


class CustomInputBoolean(InputBoolean):
    register: str
    reg_id: str
    reg: str
    bitmask: int
    heatpump: HeatPump

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        # Don't restore if we got an initial value.
        await super().async_added_to_hass()
        if self._config.get(CONF_INITIAL) is not None:
            return

        state = await self.async_get_last_state()
        self._attr_is_on = state is not None and state.state == STATE_ON


    async def async_internal_will_remove_from_hass(self):
        await Entity.async_internal_will_remove_from_hass(self)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.async_set_value(False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.async_set_value(True)

    async def async_set_value(self, value)-> None:
        """Set the entity to value."""
        _LOGGER.debug("inp %s", self.entity_id)
        _LOGGER.debug("async_set: %s [%s]", self.entity_id, value)
        # is value updated by GUI?
        if value:
            self._attr_is_on = True
            self.async_write_ha_state()
            reg=1
        else:
            self._attr_is_on = False
            self.async_write_ha_state()
            reg=0
        # We require that we have values from the hp before sending MQTT msgs
        mqtt_ctr=self.heatpump._hpstate['mqtt_counter']
        if mqtt_ctr > 0:
            if self.heatpump._hpstate[self.reg] != reg:
                self.heatpump._hpstate[self.reg] = reg
                self.heatpump._hass.bus.fire(
                    # This will reload all sensor entities in this heatpump
                    f"{self.heatpump._domain}_{self.heatpump._id}_msg_rec_event",
                    {},
                )
                await self.heatpump.send_mqtt_reg(self.reg_id, value, 0xFFFF)


async def setup_input_booleans(heatpump) -> None:
    """Setup input boolean."""

    await update_input_boolean(heatpump)


async def update_input_boolean(heatpump) -> None:
    """Update built in input boolean."""

    platform: EntityPlatform = heatpump._hass.data[CONF_ENTITY_PLATFORM][PLATFORM][0]
    to_add: List[CustomInputBoolean] = []
    entity_list = []

    for key in reg_id:
        if reg_id[key][FIELD_REGTYPE] in [
            "generated_input_boolean",
        ]:
            value = None
            entity_id = f"input_boolean.{heatpump._domain}_{heatpump._id}_{key}"
            bitmask=reg_id[key][FIELD_BITMASK]


            inp = create_input_boolean_entity(heatpump, key,value,bitmask)
            to_add.append(inp)
#            entity_list.append(
#                f"{PLATFORM}.{heatpump._domain}_{heatpump._id}" + "_" + key
#            )

    await platform.async_add_entities(to_add)
    platform.async_register_entity_service(SERVICE_SET_VALUE,{ vol.Required('value'): vol.Coerce(bool)}, "async_set_value")


def create_input_boolean_entity(heatpump, name, value, bitmask) -> CustomInputBoolean:
    """Create a CustomInputBoolean instance."""

    entity_id = f"{heatpump._domain}_{heatpump._id}_{name}"

    if name in id_names:
        friendly_name = id_names[name][heatpump._langid]
    else:
        friendly_name = name

    icon = "mdi:gauge"

    config = {
        CONF_ID: entity_id,
        CONF_NAME: friendly_name,
        CONF_ICON: icon,
        CONF_INITIAL: False,
    }

    entity = CustomInputBoolean.from_yaml(config)
    entity.reg = reg_id[name][FIELD_REGNUM]
    entity.reg_id = name
    entity.heatpump = heatpump
    # Bitmask is all bits
    entity.bitmask = bitmask

    _LOGGER.debug("entity_id:" + entity.entity_id)
    if value is not None:
        _LOGGER.debug("value:" + value)
    return entity