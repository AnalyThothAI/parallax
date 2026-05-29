from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DELETED_PATHS = (
    ROOT / "src/gmgn_twitter_intel/domains/equity_event_intel",
    ROOT / "src/gmgn_twitter_intel/app/surfaces/api/routes_equity_events.py",
    ROOT / "src/gmgn_twitter_intel/app/runtime/worker_factories/equity_event_intel.py",
    ROOT / "src/gmgn_twitter_intel/app/runtime/provider_wiring/equity_events.py",
    ROOT / "src/gmgn_twitter_intel/integrations/equity_events",
    ROOT / "src/gmgn_twitter_intel/integrations/model_execution/equity_event_brief_agent_client.py",
    ROOT / "web/src/features/equity-events",
    ROOT / "web/src/routes/equity-events.route.tsx",
)

SOURCE_ROOTS = (
    ROOT / "src/gmgn_twitter_intel/app",
    ROOT / "src/gmgn_twitter_intel/platform",
    ROOT / "src/gmgn_twitter_intel/integrations",
    ROOT / "web/src",
)

DOC_CONFIG_FILES = (
    ROOT / "config.example.yaml",
    ROOT / "docs/ARCHITECTURE.md",
    ROOT / "docs/CONTRACTS.md",
    ROOT / "docs/FRONTEND.md",
    ROOT / "docs/WORKERS.md",
)

ALEMBIC_VERSIONS = ROOT / "src/gmgn_twitter_intel/platform/db/alembic/versions"
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".css", ".yaml", ".yml"}

FORBIDDEN_RUNTIME_TOKENS = (
    "equity_event_intel",
    "routes_equity_events",
    "EquityEventIntel",
    "EquityEventBrief",
    "EquityEventDocument",
    "equity_event.brief",
    "equity_event_source_reconcile",
    "equity_event_fetch",
    "equity_event_evidence_hydration",
    "equity_event_process",
    "equity_event_story_projection",
    "equity_event_page_projection",
    "equity_event_brief",
    "/api/equity-events",
    "/earnings",
)

FORBIDDEN_DOC_TOKENS = (
    "equity_event_intel",
    "/api/equity-events",
    "/earnings",
    "equity_event.brief",
    "equity_event_",
)


def test_earnings_product_paths_are_deleted() -> None:
    existing_paths = [str(path.relative_to(ROOT)) for path in DELETED_PATHS if path.exists()]

    assert existing_paths == []


def test_earnings_runtime_tokens_are_absent_from_runtime_and_frontend_sources() -> None:
    hits = _token_hits(_text_files(SOURCE_ROOTS), FORBIDDEN_RUNTIME_TOKENS)

    assert hits == []


def test_earnings_doc_tokens_are_absent_from_canonical_docs_and_config() -> None:
    existing_files = [path for path in DOC_CONFIG_FILES if path.exists()]
    hits = _token_hits(existing_files, FORBIDDEN_DOC_TOKENS)

    assert hits == []


def _text_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        candidates = (root,) if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if ALEMBIC_VERSIONS in path.parents:
                continue
            files.append(path)
    return sorted(files)


def _token_hits(paths: list[Path], tokens: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        hits.extend(f"{path.relative_to(ROOT)} contains {token}" for token in tokens if token in text)
    return hits
