# Home Assistant ThermIQ-MQTT Integration (Pre-Release)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

This integration allows you to use the ThermIQ-MQTT hardware interface to control and monitor your Thermia or Danfoss heatpump from Home Assistant. The idea is to make it available as a custom component through HACS and eventually submit it as an official Home Assistant component.

Some info background information on the ThermIQ-MQTT interface can be found here:
https://thermiq.net

**This integration is in pre-release and will evolve over time**


## Requirements

- MQTT server and the MQTT integration set up in Home Assistant
- ThermIQ-MQTT interface installed in your heatpump and properly configured to communicate over MQTT

- A couple of Lovelace plugins

## Quick start
1. Make sure that ThermIQ is properly setup and communicating with the MQTT server
2. Make sure that MQTT Integration in Home Assistant is setup and communicating with the MQTT server
3. Make sure you have HACS set-up (https://github.com/custom-components/hacs).
4. In HACS, Go to settings and install custom repository: https://github.com/ThermIQ/thermiq_mqtt-ha as Integration
5. Go to the HACS integrations page, add ThermIQ integration.

## Configuration
#### Component Configuration:
```yaml
# ThermIQ-MQTT configuration.yaml entry
# Set the mqtt_node name here. Thats all!
thermiq_mqtt:
  mqtt_node: ThermIQ/ThermIQ-mqtt
  
#Input entities for ThermIQ -> configuration.yaml
input_number:
  thermiq_rum_bor2:
    name: 'Indoor target temp.'
    initial: 11
    min:  0
    max:  50
    step: 1
    unit_of_measurement: 'C'
    icon: 'mdi:temperature'
    mode: slider

  thermiq_kurva:
    name: 'Curve'
    initial: 11
    min:  0
    max:  200
    step: 1
    unit_of_measurement: 'C'
    icon: 'mdi:temperature'
    mode: slider
   
   
```
The complete configuration entry can be found in [configuration_thermiq.yaml](https://github.com/ThermIQ/thermiq_mqtt-ha/configuration_thermiq.yaml) and should be copied to your automations.yaml file.

### Automations configuration
A complete automation between frontend input entities to the backend control is included in [automations_thermiq.yaml](https://github.com/ThermIQ/thermiq_mqtt-ha/automations_thermiq.yaml) and should be copied to your automations.yaml file.


#### Lovelace Configuration:
The file [lovelace_config.yaml](https://github.com/ThermIQ/thermiq_mqtt-ha/lovelace_config.yaml) contains a complete setup of all available variables. A short example could look like:

```yaml
#Input entities for ThermIQ -> configuration.yaml
input_number:
  thermiq_rum_bor2:
    name: 'Indoor target temp.'
    initial: 11
    min:  0
    max:  50
    step: 1
    unit_of_measurement: 'C'
    icon: 'mdi:temperature'
    mode: slider

  thermiq_kurva:
    name: 'Curve'
    initial: 11
    min:  0
    max:  200
    step: 1
    unit_of_measurement: 'C'
    icon: 'mdi:temperature'
    mode: slider

  thermiq_kurva_min:
    name: 'Curve min'
    initial: 11
    min:  0
    max:  200
    step: 1
    unit_of_measurement: 'C'
    icon: 'mdi:temperature'
    mode: slider

```

The lovelace setup requires the following custom card to be installed in HACS
```
- text-divider-row


```

## Features and Limitations
- Currently provides all data from the heatpum in the form of sensors and binary sensors
- Allows control over the heatpump 

## Contributing
Contributions are welcome! If you'd like to contribute, feel free to pick up anything on the current [GitHub issues](https://github.com/ThermIQ/thermiq_mqtt-ha/issues) list!
Also, help making a nice lovelace card would be great!

### Code Formatting
This is a first hack. Our experience with Home Automation is limited but expanding. In the future we should try to follow the core Home Assistant style guidelines. Code should be formatted with `black` and imports sorted with `isort` (pending).

## Upstream Resources Used
