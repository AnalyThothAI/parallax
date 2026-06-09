from __future__ import annotations

import re
from pathlib import Path

import pytest

from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.platform.config.settings import WorkersSettings

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs" / "CONTRACTS.md"
API_WS = ROOT / "src" / "parallax" / "app" / "surfaces" / "api" / "ws.py"
NEWS_ROUTES = ROOT / "src" / "parallax" / "app" / "surfaces" / "api" / "routes_news.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start) + len(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def _between_pattern(text: str, start_pattern: str, end_pattern: str) -> str:
    start_match = re.search(start_pattern, text, re.MULTILINE)
    assert start_match is not None, f"start pattern not found: {start_pattern}"
    end_match = re.search(end_pattern, text[start_match.end() :], re.MULTILINE)
    assert end_match is not None, f"end pattern not found: {end_pattern}"
    return text[start_match.end() : start_match.end() + end_match.start()]


def _code_values(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"`([^`]+)`", text))


@pytest.mark.architecture
def test_contracts_worker_keys_match_manifest_registry() -> None:
    contracts = _read(CONTRACTS)
    worker_key_block = _between_pattern(
        contracts,
        r"per manifest worker key,\s+in manifest registry\s+order:",
        r"The schema is",
    )

    documented_keys = _code_values(worker_key_block)
    manifest_keys = tuple(manifest.name for manifest in all_worker_manifests())

    assert documented_keys == manifest_keys


@pytest.mark.architecture
def test_contracts_agent_runtime_lanes_match_settings_defaults() -> None:
    contracts = _read(CONTRACTS)
    lane_block = _between_pattern(contracts, r"Default lane keys are ", r"\.\s+Each lane may override")

    documented_lanes = _code_values(lane_block)
    default_lanes = tuple(WorkersSettings().agent_runtime.lanes)

    assert documented_lanes == default_lanes


@pytest.mark.architecture
def test_contracts_websocket_payloads_match_current_surface() -> None:
    contracts = _read(CONTRACTS)
    ws_source = _read(API_WS)
    websocket_contract = _between(contracts, "## WebSocket at `/ws`", "## HTTP")

    for source_token in ('"event"', '"entities"', '"alerts"', '"token_intents"', '"token_resolutions"'):
        assert source_token in ws_source
    assert 'payload.get("type") == "notification"' in ws_source
    assert 'payload.get("type") == "live_market_update"' in ws_source

    for documented_token in (
        "event",
        "entities",
        "alerts",
        "token_intents",
        "token_resolutions",
        "notification",
        "social_event_enrichment_update",
        "live_market_update",
    ):
        assert f"`{documented_token}`" in websocket_contract
    assert "`enrichment`" not in websocket_contract


@pytest.mark.architecture
def test_contracts_news_item_detail_route_matches_fastapi_route() -> None:
    contracts = _read(CONTRACTS)
    news_routes = _read(NEWS_ROUTES)
    news_contract = _between(contracts, "News Intel contract:", "Token Radar market contract:")

    assert '@router.get("/news/items/{news_item_id}"' in news_routes
    assert "`/api/news/items/{news_item_id}`" in news_contract
    assert "`/api/news/{news_item_id}`" not in news_contract
