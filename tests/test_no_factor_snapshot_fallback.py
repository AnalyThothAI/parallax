from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src" / "gmgn_twitter_intel"
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

FACTOR_SNAPSHOT_PRODUCER_FILES = (
    SRC_ROOT / "domains" / "token_intel" / "_constants.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "factor_snapshot.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "cross_section_normalizer.py",
    SRC_ROOT / "domains" / "token_intel" / "scoring" / "factor_cohort.py",
    SRC_ROOT / "domains" / "token_intel" / "services" / "token_radar_projection.py",
)

FACTOR_SNAPSHOT_FALLBACK_PATTERNS = (
    "token_factor_snapshot_v1",
    "hard_gates",
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


def test_token_factor_snapshot_producers_have_no_legacy_snapshot_fallback_contract() -> None:
    offenders = _matches(
        list(FACTOR_SNAPSHOT_PRODUCER_FILES),
        patterns=FACTOR_SNAPSHOT_FALLBACK_PATTERNS,
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
