#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Constants for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

# Device unit numbers - base starting points for different device types
UNIT_BASE_SITE = 1                # Base for site devices (1-19)
UNIT_BASE_BATTERY = 20            # Base for battery devices (20-39)
UNIT_BASE_PV = 40                 # Base for PV system devices (40-59)
UNIT_BASE_TARIFF = 60             # Base for tariff devices (60-79)
UNIT_BASE_GRID = 80               # Base for detailed grid devices (80-99)
UNIT_BASE_VEHICLE = 100           # Base for vehicle devices (100-199)
UNIT_BASE_LOADPOINT = 200         # Base for loadpoint devices (200+)
UNIT_BASE_SESSION = 300           # Base for session metrics (300+)

# Default update interval
DEFAULT_UPDATE_INTERVAL = 60      # Default to 60 seconds

# Device Types
TYPE_CUSTOM = 243                 # Custom sensor type
SUBTYPE_POWER = 29                # Power device (W)
SUBTYPE_ENERGY = 33               # Energy meter (kWh)
SUBTYPE_PERCENTAGE = 6            # Percentage
SUBTYPE_DISTANCE = 31             # Distance (km)
SUBTYPE_COUNTER = 8               # Counter
SUBTYPE_CURRENT = 23              # Current (A)
SUBTYPE_CURRENCY = 1              # Currency (for prices)