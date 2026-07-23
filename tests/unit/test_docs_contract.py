from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_daily_macro_judgment_docs_match_runtime_contract() -> None:
    architecture = _read("docs/ARCHITECTURE.md")
    contracts = _read("docs/CONTRACTS.md")
    operations = _read("docs/OPERATIONS.md")
    security = _read("docs/SECURITY.md")
    setup = _read("docs/SETUP.md")
    domain = _read("src/parallax/domains/macro_intel/ARCHITECTURE.md")

    assert "daily_macro_judgment" in architecture
    assert "one DeepAgents Analyst -> native task -> one isolated Reviewer" in architecture
    assert "/api/macro/daily-judgment" in contracts
    assert "experimental_shadow_research" in contracts
    assert "`historical`, `stale`, `pending`, `running`, `retryable`, `blocked`, `failed`" in contracts
    assert "or `missing`" in contracts
    assert "zero model calls and zero publication" in operations
    assert "filesystem,\nexecution, search, and general-purpose subagent tools are excluded" in security
    assert "`workers.daily_macro_judgment`" in setup
    assert "`analyst_model`\nand `reviewer_model`" in setup
    assert "Analyst and Reviewer model names" in security
    assert "`macro_judgment_publications`" in domain
    assert "Same-session replay performs zero model calls and zero writes." in domain

    combined = "\n".join((architecture, contracts, operations, security, setup, domain))
    assert "only dormant provider credentials" not in combined
    assert "Production bootstrap does not instantiate a\nmodel consumer" not in combined


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
