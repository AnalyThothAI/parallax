import os
import unittest

from gmgn_twitter_intel.settings import load_settings


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
    app_home = tmp_path / "app-home"
    monkeypatch.setenv("GMGN_TWITTER_HOME", str(app_home))

    settings = load_settings(
        {
            "MONITOR_HANDLES": "toly",
            "WS_TOKEN": "secret",
            "EVENT_DB_PATH": str(tmp_path / "ignored.sqlite3"),
            "LOG_FILE": str(tmp_path / "ignored.log"),
        }
    )

    assert settings.lancedb_path == app_home / "twitter_intel.lancedb"
    assert settings.log_file == app_home / "logs" / "gmgn-twitter-intel.log"


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


def test_load_settings_can_skip_ws_token_for_read_only_cli():
    settings = load_settings({"MONITOR_HANDLES": "toly"}, require_ws_token=False)

    assert settings.handles == ("toly",)
    assert settings.ws_token is None


def test_load_settings_reads_default_app_home_env_file(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    app_home.mkdir()
    (app_home / ".env").write_text(
        "WS_TOKEN=secret-from-home\nMONITOR_HANDLES=toly,traderpow\nEMBEDDING_DIM=8\n",
        encoding="utf-8",
    )
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(workdir)

    settings = load_settings()

    assert settings.ws_token == "secret-from-home"
    assert settings.handles == ("toly", "traderpow")
    assert settings.embedding_dim == 8


def test_load_settings_prefers_current_env_file_over_default_app_home_env_file(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    app_home.mkdir()
    (app_home / ".env").write_text("WS_TOKEN=home-secret\nMONITOR_HANDLES=home\n", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / ".env").write_text("WS_TOKEN=local-secret\nMONITOR_HANDLES=local\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(workdir)

    settings = load_settings()

    assert settings.ws_token == "local-secret"
    assert settings.handles == ("local",)


if __name__ == "__main__":
    unittest.main()
