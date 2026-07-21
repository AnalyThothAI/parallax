from __future__ import annotations

from pathlib import Path

from parallax.app.runtime.worker_manifest import worker_names
from parallax.platform.config.settings import WorkersSettings

SRC = Path(__file__).resolve().parents[2] / "src" / "parallax"


def test_watchlist_and_social_agent_workers_are_not_runtime_workers() -> None:
    names = set(worker_names())

    assert "enrichment" not in names
    assert "handle_summary" not in names


def test_watchlist_and_social_agent_lanes_are_not_configurable() -> None:
    lanes = set(WorkersSettings().agent_runtime.lanes)

    assert "social.event_enrichment" not in lanes
    assert "watchlist.handle_summary" not in lanes
    assert "news.item_brief" in lanes


def test_agent_provider_wiring_only_builds_current_news_agents() -> None:
    provider_wiring = (SRC / "app/runtime/provider_wiring/__init__.py").read_text(encoding="utf-8")
    model_execution = (SRC / "app/runtime/provider_wiring/model_execution.py").read_text(encoding="utf-8")

    assert "litellm_social_event_provider" not in provider_wiring
    assert "litellm_watchlist_summary_provider" not in provider_wiring
    assert "litellm_social_event_provider" not in model_execution
    assert "litellm_watchlist_summary_provider" not in model_execution
    assert "litellm_news_item_brief_provider" in model_execution


def test_ingest_no_longer_enqueues_social_enrichment_jobs() -> None:
    ingest_service = (SRC / "domains/evidence/services/ingest_service.py").read_text(encoding="utf-8")

    assert "watched_social_event_priority" not in ingest_service
    assert "enqueue_watched_event" not in ingest_service


def test_watchlist_public_contract_does_not_restore_retired_summary_agent_surface() -> None:
    project_root = SRC.parents[1]
    contracts = (project_root / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    workers = (project_root / "docs" / "WORKERS.md").read_text(encoding="utf-8")
    watchlist_contract = contracts.split("Watchlist handle intel contract:", 1)[1].split(
        "Search V2 contract:",
        1,
    )[0]
    forbidden_contract_tokens = (
        "/api/watchlist/handle/{handle}/summary",
        "social_event_extraction",
        "social_event.summary_zh",
    )
    forbidden_worker_tokens = (
        "watchlist_handle_signal_stats",
        "watchlist summaries",
    )

    assert [token for token in forbidden_contract_tokens if token in watchlist_contract] == []
    assert [token for token in forbidden_worker_tokens if token in workers] == []
