#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

OKX_CEX_KEYS = ("cex_base_url", "cex_sync_enabled", "cex_inst_types")
BINANCE_DEFAULTS = {
    "cex_profile_base_url": "https://www.binance.com",
    "usdm_futures_base_url": "https://fapi.binance.com",
    "cex_universe_quote_symbol": "USDT",
    "cex_universe_contract_type": "PERPETUAL",
}


def default_config_path() -> Path:
    return Path.home() / ".gmgn-twitter-intel" / "config.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate provider config from OKX CEX keys to Binance USD-M perpetual defaults."
    )
    parser.add_argument("--config-path", type=Path, default=default_config_path())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="show planned config changes without writing files")
    mode.add_argument("--execute", action="store_true", help="write a backup and update the config file")
    return parser.parse_args(argv)


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as config_file:
        payload = yaml.safe_load(config_file) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"config at {path} must be a YAML mapping")
    return payload


def migrate_config(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    migrated = dict(payload)
    providers = migrated.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("config providers must be a YAML mapping")

    okx = providers.setdefault("okx", {})
    if not isinstance(okx, dict):
        raise ValueError("config providers.okx must be a YAML mapping")
    binance = providers.setdefault("binance", {})
    if not isinstance(binance, dict):
        raise ValueError("config providers.binance must be a YAML mapping")

    changes: list[str] = []
    for key in OKX_CEX_KEYS:
        if key in okx:
            okx.pop(key)
            changes.append(f"removed providers.okx.{key}")

    for key, value in BINANCE_DEFAULTS.items():
        if key not in binance:
            binance[key] = value
            changes.append(f"added providers.binance.{key}")

    return migrated, changes


def backup_path_for(config_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return config_path.with_name(f"{config_path.name}.{timestamp}.bak")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config_path.expanduser()
    payload = load_yaml_mapping(config_path)
    migrated, changes = migrate_config(payload)

    mode = "execute" if args.execute else "dry-run"
    if not changes:
        print(f"{mode}: no config changes needed for {config_path}")
    else:
        print(f"{mode}: {len(changes)} config change(s) for {config_path}")
        for change in changes:
            print(f"- {change}")

    if args.execute:
        backup_path = backup_path_for(config_path)
        shutil.copy2(config_path, backup_path)
        write_yaml(config_path, migrated)
        print(f"backup: {backup_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
