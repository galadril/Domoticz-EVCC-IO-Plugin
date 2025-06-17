"""
<plugin key="Domoticz-EVCC-IO-Plugin" name="Domoticz EVCC IO Plugin" author="Mark Heinis" version="0.0.3" wikilink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin/wiki" externallink="https://github.com/galadril/Domoticz-EVCC-IO-Plugin">
    <description>
        Plugin for retrieving and updating EV charging data from EVCC.IO API.
    </description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="192.168.1.100"/>
        <param field="Port" label="Port" width="30px" required="true" default="7070"/>
        <param field="Password" label="Password (if auth enabled)" width="200px" required="false" default="" password="true"/>
        <param field="Mode1" label="Use WebSocket" width="75px">
            <options>
                <option label="Yes" value="1" default="true"/>
                <option label="No" value="0"/>
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
import sys
import os

# Import our modules
try:
    from api import EVCCApi, websocket_available
    from devices import DeviceManager
    from constants import DEFAULT_UPDATE_INTERVAL
    from helpers import update_device_value
except ImportError as e:
    Domoticz.Error(f"Error importing modules: {str(e)}")
    # Try to add the plugin directory to path
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.append(plugin_dir)
        Domoticz.Log(f"Added plugin directory to path: {plugin_dir}")
    
    # Try import again
    try:
        from api import EVCCApi, websocket_available
        from devices import DeviceManager
        from constants import DEFAULT_UPDATE_INTERVAL
        from helpers import update_device_value
    except ImportError as e:
        Domoticz.Error(f"Failed to import modules even after adding plugin directory to path: {str(e)}")
        # Define dummy classes in case imports failed
        class DummyDeviceManager:
            def __init__(self): pass
        class DummyEVCCApi:
            def __init__(self, address, port, password): pass
        EVCCApi = DummyEVCCApi
        DeviceManager = DummyDeviceManager
        DEFAULT_UPDATE_INTERVAL = 60
        def update_device_value(unit, n_value, s_value, Devices): pass
        websocket_available = False

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
        
    def onStart(self):
        Domoticz.Debug("onStart called")
        
        # Set update interval from parameters
        if Parameters["Mode2"] != "":
            self.update_interval = int(Parameters["Mode2"])
        
        # Whether to use WebSocket
        if Parameters["Mode1"] == "0":
            self.use_websocket = False
        
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
        
        # Connect to WebSocket if required and available
        if self.use_websocket:
            if not websocket_available:
                Domoticz.Log("WebSocket support is not available. Will use REST API instead.")
                Domoticz.Log("Please install websocket-client package if you want WebSocket support.")
                self.use_websocket = False
            else:
                ws_connected = self.api.connect_websocket()
                if not ws_connected:
                    Domoticz.Log("Failed to connect to WebSocket. Will use REST API instead.")
                    self.use_websocket = False
                else:
                    Domoticz.Log("WebSocket connected successfully. Will receive real-time updates.")
        
        # Fetch initial state to create devices
        self._get_initial_state()
        
        # Configure heartbeat - use a more frequent heartbeat if using WebSocket
        # so we can check for new data often, while still respecting update_interval for REST API
        if self.use_websocket:
            Domoticz.Heartbeat(2)  # Check for new WebSocket data every 2 seconds
        else:
            Domoticz.Heartbeat(10)  # Use standard 10-second interval for REST API

    def _get_initial_state(self):
        """Fetch initial state to discover devices"""
        try:
            state = self.api.get_state()
            if not state:
                Domoticz.Error("Failed to get initial state from EVCC API")
                return
            
            # Cache the initial state
            self.last_data = state
            
            # Process flat structure from WebSocket
            # Check for loadpoint structure that's common in WebSocket format
            has_loadpoint_prefix = any(key.startswith("loadpoints.") for key in state)
                
            # Create site devices
            if has_loadpoint_prefix:
                # This is a WebSocket flat structure
                Domoticz.Log("Detected WebSocket flat data structure")
                self._process_websocket_data(state)
            else:
                # This is the original REST API nested structure
                Domoticz.Log("Detected REST API nested data structure")
                self._process_rest_api_data(state)
            
            # Mark as successfully updated
            self.last_device_update = time.time()
            
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

    def onHeartbeat(self):
        current_time = time.time()
        
        # For WebSocket mode, check if we have new data available
        if self.use_websocket:
            # Check if we have new WebSocket data
            if self.api.ws_connected and self.api.ws_last_data:
                # Check if the data is different from what we last processed
                if (self.api.ws_last_data != self.last_data and 
                    current_time - self.last_websocket_update >= self.min_websocket_update_interval):
                    # Update data and process changes
                    self.last_data = self.api.ws_last_data
                    self.last_websocket_update = current_time
                    self.update_devices()
        else:
            # For REST API mode, use the standard interval
            self.run_again -= 1
            if self.run_again <= 0:
                self.run_again = self.update_interval / 10  # Set for next update interval
                self.update_devices()

    def update_devices(self):
        """Update all device values from EVCC API"""
        try:
            # Get the EVCC system state
            if self.use_websocket and self.last_data:
                # Use cached data if using WebSocket since it's continually updated
                state = self.last_data
            else:
                # Otherwise, fetch fresh data
                state = self.api.get_state()
                self.last_data = state
                
            if not state:
                Domoticz.Debug("No state data available for update")
                return
            
            # Check for loadpoint structure that's common in WebSocket format
            has_loadpoint_prefix = any(key.startswith("loadpoints.") for key in state)
                
            if has_loadpoint_prefix:
                # This is a flat structure from WebSocket
                self._update_devices_from_websocket_data(state)
            else:
                # This is the original REST API nested structure
                self._update_devices_from_rest_api_data(state)
            
            # Mark the last update time
            self.last_device_update = time.time()
                    
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
            if key.startswith("