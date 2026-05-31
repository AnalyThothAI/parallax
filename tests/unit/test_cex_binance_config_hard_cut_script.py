import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "cex_binance_config_hard_cut.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("cex_binance_config_hard_cut", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_legacy_config(path: Path, *, binance: dict | None = None) -> None:
    payload = {
        "ws_token": "secret",
        "providers": {
            "okx": {
                "dex_ws_url": "wss://wsdex.okx.com/ws/v6/dex",
                "cex_base_url": "https://www.okx.com",
                "cex_sync_enabled": True,
                "cex_inst_types": ["SPOT", "SWAP"],
            },
            "binance": binance or {"enabled": True, "web3_base_url": "https://web3.binance.com"},
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_dry_run_reports_migration_without_writing_config_or_backup(tmp_path, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    _write_legacy_config(config_path)
    original_text = config_path.read_text(encoding="utf-8")
    script = _load_script()

    exit_code = script.main(["--config-path", str(config_path), "--dry-run"])

    assert exit_code == 0
    assert config_path.read_text(encoding="utf-8") == original_text
    assert not list(tmp_path.glob("config.yaml.*.bak"))
    assert "dry-run" in capsys.readouterr().out


def test_execute_writes_backup_and_migrated_yaml(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_legacy_config(config_path)
    original_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    script = _load_script()

    exit_code = script.main(["--config-path", str(config_path), "--execute"])

    assert exit_code == 0
    backups = list(tmp_path.glob("config.yaml.*.bak"))
    assert len(backups) == 1
    assert yaml.safe_load(backups[0].read_text(encoding="utf-8")) == original_payload
    migrated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert migrated["providers"]["okx"] == {"dex_ws_url": "wss://wsdex.okx.com/ws/v6/dex"}
    assert migrated["providers"]["binance"] == {
        "enabled": True,
        "web3_base_url": "https://web3.binance.com",
        "cex_profile_base_url": "https://www.binance.com",
        "usdm_futures_base_url": "https://fapi.binance.com",
        "cex_universe_quote_symbol": "USDT",
        "cex_universe_contract_type": "PERPETUAL",
    }


def test_execute_is_idempotent_and_preserves_existing_binance_values(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_legacy_config(
        config_path,
        binance={
            "enabled": True,
            "cex_profile_base_url": "https://custom.binance.example",
            "usdm_futures_base_url": "https://custom-fapi.binance.example",
            "cex_universe_quote_symbol": "USDC",
            "cex_universe_contract_type": "CURRENT_QUARTER",
        },
    )
    script = _load_script()

    assert script.main(["--config-path", str(config_path), "--execute"]) == 0
    first_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert script.main(["--config-path", str(config_path), "--execute"]) == 0

    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == first_payload
    assert first_payload["providers"]["binance"] == {
        "enabled": True,
        "cex_profile_base_url": "https://custom.binance.example",
        "usdm_futures_base_url": "https://custom-fapi.binance.example",
        "cex_universe_quote_symbol": "USDC",
        "cex_universe_contract_type": "CURRENT_QUARTER",
    }


def test_script_does_not_import_application_settings() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "parallax.platform.config.settings" not in source
    assert "from parallax" not in source
    assert "import parallax" not in source
