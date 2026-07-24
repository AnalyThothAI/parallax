from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_deepagents_macro_research_docs_match_runtime_contract() -> None:
    architecture = _read("docs/ARCHITECTURE.md")
    contracts = _read("docs/CONTRACTS.md")
    operations = _read("docs/OPERATIONS.md")
    security = _read("docs/SECURITY.md")
    setup = _read("docs/SETUP.md")
    frontend = _read("docs/FRONTEND.md")
    postgres = _read("docs/references/POSTGRES_PERFORMANCE.md")
    domain = _read("src/parallax/domains/macro_intel/ARCHITECTURE.md")

    assert "`macro_research` worker" in architecture
    assert "todo plan, evidence selection, virtual-filesystem notes" in architecture
    assert "production PostgreSQL checkpointer" in architecture
    assert "one parameterized live-fact read family and one research read" in contracts
    assert "/api/macro/evidence/{view_id}" in contracts
    assert contracts.count("/api/macro/research") >= 2
    assert "`historical`, `generating`, `failed`, or `missing`" in contracts
    assert "does not reject content through language, coverage, readiness" in contracts
    assert "`AsyncPostgresSaver`" in operations
    assert "zero model calls and zero publication writes" in operations
    assert "native todo planning, checkpoint-backed virtual" in security
    assert "real `execute`" in security
    assert "never exposes checkpoint\npayloads" in security
    assert "`workers.macro_research`" in setup
    assert "`model`, `model_request_timeout_seconds`" in setup
    assert "`max_tokens`" in setup
    assert "`/macro` is the six-category live-fact dashboard" in frontend
    assert "`/macro/research` is the separate completed-session research workbench" in frontend
    assert "`macro_research_publications`" in postgres
    assert "`macro_research_publications`" in domain
    assert "session performs zero model calls and zero serving writes on replay." in domain
    assert "evidence sufficiency" in security
    assert "professional judgment" in security

    combined = "\n".join((architecture, contracts, operations, security, setup, frontend, postgres, domain))
    retired_markers = (
        "macro_decision_v2",
        "macro_view_projection",
        "daily_macro_judgment",
        "macro_judgment_publications",
        "macro_projection_dirty_targets",
        "macro_observation_series_rows",
        "/api/macro/overview",
        "/api/macro/cross-asset",
        "/api/macro/rates-inflation",
        "/api/macro/growth-labor",
        "/api/macro/liquidity-funding",
        "/api/macro/credit",
        "/api/macro/series",
        "/api/macro/daily-judgment",
        "risk_lanes",
        "experimental_shadow_research",
    )
    for marker in retired_markers:
        assert marker not in combined


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
