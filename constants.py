#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Constants for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

# Device unit numbers - base starting points for different device types
UNIT_BASE_SITE = 1                # Base for site devices (1-19)
UNIT_BASE_BATTERY = 20            # Base for battery devices (20-39)
UNIT_BASE_VEHICLE = 100           # Base for vehicle devices (100-199)
UNIT_BASE_LOADPOINT = 200         # Base for loadpoint devices (200+)

# Default update interval
DEFAULT_UPDATE_INTERVAL = 60      # Default to 60 seconds