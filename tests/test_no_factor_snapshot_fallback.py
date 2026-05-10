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
        for pattern in patterns:
            if pattern in text:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {pattern}")
    return offenders
