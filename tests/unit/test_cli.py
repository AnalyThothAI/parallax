from __future__ import annotations

import pytest

from parallax.app.surfaces.cli.parser import build_parser


def test_config_redaction_never_returns_an_unparseable_dsn() -> None:
    from parallax.app.surfaces.cli.commands.config import _redacted_postgres_dsn

    raw = "postgresql://operator:secret@["

    assert _redacted_postgres_dsn(raw) == "<invalid>"


def test_removed_watchlist_signal_stats_backfill_command_is_not_registered() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
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
        parser.parse_args(["ops", "enqueue-runtime-worker-dirty-targets", "--work", "retired_work"])


def test_ops_mirror_token_images_parser_accepts_limits() -> None:
    args = build_parser().parse_args(
        [
            "ops",
            "mirror-token-images",
            "--limit",
            "500",
        ]
    )

    assert args.command == "ops"
    assert args.ops_command == "mirror-token-images"
    assert args.limit == 500


def test_ops_mirror_token_images_parser_rejects_source_limit() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["ops", "mirror-token-images", "--source-limit", "5000"])


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

    for args in (
        ["ops", "enqueue-token-radar-dirty-targets", "--source", "events", "--since-ms", "-1", "--dry-run"],
        ["ops", "enqueue-token-radar-dirty-targets", "--source", "events", "--limit", "0", "--dry-run"],
        ["ops", "enqueue-token-radar-dirty-targets", "--source", "events", "--limit", "-1", "--dry-run"],
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(args)


def test_ops_rebuild_market_current_parser_requires_execute_and_positive_limit() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "ops",
            "rebuild-market-current",
            "--after-target-type",
            "Asset",
            "--after-target-id",
            "asset:sol",
            "--limit",
            "25",
            "--execute",
        ]
    )

    assert args.ops_command == "rebuild-market-current"
    assert args.after_target_type == "Asset"
    assert args.after_target_id == "asset:sol"
    assert args.limit == 25
    assert args.execute is True
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-market-current"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-market-current", "--limit", "0", "--execute"])


def test_retired_token_capture_tier_ops_command_is_not_registered() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["ops", "enqueue-token-capture-tier-rank-set", "--dry-run"])


def test_ops_news_dedup_diagnostics_is_registered_without_compatibility_flags() -> None:
    parser = build_parser()

    diagnostics = parser.parse_args(["ops", "news-dedup-diagnostics"])
    diagnostics_custom = parser.parse_args(["ops", "news-dedup-diagnostics", "--window-hours", "4"])
    assert diagnostics.ops_command == "news-dedup-diagnostics"
    assert diagnostics.window_hours == 8.0
    assert diagnostics_custom.window_hours == 4.0
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "news-dedup-diagnostics", "--window-hours", "0"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "news-dedup-diagnostics", "--window-hours", "-1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "news-dedup-diagnostics", "--score-threshold", "90"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "25", "--dry-run"])
    assert not hasattr(diagnostics, "include_legacy")
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-duplicates-hard-cut"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-duplicates-hard-cut", "--limit", "25", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-duplicates-hard-cut", "--limit", "25", "--execute"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-agent-market-admission", "--since-ms", "1000", "--until-ms", "2000"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-intel-hard-cut"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-intel-hard-cut", "--execute"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-brief-input"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-brief-input", "--dry-run"])


def test_removed_repair_news_market_signal_command_is_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-market-signal", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-market-signal", "--dry-run", "--execute"])
