from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EQUITY_EVENT_INTEL_ROOT = ROOT / "src/gmgn_twitter_intel/domains/equity_event_intel"
API_ROOT = ROOT / "src/gmgn_twitter_intel/app/surfaces/api"
WEB_ROOT = ROOT / "web/src"

FORBIDDEN_TABLE_REFERENCES = (
    "token_radar_rows",
    "token_radar_current_rows",
    "token_radar_rank_history",
    "token_radar_snapshot_audit",
    "pulse_candidates",
    "news_items",
    "news_page_rows",
    "market_ticks",
)

FORBIDDEN_ROUTE_TOKENS = (
    "EquityEventSourceReconcileWorker",
    "EquityEventFetchWorker",
    "EquityEventProcessWorker",
    "EquityEventStoryProjectionWorker",
    "EquityEventPageProjectionWorker",
    "EquityEventBriefWorker",
    "httpx",
    "feedparser",
    "classify_equity_event(",
    "build_fact_candidates(",
)

PLANNED_SURFACE_PATHS = (
    API_ROOT / "routes_equity_event.py",
    API_ROOT / "routes_equity_events.py",
    API_ROOT / "routes_equity_event_intel.py",
    API_ROOT / "routes_stocks.py",
    WEB_ROOT / "routes/stocks.route.tsx",
    WEB_ROOT / "routes/equity-event.route.tsx",
    WEB_ROOT / "routes/equity-events.route.tsx",
    WEB_ROOT / "features/equity-event",
    WEB_ROOT / "features/equity-events",
    WEB_ROOT / "features/stocks",
)


def test_equity_event_intel_domain_exists_with_python_files() -> None:
    assert EQUITY_EVENT_INTEL_ROOT.exists()
    assert list(EQUITY_EVENT_INTEL_ROOT.rglob("*.py"))


def test_equity_event_intel_does_not_reference_forbidden_cross_domain_tables() -> None:
    for path in EQUITY_EVENT_INTEL_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_TABLE_REFERENCES:
            assert forbidden not in text, f"{path} references forbidden cross-domain table {forbidden}"


def test_equity_event_surfaces_stay_read_side_when_present() -> None:
    for path in _existing_surface_files():
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_ROUTE_TOKENS:
            assert forbidden not in text, f"{path} contains write-side or provider token {forbidden}"


def _existing_surface_files() -> list[Path]:
    files: list[Path] = []
    for path in PLANNED_SURFACE_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(candidate for candidate in path.rglob("*") if candidate.is_file()))
    return files
