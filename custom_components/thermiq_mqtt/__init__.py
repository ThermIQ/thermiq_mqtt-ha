"""Component for ThermIQ-MQTT support."""
import logging
from builtins import property
from datetime import datetime
from sqlalchemy import update, select, delete

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    UnitOfTemperature
)
from homeassistant.helpers.recorder import session_scope, get_instance as recorder_get_instance
from homeassistant.components.recorder.statistics import async_change_statistics_unit
from homeassistant.helpers import entity_registry as er
from homeassistant.components.recorder.db_schema import StatisticsMeta, Statistics, StatisticsShortTerm

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

# from .automation import setup_automations
from .input_number import setup_input_numbers
from .input_select import setup_input_selects
from .input_boolean import setup_input_booleans

_LOGGER = logging.getLogger(__name__)
SERVICE_SET_VALUE = "set_value"

PLATFORMS = [
    "sensor",
    "binary_sensor",
]

async def async_setup(hass, config):
    """Set up HASL integration"""
    _LOGGER.info("Setup ThermIQ-MQTT integration")

    if DOMAIN not in hass.data:
        worker = hass.data.setdefault(DOMAIN, ThermIQWorker(hass))
    return True

# This call is for the ThermIQ global entry migration, not per-heatpump migration
async def async_migrate_entry(hass: HomeAssistant, config_entry) -> bool:
    _LOGGER.info("Migrate ThermIQ-MQTT integration")
    return True


async def async_migrate_state_temperature_celsius(hass: HomeAssistant, config_entry) -> bool:
    """Migrate sensor state classes with safety checks and logging.
    """

    # Check if migration has already been run
    current_version = config_entry.data.get(CONF_DB_VERSION, 0)
    if current_version >= DATABASE_VERSION:
        _LOGGER.info("Migration already completed (version %s)", current_version)
        return True

    _LOGGER.info("Starting state class migration for ThermIQ-MQTT  temperature sensors from %s to %s)", current_version, DATABASE_VERSION)

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
                "generated_input"
            ]:
                unit=reg_id[key][2]
                if len(unit)>0 and unit[-1:] == 'C':
                    # Decimal temperature cannot be converted automatically
                    if not (unit[:1] == '0'):
                        entities.append(key)

        # List of time/runtime sensors that needs migration

        migrated_entities = []
        failed_entities = []
        entity_id = ""

        for key in entities:
            try:
                entity_id= f"{entity_id_prefix}{key}"
                unit=reg_id[key][2]
                decimal=False
                if len(unit)>0:
                    decimal=unit[:1] == '0'
                entity_entry = entity_reg.async_get(entity_id)

                if entity_entry is None:
                    _LOGGER.debug("Entity %s not found in registry, skipping", entity_id)
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
                _LOGGER.error("Error migrating %s: %s", entity_id, str(e), exc_info=True)
                failed_entities.append(entity_id)

        # Log summary
        _LOGGER.info(
            "Migration summary: %s succeeded, %s failed, %s total",
            len(migrated_entities),
            len(failed_entities),
            len(entities)
        )

        if migrated_entities:
            _LOGGER.info("Migrated entities: %s", ", ".join(migrated_entities))

        if failed_entities:
            _LOGGER.warning("Failed entities: %s", ", ".join(failed_entities))

        # Consider it successful if at least one entity was migrated
        # or if no entities exist yet (fresh install)
        return len(failed_entities) == 0 or len(migrated_entities) > 0

    except Exception as e:
        _LOGGER.error("Critical error during state class migration: %s", str(e), exc_info=True)
        return False

async def _migrate_celsius(hass: HomeAssistant, recorder, entity_id: str, decimal) -> bool:
    """
    Migrate statistics metadata for a single entity.
    Returns True if successful, False otherwise.
    """

    def _update_celsius(decimal=False):
        """Update metadata within a database session."""

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
                    _LOGGER.debug("No statistics metadata found for %s (new sensor)",entity_id)
                    return True  # Not an error - sensor might be new

                unit = existing.unit_of_measurement
                if unit is None:
                    unit=''
                if decimal:
                    if unit!= '0.1'+UnitOfTemperature.CELSIUS:
                        async_change_statistics_unit(hass,entity_id,new_unit_of_measurement='0.1' + UnitOfTemperature.CELSIUS, old_unit_of_measurement=unit)
                    else:
                        _LOGGER.debug("No unit change needed for %s", entity_id)
                else:
                    if unit!= UnitOfTemperature.CELSIUS:
                        update_unit = (
                            update(StatisticsMeta)
                            .where(StatisticsMeta.statistic_id == entity_id)
                            .values(
                                unit_of_measurement=UnitOfTemperature.CELSIUS
                            )
                        )
                        stats_result = session.execute(update_unit)
                        _LOGGER.debug("Updated %s rows in Statistics", stats_result.rowcount)
                        async_change_statistics_unit(hass,entity_id,new_unit_of_measurement=UnitOfTemperature.CELSIUS, old_unit_of_measurement=UnitOfTemperature.CELSIUS)
                    else:
                        _LOGGER.debug("No unit change needed for %s", entity_id)
                return True

        except Exception as e:
            _LOGGER.error("Error in database operation for %s: %s", entity_id, str(e))
            return False

    try:
        result = recorder.async_add_executor_job(_update_celsius)
        return result
    except Exception as e:
        _LOGGER.error("Could not update celsius for %s: %s", entity_id, str(e), exc_info=True)
        return False


async def async_migrate_state_class_inc_hour(hass: HomeAssistant, config_entry) -> bool:
    """Migrate sensor state classes with safety checks and logging.
    """

    # Check if migration has already been run
    current_version = config_entry.data.get(CONF_DB_VERSION, 0)
    if current_version >= DATABASE_VERSION:
        _LOGGER.info("Migration already completed (version %s)", current_version)
        return True

    _LOGGER.info("Starting state class migration for ThermIQ sensors from %s to %s)", current_version, DATABASE_VERSION)

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
                    _LOGGER.debug("Entity %s not found in registry, skipping", entity_id)
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
                _LOGGER.error("Error migrating %s: %s", entity_id, str(e), exc_info=True)
                failed_entities.append(entity_id)

        # Log summary
        _LOGGER.info(
            "Migration summary: %s succeeded, %s failed, %s total",
            len(migrated_entities),
            len(failed_entities),
            len(time_sensor_suffixes)
        )

        if migrated_entities:
            _LOGGER.info("Migrated entities: %s", ", ".join(migrated_entities))

        if failed_entities:
            _LOGGER.warning("Failed entities: %s", ", ".join(failed_entities))

        # Consider it successful if at least one entity was migrated
        # or if no entities exist yet (fresh install)
        return len(failed_entities) == 0 or len(migrated_entities) > 0

    except Exception as e:
        _LOGGER.error("Critical error during state class migration: %s", str(e), exc_info=True)
        return False


async def _migrate_statistics_metadata(hass: HomeAssistant, recorder, entity_id: str) -> bool:
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
                    _LOGGER.debug("No statistics metadata found for %s (new sensor)", entity_id)
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
                    existing.has_sum
                )

                metadata_id = existing.id

                # Strategy: Convert mean-based statistics to cumulative sum
                # For runtime sensors (hours), the mean value IS the cumulative runtime at that point
                # We convert: mean -> sum, clear mean/min/max, and update mean_type to 0

                _LOGGER.info("Converting statistics data for %s from mean to cumulative sum", entity_id)

                # Update Statistics table: convert mean to sum and state, clear mean/min/max
                # For TOTAL_INCREASING, both sum and state should be the cumulative value
                update_stats = (
                    update(Statistics)
                    .where(Statistics.metadata_id == metadata_id)
                    .values(
                        sum=Statistics.mean,    # The mean value is actually the cumulative hours
                        state=Statistics.mean,  # State is also the cumulative value at that time
                        mean=None,
                        min=None,
                        max=None
                    )
                )
                stats_result = session.execute(update_stats)
                _LOGGER.debug("Updated %s rows in Statistics", stats_result.rowcount)

                # Update StatisticsShortTerm table: convert mean to sum and state, clear mean/min/max
                update_short_term = (
                    update(StatisticsShortTerm)
                    .where(StatisticsShortTerm.metadata_id == metadata_id)
                    .values(
                        sum=StatisticsShortTerm.mean,    # The mean value is actually the cumulative hours
                        state=StatisticsShortTerm.mean,  # State is also the cumulative value at that time
                        mean=None,
                        min=None,
                        max=None
                    )
                )
                short_term_result = session.execute(update_short_term)
                _LOGGER.debug("Updated %s rows in StatisticsShortTerm", short_term_result.rowcount)

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
                        stats_result.rowcount + short_term_result.rowcount
                    )
                    return True
                else:
                    _LOGGER.warning("Failed to update statistics metadata for %s", entity_id)
                    return False

        except Exception as e:
            _LOGGER.error("Error in database operation for %s: %s", entity_id, str(e))
            return False


    try:
        result = await recorder.async_add_executor_job(_migrate_statistics)
        return result
    except Exception as e:
        _LOGGER.error("Could not migrate statistics for %s: %s", entity_id, str(e), exc_info=True)
        return False


async def _async_migrate_entry(hass: HomeAssistant, config_entry) -> bool:
    """
    Main migration entry point.

    Called during setup of hass

    Returns:
        bool: True if migration succeeded or was not needed, False if critical failure
    """


    current_version = config_entry.data.get(CONF_DB_VERSION, 0)
    _LOGGER.info("Checking for possible migrations for ThermIQ [%s] data. Current installed version: %s, Update %s", config_entry.data[CONF_ID], current_version, DATABASE_VERSION)
    # Check if migration has already been run
    if current_version >= DATABASE_VERSION:
        if (config_entry.data.get(CONF_MIGRATE_DATA, True)):
            _LOGGER.info("Data migration requested for ThermIQ-MQTT [%s]", config_entry.data.get(CONF_ID, "unknown"))
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
            _LOGGER.error("Migration to temperature celsius - some entities may not function correctly")
            # You can choose to return False here to prevent setup
            # or return True to continue with warnings
            # return True  # Continue anyway - partial failure is acceptable
        else:
            _LOGGER.info("Temperature migrations completed successfully")

        # Run state class migration
        success2 = await async_migrate_state_class_inc_hour(hass, config_entry)

        if not success2:
            _LOGGER.error("Migration to increasing hours failed - some entities may not function correctly")
            # You can choose to return False here to prevent setup
            # or return True to continue with warnings
            # return True  # Continue anyway - partial failure is acceptable
        else:
            _LOGGER.info("State class migrations completed successfully")


        if success1 and success2:
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




async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up component from a config entry, config_entry contains data from config entry database."""
    _LOGGER.info("Setup ThermIQ-MQTT [%s]", entry.data.get(CONF_ID, "unknown"))
    await _async_migrate_entry(hass, entry)

    async def handle_hass_started(_event: Event) -> None:
        """Event handler for when HA has started."""
        await hass.async_create_task(heatpump.setup_mqtt())

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
    hass.async_create_task(setup_input_numbers(heatpump))
    hass.async_create_task(setup_input_selects(heatpump))
    hass.async_create_task(setup_input_booleans(heatpump))

    # Load the platforms for heatpump
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )

    # Wait for hass to start and then add the input_* entities
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, handle_hass_started)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        worker = hass.data[DOMAIN]
        worker.remove_entry(entry)
        if worker.is_idle():
            # also remove worker if not used by any entry any more
            del hass.data[DOMAIN]

    return unload_ok


async def reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if DOMAIN in hass.data:
        worker = hass.data[DOMAIN]
        await worker.update_heatpump_entry(entry)


class ThermIQWorker:
    """worker object. Stored in hass.data."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the instance."""
        self._hass = hass
        self._heatpumps = {}
        self._fetch_callback_listener = None
        self._worker = True

    @property
    def worker(self):
        return self._worker

    @property
    def heatpumps(self):
        return self._heatpumps

    async def add_entry(self, config_entry: ConfigEntry):
        """Add entry."""
        heatpump = HeatPump(self._hass, config_entry)
        await heatpump.update_config(config_entry)
        self._heatpumps[config_entry.data[CONF_ID]] = heatpump
        self._hass.bus.fire(
            f"{DOMAIN}_changed",
            {"action": "add", "heatpump": config_entry.data[CONF_ID]},
        )
        return heatpump

    def remove_entry(self, config_entry: ConfigEntry):
        """Remove entry."""
        self._hass.bus.fire(
            f"{DOMAIN}_changed",
            {"action": "remove", "heatpump": config_entry.data[CONF_ID]},
        )
        self._heatpumps.pop(config_entry.data[CONF_ID])

    async def update_heatpump_entry(self, config_entry: ConfigEntry):
        heatpump = self._heatpumps[config_entry.data[CONF_ID]]
        await heatpump.update_config(config_entry)
        await self._hass.async_create_task(heatpump.setup_mqtt())

    def is_idle(self) -> bool:
        return not bool(self._heatpumps)
