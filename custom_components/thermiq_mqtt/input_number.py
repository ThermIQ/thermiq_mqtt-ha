"""Input numbers used for settings."""
import logging
from typing import List

from contextlib import suppress

from homeassistant.components.input_number import (
    CONF_INITIAL,
    CONF_MAX,
    CONF_MIN,
    CONF_STEP,
    InputNumber,
    MODE_BOX,
)
from homeassistant.const import (
    CONF_ICON,
    CONF_ID,
    CONF_UNIQUE_ID,
    CONF_MODE,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    UnitOfTemperature,
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

from .const import CONF_ENTITY_PLATFORM, PLATFORM_INPUT_NUMBER

_LOGGER = logging.getLogger(__name__)


PLATFORM = PLATFORM_INPUT_NUMBER


class CustomInputNumber(InputNumber):
    register: str
    reg_id: str
    reg: str
    heatpump: HeatPump
    unique_id: str

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        #await super().async_added_to_hass()
        if self._current_value is not None:
            return

        value: float | None = None
        if state := await self.async_get_last_state():
            with suppress(ValueError):
                value = float(state.state)

        # Check against None because value can be 0
        if value is not None and self._minimum <= value <= self._maximum:
            self._current_value = value
        else:
            self._current_value = None #Keep as none to maintain historic values and avoid gaps when starting up. Will get a value with first mqtt message

    async def async_internal_will_remove_from_hass(self):
        await Entity.async_internal_will_remove_from_hass(self)

    async def async_set_value(self, value):
        _LOGGER.debug("inp %s", self.entity_id)
        # We require that we have values from the hp before allowing updates from GUI
        await super().async_set_value(value)
        _LOGGER.debug("async_set: " + self.entity_id)
        # is value updated by GUI?
        if self.heatpump._hpstate["mqtt_counter"] > -1:
            if value != self.heatpump._hpstate[self.reg]:
                self.heatpump._hpstate[self.reg] = value
                self.heatpump._hass.bus.fire(
                    # This will reload all sensor entities in this heatpump
                    f"{self.heatpump._domain}_{self.heatpump._id}_msg_rec_event",
                    {},
                )
                await self.heatpump.send_mqtt_reg(self.reg_id, value, 0xFFFF)


async def setup_input_numbers(heatpump) -> None:
    """Setup input numbers."""

    await update_input_numbers(heatpump)


async def update_input_numbers(heatpump) -> None:
    """Update built in input numbers."""

    platform: EntityPlatform = heatpump._hass.data[CONF_ENTITY_PLATFORM][PLATFORM][0]
    to_add: List[CustomInputNumber] = []
    entity_list = []

    for key in reg_id:
        if reg_id[key][1] in [
            "temperature_input",
            "time_input",
            "sensor_input",
            "generated_input",
        ]:
            value = None
            entity_id = f"input_number.{heatpump._domain}_{heatpump._id}_{key}"

            inp = create_input_number_entity(heatpump, key,value)
            to_add.append(inp)
            entity_list.append(
                f"{PLATFORM}.{heatpump._domain}_{heatpump._id}" + "_" + key
            )

    await platform.async_add_entities(to_add)


def create_input_number_entity(heatpump, name, value) -> CustomInputNumber:
    """Create a CustomInputNumber instance."""

    entity_id = f"{heatpump._domain}_{heatpump._id}_{name}"

    if name in id_names:
        friendly_name = id_names[name][heatpump._langid]
    else:
        friendly_name = name
    input_step = 1
    if reg_id[name][0] == "indr_t":
        input_step = 0.1
    icon = None
    unit = None
    if (reg_id[name][1] in ["temperature_input",]) or (
        reg_id[name][2]
        in [
            "C",
        ]
    ):
        icon = "mdi:temperature-celsius"
        unit = UnitOfTemperature.CELSIUS
    else:
        unit = reg_id[name][2]
        icon = "mdi:gauge"
    # "mdi:thermometer" ,"mdi:oil-temperature", "mdi:gauge", "mdi:speedometer", "mdi:alert"


    config = {
        CONF_ID: entity_id,
        CONF_NAME: friendly_name,
        CONF_MIN: reg_id[name][3],
        CONF_MAX: reg_id[name][4],
        CONF_STEP: input_step,
        CONF_ICON: icon,
        CONF_MODE: MODE_BOX,
        CONF_INITIAL: None,
        CONF_UNIT_OF_MEASUREMENT: unit,
    }

    entity = CustomInputNumber.from_yaml(config)
    entity.reg = reg_id[name][0]
    entity.reg_id = name
    entity.heatpump = heatpump
    # Bitmask is all bits
    entity.bitmask = 0xFFFF

    _LOGGER.debug("entity_id:" + entity.entity_id)
    if value is not None:
        _LOGGER.debug("value:" + value)

    return entity