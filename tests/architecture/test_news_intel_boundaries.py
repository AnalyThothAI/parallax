from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEWS_INTEL_ROOT = ROOT / "src/gmgn_twitter_intel/domains/news_intel"
ROUTES_NEWS = ROOT / "src/gmgn_twitter_intel/app/surfaces/api/routes_news.py"
OPENNEWS_CLIENT = ROOT / "src/gmgn_twitter_intel/integrations/news_feeds/opennews_client.py"
NEWS_PROVIDER_WIRING = ROOT / "src/gmgn_twitter_intel/app/runtime/provider_wiring/news.py"

FORBIDDEN_IMPORTS = (
    "domains.token_intel.runtime",
    "domains.token_intel.services.token_radar_projection",
    "domains.pulse_lab",
    "domains.asset_market.runtime.market_tick",
)

FORBIDDEN_TABLE_REFERENCES = (
    "token_radar_rows",
    "token_radar_current_rows",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "pulse_candidates",
    "market_ticks",
)

FORBIDDEN_ROUTE_TOKENS = (
    "NewsFetchWorker",
    "NewsItemProcessWorker",
    "feedparser",
    "resolve(",
    "extract_",
)


def test_news_intel_domain_exists_with_python_files() -> None:
    assert NEWS_INTEL_ROOT.exists()
    assert list(NEWS_INTEL_ROOT.rglob("*.py"))


def test_news_intel_does_not_import_runtime_or_projection_neighbors() -> None:
    for path in NEWS_INTEL_ROOT.rglob("*.py"):
        text = path.read_text()
        for forbidden in FORBIDDEN_IMPORTS:
            assert forbidden not in text, f"{path} imports forbidden boundary {forbidden}"


def test_news_intel_does_not_write_or_reference_other_read_models() -> None:
    for path in NEWS_INTEL_ROOT.rglob("*.py"):
        text = path.read_text()
        for forbidden in FORBIDDEN_TABLE_REFERENCES:
            assert forbidden not in text, f"{path} references forbidden table {forbidden}"


def test_news_routes_stay_read_only_when_present() -> None:
    if not ROUTES_NEWS.exists():
        return

    text = ROUTES_NEWS.read_text()
    for forbidden in FORBIDDEN_ROUTE_TOKENS:
        assert forbidden not in text, f"{ROUTES_NEWS} contains write-side token {forbidden}"


def test_opennews_runtime_has_no_short_lived_websocket_fetch_path() -> None:
    forbidden_tokens = (
        "DEFAULT_OPENNEWS_WSS_URL",
        "news.subscribe",
        "news.unsubscribe",
        "_entry_from_message",
        "_fetch_mode",
        "_default_connect",
        "websockets.connect",
        "status_code=101",
    )
    combined = "\n".join(path.read_text() for path in (OPENNEWS_CLIENT, NEWS_PROVIDER_WIRING))

    for forbidden in forbidden_tokens:
        assert forbidden not in combined


def test_news_reliability_docs_pin_opennews_rest_only_worker_contract() -> None:
    text = " ".join((ROOT / "docs/RELIABILITY.md").read_text().split())

    assert "OpenNews provider ingestion is REST-only" in text
    assert "must not open short-lived WebSocket subscribe cycles" in text
    assert "separate provider input path" in text
