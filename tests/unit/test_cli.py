from __future__ import annotations

import pytest

from parallax.app.surfaces.cli.commands.ops import _rebuild_news_canonical_items
from parallax.app.surfaces.cli.parser import build_parser


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
        parser.parse_args(["ops", "enqueue-runtime-worker-dirty-targets", "--work", "pulse_trigger"])


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


def test_ops_enqueue_token_capture_tier_rank_set_parser_requires_mode() -> None:
    parser = build_parser()

    dry_run = parser.parse_args(["ops", "enqueue-token-capture-tier-rank-set", "--dry-run"])
    execute = parser.parse_args(
        [
            "ops",
            "enqueue-token-capture-tier-rank-set",
            "--window",
            "1h",
            "--limit",
            "25",
            "--execute",
        ]
    )

    assert dry_run.ops_command == "enqueue-token-capture-tier-rank-set"
    assert dry_run.window == "24h"
    assert dry_run.limit == 500
    assert dry_run.dry_run is True
    assert execute.window == "1h"
    assert execute.limit == 25
    assert execute.execute is True

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "enqueue-token-capture-tier-rank-set"])

    for limit in ("0", "-1"):
        with pytest.raises(SystemExit):
            parser.parse_args(["ops", "enqueue-token-capture-tier-rank-set", "--limit", limit, "--dry-run"])


def test_ops_news_dedup_commands_are_registered_without_compatibility_flags() -> None:
    parser = build_parser()

    diagnostics = parser.parse_args(["ops", "news-dedup-diagnostics"])
    diagnostics_custom = parser.parse_args(["ops", "news-dedup-diagnostics", "--window-hours", "4"])
    rebuild_dry_run = parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "25", "--dry-run"])
    rebuild_execute = parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "25", "--execute"])

    assert diagnostics.ops_command == "news-dedup-diagnostics"
    assert diagnostics.window_hours == 8.0
    assert diagnostics_custom.window_hours == 4.0
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "news-dedup-diagnostics", "--window-hours", "0"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "news-dedup-diagnostics", "--window-hours", "-1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "news-dedup-diagnostics", "--score-threshold", "90"])
    assert rebuild_dry_run.ops_command == "rebuild-news-canonical-items"
    assert rebuild_dry_run.limit == 25
    assert rebuild_dry_run.dry_run is True
    assert rebuild_dry_run.execute is False
    assert rebuild_execute.execute is True
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "0", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-news-canonical-items", "--limit", "-1", "--dry-run"])
    assert not hasattr(diagnostics, "include_legacy")
    assert not hasattr(rebuild_execute, "legacy_id")
    assert not hasattr(rebuild_execute, "raw_item_id")

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "rebuild-news-canonical-items"])
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


@pytest.mark.parametrize("limit", [0, -1, True, "25"])
def test_rebuild_news_canonical_items_rejects_malformed_limit_before_repo(limit: object) -> None:
    class Repos:
        conn = object()
        news = None

    with pytest.raises(ValueError, match="ops_news_canonical_rebuild_limit_required"):
        _rebuild_news_canonical_items(
            Repos(),
            limit=limit,  # type: ignore[arg-type]
            dry_run=True,
            execute=False,
            now_ms=1_000,
        )


def test_removed_cleanup_news_item_brief_schema_hard_cut_command_is_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-item-brief-schema-hard-cut", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "cleanup-news-item-brief-schema-hard-cut", "--execute"])


def test_removed_repair_news_market_signal_command_is_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-market-signal", "--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["ops", "repair-news-market-signal", "--dry-run", "--execute"])
