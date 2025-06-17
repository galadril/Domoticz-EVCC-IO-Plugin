#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API communication for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

import Domoticz
import requests
import json

class EVCCApi:
    """Class for handling EVCC API communications"""
    
    def __init__(self, address, port, password=None):
        """Initialize API client with connection settings"""
        self.base_url = f"http://{address}:{port}/api"
        self.password = password
        self.auth_cookie = None
        
    def login(self):
        """Login to EVCC API if password is provided"""
        if not self.password:
            return True
            
        Domoticz.Debug("Logging in to EVCC API")
        try:
            response = requests.post(
                url=f"{self.base_url}/auth/login", 
                json={"password": self.password}
            )
            
            if response.status_code == 200:
                cookies = response.cookies
                for cookie in cookies:
                    if cookie.name == "auth":
                        self.auth_cookie = cookie
                        Domoticz.Log("Successfully logged in to EVCC API")
                        return True
                        
                Domoticz.Error("No auth cookie received after login")
                return False
            else:
                Domoticz.Error(f"Login failed with status code: {response.status_code}")
                return False
                
        except Exception as e:
            Domoticz.Error(f"Error logging in to EVCC API: {str(e)}")
            return False
            
    def logout(self):
        """Logout from EVCC API"""
        if self.auth_cookie is not None:
            try:
                requests.post(f"{self.base_url}/auth/logout")
                self.auth_cookie = None
                return True
            except Exception as e:
                Domoticz.Error(f"Error logging out from EVCC API: {str(e)}")
                return False
        return True
        
    def get_cookies(self):
        """Get authentication cookies if available"""
        if self.auth_cookie:
            return {"auth": self.auth_cookie.value}
        return {}
        
    def get_state(self):
        """Get the current state of the EVCC system"""
        try:
            cookies = self.get_cookies()
            
            response = requests.get(f"{self.base_url}/state", cookies=cookies)
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get EVCC state: {response.status_code}")
                return None

            data = response.json()
            
            # Check if this is data or result.data
            if "result" in data:
                return data["result"]
            else:
                return data
                
        except Exception as e:
            Domoticz.Error(f"Error getting EVCC state: {str(e)}")
            return None
            
    def set_loadpoint_mode(self, loadpoint_id, mode):
        """Set charging mode for a loadpoint"""
        try:
            cookies = self.get_cookies()
            response = requests.post(
                f"{self.base_url}/loadpoints/{loadpoint_id}/mode/{mode}", 
                cookies=cookies
            )
            if response.status_code == 200:
                Domoticz.Log(f"Successfully changed charging mode to {mode} for loadpoint {loadpoint_id}")
                return True
            else:
                Domoticz.Error(f"Failed to change charging mode: {response.status_code}")
                return False
        except Exception as e:
            Domoticz.Error(f"Error setting loadpoint mode: {str(e)}")
            return False
            
    def set_loadpoint_phases(self, loadpoint_id, phases):
        """Set number of phases for a loadpoint"""
        try:
            cookies = self.get_cookies()
            response = requests.post(
                f"{self.base_url}/loadpoints/{loadpoint_id}/phases/{phases}", 
                cookies=cookies
            )
            if response.status_code == 200:
                Domoticz.Log(f"Successfully changed charging phases to {phases} for loadpoint {loadpoint_id}")
                return True
            else:
                Domoticz.Error(f"Failed to change charging phases: {response.status_code}")
                return False
        except Exception as e:
            Domoticz.Error(f"Error setting loadpoint phases: {str(e)}")
            return False
            
    def set_loadpoint_min_soc(self, loadpoint_id, min_soc):
        """Set minimum SoC for a loadpoint"""
        try:
            cookies = self.get_cookies()
            response = requests.post(
                f"{self.base_url}/loadpoints/{loadpoint_id}/minsoc/{min_soc}", 
                cookies=cookies
            )
            if response.status_code == 200:
                Domoticz.Log(f"Successfully changed min SoC to {min_soc} for loadpoint {loadpoint_id}")
                return True
            else:
                Domoticz.Error(f"Failed to change min SoC: {response.status_code}")
                return False
        except Exception as e:
            Domoticz.Error(f"Error setting min SoC: {str(e)}")
            return False
            
    def set_loadpoint_target_soc(self, loadpoint_id, target_soc):
        """Set target SoC for a loadpoint"""
        try:
            cookies = self.get_cookies()
            response = requests.post(
                f"{self.base_url}/loadpoints/{loadpoint_id}/limitsoc/{target_soc}", 
                cookies=cookies
            )
            if response.status_code == 200:
                Domoticz.Log(f"Successfully changed target SoC to {target_soc} for loadpoint {loadpoint_id}")
                return True
            else:
                Domoticz.Error(f"Failed to change target SoC: {response.status_code}")
                return False
        except Exception as e:
            Domoticz.Error(f"Error setting target SoC: {str(e)}")
            return False
            
    def set_battery_mode(self, mode):
        """Set battery operating mode"""
        try:
            cookies = self.get_cookies()
            response = requests.post(
                f"{self.base_url}/batterymode/{mode}", 
                cookies=cookies
            )
            if response.status_code == 200:
                Domoticz.Log(f"Successfully changed battery mode to {mode}")
                return True
            else:
                Domoticz.Error(f"Failed to change battery mode: {response.status_code}")
                return False
        except Exception as e:
            Domoticz.Error(f"Error setting battery mode: {str(e)}")
            return False