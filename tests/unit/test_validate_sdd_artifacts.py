from __future__ import annotations

from pathlib import Path

from scripts.validate_sdd_artifacts import (
    ArtifactRecord,
    SddFeature,
    _spec_background_issues,
    verify_gate_evidence_issues,
)


def _feature_with_background(
    root: Path,
    *,
    state: str,
    background: str,
) -> tuple[SddFeature, ArtifactRecord]:
    feature_path = root / "docs" / "sdd" / "features" / state / "2026-01-01-example"
    artifact_path = feature_path / "spec.md"
    artifact = ArtifactRecord(
        name="spec.md",
        path=artifact_path,
        relative_path=str(artifact_path.relative_to(root)),
        text=f"# Spec\n\n## Background\n\n{background}\n",
        status="verified" if state == "completed" else "in progress",
        fields={},
    )
    feature = SddFeature(
        slug=feature_path.name,
        state=state,
        path=feature_path,
        relative_path=str(feature_path.relative_to(root)),
        artifacts={"spec.md": artifact},
        tasks=(),
    )
    return feature, artifact


def test_completed_spec_keeps_deleted_source_as_historical_citation(tmp_path: Path) -> None:
    feature, artifact = _feature_with_background(
        tmp_path,
        state="completed",
        background=(
            "The retired worker used a durable ledger (`src/parallax/domains/news_intel/runtime/retired_worker.py:12`)."
        ),
    )

    assert _spec_background_issues(feature, artifact) == []


def test_active_spec_requires_cited_source_to_exist(tmp_path: Path) -> None:
    feature, artifact = _feature_with_background(
        tmp_path,
        state="active",
        background=(
            "The current worker uses a durable ledger (`src/parallax/domains/news_intel/runtime/missing_worker.py:12`)."
        ),
    )

    issues = _spec_background_issues(feature, artifact)

    assert len(issues) == 1
    assert issues[0].code == "spec-background-uncited"
    assert "does not exist" in issues[0].message


def test_completed_spec_still_requires_citation_syntax(tmp_path: Path) -> None:
    feature, artifact = _feature_with_background(
        tmp_path,
        state="completed",
        background="The retired worker used a durable ledger.",
    )

    issues = _spec_background_issues(feature, artifact)

    assert len(issues) == 1
    assert issues[0].code == "spec-background-uncited"
    assert "missing citation" in issues[0].message


def _feature_with_verification(
    root: Path,
    *,
    evidence_rows: str,
    command_transcript: str,
) -> SddFeature:
    feature_path = root / "docs" / "sdd" / "features" / "completed" / "2026-01-01-example"
    spec_text = """# Spec

## Acceptance criteria

- AC1. WHEN the first behavior is checked THEN the system SHALL pass.
- AC2. WHEN the second behavior is checked THEN the system SHALL pass.
"""
    verification_text = f"""# Verification

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
{evidence_rows}

## Verification commands

```text
{command_transcript}
```
"""
    spec = ArtifactRecord(
        name="spec.md",
        path=feature_path / "spec.md",
        relative_path=str((feature_path / "spec.md").relative_to(root)),
        text=spec_text,
        status="verified",
        fields={},
    )
    verification = ArtifactRecord(
        name="verification.md",
        path=feature_path / "verification.md",
        relative_path=str((feature_path / "verification.md").relative_to(root)),
        text=verification_text,
        status="verified",
        fields={},
    )
    return SddFeature(
        slug=feature_path.name,
        state="completed",
        path=feature_path,
        relative_path=str(feature_path.relative_to(root)),
        artifacts={"spec.md": spec, "verification.md": verification},
        tasks=(),
    )


def test_verified_feature_accepts_relevant_commands_without_repository_wide_gate(tmp_path: Path) -> None:
    feature = _feature_with_verification(
        tmp_path,
        evidence_rows=(
            "| AC1 - focused static behavior. | Pass | `make check` exited 0. |\n"
            "| AC2 - focused integration behavior. | Pass | "
            "`uv run pytest tests/integration/test_example.py -q` exited 0. |"
        ),
        command_transcript=(
            "$ make check\n"
            "checks passed\n"
            "exit code: 0\n\n"
            "$ uv run pytest tests/integration/test_example.py -q\n"
            "1 passed\n"
            "exit code: 0"
        ),
    )

    assert verify_gate_evidence_issues(feature) == []


def test_verified_feature_rejects_cited_command_without_successful_evidence(tmp_path: Path) -> None:
    feature = _feature_with_verification(
        tmp_path,
        evidence_rows=(
            "| AC1 - focused static behavior. | Pass | `make check` exited 0. |\n"
            "| AC2 - focused integration behavior. | Pass | "
            "`uv run pytest tests/integration/test_example.py -q` exited 0. |"
        ),
        command_transcript=(
            "$ make check\n"
            "checks passed\n"
            "exit code: 0\n\n"
            "$ uv run pytest tests/integration/test_example.py -q\n"
            "1 failed\n"
            "exit code: 1"
        ),
    )

    issues = verify_gate_evidence_issues(feature)

    assert [issue.code for issue in issues] == ["verified-missing-spec-compliance-evidence"]


def test_verified_feature_rejects_acceptance_row_without_command_evidence(tmp_path: Path) -> None:
    feature = _feature_with_verification(
        tmp_path,
        evidence_rows=(
            "| AC1 - focused static behavior. | Pass | `make check` exited 0. |\n"
            "| AC2 - focused integration behavior. | Pass | Reviewed manually. |"
        ),
        command_transcript="$ make check\nchecks passed\nexit code: 0",
    )

    issues = verify_gate_evidence_issues(feature)

    assert [issue.code for issue in issues] == ["verified-missing-spec-compliance-evidence"]
