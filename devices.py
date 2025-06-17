#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Device management for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

import Domoticz
from helpers import get_device_unit
import re

class DeviceManager:
    """Class for handling device creation and updates"""
    
    def __init__(self):
        # Track created devices with mapping: {type}_{id} -> unit
        # Example: "vehicle_1_soc" -> unit number
        self.device_unit_mapping = {}
        
        # Reverse mapping: unit -> {type}_{id}
        self.unit_device_mapping = {}
        
        # Track EVCC API objects by ID
        self.loadpoints = {}
        self.vehicles = {}
        self.battery_present = False
        
        # Load existing device mappings
        self._load_device_mapping()
        
    def _load_device_mapping(self):
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
                
                Domoticz.Debug(f"Loaded device mapping: {key} -> Unit {unit}")
        
    def create_site_devices(self, site_data):
        """Create the site devices based on available data"""
        # Grid power
        if "gridPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "grid_power", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name="Grid Power", Type=243, Subtype=29, 
                               Used=1, Description="site_1_grid_power").Create()
        
        # Home power
        if "homePower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "home_power", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name="Home Power", Type=243, Subtype=29, 
                               Used=1, Description="site_1_home_power").Create()
                
        # PV power
        if "pvPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "pv_power", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name="PV Power", Type=243, Subtype=29, 
                               Used=1, Description="site_1_pv_power").Create()
                
        # Battery devices if present
        if "batteryPower" in site_data or "batterySoc" in site_data:
            self.battery_present = True
            self.create_battery_devices(site_data)
    
    def create_battery_devices(self, site_data):
        """Create battery devices"""
        # Battery power
        if "batteryPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "power", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name="Battery Power", Type=243, Subtype=29, 
                               Used=1, Description="battery_1_power").Create()
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "soc", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name="Battery State of Charge", Type=243, Subtype=6, 
                               Used=1, Description="battery_1_soc").Create()
                
        # Battery mode
        if "batteryMode" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "mode", True)
            if unit not in Domoticz.Devices:
                Options = {"LevelActions": "|||||",
                          "LevelNames": "Unknown|Normal|Hold|Charge|External",
                          "LevelOffHidden": "false",
                          "SelectorStyle": "0"}
                Domoticz.Device(Unit=unit, Name="Battery Mode", Type=244, Subtype=62, 
                              Switchtype=18, Image=9, Options=Options, Used=1, 
                              Description="battery_1_mode").Create()
    
    def create_vehicle_devices(self, vehicle_id, vehicle_data):
        """Create devices for a vehicle"""
        vehicle_name = self.vehicles.get(vehicle_id, f"Vehicle {vehicle_id}")
        
        # Vehicle SoC
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "vehicle", vehicle_id, "soc", True)
        if unit not in Domoticz.Devices:
            Domoticz.Device(Unit=unit, Name=f"{vehicle_name} SoC", Type=243, Subtype=6, 
                           Used=1, Description=f"vehicle_{vehicle_id}_soc").Create()
            
        # Vehicle range
        if "range" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "range", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Range", Type=243, Subtype=31, 
                               Used=1, Description=f"vehicle_{vehicle_id}_range").Create()
            
        # Vehicle status
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "vehicle", vehicle_id, "status", True)
        if unit not in Domoticz.Devices:
            Options = {"LevelActions": "||||",
                      "LevelNames": "Disconnected|Connected|Charging|Complete",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{vehicle_name} Status", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"vehicle_{vehicle_id}_status").Create()
    
    def create_loadpoint_devices(self, loadpoint_id, loadpoint_data):
        """Create devices for a loadpoint"""
        loadpoint_name = self.loadpoints.get(loadpoint_id, f"Loadpoint {loadpoint_id}")
        
        # Charging power
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_power", True)
        if unit not in Domoticz.Devices:
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Power", Type=243, Subtype=29, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charging_power").Create()
        
        # Charged energy
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charged_energy", True)
        if unit not in Domoticz.Devices:
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charged Energy", Type=243, Subtype=33, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charged_energy").Create()
            
        # Charging mode
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "mode", True)
        if unit not in Domoticz.Devices:
            Options = {"LevelActions": "||||",
                      "LevelNames": "Off|Now|Min+PV|PV",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Mode", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"loadpoint_{loadpoint_id}_mode").Create()
            
        # Phases
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "phases", True)
        if unit not in Domoticz.Devices:
            Options = {"LevelActions": "|||",
                      "LevelNames": "Auto|1-Phase|3-Phase",
                      "LevelOffHidden": "false",
                      "SelectorStyle": "0"}
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Phases", Type=244, Subtype=62, 
                           Switchtype=18, Image=9, Options=Options, Used=1, 
                           Description=f"loadpoint_{loadpoint_id}_phases").Create()
            
        # Min SoC if applicable
        if "minSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "min_soc", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Min SoC", Type=243, Subtype=6, 
                               Used=1, Description=f"loadpoint_{loadpoint_id}_min_soc").Create()
            
        # Target SoC if applicable
        if "targetSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "target_soc", True)
            if unit not in Domoticz.Devices:
                Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Target SoC", Type=243, Subtype=6, 
                               Used=1, Description=f"loadpoint_{loadpoint_id}_target_soc").Create()
        
        # Charging timer
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_timer", True)
        if unit not in Domoticz.Devices:
            Domoticz.Device(Unit=unit, Name=f"{loadpoint_name} Charging Timer", Type=243, Subtype=8, 
                           Used=1, Description=f"loadpoint_{loadpoint_id}_charging_timer").Create()
    
    def update_site_devices(self, site_data):
        """Update site devices"""
        from helpers import update_device_value
        
        # Grid power
        if "gridPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "grid_power")
            if unit is not None:
                update_device_value(unit, 0, site_data["gridPower"])
        
        # Home power
        if "homePower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "home_power")
            if unit is not None:
                update_device_value(unit, 0, site_data["homePower"])
                
        # PV power
        if "pvPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "site", 1, "pv_power")
            if unit is not None:
                update_device_value(unit, 0, site_data["pvPower"])
    
    def update_battery_devices(self, site_data):
        """Update battery devices"""
        from helpers import update_device_value
        
        # Battery power
        if "batteryPower" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "power")
            if unit is not None:
                update_device_value(unit, 0, site_data["batteryPower"])
                
        # Battery SoC
        if "batterySoc" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "soc")
            if unit is not None:
                update_device_value(unit, 0, site_data["batterySoc"])
                
        # Battery mode
        if "batteryMode" in site_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "battery", 1, "mode")
            if unit is not None:
                battery_mode = site_data["batteryMode"]
                mode_value = 0  # unknown
                if battery_mode == "normal": mode_value = 10
                elif battery_mode == "hold": mode_value = 20
                elif battery_mode == "charge": mode_value = 30
                elif battery_mode == "external": mode_value = 40
                update_device_value(unit, mode_value, 0)
    
    def update_vehicle_devices(self, vehicle_id, vehicle_data):
        """Update vehicle devices"""
        from helpers import update_device_value
        
        # Vehicle SoC
        if "soc" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "soc")
            if unit is not None:
                update_device_value(unit, 0, vehicle_data["soc"])
                
        # Vehicle range
        if "range" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "range")
            if unit is not None:
                update_device_value(unit, 0, vehicle_data["range"])
        
        # Vehicle status
        if "status" in vehicle_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "vehicle", vehicle_id, "status")
            if unit is not None:
                status = vehicle_data["status"]
                status_value = 0  # disconnected
                if status == "A": status_value = 10  # connected
                elif status == "B": status_value = 20  # charging
                elif status == "C": status_value = 30  # complete
                update_device_value(unit, status_value, 0)
    
    def update_loadpoint_devices(self, loadpoint_id, loadpoint_data):
        """Update loadpoint devices"""
        from helpers import update_device_value
        
        # Charging power
        if "chargePower" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "charging_power")
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["chargePower"])
        
        # Charged energy
        if "chargedEnergy" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "charged_energy")
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["chargedEnergy"])
                
        # Charging mode
        if "mode" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "mode")
            if unit is not None:
                mode = loadpoint_data["mode"]
                mode_value = 0
                if mode == "off": mode_value = 0
                elif mode == "now": mode_value = 10
                elif mode == "minpv": mode_value = 20
                elif mode == "pv": mode_value = 30
                update_device_value(unit, mode_value, 0)
        
        # Phases
        if "phases" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "phases")
            if unit is not None:
                phases = loadpoint_data["phases"]
                phases_value = 0
                if phases == 0: phases_value = 0  # auto
                elif phases == 1: phases_value = 10  # 1-phase
                elif phases == 3: phases_value = 20  # 3-phase
                update_device_value(unit, phases_value, 0)
        
        # Min SoC
        if "minSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "min_soc")
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["minSoc"])
        
        # Target SoC
        if "targetSoc" in loadpoint_data:
            unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                                  "loadpoint", loadpoint_id, "target_soc")
            if unit is not None:
                update_device_value(unit, 0, loadpoint_data["targetSoc"])
        
        # Charging timer
        unit = get_device_unit(self.device_unit_mapping, self.unit_device_mapping, 
                              "loadpoint", loadpoint_id, "charging_timer")
        if unit is not None:
            if "charging" in loadpoint_data and loadpoint_data["charging"]:
                if "chargeTimer" in loadpoint_data:
                    charge_timer = loadpoint_data["chargeTimer"]
                    minutes = int(charge_timer / 60)
                    update_device_value(unit, 0, minutes)
            else:
                update_device_value(unit, 0, 0)
                
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