from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DELETED_PATHS = (
    ROOT / "src/parallax/domains/pulse_lab",
    ROOT / "src/parallax/app/runtime/worker_factories/pulse.py",
    ROOT / "src/parallax/app/surfaces/api/routes_pulse.py",
    ROOT / "src/parallax/app/surfaces/cli/commands/pulse_replay.py",
    ROOT / "src/parallax/domains/notifications/services/pulse_surface_card.py",
    ROOT / "src/parallax/integrations/model_execution/pulse_decision_agent_client.py",
    ROOT / "web/src/features/signal-lab",
    ROOT / "docs/prototypes/obsidian-desk-v2-static.html",
    ROOT / "docs/prototypes/token-radar-redesign-static.html",
)

CURRENT_SOURCE_ROOTS = (
    ROOT / "src/parallax/app",
    ROOT / "src/parallax/domains",
    ROOT / "src/parallax/integrations",
    ROOT / "src/parallax/platform",
    ROOT / "web/src",
)

CURRENT_CONTRACT_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "README.md",
    ROOT / "config.example.yaml",
    ROOT / "docs/AGENT_EXECUTION.md",
    ROOT / "docs/ARCHITECTURE.md",
    ROOT / "docs/CONTRACTS.md",
    ROOT / "docs/FRONTEND.md",
    ROOT / "docs/RELIABILITY.md",
    ROOT / "docs/TESTING.md",
    ROOT / "docs/TECH_DEBT.md",
    ROOT / "docs/WORKERS.md",
    ROOT / "docs/WORKER_FLOW.md",
    ROOT / "docs/agent-playbook/read-model-change-checklist.md",
    ROOT / "docs/agent-playbook/task-reading-matrix.md",
    ROOT / "docs/generated/cli-help.md",
    ROOT / "docs/generated/db-schema.md",
    ROOT / "docs/generated/openapi.json",
)

ALEMBIC_VERSIONS = ROOT / "src/parallax/platform/db/alembic/versions"
TEXT_SUFFIXES = {".css", ".json", ".md", ".py", ".ts", ".tsx", ".yaml", ".yml"}

FORBIDDEN_CURRENT_TOKENS = (
    "pulse_lab",
    "pulse_candidate",
    "pulsecandidate",
    "pulse candidate",
    "pulse trigger",
    "pulse decision",
    "pulse overlay",
    "pulse evidence",
    "pulse.decision",
    "pulse_agent_jobs",
    "pulse_trigger_dirty_targets",
    "signal_pulse_candidate",
    "signalpulse",
    "signal pulse",
    "signal-pulse",
    "signal lab",
    "/api/signal-lab/pulse",
    "pulse_overlay",
)

AUDIT = ROOT / "docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md"
AUDIT_REQUIRED_EVIDENCE = (
    "13,298",
    "19,206",
    "1,055",
    "21,172",
    "35,561,472",
    "52",
    "6,193,803",
    "Kappa/CQRS",
    "保留",
    "移除",
    "延期",
)


def test_signal_pulse_current_runtime_surface_is_absent() -> None:
    existing_paths = [str(path.relative_to(ROOT)) for path in DELETED_PATHS if path.exists()]

    assert existing_paths == []


def test_signal_pulse_current_contract_tokens_are_absent() -> None:
    paths = _text_files(CURRENT_SOURCE_ROOTS)
    paths.extend(path for path in CURRENT_CONTRACT_FILES if path.exists())

    assert _token_hits(paths, FORBIDDEN_CURRENT_TOKENS) == []


def test_architecture_audit_records_measured_hard_cut_evidence() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    missing = [token for token in AUDIT_REQUIRED_EVIDENCE if token not in text]

    assert missing == []


def _text_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if ALEMBIC_VERSIONS in path.parents:
                continue
            files.append(path)
    return sorted(files)


def _token_hits(paths: list[Path], tokens: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        hits.extend(f"{path.relative_to(ROOT)} contains {token}" for token in tokens if token in text)
    return hits
