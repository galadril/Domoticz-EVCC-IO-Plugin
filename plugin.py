"""
<plugin key="Domoticz-EVCC-IO-Plugin" name="Domoticz EVCC IO Plugin" author="Mark Heinis" version="0.0.5" wikilink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin/wiki" externallink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin">
    <description>
        Plugin for retrieving and updating EV charging data from EVCC.IO API.
    </description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="192.168.1.100"/>
        <param field="Port" label="Port" width="30px" required="true" default="7070"/>
        <param field="Password" label="Password (if auth enabled)" width="200px" required="false" default="" password="true"/>
        <param field="Mode1" label="Install Custom Page" width="75px">
            <options>
                <option label="Yes" value="true" default="true"/>
                <option label="No" value="false"/>
            </options>
        </param>
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
import os
import traceback
from shutil import copy2

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
        self.last_data_hash = None  # Track data hash to detect real changes
        self.min_websocket_update_interval = 5  # Minimum seconds between updates
        self.ws_initialized = False  # Track if WebSocket has been initialized
        self.ws_retry_count = 0
        self.max_ws_retries = 3  # Maximum number of WebSocket reconnection attempts
        self.last_ws_reconnect = 0  # Track last websocket reconnection time
        self.ws_reconnect_interval = 60  # Force reconnect every 60 seconds
        self.plugin_path = os.path.dirname(os.path.realpath(__file__))
        self.update_in_progress = False  # Flag to prevent multiple concurrent updates
        self.install_custom_page = True  # Default to installing custom page
        
    def _install_custom_page(self):
        """Install the custom EVCC dashboard page"""
        # Skip if custom page installation is disabled
        if not self.install_custom_page:
            Domoticz.Log("Custom EVCC dashboard installation skipped (disabled in settings)")
            return
            
        html_file = os.path.join(self.plugin_path, 'evcc.html')
        target_file = os.path.join('www', 'templates', 'evcc.html')
        
        # Update IP address and port in the HTML file
        with open(html_file, 'r') as f:
            content = f.read()
        
        # Replace the placeholders with the configured address and port
        content = content.replace('{{EVCC_ADDRESS}}', Parameters["Address"])
        content = content.replace('{{EVCC_PORT}}', Parameters["Port"])
        
        # Write the updated content to a temporary file
        temp_file = os.path.join(self.plugin_path, 'evcc_temp.html')
        with open(temp_file, 'w') as f:
            f.write(content)
        
        # Copy the temporary file to the target location
        if os.path.exists(target_file):
            os.remove(target_file)
        copy2(temp_file, target_file)
        
        # Clean up temporary file
        os.remove(temp_file)
        
        Domoticz.Log("Custom EVCC dashboard installed successfully")
        
    def _remove_custom_page(self):
        """Remove the custom EVCC dashboard page"""
        target_file = os.path.join('www', 'templates', 'evcc.html')
        if os.path.exists(target_file):
            os.remove(target_file)
            Domoticz.Log("Custom EVCC dashboard removed")

    def onStart(self):
        Domoticz.Debug("onStart called")
        
        # Set update interval from parameters
        if Parameters["Mode2"] != "":
            self.update_interval = int(Parameters["Mode2"])
        
        # Set custom page installation preference
        self.install_custom_page = Parameters["Mode1"] == "true"
        Domoticz.Log(f"Custom page installation is {'enabled' if self.install_custom_page else 'disabled'}")
        
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
        # Share API instance with device manager
        self.device_manager.api = self.api
        
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
        
        # Install custom page if enabled
        if self.install_custom_page:
            self._install_custom_page()
        
        Domoticz.Heartbeat(10)
        
    def onStop(self):
        Domoticz.Debug("onStop called")
        if self.api:
            self.api.logout()
        if self.install_custom_page:
            self._remove_custom_page()

    def _initialize_websocket(self):
        """Initialize WebSocket connection"""
        # First ensure any existing connection is properly closed
        if self.api.ws_connected:
            self.api.close_websocket()
            # Small delay to ensure socket is fully closed
            time.sleep(0.5)
            
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
        self.last_ws_reconnect = time.time()  # Update the last reconnect time
        return True

    def onHeartbeat(self):
        current_time = time.time()
        
        # Skip this update if already in progress
        if self.update_in_progress:
            Domoticz.Debug("Update already in progress, skipping this heartbeat")
            return
            
        self.update_in_progress = True
        
        try:
            # For WebSocket mode, check if we have new data available
            if self.use_websocket:
                # Force reconnect periodically
                if (current_time - self.last_ws_reconnect >= self.ws_reconnect_interval):
                    Domoticz.Log("Forcing WebSocket reconnection after reconnect interval")
                    self._initialize_websocket()  # This will handle closing and reconnecting
                    self.update_in_progress = False
                    return  # Skip this heartbeat cycle to allow connection to establish
                
                # Check WebSocket connection and try to reconnect if needed
                if not self.api.ws_connected:
                    if self.ws_retry_count < self.max_ws_retries:
                        if not self._initialize_websocket():
                            # If reconnection fails, try again next heartbeat
                            self.update_in_progress = False
                            return
                    else:
                        # If we've exceeded retry attempts, fall back to REST API
                        self.use_websocket = False
                        self.update_devices_rest()
                        self.update_in_progress = False
                        return
                    
                # Check if we have new WebSocket data
                if self.api.ws_connected and self.api.ws_last_data:
                    # Calculate a hash of the current data to check for real changes
                    current_hash = hash(json.dumps(self.api.ws_last_data, sort_keys=True))
                    
                    # Only update if we have new data and enough time has passed
                    if ((current_hash != self.last_data_hash) and 
                        (current_time - self.last_websocket_update >= self.min_websocket_update_interval)):
                        # Update data and process changes
                        self.last_data = self.api.ws_last_data.copy()  # Make a copy to detect future changes
                        self.last_data_hash = current_hash
                        self.last_websocket_update = current_time
                        Domoticz.Debug("WebSocket data changed, updating devices")
                        self.update_devices()
                        self.ws_retry_count = 0  # Reset retry count on successful update
            else:
                # For REST API mode, use the standard interval
                self.run_again -= 1
                if self.run_again <= 0:
                    self.run_again = self.update_interval / 10  # Set for next update interval
                    self.update_devices_rest()
        finally:
            self.update_in_progress = False

    def update_devices_rest(self):
        """Update devices using REST API"""
        try:
            Domoticz.Debug("Updating devices using REST API")
            state = self.api.get_state()
            if state:
                self.last_data = state
                self._update_devices_from_rest_api_data(state)
                self.last_device_update = time.time()
        except Exception as e:
            Domoticz.Error(f"Error updating devices via REST API: {str(e)}")
            Domoticz.Error(traceback.format_exc())

    def update_devices(self):
        """Update devices with current data"""
        if not self.last_data:
            return
            
        try:
            # Check for loadpoint structure that's common in WebSocket format
            has_loadpoint_prefix = any(key.startswith("loadpoints.") for key in self.last_data)
            
            current_time = time.time()
            Domoticz.Debug(f"Updating devices (last update: {int(current_time - self.last_device_update)}s ago)")
            self.last_device_update = current_time
                
            if has_loadpoint_prefix:
                # This is a flat structure from WebSocket
                self._update_devices_from_websocket_data(self.last_data)
            else:
                # This is the original REST API nested structure
                self._update_devices_from_rest_api_data(self.last_data)
                    
        except Exception as e:
            Domoticz.Error(f"Error updating devices: {str(e)}")
            Domoticz.Error(traceback.format_exc())
    
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
            Domoticz.Error(traceback.format_exc())
    
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

    def _update_devices_from_websocket_data(self, data):
        """Update devices from flat WebSocket data structure"""
        try:
            # Extract site-level data (grid, home, pv, etc.)
            site_data = {
                key: value for key, value in data.items() 
                if not key.startswith(("loadpoints.", "vehicles."))
            }
            
            # Create a mapping between WebSocket flat keys and expected nested structure
            if "gridPower" not in site_data and "grid.power" in data:
                site_data["gridPower"] = data["grid.power"]
                
            if "grid" not in site_data and "grid.power" in data:
                site_data["grid"] = {"power": data["grid.power"]}
                if "grid.currents" in data and isinstance(data["grid.currents"], list):
                    site_data["grid"]["currents"] = data["grid.currents"]
                if "grid.energy" in data:
                    site_data["grid"]["energy"] = data["grid.energy"]

            # Map individual battery fields to expected structure
            if any(key in site_data for key in ["batteryPower", "batterySoc", "batteryMode", "batteryEnergy"]):
                if "battery" not in site_data:
                    site_data["battery"] = []
                    battery_data = {}
                    if "batteryPower" in site_data: 
                        battery_data["power"] = site_data["batteryPower"]
                    if "batterySoc" in site_data:
                        battery_data["soc"] = site_data["batterySoc"]
                    if "batteryMode" in site_data:
                        battery_data["mode"] = site_data["batteryMode"]
                    if "batteryEnergy" in site_data:
                        battery_data["energy"] = site_data["batteryEnergy"]
                    if battery_data:
                        battery_data["title"] = "Battery"
                        site_data["battery"].append(battery_data)
            
            # Log the data we're about to use for updating
            Domoticz.Debug(f"Updating site devices with data: {json.dumps(site_data)[:200]}...")
            
            # Update site devices including PV and battery
            if site_data:
                self.device_manager.update_site_devices(site_data, Devices)

            # Parse loadpoint data
            loadpoint_indexes = set()
            for key in data.keys():
                if key.startswith("loadpoints."):
                    parts = key.split(".")
                    if len(parts) >= 2 and parts[1].isdigit():
                        loadpoint_indexes.add(int(parts[1]))
            
            # Update each loadpoint's devices
            for idx in loadpoint_indexes:
                prefix = f"loadpoints.{idx}."
                loadpoint_data = {
                    key[len(prefix):]: value 
                    for key, value in data.items() 
                    if key.startswith(prefix)
                }
                
                # Skip empty data
                if not loadpoint_data:
                    continue
                    
                # Update loadpoint with numeric ID
                loadpoint_id = idx + 1
                
                # Get charger status if available
                if "charger" in loadpoint_data and isinstance(loadpoint_data["charger"], str):
                    charger_id = loadpoint_data["charger"]
                    Domoticz.Debug(f"Getting detailed status for charger {charger_id}")
                    charger_status = self.api.get_charger_status(charger_id)
                    if charger_status:
                        Domoticz.Debug(f"Charger status received: {json.dumps(charger_status)}")
                        loadpoint_data.update(charger_status)
                
                # Map WebSocket fields to expected fields if needed
                if "chargePower" not in loadpoint_data and "chargePower" in site_data:
                    loadpoint_data["chargePower"] = site_data["chargePower"]
                
                Domoticz.Debug(f"Updating loadpoint {loadpoint_id} with data: {json.dumps(loadpoint_data)[:200]}...")
                self.device_manager.update_loadpoint_devices(loadpoint_id, loadpoint_data, Devices)

            # Process vehicle data
            if "vehicles" in data and isinstance(data["vehicles"], dict):
                vehicle_index = 1
                for vehicle_id_str, vehicle_data in data["vehicles"].items():
                    if isinstance(vehicle_data, dict):
                        # Get detailed vehicle status
                        Domoticz.Debug(f"Getting detailed status for vehicle {vehicle_id_str}")
                        vehicle_status = self.api.get_vehicle_status(vehicle_id_str)
                        if vehicle_status:
                            # Map charge status to selector switch values
                            if "chargeStatus" in vehicle_status:
                                status = vehicle_status["chargeStatus"]
                                vehicle_status["status"] = status  # Keep original status code
                            # Merge status with websocket data
                            vehicle_data.update(vehicle_status)
                            Domoticz.Debug(f"Updated vehicle data: {json.dumps(vehicle_data)}")
                        
                        Domoticz.Debug(f"Updating vehicle {vehicle_index} with data: {json.dumps(vehicle_data)[:200]}...")
                        self.device_manager.update_vehicle_devices(vehicle_index, vehicle_data, Devices)
                        vehicle_index += 1

        except Exception as e:
            Domoticz.Error(f"Error updating devices from WebSocket data: {str(e)}")
            Domoticz.Error(f"Traceback: {traceback.format_exc()}")

    def _update_devices_from_rest_api_data(self, state):
        """Update devices from nested REST API data structure"""
        try:
            # Update site devices
            if "site" in state:
                self.device_manager.update_site_devices(state["site"], Devices)
            
            # Update loadpoint devices
            if "loadpoints" in state:
                loadpoints = state["loadpoints"]
                if isinstance(loadpoints, list):
                    for i, loadpoint in enumerate(loadpoints):
                        loadpoint_id = i + 1
                        if isinstance(loadpoint, dict):
                            self.device_manager.update_loadpoint_devices(loadpoint_id, loadpoint, Devices)
                elif isinstance(loadpoints, dict):
                    loadpoint_index = 1
                    for loadpoint_id_str, loadpoint in loadpoints.items():
                        if isinstance(loadpoint, dict):
                            self.device_manager.update_loadpoint_devices(loadpoint_index, loadpoint, Devices)
                            loadpoint_index += 1
            
            # Update vehicle devices
            if "vehicles" in state:
                vehicles = state["vehicles"]
                if isinstance(vehicles, list):
                    for i, vehicle in enumerate(vehicles):
                        vehicle_id = i + 1
                        if isinstance(vehicle, dict):
                            # Get vehicle ID from DeviceID if available
                            external_id = None
                            for unit, device in Devices.items():
                                if device.DeviceID and device.Description.startswith(f"vehicle_{vehicle_id}_"):
                                    external_id = device.DeviceID
                                    break
                            if external_id:
                                # Get detailed vehicle status
                                vehicle_status = self.api.get_vehicle_status(external_id)
                                if vehicle_status:
                                    # Merge status with REST API data
                                    vehicle.update(vehicle_status)
                            self.device_manager.update_vehicle_devices(vehicle_id, vehicle, Devices)
                elif isinstance(vehicles, dict):
                    vehicle_index = 1
                    for vehicle_id_str, vehicle in vehicles.items():
                        if isinstance(vehicle, dict):
                            # Get detailed vehicle status
                            vehicle_status = self.api.get_vehicle_status(vehicle_id_str)
                            if vehicle_status:
                                # Merge status with REST API data
                                vehicle.update(vehicle_status)
                            self.device_manager.update_vehicle_devices(vehicle_index, vehicle, Devices)
                            vehicle_index += 1

        except Exception as e:
            Domoticz.Error(f"Error updating devices from REST API data: {str(e)}")
            Domoticz.Error(traceback.format_exc())

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
            Domoticz.Error(traceback.format_exc())

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