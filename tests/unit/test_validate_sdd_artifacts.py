from __future__ import annotations

from pathlib import Path

from scripts.validate_sdd_artifacts import (
    ArtifactRecord,
    SddFeature,
    _spec_background_issues,
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
