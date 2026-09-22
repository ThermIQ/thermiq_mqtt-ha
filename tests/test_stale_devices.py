"""Leftover device entries are removed on setup.

This integration creates no devices on purpose - with ~190 entities under one
device, Home Assistant prefixes every friendly name with the device name and
they all become too long. But versions up to v3.3.1, and upstream, did create
one, and Home Assistant keeps a device alive for as long as a config entry
references it. Upgraders were left with an empty device that looks like a
broken heatpump, which is what issue #28 reported.
"""

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thermiq_mqtt import _remove_stale_devices
from custom_components.thermiq_mqtt.const import DOMAIN

VALID_INPUT = {
    "id_name": "vp1",
    "mqtt_node": "ThermIQ/ThermIQ-mqtt",
    "language": "en",
    "hexformat": False,
    "thermiq_dbg": False,
    "migrate_data": False,
}


def _entry_with_device(hass, identifiers):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"{DOMAIN}_vp1", data=VALID_INPUT)
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        name="Heatpump status",
        manufacturer="ThermIQ.net",
    )
    return entry, device


async def test_a_device_from_an_older_version_is_removed(hass):
    """The identifiers v3.3.1 and upstream used."""
    entry, device = _entry_with_device(hass, {(DOMAIN, "vp1")})
    registry = dr.async_get(hass)
    assert registry.async_get(device.id) is not None

    _remove_stale_devices(hass, entry)

    assert registry.async_get(device.id) is None


async def test_removal_is_idempotent(hass):
    """Setup runs on every restart; the second pass must be a no-op."""
    entry, _ = _entry_with_device(hass, {(DOMAIN, "vp1")})
    _remove_stale_devices(hass, entry)
    _remove_stale_devices(hass, entry)
    assert dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id) == []


async def test_a_device_shared_with_another_integration_survives(hass):
    """Only our claim on it is dropped, not somebody else's device."""
    entry, device = _entry_with_device(hass, {(DOMAIN, "vp1")})
    other = MockConfigEntry(domain="mqtt", unique_id="other")
    other.add_to_hass(hass)
    registry = dr.async_get(hass)
    registry.async_update_device(device.id, add_config_entry_id=other.entry_id)

    _remove_stale_devices(hass, entry)

    survivor = registry.async_get(device.id)
    assert survivor is not None, "a device another integration also owns must remain"
    assert entry.entry_id not in survivor.config_entries


async def test_nothing_to_remove_is_fine(hass):
    """The normal case for a fresh install."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=f"{DOMAIN}_vp1", data=VALID_INPUT)
    entry.add_to_hass(hass)
    _remove_stale_devices(hass, entry)
    assert dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id) == []
