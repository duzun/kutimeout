#!/usr/bin/env python3
"""
KDE Plasma Timeout Script
-------------------------
This script limits computer usage to a predefined amount of time per day.
Once the time limit is reached, it will automatically log out the user.

Usage:
    timeout_kde.py [--time-limit MINUTES] [--config CONFIG_FILE]
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


class TimeoutManager:
    def __init__(self, time_limit_minutes=60, config_file=None, startup_grace_period=1):
        """
        Initialize the timeout manager.
        
        Args:
            time_limit_minutes: Daily time limit in minutes
            config_file: Path to the configuration file
            startup_grace_period: Grace period in minutes after startup before enforcing logout
        """
        self.time_limit_minutes = time_limit_minutes
        self.startup_time = datetime.now()
        self.last_update = self.startup_time
        self.startup_grace_period = startup_grace_period  # Grace period in minutes
        
        # Use default config file if none provided
        if config_file is None:
            self.config_file = Path.home() / ".config" / "timeout_kde" / "config.json"
        else:
            self.config_file = Path(config_file)
            
        # Create config directory if it doesn't exist
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load or create config
        self.config = self.load_config()
        
        # Set up signal handlers for clean shutdown
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)
        
    def load_config(self):
        """Load configuration from file or create default if it doesn't exist."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config: {e}")
                return self.create_default_config()
        else:
            return self.create_default_config()
    
    def create_default_config(self):
        """Create a default configuration."""
        today = datetime.now().strftime("%Y-%m-%d")
        config = {
            "time_limit_minutes": self.time_limit_minutes,
            "usage": {
                today: 0  # Minutes used today
            },
            "last_update": datetime.now().isoformat()
        }
        self.save_config(config)
        return config
    
    def save_config(self, config=None):
        """Save the current configuration to file."""
        if config is None:
            config = self.config
            
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            print(f"Error saving config: {e}")
    
    def update_usage(self):
        """Update the usage time in the configuration."""
        # First read the current configuration from file to get any external changes
        current_config = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    current_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading current config: {e}")
                # If we can't read the current config, use the in-memory one
                current_config = self.config
        else:
            current_config = self.config
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Ensure 'usage' exists in both configs
        if "usage" not in current_config:
            current_config["usage"] = {}

        # Initialize today's usage if not present in current config
        if today not in current_config["usage"]:
            current_config["usage"][today] = 0

        # Calculate time elapsed since last update using in-memory config
        last_update = self.last_update
        now = datetime.now()
        elapsed_minutes = (now - last_update).total_seconds() / 60

        # Update today's usage in current config
        current_config["usage"][today] += elapsed_minutes
        current_config["last_update"] = now.isoformat()
        self.last_update = now

        # Update in-memory config with the updated values
        self.config = current_config

        # Save updated config
        self.save_config(current_config)
        
        return self.config["usage"][today]
    
    def check_time_limit(self):
        """Check if the time limit has been reached."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Initialize today's usage if not present
        if today not in self.config["usage"]:
            self.config["usage"] = {today: 0}
            self.save_config()
            return False
            
        # Get current usage
        current_usage = self.config["usage"][today]
        
        # Check if time limit is reached
        time_limit_reached = current_usage >= self.config["time_limit_minutes"]
        
        # If we're in the startup grace period, don't enforce the limit yet
        if time_limit_reached:
            time_since_startup = (datetime.now() - self.startup_time).total_seconds() / 60
            if time_since_startup < self.startup_grace_period:
                print(f"Time limit reached but within startup grace period ({time_since_startup:.1f}/{self.startup_grace_period} minutes). Allowing login to complete.")
                return False
                
        return time_limit_reached
    
    def logout_user(self):
        """Log out the current KDE Plasma session."""
        try:
            # Using qdbus to trigger KDE logout
            subprocess.run(["qdbus", "org.kde.Shutdown", "/Shutdown", "logout"], 
                          check=True)

            print("Logging out user due to time limit reached.")
        except subprocess.SubprocessError as e:
            print(f"Error logging out: {e}")
            # Fallback method
            try:
                subprocess.run(["qdbus", "org.kde.ksmserver", "/KSMServer", "logout", "0", "3", "3"], 
                          check=True)

                # subprocess.run(["loginctl", "terminate-user", os.environ.get("USER", "")], check=True)
            except subprocess.SubprocessError as e2:
                print(f"Fallback logout failed: {e2}")
    
    def handle_signal(self, signum, frame):
        """Handle termination signals gracefully."""
        print(f"Received signal {signum}, shutting down...")
        self.update_usage()
        sys.exit(0)
    
    def run(self):
        """Main execution loop."""
        print(f"Starting KDE Timeout Manager (limit: {self.config['time_limit_minutes']} minutes per day, startup grace period: {self.startup_grace_period} minutes)")
        
        try:
            while True:
                # Update usage time
                current_usage = self.update_usage()
                
                # Check if time limit is reached
                if self.check_time_limit():
                    print(f"Time limit of {self.config['time_limit_minutes']} minutes reached.")
                    print(f"Total usage today: {current_usage:.2f} minutes")
                    self.logout_user()
                    break
                
                # Calculate and display remaining time
                remaining = self.config["time_limit_minutes"] - current_usage
                print(f"Time used today: {current_usage:.2f} minutes. Remaining: {remaining:.2f} minutes")
                
                # Sleep for a while before checking again (1 minute)
                time.sleep(60)
                
        except KeyboardInterrupt:
            print("Manually interrupted.")
            self.update_usage()
        except Exception as e:
            print(f"Error: {e}")
            self.update_usage()
        
        print("Timeout manager stopped.")


def main():
    """Parse command line arguments and start the timeout manager."""
    parser = argparse.ArgumentParser(description="KDE Plasma session timeout manager")
    parser.add_argument("--time-limit", type=int, default=60,
                        help="Daily time limit in minutes (default: 60)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to configuration file")
    parser.add_argument("--grace-period", type=int, default=1,
                        help="Grace period in minutes after startup before enforcing logout (default: 1)")
    
    args = parser.parse_args()
    
    # Create and run the timeout manager
    timeout_manager = TimeoutManager(
        time_limit_minutes=args.time_limit,
        config_file=args.config,
        startup_grace_period=args.grace_period
    )
    
    timeout_manager.run()


if __name__ == "__main__":
    main()
