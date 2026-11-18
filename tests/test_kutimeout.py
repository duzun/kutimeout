import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import kutimeout
from kutimeout import TimeoutManager

logging.disable(logging.CRITICAL)  # keep test output clean


class TestTimeoutManager(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = Path(tmp.name) / "config.json"
        self.usage_file = Path(tmp.name) / "usage.json"
        self.locked = "false"
        self.fail_commands = set()  # command args whose subprocess.run raises

        patcher = patch.object(kutimeout.subprocess, "run", side_effect=self._run)
        self.run = patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, cmd, **kwargs):
        if cmd[1] in self.fail_commands:
            raise subprocess.CalledProcessError(1, cmd)
        result = subprocess.CompletedProcess(cmd, 0)
        result.stdout = self.locked
        return result

    def make(self, **kw):
        kw.setdefault("startup_grace_period", 0)
        return TimeoutManager(config_file=self.cfg, **kw)

    def read(self, path):
        return json.loads(path.read_text())

    def today(self):
        return datetime.now().strftime("%Y-%m-%d")

    def set_usage(self, minutes):
        self.usage_file.write_text(json.dumps({"usage": {self.today(): minutes}}))

    def commands(self, name):
        return [c.args[0] for c in self.run.call_args_list if c.args[0][0] == name]

    def check(self, tm):
        tm.update_usage()  # like the main loop: refresh usage, then check
        return tm.check_time_limit()

    # --- configuration ---

    def test_new_config_gets_defaults_and_cli_limit(self):
        TimeoutManager(config_file=self.cfg, time_limit_minutes=60)
        cfg = self.read(self.cfg)
        self.assertEqual(cfg["time_limit_minutes"], 60)
        self.assertEqual(cfg["grace_period_minutes"], 1)
        self.assertEqual(cfg["warning_minutes"], 5)
        self.assertFalse(cfg["track_usage"])

    def test_cli_limit_overrides_and_persists(self):
        self.cfg.write_text(json.dumps({"time_limit_minutes": 30}))
        tm = self.make(time_limit_minutes=120)
        self.assertEqual(tm.time_limit_minutes, 120)
        self.assertEqual(self.read(self.cfg)["time_limit_minutes"], 120)

    def test_save_keeps_other_settings_from_config(self):
        self.cfg.write_text(json.dumps({"grace_period_minutes": 7, "warning_minutes": 9}))
        with self.assertRaises(SystemExit) as cm:
            kutimeout.main(["-c", str(self.cfg), "-l", "30", "-s"])
        self.assertEqual(cm.exception.code, 0)
        cfg = self.read(self.cfg)
        self.assertEqual(
            (cfg["time_limit_minutes"], cfg["grace_period_minutes"], cfg["warning_minutes"]),
            (30, 7, 9),
        )

    def test_enabled(self):
        self.assertFalse(self.make(time_limit_minutes=0).enabled)
        self.assertTrue(self.make(time_limit_minutes=0, track_usage=True).enabled)
        self.assertTrue(self.make(time_limit_minutes=-1, track_usage=False).enabled)
        self.assertTrue(self.make(time_limit_minutes=60, track_usage=False).enabled)

    # --- usage tracking ---

    def test_unlocked_time_is_counted_and_saved(self):
        tm = self.make(time_limit_minutes=60)
        tm.last_update = datetime.now() - timedelta(minutes=3)
        self.assertAlmostEqual(tm.update_usage(), 3.0, places=1)
        self.assertAlmostEqual(self.read(self.usage_file)["usage"][self.today()], 3.0, places=1)

    def test_locked_time_is_not_counted(self):
        self.locked = "true"
        tm = self.make(time_limit_minutes=60)
        tm.last_update = datetime.now() - timedelta(minutes=3)
        self.assertEqual(tm.update_usage(), 0.0)

    def test_time_jumps_are_ignored(self):
        tm = self.make(time_limit_minutes=60)
        tm.last_update = datetime.now() - timedelta(minutes=10)  # suspend
        self.assertEqual(tm.update_usage(), 0.0)
        tm.last_update = datetime.now() + timedelta(minutes=5)  # clock set back
        self.assertEqual(tm.update_usage(), 0.0)

    def test_external_usage_edit_is_picked_up(self):
        tm = self.make(time_limit_minutes=60)
        self.set_usage(40)
        self.assertAlmostEqual(tm.update_usage(), 40.0, places=1)

    def test_interrupted_write_keeps_previous_usage(self):
        tm = self.make(time_limit_minutes=60)
        self.set_usage(40)

        def crash_mid_write(data, f, **kw):
            f.write('{"usage": {')  # partial write, then crash
            raise OSError("disk full")

        with patch.object(kutimeout.json, "dump", side_effect=crash_mid_write):
            tm.update_usage()

        self.assertEqual(self.read(self.usage_file)["usage"][self.today()], 40)

    # --- warning and logout ---

    def test_warning_only_inside_warning_window(self):
        tm = self.make(time_limit_minutes=60, warning_minutes=5)
        self.set_usage(54)
        self.assertFalse(self.check(tm))
        self.assertEqual(self.commands("notify-send"), [])

        self.set_usage(56)
        self.assertFalse(self.check(tm))
        self.assertEqual(len(self.commands("notify-send")), 1)

        self.assertFalse(self.check(tm))  # warned once only
        self.assertEqual(len(self.commands("notify-send")), 1)

    def test_logout_only_after_limit_and_warning_period(self):
        tm = self.make(time_limit_minutes=10, warning_minutes=2)
        self.set_usage(10.1)
        self.assertFalse(self.check(tm))  # warning shown now
        self.assertFalse(self.check(tm))  # warning period not elapsed
        tm.warning_shown_at = datetime.now() - timedelta(minutes=3)
        self.assertTrue(self.check(tm))

    def test_no_logout_before_limit_even_after_warning_period(self):
        tm = self.make(time_limit_minutes=60, warning_minutes=5)
        self.set_usage(57)
        self.check(tm)
        tm.warning_shown_at = datetime.now() - timedelta(minutes=10)
        self.assertFalse(self.check(tm))

    def test_grace_period_blocks_logout(self):
        tm = self.make(time_limit_minutes=10, warning_minutes=2, startup_grace_period=5)
        self.set_usage(100)
        self.assertFalse(self.check(tm))
        self.assertEqual(self.commands("notify-send"), [])

    def test_unlimited_modes_never_warn_or_logout(self):
        for limit, track in ((-1, False), (0, True)):
            with self.subTest(limit=limit, track=track):
                self.run.reset_mock()
                tm = self.make(time_limit_minutes=limit, track_usage=track)
                self.set_usage(10000)
                tm.warning_shown_at = datetime.now() - timedelta(minutes=60)
                self.assertFalse(self.check(tm))
                self.assertEqual(self.commands("notify-send"), [])

    # --- migration ---

    def test_usage_migrated_from_legacy_config(self):
        self.cfg.write_text(json.dumps({
            "time_limit_minutes": 60,
            "usage": {"2026-06-22": 45.5, "2026-06-21": 1},
            "last_update": "2026-06-22T12:00:00",
        }))
        self.usage_file.write_text(json.dumps({"usage": {"2026-06-21": 99}}))
        self.make()
        cfg = self.read(self.cfg)
        self.assertEqual(cfg["time_limit_minutes"], 60)
        self.assertNotIn("usage", cfg)
        self.assertNotIn("last_update", cfg)
        usage = self.read(self.usage_file)["usage"]
        self.assertEqual(usage["2026-06-22"], 45.5)
        self.assertEqual(usage["2026-06-21"], 99)  # existing usage.json wins

    # --- logout command ---

    def test_logout_command(self):
        self.make(time_limit_minutes=60).logout_user()
        self.assertEqual(
            self.commands("qdbus")[-1], ["qdbus", "org.kde.Shutdown", "/Shutdown", "logout"]
        )

    def test_logout_falls_back_to_ksmserver(self):
        self.fail_commands.add("org.kde.Shutdown")
        self.make(time_limit_minutes=60).logout_user()
        self.assertEqual(self.commands("qdbus")[-1][1], "org.kde.ksmserver")


if __name__ == "__main__":
    unittest.main()
