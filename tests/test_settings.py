import os
import unittest

from gmgn_twitter_cli.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_load_settings_accepts_only_handle_list_as_public_subscription(self):
        settings = load_settings(
            {
                "MONITOR_HANDLES": " @toly, CryptoDevinL,heyibinance ",
                "WS_TOKEN": "secret",
            }
        )

        self.assertEqual(settings.handles, ("toly", "cryptodevinl", "heyibinance"))
        self.assertEqual(settings.api_host, "0.0.0.0")
        self.assertEqual(settings.api_port, 8765)
        self.assertEqual(settings.embedding_dim, 1024)
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


def test_runtime_paths_use_lancedb_and_ignore_old_sqlite_configuration(tmp_path, monkeypatch):
    state_home = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))

    settings = load_settings(
        {
            "MONITOR_HANDLES": "toly",
            "WS_TOKEN": "secret",
            "EVENT_DB_PATH": str(tmp_path / "ignored.sqlite3"),
            "LOG_FILE": str(tmp_path / "ignored.log"),
        }
    )

    assert settings.lancedb_path == state_home / "gmgn-twitter-cli" / "twitter_intel.lancedb"
    assert settings.log_file == state_home / "gmgn-twitter-cli" / "gmgn-twitter-cli.log"


def test_lancedb_path_can_be_explicitly_configured(tmp_path):
    configured_path = tmp_path / "custom.lancedb"

    settings = load_settings(
        {
            "MONITOR_HANDLES": "toly",
            "WS_TOKEN": "secret",
            "LANCEDB_PATH": str(configured_path),
        }
    )

    assert settings.lancedb_path == configured_path


if __name__ == "__main__":
    unittest.main()
