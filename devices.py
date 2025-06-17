#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Device management for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

import Domoticz
from helpers import get_device_unit, update_device_value
import re

class DeviceManager:
    """Class for handling device creation and updates"""
    
    def __init__(self):
        # Track created Domoticz.Devices with mapping: {type}_{id} -> unit
        # Example: "vehicle_1_soc" -> unit number
        self.device_unit_mapping = {}
        
        # Reverse mapping: unit -> {type}_{id}
        self.unit_device_mapping = {}
        
        # Track EVCC API objects by ID
        self.loadpoints = {}
        self.vehicles = {}
        self.battery_present = False
        
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
            match = re.search(r'^([a-z]+)_(\d+)_([a-z_]+)$', device.Description)
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
                    int_id = int(device_id)
                    # Extract the vehicle name from device name (remove the parameter part)
                    if parameter == "soc" and " SoC" in device.Name:
                        vehicle_name = device.Name.replace(" SoC", "")
                        if int_id not in self.vehicles or isinstance(self.vehicles[int_id], dict):
                            self.vehicles[int_id] = vehicle_name
                    elif parameter == "status" and " Status" in device.Name:
                        vehicle_name = device.Name.replace(" Status", "")
                        if int_id not in self.vehicles or isinstance(self.vehicles[int_id], dict):
                            self.vehicles[int_id] = vehicle_name
                    elif parameter == "range" and " Range" in device.Name:
                        vehicle_name = device.Name.replace(" Range", "")
                        if int_id not in self.vehicles or isinstance(self.vehicles[int_id], dict):
                            self.vehicles[int_id] = vehicle_name
                
                # Store loadpoint info from Name and DeviceID if available
                if device_type == "loadpoint":
                    int_id = int(device_id)
                    # Extract the loadpoint name from device name (remove the parameter part)
                    if " Charging Power" in device.Name:
                        loadpoint_name = device.Name.replace(" Charging Power", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                    elif " Charging Mode" in device.Name:
                        loadpoint_name = device.Name.replace(" Charging Mode", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                    elif " Charging Phases" in device.Name:
                        loadpoint_name = device.Name.replace(" Charging Phases", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                    elif " Min SoC" in device.Name:
                        loadpoint_name = device.Name.replace(" Min SoC", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                    elif " Target SoC" in device.Name:
                        loadpoint_name = device.Name.replace(" Target SoC", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                    elif " Charging Timer" in device.Name:
                        loadpoint_name = device.Name.replace(" Charging Timer", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                    elif " Charged Energy" in device.Name:
                        loadpoint_name = device.Name.replace(" Charged Energy", "")
                        if int_id not in self.loadpoints or isinstance(self.loadpoints[int_id], dict):
                            self.loadpoints[int_id] = loadpoint_name
                
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
                Domoticz.Device(Unit=unit, Name="Grid Power", Type=243, Subtype=29, 
                               Used=1, Description="site_1_grid_power").Create()
        
        # Home power
        if "homePower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "home_power", True, Devices)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Home Power", Type=243, Subtype=29, 
                               Used=1, Description="site_1_home_power").Create()
                
        # PV power
        if "pvPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "pv_power", True, Devices)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="PV Power", Type=243, Subtype=29, 
                               Used=1, Description="site_1_pv_power").Create()
                
        # Battery Domoticz.Devices if present
        if "batteryPower" in site_data or "batterySoc" in site_data:
            self.battery_present = True
            self.create_battery_devices(site_data, Devices)
    
    def create_battery_devices(self, site_data, Devices):
        """Create battery Domoticz.Devices"""
        # Battery power
        if "batteryPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "power", True, Devices)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Battery Power", Type=243, Subtype=29, 
                               Used=1, Description="battery_1_power").Create()
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "soc", True, Devices)
            if unit not in Devices:
                Domoticz.Device(Unit=unit, Name="Battery State of Charge", Type=243, Subtype=6, 
                               Used=1, Description="battery_1_soc").Create()
                
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
                              Switchtype=18, Image=9, Options=Options, Used=1, 
                              Description="battery_1_mode").Create()
    
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
                           Used=1, Description=f"vehicle_{vehicle_id}_soc", 
                           DeviceID=external_id).Create()
            
        # Vehicle range
        if "range" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "range", True, Devices)
            if unit not in Devices:
                Domoticz.Log(f"Creating device '{vehicle_name} Range'.")
                Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Range", Type=243, Subtype=31, 
                               Used=1, Description=f"vehicle_{vehicle_id}_range", 
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
                           Switchtype=18, Image=9, Options=Options, Used=1, 
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
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Power'.")
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Power", Type=243, Subtype=29, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charging_power", 
                           DeviceID=external_id).Create()
        
        # Charged energy
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charged_energy", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{loadpoint_name} Charged Energy'.")
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charged Energy", Type=243, Subtype=33, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charged_energy", 
                           DeviceID=external_id).Create()
            
        # Charging mode
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "mode", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Mode'.")
            Options = {"LevelActions": "||||",
                      "LevelNames": "Off|Now|Min+PV|PV",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Mode", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"loadpoint_{loadpoint_id}_mode", 
                           DeviceID=external_id).Create()
            
        # Phases
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "phases", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Phases'.")
            Options = {"LevelActions": "|||",
                      "LevelNames": "Auto|1-Phase|3-Phase",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Phases", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"loadpoint_{loadpoint_id}_phases", 
                           DeviceID=external_id).Create()
            
        # Min SoC if applicable
        if "minSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "min_soc", True, Devices)
            if unit not in Devices:
                Domoticz.Log(f"Creating device '{loadpoint_name} Min SoC'.")
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Min SoC", Type=243, Subtype=6, 
                               Used=1, Description=f"loadpoint_{loadpoint_id}_min_soc", 
                               DeviceID=external_id).Create()
            
        # Target SoC if applicable
        if "targetSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "target_soc", True, Devices)
            if unit not in Devices:
                Domoticz.Log(f"Creating device '{loadpoint_name} Target SoC'.")
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Target SoC", Type=243, Subtype=6, 
                               Used=1, Description=f"loadpoint_{loadpoint_id}_target_soc", 
                               DeviceID=external_id).Create()
        
        # Charging timer
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_timer", True, Devices)
        if unit not in Devices:
            Domoticz.Log(f"Creating device '{loadpoint_name} Charging Timer'.")
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Timer", Type=243, Subtype=8, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charging_timer", 
                           DeviceID=external_id).Create()
    
    def update_site_devices(self, site_data, Devices):
        """Update site Domoticz.Devices"""
        # Grid power
        if "gridPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "grid_power", False, Devices)
            if unit is not None:
                update_device_value(unit, 0, site_data["gridPower"], Devices)
        
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