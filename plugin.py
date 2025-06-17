"""
<plugin key="Domoticz-EVCC-IO-Plugin" name="Domoticz EVCC IO Plugin" author="Mark Heinis" version="0.0.3" wikilink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin/wiki" externallink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin">
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
import json

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
        self.use_websocket = True
        self.last_websocket_update = 0
        self.last_device_update = 0
        self.last_data = None
        self.min_websocket_update_interval = 5  # Minimum seconds between updates
        self.ws_initialized = False  # Track if WebSocket has been initialized
        self.ws_retry_count = 0
        self.max_ws_retries = 3  # Maximum number of WebSocket reconnection attempts
        self.last_ws_reconnect = 0  # Track last websocket reconnection time
        self.ws_reconnect_interval = 60  # Force reconnect every 60 seconds
        
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
        
        # Initialize WebSocket if enabled
        if self.use_websocket:
            self._initialize_websocket()
        
        # Fetch initial state to create devices
        self._get_initial_state()
        
        Domoticz.Heartbeat(10)

    def _initialize_websocket(self):
        """Initialize WebSocket connection"""
        ws_connected = self.api.connect_websocket(keep_connection=True)
        if not ws_connected:
            if self.ws_retry_count < self.max_ws_retries:
                self.ws_retry_count += 1
                Domoticz.Log(f"Failed to connect to WebSocket (attempt {self.ws_retry_count}/{self.max_ws_retries}). Will retry...")
                return False
            else:
                Domoticz.Log("Failed to connect to WebSocket after multiple attempts. Will use REST API instead.")
                self.use_websocket = False
                return False
            
        Domoticz.Log("WebSocket connected successfully. Will receive real-time updates.")
        self.ws_initialized = True
        self.ws_retry_count = 0  # Reset retry count on successful connection
        return True

    def onHeartbeat(self):
        current_time = time.time()
        
        # For WebSocket mode, check if we have new data available
        if self.use_websocket:
            # Force reconnect every 60 seconds
            if (current_time - self.last_ws_reconnect >= self.ws_reconnect_interval):
                Domoticz.Log("Forcing WebSocket reconnection after 60 seconds")
                self.api.close_websocket()  # Close existing connection
                self.ws_initialized = False
                self.last_ws_reconnect = current_time
                self.ws_retry_count = 0  # Reset retry count for fresh connection attempt
            
            # Check WebSocket connection and try to reconnect if needed
            if not self.api.ws_connected:
                if self.ws_retry_count < self.max_ws_retries:
                    if not self._initialize_websocket():
                        # If reconnection fails, try again next heartbeat
                        return
                else:
                    # If we've exceeded retry attempts, fall back to REST API
                    self.use_websocket = False
                    self.update_devices_rest()
                    return
                
            # Check if we have new WebSocket data
            if self.api.ws_connected and self.api.ws_last_data:
                # Only update if we have new data and enough time has passed
                if (self.api.ws_last_data != self.last_data and 
                    current_time - self.last_websocket_update >= self.min_websocket_update_interval):
                    # Update data and process changes
                    self.last_data = self.api.ws_last_data.copy()  # Make a copy to detect future changes
                    self.last_websocket_update = current_time
                    self.update_devices()
                    self.ws_retry_count = 0  # Reset retry count on successful update
        else:
            # For REST API mode, use the standard interval
            self.run_again -= 1
            if self.run_again <= 0:
                self.run_again = self.update_interval / 10  # Set for next update interval
                self.update_devices_rest()
    
    def update_devices_rest(self):
        """Update devices using REST API"""
        try:
            state = self.api.get_state()
            if state:
                self.last_data = state
                self._update_devices_from_rest_api_data(state)
        except Exception as e:
            Domoticz.Error(f"Error updating devices via REST API: {str(e)}")

    def update_devices(self):
        """Update devices with current data"""
        if not self.last_data:
            return
            
        try:
            # Check for loadpoint structure that's common in WebSocket format
            has_loadpoint_prefix = any(key.startswith("loadpoints.") for key in self.last_data)
                
            if has_loadpoint_prefix:
                # This is a flat structure from WebSocket
                self._update_devices_from_websocket_data(self.last_data)
            else:
                # This is the original REST API nested structure
                self._update_devices_from_rest_api_data(self.last_data)
                    
        except Exception as e:
            Domoticz.Error(f"Error updating devices: {str(e)}")
    
    def _get_initial_state(self):
        """Fetch initial state to discover devices"""
        try:
            state = self.api.get_state()
            if not state:
                return
            
            # Process flat structure from WebSocket
            # Check for loadpoint structure that's common in WebSocket format
            has_loadpoint_prefix = any(key.startswith("loadpoints.") for key in state)
                
            # Create site devices
            if has_loadpoint_prefix:
                # This is a WebSocket flat structure
                self._process_websocket_data(state)
            else:
                # This is the original REST API nested structure
                self._process_rest_api_data(state)
            
        except Exception as e:
            Domoticz.Error(f"Error getting initial state: {str(e)}")
    
    def _process_websocket_data(self, data):
        """Process flat data structure from WebSocket format"""
        # WebSocket format has a flat structure with keys like:
        # "loadpoints.0.title", "battery", "pvPower", etc.
        
        # Extract site-level data (grid, home, pv, etc.)
        site_data = {
            key: value for key, value in data.items() 
            if not key.startswith(("loadpoints.", "vehicles."))
        }
        
        # Create site devices including PV and battery
        self.device_manager.create_site_devices(site_data, Devices)
        
        # Parse loadpoint data (loadpoints.0.*, loadpoints.1.*, etc.)
        loadpoints = {}
        loadpoint_indexes = set()
        
        # First identify all loadpoints
        for key in data.keys():
            if key.startswith("loadpoints."):
                parts = key.split(".")
                if len(parts) >= 2:
                    loadpoint_index = parts[1]
                    if loadpoint_index.isdigit():
                        loadpoint_indexes.add(int(loadpoint_index))
        
        # Then gather each loadpoint's data
        for idx in loadpoint_indexes:
            prefix = f"loadpoints.{idx}."
            loadpoint_data = {
                key[len(prefix):]: value 
                for key, value in data.items() 
                if key.startswith(prefix)
            }
            
            # Create loadpoint with a numeric ID
            loadpoint_id = idx + 1
            # Get title if available
            if "title" in loadpoint_data:
                self.device_manager.loadpoints[loadpoint_id] = loadpoint_data["title"]
            
            # Map WebSocket fields to expected fields
            if "chargePower" not in loadpoint_data and "chargePower" in site_data:
                loadpoint_data["chargePower"] = site_data["chargePower"]
            
            # Create devices for this loadpoint
            self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint_data, Devices)
        
        # Process vehicle data if available
        # In WebSocket format, vehicles are typically in a dictionary
        if "vehicles" in data and isinstance(data["vehicles"], dict):
            vehicle_index = 1
            for vehicle_id_str, vehicle_data in data["vehicles"].items():
                if isinstance(vehicle_data, dict):
                    # Store the external ID for API calls
                    vehicle_data["original_id"] = vehicle_id_str
                    self.device_manager.create_vehicle_devices(vehicle_index, vehicle_data, Devices)
                    vehicle_index += 1
    
    def _process_rest_api_data(self, state):
        """Process nested data structure from REST API"""
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
                        # Store the original ID in the loadpoint data for API calls
                        loadpoint["original_id"] = str(loadpoint_id)
                        self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint, Devices)
            elif isinstance(loadpoints, dict):
                loadpoint_index = 1
                for loadpoint_id_str, loadpoint in loadpoints.items():
                    if isinstance(loadpoint, dict):
                        loadpoint_name = loadpoint.get("title", f"Loadpoint {loadpoint_index}")
                        self.device_manager.loadpoints[loadpoint_index] = loadpoint_name
                        # Store the external ID in the loadpoint data
                        loadpoint["original_id"] = loadpoint_id_str
                        self.device_manager.create_loadpoint_devices(loadpoint_index, loadpoint, Devices)
                        loadpoint_index += 1
        
        # Create vehicle devices
        if "vehicles" in state:
            vehicles = state["vehicles"]
            if isinstance(vehicles, list):
                for i, vehicle in enumerate(vehicles):
                    vehicle_id = i + 1
                    if isinstance(vehicle, dict):
                        vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_id}"))
                        self.device_manager.vehicles[vehicle_id] = vehicle_name
                        # Store the original ID in the vehicle data for API calls
                        vehicle["original_id"] = str(vehicle_id)
                        self.device_manager.create_vehicle_devices(vehicle_id, vehicle, Devices)
            elif isinstance(vehicles, dict):
                vehicle_index = 1
                for vehicle_id_str, vehicle in vehicles.items():
                    if isinstance(vehicle, dict):
                        vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {vehicle_index}"))
                        self.device_manager.vehicles[vehicle_index] = vehicle_name
                        # Store the external ID in the vehicle data
                        vehicle["original_id"] = vehicle_id_str
                        self.device_manager.create_vehicle_devices(vehicle_index, vehicle, Devices)
                        vehicle_index += 1

    def onStop(self):
        Domoticz.Debug("onStop called")
        if self.api:
            self.api.logout()

    def update_devices_rest(self):
        """Update devices using REST API"""
        try:
            state = self.api.get_state()
            if state:
                self.last_data = state
                self._update_devices_from_rest_api_data(state)
        except Exception as e:
            Domoticz.Error(f"Error updating devices via REST API: {str(e)}")

    def update_devices(self):
        """Update devices with current data"""
        if not self.last_data:
            return
            
        try:
            # Check for loadpoint structure that's common in WebSocket format
            has_loadpoint_prefix = any(key.startswith("loadpoints.") for key in self.last_data)
                
            if has_loadpoint_prefix:
                # This is a flat structure from WebSocket
                self._update_devices_from_websocket_data(self.last_data)
            else:
                # This is the original REST API nested structure
                self._update_devices_from_rest_api_data(self.last_data)
                    
        except Exception as e:
            Domoticz.Error(f"Error updating devices: {str(e)}")
    
    def _update_devices_from_websocket_data(self, data):
        """Update devices with WebSocket data"""
        # Extract site-level data
        site_data = {
            key: value for key, value in data.items() 
            if not key.startswith(("loadpoints.", "vehicles."))
        }
        
        # Update site and battery information
        self.device_manager.update_site_devices(site_data, Devices)
        
        # If battery is present, update battery devices
        if self.device_manager.battery_present:
            if "battery" in site_data and isinstance(site_data["battery"], list) and site_data["battery"]:
                self.device_manager.update_battery_devices_from_array(site_data, Devices)
            else:
                self.device_manager.update_battery_devices(site_data, Devices)
        
        # Update loadpoint data
        loadpoint_indexes = set()
        for key in data.keys():
            if key.startswith("loadpoints."):
                parts = key.split(".")
                if len(parts) >= 2:
                    loadpoint_index = parts[1]
                    if loadpoint_index.isdigit():
                        loadpoint_indexes.add(int(loadpoint_index))
        
        # Then update each loadpoint's data
        for idx in loadpoint_indexes:
            prefix = f"loadpoints.{idx}."
            loadpoint_data = {
                key[len(prefix):]: value 
                for key, value in data.items() 
                if key.startswith(prefix)
            }
            
            # Create or update loadpoint with a numeric ID
            loadpoint_id = idx + 1
            
            # If this is a new loadpoint, create devices for it
            if loadpoint_id not in self.device_manager.loadpoints:
                if "title" in loadpoint_data:
                    self.device_manager.loadpoints[loadpoint_id] = loadpoint_data["title"]
                else:
                    self.device_manager.loadpoints[loadpoint_id] = f"Loadpoint {loadpoint_id}"
                self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint_data, Devices)
            
            # Update the devices for this loadpoint
            self.device_manager.update_loadpoint_devices(loadpoint_id, loadpoint_data, Devices)
        
        # Process vehicle data if available
        if "vehicles" in data and isinstance(data["vehicles"], dict):
            # First try to map external IDs to our internal IDs
            vehicle_id_mapping = {}
            
            # Scan through existing devices to find vehicles and their external IDs
            for unit in Devices:
                device_info = self.device_manager.get_device_info(unit)
                if device_info and device_info["device_type"] == "vehicle":
                    if Devices[unit].DeviceID and Devices[unit].DeviceID in data["vehicles"]:
                        internal_id = int(device_info["device_id"])
                        external_id = Devices[unit].DeviceID
                        vehicle_id_mapping[external_id] = internal_id
            
            # Process each vehicle
            for vehicle_id_str, vehicle_data in data["vehicles"].items():
                if isinstance(vehicle_data, dict):
                    if vehicle_id_str in vehicle_id_mapping:
                        # Update existing vehicle
                        our_vehicle_id = vehicle_id_mapping[vehicle_id_str]
                        self.device_manager.update_vehicle_devices(our_vehicle_id, vehicle_data, Devices)
                    else:
                        # Create new vehicle
                        our_vehicle_id = len(self.device_manager.vehicles) + 1
                        vehicle_name = vehicle_data.get("title", f"Vehicle {our_vehicle_id}")
                        self.device_manager.vehicles[our_vehicle_id] = vehicle_name
                        vehicle_data["original_id"] = vehicle_id_str
                        self.device_manager.create_vehicle_devices(our_vehicle_id, vehicle_data, Devices)
    
    def _update_devices_from_rest_api_data(self, state):
        """Update devices with REST API data"""
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
                            # Store the original ID in the vehicle data for API calls
                            vehicle["original_id"] = str(vehicle_id)
                            self.device_manager.create_vehicle_devices(vehicle_id, vehicle, Devices)
                        self.device_manager.update_vehicle_devices(vehicle_id, vehicle, Devices)
            elif isinstance(vehicles, dict):
                # First try to find existing vehicles with external IDs
                vehicle_id_mapping = {}
                
                # Scan through existing devices to find vehicles and their external IDs
                for unit in Devices:
                    device_info = self.device_manager.get_device_info(unit)
                    if device_info and device_info["device_type"] == "vehicle":
                        if Devices[unit].DeviceID and Devices[unit].DeviceID in vehicles:
                            internal_id = int(device_info["device_id"])
                            external_id = Devices[unit].DeviceID
                            vehicle_id_mapping[external_id] = internal_id
                            
                            # Ensure we have a clean name in the vehicles dict
                            if internal_id in self.device_manager.vehicles and isinstance(self.device_manager.vehicles[internal_id], dict):
                                # Extract just the name from the dict if needed
                                if "name" in self.device_manager.vehicles[internal_id]:
                                    self.device_manager.vehicles[internal_id] = self.device_manager.vehicles[internal_id]["name"]
                
                # Process vehicles, updating if known or creating if new
                for vehicle_id_str, vehicle in vehicles.items():
                    if vehicle_id_str in vehicle_id_mapping:
                        # We already know this vehicle, update it
                        our_vehicle_id = vehicle_id_mapping[vehicle_id_str]
                        self.device_manager.update_vehicle_devices(our_vehicle_id, vehicle, Devices)
                    else:
                        # This is a new vehicle
                        our_vehicle_id = len(self.device_manager.vehicles) + 1
                        if isinstance(vehicle, dict):
                            vehicle_name = vehicle.get("title", vehicle.get("name", f"Vehicle {our_vehicle_id}"))
                            self.device_manager.vehicles[our_vehicle_id] = vehicle_name
                            # Store the external ID in the vehicle data
                            vehicle["original_id"] = vehicle_id_str
                            self.device_manager.create_vehicle_devices(our_vehicle_id, vehicle, Devices)
        
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
                            # Store the original ID in the loadpoint data for API calls
                            loadpoint["original_id"] = str(loadpoint_id)
                            self.device_manager.create_loadpoint_devices(loadpoint_id, loadpoint, Devices)
                        self.device_manager.update_loadpoint_devices(loadpoint_id, loadpoint, Devices)
            elif isinstance(loadpoints, dict):
                # First try to find existing loadpoints with external IDs
                loadpoint_id_mapping = {}
                
                # Scan through existing devices to find loadpoints and their external IDs
                for unit in Devices:
                    device_info = self.device_manager.get_device_info(unit)
                    if device_info and device_info["device_type"] == "loadpoint":
                        if Devices[unit].DeviceID and Devices[unit].DeviceID in loadpoints:
                            internal_id = int(device_info["device_id"])
                            external_id = Devices[unit].DeviceID
                            loadpoint_id_mapping[external_id] = internal_id
                            
                            # Ensure we have a clean name in the loadpoints dict
                            if internal_id in self.device_manager.loadpoints and isinstance(self.device_manager.loadpoints[internal_id], dict):
                                # Extract just the name from the dict if needed
                                if "name" in self.device_manager.loadpoints[internal_id]:
                                    self.device_manager.loadpoints[internal_id] = self.device_manager.loadpoints[internal_id]["name"]
                
                # Process loadpoints, updating if known or creating if new
                for loadpoint_id_str, loadpoint in loadpoints.items():
                    if loadpoint_id_str in loadpoint_id_mapping:
                        # We already know this loadpoint, update it
                        our_loadpoint_id = loadpoint_id_mapping[loadpoint_id_str]
                        self.device_manager.update_loadpoint_devices(our_loadpoint_id, loadpoint, Devices)
                    else:
                        # This is a new loadpoint
                        our_loadpoint_id = len(self.device_manager.loadpoints) + 1
                        if isinstance(loadpoint, dict):
                            loadpoint_name = loadpoint.get("title", f"Loadpoint {our_loadpoint_id}")
                            self.device_manager.loadpoints[our_loadpoint_id] = loadpoint_name
                            # Store the external ID in the loadpoint data
                            loadpoint["original_id"] = loadpoint_id_str
                            self.device_manager.create_loadpoint_devices(our_loadpoint_id, loadpoint, Devices)
            
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
                    
                    # Get original ID from DeviceID if available
                    external_id = device_id
                    if Devices[Unit].DeviceID:
                        external_id = Devices[Unit].DeviceID
                    
                    if self.api.set_loadpoint_mode(external_id, mode):
                        update_device_value(Unit, Level, 0, Devices)
                
                elif parameter == "phases":
                    phases = 0
                    if Level == 0: phases = 0  # auto
                    elif Level == 10: phases = 1  # 1-phase
                    elif Level == 20: phases = 3  # 3-phase
                    
                    # Get original ID from DeviceID if available
                    external_id = device_id
                    if Devices[Unit].DeviceID:
                        external_id = Devices[Unit].DeviceID
                    
                    if self.api.set_loadpoint_phases(external_id, phases):
                        update_device_value(Unit, Level, 0, Devices)
                
                elif parameter == "min_soc":
                    # Get original ID from DeviceID if available
                    external_id = device_id
                    if Devices[Unit].DeviceID:
                        external_id = Devices[Unit].DeviceID
                    
                    if self.api.set_loadpoint_min_soc(external_id, Level):
                        update_device_value(Unit, 0, Level, Devices)
                
                elif parameter == "target_soc":
                    # Get original ID from DeviceID if available
                    external_id = device_id
                    if Devices[Unit].DeviceID:
                        external_id = Devices[Unit].DeviceID
                    
                    if self.api.set_loadpoint_target_soc(external_id, Level):
                        update_device_value(Unit, 0, Level, Devices)
            
            elif device_type == "battery" and parameter == "mode":
                mode = "normal"
                if Level == 0: mode = "unknown"
                elif Level == 10: mode = "normal"
                elif Level == 20: mode = "hold"
                elif Level == 30: mode = "charge"
                
                if self.api.set_battery_mode(mode):
                    update_device_value(Unit, Level, 0, Devices)
                    
            elif device_type == "vehicle":
                # Get original ID from DeviceID if available
                external_id = None
                if Devices[Unit].DeviceID:
                    external_id = Devices[Unit].DeviceID
                
                if external_id:
                    Domoticz.Log(f"Command for vehicle {external_id} parameter {parameter} not implemented yet")
                else:
                    Domoticz.Error(f"Cannot find external ID for vehicle {device_id}")
                
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