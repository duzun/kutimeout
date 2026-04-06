#!/usr/bin/env python3
"""
KDE Plasma Timeout Script
-------------------------
This script limits computer usage to a predefined amount of time per day.
Once the time limit is reached, it will automatically log out the user.
@version 0.0.1

Usage:
    kutimeout.py --help
    kutimeout.py [-l MINUTES] [-c CONFIG_FILE] [-g MINUTES] [-w MINUTES] [-t] [-v] [-s]
    kutimeout.py [--time-limit MINUTES] [--config CONFIG_FILE] [--grace-period MINUTES] [--warning-minutes MINUTES] [--track-usage] [--verbose] [--save]
"""

import argparse
import gettext
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Setup translation
APP_NAME = "kutimeout"
LOCALE_DIR = Path(__file__).parent / "locale"
gettext.bindtextdomain(APP_NAME, LOCALE_DIR)
gettext.textdomain(APP_NAME)


def _(message):
    return gettext.gettext(message)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("kutimeout")


class TimeoutManager:
    def __init__(
        self,
        time_limit_minutes=None,
        config_file=None,
        startup_grace_period=1,
        warning_minutes=5,
        track_usage=None,
    ):
        """
        Initialize the timeout manager.

        Args:
            time_limit_minutes: Daily time limit in minutes (from CLI)
            config_file: Path to the configuration file
            startup_grace_period: Grace period in minutes after startup before enforcing logout
            warning_minutes: Minutes before logout to warn the user
            track_usage: Keep running and track usage even if no time limit is set
        """
        self.cli_time_limit = time_limit_minutes
        self.startup_time = datetime.now()
        self.last_update = self.startup_time
        self.warning_shown = False  # Whether the pre-logout warning has been shown
        self.warning_shown_at = None  # When the warning was first shown
        self.screen_locked = False  # Track screen lock state

        # Use default config file if none provided
        if config_file is None:
            self.config_file = Path.home() / ".config" / "kutimeout" / "config.json"
        else:
            self.config_file = Path(config_file)

        # Create config directory if it doesn't exist
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Could not create config directory: {e}")
            sys.exit(1)

        # Load or create config
        self.config = self.load_config()

        config_updated = False

        # Apply CLI overrides if provided
        if self.cli_time_limit is not None:
            if self.config.get("time_limit_minutes") != self.cli_time_limit:
                logger.info(
                    f"Overriding config time limit ({self.config.get('time_limit_minutes')} min) with CLI argument ({self.cli_time_limit} min)"
                )
                self.config["time_limit_minutes"] = self.cli_time_limit
                config_updated = True

        if startup_grace_period is not None:
            if self.config.get("grace_period_minutes") != startup_grace_period:
                logger.info(
                    f"Overriding config grace period ({self.config.get('grace_period_minutes')} min) with CLI argument ({startup_grace_period} min)"
                )
                self.config["grace_period_minutes"] = startup_grace_period
                config_updated = True

        if warning_minutes is not None:
            if self.config.get("warning_minutes") != warning_minutes:
                logger.info(
                    f"Overriding config warning time ({self.config.get('warning_minutes')} min) with CLI argument ({warning_minutes} min)"
                )
                self.config["warning_minutes"] = warning_minutes
                config_updated = True

        if track_usage is not None:
            if self.config.get("track_usage") != track_usage:
                logger.info(
                    f"Overriding config track_usage ({self.config.get('track_usage')}) with CLI argument ({track_usage})"
                )
                self.config["track_usage"] = track_usage
                config_updated = True

        if config_updated:
            self.save_config()

        # Set the effective values from config (falling back to CLI/defaults)
        self.time_limit_minutes = self.config.get(
            "time_limit_minutes", self.cli_time_limit or 0
        )
        self.startup_grace_period = self.config.get(
            "grace_period_minutes", startup_grace_period or 1
        )
        self.warning_minutes = self.config.get("warning_minutes", warning_minutes or 5)
        self.track_usage = self.config.get("track_usage", track_usage or False)

        # Check for missing, 0, or -1 time limit and exit if necessary
        if self.time_limit_minutes <= 0 and not self.track_usage:
            logger.info(
                "Daily time limit not set or disabled (time_limit_minutes <= 0) and track_usage is False. Exiting."
            )
            sys.exit(0)

        # Set up signal handlers for clean shutdown
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

    def load_config(self):
        """Load configuration from file or create default if it doesn't exist."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    return config
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading config: {e}")
                return self.create_default_config()
        else:
            return self.create_default_config()

    def create_default_config(self):
        """Create a default configuration."""
        today = datetime.now().strftime("%Y-%m-%d")
        config = {
            "time_limit_minutes": self.cli_time_limit
            if self.cli_time_limit is not None
            else 0,
            "grace_period_minutes": 1,
            "warning_minutes": 5,
            "track_usage": False,
            "usage": {today: 0},  # Minutes used today
            "last_update": datetime.now().isoformat(),
        }
        self.save_config(config)
        return config

    def save_config(self, config=None):
        """Save the current configuration to file."""
        if config is None:
            config = self.config

        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving config: {e}")

    def is_screen_locked(self):
        """Check if the KDE screen is locked."""
        try:
            result = subprocess.run(
                [
                    "qdbus",
                    "org.freedesktop.ScreenSaver",
                    "/ScreenSaver",
                    "org.freedesktop.ScreenSaver.GetActive",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            locked = result.stdout.strip().lower() == "true"
            if locked != self.screen_locked:
                self.screen_locked = locked
                logger.info(f"Screen {'locked' if locked else 'unlocked'}")
            return locked
        except (subprocess.SubprocessError, OSError) as e:
            logger.debug(f"Could not check screen lock state: {e}")
            return False

    def notify_user(self, title, message, urgency="critical", timeout_ms=30000):
        """Show a desktop notification to the user."""
        try:
            subprocess.run(
                [
                    "notify-send",
                    "-u",
                    urgency,
                    "-t",
                    str(timeout_ms),
                    "-a",
                    "KUTimeout",
                    title,
                    message,
                ],
                check=False,
                timeout=5,
            )
        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Could not send notification: {e}")

    def update_usage(self):
        """Update the usage time in the configuration. Skips counting when screen is locked."""
        now = datetime.now()
        locked = self.is_screen_locked()

        # First read the current configuration from file to get any external changes
        current_config = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    current_config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading current config: {e}")
                # If we can't read the current config, use the in-memory one
                current_config = self.config
        else:
            current_config = self.config

        today = now.strftime("%Y-%m-%d")

        # Ensure 'usage' exists in both configs
        if "usage" not in current_config:
            current_config["usage"] = {}

        # Initialize today's usage if not present in current config
        if today not in current_config["usage"]:
            current_config["usage"][today] = 0

        # Calculate time elapsed since last update
        elapsed_minutes = (now - self.last_update).total_seconds() / 60
        self.last_update = now

        # Only count time when the screen is NOT locked
        if not locked:
            current_config["usage"][today] += elapsed_minutes
        else:
            logger.debug(f"Screen locked — not counting {elapsed_minutes:.1f} min")

        current_config["last_update"] = now.isoformat()

        # Update in-memory config with the updated values
        self.config = current_config

        # Save updated config
        self.save_config(current_config)

        return self.config["usage"][today]

    def get_remaining_minutes(self):
        """Get the remaining minutes for today."""
        today = datetime.now().strftime("%Y-%m-%d")
        current_usage = self.config.get("usage", {}).get(today, 0)
        return (
            self.config.get("time_limit_minutes", self.time_limit_minutes)
            - current_usage
        )

    def check_time_limit(self):
        """Check if the time limit has been reached and handle warnings.

        Returns True only when it's time to actually log out (after warning period).
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Initialize today's usage if not present
        if today not in self.config.get("usage", {}):
            if "usage" not in self.config:
                self.config["usage"] = {}
            self.config["usage"][today] = 0
            self.save_config()
            return False

        remaining = self.get_remaining_minutes()

        # If we're in the startup grace period, don't enforce the limit yet
        time_since_startup = (datetime.now() - self.startup_time).total_seconds() / 60
        if time_since_startup < self.startup_grace_period:
            if remaining <= 0:
                logger.info(
                    f"Time limit reached but within startup grace period ({time_since_startup:.1f}/{self.startup_grace_period} min)."
                )
            return False

        # Show warning when approaching the limit
        if remaining <= self.warning_minutes and not self.warning_shown:
            self.warning_shown = True
            self.warning_shown_at = datetime.now()

            # The warning period is part of the main time limit, but we always
            # ensure the user gets the full warning duration.
            logout_in_minutes = max(remaining, self.warning_minutes)

            msg = _(
                "Your daily time limit of {limit} min is approaching.\n"
                "You will be logged out in approximately {remaining:.0f} minutes."
            ).format(limit=self.time_limit_minutes, remaining=logout_in_minutes)

            logger.warning(msg)
            self.notify_user(_("Time Limit Warning"), msg)
            return False

        # Only proceed to logout after both:
        # 1. The daily limit has been reached (remaining <= 0)
        # 2. The full warning period has elapsed
        if self.warning_shown:
            warning_elapsed = (
                datetime.now() - self.warning_shown_at
            ).total_seconds() / 60
            if remaining <= 0 and warning_elapsed >= self.warning_minutes:
                return True

            if remaining <= 0:
                mins_left = self.warning_minutes - warning_elapsed
                # Use debug to avoid log spam, the main loop already prints status
                logger.debug(
                    f"Logout in {mins_left:.1f} min (waiting for warning period)"
                )

        return False

    def logout_user(self):
        """Log out the current KDE Plasma session."""
        try:
            # Using qdbus to trigger KDE logout
            subprocess.run(
                ["qdbus", "org.kde.Shutdown", "/Shutdown", "logout"], check=True
            )

            logger.info("Logging out user due to time limit reached.")
        except subprocess.SubprocessError as e:
            logger.error(f"Error logging out: {e}")
            # Fallback method
            try:
                subprocess.run(
                    [
                        "qdbus",
                        "org.kde.ksmserver",
                        "/KSMServer",
                        "logout",
                        "0",
                        "3",
                        "3",
                    ],
                    check=True,
                )
            except subprocess.SubprocessError as e2:
                logger.error(f"Fallback logout failed: {e2}")

    def handle_signal(self, signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.update_usage()
        sys.exit(0)

    def run(self):
        """Main execution loop."""
        time_limit = self.config.get("time_limit_minutes", self.time_limit_minutes)
        logger.info(
            f"Starting KDE Timeout Manager (limit: {time_limit} min/day, "
            f"warning: {self.warning_minutes} min, grace: {self.startup_grace_period} min)"
        )

        try:
            while True:
                # Update usage time (skips counting when screen is locked)
                current_usage = self.update_usage()

                # Check if time limit is reached (handles warnings + grace)
                if self.check_time_limit():
                    logger.info(f"Time limit of {time_limit} minutes reached.")
                    logger.info(f"Total usage today: {current_usage:.2f} minutes")
                    self.notify_user(
                        _("Logging Out"),
                        _("Your daily time limit has been reached. Logging out now."),
                    )
                    time.sleep(5)  # Brief pause so user can see the notification
                    self.logout_user()
                    break

                # Calculate and display remaining time
                remaining = self.get_remaining_minutes()
                logger.info(
                    f"Time used: {current_usage:.1f} min. Remaining: {remaining:.1f} min"
                )

                # Poll more frequently when close to limit or during warning period
                if self.warning_shown:
                    time.sleep(15)
                elif remaining <= self.warning_minutes + 1:
                    time.sleep(30)
                else:
                    time.sleep(60)

        except KeyboardInterrupt:
            logger.info("Manually interrupted.")
            self.update_usage()
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            self.update_usage()

        logger.info("Timeout manager stopped.")


def main():
    """Parse command line arguments and start the timeout manager."""
    parser = argparse.ArgumentParser(
        description=_("KDE Plasma session timeout manager")
    )
    parser.add_argument(
        "-l",
        "--time-limit",
        type=int,
        default=None,
        help=_(
            "Daily time limit in minutes. Use 0 to disable. (default: 0 or from config)"
        ),
    )
    parser.add_argument(
        "-g",
        "--grace-period",
        type=int,
        default=1,
        help=_(
            "Minimum minutes to wait after startup before logging out, even if the limit is exceeded (default: 1)"
        ),
    )
    parser.add_argument(
        "-w",
        "--warning-minutes",
        type=int,
        default=5,
        help=_("Minutes before logout to show a warning notification (default: 5)"),
    )
    parser.add_argument(
        "-t",
        "--track-usage",
        action="store_true",
        default=None,
        help=_("Keep the service running and track usage even if no time limit is set"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=_("Enable detailed logging for troubleshooting"),
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help=_(
            "Path to the configuration file (default: ~/.config/kutimeout/config.json)"
        ),
    )
    parser.add_argument(
        "-s",
        "--save",
        action="store_true",
        help=_(
            "Update the configuration file with the provided CLI arguments and exit immediately"
        ),
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Multi-user consideration: warn if running as root
    if os.geteuid() == 0:
        logger.warning(
            "Running as root! This script is intended to run as a normal user to manage their session."
        )

    # Create and run the timeout manager
    timeout_manager = TimeoutManager(
        time_limit_minutes=args.time_limit,
        config_file=args.config,
        startup_grace_period=args.grace_period,
        warning_minutes=args.warning_minutes,
        track_usage=args.track_usage,
    )

    if args.save:
        logger.info(f"Configuration saved to {timeout_manager.config_file}. Exiting.")
        sys.exit(0)

    timeout_manager.run()


if __name__ == "__main__":
    main()
