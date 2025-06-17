"""
<plugin key="Domoticz-EVCC-IO-Plugin" name="Domoticz EVCC IO Plugin" author="Mark Heinis" version="0.0.1" wikilink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin/wiki" externallink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin">
    <description>
        Plugin for retrieving and updating EV charging data from EVCC.IO API.
    </description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="192.168.1.100"/>
        <param field="Port" label="Port" width="30px" required="true" default="7070"/>
        <param field="Mode1" label="Password (if auth enabled)" width="200px" required="false" default="" password="true"/>
        <param field="Mode2" label="Update interval (seconds)" width="30px" required="true" default="60"/>
        <param field="Mode6" label="Debug" width="200px">
            <options>
                <option label="None" value="0" default="true"/>
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import json
import requests
import time
from datetime import datetime
import re

class BasePlugin:
    # Plugin variables
    httpConn = None
    evccUrl = ""
    auth_cookie = None
    runAgain = 6
    updateInterval = 60  # default to 60 seconds
    
    # Device unit numbers - base starting points for different device types
    UNIT_BASE_SITE = 1                # Base for site devices (1-19)
    UNIT_BASE_BATTERY = 20            # Base for battery devices (20-39)
    UNIT_BASE_VEHICLE = 100           # Base for vehicle devices (100-199)
    UNIT_BASE_LOADPOINT = 200         # Base for loadpoint devices (200+)
    
    # Track created devices with mapping: {type}_{id} -> unit
    # Example: "vehicle_1_soc" -> unit number
    deviceUnitMapping = {}
    
    # Reverse mapping: unit -> {type}_{id}
    unitDeviceMapping = {}
    
    # Track EVCC API objects by ID
    loadpoints = {}
    vehicles = {}
    batteryPresent = False
    
    def __init__(self):
        return

    def onStart(self):
        Domoticz.Debug("onStart called")
        
        # Set update interval from parameters
        if Parameters["Mode2"] != "":
            self.updateInterval = int(Parameters["Mode2"])
        
        # Set base URL
        self.evccUrl = f"http://{Parameters['Address']}:{Parameters['Port']}/api"
        
        # Set Debugging
        Domoticz.Debugging(int(Parameters["Mode6"]))
        
        # Load device mapping from device descriptions
        self._loadDeviceMapping()
        
        # If authentication is required, login first
        if Parameters["Mode1"] != "":
            self.login()
        
        # Fetch initial state to create devices
        self._getInitialState()
        
        # Configure heartbeat
        Domoticz.Heartbeat(10)

    def _loadDeviceMapping(self):
        """Load device mapping from existing device descriptions"""
        self.deviceUnitMapping = {}
        self.unitDeviceMapping = {}
        
        for unit in Devices:
            device = Devices[unit]
            # Try to extract mappings from device description if it follows our convention
            # Format: {type}_{id}_{parameter}
            match = re.search(r'^([a-z]+)_(\d+)_([a-z_]+)$', device.Description)
            if match:
                device_type = match.group(1)
                device_id = match.group(2)
                parameter = match.group(3)
                
                # Store in mapping
                key = f"{device_type}_{device_id}_{parameter}"
                self.deviceUnitMapping[key] = unit
                self.unitDeviceMapping[unit] = key
                
                Domoticz.Debug(f"Loaded device mapping: {key} -> Unit {unit}")

    def _getInitialState(self):
        """Fetch initial state to discover devices"""
        try:
            headers = {}
            cookies = {}
            
            if self.auth_cookie is not None:
                cookies = {"auth": self.auth_cookie.value}
            
            response = requests.get(f"{self.evccUrl}/state", headers=headers, cookies=cookies)
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get initial EVCC state: {response.status_code}")
                return

            data = response.json()
            
            # Check if this is data or result.data
            if "result" in data:
                state = data["result"]
            else:
                state = data
                
            # Create site devices
            if "site" in state:
                self._createSiteDevices(state["site"])
                
            # Create loadpoint devices
            if "loadpoints" in state:
                for i, loadpoint in enumerate(state["loadpoints"]):
                    loadpoint_id = i + 1
                    self.loadpoints[loadpoint_id] = loadpoint.get("title", f"Loadpoint {loadpoint_id}")
                    self._createLoadpointDevices(loadpoint_id, loadpoint)
            
            # Create vehicle devices
            if "vehicles" in state:
                for i, vehicle in enumerate(state["vehicles"]):
                    vehicle_id = i + 1
                    vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_id}"))
                    self.vehicles[vehicle_id] = vehicle_name
                    self._createVehicleDevices(vehicle_id, vehicle)
            
        except Exception as e:
            Domoticz.Error(f"Error getting initial state: {str(e)}")

    def login(self):
        """Login to EVCC API if password is provided"""
        if Parameters["Mode1"] == "":
            return
            
        Domoticz.Debug("Logging in to EVCC API")
        try:
            response = requests.post(
                url=f"{self.evccUrl}/auth/login", 
                json={"password": Parameters["Mode1"]}
            )
            
            if response.status_code == 200:
                cookies = response.cookies
                for cookie in cookies:
                    if cookie.name == "auth":
                        self.auth_cookie = cookie
                        Domoticz.Log("Successfully logged in to EVCC API")
                        return
                        
                Domoticz.Error("No auth cookie received after login")
            else:
                Domoticz.Error(f"Login failed with status code: {response.status_code}")
                
        except Exception as e:
            Domoticz.Error(f"Error logging in to EVCC API: {str(e)}")

    def onStop(self):
        Domoticz.Debug("onStop called")
        if self.auth_cookie is not None:
            # Logout if we were logged in
            try:
                requests.post(f"{self.evccUrl}/auth/logout")
            except:
                pass

    def onHeartbeat(self):
        self.runAgain -= 1
        if self.runAgain <= 0:
            self.runAgain = self.updateInterval / 10  # Set for next update interval
            self.updateDevices()

    def _getDeviceUnit(self, device_type, device_id, parameter, create_new=False):
        """Get or create a device unit number for the specified device"""
        key = f"{device_type}_{device_id}_{parameter}"
        
        # If mapping exists, return it
        if key in self.deviceUnitMapping:
            return self.deviceUnitMapping[key]
        
        # If not supposed to create a new one, return None
        if not create_new:
            return None
        
        # Create a new unit number based on device type
        base_unit = 1
        if device_type == "site":
            base_unit = self.UNIT_BASE_SITE
        elif device_type == "battery":
            base_unit = self.UNIT_BASE_BATTERY
        elif device_type == "vehicle":
            base_unit = self.UNIT_BASE_VEHICLE + (int(device_id) - 1) * 20
        elif device_type == "loadpoint":
            base_unit = self.UNIT_BASE_LOADPOINT + (int(device_id) - 1) * 20
        
        # Find the next available unit number
        unit = base_unit
        while unit in Devices:
            unit += 1
        
        # Store the mapping
        self.deviceUnitMapping[key] = unit
        self.unitDeviceMapping[unit] = key
        
        Domoticz.Debug(f"Created new device unit mapping: {key} -> Unit {unit}")
        return unit

    def _createSiteDevices(self, site_data):
        """Create the site devices based on available data"""
        # Grid power
        if "gridPower" in site_data:
            unit = self._getDeviceUnit("site", 1, "grid_power", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Grid Power", Type=243, Subtype=29, Used=1, Description="site_1_grid_power").Create()
        
        # Home power
        if "homePower" in site_data:
            unit = self._getDeviceUnit("site", 1, "home_power", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Home Power", Type=243, Subtype=29, Used=1, Description="site_1_home_power").Create()
                
        # PV power
        if "pvPower" in site_data:
            unit = self._getDeviceUnit("site", 1, "pv_power", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="PV Power", Type=243, Subtype=29, Used=1, Description="site_1_pv_power").Create()
                
        # Battery devices if present
        if "batteryPower" in site_data or "batterySoc" in site_data:
            self.batteryPresent = True
            self._createBatteryDevices(site_data)

    def _createBatteryDevices(self, site_data):
        """Create battery devices"""
        # Battery power
        if "batteryPower" in site_data:
            unit = self._getDeviceUnit("battery", 1, "power", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Battery Power", Type=243, Subtype=29, Used=1, Description="battery_1_power").Create()
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = self._getDeviceUnit("battery", 1, "soc", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Battery State of Charge", Type=243, Subtype=6, Used=1, Description="battery_1_soc").Create()
                
        # Battery mode
        if "batteryMode" in site_data:
            unit = self._getDeviceUnit("battery", 1, "mode", True)
            if unit not in Devices:
                Options = {"LevelActions": "|||||",
                          "LevelNames": "Unknown|Normal|Hold|Charge|External",
                          "LevelOffHidden": "false",
                          "SelectorStyle": "0"}
                Domoticz.Device(Unit=unit, Name="Battery Mode", Type=244, Subtype=62, 
                              Switchtype=18, Image=9, Options=Options, Used=1, Description="battery_1_mode").Create()

    def _createVehicleDevices(self, vehicle_id, vehicle_data):
        """Create devices for a vehicle"""
        vehicle_name = self.vehicles.get(vehicle_id, f"Vehicle {vehicle_id}")
        
        # Vehicle SoC
        unit = self._getDeviceUnit("vehicle", vehicle_id, "soc", True)
        if unit not in Devices:
            Domoticz.Device(Unit=unit, Name=f"{vehicle_name} SoC", Type=243, Subtype=6, 
                           Used=1, Description=f"vehicle_{vehicle_id}_soc").Create()
            
        # Vehicle range
        if "range" in vehicle_data:
            unit = self._getDeviceUnit("vehicle", vehicle_id, "range", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Range", Type=243, Subtype=31, 
                               Used=1, Description=f"vehicle_{vehicle_id}_range").Create()
            
        # Vehicle status
        unit = self._getDeviceUnit("vehicle", vehicle_id, "status", True)
        if unit not in Devices:
            Options = {"LevelActions": "||||",
                      "LevelNames": "Disconnected|Connected|Charging|Complete",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Status", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"vehicle_{vehicle_id}_status").Create()

    def _createLoadpointDevices(self, loadpoint_id, loadpoint_data):
        """Create devices for a loadpoint"""
        loadpoint_name = self.loadpoints.get(loadpoint_id, f"Loadpoint {loadpoint_id}")
        
        # Charging power
        unit = self._getDeviceUnit("loadpoint", loadpoint_id, "charging_power", True)
        if unit not in Devices:
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Power", Type=243, Subtype=29, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charging_power").Create()
        
        # Charged energy
        unit = self._getDeviceUnit("loadpoint", loadpoint_id, "charged_energy", True)
        if unit not in Devices:
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charged Energy", Type=243, Subtype=33, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charged_energy").Create()
            
        # Charging mode
        unit = self._getDeviceUnit("loadpoint", loadpoint_id, "mode", True)
        if unit not in Devices:
            Options = {"LevelActions": "||||",
                      "LevelNames": "Off|Now|Min+PV|PV",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Mode", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"loadpoint_{loadpoint_id}_mode").Create()
            
        # Phases
        unit = self._getDeviceUnit("loadpoint", loadpoint_id, "phases", True)
        if unit not in Devices:
            Options = {"LevelActions": "|||",
                      "LevelNames": "Auto|1-Phase|3-Phase",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Phases", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"loadpoint_{loadpoint_id}_phases").Create()
            
        # Min SoC if applicable
        if "minSoc" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "min_soc", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Min SoC", Type=243, Subtype=6, 
                               Used=1, Description=f"loadpoint_{loadpoint_id}_min_soc").Create()
            
        # Target SoC if applicable
        if "targetSoc" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "target_soc", True)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Target SoC", Type=243, Subtype=6, 
                               Used=1, Description=f"loadpoint_{loadpoint_id}_target_soc").Create()
        
        # Charging timer
        unit = self._getDeviceUnit("loadpoint", loadpoint_id, "charging_timer", True)
        if unit not in Devices:
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Timer", Type=243, Subtype=8, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charging_timer").Create()

    def updateDevices(self):
        """Update all device values from EVCC API"""
        try:
            # Get the EVCC system state
            headers = {}
            cookies = {}
            
            if self.auth_cookie is not None:
                cookies = {"auth": self.auth_cookie.value}
            
            response = requests.get(f"{self.evccUrl}/state", headers=headers, cookies=cookies)
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get EVCC state: {response.status_code}")
                return

            data = response.json()
            
            # Check if this is data or result.data
            if "result" in data:
                state = data["result"]
            else:
                state = data
                
            # Update site and battery information
            if "site" in state:
                site_data = state["site"]
                self._updateSiteDevices(site_data)
                
                # Update battery devices if present
                if self.batteryPresent:
                    self._updateBatteryDevices(site_data)
            
            # Update vehicle information
            if "vehicles" in state:
                for i, vehicle in enumerate(state["vehicles"]):
                    vehicle_id = i + 1
                    
                    # Check if it's a new vehicle not seen before
                    if vehicle_id not in self.vehicles:
                        vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_id}"))
                        self.vehicles[vehicle_id] = vehicle_name
                        self._createVehicleDevices(vehicle_id, vehicle)
                    
                    self._updateVehicleDevices(vehicle_id, vehicle)
            
            # Update loadpoint information
            if "loadpoints" in state:
                for i, loadpoint in enumerate(state["loadpoints"]):
                    loadpoint_id = i + 1
                    
                    # Check if it's a new loadpoint not seen before
                    if loadpoint_id not in self.loadpoints:
                        loadpoint_name = loadpoint.get("title", f"Loadpoint {loadpoint_id}")
                        self.loadpoints[loadpoint_id] = loadpoint_name
                        self._createLoadpointDevices(loadpoint_id, loadpoint)
                    
                    self._updateLoadpointDevices(loadpoint_id, loadpoint)
                    
        except Exception as e:
            Domoticz.Error(f"Error updating devices: {str(e)}")

    def _updateSiteDevices(self, site_data):
        """Update site devices"""
        # Grid power
        if "gridPower" in site_data:
            unit = self._getDeviceUnit("site", 1, "grid_power")
            if unit is not None:
                self._updateDeviceValue(unit, 0, site_data["gridPower"])
        
        # Home power
        if "homePower" in site_data:
            unit = self._getDeviceUnit("site", 1, "home_power")
            if unit is not None:
                self._updateDeviceValue(unit, 0, site_data["homePower"])
                
        # PV power
        if "pvPower" in site_data:
            unit = self._getDeviceUnit("site", 1, "pv_power")
            if unit is not None:
                self._updateDeviceValue(unit, 0, site_data["pvPower"])

    def _updateBatteryDevices(self, site_data):
        """Update battery devices"""
        # Battery power
        if "batteryPower" in site_data:
            unit = self._getDeviceUnit("battery", 1, "power")
            if unit is not None:
                self._updateDeviceValue(unit, 0, site_data["batteryPower"])
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = self._getDeviceUnit("battery", 1, "soc")
            if unit is not None:
                self._updateDeviceValue(unit, 0, site_data["batterySoc"])
                
        # Battery mode
        if "batteryMode" in site_data:
            unit = self._getDeviceUnit("battery", 1, "mode")
            if unit is not None:
                battery_mode = site_data["batteryMode"]
                mode_value = 0  # unknown
                if battery_mode == "normal": mode_value = 10
                elif battery_mode == "hold": mode_value = 20
                elif battery_mode == "charge": mode_value = 30
                elif battery_mode == "external": mode_value = 40
                self._updateDeviceValue(unit, mode_value, 0)

    def _updateVehicleDevices(self, vehicle_id, vehicle_data):
        """Update vehicle devices"""
        # Vehicle SoC
        if "soc" in vehicle_data:
            unit = self._getDeviceUnit("vehicle", vehicle_id, "soc")
            if unit is not None:
                self._updateDeviceValue(unit, 0, vehicle_data["soc"])
                
        # Vehicle range
        if "range" in vehicle_data:
            unit = self._getDeviceUnit("vehicle", vehicle_id, "range")
            if unit is not None:
                self._updateDeviceValue(unit, 0, vehicle_data["range"])
        
        # Vehicle status
        if "status" in vehicle_data:
            unit = self._getDeviceUnit("vehicle", vehicle_id, "status")
            if unit is not None:
                status = vehicle_data["status"]
                status_value = 0  # disconnected
                if status == "A": status_value = 10  # connected
                elif status == "B": status_value = 20  # charging
                elif status == "C": status_value = 30  # complete
                self._updateDeviceValue(unit, status_value, 0)

    def _updateLoadpointDevices(self, loadpoint_id, loadpoint_data):
        """Update loadpoint devices"""
        # Charging power
        if "chargePower" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "charging_power")
            if unit is not None:
                self._updateDeviceValue(unit, 0, loadpoint_data["chargePower"])
        
        # Charged energy
        if "chargedEnergy" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "charged_energy")
            if unit is not None:
                self._updateDeviceValue(unit, 0, loadpoint_data["chargedEnergy"])
                
        # Charging mode
        if "mode" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "mode")
            if unit is not None:
                mode = loadpoint_data["mode"]
                mode_value = 0
                if mode == "off": mode_value = 0
                elif mode == "now": mode_value = 10
                elif mode == "minpv": mode_value = 20
                elif mode == "pv": mode_value = 30
                self._updateDeviceValue(unit, mode_value, 0)
        
        # Phases
        if "phases" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "phases")
            if unit is not None:
                phases = loadpoint_data["phases"]
                phases_value = 0
                if phases == 0: phases_value = 0  # auto
                elif phases == 1: phases_value = 10  # 1-phase
                elif phases == 3: phases_value = 20  # 3-phase
                self._updateDeviceValue(unit, phases_value, 0)
        
        # Min SoC
        if "minSoc" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "min_soc")
            if unit is not None:
                self._updateDeviceValue(unit, 0, loadpoint_data["minSoc"])
        
        # Target SoC
        if "targetSoc" in loadpoint_data:
            unit = self._getDeviceUnit("loadpoint", loadpoint_id, "target_soc")
            if unit is not None:
                self._updateDeviceValue(unit, 0, loadpoint_data["targetSoc"])
        
        # Charging timer
        unit = self._getDeviceUnit("loadpoint", loadpoint_id, "charging_timer")
        if unit is not None:
            if "charging" in loadpoint_data and loadpoint_data["charging"]:
                # If charging, update the charging timer
                if "chargeTimer" in loadpoint_data:
                    charge_timer = loadpoint_data["chargeTimer"]
                    # Convert seconds to minutes for the timer device
                    minutes = int(charge_timer / 60)
                    self._updateDeviceValue(unit, 0, minutes)
            else:
                # Not charging, set timer to 0
                self._updateDeviceValue(unit, 0, 0)

    def _updateDeviceValue(self, unit, n_value, s_value):
        """Helper method to update device values"""
        # Make sure device exists
        if unit not in Devices:
            Domoticz.Error(f"Device unit {unit} does not exist")
            return
            
        # Update the device
        try:
            if isinstance(s_value, (int, float)):
                s_value = str(s_value)
                
            Domoticz.Debug(f"Updating device {unit} - n_value: {n_value}, s_value: {s_value}")
            Devices[unit].Update(nValue=n_value, sValue=s_value, TimedOut=0)
            
        except Exception as e:
            Domoticz.Error(f"Error updating device {unit}: {str(e)}")
            
    def onCommand(self, Unit, Command, Level, Hue):
        """Handle commands sent to devices"""
        Domoticz.Debug(f"onCommand called for Unit: {Unit} Command: {Command} Level: {Level}")
        
        # Find device type from unit mapping
        if Unit not in self.unitDeviceMapping:
            Domoticz.Error(f"Unknown device unit: {Unit}")
            return
            
        device_info = self.unitDeviceMapping[Unit].split("_")
        if len(device_info) < 3:
            Domoticz.Error(f"Invalid device info for unit {Unit}: {self.unitDeviceMapping[Unit]}")
            return
            
        device_type = device_info[0]
        device_id = device_info[1]
        parameter = device_info[2]
        
        try:
            # Handle loadpoint devices
            if device_type == "loadpoint":
                # Handle charging mode changes
                if parameter == "mode":
                    mode = "off"
                    if Level == 10: mode = "now" 
                    elif Level == 20: mode = "minpv"
                    elif Level == 30: mode = "pv"
                    
                    response = requests.post(f"{self.evccUrl}/loadpoints/{device_id}/mode/{mode}")
                    if response.status_code == 200:
                        Domoticz.Log(f"Successfully changed charging mode to {mode} for loadpoint {device_id}")
                        self._updateDeviceValue(Unit, Level, 0)
                    else:
                        Domoticz.Error(f"Failed to change charging mode: {response.status_code}")
                
                # Handle phases changes
                elif parameter == "phases":
                    phases = 0
                    if Level == 0: phases = 0  # auto
                    elif Level == 10: phases = 1  # 1-phase
                    elif Level == 20: phases = 3  # 3-phase
                    
                    response = requests.post(f"{self.evccUrl}/loadpoints/{device_id}/phases/{phases}")
                    if response.status_code == 200:
                        Domoticz.Log(f"Successfully changed charging phases to {phases} for loadpoint {device_id}")
                        self._updateDeviceValue(Unit, Level, 0)
                    else:
                        Domoticz.Error(f"Failed to change charging phases: {response.status_code}")
                
                # Handle min SoC changes
                elif parameter == "min_soc":
                    # Level contains the SoC value
                    response = requests.post(f"{self.evccUrl}/loadpoints/{device_id}/minsoc/{Level}")
                    if response.status_code == 200:
                        Domoticz.Log(f"Successfully changed min SoC to {Level} for loadpoint {device_id}")
                        self._updateDeviceValue(Unit, 0, Level)
                    else:
                        Domoticz.Error(f"Failed to change min SoC: {response.status_code}")
                
                # Handle target SoC changes
                elif parameter == "target_soc":
                    # Level contains the SoC value
                    response = requests.post(f"{self.evccUrl}/loadpoints/{device_id}/limitsoc/{Level}")
                    if response.status_code == 200:
                        Domoticz.Log(f"Successfully changed target SoC to {Level} for loadpoint {device_id}")
                        self._updateDeviceValue(Unit, 0, Level)
                    else:
                        Domoticz.Error(f"Failed to change target SoC: {response.status_code}")
            
            # Handle battery mode changes
            elif device_type == "battery" and parameter == "mode":
                mode = "normal"
                if Level == 0: mode = "unknown"
                elif Level == 10: mode = "normal"
                elif Level == 20: mode = "hold"
                elif Level == 30: mode = "charge"
                
                response = requests.post(f"{self.evccUrl}/batterymode/{mode}")
                if response.status_code == 200:
                    Domoticz.Log(f"Successfully changed battery mode to {mode}")
                    self._updateDeviceValue(Unit, Level, 0)
                else:
                    Domoticz.Error(f"Failed to change battery mode: {response.status_code}")
                    
            # Handle vehicle specific commands
            elif device_type == "vehicle":
                # Could implement vehicle-specific commands here
                # such as setting min/max SoC for a specific vehicle
                Domoticz.Log(f"Command for vehicle {device_id} parameter {parameter} not implemented yet")
                
        except Exception as e:
            Domoticz.Error(f"Error handling command: {str(e)}")

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)