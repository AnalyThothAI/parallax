#!/usr/bin/env python
from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.queries.pulse_agent_cost_report import (
    build_signal_pulse_agent_cost_report,
    write_signal_pulse_agent_cost_report,
)
from gmgn_twitter_intel.platform.config.settings import load_settings
from gmgn_twitter_intel.platform.db.postgres_client import connect_postgres, with_password_from_file
from gmgn_twitter_intel.platform.paths.runtime_paths import config_path, workers_config_path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "docs" / "generated"
OPERATOR_HOME = Path.home() / ".gmgn-twitter-intel"


def main() -> None:
    args = _parse_args()
    settings = load_settings(require_ws_token=False)
    context = _config_context(settings)
    dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
    conn = connect_postgres(dsn, connect_timeout_seconds=settings.postgres_connect_timeout_seconds)
    try:
        conn.execute("SET statement_timeout = '60s'")
        conn.execute("SET default_transaction_read_only = on")
        report = build_signal_pulse_agent_cost_report(
            conn,
            now_ms=int(time.time() * 1000),
            lookback_hours=args.lookback_hours,
            dry_run_policy=None if args.dry_run else {"skip_deepseek_display_status_prefixes": ()},
        )
    finally:
        conn.close()

    generated_date = datetime.now().date().isoformat()
    output_path = write_signal_pulse_agent_cost_report(
        report,
        output_dir=OUTPUT_DIR,
        generated_date=generated_date,
        config_context=context,
        dry_run=bool(args.dry_run),
    )
    print(f"output_path={output_path}")
    print(f"config_path_under_operator_home={str(context['config_path_under_operator_home']).lower()}")
    print(f"workers_config_path_under_operator_home={str(context['workers_config_path_under_operator_home']).lower()}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Signal Pulse agent cost guard dry-run savings.")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _config_context(settings: Any) -> dict[str, Any]:
    configured_home = settings.config_dir
    resolved_config_path = config_path(configured_home).resolve()
    resolved_workers_path = workers_config_path(configured_home).resolve()
    return {
        "config_path": str(resolved_config_path),
        "workers_config_path": str(resolved_workers_path),
        "config_path_under_operator_home": _is_relative_to(resolved_config_path, OPERATOR_HOME),
        "workers_config_path_under_operator_home": _is_relative_to(resolved_workers_path, OPERATOR_HOME),
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    main()
