# Home Assistant ThermIQ-MQTT Integration
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

![Screenshot](docs/Lovelace1.jpg)

This integration allows you to use the ThermIQ-MQTT hardware interface to control and monitor your Thermia or Danfoss heatpump from Home Assistant. It is available as a default component of HACS, the Home Assistant Community Store.

Some info background information on the ThermIQ-MQTT interface can be found here:
https://thermiq.net

**This integration will evolve over time**
Please note that since Release 1.2.0 the setup has changed significantly and you need to update your setup accordingly.

## Requirements

- MQTT server and the MQTT integration set up in Home Assistant
- ThermIQ-MQTT interface installed in your heatpump and properly configured to communicate over MQTT

- A couple of Lovelace plugins

## Quick start
1. Make sure that ThermIQ is properly setup and communicating with the MQTT server
2. Make sure that MQTT Integration in Home Assistant is setup and communicating with the MQTT server
3. Make sure you have HACS set-up (https://github.com/custom-components/hacs).
4. Make sure you have the required Lovelace plugins
5. Go to the HACS integrations page, add ThermIQ integration.

## Configuration
#### Component Configuration:
The complete configuration entry needed is:

```yaml
# Begin ThermIQ #####
# ThermIQ-MQTT configuration.yaml entry
# Set your mqtt_node name here (from ThermIQ-MQTT WiFi config). Thats all!
# The mqtt_node name can also be seen in MQTT-Eplorer or similar

thermiq_mqtt:
  mqtt_node: ThermIQ/ThermIQ-mqtt
  language: 'en'   # Change friendly names of values. Implemented languages: en,se,fi,no,de
  thermiq_dbg: False

# End ThermIQ ######
# ##################

```

#### Automations configuration
No setup of automations is needed

#### Lovelace Configuration:
The file [lovelace_config.yaml](https://github.com/ThermIQ/thermiq_mqtt-ha/blob/master/lovelace_config.yaml) contains a status view and a comprehensive set of variables. The lovelace_config.yaml should be inserted in the lovelace raw configuration editor. It should look something like this:

```yaml
# ################################################
# ##### ThermIQ Lovelace config. Add in Raw configuration editor
      - type: entities
        title: ThermIQ
        theme: default
        show_header_toggle: false
        entities:
          - type: custom:html-template-card
            title: null
            ignore_line_breaks: true
            content: >
              <head><style> 
              .hpwidget-val {width:35px;height:16px;background:#a0a0a0;text-align: center;color:white;border-radius: 0.25em;}
              .hpwidget-name-span{}
              .hpwidget-unit-span{text-align:right;overflow:hidden;color:white;font-size:70%}
              @keyframes rotating {to { transform: rotate(1turn); }}
              </style></head> 
 ...
 ...
 
```

The lovelace setup requires the following custom cards to be installed in HACS
```
- html-template-card from HTML Jinja2 Template card
- numberbox-card from Number Box
- fold-entity-row
```
 It is also necessary to move the three picture files below to the be in the lovelace path. They are currently coded to the **www/community/** directory (**local/community/**)
 ```
 vp_base.jpg
 vp_base_hgw_on.jpg
 vp_base_hw.jpg
 ```
#### Restart
The Home Assistant server needs to be restarted once all configuration is done

## Features and Limitations
- Currently provides all data from the heatpump in the form of sensors and binary sensors
- Allows control over the heatpump 

## Glossary

- Active cooling (active_cooling_on) – 
- Add-on flow guard (opt_flowguard_installed) – 
- Add-on HGW (opt_hgw_installed) – 
- Add-on Optimum (opt_optimum_installed) – 
- Add-on phase order measurement (opt_phasemeassure_installed) – 
- Alarm (alarm_indication_on) – 
- Alarm highpr.pressostate (highpressure_alm) – 
- Alarm hotw. t-sensor (boiler_sensor_alm) – 
- Alarm incorrect 3-phase order (phase_order_alm) – 
- Alarm indoor t-sensor (indoor_sensor_alm) – 
- Alarm low flow brine (brine_flow_alm) – 
- Alarm low temp. brine (brine_temperature_alm) – 
- Alarm lowpr.pressostate (lowpressure_alm) – 
- Alarm motorcircuit breaker (motorbreaker_alm) – 
- Alarm outdoor t-sensor (outdoor_sensor_alm) – 
- Alarm overheating (overheating_alm) – 
- Alarm returnline t-sensor (returnline_sensor_alm) – 
- Alarm supplyline t-sensor (supplyline_sensor_alm) – 
- Aux. heater 3 kW (boiler_3kw_on) – 
- Aux. heater 6 kW (boiler_6kw_on) – 
- Auxilliary 1 (aux1_heating_on) – 
- Auxilliary 2 (aux2_heating_on) – 
- Brine in temp. (brine_in_t) – 
- Brine out temp. (brine_out_t) – 
- Brine run-in duration (brine_run_in_t) – 
- Brine run-out duration (brine_runout_t) – 
- Brinepump (brine_pump_on) – 
- Brinepump speed (brine_pump_speed) – 
- Brinetemp., min limit (-15=OFFV) (brine_min_t) – 
- Calibration brine in sensor (brine_out_sensor_offset_t) – 
- Calibration brine out sensor (brine_in_sensor_offset_t) – 
- Calibration hotwater sensor (boiler_sensor_offset_t) – 
- Calibration outdoor sensor (outdoor_sensor_offset_t) – 
- Calibration returnline sensor (returnline_sensor_offset_t) – 
- Calibration supplyline sensor (supplyline_sensor_offset_t) – 
- Compressor (compressor_on) – 
- Cooling temp. (cooling_t) – 
- Cooling, target (cooling_target_t) – 
- Curve (integral1_curve_slope) – the relationship between the heating system supply temperature and the outside air temperature ([TECH Sterowniki](http://tech-controllers.com/blog/heating-curve---what-is-it-and-how-to-set-it))
- Curve +5 (integral1_curve_p5) – Used to adjust the heat curve at an outdoor temperature of +5°C
- Curve -5 (integral1_curve_n5) – Used to adjust the heat curve at an outdoor temperature of -5°C
- Curve 0 (integral1_curve_0) – Used to adjust the heat curve at an outdoor temperature of 0°C
- Curve 2 (integral2_curve_slope) – 
- Curve 2 max (integral2_curve_max) – 
- Curve 2 min (integral2_curve_min) – 
- Curve 2, Actual (integral2_curve_actual) – 
- Curve 2, Target (integral2_curve_target) – 
- Curve max (integral1_curve_max) – Highest setpoint for supply temperature
- Curve min (integral1_curve_min) – Lowest setpoint for supply temperature ([Thermia manual, page 14](http://www.tcmadmin.thermia.se/docroot/dokumentbank/Th_Total_UG_VUGFD302_EN_X013761.pdf))
- DACT_MSD1 (msd1_d) – 
- Defrost (defrost_time_m) – 
- DEMAND1 (demand1) – 
- DEMAND2 (demand2) – 
- DPAS_MSD1 (msd1_d) – 
- DT_LARMOFF (status7) – 
- DTS2_MSD1 (msd1_d) – 
- DTS_MSD1 (msd1_dtp) – 
- DVP_MSD1 (msd1_dvp) – 
- DVV_MSD1 (msd1_dvv) – 
- Electrical Current (current_consumed_a) – 
- Electrical current, max limit (current_consumption_max_a) – 
- Flowlinepump (supply_pump_on) – 
- Flowlinepump speed (supply_pump_speed) – 
- GrafCounterOffSet    (graph_display_offset) – 
- Heating system type 0=VL 4=D (heatingsystem_type) – 
- Heatpump operating time (heatpump_runtime_m) – 
- Heatstop (heating_stop_t) – This function stops all production of heat when the outdoor temperature is equal to, or higher than, the heat stop value currently set.
- Hotw. supplyline temp. (hgw_water_t) – 
- Hotwater operating time (hotwater_runtime_m) – 
- Hotwater production. (hotwaterproduction_on) – 
- Hotwater starttemp. (hotwater_start_t) – 
- Hotwater stop temp. (hotwater_stop_t) – 
- Hotwater temp. (boiler_t) – 
- Hysteresis A1 (integral1_hysteresis_t) – 
- Hysteresis limit A2 (integral2_hysteresis_t) – 
- Indoor target temp. (indoor_requested_t) – If the ROOM value is used to affect the system’s heat curve, the heat curve does not become steeper or flatter, as it does when the CURVE value changes. Instead the entire heat curve is moved by 3°C for every degree change of the ROOM value.
- Indoor target temp. (indoor_target_t) – 
- Indoor target temp., decimal (indoor_target_dec_t) – 
- Indoor temp. (indoor_t) – 
- Indoor temp., decimal (indoor_dec_t) – 
- Integral (A1) (integral1) – value of how much heat is needed in a home at a given time ([ThermiaTube](https://www.youtube.com/watch?v=POrEukfPgXk))
- Integral limit A1 (integral1_a_limit) – 
- Integral limit A2 (integral2_a_limit) – 
- Integral, reached A-limit (integral1_a_limit) – 
- Language (language) – 
- Legionella interval (legionella_interval_d) – 
- Legionella peak heating duration (legionella_run_length_h) – 
- Legionella peak heating enable (legionella_run_on) – 
- Legionella stop temp. (legionella_stop_t) – 
- Logging time (internal_logging_t) – 
- Manual test mode (manual_test_mode_on) – 
- Max Electric steps (elect_boiler_steps_max) – 
- Minimum start interval (start_interval_min_m) – 
- Minimum time to start (time_to_start_min_m) – 
- Mode (main_mode) – 
- Outdoor stop temp. (20=-20C) (outdoor_stop_t) – 
- Outdoor temp. (outdoor_t) – 
- Passive cooling (passive_cooling_on) – 
- Pressurepipe temp. (pressurepipe_t) – 
- Pressurepipe, temp. limit (pressure_pipe_limit_t) – 
- Program version (sw_version) – 
- PWM Out (pwm_out_period) – 
- Reset runtime counters (runtime_counters_reset_req) – 
- Reset to Factory settings (factory_reset_req) – 
- Returnline temp. (returnline_t) – 
- Returnline temp., max limit (returnline_max_t) – 
- Room factor (room_factor) – 
- Room sensor, Set target','Rums sensor, Styrvärde', 'Room sensor, Set target', 'Room sensor, Set target', 'Room sensor, Set target'], (room_sensor_set_t) – 
- Runtime 3 kW (boiler_3kw_runtime_h) – 
- Runtime 6 kW (boiler_6kw_on_runtime_h) – 
- Runtime active cooling (active_cooling_runtime_h) – 
- Runtime compressor (compressor_runtime_h) – 
- Runtime hotwater production (hotwater_runtime_h) – 
- Runtime passive cooling (passive_cooling_runtime_h) – 
- SERVFAS (status8) – 
- Shunt + (shunt1_p) – 
- Shunt - (shunt1_n) – 
- Shunt cooling + (shunt_cooling_p) – 
- Shunt cooling - (shunt_cooling_n) – 
- Shunt time (shunt_time_s) – 
- Shuntgroup + (shunt2_p) – 
- Shuntgroup - (shunt2_n) – 
- STATUS3 (status3_m) – 
- Supplyline target temp. (supplyline_target_t) – 
- Supplyline target temp., shunt (supplyline_shunt_target_t) – 
- Supplyline temp. (supplyline_t) – 
- Supplyline temp., shunt (supply_shunt_t) – 
- Temp. reduction (reduction_t) – 
- TILL2 (opt_2_installed) – 
- TILL4 (opt_4_installed) – 
- TILL5 (opt_5_installed) – 
- TILL6 (opt_6_installed) – 

## Contributing
Contributions are welcome! If you'd like to contribute, feel free to pick up anything on the current [GitHub issues](https://github.com/ThermIQ/thermiq_mqtt-ha/issues) list!
All help improving the integration is appreciated!



