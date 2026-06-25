from __future__ import annotations

from pathlib import Path

import pytest

from parallax.domains.token_intel.scoring.factor_snapshot_contract import require_token_factor_snapshot

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "parallax"
WEB_SRC_ROOT = ROOT / "web" / "src"

LEGACY_BACKEND_PATTERNS = (
    "PulseThesis",
    "write_thesis",
    "thesis_provider",
    "thesis_client",
    "pulse_thesis",
    "radar_score_json",
    "market_context_json",
    "thesis_json",
    "confirmation_triggers_zh",
    "top_risks",
    "why_now_zh",
    "bull_case_zh",
    "bear_case_zh",
    "pulse_agent_asset_heat_min",
    "pulse_agent_asset_propagation_min",
    "pulse_agent_trade_heat_min",
    "pulse_agent_trade_quality_min",
    "pulse_agent_trade_propagation_min",
    "pulse_agent_tradeability_min",
    "pulse_agent_timing_min",
    "pulse_agent_confidence_min",
    "pulse_agent_token_watch_signal_min",
)

LEGACY_FRONTEND_PATTERNS = (
    "item.summary_zh",
    "why_now_zh",
    "radar_score_json",
    "market_context_json",
    "thesis_json",
    "confirmation_triggers_zh",
    "top_risks",
)

LEGACY_MARKET_OVERLAY_BACKEND_PATTERNS = (
    "_overlay_" + "live_market",
    "token_market_price_" + "baselines",
    '"live_' + 'market":',
    'row.get("live_' + 'market")',
    "row['live_" + "market']",
)

LEGACY_MARKET_OVERLAY_FRONTEND_PATTERNS = (
    "liveMarket" + "Updates[0]",
    ".live_" + "market",
    "row.live_" + "market",
    "radar.live_" + "market",
    "update.live_" + "market",
)

FACTOR_SNAPSHOT_PRODUCER_FILES = (
    SRC_ROOT / "domains" / "token_intel" / "_constants.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "factor_snapshot.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "cross_section_normalizer.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "factor_cohort.py",
    SRC_ROOT / "domains" / "token_intel" / "services" / "token_radar_projection.py",
)
TOKEN_FACTOR_EVALUATION_SERVICE = SRC_ROOT / "domains" / "token_intel" / "services" / "token_factor_evaluation.py"

FACTOR_SNAPSHOT_FALLBACK_PATTERNS = (
    "token_factor_snapshot_v1",
    "hard_gates",
)

STALE_FACTOR_SNAPSHOT_VALIDATOR_PATTERNS = (
    "require_token_factor_snapshot_v2",
    "is_token_factor_snapshot_v2",
    "requireTokenFactorSnapshotV2",
)

LEGACY_SCORING_MODULE_PATHS = (
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "social_heat_scoring.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "propagation_scoring.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "discussion_quality_scoring.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "tradeability_scoring.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "opportunity_scoring.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "timing_scoring.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "timeline_features.py",
)

LEGACY_SCORING_VERSION_PATTERNS = (
    "social_heat_v3",
    "propagation_v2",
    "discussion_quality_v3",
    "tradeability_v2",
    "social_opportunity_v4",
    "timing_v5",
)


def test_runtime_has_no_legacy_pulse_thesis_or_score_fallback_paths() -> None:
    offenders = _matches(
        _python_runtime_files(),
        patterns=LEGACY_BACKEND_PATTERNS,
    )

    assert offenders == []
    assert not (SRC_ROOT / "domains" / "pulse_lab" / "types" / "pulse_thesis.py").exists()


def test_frontend_runtime_has_no_legacy_signal_pulse_fallback_fields() -> None:
    offenders = _matches(
        _frontend_runtime_files(),
        patterns=LEGACY_FRONTEND_PATTERNS,
    )

    assert offenders == []


def test_no_runtime_legacy_market_payload_fallbacks() -> None:
    backend_offenders = _matches(
        _python_runtime_files(),
        patterns=LEGACY_MARKET_OVERLAY_BACKEND_PATTERNS,
    )
    frontend_offenders = _matches(
        _frontend_runtime_files(),
        patterns=LEGACY_MARKET_OVERLAY_FRONTEND_PATTERNS,
    )

    assert backend_offenders + frontend_offenders == []


def test_token_factor_snapshot_producers_have_no_legacy_snapshot_fallback_contract() -> None:
    offenders = _matches(
        list(FACTOR_SNAPSHOT_PRODUCER_FILES),
        patterns=FACTOR_SNAPSHOT_FALLBACK_PATTERNS,
    )

    assert offenders == []


def test_factor_snapshot_contract_rejects_old_family_before_missing_new_family() -> None:
    snapshot = _valid_factor_snapshot()
    snapshot["families"]["attention_heat"] = _family_block()

    with pytest.raises(ValueError, match=r"^factor_snapshot\.families\.attention_heat is not allowed$"):
        require_token_factor_snapshot(snapshot)


@pytest.mark.parametrize(
    ("section", "field", "error"),
    (
        ("composite", "rank_score", r"^factor_snapshot\.composite\.rank_score is required$"),
        ("composite", "recommended_decision", r"^factor_snapshot\.composite\.recommended_decision is required$"),
        ("gates", "max_decision", r"^factor_snapshot\.gates\.max_decision is required$"),
    ),
)
def test_factor_snapshot_contract_requires_core_score_decision_fields(section: str, field: str, error: str) -> None:
    snapshot = _valid_factor_snapshot()
    del snapshot[section][field]  # type: ignore[index]

    with pytest.raises(ValueError, match=error):
        require_token_factor_snapshot(snapshot)


def test_token_factor_evaluation_requires_formal_snapshot_rank_score_without_zero_default() -> None:
    source = TOKEN_FACTOR_EVALUATION_SERVICE.read_text()
    forbidden = (
        'float(composite.get("rank_score") or 0.0)',
        "return 0.0",
        "max(0, int(limit))",
    )
    required = (
        "require_token_factor_snapshot",
        'field_name="factor_snapshot_json"',
        'composite["rank_score"]',
        "token_factor_evaluation_limit_required",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_factor_evaluation_uses_snapshot_subject_identity_without_row_fallback() -> None:
    source = TOKEN_FACTOR_EVALUATION_SERVICE.read_text()
    forbidden = (
        'subject.get("target_type") or row.get("target_type")',
        'subject.get("target_id") or row.get("target_id")',
        "_market_tick_target(row=row",
        'snapshot = _mapping(row.get("factor_snapshot_json"))',
        'subject_type in {"chain_token", "cex_symbol"}',
    )
    required = (
        "_subject_identity(subject)",
        "factor_snapshot_json.subject.target_type is required",
        "factor_snapshot_json.subject.target_id is required",
        "factor_snapshot_json.subject.target_type is invalid",
        "_market_tick_target(subject=subject)",
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_factor_evaluation_uses_snapshot_provenance_time_without_zero_default() -> None:
    source = TOKEN_FACTOR_EVALUATION_SERVICE.read_text()
    forbidden = (
        'int(row.get("computed_at_ms") or 0)',
        'row.get("computed_at_ms") or 0',
    )
    required = (
        "_snapshot_computed_at_ms(snapshot)",
        'snapshot["provenance"]',
        'provenance["computed_at_ms"]',
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_factor_evaluation_reads_family_scores_from_formal_families_without_composite_alias() -> None:
    source = TOKEN_FACTOR_EVALUATION_SERVICE.read_text()
    forbidden = (
        'composite.get("family_scores")',
        'snapshot.get("composite")',
    )
    required = (
        'snapshot["families"]',
        "_family_score(families, family)",
        'family_block["score"]',
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_factor_evaluation_uses_cex_subject_market_identity_without_market_context_or_alias_fallback() -> None:
    source = TOKEN_FACTOR_EVALUATION_SERVICE.read_text()
    forbidden = (
        'decision_latest = _mapping(market.get("decision_latest"))',
        'subject.get("provider") or decision_latest.get("provider")',
        'subject.get("native_market_id") or subject.get("instrument")',
        'subject.get("instrument")',
    )
    required = (
        'provider = _clean(subject.get("provider"))',
        'native_market_id = _clean(subject.get("native_market_id"))',
        'return "cex_symbol", f"{provider}:{native_market_id}"',
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_token_factor_evaluation_uses_asset_subject_market_identity_without_alias_fallback() -> None:
    source = TOKEN_FACTOR_EVALUATION_SERVICE.read_text()
    forbidden = (
        'subject.get("chain") or subject.get("chain_id")',
        'subject.get("address") or subject.get("asset_address")',
        'subject.get("chain_id")',
        'subject.get("asset_address")',
    )
    required = (
        'chain = _clean(subject.get("chain"))',
        'address = _clean(subject.get("address"))',
    )

    assert [token for token in forbidden if token in source] == []
    assert [token for token in required if token not in source] == []


def test_python_runtime_has_no_stale_factor_snapshot_validator_names() -> None:
    offenders = _matches(
        _python_runtime_files(),
        patterns=STALE_FACTOR_SNAPSHOT_VALIDATOR_PATTERNS,
    )

    assert offenders == []


def test_frontend_runtime_has_no_stale_factor_snapshot_validator_names() -> None:
    offenders = _matches(
        _frontend_runtime_files(),
        patterns=STALE_FACTOR_SNAPSHOT_VALIDATOR_PATTERNS,
    )

    assert offenders == []


def test_legacy_token_radar_scoring_modules_are_removed() -> None:
    assert [path.relative_to(ROOT).as_posix() for path in LEGACY_SCORING_MODULE_PATHS if path.exists()] == []


def test_runtime_has_no_legacy_scoring_version_literals() -> None:
    offenders = _matches(
        _python_runtime_files(),
        patterns=LEGACY_SCORING_VERSION_PATTERNS,
    )

    assert offenders == []


def test_pulse_worker_uses_token_radar_factor_family_constant_as_single_source() -> None:
    worker_path = SRC_ROOT / "domains" / "pulse_lab" / "runtime" / "pulse_candidate_worker.py"
    assert "V2_ALPHA_FAMILIES" not in worker_path.read_text()


def _python_runtime_files() -> list[Path]:
    files: list[Path] = []
    for path in SRC_ROOT.rglob("*.py"):
        if "alembic/versions" in path.as_posix():
            continue
        files.append(path)
    return files


def _frontend_runtime_files() -> list[Path]:
    files: list[Path] = []
    for path in WEB_SRC_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        if ".test." in path.name or "__tests__" in path.parts:
            continue
        files.append(path)
    return files


def _matches(files: list[Path], *, patterns: tuple[str, ...]) -> list[str]:
    offenders: list[str] = []
    for path in files:
        text = path.read_text()
        offenders.extend(f"{path.relative_to(ROOT).as_posix()}: {pattern}" for pattern in patterns if pattern in text)
    return offenders


def _valid_factor_snapshot() -> dict[str, object]:
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {"target_type": "Asset", "target_id": "asset:test"},
        "market": {
            "event_anchor": None,
            "decision_latest": None,
            "readiness": {
                "anchor_status": "missing",
                "latest_status": "missing",
                "dex_floor_status": "missing_fields",
                "missing_fields": [
                    "holders",
                    "liquidity_usd",
                    "market_cap_usd",
                ],
                "stale_fields": [],
            },
        },
        "gates": {
            "eligible_for_high_alert": False,
            "blocked_reasons": [],
            "risk_reasons": [],
            "discard_cap_reasons": [],
            "max_decision": "discard",
        },
        "data_health": {
            "identity": "ready",
            "market": "missing",
            "social": "missing",
            "alpha": "missing",
        },
        "families": {
            "social_heat": _family_block(),
            "social_propagation": _family_block(),
            "semantic_catalyst": _family_block(),
            "timing_risk": _family_block(),
        },
        "normalization": {
            "status": "no_signal",
            "cohort_status": "insufficient",
            "cohort": {},
            "factor_ranks": {},
            "alpha_rank": None,
        },
        "composite": {
            "raw_alpha_score": 0,
            "rank_score": 0,
            "family_scores": {},
            "recommended_decision": "discard",
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1},
    }


def _family_block() -> dict[str, object]:
    return {
        "raw_score": 0,
        "score": 0,
        "weight": 0,
        "data_health": "missing",
        "facts": {},
        "factors": {},
    }
