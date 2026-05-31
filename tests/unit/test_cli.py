from __future__ import annotations

import pytest

from parallax.app.surfaces.cli.parser import build_parser


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


def test_removed_token_radar_storage_ops_commands_are_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "prune-token-radar", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "backfill-token-radar-first-seen"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "clean-reset-token-radar-storage"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "reset-token-radar-postgres-hard-cut", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "ensure-postgres-partitions", "--execute"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "drop-expired-postgres-partitions", "--execute"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-token-radar-rank-inputs", "--execute", "--reason", "manual"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "enqueue-runtime-worker-dirty-targets", "--work", "pulse_trigger"])


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


def test_ops_rebuild_market_tick_current_parser_requires_explicit_mode() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(["ops", "rebuild-market-tick-current", "--dry-run"])
    execute = parser.parse_args(["ops", "rebuild-market-tick-current", "--execute"])

    assert dry_run.ops_command == "rebuild-market-tick-current"
    assert dry_run.dry_run is True
    assert dry_run.execute is False
    assert execute.ops_command == "rebuild-market-tick-current"
    assert execute.execute is True
    assert execute.dry_run is False

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-market-tick-current"])


def test_ops_enqueue_token_radar_dirty_targets_parser_accepts_source_since_limit_and_mode() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(
        [
            "ops",
            "enqueue-token-radar-dirty-targets",
            "--source",
            "events",
            "--since-ms",
            "0",
            "--dry-run",
        ]
    )
    execute = parser.parse_args(
        [
            "ops",
            "enqueue-token-radar-dirty-targets",
            "--source",
            "market-current",
            "--since-ms",
            "123",
            "--limit",
            "25",
            "--execute",
        ]
    )

    assert dry_run.ops_command == "enqueue-token-radar-dirty-targets"
    assert dry_run.source == "events"
    assert dry_run.since_ms == 0
    assert dry_run.limit == 5000
    assert dry_run.dry_run is True
    assert execute.source == "market-current"
    assert execute.since_ms == 123
    assert execute.limit == 25
    assert execute.execute is True

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "enqueue-token-radar-dirty-targets", "--source", "events"])


def test_ops_news_dedup_commands_are_registered_without_compatibility_flags() -> None:
    parser = build_parser()

    diagnostics = parser.parse_args(["ops", "news-dedup-diagnostics"])
    rebuild_dry_run = parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "25", "--dry-run"])
    rebuild_execute = parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "25", "--execute"])

    assert diagnostics.ops_command == "news-dedup-diagnostics"
    assert rebuild_dry_run.ops_command == "rebuild-news-canonical-items"
    assert rebuild_dry_run.limit == 25
    assert rebuild_dry_run.dry_run is True
    assert rebuild_dry_run.execute is False
    assert rebuild_execute.execute is True
    assert not hasattr(diagnostics, "include_legacy")
    assert not hasattr(rebuild_execute, "legacy_id")
    assert not hasattr(rebuild_execute, "raw_item_id")

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-news-canonical-items"])
