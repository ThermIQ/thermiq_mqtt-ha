"""Tests that keep AI_INSTALL.md honest.

An agent follows that runbook literally: it posts the documented payload to the
config flow and greps for the documented entity ids. A doc that has drifted from
the code is therefore a broken installer, not a stale paragraph - so the pieces
an agent copies verbatim are pinned to the code here.
"""

import json
import re
from pathlib import Path

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResultType

from custom_components.thermiq_mqtt.config_flow import DomainConfigFlow
from custom_components.thermiq_mqtt.const import (
    AVAILABLE_LANGUAGES,
    CONF_ID,
    CONF_LANGUAGE,
    CONF_MIGRATE_DATA,
    CONF_MQTT_DBG,
    CONF_MQTT_HEX,
    CONF_MQTT_NODE,
    DOMAIN,
)
from custom_components.thermiq_mqtt.heatpump.thermiq_regs import reg_id

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = (REPO_ROOT / "AI_INSTALL.md").read_text(encoding="utf-8")

# The payload block is marked so the test picks up the one an agent submits,
# not some other json example that may be added to the doc later
PAYLOAD_BLOCK = re.compile(
    r"<!-- ai-install:config-flow-payload -->\s*```json\n(.*?)```",
    re.DOTALL,
)

# Entity ids spelled out in full in the doc, e.g. sensor.thermiq_mqtt_vp1_outdoor_t
ENTITY_ID = re.compile(
    r"\b(?:sensor|binary_sensor|number|select|switch)\.thermiq_mqtt_vp1_([a-z0-9_]+)"
)


def documented_payload():
    """The config flow payload the runbook tells an agent to post."""
    match = PAYLOAD_BLOCK.search(DOC)
    assert match, "AI_INSTALL.md has no marked config-flow payload block"
    return json.loads(match.group(1))


def _make_flow(hass):
    flow = DomainConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {}
    return flow


def test_documented_payload_has_exactly_the_config_flow_fields():
    """A missing key means the agent submits an incomplete form."""
    assert set(documented_payload()) == {
        CONF_ID,
        CONF_MQTT_NODE,
        CONF_LANGUAGE,
        CONF_MQTT_HEX,
        CONF_MQTT_DBG,
        CONF_MIGRATE_DATA,
    }


async def test_documented_payload_creates_an_entry(hass):
    """The runbook's payload is run through the real flow, not eyeballed."""
    flow = _make_flow(hass)
    result = await flow.async_step_user(documented_payload())
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ID] == documented_payload()[CONF_ID]


async def test_documented_payload_matches_the_form_defaults(hass):
    """The doc's example values are the form's own defaults, not invented ones."""
    flow = _make_flow(hass)
    result = await flow.async_step_user(None)
    schema = result["data_schema"]
    assert schema is not None
    defaults = {
        str(key): key.default()
        for key in schema.schema
        if key.default is not vol.UNDEFINED
    }
    assert documented_payload() == defaults


def test_fresh_install_payload_is_the_safe_one():
    """migrate_data rewrites recorder history and cannot be undone."""
    payload = documented_payload()
    assert payload[CONF_MIGRATE_DATA] is False
    assert payload[CONF_MQTT_DBG] is False


def test_documented_languages_match_the_code():
    assert ", ".join(f"`{lang}`" for lang in AVAILABLE_LANGUAGES) in DOC


def test_documented_entity_ids_exist():
    """An agent verifies the install by reading these entity ids."""
    suffixes = set(ENTITY_ID.findall(DOC))
    assert suffixes, "AI_INSTALL.md quotes no entity ids to verify against"
    assert suffixes <= set(reg_id), f"unknown registers in AI_INSTALL.md: {suffixes}"


def test_documented_minimum_ha_version_matches_hacs_json():
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert hacs["homeassistant"] in DOC


def test_documented_card_dependency_is_still_a_card_dependency():
    """The runbook installs fold-entity-row because the card needs it."""
    card = (REPO_ROOT / "ThermIQ_Card.yaml").read_text(encoding="utf-8")
    assert ("custom:fold-entity-row" in card) == ("fold-entity-row" in DOC)


def test_documented_debug_topics_match_the_code():
    """The doc promises thermiq_dbg diverts writes to these topics."""
    source = (
        REPO_ROOT / "custom_components/thermiq_mqtt/heatpump/__init__.py"
    ).read_text(encoding="utf-8")
    for topic in ("dbg_write", "dbg_set"):
        assert f'"{topic}"' in source
        assert topic in DOC


def test_documented_migration_notification_id_matches_the_code():
    source = (REPO_ROOT / "custom_components/thermiq_mqtt/__init__.py").read_text(
        encoding="utf-8"
    )
    assert 'f"{DOMAIN}_{id_name}_input_platform_migration"' in source
    assert f"{DOMAIN}_<id_name>_input_platform_migration" in DOC
