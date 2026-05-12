"""One-off audit + dedup of duplicate tokens across (chain, symbol).

See docs/superpowers/specs/active/2026-05-12-duplicate-token-audit-and-dedup-design-cn.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.only_phase1 and args.only_phase2:
        parser.error("--only-phase1 and --only-phase2 are mutually exclusive")

    # Phases wired in later tasks. For now just print a banner.
    sys.stdout.write(
        f"audit_duplicate_tokens: mode={'apply' if args.apply else 'dry-run'} "
        f"chain={args.chain} symbol={args.symbol} "
        f"holders>={args.threshold_holders} liq>={args.threshold_liq_usd}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
