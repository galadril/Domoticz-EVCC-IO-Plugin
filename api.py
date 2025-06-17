#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API communication for the Domoticz EVCC IO Plugin
Author: Mark Heinis
"""

import Domoticz
import requests
import json
import threading
import time
import sys
import os

# Try to import websocket, with a fallback for Domoticz environment
websocket_available = False
try:
    # Add plugin directory to path to ensure all packages can be found
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import websocket
    websocket_available = True
    Domoticz.Log("Websocket module successfully imported")
except ImportError:
    Domoticz.Error("Websocket-client module not found. Install it using: pip3 install websocket-client")
    websocket_available = False

class EVCCApi:
    """Class for handling EVCC API communications"""
    
    def __init__(self, address, port, password=None):
        """Initialize API client with connection settings"""
        self.base_url = f"http://{address}:{port}/api"
        self.ws_url = f"ws://{address}:{port}/ws"
        self.password = password
        self.auth_cookie = None
        self.ws = None
        self.ws_connected = False
        self.ws_last_data = None
        self.ws_error = None
        self.ws_reconnect_interval = 60  # Reconnect every 60 seconds if connection lost
        self.ws_thread = None
        self.ws_last_log_time = 0
        self.ws_log_interval = 60  # Log only once per minute to avoid log spam
        
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
        # Close WebSocket connection if it exists
        self.close_websocket()
        
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
    
    def connect_websocket(self):
        """Connect to EVCC WebSocket for real-time data"""
        if not websocket_available:
            Domoticz.Error("Websocket module not available. Install it using: pip3 install websocket-client")
            return False
            
        if self.ws_connected:
            return True
            
        try:
            # Create WebSocket connection
            headers = {}
            cookies = self.get_cookies()
            if cookies:
                cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                headers["Cookie"] = cookie_str
            
            # Define WebSocket callbacks
            def on_message(ws, message):
                try:
                    # Parse the JSON message
                    data = json.loads(message)
                    
                    # Determine if this is a partial update or complete state
                    is_complete_state = False
                    
                    # Check if this is a complete state update
                    # Complete updates typically include pvPower, grid, or specific identifiers
                    if any(key in data for key in ["pvPower", "grid", "homePower", "version", "vehicles"]):
                        is_complete_state = True
                    
                    # Log only complete state updates or once per minute for partial updates
                    current_time = time.time()
                    if is_complete_state:
                        Domoticz.Debug("Complete WebSocket state update received")
                        self.ws_last_data = data
                    else:
                        # For partial updates, limit logging to reduce spam
                        if (current_time - self.ws_last_log_time) > self.ws_log_interval:
                            self.ws_last_log_time = current_time
                            Domoticz.Debug(f"Partial WebSocket update received with keys: {', '.join(list(data.keys())[:5])}...")
                        
                        # Merge partial updates with last complete state if available
                        if self.ws_last_data:
                            self.ws_last_data.update(data)
                        else:
                            # If no previous state, store this as the base state
                            self.ws_last_data = data
                    
                except Exception as e:
                    Domoticz.Error(f"Error parsing WebSocket data: {str(e)}")
            
            def on_error(ws, error):
                self.ws_error = str(error)
                Domoticz.Error(f"WebSocket error: {self.ws_error}")
                
            def on_close(ws, close_status_code, close_msg):
                self.ws_connected = False
                Domoticz.Log("WebSocket connection closed")
                
            def on_open(ws):
                self.ws_connected = True
                self.ws_error = None
                self.ws_last_data = None  # Reset data on new connection
                Domoticz.Log("WebSocket connection established")
            
            # Create WebSocket instance
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Start WebSocket in a separate thread
            def run_websocket():
                while True:
                    try:
                        self.ws.run_forever()
                        Domoticz.Log("WebSocket connection lost, reconnecting...")
                        time.sleep(5)  # Wait before reconnecting
                    except Exception as e:
                        Domoticz.Error(f"WebSocket thread error: {str(e)}")
                        time.sleep(self.ws_reconnect_interval)
            
            self.ws_thread = threading.Thread(target=run_websocket)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Wait for connection to establish
            timeout = 10
            start_time = time.time()
            while not self.ws_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            return self.ws_connected
            
        except Exception as e:
            Domoticz.Error(f"Error connecting to WebSocket: {str(e)}")
            return False
    
    def close_websocket(self):
        """Close WebSocket connection"""
        if self.ws:
            try:
                self.ws.close()
                self.ws_connected = False
                Domoticz.Log("WebSocket connection closed")
            except Exception as e:
                Domoticz.Error(f"Error closing WebSocket: {str(e)}")
    
    def get_state(self):
        """Get the current state of the EVCC system"""
        # First try to get data from WebSocket if connected
        if self.ws_connected and self.ws_last_data:
            return self.ws_last_data
        
        # If WebSocket not available, fall back to REST API
        try:
            # First try to connect WebSocket if not already connected
            if not self.ws_connected and websocket_available:
                self.connect_websocket()
                # If connection successful and data available, return it
                if self.ws_connected and self.ws_last_data:
                    return self.ws_last_data
            
            # Otherwise use regular API
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