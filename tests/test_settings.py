import os
import tempfile
import unittest
from pathlib import Path

from gmgn_twitter_cli.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_load_settings_accepts_only_handle_list_as_public_subscription(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = load_settings(
                {
                    "MONITOR_HANDLES": " @toly, CryptoDevinL,heyibinance ",
                    "WS_TOKEN": "secret",
                    "EVENT_DB_PATH": str(Path(tmpdir) / "events.sqlite3"),
                }
            )

        self.assertEqual(settings.handles, ("toly", "cryptodevinl", "heyibinance"))
        self.assertEqual(settings.api_host, "0.0.0.0")
        self.assertEqual(settings.api_port, 8765)
        self.assertEqual(settings.observed_retention_days, 7)
        self.assertEqual(settings.matched_retention_days, 180)
        self.assertEqual(settings.upstream_chains, ("sol", "eth", "base", "bsc"))
        self.assertEqual(settings.upstream_channels, ("twitter_monitor_basic", "twitter_monitor_token"))

    def test_load_settings_rejects_missing_ws_token(self):
        with self.assertRaises(ValueError):
            load_settings({"MONITOR_HANDLES": "toly", "WS_TOKEN": ""})

    def test_environment_loader_does_not_depend_on_process_env_mutation(self):
        original = os.environ.copy()
        try:
            settings = load_settings({"MONITOR_HANDLES": "elonmusk", "WS_TOKEN": "secret"})
            self.assertEqual(settings.handles, ("elonmusk",))
        finally:
            self.assertEqual(os.environ, original)


if __name__ == "__main__":
    unittest.main()
