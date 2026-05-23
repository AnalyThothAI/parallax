from __future__ import annotations

import pytest

from gmgn_twitter_intel.app.surfaces.cli.parser import build_parser


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
    assert args.after_cursor == ""
    assert args.dry_run is True


def test_ops_reset_token_radar_postgres_hard_cut_parser_requires_explicit_mode() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(
        [
            "ops",
            "reset-token-radar-postgres-hard-cut",
            "--dry-run",
        ]
    )
    execute = parser.parse_args(
        [
            "ops",
            "reset-token-radar-postgres-hard-cut",
            "--execute",
        ]
    )

    assert dry_run.ops_command == "reset-token-radar-postgres-hard-cut"
    assert dry_run.dry_run is True
    assert dry_run.execute is False
    assert execute.execute is True
    assert execute.dry_run is False


def test_removed_token_radar_storage_ops_commands_are_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "prune-token-radar", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "backfill-token-radar-first-seen"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "clean-reset-token-radar-storage"])


def test_ops_postgres_partition_helpers_require_execute() -> None:
    parser = build_parser()

    ensure = parser.parse_args(["ops", "ensure-postgres-partitions", "--execute"])
    drop_expired = parser.parse_args(["ops", "drop-expired-postgres-partitions", "--execute"])

    assert ensure.ops_command == "ensure-postgres-partitions"
    assert ensure.execute is True
    assert drop_expired.ops_command == "drop-expired-postgres-partitions"
    assert drop_expired.execute is True


def test_ops_mirror_token_images_parser_accepts_limits() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "mirror-token-images",
            "--limit",
            "500",
            "--source-limit",
            "5000",
        ]
    )

    assert args.command == "ops"
    assert args.ops_command == "mirror-token-images"
    assert args.limit == 500
    assert args.source_limit == 5000
