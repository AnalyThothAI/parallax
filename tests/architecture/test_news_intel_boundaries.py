from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEWS_INTEL_ROOT = ROOT / "src/gmgn_twitter_intel/domains/news_intel"
ROUTES_NEWS = ROOT / "src/gmgn_twitter_intel/app/surfaces/api/routes_news.py"

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
