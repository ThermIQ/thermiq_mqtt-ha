"""Component for ThermIQ-MQTT support."""

from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from sqlalchemy import update, select

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, UnitOfTemperature
from homeassistant.helpers.recorder import (
    session_scope,
    get_instance as recorder_get_instance,
)
from homeassistant.components.recorder.statistics import async_change_statistics_unit
from homeassistant.helpers import entity_registry as er
from homeassistant.components.recorder.db_schema import (
    StatisticsMeta,
    Statistics,
    StatisticsShortTerm,
    States,
    StatesMeta,
)
from homeassistant.components import persistent_notification
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_ID,
    CONF_DB_VERSION,
    CONF_MIGRATE_DATA,
    DATABASE_VERSION,
)

# from .heatpump.sensor import HeatPumpSensor

from .heatpump import (
    HeatPump,
)

from .heatpump.thermiq_regs import (
    reg_id,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "number",
    "select",
    "switch",
]

# The dashboard widget ships inside the integration, so installing via HACS is
# the whole install: nothing to copy into www/ and no resource to register by
# hand. Bumping CARD_VERSION busts the browser cache for the card.
FRONTEND_URL_BASE = f"/{DOMAIN}_frontend"
CARD_FILENAME = "thermiq-widget-card.js"
CARD_VERSION = "1.5.0"
CARD_URL = f"{FRONTEND_URL_BASE}/{CARD_FILENAME}"
FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"

# How the card module reaches the browser.
#
#   "extra_js"  - add_extra_js_url. The module is imported from the frontend
#                 index at page bootstrap. What we have always shipped.
#   "resource"  - registered in Lovelace's own resource list, the documented
#                 route every HACS card uses.
#
# Never both: each mechanism imports the module under its own URL, and a
# second evaluation of the module calls customElements.define with a name that
# already exists, which throws.
#
# "resource" is the default because "extra_js" is measurably broken, for a
# reason that took a browser to find (#28).
#
# add_extra_js_url imports the card from the frontend index, at page
# bootstrap - earlier than any other custom card, which all arrive later as
# Lovelace resources. Something in a loaded page then patches
# customElements.define in place: it is native at document-start and a
# polyfill implementation by the time the dashboard renders, with its own
# internal registry. A define() that ran before that patch lands in the
# native registry and is invisible to the patched one Home Assistant then
# queries - so the element exists, window.customCards lists it, the card's
# own banner is in the console, and Lovelace still reports "Custom element
# doesn't exist", permanently, for that page load.
#
# Measured on a live installation, same browser, same steps:
#
#   extra_js   first load: undefined, 0 widgets | after Ctrl+F5: undefined, 0
#   resource   first load: function,  1 widget  | after Ctrl+F5: function,  1
#
# Being a resource puts us in the same load phase as every other custom card,
# after the patch. That is why every HACS card works and only ours did not.
CARD_DELIVERY = "resource"


async def _async_register_lovelace_resource(hass: HomeAssistant, url: str) -> bool:
    """List the card in Lovelace's resource collection.
    Returns True only if the card is now listed, so the caller knows whether
    it still has to fall back to add_extra_js_url. False for every reason it
    cannot be: Lovelace not set up yet, YAML-mode resources (which the user
    owns in configuration.yaml and we must not touch), or an internal API that
    moved - none of which should stop the integration loading.
    An existing entry for the same file is updated rather than duplicated, so
    a CARD_VERSION bump changes the ?v= in place instead of leaving the old
    URL behind to be imported alongside the new one.
    """
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:  # pragma: no cover - only on a frontend-less build
        return False
    data = hass.data.get(LOVELACE_DATA)
    if data is None:
        _LOGGER.debug("Lovelace is not set up yet; using add_extra_js_url instead")
        return False
    if getattr(data, "resource_mode", None) != "storage":
        # YAML mode: the resource list is the user's file, not ours to edit.
        _LOGGER.debug("Lovelace resources are in YAML mode; not adding the card")
        return False
    resources = data.resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    for item in resources.async_items():
        existing = str(item.get("url", ""))
        if existing.split("?", 1)[0] != CARD_URL:
            continue
        if existing != url:
            await resources.async_update_item(item["id"], {"url": url})
            _LOGGER.debug("Updated the ThermIQ card resource to %s", url)
        return True
    await resources.async_create_item({"res_type": "module", "url": url})
    _LOGGER.debug("Registered the ThermIQ card as a Lovelace resource: %s", url)
    return True


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the widget card and register it with the frontend.

    Registering the static path twice raises, and add_extra_js_url would queue
    the module more than once, so this is guarded to run only on first setup.
    """
    if hass.data.get(FRONTEND_REGISTERED):
        return

    frontend_dir = Path(__file__).parent / "frontend"
    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    FRONTEND_URL_BASE,
                    str(frontend_dir),
                    # Cache like every other frontend module. With
                    # cache_headers=False this path served no Cache-Control at
                    # all, so the browser revalidated the card over the network
                    # on every single page load - while Home Assistant's own
                    # bundle and every HACS module came straight from disk
                    # cache with max-age=31d. The frontend imports the card
                    # with a bare dynamic import() that nothing awaits, so
                    # losing that race means Lovelace builds its cards before
                    # the element is defined. Freshness comes from the ?v=
                    # cache-buster for the card, and from the card's own
                    # fetch(..., {cache: "no-store"}) for the template, which
                    # bypasses the HTTP cache regardless of these headers.
                    cache_headers=True,
                )
            ]
        )
        versioned = f"{CARD_URL}?v={CARD_VERSION}"
        if CARD_DELIVERY == "resource" and await _async_register_lovelace_resource(
            hass, versioned
        ):
            pass  # listed as a Lovelace resource; must not also add_extra_js_url
        else:
            add_extra_js_url(hass, versioned)
    except Exception as err:  # noqa: BLE001 - the integration must still load
        _LOGGER.error(
            "Could not register the ThermIQ dashboard card: %s. "
            "The integration works, but the widget must be installed manually",
            err,
        )
        return

    hass.data[FRONTEND_REGISTERED] = True
    _LOGGER.debug("Registered ThermIQ widget card at %s", FRONTEND_URL_BASE)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up HASL integration"""
    _LOGGER.info("Setup ThermIQ-MQTT integration")

    if DOMAIN not in hass.data:
        worker = hass.data.setdefault(DOMAIN, ThermIQWorker(hass))
    await async_register_frontend(hass)
    return True


# This call is for the ThermIQ global entry migration, not per-heatpump migration
async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.info("Migrate ThermIQ-MQTT integration")
    return True


async def async_migrate_state_temperature_celsius(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Migrate sensor state classes with safety checks and logging."""

    # Check if migration has already been run
    current_version = config_entry.data.get(CONF_DB_VERSION, 0)
    if current_version >= DATABASE_VERSION:
        _LOGGER.info("Migration already completed (version %s)", current_version)
        return True
    _LOGGER.info(
        "Starting state class migration for ThermIQ-MQTT  temperature sensors from %s to %s)",
        current_version,
        DATABASE_VERSION,
    )

    # Verify recorder is available
    recorder = recorder_get_instance(hass)
    if recorder is None:
        _LOGGER.error("Recorder not available, cannot perform migration")
        return False

    # Wait for recorder to be ready
    if not recorder.recording:
        _LOGGER.warning("Recorder not yet recording, migration may be incomplete")

    try:
        entity_reg = er.async_get(hass)

        # Get the unique ID from config - adjust this to match your config structure
        conf_id = config_entry.data.get(CONF_ID, "vp1")
        domain_prefix = f"thermiq_mqtt_{conf_id}"
        entity_id_prefix = f"sensor.{domain_prefix}_"

        entities = []

        for key in reg_id:
            if reg_id[key][1] in [
                "temperature",
                "temperature_input",
                "generated_input",
            ]:
                unit = reg_id[key][2]
                if len(unit) > 0 and unit[-1:] == "C":
                    # Decimal temperature cannot be converted automatically
                    if not (unit[:1] == "0"):
                        entities.append(key)

        # List of time/runtime sensors that needs migration

        migrated_entities = []
        failed_entities = []
        entity_id = ""

        for key in entities:
            try:
                entity_id = f"{entity_id_prefix}{key}"
                unit = reg_id[key][2]
                decimal = False
                if len(unit) > 0:
                    decimal = unit[:1] == "0"
                entity_entry = entity_reg.async_get(entity_id)

                if entity_entry is None:
                    _LOGGER.debug(
                        "Entity %s not found in registry, skipping", entity_id
                    )
                    continue

                _LOGGER.info("Migrating entity %s to temperature celsius", entity_id)

                # Migrate statistics metadata
                success = await _migrate_celsius(hass, recorder, entity_id, decimal)

                if success:
                    migrated_entities.append(entity_id)
                    _LOGGER.info("Successfully migrated %s", entity_id)
                else:
                    failed_entities.append(entity_id)
                    _LOGGER.warning("Failed to migrate %s", entity_id)

            except Exception as e:
                _LOGGER.error(
                    "Error migrating %s: %s", entity_id, str(e), exc_info=True
                )
                failed_entities.append(entity_id)

        # Log summary
        _LOGGER.info(
            "Migration summary: %s succeeded, %s failed, %s total",
            len(migrated_entities),
            len(failed_entities),
            len(entities),
        )

        if migrated_entities:
            _LOGGER.info("Migrated entities: %s", ", ".join(migrated_entities))

        if failed_entities:
            _LOGGER.warning("Failed entities: %s", ", ".join(failed_entities))

        # Consider it successful if at least one entity was migrated
        # or if no entities exist yet (fresh install)
        return len(failed_entities) == 0 or len(migrated_entities) > 0

    except Exception as e:
        _LOGGER.error(
            "Critical error during state class migration: %s", str(e), exc_info=True
        )
        return False


async def _migrate_celsius(
    hass: HomeAssistant, recorder, entity_id: str, decimal: bool
) -> bool:
    """
    Migrate statistics metadata for a single entity.

    Database work runs in the recorder executor; async_change_statistics_unit
    is a loop-only API and must be called from the event loop, never from
    inside the executor job.
    Returns True if successful, False otherwise.
    """

    def _update_celsius():
        """Update metadata within a database session (executor thread).

        Returns (found, current_unit). The non-decimal unit fix is done
        directly in the database here; a needed decimal conversion is
        signalled back to the event loop via the returned unit.
        """
        with session_scope(hass=hass, read_only=False) as session:
            # First check if metadata exists
            stmt = select(StatisticsMeta).where(
                StatisticsMeta.statistic_id == entity_id
            )
            result = session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                return (False, None)  # Not an error - sensor might be new

            unit = existing.unit_of_measurement
            if unit is None:
                unit = ""
            if not decimal and unit != UnitOfTemperature.CELSIUS:
                update_unit = (
                    update(StatisticsMeta)
                    .where(StatisticsMeta.statistic_id == entity_id)
                    .values(unit_of_measurement=UnitOfTemperature.CELSIUS)
                )
                stats_result = session.execute(update_unit)
                _LOGGER.debug(
                    "Updated %s rows in StatisticsMeta", stats_result.rowcount
                )
            return (True, unit)

    try:
        found, unit = await recorder.async_add_executor_job(_update_celsius)
        if not found:
            _LOGGER.debug("No statistics metadata found for %s (new sensor)", entity_id)
            return True

        if decimal:
            decimal_unit = "0.1" + UnitOfTemperature.CELSIUS
            if unit != decimal_unit:
                # Called from the event loop as required
                async_change_statistics_unit(
                    hass,
                    entity_id,
                    new_unit_of_measurement=decimal_unit,
                    old_unit_of_measurement=unit,
                )
            else:
                _LOGGER.debug("No unit change needed for %s", entity_id)
        return True
    except Exception as e:
        _LOGGER.error(
            "Could not update celsius for %s: %s", entity_id, str(e), exc_info=True
        )
        return False


async def async_migrate_state_class_inc_hour(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Migrate sensor state classes with safety checks and logging."""

    # Check if migration has already been run
    current_version = config_entry.data.get(CONF_DB_VERSION, 0)
    if current_version >= DATABASE_VERSION:
        _LOGGER.info("Migration already completed (version %s)", current_version)
        return True

    _LOGGER.info(
        "Starting state class migration for ThermIQ sensors from %s to %s)",
        current_version,
        DATABASE_VERSION,
    )

    # Verify recorder is available
    recorder = recorder_get_instance(hass)
    if recorder is None:
        _LOGGER.error("Recorder not available, cannot perform migration")
        return False

    # Wait for recorder to be ready
    if not recorder.recording:
        _LOGGER.warning("Recorder not yet recording, migration may be incomplete")

    try:
        entity_reg = er.async_get(hass)

        # Get the unique ID from config - adjust this to match your config structure
        conf_id = config_entry.data.get(CONF_ID, "vp1")
        domain_prefix = f"thermiq_mqtt_{conf_id}"
        entity_id_prefix = f"sensor.{domain_prefix}_"

        # List of time/runtime sensors that need migration
        time_sensor_suffixes = [
            "compressor_runtime_h",
            "boiler_3kw_runtime_h",
            "boiler_6kw_on_runtime_h",
            "hotwater_runtime_h",
            "passive_cooling_runtime_h",
            "active_cooling_runtime_h",
        ]

        migrated_entities = []
        failed_entities = []

        for suffix in time_sensor_suffixes:
            entity_id = f"{entity_id_prefix}{suffix}"

            try:
                entity_entry = entity_reg.async_get(entity_id)

                if entity_entry is None:
                    _LOGGER.debug(
                        "Entity %s not found in registry, skipping", entity_id
                    )
                    continue

                _LOGGER.info("Migrating entity %s to TOTAL_INCREASING", entity_id)

                # Migrate statistics metadata
                success = await _migrate_statistics_metadata(hass, recorder, entity_id)

                if success:
                    migrated_entities.append(entity_id)
                    _LOGGER.info("Successfully migrated %s", entity_id)
                else:
                    failed_entities.append(entity_id)
                    _LOGGER.warning("Failed to migrate %s", entity_id)

            except Exception as e:
                _LOGGER.error(
                    "Error migrating %s: %s", entity_id, str(e), exc_info=True
                )
                failed_entities.append(entity_id)

        # Log summary
        _LOGGER.info(
            "Migration summary: %s succeeded, %s failed, %s total",
            len(migrated_entities),
            len(failed_entities),
            len(time_sensor_suffixes),
        )

        if migrated_entities:
            _LOGGER.info("Migrated entities: %s", ", ".join(migrated_entities))

        if failed_entities:
            _LOGGER.warning("Failed entities: %s", ", ".join(failed_entities))

        # Consider it successful if at least one entity was migrated
        # or if no entities exist yet (fresh install)
        return len(failed_entities) == 0 or len(migrated_entities) > 0

    except Exception as e:
        _LOGGER.error(
            "Critical error during state class migration: %s", str(e), exc_info=True
        )
        return False


async def _migrate_statistics_metadata(
    hass: HomeAssistant, recorder, entity_id: str
) -> bool:
    """
    Migrate statistics for a single entity from MEASUREMENT to TOTAL_INCREASING.
    This preserves historical data by:
    1. Converting mean values to sum values (for runtime sensors, mean IS cumulative)
    2. Clearing mean/min/max fields (not used by TOTAL_INCREASING)
    3. Updating metadata: has_sum=True, has_mean=False, mean_type=0
    The key is updating mean_type from 1 (Arithmetic) to 0 (No mean) to prevent
    Home Assistant's validation error about incompatible mean types.
    Returns True if successful, False otherwise.
    """

    def _migrate_statistics():
        """Migrate metadata and statistics data within a database session."""

        try:
            # Create the session inside the executor job
            with session_scope(hass=hass, read_only=False) as session:
                # First check if metadata exists
                stmt = select(StatisticsMeta).where(
                    StatisticsMeta.statistic_id == entity_id
                )
                result = session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing is None:
                    _LOGGER.debug(
                        "No statistics metadata found for %s (new sensor)", entity_id
                    )
                    return True  # Not an error - sensor might be new

                # Check if already migrated
                if existing.has_sum and not existing.has_mean:
                    _LOGGER.debug("Statistics for %s already migrated", entity_id)
                    return True

                # Log current state
                _LOGGER.info(
                    "Migrating statistics for %s from MEASUREMENT to TOTAL_INCREASING (has_mean=%s, has_sum=%s)",
                    entity_id,
                    existing.has_mean,
                    existing.has_sum,
                )

                metadata_id = existing.id

                # Strategy: Convert mean-based statistics to cumulative sum
                # For runtime sensors (hours), the mean value IS the cumulative runtime at that point
                # We convert: mean -> sum, clear mean/min/max, and update mean_type to 0

                _LOGGER.info(
                    "Converting statistics data for %s from mean to cumulative sum",
                    entity_id,
                )

                # Update Statistics table: convert mean to sum and state, clear mean/min/max
                # For TOTAL_INCREASING, both sum and state should be the cumulative value
                update_stats = (
                    update(Statistics)
                    .where(Statistics.metadata_id == metadata_id)
                    .values(
                        sum=Statistics.mean,  # The mean value is actually the cumulative hours
                        state=Statistics.mean,  # State is also the cumulative value at that time
                        mean=None,
                        min=None,
                        max=None,
                    )
                )
                stats_result = session.execute(update_stats)
                _LOGGER.debug("Updated %s rows in Statistics", stats_result.rowcount)

                # Update StatisticsShortTerm table: convert mean to sum and state, clear mean/min/max
                update_short_term = (
                    update(StatisticsShortTerm)
                    .where(StatisticsShortTerm.metadata_id == metadata_id)
                    .values(
                        sum=StatisticsShortTerm.mean,  # The mean value is actually the cumulative hours
                        state=StatisticsShortTerm.mean,  # State is also the cumulative value at that time
                        mean=None,
                        min=None,
                        max=None,
                    )
                )
                short_term_result = session.execute(update_short_term)
                _LOGGER.debug(
                    "Updated %s rows in StatisticsShortTerm", short_term_result.rowcount
                )

                # Update metadata to TOTAL_INCREASING characteristics
                # has_sum=True, has_mean=False, mean_type=0 (No mean)
                # Setting mean_type=0 is CRITICAL to prevent validation errors
                update_meta = (
                    update(StatisticsMeta)
                    .where(StatisticsMeta.statistic_id == entity_id)
                    .values(has_sum=True, has_mean=False, mean_type=0)
                )

                meta_result = session.execute(update_meta)

                if meta_result.rowcount > 0:
                    _LOGGER.info(
                        "Successfully migrated %s: metadata updated, %s statistics records converted",
                        entity_id,
                        stats_result.rowcount + short_term_result.rowcount,
                    )
                    return True
                else:
                    _LOGGER.warning(
                        "Failed to update statistics metadata for %s", entity_id
                    )
                    return False

        except Exception as e:
            _LOGGER.error("Error in database operation for %s: %s", entity_id, str(e))
            return False

    try:
        result = await recorder.async_add_executor_job(_migrate_statistics)
        return bool(result)
    except Exception as e:
        _LOGGER.error(
            "Could not migrate statistics for %s: %s", entity_id, str(e), exc_info=True
        )
        return False


async def _async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """
    Main migration entry point.

    Called during setup of hass

    Returns:
        bool: True if migration succeeded or was not needed, False if critical failure
    """

    current_version = config_entry.data.get(CONF_DB_VERSION, 0)
    _LOGGER.info(
        "Checking for possible migrations for ThermIQ [%s] data. Current installed version: %s, Update %s",
        config_entry.data[CONF_ID],
        current_version,
        DATABASE_VERSION,
    )
    # Check if migration has already been run
    if current_version >= DATABASE_VERSION:
        if config_entry.data.get(CONF_MIGRATE_DATA, True):
            _LOGGER.info(
                "Data migration requested for ThermIQ-MQTT [%s]",
                config_entry.data.get(CONF_ID, "unknown"),
            )
        else:
            _LOGGER.info("Migration already completed (version %s)", current_version)
            return True

    # Mark migration request as disabled to avoid endless loops
    migration_data = {
        **config_entry.data,
        CONF_MIGRATE_DATA: False,
        "migration_date": datetime.now().isoformat(),
    }
    hass.config_entries.async_update_entry(config_entry, data=migration_data)

    try:
        success1 = await async_migrate_state_temperature_celsius(hass, config_entry)
        if not success1:
            _LOGGER.error(
                "Migration to temperature celsius - some entities may not function correctly"
            )
            # You can choose to return False here to prevent setup
            # or return True to continue with warnings
            # return True  # Continue anyway - partial failure is acceptable
        else:
            _LOGGER.info("Temperature migrations completed successfully")

        # Run state class migration
        success2 = await async_migrate_state_class_inc_hour(hass, config_entry)

        if not success2:
            _LOGGER.error(
                "Migration to increasing hours failed - some entities may not function correctly"
            )
            # You can choose to return False here to prevent setup
            # or return True to continue with warnings
            # return True  # Continue anyway - partial failure is acceptable
        else:
            _LOGGER.info("State class migrations completed successfully")

        # Run input_* -> number/select/switch platform migration
        success3 = await async_migrate_input_platforms(hass, config_entry)

        if not success3:
            _LOGGER.error(
                "Migration of input_* platforms failed - history may remain "
                "split across the old and new entity ids"
            )
        else:
            _LOGGER.info("input_* platform migration completed successfully")

        if success1 and success2 and success3:
            # Mark migration as complete even if some entities failed
            # (they might not exist yet, or be created later)
            migration_data = {
                **config_entry.data,
                CONF_DB_VERSION: DATABASE_VERSION,
                "migration_date": datetime.now().isoformat(),
            }

            hass.config_entries.async_update_entry(config_entry, data=migration_data)

        return True

    except Exception as e:
        _LOGGER.error("Unexpected error during migration: %s", str(e), exc_info=True)
        return True  # Continue setup even if migration fails


# ---------------------------------------------------------------------------
# 3.3.0 platform migration:
#     input_number.*  -> number.*
#     input_select.*  -> select.*
#     input_boolean.* -> switch.*
#
# Up to 3.1.x the integration hijacked Home Assistant's own input_* helper
# platforms. Each helper was built with
#
#     config[CONF_ID] = f"{heatpump._domain}_{heatpump._id}_{key}"
#     entity          = CustomInputNumber.from_yaml(config)
#
# giving entity ids of the form
#
#     input_number.{DOMAIN}_{id_name}_{key}     on platform "input_number"
#
# 3.3.0 replaced these with real NumberEntity/SelectEntity/SwitchEntity on this
# integration's own platform:
#
#     number.{DOMAIN}_{id_name}_{key}           on platform "thermiq_mqtt"
#     unique_id = "uid-" + entity_id
#
# The object_id is identical on both sides; only the domain prefix changes, so
# the mapping is a pure domain swap with no name matching involved.
#
# The entity registry cannot perform this rename for us: an entity_id's domain
# must match its platform's domain, and the stale rows belong to the input_*
# integrations rather than to this one. So the recorder rows are repointed
# directly and the orphaned registry entries are then dropped.
# ---------------------------------------------------------------------------

PLATFORM_MIGRATION_MAP = {
    "input_number": "number",
    "input_select": "select",
    "input_boolean": "switch",
}


async def async_migrate_input_platforms(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """
    Carry history and long-term statistics from the pre-3.3.0 input_* helper
    entities over to the number/select/switch entities that replaced them, then
    remove the orphaned input_* registry entries.

    Idempotent: once the old rows are gone the scan finds nothing and returns
    True immediately, so re-running is harmless.

    Returns:
        bool: True if migration succeeded or was not needed, False on a
              critical failure. Per-entity problems are logged and do not fail
              the migration as a whole.
    """
    id_name = config_entry.data[CONF_ID]
    entity_reg = er.async_get(hass)
    recorder = recorder_get_instance(hass)

    prefixes = {
        f"{old_domain}.{DOMAIN}_{id_name}_": new_domain
        for old_domain, new_domain in PLATFORM_MIGRATION_MAP.items()
    }

    old_entity_ids: set[str] = set()

    # 1. Entities visible in the registry.
    for entry in list(entity_reg.entities.values()):
        if any(entry.entity_id.startswith(p) for p in prefixes):
            old_entity_ids.add(entry.entity_id)

    # 2. Recorder-only orphans. A helper created without a unique_id never
    #    entered the registry, yet still owns states_meta rows holding its
    #    history - upstream's input_boolean.py is exactly this case, its
    #    unique_id registration being commented out. Without this pass their
    #    history would be silently left behind.
    try:
        orphans = await recorder.async_add_executor_job(
            _discover_recorder_entities, hass, tuple(prefixes)
        )
        old_entity_ids.update(orphans)
    except Exception as e:  # noqa: BLE001 - discovery must not block setup
        _LOGGER.warning(
            "Could not scan recorder for orphaned input_* entities: %s", str(e)
        )

    if not old_entity_ids:
        _LOGGER.debug(
            "No pre-3.3.0 input_* entities found for ThermIQ [%s], nothing to migrate",
            id_name,
        )
        return True

    renames: list[tuple[str, str]] = []
    for old_entity_id in sorted(old_entity_ids):
        old_domain, object_id = old_entity_id.split(".", 1)
        new_domain = PLATFORM_MIGRATION_MAP[old_domain]
        renames.append((old_entity_id, f"{new_domain}.{object_id}"))

    _LOGGER.info(
        "Migrating %s pre-3.3.0 input_* entities for ThermIQ [%s] to number/select/switch",
        len(renames),
        id_name,
    )

    try:
        migrated = await recorder.async_add_executor_job(
            _migrate_recorder_rows, hass, renames
        )
    except Exception as e:  # noqa: BLE001 - migration must never block setup
        _LOGGER.error(
            "Could not migrate recorder rows for ThermIQ [%s]: %s",
            id_name,
            str(e),
            exc_info=True,
        )
        return False

    # Drop the orphaned registry entries only after the recorder rows have been
    # repointed - otherwise a failure above would strand the history under an
    # entity_id with no registry entry left to find it by.
    removed = 0
    for old_entity_id, _new_entity_id in renames:
        if entity_reg.async_get(old_entity_id) is None:
            continue
        try:
            entity_reg.async_remove(old_entity_id)
            removed += 1
        except Exception as e:  # noqa: BLE001
            _LOGGER.warning(
                "Could not remove stale registry entry %s: %s", old_entity_id, str(e)
            )

    _LOGGER.info(
        "ThermIQ [%s]: repointed %s recorder entities, removed %s stale registry entries",
        id_name,
        migrated,
        removed,
    )

    _notify_entity_id_changes(hass, id_name, renames)
    return True


def _discover_recorder_entities(
    hass: HomeAssistant, prefixes: tuple[str, ...]
) -> list[str]:
    """
    Find entity_ids in states_meta matching any of the old input_* prefixes.

    Filtering happens in Python rather than via SQL LIKE on purpose: an
    entity_id prefix such as "input_number.thermiq_mqtt_myhp_" is full of
    underscores, and LIKE treats "_" as a single-character wildcard, so the
    pattern would match far more than intended. states_meta holds one row per
    entity, so reading the id column is cheap.

    Runs inside a recorder executor job.
    """
    with session_scope(hass=hass, read_only=True) as session:
        all_ids = session.execute(select(StatesMeta.entity_id)).scalars().all()

    return [eid for eid in all_ids if any(eid.startswith(p) for p in prefixes)]


def _migrate_recorder_rows(hass: HomeAssistant, renames: list[tuple[str, str]]) -> int:
    """
    Repoint recorder rows from the old entity_ids onto the new ones.

    Two cases per entity:

    * new row absent  - the states_meta/statistics_meta row is renamed in
      place, carrying all of its history with it.
    * new row present - the user already ran 3.3.0, so history is split across
      two rows. The old rows' data is repointed onto the new metadata_id and
      the emptied old row deleted, merging the two series.

    Runs inside a recorder executor job, opening its own session as the other
    migrations in this module do.

    Returns the number of entities that had at least one row migrated.
    """
    migrated = 0

    with session_scope(hass=hass, read_only=False) as session:
        for old_entity_id, new_entity_id in renames:
            touched = False

            # --- recorded states -------------------------------------------
            old_meta = session.execute(
                select(StatesMeta).where(StatesMeta.entity_id == old_entity_id)
            ).scalar_one_or_none()

            if old_meta is not None:
                new_meta = session.execute(
                    select(StatesMeta).where(StatesMeta.entity_id == new_entity_id)
                ).scalar_one_or_none()

                if new_meta is None:
                    session.execute(
                        update(StatesMeta)
                        .where(StatesMeta.metadata_id == old_meta.metadata_id)
                        .values(entity_id=new_entity_id)
                    )
                    _LOGGER.debug(
                        "Renamed states %s -> %s", old_entity_id, new_entity_id
                    )
                else:
                    session.execute(
                        update(States)
                        .where(States.metadata_id == old_meta.metadata_id)
                        .values(metadata_id=new_meta.metadata_id)
                    )
                    session.delete(old_meta)
                    _LOGGER.debug(
                        "Merged states %s into %s", old_entity_id, new_entity_id
                    )
                touched = True

            # --- long term statistics --------------------------------------
            # Normally a no-op: input_number helpers carry no state_class and
            # so have no long-term statistics. Handled anyway for installs that
            # added one by hand via customize.
            old_stat = session.execute(
                select(StatisticsMeta).where(
                    StatisticsMeta.statistic_id == old_entity_id
                )
            ).scalar_one_or_none()

            if old_stat is not None:
                new_stat = session.execute(
                    select(StatisticsMeta).where(
                        StatisticsMeta.statistic_id == new_entity_id
                    )
                ).scalar_one_or_none()

                if new_stat is None:
                    session.execute(
                        update(StatisticsMeta)
                        .where(StatisticsMeta.id == old_stat.id)
                        .values(statistic_id=new_entity_id)
                    )
                    _LOGGER.debug(
                        "Renamed statistics %s -> %s", old_entity_id, new_entity_id
                    )
                else:
                    for table in (Statistics, StatisticsShortTerm):
                        session.execute(
                            update(table)
                            .where(table.metadata_id == old_stat.id)
                            .values(metadata_id=new_stat.id)
                        )
                    session.delete(old_stat)
                    _LOGGER.debug(
                        "Merged statistics %s into %s", old_entity_id, new_entity_id
                    )
                touched = True

            if touched:
                migrated += 1

    return migrated


def _notify_entity_id_changes(
    hass: HomeAssistant, id_name: str, renames: list[tuple[str, str]]
) -> None:
    """
    Tell the user which entity ids moved.

    History and statistics follow automatically, but automations, scripts,
    dashboards and templates cannot be rewritten safely from inside the
    integration - they live in user-authored YAML and Lovelace storage.
    Listing the mapping is what turns a silent break into a quick
    find-and-replace.
    """
    lines = "\n".join(f"- `{old}` &rarr; `{new}`" for old, new in renames)
    persistent_notification.async_create(
        hass,
        (
            f"ThermIQ-MQTT **{id_name}** has replaced its `input_*` helper "
            f"entities with proper `number`/`select`/`switch` entities.\n\n"
            f"History and long-term statistics were moved across "
            f"automatically. Any **automations, scripts, dashboards or "
            f"templates** still referencing the old ids need updating:\n\n"
            f"{lines}"
        ),
        title="ThermIQ-MQTT: entities renamed",
        notification_id=f"{DOMAIN}_{id_name}_input_platform_migration",
    )


def _remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop device entries left behind by older versions.
    This integration deliberately creates no devices: with ~190 entities under
    one device, Home Assistant would prefix every friendly name with the
    device name and they would all be too long (see 729669a). But versions up
    to v3.3.1 - and upstream - did create one, and Home Assistant keeps a
    device for as long as a config entry references it. The result is an empty
    device that looks like a broken heatpump, reported in #28.
    Anything attached to this entry can only be such a leftover, so it goes.
    """
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        _LOGGER.info(
            "Removing stale device [%s] left by an earlier version; this "
            "integration does not group entities under a device",
            device.name or device.id,
        )
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up component from a config entry, config_entry contains data from config entry database."""
    _LOGGER.info("Setup ThermIQ-MQTT [%s]", entry.data.get(CONF_ID, "unknown"))
    _remove_stale_devices(hass, entry)
    await _async_migrate_entry(hass, entry)

    async def handle_hass_started(_event: Event) -> None:
        """Event handler for when HA has started."""
        await heatpump.setup_mqtt()

    # One common ThermIQWorker serves all HeatPump objects
    if DOMAIN in hass.data:
        worker = hass.data[DOMAIN]
    else:
        worker = hass.data.setdefault(DOMAIN, ThermIQWorker(hass))

    # add new heatpump to worker
    heatpump = await worker.add_entry(entry)
    # Make config reload
    rld = entry.add_update_listener(reload_entry)
    entry.async_on_unload(rld)

    # Load all platforms (sensor, binary_sensor, number, select, switch) and
    # await them so the entities are fully set up before this entry is marked
    # done (avoids races where consumers access the data before it is ready)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Subscribe to MQTT
    if hass.is_running:
        # HA is already up (e.g. the integration was just added via the UI) -
        # EVENT_HOMEASSISTANT_STARTED has fired and never will again, so
        # subscribe immediately
        await heatpump.setup_mqtt()
    else:
        # Wait for hass to start before subscribing
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, handle_hass_started)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = bool(await hass.config_entries.async_unload_platforms(entry, PLATFORMS))
    if unload_ok:
        worker = hass.data[DOMAIN]
        # Unsubscribe MQTT and remove the generated helper entities so a
        # reload does not leak subscriptions or orphan input_* entities
        heatpump = worker.heatpumps.get(entry.data[CONF_ID])
        if heatpump is not None:
            await heatpump.async_reset()
        worker.remove_entry(entry)
        if worker.is_idle():
            # also remove worker if not used by any entry any more
            del hass.data[DOMAIN]

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry
) -> bool:
    """Allow removing devices from the UI/registry.
    The integration no longer creates devices (entity names would get the
    device name prefixed), so any remaining device entry is stale and may
    always be removed.
    """
    return True


async def reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if DOMAIN in hass.data:
        worker = hass.data[DOMAIN]
        await worker.update_heatpump_entry(entry)


class ThermIQWorker:
    """worker object. Stored in hass.data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the instance."""
        self._hass = hass
        self._heatpumps: dict[str, HeatPump] = {}
        self._fetch_callback_listener = None
        self._worker = True

    @property
    def worker(self) -> bool:
        return self._worker

    @property
    def heatpumps(self) -> dict[str, HeatPump]:
        return self._heatpumps

    async def add_entry(self, config_entry: ConfigEntry) -> HeatPump:
        """Add entry."""
        heatpump = HeatPump(self._hass, config_entry)
        await heatpump.update_config(config_entry)
        self._heatpumps[config_entry.data[CONF_ID]] = heatpump
        self._hass.bus.fire(
            f"{DOMAIN}_changed",
            {"action": "add", "heatpump": config_entry.data[CONF_ID]},
        )
        return heatpump

    def remove_entry(self, config_entry: ConfigEntry) -> None:
        """Remove entry."""
        self._hass.bus.fire(
            f"{DOMAIN}_changed",
            {"action": "remove", "heatpump": config_entry.data[CONF_ID]},
        )
        self._heatpumps.pop(config_entry.data[CONF_ID])

    async def update_heatpump_entry(self, config_entry: ConfigEntry) -> None:
        heatpump = self._heatpumps[config_entry.data[CONF_ID]]
        await heatpump.update_config(config_entry)
        await self._hass.async_create_task(heatpump.setup_mqtt())

    def is_idle(self) -> bool:
        return not bool(self._heatpumps)
