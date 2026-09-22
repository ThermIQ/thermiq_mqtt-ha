"""Tests for the ThermIQ config flow validation paths.

The flow object is driven directly (not via flow.async_init) so the test
does not have to set up the integration's mqtt/recorder dependencies.
"""

import pytest

from homeassistant.data_entry_flow import AbortFlow, FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thermiq_mqtt.config_flow import DomainConfigFlow
from custom_components.thermiq_mqtt.const import DOMAIN

VALID_INPUT = {
    "id_name": "vp1",
    "mqtt_node": "ThermIQ/ThermIQ-mqtt",
    "language": "en",
    "hexformat": False,
    "thermiq_dbg": False,
    "migrate_data": False,
}


def _make_flow(hass):
    flow = DomainConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {}
    return flow


async def test_form_is_shown(hass):
    flow = _make_flow(hass)
    result = await flow.async_step_user(None)
    assert result["type"] == FlowResultType.FORM
    assert not result.get("errors")


async def test_valid_input_creates_entry(hass):
    flow = _make_flow(hass)
    result = await flow.async_step_user(dict(VALID_INPUT))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{DOMAIN}_vp1"
    assert result["data"]["id_name"] == "vp1"
    assert result["data"]["mqtt_node"] == "ThermIQ/ThermIQ-mqtt"


@pytest.mark.parametrize("bad_id", ["VP 1", "vp-1", "Vp1", "vp/1", ""])
async def test_id_name_must_be_slug_safe(hass, bad_id):
    flow = _make_flow(hass)
    result = await flow.async_step_user({**VALID_INPUT, "id_name": bad_id})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "creation_id"}


async def test_invalid_mqtt_node_is_rejected(hass):
    flow = _make_flow(hass)
    result = await flow.async_step_user({**VALID_INPUT, "mqtt_node": "Therm#IQ"})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_nodename"}


async def test_trailing_slash_is_stripped_from_mqtt_node(hass):
    flow = _make_flow(hass)
    result = await flow.async_step_user(
        {**VALID_INPUT, "mqtt_node": "ThermIQ/ThermIQ-mqtt/"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["mqtt_node"] == "ThermIQ/ThermIQ-mqtt"


async def test_duplicate_id_aborts(hass):
    MockConfigEntry(
        domain=DOMAIN, unique_id=f"{DOMAIN}_vp1", data=VALID_INPUT
    ).add_to_hass(hass)
    flow = _make_flow(hass)
    # Driving the flow object directly means AbortFlow propagates as an
    # exception (the flow manager would turn it into an abort result)
    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user(dict(VALID_INPUT))
