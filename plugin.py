"""
<plugin key="Domoticz-EVCC-IO-Plugin" name="Domoticz EVCC IO Plugin" author="Mark Heinis" version="0.0.2" wikilink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin/wiki" externallink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin">
    <description>
        Plugin for retrieving and updating EV charging data from EVCC.IO API.
    </description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="192.168.1.100"/>
        <param field="Port" label="Port" width="30px" required="true" default="7070"/>
        <param field="Password" label="Password (if auth enabled)" width="200px" required="false" default="" password="true"/>
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
import time

# Import our modules
from api import EVCCApi
from devices import DeviceManager
from constants import DEFAULT_UPDATE_INTERVAL
from helpers import update_device_value

class BasePlugin:
    """Main EVCC IO Plugin class"""
    
    def __init__(self):
        self.api = None
        self.device_manager = None
        self.run_again = 6
        self.update_interval = DEFAULT_UPDATE_INTERVAL
        
    def onStart(self):
        Domoticz.Debug("onStart called")
        
        # Set update interval from parameters
        if Parameters["Mode2"] != "":
            self.update_interval = int(Parameters["Mode2"])
        
        # Set Debugging
        Domoticz.Debugging(int(Parameters["Mode6"]))
        
        # Initialize API client
        self.api = EVCCApi(
            address=Parameters["Address"],
            port=Parameters["Port"],
            password=Parameters["Password"] if Parameters["Password"] != "" else None
        )
        
        # Initialize device manager
        self.device_manager = DeviceManager()
        
        # Load existing device mappings with Devices object
        self.device_manager._load_device_mapping(Devices)
        
        # If authentication is required, login first
        if Parameters["Password"] != "":
            self.api.login()
        
        # Fetch initial state to create devices
        self._get_initial_state()
        
        # Configure heartbeat
        Domoticz.Heartbeat(10)

    def _get_initial_state(self):
        """Fetch initial state to discover devices"""
        try:
            state = self.api.get_state()
            if not state:
                return
                
            # Create site devices
            if "site" in state:
                self.device_manager.create_site_devices(state["site"], Devices)
                
            # Create loadpoint devices
            if "loadpoints" in state:
                loadpoints = state["loadpoints"]
                if isinstance(loadpoints, list):
                    for i, loadpoint in enumerate(loadpoints):
                        loadpoint_id = i + 1
                        if isinstance(loadpoint, dict):
                            self.device_manager.loadpoints[loadpoint_id] = loadpoint.get("title", f"Loadpoint {loadpoint_id}")
                            self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint, Devices)
                elif isinstance(loadpoints, dict):
                    for loadpoint_id_str, loadpoint in loadpoints.items():
                        loadpoint_id = len(self.device_manager.loadpoints) + 1
                        if isinstance(loadpoint, dict):
                            self.device_manager.loadpoints[loadpoint_id] = loadpoint.get("title", f"Loadpoint {loadpoint_id}")
                            self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint, Devices)
            
            # Create vehicle devices
            if "vehicles" in state:
                vehicles = state["vehicles"]
                if isinstance(vehicles, list):
                    for i, vehicle in enumerate(vehicles):
                        vehicle_id = i + 1
                        if isinstance(vehicle, dict):
                            vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_id}"))
                            self.device_manager.vehicles[vehicle_id] = vehicle_name
                            self.device_manager.create_vehicle_devices(vehicle_id, vehicle, Devices)
                elif isinstance(vehicles, dict):
                    vehicle_index = 1
                    for vehicle_id_str, vehicle in vehicles.items():
                        if isinstance(vehicle, dict):
                            vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_index}"))
                            self.device_manager.vehicles[vehicle_index] = vehicle_name
                            vehicle["original_id"] = vehicle_id_str
                            self.device_manager.create_vehicle_devices(vehicle_index, vehicle, Devices)
                            vehicle_index += 1
            
        except Exception as e:
            Domoticz.Error(f"Error getting initial state: {str(e)}")

    def onStop(self):
        Domoticz.Debug("onStop called")
        if self.api:
            self.api.logout()

    def onHeartbeat(self):
        self.run_again -= 1



        if self.run_again <= 0:
            self.run_again = self.update_interval / 10  # Set for next update interval
            self.update_devices()

    def update_devices(self):
        """Update all device values from EVCC API"""
        try:
            # Get the EVCC system state
            state = self.api.get_state()
            if not state:
                return
                
            # Update site and battery information
            if "site" in state:
                site_data = state["site"]
                self.device_manager.update_site_devices(site_data, Devices)
                
                # Update battery devices if present
                if self.device_manager.battery_present:
                    self.device_manager.update_battery_devices(site_data, Devices)
            
            # Update vehicle information
            if "vehicles" in state:
                vehicles = state["vehicles"]
                if isinstance(vehicles, list):
                    for i, vehicle in enumerate(vehicles):
                        vehicle_id = i + 1
                        if isinstance(vehicle, dict):
                            if vehicle_id not in self.device_manager.vehicles:
                                vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_id}"))
                                self.device_manager.vehicles[vehicle_id] = vehicle_name
                                self.device_manager.create_vehicle_devices(vehicle_id, vehicle, Devices)
                            self.device_manager.update_vehicle_devices(vehicle_id, vehicle, Devices)
                elif isinstance(vehicles, dict):
                    for vehicle_id_str, vehicle in vehicles.items():
                        our_vehicle_id = None
                        for idx, v_info in self.device_manager.vehicles.items():
                            if isinstance(v_info, dict) and v_info.get("original_id") == vehicle_id_str:
                                our_vehicle_id = idx
                                break
                        if our_vehicle_id is None:
                            our_vehicle_id = len(self.device_manager.vehicles) + 1
                            if isinstance(vehicle, dict):
                                vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {our_vehicle_id}"))
                                self.device_manager.vehicles[our_vehicle_id] = {
                                    "name": vehicle_name,
                                    "original_id": vehicle_id_str
                                }
                                vehicle["original_id"] = vehicle_id_str
                                self.device_manager.create_vehicle_devices(our_vehicle_id, vehicle, Devices)
                        if isinstance(vehicle, dict):
                            self.device_manager.update_vehicle_devices(our_vehicle_id, vehicle, Devices)
            
            # Update loadpoint information
            if "loadpoints" in state:
                loadpoints = state["loadpoints"]
                if isinstance(loadpoints, list):
                    for i, loadpoint in enumerate(loadpoints):
                        loadpoint_id = i + 1
                        if isinstance(loadpoint, dict):
                            if loadpoint_id not in self.device_manager.loadpoints:
                                loadpoint_name = loadpoint.get("title", f"Loadpoint {loadpoint_id}")
                                self.device_manager.loadpoints[loadpoint_id] = loadpoint_name
                                self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint, Devices)
                            self.device_manager.update_loadpoint_devices(loadpoint_id, loadpoint, Devices)
                elif isinstance(loadpoints, dict):
                    for loadpoint_id_str, loadpoint in loadpoints.items():
                        our_loadpoint_id = None
                        for idx, lp_name in self.device_manager.loadpoints.items():
                            if isinstance(lp_name, dict) and lp_name.get("original_id", "") == loadpoint_id_str:
                                our_loadpoint_id = idx
                                break
                        if our_loadpoint_id is None:
                            our_loadpoint_id = len(self.device_manager.loadpoints) + 1
                            if isinstance(loadpoint, dict):
                                loadpoint_name = loadpoint.get("title", f"Loadpoint {our_loadpoint_id}")
                                self.device_manager.loadpoints[our_loadpoint_id] = {
                                    "name": loadpoint_name,
                                    "original_id": loadpoint_id_str
                                }
                                self.device_manager.create_loadpoint_devices(our_loadpoint_id, loadpoint, Devices)
                        if isinstance(loadpoint, dict):
                            self.device_manager.update_loadpoint_devices(our_loadpoint_id, loadpoint, Devices)
                    
        except Exception as e:
            Domoticz.Error(f"Error updating devices: {str(e)}")
            
    def onCommand(self, Unit, Command, Level, Hue):
        """Handle commands sent to devices"""
        Domoticz.Debug(f"onCommand called for Unit: {Unit} Command: {Command} Level: {Level}")
        
        device_info = self.device_manager.get_device_info(Unit)
        if not device_info:
            Domoticz.Error(f"Unknown device unit: {Unit}")
            return
            
        device_type = device_info["device_type"]
        device_id = device_info["device_id"]
        parameter = device_info["parameter"]
        
        try:
            if device_type == "loadpoint":
                if parameter == "mode":
                    mode = "off"
                    if Level == 10: mode = "now" 
                    elif Level == 20: mode = "minpv"
                    elif Level == 30: mode = "pv"
                    
                    if self.api.set_loadpoint_mode(device_id, mode):
                        update_device_value(Unit, Level, 0)
                
                elif parameter == "phases":
                    phases = 0
                    if Level == 0: phases = 0  # auto
                    elif Level == 10: phases = 1  # 1-phase
                    elif Level == 20: phases = 3  # 3-phase
                    
                    if self.api.set_loadpoint_phases(device_id, phases):
                        update_device_value(Unit, Level, 0)
                
                elif parameter == "min_soc":
                    if self.api.set_loadpoint_min_soc(device_id, Level):
                        update_device_value(Unit, 0, Level)
                
                elif parameter == "target_soc":
                    if self.api.set_loadpoint_target_soc(device_id, Level):
                        update_device_value(Unit, 0, Level)
            
            elif device_type == "battery" and parameter == "mode":
                mode = "normal"
                if Level == 0: mode = "unknown"
                elif Level == 10: mode = "normal"
                elif Level == 20: mode = "hold"
                elif Level == 30: mode = "charge"
                
                if self.api.set_battery_mode(mode):
                    update_device_value(Unit, Level, 0)
                    
            elif device_type == "vehicle":
                vehicle_info = self.device_manager.vehicles.get(int(device_id), None)
                original_id = None
                
                if vehicle_info:
                    if isinstance(vehicle_info, dict):
                        original_id = vehicle_info.get("original_id", None)
                    else:
                        original_id = f"vehicle_{device_id}"
                
                if original_id:
                    Domoticz.Log(f"Command for vehicle {original_id} parameter {parameter} not implemented yet")
                else:
                    Domoticz.Error(f"Cannot find original ID for vehicle {device_id}")
                
        except Exception as e:
            Domoticz.Error(f"Error handling command: {str(e)}")

# Global plugin instance
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