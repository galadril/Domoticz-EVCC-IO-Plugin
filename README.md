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
cd ~/domoticz/plugins
git clone https://github.com/galadril/Domoticz-EVCC-IO-Plugin.git
2. Install required Python packages:
cd Domoticz-EVCC-IO-Plugin
pip3 install -r requirements.txt
If you're running Domoticz in a different environment or have trouble with the dependencies, try:
# Find the Python used by Domoticz
which python3
# Use that path to install the dependencies
/path/to/python3 -m pip install websocket-client requests
For Domoticz running inside Docker:
docker exec -it domoticz pip3 install websocket-client requests
3. Make sure the plugin directory and all files have the correct permissions:
chmod -R 755 ~/domoticz/plugins/Domoticz-EVCC-IO-Plugin
4. Restart Domoticz:
sudo systemctl restart domoticz
# Or if running in Docker
docker restart domoticz
5. Add the plugin in Domoticz:
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
2. Ensure the websocket-client package is installed properly for your Domoticz environment

### Troubleshooting WebSocket Connection

If you see an error message "Websocket module not available" in the Domoticz log:

1. Check if the websocket-client package is installed:pip3 list | grep websocket
2. Make sure it's installed for the Python environment that Domoticz is using:# Find Domoticz's Python interpreter
ps aux | grep domoticz
# Install for that specific Python
/path/to/domoticz/python -m pip install websocket-client
3. You may need to restart Domoticz after installing the package.

WebSocket connection provides more comprehensive data, including detailed battery information, PV system details, and more accurate power measurements.

## Troubleshooting

If you encounter issues with the plugin:

1. Enable Debug logging in Domoticz:
   - Go to Setup ? Settings ? Log
   - Set "Log Level" to "Debug"
   
2. Check the Domoticz log for error messages:
   - Look for entries with "EVCC.IO" prefix
   
3. Verify that your EVCC.IO installation is accessible:
   - Try accessing the EVCC web interface at http://YOUR_EVCC_IP:7070
   - Test API access: http://YOUR_EVCC_IP:7070/api/state
   
4. Check if authentication is configured correctly:
   - Make sure the password matches what's set in EVCC
   
5. If you see Python errors, check the Python dependencies:pip3 show websocket-client
pip3 show requests
6. Restart Domoticz after making any changes to the plugin files

## License

This project is licensed under the MIT License - see the LICENSE file for details.