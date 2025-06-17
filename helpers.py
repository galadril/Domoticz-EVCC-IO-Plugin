#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Helper functions for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

import Domoticz
import re

def extract_device_info_from_description(description):
    """Extract device type, id, and parameter from device description"""
    match = re.search(r'^([a-z]+)_(\d+)_([a-z_]+)$', description)
    if match:
        return {
            'device_type': match.group(1),
            'device_id': match.group(2),
            'parameter': match.group(3)
        }
    return None

def update_device_value(unit, n_value, s_value):
    """Helper method to update device values"""
    # Devices is a global in the plugin context, so we can use it directly here
    if unit not in Devices:
        Domoticz.Error(f"Device unit {unit} does not exist")
        return
        
    try:
        if isinstance(s_value, (int, float)):
            s_value = str(s_value)
            
        Domoticz.Debug(f"Updating device {unit} - n_value: {n_value}, s_value: {s_value}")
        Devices[unit].Update(nValue=n_value, sValue=s_value, TimedOut=0)
        
    except Exception as e:
        Domoticz.Error(f"Error updating device {unit}: {str(e)}")

def get_device_unit(device_mapping, unit_device_mapping, device_type, device_id, parameter, create_new=False):
    """Get or create a device unit number for the specified device"""
    # Import here to avoid circular imports
    from constants import (UNIT_BASE_SITE, UNIT_BASE_BATTERY, 
                          UNIT_BASE_VEHICLE, UNIT_BASE_LOADPOINT)
    
    key = f"{device_type}_{device_id}_{parameter}"
    
    # If mapping exists, return it
    if key in device_mapping:
        return device_mapping[key]
    
    # If not supposed to create a new one, return None
    if not create_new:
        return None
    
    # Create a new unit number based on device type
    base_unit = 1
    if device_type == "site":
        base_unit = UNIT_BASE_SITE
    elif device_type == "battery":
        base_unit = UNIT_BASE_BATTERY
    elif device_type == "vehicle":
        base_unit = UNIT_BASE_VEHICLE + (int(device_id) - 1) * 20
    elif device_type == "loadpoint":
        base_unit = UNIT_BASE_LOADPOINT + (int(device_id) - 1) * 20
    
    # Find the next available unit number
    unit = base_unit
    # Devices is a global in the plugin context
    while unit in Devices:
        unit += 1
    
    # Store the mapping
    device_mapping[key] = unit
    unit_device_mapping[unit] = key
    
    Domoticz.Debug(f"Created new device unit mapping: {key} -> Unit {unit}")
    return unit