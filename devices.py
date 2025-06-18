#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Device management for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

import Domoticz
from helpers import get_device_unit, update_device_value, format_device_name
import re

class DeviceManager:
    """Class for handling device creation and updates"""
    
    def __init__(self):
        # Track created Domoticz.Devices with mapping: {type}_{id}_{parameter} -> unit
        # Example: "vehicle_1_soc" -> unit number
        self.device_unit_mapping = {}
        
        # Reverse mapping: unit -> {type}_{id}_{parameter}
        self.unit_device_mapping = {}
        
        # Track EVCC API objects by ID
        self.loadpoints = {}
        self.vehicles = {}
        self.battery_present = False
        self.pv_systems = {}
        self.grid_details = {}
        self.tariffs = {}
        self.session_stats = {}
        
        # Load existing device mappings will be done in onStart
        # after Devices are available

    def _load_device_mapping(self, Devices):
        """Load device mapping from existing device descriptions"""
        self.device_unit_mapping = {}
        self.unit_device_mapping = {}
        
        for unit in Devices:
            device = Devices[unit]
            # Try to extract mappings from device description if it follows our convention
            # Format: {type}_{id}_{parameter}
            match = re.search(r'^([a-z]+)_([a-zA-Z0-9:]+)_([a-z_]+)$', device.Description)
            if match:
                device_type = match.group(1)
                device_id = match.group(2)
                parameter = match.group(3)
                
                # Store in mapping
                key = f"{device_type}_{device_id}_{parameter}"
                self.device_unit_mapping[key] = unit
                self.unit_device_mapping[unit] = key
                
                # Store vehicle info from Name and DeviceID if available
                if device_type == "vehicle":
                    if ":" in device_id:  # WebSocket format
                        vehicle_name = device.Name.split(" ")[0]  # Get name before parameter
                        self.vehicles[device_id] = vehicle_name
                    else:  # REST API format
                        int_id = int(device_id)
                        vehicle_name = device.Name.split(" ")[0]  # Get name before parameter
                        if int_id not in self.vehicles:
                            self.vehicles[int_id] = vehicle_name
                
                # Store loadpoint info
                elif device_type == "loadpoint":
                    int_id = int(device_id)
                    loadpoint_name = device.Name.split(" ")[0]  # Get name before parameter
                    if int_id not in self.loadpoints:
                        self.loadpoints[int_id] = loadpoint_name
                
                # Track battery presence
                elif device_type == "battery":
                    self.battery_present = True
                    
                # Track grid details
                elif device_type == "grid":
                    if device_id not in self.grid_details:
                        self.grid_details[device_id] = {}
                    self.grid_details[device_id][parameter] = unit
                
                # Track tariffs
                elif device_type == "tariff":
                    if device_id not in self.tariffs:
                        self.tariffs[device_id] = {}
                    self.tariffs[device_id][parameter] = unit
                
                # Track session stats
                elif device_type == "session":
                    if device_id not in self.session_stats:
                        self.session_stats[device_id] = {}
                    self.session_stats[device_id][parameter] = unit
                
                Domoticz.Debug(f"Loaded device mapping: {key} -> Unit {unit}")
                if device.DeviceID:
                    Domoticz.Debug(f"  with external ID: {device.DeviceID}")

    def create_site_devices(self, site_data, Devices):
        """Create the site Domoticz.Devices based on available data"""
        # Grid power
        if "gridPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "grid_power", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;Watt'}  # Define custom options for power sensor
                Domoticz.Device(Unit=unit, Name="Grid Power", Type=243, Subtype=29, 
                              Options=options, Used=0, Description="site_1_grid_power").Create()
        elif "grid" in site_data and isinstance(site_data["grid"], dict) and "power" in site_data["grid"]:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "site", 1, "grid_power", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;Watt'}  # Define custom options for power sensor
                Domoticz.Device(Unit=unit, Name="Grid Power", Type=243, Subtype=29, 
                              Options=options, Used=0, Description="site_1_grid_power").Create()
        
        # Home power
        if "homePower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "home_power", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;Watt'}  # Define custom options for power sensor
                Domoticz.Device(Unit=unit, Name="Home Power", Type=243, Subtype=29, 
                              Options=options, Used=0, Description="site_1_home_power").Create()
                
        # PV power
        if "pvPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "pv_power", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;Watt'}  # Define custom options for power sensor
                Domoticz.Device(Unit=unit, Name="PV Power", Type=243, Subtype=29, 
                              Options=options, Used=0, Description="site_1_pv_power").Create()
        
        # Create PV system devices if available
        if "pv" in site_data and isinstance(site_data["pv"], list) and len(site_data["pv"]) > 0:
            self.create_pv_devices(site_data, Devices)
                
        # Battery Domoticz.Devices if present
        if any(key in site_data for key in ["batteryPower", "batterySoc", "batteryMode"]):
            self.battery_present = True
            self.create_battery_devices(site_data, Devices)
        # Check for battery array in WebSocket format
        elif "battery" in site_data and isinstance(site_data["battery"], list):
            self.battery_present = True
            self.create_battery_devices_from_array(site_data, Devices)
        
        # Create tariff devices
        if "tariffGrid" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "tariff", 1, "grid", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;EUR/kWh'}
                Domoticz.Device(Unit=unit, Name="Grid Tariff", Type=243, Subtype=1,
                              Options=options, Used=0, Description="tariff_1_grid").Create()

        if "tariffPriceHome" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "tariff", 1, "home", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;EUR/kWh'}
                Domoticz.Device(Unit=unit, Name="Home Tariff", Type=243, Subtype=1,
                              Options=options, Used=0, Description="tariff_1_home").Create()

        if "tariffPriceLoadpoints" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "tariff", 1, "loadpoints", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;EUR/kWh'}
                Domoticz.Device(Unit=unit, Name="Loadpoints Tariff", Type=243, Subtype=1,
                              Options=options, Used=0, Description="tariff_1_loadpoints").Create()

        # Create grid current devices
        if "grid" in site_data and isinstance(site_data["grid"], dict) and "currents" in site_data["grid"]:
            currents = site_data["grid"]["currents"]
            for phase in range(len(currents)):
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                     "grid", 1, f"current_l{phase+1}", True, Devices)
                if unit not in Devices:
                    options = {'Custom': '1;A'}
                    Domoticz.Device(Unit=unit, Name=f"Grid Current L{phase+1}", Type=243, Subtype=23,
                                  Options=options, Used=0, Description=f"grid_1_current_l{phase+1}").Create()

        # Create grid energy device
        if "grid" in site_data and isinstance(site_data["grid"], dict) and "energy" in site_data["grid"]:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "grid", 1, "energy", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;kWh'}
                Domoticz.Device(Unit=unit, Name="Grid Energy", Type=243, Subtype=33,
                              Options=options, Used=0, Description="grid_1_energy").Create()

        # Create green share devices
        if "greenShareHome" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "site", 1, "green_share_home", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;%'}
                Domoticz.Device(Unit=unit, Name="Home Green Share", Type=243, Subtype=6,
                              Options=options, Used=0, Description="site_1_green_share_home").Create()

        if "greenShareLoadpoints" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "site", 1, "green_share_loadpoints", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;%'}
                Domoticz.Device(Unit=unit, Name="Loadpoints Green Share", Type=243, Subtype=6,
                              Options=options, Used=0, Description="site_1_green_share_loadpoints").Create()
    
    def create_pv_devices(self, site_data, Devices):
        """Create PV system devices"""
        pv_systems = site_data.get("pv", [])
        
        for i, pv_system in enumerate(pv_systems):
            pv_id = i + 1
            pv_name = pv_system.get("title", f"PV System {pv_id}")
            self.pv_systems[pv_id] = pv_name
            
            # PV System Power
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "pv", pv_id, "power", True, Devices)
            if unit not in Devices:
                Domoticz.Log(f"Creating device '{pv_name} Power'.")
                Domoticz.Device(Unit=unit, Name=f"{pv_name} Power", Type=243, Subtype=29, 
                               Used=0, Description=f"pv_{pv_id}_power").Create()
    
    def create_battery_devices(self, site_data, Devices):
        """Create battery Domoticz.Devices"""
        # Battery power
        if "batteryPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "power", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;Watt'}  # Define custom options for power sensor
                Domoticz.Device(Unit=unit, Name="Battery Power", Type=243, Subtype=29, 
                               Options=options, Used=0, Description="battery_1_power").Create()
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "soc", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;%'}  # Define custom options for percentage sensor
                Domoticz.Device(Unit=unit, Name="Battery State of Charge", Type=243, Subtype=6, 
                               Options=options, Used=0, Description="battery_1_soc").Create()
                
        # Battery mode
        if "batteryMode" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "mode", True, Devices)
            if unit not in Devices:
                Options = {"LevelActions": "|||||",
                          "LevelNames": "Unknown|Normal|Hold|Charge|External",
                          "LevelOffHidden": "false",
                          "SelectorStyle": "0"}
                Domoticz.Device(Unit=unit, Name="Battery Mode", Type=244, Subtype=62, 
                              Switchtype=18, Image=9, Options=Options, Used=0, 
                              Description="battery_1_mode").Create()
    
    def create_battery_devices_from_array(self, site_data, Devices):
        """Create battery devices from the WebSocket battery array format"""
        battery_array = site_data.get("battery", [])
        
        if not battery_array:
            return
        
        for i, battery in enumerate(battery_array):
            battery_id = i + 1
            battery_name = battery.get("title", f"Battery {battery_id}")
            
            # Battery power
            if "power" in battery:
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                    "battery", battery_id, "power", True, Devices)
                if unit not in Devices:
                    options = {'Custom': '1;Watt'}  # Define custom options for power sensor
                    Domoticz.Log(f"Creating device '{battery_name} Power'.")
                    Domoticz.Device(Unit=unit, Name=f"{battery_name} Power", Type=243, Subtype=29, 
                                  Options=options, Used=0, Description=f"battery_{battery_id}_power").Create()
                    
            # Battery SoC
            if "soc" in battery:
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                    "battery", battery_id, "soc", True, Devices)
                if unit not in Devices:
                    options = {'Custom': '1;%'}  # Define custom options for percentage sensor
                    Domoticz.Log(f"Creating device '{battery_name} State of Charge'.")
                    Domoticz.Device(Unit=unit, Name=f"{battery_name} State of Charge", Type=243, Subtype=6, 
                                  Options=options, Used=0, Description=f"battery_{battery_id}_soc").Create()
    
    def create_vehicle_devices(self, vehicle_id, vehicle_data, Devices):
        """Create Domoticz.Devices for a vehicle"""
        # Get the vehicle name, accounting for possible dictionary storage
        vehicle_name = None
        if vehicle_id in self.vehicles:
            if isinstance(self.vehicles[vehicle_id], dict) and "name" in self.vehicles[vehicle_id]:
                vehicle_name = self.vehicles[vehicle_id]["name"]
            else:
                vehicle_name = self.vehicles[vehicle_id]
        
        # If no name found yet, try to get it from the vehicle data
        if not vehicle_name:
            vehicle_name = vehicle_data.get("title", vehicle_data.get("name", f"Vehicle {vehicle_id}"))
            # Store it properly for future use
            self.vehicles[vehicle_id] = vehicle_name
        
        # Log the vehicle being created
        Domoticz.Debug(f"Creating devices for vehicle ID {vehicle_id}: {vehicle_name}")
        
        # Use the original_id as DeviceID if provided
        external_id = ""
        if "original_id" in vehicle_data:
            external_id = vehicle_data["original_id"]
        
        # Vehicle SoC
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "vehicle", vehicle_id, "soc", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{vehicle_name} SoC'.")
            Domoticz.Device(Unit=unit, Name=f"{vehicle_name} SoC", Type=243, Subtype=6, 
                           Used=0, Description=f"vehicle_{vehicle_id}_soc", 
                           DeviceID=external_id).Create()
            
        # Vehicle range
        if "range" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "range", True, Devices)
            if unit not in Devices:
                Domoticz.Log(f"Creating device '{vehicle_name} Range'.")
                Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Range", Type=243, Subtype=31, 
                               Used=0, Description=f"vehicle_{vehicle_id}_range", 
                               DeviceID=external_id).Create()
            
        # Vehicle status
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "vehicle", vehicle_id, "status", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{vehicle_name} Status'.")
            Options = {"LevelActions": "||||",
                      "LevelNames": "Disconnected|Connected|Charging|Complete",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Status", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=0, 
                           Description=f"vehicle_{vehicle_id}_status", 
                           DeviceID=external_id).Create()
    
    def create_loadpoint_devices(self, loadpoint_id, loadpoint_data, Devices):
        """Create Domoticz.Devices for a loadpoint"""
        # Get the loadpoint name, accounting for possible dictionary storage
        loadpoint_name = None
        if loadpoint_id in self.loadpoints:
            if isinstance(self.loadpoints[loadpoint_id], dict) and "name" in self.loadpoints[loadpoint_id]:
                loadpoint_name = self.loadpoints[loadpoint_id]["name"]
            else:
                loadpoint_name = self.loadpoints[loadpoint_id]
        
        # If no name found yet, try to get it from the loadpoint data
        if not loadpoint_name:
            loadpoint_name = loadpoint_data.get("title", f"Loadpoint {loadpoint_id}")
            # Store it properly for future use
            self.loadpoints[loadpoint_id] = loadpoint_name
            
        # Log the loadpoint being created
        Domoticz.Debug(f"Creating devices for loadpoint ID {loadpoint_id}: {loadpoint_name}")
        
        # Use the original_id as DeviceID if provided
        external_id = ""
        if "original_id" in loadpoint_data:
            external_id = loadpoint_data["original_id"]
        
        # Charging power
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_power", True, Devices)
        if unit not in Devices:
            options = {'Custom': '1;Watt'}  # Define custom options for power sensor
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Power'.")
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Power", Type=243, Subtype=29, 
                           Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_charging_power", 
                           DeviceID=external_id).Create()
        
        # Charged energy (kWh)
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charged_energy", True, Devices)
        if unit not in Devices:
            options = {'Custom': '1;kWh'}  # Define custom options for energy sensor
            Domoticz.Log(f"Creating device '{loadpoint_name} Charged Energy'.")
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charged Energy", Type=243, Subtype=33, 
                           Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_charged_energy", 
                           DeviceID=external_id).Create()
            
        # Charging mode selector
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "mode", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Mode'.")
            Options = {"LevelActions": "||||",
                      "LevelNames": "Off|Now|Min+PV|PV",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Mode", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=0, 
                           Description=f"loadpoint_{loadpoint_id}_mode", 
                           DeviceID=external_id).Create()
            
        # Phases selector  
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "phases", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Phases'.")
            Options = {"LevelActions": "|||",
                      "LevelNames": "Auto|1-Phase|3-Phase",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Phases", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=0, 
                           Description=f"loadpoint_{loadpoint_id}_phases", 
                           DeviceID=external_id).Create()
            
        # Min SoC percentage if applicable
        if "minSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "min_soc", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;%'}  # Define custom options for percentage sensor
                Domoticz.Log(f"Creating device '{loadpoint_name} Min SoC'.")
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Min SoC", Type=243, Subtype=6, 
                               Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_min_soc", 
                               DeviceID=external_id).Create()
            
        # Target SoC percentage if applicable
        if "targetSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "target_soc", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;%'}  # Define custom options for percentage sensor
                Domoticz.Log(f"Creating device '{loadpoint_name} Target SoC'.")
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Target SoC", Type=243, Subtype=6, 
                               Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_target_soc", 
                               DeviceID=external_id).Create()
        
        # Charging timer (minutes)
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_timer", True, Devices)
        if unit not in Devices:
            options = {'Custom': '1;minutes'}  # Define custom options for time sensor
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Timer'.")
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Timer", Type=243, Subtype=8, 
                           Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_charging_timer", 
                           DeviceID=external_id).Create()
        
        # Create session statistics devices
        if "sessionEnergy" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_energy", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;kWh'}
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Session Energy", Type=243, Subtype=33,
                              Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_session_energy").Create()

        if "sessionPrice" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_price", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;EUR'}
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Session Price", Type=243, Subtype=1,
                              Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_session_price").Create()

        if "sessionPricePerKWh" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_price_per_kwh", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;EUR/kWh'}
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Session Price per kWh", Type=243, Subtype=1,
                              Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_session_price_per_kwh").Create()

        if "sessionSolarPercentage" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_solar_percentage", True, Devices)
            if unit not in Devices:
                options = {'Custom': '1;%'}
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Session Solar Percentage", Type=243, Subtype=6,
                              Options=options, Used=0, Description=f"loadpoint_{loadpoint_id}_session_solar_percentage").Create()
    
    def update_site_devices(self, site_data, Devices):
        """Update site Domoticz.Devices"""
        # Grid power - handle both formats (direct or nested in grid object)
        if "gridPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "grid_power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["gridPower"], Devices)
        elif "grid" in site_data and isinstance(site_data["grid"], dict) and "power" in site_data["grid"]:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "grid_power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["grid"]["power"], Devices)
        
        # Home power
        if "homePower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "home_power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["homePower"], Devices)
                
        # PV power
        if "pvPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "pv_power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["pvPower"], Devices)
        
        # Update PV system devices if available
        if "pv" in site_data and isinstance(site_data["pv"], list) and len(site_data["pv"]) > 0:
            self.update_pv_devices(site_data, Devices)
        
        # Update tariff devices
        if "tariffGrid" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "tariff", 1, "grid", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["tariffGrid"], Devices)

        if "tariffPriceHome" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "tariff", 1, "home", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["tariffPriceHome"], Devices)

        if "tariffPriceLoadpoints" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "tariff", 1, "loadpoints", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["tariffPriceLoadpoints"], Devices)

        # Update grid current devices
        if "grid" in site_data and isinstance(site_data["grid"], dict) and "currents" in site_data["grid"]:
            currents = site_data["grid"]["currents"]
            for phase in range(len(currents)):
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                     "grid", 1, f"current_l{phase+1}", False, Devices)
                if unit is not None:
                    update_device_value(unit, 0, currents[phase], Devices)

        # Update grid energy device
        if "grid" in site_data and isinstance(site_data["grid"], dict) and "energy" in site_data["grid"]:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "grid", 1, "energy", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["grid"]["energy"], Devices)

        # Update green share devices
        if "greenShareHome" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "site", 1, "green_share_home", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["greenShareHome"] * 100, Devices)

        if "greenShareLoadpoints" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "site", 1, "green_share_loadpoints", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["greenShareLoadpoints"] * 100, Devices)
    
    def update_pv_devices(self, site_data, Devices):
        """Update PV system devices"""
        pv_systems = site_data.get("pv", [])
        
        for i, pv_system in enumerate(pv_systems):
            pv_id = i + 1
            
            # PV System Power
            if "power" in pv_system:
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                      "pv", pv_id, "power", False, Devices)
                if unit is not None:
                    update_device_value(unit, 0, pv_system["power"], Devices)
    
    def update_battery_devices(self, site_data, Devices):
        """Update battery Domoticz.Devices"""
        # Battery power
        if "batteryPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["batteryPower"], Devices)
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "soc", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["batterySoc"], Devices)
                
        # Battery mode
        if "batteryMode" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "mode", False, Devices)
            if unit is not None:
                battery_mode = site_data["batteryMode"]
                mode_value = 0  # unknown
                if battery_mode == "normal": mode_value = 10
                elif battery_mode == "hold": mode_value = 20
                elif battery_mode == "charge": mode_value = 30
                elif battery_mode == "external": mode_value = 40
                update_device_value(unit, mode_value, 0, Devices)
    
    def update_battery_devices_from_array(self, site_data, Devices):
        """Update battery devices from WebSocket battery array format"""
        battery_array = site_data.get("battery", [])
        
        if not battery_array:
            return
        
        for i, battery in enumerate(battery_array):
            battery_id = i + 1
            
            # Battery power
            if "power" in battery:
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                      "battery", battery_id, "power", False, Devices)
                if unit is not None:
                    update_device_value(unit, 0, battery["power"], Devices)
                    
            # Battery SoC
            if "soc" in battery:
                unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                      "battery", battery_id, "soc", False, Devices)
                if unit is not None:
                    update_device_value(unit, 0, battery["soc"], Devices)
    
    def update_vehicle_devices(self, vehicle_id, vehicle_data, Devices):
        """Update vehicle Domoticz.Devices"""
        # Vehicle SoC
        if "soc" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "soc", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, vehicle_data["soc"], Devices)
                
        # Vehicle range
        if "range" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "range", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, vehicle_data["range"], Devices)
        
        # Vehicle status
        if "status" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "status", False, Devices)
            if unit is not None:
                status = vehicle_data["status"]
                status_value = 0  # disconnected
                if status == "A": status_value = 10  # connected
                elif status == "B": status_value = 20  # charging
                elif status == "C": status_value = 30  # complete
                update_device_value(unit, status_value, 0, Devices)
    
    def update_loadpoint_devices(self, loadpoint_id, loadpoint_data, Devices):
        """Update loadpoint Domoticz.Devices"""
        # Charging power
        if "chargePower" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "charging_power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["chargePower"], Devices)
        
        # Charged energy
        if "chargedEnergy" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "charged_energy", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["chargedEnergy"], Devices)
                
        # Charging mode
        if "mode" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "mode", False, Devices)
            if unit is not None:
                mode = loadpoint_data["mode"]
                mode_value = 0
                if mode == "off": mode_value = 0
                elif mode == "now": mode_value = 10
                elif mode == "minpv": mode_value = 20
                elif mode == "pv": mode_value = 30
                update_device_value(unit, mode_value, 0, Devices)
        
        # Phases
        if "phases" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "phases", False, Devices)
            if unit is not None:
                phases = loadpoint_data["phases"]
                phases_value = 0
                if phases == 0: phases_value = 0  # auto
                elif phases == 1: phases_value = 10  # 1-phase
                elif phases == 3: phases_value = 20  # 3-phase
                update_device_value(unit, phases_value, 0, Devices)
        
        # Min SoC
        if "minSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "min_soc", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["minSoc"], Devices)
        
        # Target SoC
        if "targetSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "target_soc", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["targetSoc"], Devices)
        
        # Charging timer
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_timer", False, Devices)
        if unit is not None:
            if "charging" in loadpoint_data and loadpoint_data["charging"]:
                if "chargeTimer" in loadpoint_data:
                    charge_timer = loadpoint_data["chargeTimer"]
                    minutes = int(charge_timer / 60)
                    update_device_value(unit, 0, minutes, Devices)
            else:
                update_device_value(unit, 0, 0, Devices)
        
        # Update session statistics devices
        if "sessionEnergy" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_energy", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["sessionEnergy"], Devices)

        if "sessionPrice" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_price", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["sessionPrice"], Devices)

        if "sessionPricePerKWh" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_price_per_kwh", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["sessionPricePerKWh"], Devices)

        if "sessionSolarPercentage" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                 "loadpoint", loadpoint_id, "session_solar_percentage", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["sessionSolarPercentage"], Devices)
                
    def get_device_info(self, unit):
        """Get device type, id and parameter from unit number"""
        if unit not in self.unit_device_mapping:
            return None
            
        device_info = self.unit_device_mapping[unit].split("_")
        if len(device_info) < 3:
            return None
            
        return {
            "device_type": device_info[0],
            "device_id": device_info[1],
            "parameter": device_info[2]
        }