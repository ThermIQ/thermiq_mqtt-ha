# Home Assistant ThermIQ-MQTT Integration
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

![Screenshot](docs/Lovelace1.jpg)

This integration allows you to use the ThermIQ-MQTT hardware interface to control and monitor your Thermia or Danfoss heatpump from Home Assistant. 
Get the neccessary hardware from [Thermiq.net](https://thermiq.net), where you also can read more about the background.

# Steps to install
1. Install the Mosquitto Add-on in Home Assistant.
2. Install [MQTT Explorer](https://mqtt-explorer.com/) on your PC and verify that you can connect to Mosquitto
3. Configure your ThermIQ-MQTT device according to the indstructions at [Thermiq.net](https://thermiq.net)
1. Use MQTT-Explorer to verify that your ThermIQ-MQTT device is sending information to Mosquitto. You should see MQTT messages in MQTT-Explorer from the heatpump every 30s
2. Install the MQTT Integration in Home Assistant and verify that it's communicating with the Mosquitto Add-on.
3. Install [HACS](https://github.com/custom-components/hacs)
5. Go to the HACS integrations page, add ThermIQ integration and restart HA.
6. Go to Integrations and add ThermIQ.
   1. ![configuration](docs/config_small.jpg)
   1. The MQTT Nodename should be set without a "/" at the end
   2. Use hexformat only if you have the old 1.xx ThermIQ-MQTT firmware 
   3. Use debug if you want to try it out without actually writing to the heatpump
8. To control and monitor the heatpump from your dashboard:
   1. HACS->Frontend->Explore/Add [HTML Jinja2 Template card](https://github.com/PiotrMachowski/Home-Assistant-Lovelace-HTML-Jinja2-Template-card)
   2. HACS->Frontend->Explore/Add [Number Box](https://github.com/htmltiger/numberbox-card)
   3. HACS->Frontend->Explore/Add [fold-entity-row](https://github.com/thomasloven/lovelace-fold-entity-row)
   4. Download/save the images [vp_base.jpg](vp_base.jpg), [vp_base_hgw_on.jpg](vp_base_hgw_on.jpg) and [vp_base_hw.jpg](vp_base_hw.jpg)
   5. Upload the downloaded files to your Home Assistant machine to either the folder **www/community/** or (**local/community/**)
   6. Go to your dashboard and add a new manual card
   7. Copy/paste the contents of [ThermIQ_Card.yaml](https://github.com/ThermIQ/thermiq_mqtt-ha/blob/master/ThermIQ_Card.yaml) into your manual card
   8. Before you save the card, adjust the ID if you've used anything else than the default **vp1** when setting up the integration. If you do: Ctrl+F with find/replace is your friend.


## Debugging
Make sure you see proper mqtt messages from the ThermIQ-MQTT in MQTT-Explorer before setting up HA

Home Assistant server sometimes needs to be restarted once all configuration is done

Use [MQTT Explorer](https://mqtt-explorer.com/) to ensure your heat pump is communicating with the Moqsuitto Add-on.

Updating from Release 1.x to Release 2.0 requires some significant changes in your configuration and you need to update/cleanup your setup accordingly.


# Automations
No setup of automations is needed. You can use the normal "input_number" services to change a value in the heatpump. For example:

```service: input_number.set_value
data: {"entity_id": "input_number.thermiq_mqtt_vp1_indoor_requested_t", "value":20}
```

# Available data
The data available is listed in [REGISTERS.md](https://github.com/ThermIQ/thermiq_mqtt-ha/blob/master/REGISTERS.md)

# Features and Limitations
- Currently provides all data from the heatpump in the form of sensors and binary sensors
- Allows control over the heatpump 

# Contributing
Contributions are welcome! If you'd like to contribute, feel free to pick up anything on the current [GitHub issues](https://github.com/ThermIQ/thermiq_mqtt-ha/issues) list!
The naming, translation and grouping of registers can be improved, your input is appreciated. Most of it is in the [thermiq_regs.py](https://github.com/ThermIQ/thermiq_mqtt-ha/blob/master/custom_components/thermiq_mqtt/heatpump/thermiq_regs.py)  

All help improving the integration is appreciated!

# ThermIQ-USB Support
Tom R has created [a Node-RED flow](https://github.com/tomrosenback/thermiq-node-red-homeassistant-config) converting the previous version, ThermIQ-USB, to use the same MQTT messages making it compatible with this integration.

# Domoticz Support
If you are looking for a Domoticz version, it's available from Jack: [Domoticz](https://github.com/jackfagner/ThermIQ-Domoticz)
