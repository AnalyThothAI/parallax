from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_evidence_repository_read_limits_reject_runtime_int_repairs() -> None:
    evidence_source = _read("src/parallax/domains/evidence/repositories/evidence_repository.py")
    entity_source = _read("src/parallax/domains/evidence/repositories/entity_repository.py")
    combined = evidence_source + entity_source

    assert "max(0, int(limit))" not in combined
    assert "max(0, int(per_filter_limit))" not in evidence_source
    assert "evidence_recent_events_limit_required" in evidence_source
    assert "evidence_token_filter_limit_required" in evidence_source
    assert "evidence_token_filter_per_filter_limit_required" in evidence_source
    assert "entity_repository_find_limit_required" in entity_source
