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
    match = re.search(r'^([a-z]+)_([a-zA-Z0-9:]+)_([a-z_]+)$', description)
    if match:
        return {
            'device_type': match.group(1),
            'device_id': match.group(2),
            'parameter': match.group(3)
        }
    return None

def update_device_value(unit, n_value, s_value, Devices=None):
    """Helper method to update device values"""
    # Use the passed Devices parameter if available, otherwise fall back to global
    if Devices is not None:
        devices_to_use = Devices
    else:
        # Devices is a global in the plugin context
        devices_to_use = Devices
        
    if unit not in devices_to_use:
        Domoticz.Error(f"Device unit {unit} does not exist")
        return
        
    try:
        device = devices_to_use[unit]
        
        # Convert to string if numeric
        if isinstance(s_value, (int, float)):
            if device.Type == 113:  # Custom Counter
                # For custom counter, we need to set both nValue and sValue to the actual value
                n_value = int(s_value * 1000)  # Store value * 1000 in nValue for precision
                s_value = f"{float(s_value):.3f}"  # Format with 3 decimal places
            elif device.Type == 243:  # Custom sensor type
                if device.SubType == 29:  # Power device (W)
                    # Power value should be formatted as: "current_power;today_energy"
                    # Since we don't track energy over time, use 0 for today's energy
                    s_value = f"{float(s_value):.1f};0"
                elif device.SubType == 33:  # Energy meter (kWh)
                    # Energy meters show both instant power and total energy
                    # Format: "instant_power;total_energy"
                    # For energy values, we just show 0 for power
                    s_value = f"0;{float(s_value):.3f}"
                elif device.SubType == 6:  # Percentage
                    s_value = f"{float(s_value):.1f}"
                elif device.SubType == 31:  # Distance (km)
                    s_value = f"{float(s_value):.1f}"
                elif device.SubType == 8:  # Counter
                    s_value = f"{float(s_value):.0f}"
                elif device.SubType == 23:  # Current (A)
                    s_value = f"{float(s_value):.3f}"
                else:
                    s_value = str(s_value)
            elif device.TypeName == "kWh":
                # For kWh type, format as "instant_power;total_energy"
                # For power devices, use power value and 0 for energy
                # For energy devices, use 0 for power and energy value
                if device.Description and ("power" in device.Description):
                    s_value = f"{float(s_value):.1f};0"
                else:
                    s_value = f"0;{float(s_value):.3f}"
            elif device.TypeName == "Usage":
                # For Usage type, just use the power value
                s_value = f"{float(s_value):.1f}"
            else:
                s_value = str(s_value)
            
        Domoticz.Debug(f"Updating device {unit} - n_value: {n_value}, s_value: {s_value}")
        
        # Create update dict with only required parameters
        update_dict = {
            "nValue": int(n_value),
            "sValue": str(s_value),
            "TimedOut": 0
        }
        
        # Update the device with the properly formatted parameters
        devices_to_use[unit].Update(**update_dict)
        
    except Exception as e:
        Domoticz.Error(f"Error updating device {unit}: {str(e)}")

def get_device_unit(device_mapping, unit_device_mapping, device_type, device_id, parameter, create_new=False, Devices=None):
    """Get or create a device unit number for the specified device"""
    # Import here to avoid circular imports
    from constants import (UNIT_BASE_SITE, UNIT_BASE_BATTERY, UNIT_BASE_PV,
                          UNIT_BASE_TARIFF, UNIT_BASE_GRID, UNIT_BASE_VEHICLE,
                          UNIT_BASE_LOADPOINT, UNIT_BASE_SESSION)
    
    key = f"{device_type}_{device_id}_{parameter}"
    
    # If mapping exists, return it
    if key in device_mapping:
        return device_mapping[key]
    
    # If not supposed to create a new one, return None
    if not create_new:
        return None
    
    # Create a new unit number based on device type
    base_unit = 1
    
    # Helper function to safely convert to int
    def safe_int(value, default=0):
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                if ':' in value:
                    # Handle special case for vehicle IDs like "db:2"
                    return int(value.split(':')[1])
                return int(value)
            except (ValueError, IndexError):
                return default
        return default
    
    if device_type == "site":
        base_unit = UNIT_BASE_SITE
    elif device_type == "battery":
        base_unit = UNIT_BASE_BATTERY + safe_int(device_id) * 10
    elif device_type == "pv":
        base_unit = UNIT_BASE_PV + safe_int(device_id) * 10
    elif device_type == "tariff":
        base_unit = UNIT_BASE_TARIFF
    elif device_type == "grid":
        base_unit = UNIT_BASE_GRID
    elif device_type == "vehicle":
        base_unit = UNIT_BASE_VEHICLE + safe_int(device_id) * 20
    elif device_type == "loadpoint":
        base_unit = UNIT_BASE_LOADPOINT + safe_int(device_id) * 20
    elif device_type == "session":
        base_unit = UNIT_BASE_SESSION + safe_int(device_id) * 10
    
    # Find the next available unit number
    unit = base_unit
    # Use the passed Devices parameter if available, otherwise fall back to global
    if Devices is not None:
        while unit in Devices:
            unit += 1
    else:
        # Devices is a global in the plugin context
        while unit in Devices:
            unit += 1
    
    # Store the mapping
    device_mapping[key] = unit
    unit_device_mapping[unit] = key
    
    Domoticz.Debug(f"Created new device unit mapping: {key} -> Unit {unit}")
    return unit

def format_device_name(device_type, title, parameter):
    """Format device name based on type, title and parameter"""
    if title:
        return f"{title} {parameter.replace('_', ' ').title()}"
    return f"{device_type.title()} {parameter.replace('_', ' ').title()}"