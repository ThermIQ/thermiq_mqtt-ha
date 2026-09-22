"""Tests for serving the dashboard card from the integration.

These run against a real Home Assistant, so they are what proves the frontend
and http APIs used in async_register_frontend actually exist and are called
correctly - the card is otherwise only exercised in a browser.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.thermiq_mqtt import (
    CARD_FILENAME,
    CARD_VERSION,
    FRONTEND_REGISTERED,
    FRONTEND_URL_BASE,
    async_register_frontend,
)

FRONTEND_DIR = Path("custom_components/thermiq_mqtt/frontend")


@pytest.fixture
async def http(hass: HomeAssistant):
    """hass.http only exists once the http component is set up."""
    assert await async_setup_component(hass, "http", {})
    return hass.http


def test_card_files_are_shipped_inside_the_integration():
    """HACS installs custom_components/ only, so the card must live there."""
    assert (FRONTEND_DIR / CARD_FILENAME).is_file()
    assert (FRONTEND_DIR / "heatpump_widget.j2").is_file()


def test_card_default_url_matches_the_served_path():
    """The card fetches its template from the path the integration registers."""
    card = (FRONTEND_DIR / CARD_FILENAME).read_text()
    assert f'const DEFAULT_URL = "{FRONTEND_URL_BASE}/heatpump_widget.j2"' in card


async def test_card_and_template_are_actually_served(
    hass: HomeAssistant, http, hass_client
):
    """End to end: register for real, then fetch both files over HTTP."""
    with patch("custom_components.thermiq_mqtt.add_extra_js_url"):
        await async_register_frontend(hass)

    client = await hass_client()

    resp = await client.get(f"{FRONTEND_URL_BASE}/{CARD_FILENAME}")
    assert resp.status == 200
    assert "thermiq-widget-card" in await resp.text()

    resp = await client.get(f"{FRONTEND_URL_BASE}/heatpump_widget.j2")
    assert resp.status == 200
    assert "hpwidget" in await resp.text()


async def test_register_frontend_adds_the_module_once(hass: HomeAssistant, http):
    with patch("custom_components.thermiq_mqtt.add_extra_js_url") as add_js:
        await async_register_frontend(hass)

    add_js.assert_called_once_with(
        hass, f"{FRONTEND_URL_BASE}/{CARD_FILENAME}?v={CARD_VERSION}"
    )
    assert hass.data[FRONTEND_REGISTERED] is True

    # registering the same static path twice raises, so a second call must
    # do nothing at all
    with (
        patch.object(hass.http, "async_register_static_paths", AsyncMock()) as again,
        patch("custom_components.thermiq_mqtt.add_extra_js_url") as add_js_again,
    ):
        await async_register_frontend(hass)

    again.assert_not_called()
    add_js_again.assert_not_called()


async def test_registration_failure_does_not_break_setup(hass: HomeAssistant, http):
    """A frontend problem must not stop the integration from loading."""
    with (
        patch.object(
            hass.http,
            "async_register_static_paths",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("custom_components.thermiq_mqtt.add_extra_js_url") as add_js,
    ):
        await async_register_frontend(hass)

    add_js.assert_not_called()
    assert FRONTEND_REGISTERED not in hass.data


async def test_resource_delivery_registers_a_lovelace_resource(
    hass: HomeAssistant, http
):
    """With CARD_DELIVERY="resource" the card is listed, and NOT double-loaded."""
    assert await async_setup_component(hass, "lovelace", {})

    with (
        patch("custom_components.thermiq_mqtt.CARD_DELIVERY", "resource"),
        patch("custom_components.thermiq_mqtt.add_extra_js_url") as extra_js,
    ):
        await async_register_frontend(hass)

    from homeassistant.components.lovelace.const import LOVELACE_DATA

    urls = [item["url"] for item in hass.data[LOVELACE_DATA].resources.async_items()]
    assert f"{FRONTEND_URL_BASE}/{CARD_FILENAME}?v={CARD_VERSION}" in urls
    # Both mechanisms at once would evaluate the module twice.
    extra_js.assert_not_called()


async def test_resource_delivery_updates_rather_than_duplicates(
    hass: HomeAssistant, http
):
    """A CARD_VERSION bump must move the ?v=, not leave the old URL behind."""
    assert await async_setup_component(hass, "lovelace", {})

    from homeassistant.components.lovelace.const import LOVELACE_DATA

    resources = hass.data[LOVELACE_DATA].resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    await resources.async_create_item(
        {"res_type": "module", "url": f"{FRONTEND_URL_BASE}/{CARD_FILENAME}?v=0.0.1"}
    )

    with patch("custom_components.thermiq_mqtt.CARD_DELIVERY", "resource"):
        await async_register_frontend(hass)

    ours = [
        item["url"]
        for item in resources.async_items()
        if item["url"].split("?")[0] == f"{FRONTEND_URL_BASE}/{CARD_FILENAME}"
    ]
    assert ours == [f"{FRONTEND_URL_BASE}/{CARD_FILENAME}?v={CARD_VERSION}"]


async def test_resource_delivery_falls_back_when_lovelace_is_absent(
    hass: HomeAssistant, http
):
    """No Lovelace, no resource collection - the card must still be delivered."""
    with (
        patch("custom_components.thermiq_mqtt.CARD_DELIVERY", "resource"),
        patch("custom_components.thermiq_mqtt.add_extra_js_url") as extra_js,
    ):
        await async_register_frontend(hass)

    extra_js.assert_called_once()


def test_card_survives_being_evaluated_twice():
    """Two URLs for one file means two evaluations; the second must not throw."""
    card = (FRONTEND_DIR / CARD_FILENAME).read_text()
    assert 'if (!customElements.get("thermiq-widget-card")) {' in card
