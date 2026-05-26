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


def test_ops_enqueue_runtime_worker_dirty_targets_parser_defaults_to_dry_run() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(
        [
            "ops",
            "enqueue-runtime-worker-dirty-targets",
            "--work",
            "pulse_trigger",
            "--window",
            "1h",
            "--scope",
            "all",
            "--since-hours",
            "4",
        ]
    )
    execute = parser.parse_args(
        [
            "ops",
            "enqueue-runtime-worker-dirty-targets",
            "--work",
            "pulse_trigger",
            "--window",
            "4h",
            "--scope",
            "all",
            "--target-id",
            "asset-1",
            "--limit",
            "25",
            "--execute",
        ]
    )

    assert dry_run.ops_command == "enqueue-runtime-worker-dirty-targets"
    assert dry_run.work == "pulse_trigger"
    assert dry_run.window == "1h"
    assert dry_run.scope == "all"
    assert dry_run.since_hours == 4
    assert dry_run.limit is None
    assert dry_run.dry_run is True
    assert dry_run.execute is False
    assert execute.window == "4h"
    assert execute.target_id == "asset-1"
    assert execute.limit == 25
    assert execute.execute is True
    assert execute.dry_run is False

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "ops",
                "enqueue-runtime-worker-dirty-targets",
                "--work",
                "pulse_trigger",
                "--since-hours",
                "4",
                "--dry-run",
                "--execute",
            ]
        )


def test_ops_enqueue_runtime_worker_dirty_targets_parser_accepts_narrative_admission_work() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "enqueue-runtime-worker-dirty-targets",
            "--work",
            "narrative_admission",
            "--window",
            "1h",
            "--scope",
            "all",
            "--since-hours",
            "4",
            "--dry-run",
        ]
    )

    assert args.ops_command == "enqueue-runtime-worker-dirty-targets"
    assert args.work == "narrative_admission"
    assert args.window == "1h"
    assert args.scope == "all"
    assert args.since_hours == 4
    assert args.dry_run is True
    assert args.execute is False


def test_ops_enqueue_runtime_worker_dirty_targets_parser_accepts_discussion_digest_work() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "enqueue-runtime-worker-dirty-targets",
            "--work",
            "discussion_digest",
            "--window",
            "1h",
            "--scope",
            "matched",
            "--target-id",
            "solana:So111",
            "--limit",
            "25",
            "--dry-run",
        ]
    )

    assert args.ops_command == "enqueue-runtime-worker-dirty-targets"
    assert args.work == "discussion_digest"
    assert args.window == "1h"
    assert args.scope == "matched"
    assert args.target_id == "solana:So111"
    assert args.limit == 25
    assert args.dry_run is True
    assert args.execute is False


def test_ops_enqueue_runtime_worker_dirty_targets_parser_accepts_asset_market_repair_selectors() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "enqueue-runtime-worker-dirty-targets",
            "--work",
            "image_source",
            "--target-type",
            "Asset",
            "--target-id",
            "asset:eip155:1:erc20:0xabc",
            "--source-url",
            "https://gmgn.ai/external-res/abc.png",
            "--provider",
            "gmgn_dex_profile",
            "--limit",
            "25",
            "--dry-run",
        ]
    )

    assert args.ops_command == "enqueue-runtime-worker-dirty-targets"
    assert args.work == "image_source"
    assert args.target_type == "Asset"
    assert args.target_id == "asset:eip155:1:erc20:0xabc"
    assert args.source_url == "https://gmgn.ai/external-res/abc.png"
    assert args.provider == "gmgn_dex_profile"
    assert args.limit == 25
