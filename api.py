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
        self.ws_last_data = {}  # Change to dict for better merging
        self.ws_temp_data = {}  # Temporary storage for partial updates
        self.ws_error = None
        self.ws_reconnect_interval = 60  # Reconnect every 60 seconds if connection lost
        self.ws_thread = None
        self.ws_last_log_time = 0
        self.ws_log_interval = 60  # Log only once per minute to avoid log spam
        self.ws_keep_connection = False  # Whether to keep WebSocket connection open
        self.last_complete_update = 0
        self.min_complete_update_interval = 5  # Minimum seconds between complete updates
        self.update_in_progress = False  # Flag to prevent simultaneous update operations
        self.last_data_update = 0  # Track when the ws_last_data was last updated
        
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
    
    def connect_websocket(self, keep_connection=True):
        """Connect to EVCC WebSocket for real-time data
        
        Args:
            keep_connection: If True, keep connection open. If False, close after receiving full state.
        """
        if not websocket_available:
            Domoticz.Error("Websocket module not available. Install it using: pip3 install websocket-client")
            return False
            
        # Ensure any existing connection is closed first
        self.close_websocket()
        # Small delay to ensure socket is fully closed
        time.sleep(0.5)
            
        try:
            # Create WebSocket connection
            headers = {}
            cookies = self.get_cookies()
            if cookies:
                cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                headers["Cookie"] = cookie_str
            
            # Reset state flags
            self.ws_connected = False
            self.received_complete_state = False
            self.ws_last_data = {}
            self.ws_temp_data = {}
            self.ws_keep_connection = keep_connection
            
            # Define WebSocket callbacks
            def on_message(ws, message):
                try:
                    # Parse the JSON message
                    data = json.loads(message)
                    current_time = time.time()
                    
                    # Log the received data as a single line
                    Domoticz.Debug(f"WebSocket data: {json.dumps(data)}")
                    
                    # Determine if this is a complete state update
                    # Complete updates typically include multiple key indicators
                    complete_state_indicators = {"pvPower", "grid", "homePower", "loadpoints.0"}
                    is_complete_state = False
                    
                    # Avoid updating data while another update is in progress
                    if self.update_in_progress:
                        Domoticz.Debug("Update in progress, deferring WebSocket message processing")
                        return
                    
                    # Set update in progress flag
                    self.update_in_progress = True
                    
                    try:
                        if isinstance(data, dict):
                            present_indicators = complete_state_indicators.intersection(data.keys())
                            is_complete_state = len(present_indicators) >= 2  # Consider complete if 2+ indicators present
                            
                            if is_complete_state and (current_time - self.last_complete_update) >= self.min_complete_update_interval:
                                self.last_complete_update = current_time
                                self.ws_last_data = data.copy()  # Store complete state
                                self.ws_temp_data = {}  # Clear temporary data
                                self.received_complete_state = True
                                self.last_data_update = current_time
                                
                                # Log complete state as a single line
                                Domoticz.Debug(f"Complete state: {json.dumps(self.ws_last_data)}")
                                
                                # Handle one-time connection mode
                                if not self.ws_keep_connection:
                                    Domoticz.Log("Received complete state, closing one-time WebSocket connection")
                                    threading.Timer(2.0, self.close_websocket).start()
                            else:
                                # Handle partial update
                                # Store in temporary buffer first
                                self.ws_temp_data.update(data)
                                
                                # Only merge temp data periodically to avoid excessive updates
                                if self.ws_last_data and (current_time - self.last_data_update) >= 1:
                                    # Merge temporary data into last complete state
                                    merged_data = self.ws_last_data.copy()
                                    merged_data.update(self.ws_temp_data)
                                    self.ws_last_data = merged_data
                                    self.ws_temp_data = {}  # Clear temporary buffer
                                    self.last_data_update = current_time
                                    
                                    if (current_time - self.ws_last_log_time) > self.ws_log_interval:
                                        self.ws_last_log_time = current_time
                                        # Log merged updates as a single line
                                        Domoticz.Debug(f"Merged updates: {json.dumps(merged_data)}")
                    finally:
                        # Always clear update in progress flag
                        self.update_in_progress = False
                    
                except Exception as e:
                    self.update_in_progress = False  # Make sure flag is cleared
                    Domoticz.Error(f"Error parsing WebSocket data: {str(e)}\nRaw message: {message}")
            
            def on_error(ws, error):
                self.ws_error = str(error)
                Domoticz.Error(f"WebSocket error: {self.ws_error}")
                self.ws_connected = False
                self.ws = None  # Clear the WebSocket instance on error
                
            def on_close(ws, close_status_code, close_msg):
                self.ws_connected = False
                if close_status_code or close_msg:
                    Domoticz.Log(f"WebSocket connection closed: {close_status_code} - {close_msg}")
                else:
                    Domoticz.Log("WebSocket connection closed")
                self.ws = None  # Clear the WebSocket instance on close
                
            def on_open(ws):
                self.ws_connected = True
                self.ws_error = None
                self.ws_last_data = {}  # Reset data on new connection
                self.ws_temp_data = {}  # Reset temporary data
                self.last_complete_update = 0  # Reset update timestamp
                self.last_data_update = 0
                self.update_in_progress = False
                Domoticz.Log("WebSocket connection established")
            
            # Create WebSocket instance
            ws = websocket.WebSocketApp(
                self.ws_url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Store the WebSocket instance
            self.ws = ws
            
            # Start WebSocket in a separate thread
            def run_websocket():
                while True:
                    try:
                        # Check if WebSocket instance is still valid
                        if not self.ws:
                            Domoticz.Log("WebSocket instance no longer exists")
                            break
                            
                        self.ws.run_forever()
                        
                        # Exit conditions
                        if not self.ws_keep_connection:
                            Domoticz.Log("WebSocket connection not being kept alive")
                            break
                        if not self.ws:
                            Domoticz.Log("WebSocket instance has been cleared")
                            break
                            
                        # If we reach here, connection was lost but we want to keep it
                        if self.ws_keep_connection:
                            Domoticz.Log("WebSocket connection lost, waiting before reconnect attempt...")
                            time.sleep(5)  # Wait before reconnecting
                            
                    except Exception as e:
                        Domoticz.Error(f"WebSocket thread error: {str(e)}")
                        if not self.ws_keep_connection:
                            break
                        time.sleep(5)  # Wait before retry
                        
                Domoticz.Log("WebSocket thread ending")
                # Ensure WebSocket instance is cleared
                self.ws = None
                self.ws_connected = False
                self.update_in_progress = False
            
            # Start a new thread only if we don't already have one
            if not self.ws_thread or not self.ws_thread.is_alive():
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
                # Set flags first to prevent reconnection attempts
                self.ws_connected = False
                self.ws_keep_connection = False
                
                # Store reference to current WebSocket
                ws = self.ws
                
                # Check if connection is currently open
                try:
                    if hasattr(ws, 'sock') and ws.sock:
                        ws.close()
                        # Wait for close to complete
                        start_time = time.time()
                        while hasattr(self.ws, 'sock') and self.ws.sock and time.time() - start_time < 5:
                            time.sleep(0.1)
                except:
                    pass  # If any error occurs during close, continue to clearing
                
                # Clear the websocket instance
                self.ws = None
                self.update_in_progress = False
                Domoticz.Log("WebSocket connection closed")
                
            except Exception as e:
                self.update_in_progress = False
                Domoticz.Error(f"Error closing WebSocket: {str(e)}")
    
    def get_state(self, use_websocket=True, keep_connection=False):
        """Get the current state of the EVCC system
        
        Args:
            use_websocket: Whether to try WebSocket first
            keep_connection: If using WebSocket, whether to keep the connection open
                             after getting data (uses more resources but faster updates)
        """
        # Check if we already have WebSocket data
        if self.ws_connected and self.ws_last_data:
            Domoticz.Debug(f"Using cached WebSocket data: {json.dumps(self.ws_last_data)}")
            return self.ws_last_data
        
        # If WebSocket requested and available, try to use it
        if use_websocket and websocket_available:
            if not self.ws_connected:
                # Connect, specifying whether to keep connection open
                self.connect_websocket(keep_connection=keep_connection)
                
                # If connection successful and we have data...
                if self.ws_connected and self.ws_last_data:
                    Domoticz.Debug(f"Using new WebSocket data: {json.dumps(self.ws_last_data)}")
                    return self.ws_last_data
                
                # If one-time connection closed but we got data...
                if not self.ws_connected and not keep_connection and self.ws_last_data:
                    Domoticz.Debug(f"Using one-time WebSocket data: {json.dumps(self.ws_last_data)}")
                    return self.ws_last_data
        
        # Fall back to REST API if WebSocket not available or failed
        try:
            cookies = self.get_cookies()
            
            response = requests.get(f"{self.base_url}/state", cookies=cookies)
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get EVCC state: {response.status_code}")
                return None

            data = response.json()
            
            # Log the REST API response as a single line
            Domoticz.Debug(f"REST API response: {json.dumps(data)}")
            
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

    def get_vehicle_status(self, vehicle_id):
        """Get detailed status for a specific vehicle"""
        try:
            cookies = self.get_cookies()
            response = requests.get(
                f"{self.base_url}/config/devices/vehicle/{vehicle_id}/status",
                cookies=cookies
            )
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get vehicle status: {response.status_code}")
                return None

            data = response.json()
            if "result" in data:
                # Extract values from result
                result = {}
                for key, item in data["result"].items():
                    if isinstance(item, dict) and "value" in item:
                        result[key] = item["value"]
                return result
            return None
                
        except Exception as e:
            Domoticz.Error(f"Error getting vehicle status: {str(e)}")
            return None

    def get_meter_status(self, meter_id):
        """Get detailed status for a specific meter"""
        try:
            cookies = self.get_cookies()
            response = requests.get(
                f"{self.base_url}/config/devices/meter/{meter_id}/status",
                cookies=cookies
            )
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get meter status: {response.status_code}")
                return None

            data = response.json()
            if "result" in data:
                # Extract values from result
                result = {}
                for key, item in data["result"].items():
                    if isinstance(item, dict) and "value" in item:
                        result[key] = item["value"]
                return result
            return None
                
        except Exception as e:
            Domoticz.Error(f"Error getting meter status: {str(e)}")
            return None

    def get_charger_status(self, charger_id):
        """Get detailed status for a specific charger"""
        try:
            cookies = self.get_cookies()
            response = requests.get(
                f"{self.base_url}/config/devices/charger/{charger_id}/status",
                cookies=cookies
            )
            
            if response.status_code != 200:
                Domoticz.Error(f"Failed to get charger status: {response.status_code}")
                return None

            data = response.json()
            if "result" in data:
                # Extract values from result
                result = {}
                for key, item in data["result"].items():
                    if isinstance(item, dict) and "value" in item:
                        result[key] = item["value"]
                return result
            return None
                
        except Exception as e:
            Domoticz.Error(f"Error getting charger status: {str(e)}")
            return None