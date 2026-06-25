from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_token_intent_lookup_read_limits_reject_runtime_int_repairs() -> None:
    intent_source = _read("src/parallax/domains/token_intel/repositories/token_intent_repository.py")
    lookup_source = _read("src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py")
    combined = intent_source + lookup_source

    assert "max(0, int(limit))" not in combined
    assert "token_intent_recent_unresolved_limit_required" in intent_source
    assert "token_intent_lookup_limit_required" in lookup_source
