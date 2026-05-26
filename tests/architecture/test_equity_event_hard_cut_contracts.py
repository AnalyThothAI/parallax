from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EQUITY_EVENT_SERVICES = (
    ROOT / "src/gmgn_twitter_intel/domains/equity_event_intel/services/fact_candidates.py",
    ROOT / "src/gmgn_twitter_intel/domains/equity_event_intel/services/brief_input.py",
)
ALEMBIC_VERSIONS = ROOT / "src/gmgn_twitter_intel/platform/db/alembic/versions"
PUBLIC_CONTRACT_FILES = (
    ROOT / "docs/generated/openapi.json",
    ROOT / "src/gmgn_twitter_intel/app/surfaces/api/schemas.py",
    ROOT / "web/src/lib/api/client.ts",
    ROOT / "web/src/features/equity-events/model/equityEventTypes.ts",
    ROOT / "web/src/lib/types/openapi.ts",
)


def test_equity_fact_and_brief_inputs_do_not_use_raw_payload_text_as_evidence() -> None:
    forbidden_patterns = (
        'raw_payload.get("title")',
        'raw_payload.get("description")',
        'raw_payload.get("body_text")',
        '"press_release_text"',
        '"body_text"',
    )

    hits = [
        f"{path.relative_to(ROOT)} contains {pattern}"
        for path in EQUITY_EVENT_SERVICES
        for pattern in forbidden_patterns
        if pattern in path.read_text()
    ]

    assert hits == []


def test_equity_event_evidence_hard_cut_migration_exists_with_status_columns() -> None:
    required_tokens = (
        "equity_event_evidence_artifacts",
        "evidence_status",
        "brief_readiness_status",
    )
    matching_migrations = [
        path.relative_to(ROOT)
        for path in ALEMBIC_VERSIONS.glob("*.py")
        if all(token in path.read_text() for token in required_tokens)
    ]

    assert matching_migrations, (
        "expected an alembic migration containing equity_event_evidence_artifacts, "
        "evidence_status, and brief_readiness_status"
    )


def test_public_equity_event_contracts_do_not_expose_global_brief_pending_count() -> None:
    hits = [str(path.relative_to(ROOT)) for path in PUBLIC_CONTRACT_FILES if "brief_pending_count" in path.read_text()]

    assert hits == []
