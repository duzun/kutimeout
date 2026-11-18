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
_ = gettext.gettext

logger = logging.getLogger("kutimeout")

DEFAULTS = {
    "time_limit_minutes": 0,
    "grace_period_minutes": 1,
    "warning_minutes": 5,
    "track_usage": False,
}


def _read_json(path):
    """Return the dict stored in `path`, or None if missing or unreadable."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error loading {path}: {e}")
        return None


def _write_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logger.error(f"Error saving {path}: {e}")


class TimeoutManager:
    # Maximum allowed gap between updates in minutes before assuming a time jump (suspend/clock sync)
    MAX_POLL_GAP_MINUTES = 5.0

    def __init__(
        self,
        time_limit_minutes=None,
        config_file=None,
        startup_grace_period=None,
        warning_minutes=None,
        track_usage=None,
    ):
        """
        Initialize the timeout manager. Arguments left as None come from the
        config file (or defaults); given values override and are saved to it.

        Args:
            time_limit_minutes: Daily limit in minutes (0 = off, -1 = track only)
            config_file: Path to the configuration file
            startup_grace_period: Minutes after startup before enforcing logout
            warning_minutes: Minutes before logout to warn the user
            track_usage: Keep running and track usage even if no time limit is set
        """
        self.startup_time = datetime.now()
        self.last_update = self.startup_time
        self.warning_shown = False  # Whether the pre-logout warning has been shown
        self.warning_shown_at = None  # When the warning was first shown
        self.screen_locked = False

        if config_file is None:
            config_file = Path.home() / ".config" / "kutimeout" / "config.json"
        self.config_file = Path(config_file)
        # Usage file is stored next to the config file
        self.usage_file = self.config_file.parent / "usage.json"

        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Could not create config directory: {e}")
            sys.exit(1)

        file_config = _read_json(self.config_file)
        changed = file_config is None
        file_config = file_config or {}
        if "usage" in file_config or "last_update" in file_config:
            self.migrate_usage(file_config)
            changed = True
        self.config = {**DEFAULTS, **file_config}

        overrides = {
            "time_limit_minutes": time_limit_minutes,
            "grace_period_minutes": startup_grace_period,
            "warning_minutes": warning_minutes,
            "track_usage": track_usage,
        }
        for key, value in overrides.items():
            if value is not None and self.config[key] != value:
                logger.info(
                    f"Overriding config {key} ({self.config[key]}) with CLI argument ({value})"
                )
                self.config[key] = value
                changed = True
        if changed:
            _write_json(self.config_file, self.config)

        self.time_limit_minutes = self.config["time_limit_minutes"]
        self.startup_grace_period = self.config["grace_period_minutes"]
        self.warning_minutes = self.config["warning_minutes"]
        self.track_usage = self.config["track_usage"]

        self.usage_data = _read_json(self.usage_file) or {}
        self.usage_data.setdefault("usage", {})
        self.usage_data.setdefault("last_update", datetime.now().isoformat())

    @property
    def enabled(self):
        """False when there is nothing to do: no limit and no usage tracking."""
        return self.time_limit_minutes != 0 or self.track_usage

    def migrate_usage(self, config):
        """Move usage data from a legacy config dict (in place) to usage.json."""
        logger.info("Migrating usage metrics from config.json to usage.json...")
        usage_data = _read_json(self.usage_file) or {}
        usage = usage_data.setdefault("usage", {})
        for date, val in config.pop("usage", {}).items():
            usage.setdefault(date, val)
        if "last_update" in config:
            usage_data.setdefault("last_update", config.pop("last_update"))
        _write_json(self.usage_file, usage_data)

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
        """Add elapsed time to today's usage (unless locked) and return today's minutes."""
        now = datetime.now()
        locked = self.is_screen_locked()

        # Re-read the file to honor external changes
        data = _read_json(self.usage_file) or self.usage_data
        usage = data.setdefault("usage", {})
        today = now.strftime("%Y-%m-%d")
        usage.setdefault(today, 0)

        elapsed_minutes = (now - self.last_update).total_seconds() / 60
        self.last_update = now

        # Detect suspend/wake or clock changes (including backwards)
        if elapsed_minutes > self.MAX_POLL_GAP_MINUTES or elapsed_minutes < 0:
            logger.info(
                f"Time jump/clock change detected ({elapsed_minutes:.1f} min). "
                f"Assuming system suspend or clock sync; ignoring this interval."
            )
            elapsed_minutes = 0.0

        if not locked:
            usage[today] += elapsed_minutes
        else:
            logger.debug(f"Screen locked — not counting {elapsed_minutes:.1f} min")

        data["last_update"] = now.isoformat()
        self.usage_data = data
        _write_json(self.usage_file, data)
        return usage[today]

    def get_remaining_minutes(self):
        """Get the remaining minutes for today."""
        today = datetime.now().strftime("%Y-%m-%d")
        used = self.usage_data["usage"].get(today, 0)
        return self.time_limit_minutes - used

    def check_time_limit(self):
        """Check if the time limit has been reached and handle warnings.

        Returns True only when it's time to actually log out (after warning period).
        """
        # Limit <= 0 never warns or logs out (-1 / 0 with tracking = track only).
        if self.time_limit_minutes <= 0:
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

        # Log out only after the limit is reached AND the full warning period elapsed
        if self.warning_shown and remaining <= 0:
            warning_elapsed = (
                datetime.now() - self.warning_shown_at
            ).total_seconds() / 60
            if warning_elapsed >= self.warning_minutes:
                return True
            logger.debug(
                f"Logout in {self.warning_minutes - warning_elapsed:.1f} min (waiting for warning period)"
            )

        return False

    def logout_user(self):
        """Log out the current KDE Plasma session."""
        try:
            subprocess.run(
                ["qdbus", "org.kde.Shutdown", "/Shutdown", "logout"], check=True
            )
            logger.info("Logging out user due to time limit reached.")
        except (subprocess.SubprocessError, OSError) as e:
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
            except (subprocess.SubprocessError, OSError) as e2:
                logger.error(f"Fallback logout failed: {e2}")

    def run(self):
        """Main execution loop."""
        limit = self.time_limit_minutes
        logger.info(
            f"Starting KDE Timeout Manager (limit: {limit} min/day, "
            f"warning: {self.warning_minutes} min, grace: {self.startup_grace_period} min)"
        )

        # Turn SIGTERM into a normal exit so the usage is saved in `finally`
        signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

        try:
            while True:
                current_usage = self.update_usage()

                if self.check_time_limit():
                    logger.info(f"Time limit of {limit} minutes reached.")
                    logger.info(f"Total usage today: {current_usage:.2f} minutes")
                    self.notify_user(
                        _("Logging Out"),
                        _("Your daily time limit has been reached. Logging out now."),
                    )
                    time.sleep(5)  # Brief pause so user can see the notification
                    self.logout_user()
                    break

                if limit <= 0:
                    logger.info(
                        f"Time used: {current_usage:.1f} min. (No limit enforced)"
                    )
                    remaining = None
                else:
                    remaining = limit - current_usage
                    logger.info(
                        f"Time used: {current_usage:.1f} min. Remaining: {remaining:.1f} min"
                    )

                # Poll more frequently when close to limit or during warning period
                if self.warning_shown:
                    time.sleep(15)
                elif remaining is not None and remaining <= self.warning_minutes + 1:
                    time.sleep(30)
                else:
                    time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Manually interrupted.")
        finally:
            self.update_usage()

        logger.info("Timeout manager stopped.")


def main(argv=None):
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
            "Daily time limit in minutes. Use 0 to disable, or -1 to track time without logging out or notifications. (default: 0 or from config)"
        ),
    )
    parser.add_argument(
        "-g",
        "--grace-period",
        type=int,
        default=None,
        help=_(
            "Minimum minutes to wait after startup before logging out, even if the limit is exceeded (default: 1 or from config)"
        ),
    )
    parser.add_argument(
        "-w",
        "--warning-minutes",
        type=int,
        default=None,
        help=_(
            "Minutes before logout to show a warning notification (default: 5 or from config)"
        ),
    )
    parser.add_argument(
        "-t",
        "--track-usage",
        action=argparse.BooleanOptionalAction,
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

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Multi-user consideration: warn if running as root
    if os.geteuid() == 0:
        logger.warning(
            "Running as root! This script is intended to run as a normal user to manage their session."
        )

    manager = TimeoutManager(
        time_limit_minutes=args.time_limit,
        config_file=args.config,
        startup_grace_period=args.grace_period,
        warning_minutes=args.warning_minutes,
        track_usage=args.track_usage,
    )

    if args.save:
        logger.info(f"Configuration saved to {manager.config_file}. Exiting.")
        sys.exit(0)

    if not manager.enabled:
        logger.info(
            "Daily time limit not set (time_limit_minutes == 0) and track_usage is False. Exiting."
        )
        sys.exit(0)

    manager.run()


if __name__ == "__main__":
    main()
