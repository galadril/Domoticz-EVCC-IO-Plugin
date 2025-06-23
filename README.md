# ⚡ Domoticz-EVCC-IO-Plugin

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)  
🔌 _EVCC.IO Plugin for Domoticz Home Automation_

This plugin allows you to **monitor and control your EV charging setup** via [EVCC](https://evcc.io/) from within the Domoticz smart home platform.

> 🌞 Supports solar energy systems, ⚡ EV chargers, 🔋 home batteries, and more — all in one place!

----------

## ✨ Features

-   **Real-time Monitoring** – Track power flow, charging status, and battery levels
    
-   **Vehicle Integration** – View SoC, range, and charging state
    
-   **Smart Control** – Adjust charging modes, phases, and SoC targets _(WIP)_
    
-   **WebSocket Support** – Low-latency updates for device states
    
-   **Custom Dashboard** – Optional embedded EVCC dashboard in Domoticz
    
-   **Multi Loadpoint Support** – Monitor multiple charging stations
    
-   **Battery Management** – Track and (optionally) control battery systems
    

----------

## ⚙️ Installation

> ✅ Python 3.4+ & Domoticz v3.87xx or higher required

### Prerequisites

-   Domoticz installed & running
    
-   EVCC accessible on your network
    
-   Python packages:
    
    ```bash
    pip3 install websocket-client requests
    
    ```
    

### Setup

```bash
cd ~/domoticz/plugins
git clone https://github.com/galadril/Domoticz-EVCC-IO-Plugin.git
pip3 install websocket-client requests
sudo service domoticz.sh restart

```

----------

## 🛠 Configuration

1.  Open Domoticz and go to **Setup > Hardware**
    
2.  Add new hardware of type **"Domoticz EVCC IO Plugin"**
    
3.  Fill in:
    
    -   **IP Address** of your EVCC server
        
    -   **Port** (default: `7070`)
        
    -   **Password** (if authentication is enabled)
        
    -   **Install Custom Page** (yes/no)
        
    -   **Update Interval**
        
    -   **Debug Level**
        
4.  Click **Add**
    

----------

## 🧾 Devices Created

The plugin will auto-generate devices based on your EVCC configuration.

### Grid & Home

-   Grid Power (import/export)
    
-   Home Consumption
    
-   PV Generation
    

### Battery (if present)

-   Charge/Discharge Power
    
-   State of Charge
    
-   Battery Mode (e.g. Hold, Charge)
    

### Loadpoints (per charger)

-   Charging Power & Energy
    
-   Charging Mode (Off, PV, Min+PV, Now)
    
-   Charging Phases (1/3/Auto)
    
-   Min SoC & Target SoC
    

### Vehicles (per EV)

-   SoC
    
-   Estimated Range
    
-   Charging Status
    

----------

## 📊 Custom Dashboard

A custom EVCC dashboard can be installed in Domoticz:

1.  Enable the option during plugin setup
    
2.  Navigate to: `Setup > More Options > Custom Pages`
    
3.  Click **EVCC**
    

----------

## 🔄 Updating

```bash
cd ~/domoticz/plugins/Domoticz-EVCC-IO-Plugin
git pull
sudo service domoticz.sh restart

```

----------

## 🧩 Troubleshooting

-   **Enable Debug Mode** in plugin settings for verbose logs
    
-   **Check EVCC connectivity**:
    
    ```bash
    curl http://<EVCC_IP>:7070/api/state
    
    ```
    
-   **Verify WebSocket module**:
    
    ```bash
    pip3 show websocket-client
    
    ```
    
-   **Permissions**:
    
    ```bash
    chmod -R 755 ~/domoticz/plugins/Domoticz-EVCC-IO-Plugin
    
    ```
    

----------

## 🕘 Changelog

| Version | Information |
| ----- | ---------- |
| 0.0.1 | Initial version |
| 0.0.2 | Added WebSocket support for real-time updates |
| 0.0.3 | Improved vehicle status monitoring |
| 0.0.4 | Added battery control and bug fixes |
| 0.0.5 | Custom dashboard integration and stability improvements |

----------

## 💬 Support

For bugs or feature requests, please use the [GitHub Issues](https://github.com/galadril/Domoticz-EVCC-IO-Plugin/issues) section.

----------

## ☕ Donate

If this plugin is useful to you, consider buying me a coffee (or 🍺 beer)!

[![Donate](https://img.shields.io/badge/paypal-donate-yellow.svg?logo=paypal)](https://www.paypal.me/markheinis)

----------

## 📄 License

This project is licensed under the **MIT License**.  
See the LICENSE file for details.

