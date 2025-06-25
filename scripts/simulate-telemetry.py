#!/usr/bin/env python3
"""
Telemetry Data Simulation Script for Smart Home Energy Monitoring

This script generates 24 hours of one-minute interval telemetry data for 5 devices
and sends it to the telemetry service API.
"""

import requests
import random
import time
import uuid
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "http://localhost:8000/api/v1/telemetry"
AUTH_URL = "http://localhost:8000/api/v1/auth"

# Device configurations with realistic power consumption patterns
DEVICE_CONFIGS = {
    "fridge-001": {
        "name": "Kitchen Refrigerator",
        "type": "appliance",
        "base_power": 150,  # Base power consumption in watts
        "variation": 50,    # Power variation range
        "cycle_hours": 4,   # Compressor cycle every 4 hours
        "cycle_duration": 0.5  # Cycle lasts 30 minutes
    },
    "ac-001": {
        "name": "Living Room AC",
        "type": "hvac",
        "base_power": 2000,
        "variation": 500,
        "cycle_hours": 2,
        "cycle_duration": 1.5,
        "seasonal_factor": 1.2  # Higher in summer
    },
    "washer-001": {
        "name": "Washing Machine",
        "type": "appliance",
        "base_power": 500,
        "variation": 200,
        "cycle_hours": 8,  # Runs every 8 hours on average
        "cycle_duration": 1.0,  # 1 hour cycle
        "standby_power": 5  # Standby power when not running
    },
    "tv-001": {
        "name": "Living Room TV",
        "type": "electronics",
        "base_power": 120,
        "variation": 30,
        "usage_start": 18,  # Typically used from 6 PM
        "usage_end": 23,    # Until 11 PM
        "standby_power": 2
    },
    "lights-001": {
        "name": "Bedroom Lights",
        "type": "lighting",
        "base_power": 60,
        "variation": 20,
        "usage_start": 19,  # Evening usage
        "usage_end": 22,
        "morning_start": 7,  # Morning usage
        "morning_end": 8
    }
}


class TelemetrySimulator:
    """Telemetry data simulator"""
    
    def __init__(self, base_url: str = BASE_URL, auth_url: str = AUTH_URL):
        self.base_url = base_url
        self.auth_url = auth_url
        self.session = requests.Session()
        self.access_token = None
        
    def authenticate(self, email: str = "user@smarthome.com", password: str = "password123") -> bool:
        """Authenticate with the auth service"""
        try:
            # Try to login first
            login_data = {
                "email": email,
                "password": password
            }
            
            response = self.session.post(f"{self.auth_url}/login", json=login_data)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.access_token}"
                })
                logger.info(f"Successfully authenticated as {email}")
                return True
            elif response.status_code == 401:
                # User doesn't exist or wrong password, try to register
                logger.info("Login failed, attempting to register new user...")
                return self.register_user(email, password)
            else:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    def register_user(self, email: str, password: str, name: str = "Test User") -> bool:
        """Register a new user"""
        try:
            register_data = {
                "email": email,
                "password": password,
                "name": name
            }
            
            response = self.session.post(f"{self.auth_url}/register", json=register_data)
            
            if response.status_code == 201:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.access_token}"
                })
                logger.info(f"Successfully registered and authenticated as {email}")
                return True
            else:
                logger.error(f"Registration failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    def calculate_device_power(self, device_id: str, timestamp: datetime) -> float:
        """Calculate realistic power consumption for a device at given time"""
        config = DEVICE_CONFIGS.get(device_id, {})
        if not config:
            return random.uniform(5, 250)  # Default random power
        
        base_power = config["base_power"]
        variation = config["variation"]
        hour = timestamp.hour
        minute = timestamp.minute
        
        # Start with base power
        power = base_power
        
        # Apply device-specific logic
        if device_id == "fridge-001":
            # Refrigerator cycles on/off
            cycle_position = (hour % config["cycle_hours"]) + (minute / 60)
            if cycle_position < config["cycle_duration"]:
                power *= 1.3  # Compressor running
            else:
                power *= 0.7  # Compressor off
                
        elif device_id == "ac-001":
            # AC usage varies by time of day
            if 10 <= hour <= 22:  # Daytime usage
                power *= 1.2
            else:
                power *= 0.3  # Night/early morning
            
            # Cycling behavior
            cycle_position = (hour % config["cycle_hours"]) + (minute / 60)
            if cycle_position < config["cycle_duration"]:
                power *= 1.1
            else:
                power *= 0.8
                
        elif device_id == "washer-001":
            # Washing machine runs in cycles
            cycle_position = (hour % config["cycle_hours"]) + (minute / 60)
            if cycle_position < config["cycle_duration"]:
                # Running a wash cycle
                cycle_phase = (minute % 60) / 60
                if cycle_phase < 0.2:  # Fill phase
                    power *= 0.3
                elif cycle_phase < 0.6:  # Wash phase
                    power *= 1.2
                elif cycle_phase < 0.8:  # Rinse phase
                    power *= 0.8
                else:  # Spin phase
                    power *= 1.5
            else:
                power = config.get("standby_power", 5)
                
        elif device_id == "tv-001":
            # TV usage in evening
            if config["usage_start"] <= hour <= config["usage_end"]:
                power = base_power + random.uniform(-variation/2, variation/2)
            else:
                power = config.get("standby_power", 2)
                
        elif device_id == "lights-001":
            # Lights used in evening and morning
            if (config["usage_start"] <= hour <= config["usage_end"] or 
                config["morning_start"] <= hour <= config["morning_end"]):
                power = base_power + random.uniform(-variation/2, variation/2)
            else:
                power = 0  # Lights off
        
        # Add some random variation
        power += random.uniform(-variation * 0.2, variation * 0.2)
        
        # Ensure power is not negative
        return max(0, round(power, 2))
    
    def send_telemetry(self, device_id: str, timestamp: datetime, energy_watts: float) -> bool:
        """Send telemetry data to the API"""
        try:
            payload = {
                "device_id": device_id,
                "timestamp": timestamp.isoformat() + "Z",
                "energy_watts": energy_watts
            }
            
            response = self.session.post(self.base_url, json=payload)
            
            if response.status_code in [200, 201]:
                return True
            else:
                logger.error(f"Failed to send telemetry: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending telemetry: {e}")
            return False
    
    def simulate_24_hours(self, start_time: datetime = None, delay: float = 0.01) -> Dict[str, Any]:
        """Simulate 24 hours of telemetry data"""
        if start_time is None:
            start_time = datetime.utcnow().replace( second=0, microsecond=0)
        
        devices = list(DEVICE_CONFIGS.keys())
        total_points = 24 * 60 * len(devices)  # 24 hours * 60 minutes * 5 devices
        successful_sends = 0
        failed_sends = 0
        
        logger.info(f"Starting simulation for {len(devices)} devices over 24 hours")
        logger.info(f"Total data points to generate: {total_points}")
        logger.info(f"Devices: {', '.join(devices)}")
        
        start_simulation = time.time()
        
        # Generate data for each minute of 24 hours
        for minute_offset in range(24 * 60):  # 1440 minutes in 24 hours
            timestamp = start_time + timedelta(minutes=minute_offset)
            
            # Generate data for each device
            for device_id in devices:
                energy_watts = self.calculate_device_power(device_id, timestamp)
                
                if self.send_telemetry(device_id, timestamp, energy_watts):
                    successful_sends += 1
                else:
                    failed_sends += 1
                
                # Small delay to avoid overwhelming the API
                if delay > 0:
                    time.sleep(delay)
            
            # Progress update every hour
            if (minute_offset + 1) % 60 == 0:
                hours_completed = (minute_offset + 1) // 60
                logger.info(f"Completed {hours_completed}/24 hours - "
                          f"Success: {successful_sends}, Failed: {failed_sends}")
        
        end_simulation = time.time()
        duration = end_simulation - start_simulation
        
        results = {
            "total_points": total_points,
            "successful_sends": successful_sends,
            "failed_sends": failed_sends,
            "success_rate": (successful_sends / total_points) * 100 if total_points > 0 else 0,
            "duration_seconds": duration,
            "points_per_second": total_points / duration if duration > 0 else 0
        }
        
        logger.info("Simulation completed!")
        logger.info(f"Results: {json.dumps(results, indent=2)}")
        
        return results


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Smart Home Telemetry Simulator")
    parser.add_argument("--base-url", default=BASE_URL, help="Telemetry service base URL")
    parser.add_argument("--auth-url", default=AUTH_URL, help="Auth service base URL")
    parser.add_argument("--email", default="tadekdev@gmail.com", help="User email for authentication")
    parser.add_argument("--password", default="M@ther114", help="User password")
    parser.add_argument("--delay", type=float, default=5, help="Delay between requests (seconds)")
    parser.add_argument("--start-time", help="Start time (ISO format, defaults to today midnight)")
    
    args = parser.parse_args()
    
    # Parse start time if provided
    start_time = None
    if args.start_time:
        try:
            start_time = datetime.fromisoformat(args.start_time.replace('Z', '+00:00'))
        except ValueError:
            logger.error("Invalid start time format. Use ISO format (e.g., 2024-01-01T00:00:00)")
            return
    
    # Create simulator
    simulator = TelemetrySimulator(args.base_url, args.auth_url)
    
    # Authenticate
    if not simulator.authenticate(args.email, args.password):
        logger.error("Authentication failed. Cannot proceed with simulation.")
        return
    
    # Run simulation
    try:
        results = simulator.simulate_24_hours(start_time, args.delay)
        
        if results["success_rate"] < 90:
            logger.warning(f"Low success rate: {results['success_rate']:.1f}%")
        else:
            logger.info(f"Simulation successful with {results['success_rate']:.1f}% success rate")
            
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
    except Exception as e:
        logger.error(f"Simulation failed: {e}")


if __name__ == "__main__":
    main()
