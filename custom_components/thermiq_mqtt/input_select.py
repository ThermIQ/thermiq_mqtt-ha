"""Input numbers used for settings."""
import logging
from typing import List

from homeassistant.components.input_select import (
    CONF_INITIAL,
    CONF_OPTIONS,
    DOMAIN as PLATFORM,
    InputSelect,
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

from .const import CONF_ENTITY_PLATFORM, PLATFORM_INPUT_SELECT

_LOGGER = logging.getLogger(__name__)


class CustomInputSelect(InputSelect):
    register: str
    reg_id: str
    heatpump: HeatPump

    async def async_internal_added_to_hass(self):
        await Entity.async_internal_added_to_hass(self)

    async def async_internal_will_remove_from_hass(self):
        await Entity.async_internal_will_remove_from_hass(self)

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug("inp %s", self.entity_id)
        # We require that we have values from the hp before allowing updates from GUI
        await super().async_select_option(option)
        # is value updated by GUI?
        if self.heatpump._hpstate["mqtt_counter"] > 0:
        	# Using first char in description as value to write is a kludge
            value = int(option[0])
            if value != self.heatpump._hpstate[self.reg]:
                self.heatpump._hpstate[self.reg] = value
                self.heatpump._hass.bus.fire(
                    # This will reload all sensor entities in this heatpump
                    f"{self.heatpump._domain}_{self.heatpump._id}_msg_rec_event",
                    {},
                )
                await self.heatpump.send_mqtt_reg(self.reg_id, value, 0xFFFF)


async def setup_input_selects(heatpump) -> None:
    """Setup input numbers."""

    await update_input_select(heatpump)


async def update_input_select(heatpump) -> None:
    """Update built in input numbers."""

    platform: EntityPlatform = heatpump._hass.data[CONF_ENTITY_PLATFORM][PLATFORM][0]
    to_add: List[CustomInputSelect] = []
    entity_list = []

    for key in reg_id:
        if reg_id[key][1] in [
            "select_input",
        ]:
            inp = create_input_select_entity(heatpump, key)
            to_add.append(inp)
            entity_list.append(
                f"{PLATFORM}.{heatpump._domain}_{heatpump._id}" + "_" + key
            )

    await platform.async_add_entities(to_add)


def create_input_select_entity(heatpump, name) -> CustomInputSelect:
    """Create a CustomInputNumber instance."""

    entity_id = f"{heatpump._domain}_{heatpump._id}_{name}"
    if name in id_names:
        friendly_name = id_names[name][heatpump._langid]
    else:
        friendly_name = None
    icon = None

    config = {
        CONF_ID: entity_id,
        CONF_NAME: friendly_name,
        CONF_OPTIONS: [
            "0 - " + id_names["mode0"][heatpump._langid],
            "1 - " + id_names["mode1"][heatpump._langid],
            "2 - " + id_names["mode2"][heatpump._langid],
            "3 - " + id_names["mode3"][heatpump._langid],
            "4 - " + id_names["mode4"][heatpump._langid],
        ],
        CONF_ICON: icon,
        CONF_INITIAL: None,
    }

    entity = CustomInputSelect.from_yaml(config)
    entity.reg = reg_id[name][0]
    entity.reg_id = name
    entity.heatpump = heatpump
    # Bitmask is all bits
    entity.bitmask = 0xFFFF

    return entity
