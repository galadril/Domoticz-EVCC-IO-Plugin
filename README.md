# Domoticz EVCC IO Plugin

A plugin for Domoticz that connects to the EVCC IO API to monitor and control your EV charging setup.

## Features

- Monitor grid power, home power, and PV power
- Track battery power and state of charge
- Monitor and control EV charging stations (loadpoints)
- Track vehicle state of charge and range
- Supports both REST API and WebSocket connection for real-time updates

## Installation

### Prerequisites

- Domoticz installed and running
- EVCC.IO installed and accessible on your network
- Python 3.x with the following packages:
  - requests
  - websocket-client

### Steps

1. Clone this repository into the Domoticz plugins directory:

```bash
cd ~/domoticz/plugins
git clone https://github.com/galadril/Domoticz-EVCC-IO-Plugin.git
```

2. Install required Python packages:

```bash
cd Domoticz-EVCC-IO-Plugin
pip3 install -r requirements.txt
```

3. Restart Domoticz:

```bash
sudo systemctl restart domoticz
```

4. Add the plugin in Domoticz:
   - Go to Setup ? Hardware
   - In the Type dropdown, select "Domoticz EVCC IO Plugin"
   - Fill in the required settings
   - Click "Add"

## Configuration

| Setting | Description |
|---------|-------------|
| IP Address | The IP address of your EVCC.IO installation |
| Port | The port number of your EVCC.IO installation (default: 7070) |
| Password | Your EVCC.IO password (if authentication is enabled) |
| Use WebSocket | Enable WebSocket connection for real-time data updates |
| Update interval | How often to update the devices (in seconds) |

## Devices Created

The plugin creates various devices based on your EVCC setup:

### Site Devices
- Grid Power
- Home Power
- PV Power

### Battery Devices (if a battery is present)
- Battery Power
- Battery State of Charge
- Battery Mode

### PV System Devices (if PV systems are detected)
- PV System Power

### Vehicle Devices (for each vehicle)
- Vehicle SoC
- Vehicle Range
- Vehicle Status

### Loadpoint Devices (for each charging point)
- Charging Power
- Charged Energy
- Charging Mode
- Charging Phases
- Min SoC (if applicable)
- Target SoC (if applicable)
- Charging Timer

## WebSocket Support

The plugin can use WebSocket connection for real-time data updates from EVCC. This provides more detailed information and faster updates compared to the REST API. To use this feature:

1. Make sure the "Use WebSocket" option is enabled in the plugin settings
2. Ensure the websocket-client package is installed (`pip3 install websocket-client`)

WebSocket connection provides more comprehensive data, including detailed battery information, PV system details, and more accurate power measurements.

## Troubleshooting

If you encounter issues with the plugin:

1. Enable Debug logging in Domoticz
2. Check the Domoticz log for error messages
3. Verify that your EVCC.IO installation is accessible from Domoticz
4. Check if authentication is configured correctly

## License

This project is licensed under the MIT License - see the LICENSE file for details.