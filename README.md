# Home Assistant ThermIQ-MQTT Integration
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![Screenshot](docs/Lovelace1.jpg)

This integration allows you to use the ThermIQ-MQTT hardware interface to control and monitor your Thermia or Danfoss heatpump from Home Assistant. It is available as a default component of HACS, the Home Assistant Community Store.

Some background information on the ThermIQ-MQTT interface can be found here:
https://thermiq.net

**This integration will evolve over time**
Please note that updating from Release 1.2.0 requires some significant changes in your configuration and you need to update your setup accordingly.

## Requirements

- A running Mosquitto MQTT broker (server). If you have one already you can use it otherwise install Mosquitto broker from HA Add-On Store
- The HA MQTT Integration added in "Devices/Services" and properly configured for the above broker.
- ThermIQ-MQTT interface installed in your heatpump and properly configured to communicate over MQTT to the above broker
- A couple of Lovelace plugins

## Quick start
1. Make sure that ThermIQ is properly setup and communicating with the MQTT server
2. Make sure that MQTT Integration in Home Assistant is setup and communicating with the MQTT server
3. Make sure you have HACS set-up (https://github.com/custom-components/hacs).
4. Make sure you have the required Lovelace plugins
5. Go to the HACS integrations page, add ThermIQ integration.

## Configuration
#### Component Configuration in v2.x.x:
Component configuration is now done in the graphical interface
- Note the current 'feature' where an existing entry cannot be edited but must be removed and added 

#### Component Configuration in v1.x.x:
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

I recommend using [MQTT Explorer](https://mqtt-explorer.com/) for analysis of the MQTT setup.

## Register description
A first attempt to create a description of the function behind each register can be found here
[REGISTERS.md](https://github.com/ThermIQ/thermiq_mqtt-ha/blob/master/REGISTERS.md)

## Features and Limitations
- Currently provides all data from the heatpump in the form of sensors and binary sensors
- Allows control over the heatpump 


## ThermIQ-USB Support
Tom R has created a Node-RED flow converting the previous version, ThermIQ-USB, to use the same MQTT messages making it compatible with this integration.
https://github.com/tomrosenback/thermiq-node-red-homeassistant-config

## Contributing
Contributions are welcome! If you'd like to contribute, feel free to pick up anything on the current [GitHub issues](https://github.com/ThermIQ/thermiq_mqtt-ha/issues) list!
All help improving the integration is appreciated!



