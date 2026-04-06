import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Import the class (add current dir to path if needed)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from kutimeout import TimeoutManager


class TestTimeoutManager(unittest.TestCase):
    def setUp(self):
        """Setup a temporary config file for testing."""
        self.temp_config = Path("/tmp/test_kutimeout_config.json")
        if self.temp_config.exists():
            self.temp_config.unlink()

    def tearDown(self):
        """Cleanup the temporary config file."""
        if self.temp_config.exists():
            self.temp_config.unlink()

    @patch("subprocess.run")
    def test_initialization(self, mock_run):
        """Test default initialization and config creation."""
        tm = TimeoutManager(time_limit_minutes=60, config_file=self.temp_config)
        self.assertEqual(tm.time_limit_minutes, 60)
        self.assertTrue(self.temp_config.exists())
        with open(self.temp_config, "r") as f:
            config = json.load(f)
            self.assertEqual(config["time_limit_minutes"], 60)

    @patch("subprocess.run")
    def test_exit_on_zero_limit(self, mock_run):
        """Test that the manager exits when the time limit is 0 or not set."""
        with self.assertRaises(SystemExit):
            TimeoutManager(time_limit_minutes=0, config_file=self.temp_config)

        if self.temp_config.exists():
            self.temp_config.unlink()

        with self.assertRaises(SystemExit):
            TimeoutManager(time_limit_minutes=-1, config_file=self.temp_config)

    @patch("subprocess.run")
    def test_cli_override(self, mock_run):
        """Test that CLI arguments override the config file."""
        # Create an existing config with 30 minutes
        with open(self.temp_config, "w") as f:
            json.dump({"time_limit_minutes": 30, "usage": {}}, f)

        # Initialize with 120 minutes via CLI
        tm = TimeoutManager(time_limit_minutes=120, config_file=self.temp_config)
        self.assertEqual(tm.time_limit_minutes, 120)

        # Verify config file was updated
        with open(self.temp_config, "r") as f:
            config = json.load(f)
            self.assertEqual(config["time_limit_minutes"], 120)

    @patch("subprocess.run")
    def test_update_usage_not_locked(self, mock_run):
        """Test usage tracking when screen is NOT locked."""
        # Mock qdbus screen lock check to return false
        mock_run.return_value.stdout = "false"

        tm = TimeoutManager(time_limit_minutes=60, config_file=self.temp_config)

        # Manually manipulate last_update to simulate 10 minutes passing
        tm.last_update = datetime.now() - timedelta(minutes=10)

        usage = tm.update_usage()
        # Should be roughly 10 minutes (using almostEqual due to slight timing diffs)
        self.assertAlmostEqual(usage, 10.0, places=1)

    @patch("subprocess.run")
    def test_update_usage_locked(self, mock_run):
        """Test that usage is NOT counted when screen is locked."""
        # Mock qdbus screen lock check to return true
        mock_run.return_value.stdout = "true"

        tm = TimeoutManager(time_limit_minutes=60, config_file=self.temp_config)

        # Simulating 10 minutes passing while screen is locked
        tm.last_update = datetime.now() - timedelta(minutes=10)

        usage = tm.update_usage()
        self.assertEqual(usage, 0.0)

    @patch("subprocess.run")
    def test_warning_logic(self, mock_run):
        """Test that the warning is triggered exactly 5 minutes before the limit."""
        tm = TimeoutManager(
            time_limit_minutes=60, config_file=self.temp_config, startup_grace_period=0
        )

        # Simulate usage at 54.9 minutes (5.1 minutes left, no warning yet)
        today = datetime.now().strftime("%Y-%m-%d")
        tm.config["usage"][today] = 54.9
        self.assertFalse(tm.check_time_limit())
        self.assertFalse(tm.warning_shown)

        # Simulate usage at 55.1 minutes (4.9 minutes left, warning should trigger)
        tm.config["usage"][today] = 55.1
        res = tm.check_time_limit()

        # check_time_limit should return False (it's only True when logout is immediate)
        self.assertFalse(res)
        self.assertTrue(tm.warning_shown)
        self.assertIsNotNone(tm.warning_shown_at)

        # Verify notification was "sent" (mocked)
        mock_run.assert_any_call(
            [
                "notify-send",
                "-u",
                "critical",
                "-t",
                "30000",
                "-a",
                "KUTimeout",
                unittest.mock.ANY,
                unittest.mock.ANY,
            ],
            check=False,
            timeout=5,
        )

    @patch("subprocess.run")
    def test_logout_trigger(self, mock_run):
        """Test that logout is triggered ONLY after warning period elapses."""
        # Set warning to 2 minutes for quicker test simulation
        tm = TimeoutManager(
            time_limit_minutes=10,
            config_file=self.temp_config,
            warning_minutes=2,
            startup_grace_period=0,
        )

        today = datetime.now().strftime("%Y-%m-%d")

        # 1. Trigger the warning (limit reached)
        tm.config["usage"][today] = 10.1
        tm.check_time_limit()
        self.assertTrue(tm.warning_shown)

        # 2. Check immediately - should NOT logout yet
        tm.warning_shown_at = datetime.now()
        self.assertFalse(tm.check_time_limit())

        # 3. Simulate 3 minutes passing (exceeding the 2-minute warning period)
        tm.warning_shown_at = datetime.now() - timedelta(minutes=3)
        self.assertTrue(tm.check_time_limit())

    @patch("subprocess.run")
    def test_logout_execution_safely(self, mock_run):
        """Verify the logout command itself is correct, but mocked."""
        tm = TimeoutManager(time_limit_minutes=60, config_file=self.temp_config)

        tm.logout_user()

        # Check that the KDE logout command was the one called
        mock_run.assert_any_call(
            ["qdbus", "org.kde.Shutdown", "/Shutdown", "logout"], check=True
        )


if __name__ == "__main__":
    unittest.main()
