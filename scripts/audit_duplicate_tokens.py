"""One-off audit + dedup of duplicate tokens across (chain, symbol).

See docs/superpowers/specs/active/2026-05-12-duplicate-token-audit-and-dedup-design-cn.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `scripts.audit_dedup` is importable
# whether this file is executed directly or imported from tests.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Compute audit but do not mutate DB.")
    mode.add_argument("--apply", action="store_true", help="Apply the audit; single transaction per phase.")

    parser.add_argument("--report", type=Path, default=Path("docs/generated/duplicate-token-audit.md"),
                        help="Markdown report output path.")
    parser.add_argument("--chain", type=str, default=None, help="Filter to one chain (debug).")
    parser.add_argument("--symbol", type=str, default=None, help="Filter to one symbol (debug).")
    parser.add_argument("--threshold-holders", type=int, default=200,
                        help="Minimum holders for in-db winner; below triggers external arbitration.")
    parser.add_argument("--threshold-liq-usd", type=float, default=5000.0,
                        help="Minimum liquidity_usd for in-db winner.")
    parser.add_argument("--no-external", action="store_true",
                        help="Skip OKX/CoinGecko fallback; under-threshold groups always group-drop.")
    parser.add_argument("--only-phase1", action="store_true", help="Only run chain-name normalization.")
    parser.add_argument("--only-phase2", action="store_true", help="Only run (chain, symbol) dedup.")
    return parser


def _open_connection():
    from gmgn_twitter_intel.platform.config.settings import load_settings
    from gmgn_twitter_intel.platform.db.postgres_client import (
        connect_postgres,
        local_docker_host_dsn,
        with_password_from_file,
    )

    settings = load_settings(require_ws_token=False)
    dsn = local_docker_host_dsn(with_password_from_file(settings.postgres_dsn, settings.postgres_password_file))
    return connect_postgres(dsn)


def _build_external_arbiter(*, settings=None):
    from gmgn_twitter_intel.integrations.coingecko.search_client import CoingeckoSearchClient
    from gmgn_twitter_intel.integrations.okx.dex_client import OkxDexClient
    from gmgn_twitter_intel.platform.config.settings import load_settings
    from scripts.audit_dedup.external_arbiter import ExternalArbiter

    settings = settings or load_settings(require_ws_token=False)
    okx = OkxDexClient(
        base_url=settings.okx_dex_base_url if hasattr(settings, "okx_dex_base_url") else "https://web3.okx.com",
    )
    cg = CoingeckoSearchClient()
    return ExternalArbiter(okx_client=okx, coingecko_client=cg)


def main(argv: list[str] | None = None) -> int:
    from scripts.audit_dedup.phase1_chain_normalize import run_phase1
    from scripts.audit_dedup.phase2_dedup import Phase2Config, _NullArbiter, run_phase2  # type: ignore[attr-defined]
    from scripts.audit_dedup.report import Phase1Result, Phase2Summary, render_markdown_report

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.only_phase1 and args.only_phase2:
        parser.error("--only-phase1 and --only-phase2 are mutually exclusive")

    apply = bool(args.apply)
    conn = _open_connection()

    phase1: Phase1Result = Phase1Result.empty()
    if not args.only_phase2:
        phase1 = run_phase1(conn, apply=apply)

    arbiter = _NullArbiter() if args.no_external else _build_external_arbiter()

    phase2: Phase2Summary = Phase2Summary(0, 0, 0, 0, 0, 0, 0, 0, ())
    if not args.only_phase1:
        phase2 = run_phase2(
            conn,
            config=Phase2Config(
                threshold_holders=args.threshold_holders,
                threshold_liq_usd=args.threshold_liq_usd,
                chain_filter=args.chain,
                symbol_filter=args.symbol,
                use_external=not args.no_external,
            ),
            external_arbiter=arbiter,
            apply=apply,
        )

    markdown = render_markdown_report(
        mode="apply" if apply else "dry-run", phase1=phase1, phase2=phase2,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown, encoding="utf-8")
    sys.stdout.write(f"Audit report → {args.report}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
