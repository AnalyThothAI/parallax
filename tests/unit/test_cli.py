from __future__ import annotations

from gmgn_twitter_intel.app.surfaces.cli.parser import build_parser


def test_ops_backfill_token_radar_first_seen_parser_accepts_batch_controls() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "backfill-token-radar-first-seen",
            "--batch-size",
            "5000",
            "--max-batches",
            "1",
        ]
    )

    assert args.command == "ops"
    assert args.ops_command == "backfill-token-radar-first-seen"
    assert args.batch_size == 5000
    assert args.max_batches == 1


def test_ops_backfill_watchlist_signal_stats_parser_accepts_batch_controls() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "backfill-watchlist-signal-stats",
            "--batch-size",
            "5000",
            "--max-batches",
            "1",
            "--dry-run",
        ]
    )

    assert args.command == "ops"
    assert args.ops_command == "backfill-watchlist-signal-stats"
    assert args.batch_size == 5000
    assert args.max_batches == 1
    assert args.dry_run is True


def test_ops_prune_token_radar_parser_requires_explicit_mode() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(
        [
            "ops",
            "prune-token-radar",
            "--retention-days",
            "7",
            "--batch-size",
            "10000",
            "--max-batches",
            "1",
            "--dry-run",
        ]
    )
    execute = parser.parse_args(
        [
            "ops",
            "prune-token-radar",
            "--retention-days",
            "7",
            "--batch-size",
            "10000",
            "--max-batches",
            "1",
            "--execute",
        ]
    )

    assert dry_run.ops_command == "prune-token-radar"
    assert dry_run.dry_run is True
    assert dry_run.execute is False
    assert execute.execute is True
    assert execute.dry_run is False
