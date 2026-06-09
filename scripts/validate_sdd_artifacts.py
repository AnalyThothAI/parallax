from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDD_FEATURES = ROOT / "docs" / "sdd" / "features"
ARTIFACTS = ("spec.md", "plan.md", "tasks.md", "verification.md")
ACTIVE_STATUSES = {"draft", "approved", "in progress", "review", "blocked"}
COMPLETED_STATUSES = {"verified", "superseded"}
STATUS_RE = re.compile(r"^\s*(?:\*\*)?Status(?:\*\*)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<value>.+?)\s*$")
TASK_RE = re.compile(r"^###\s+Task\b", re.IGNORECASE | re.MULTILINE)
TASK_FIELD_RE = re.compile(r"^\s*-\s+\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<value>.*)$", re.MULTILINE)
CHECK_ALL_RE = re.compile(r"\$\s*make check-all[\s\S]*?exit code:\s*0\b", re.IGNORECASE)
SKIPPED_RE = re.compile(r"Number of skipped tests in the run above:\s*(?P<count>\d+)", re.IGNORECASE)

SECTION_REQUIREMENTS = {
    "spec.md": ("## Clarifications", "## Requirement Checklist", "## Acceptance criteria"),
    "plan.md": ("## Analyze Gate", "## Acceptance test commands"),
    "tasks.md": ("## Gate Compliance", "## Tasks"),
    "verification.md": (
        "## Spec compliance",
        "## Verification commands",
        "## Coverage",
        "## Skipped tests",
        "## E2E golden path",
    ),
}
METADATA_REQUIREMENTS = {
    "spec.md": ("status", "date", "owner", "approved by", "approved at"),
    "plan.md": ("status", "date", "worktree", "branch", "approved by", "approved at"),
    "tasks.md": ("status", "owning plan", "worktree", "branch", "approved by", "approved at"),
    "verification.md": (
        "status",
        "date",
        "owning spec",
        "owning plan",
        "branch",
        "worktree",
        "approved by",
        "approved at",
    ),
}
TASK_REQUIRED_FIELDS = (
    "file(s)",
    "owner",
    "depends on",
    "touch set",
    "conflict set",
    "failing test first",
    "subagent handoff",
    "implementation",
    "verification",
    "review owner",
    "status",
)
PLACEHOLDER_VALUES = {"", "...", "tbd", "todo", "pending", "<pending>", "<none>"}
CONTRADICTION_PHRASES = (
    "not final evidence",
    "stopped before completion",
    "was stopped",
    "exit code: pending",
    "pending final run",
    "skip_e2e=1",
)
KNOWN_ISSUE_CODES = (
    "review-lifecycle",
    "missing-status",
    "missing-artifact",
    "missing-gate-section",
    "missing-approval-metadata",
    "task-missing-coordination-fields",
    "task-incomplete-in-verified-feature",
    "verified-missing-check-all",
    "verified-contradicts-evidence",
    "verified-unexplained-skips",
    "superseded-missing-successor",
    "active-touch-conflict",
)


@dataclass(frozen=True)
class SddIssue:
    code: str
    path: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ArtifactRecord:
    name: str
    path: Path
    relative_path: str
    text: str
    status: str
    fields: dict[str, str]
    missing: bool = False


@dataclass(frozen=True)
class TaskRecord:
    title: str
    fields: dict[str, str]


@dataclass(frozen=True)
class SddFeature:
    slug: str
    state: str
    path: Path
    relative_path: str
    artifacts: dict[str, ArtifactRecord]
    tasks: tuple[TaskRecord, ...]

    @property
    def status(self) -> str:
        verification = self.artifacts.get("verification.md")
        if verification and verification.status != "missing-file":
            return verification.status
        for artifact_name in ARTIFACTS:
            artifact = self.artifacts.get(artifact_name)
            if artifact and artifact.status != "missing-file":
                return artifact.status
        return "missing-file"

    @property
    def fields(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for artifact_name in ARTIFACTS:
            artifact = self.artifacts.get(artifact_name)
            if artifact:
                merged.update({key: value for key, value in artifact.fields.items() if key not in merged})
        return merged

    @property
    def owner(self) -> str:
        return self.fields.get("owner") or _first_task_field(self.tasks, "owner") or "unspecified"

    @property
    def worktree(self) -> str:
        return self.fields.get("worktree", "unspecified")

    @property
    def branch(self) -> str:
        return self.fields.get("branch", "unspecified")

    @property
    def touch_set(self) -> tuple[str, ...]:
        return _task_set(self.tasks, "touch set")

    @property
    def conflict_set(self) -> tuple[str, ...]:
        return _task_set(self.tasks, "conflict set")

    @property
    def blocked(self) -> str:
        if self.status.lower() == "blocked":
            return self.fields.get("blocked reason", "blocked")
        return "-"

    @property
    def verification(self) -> str:
        normalized = self.status.lower()
        if normalized == "verified":
            return "verified"
        if normalized == "superseded":
            return "superseded"
        return "not-verified"


def scan_sdd_features(root: Path = ROOT) -> list[SddFeature]:
    features_root = root / "docs" / "sdd" / "features"
    records: list[SddFeature] = []
    for state in ("active", "completed"):
        lane_root = features_root / state
        if not lane_root.exists():
            continue
        for feature_dir in sorted(
            path for path in lane_root.iterdir() if path.is_dir() and not path.name.startswith(".")
        ):
            artifacts = {
                artifact_name: _read_artifact(root, feature_dir / artifact_name, artifact_name)
                for artifact_name in ARTIFACTS
            }
            records.append(
                SddFeature(
                    slug=feature_dir.name,
                    state=state,
                    path=feature_dir,
                    relative_path=_relative(root, feature_dir),
                    artifacts=artifacts,
                    tasks=tuple(_parse_tasks(artifacts["tasks.md"].text)),
                )
            )
    return records


def validate_sdd_root(root: Path = ROOT) -> list[SddIssue]:
    features = scan_sdd_features(root)
    issues: list[SddIssue] = []
    for feature in features:
        issues.extend(_feature_issues(feature))
    issues.extend(_active_touch_conflicts(features))
    return sorted(issues, key=lambda issue: (issue.path, issue.code, issue.message))


def issue_counts(issues: Iterable[SddIssue]) -> Counter[str]:
    counts: Counter[str] = Counter({code: 0 for code in KNOWN_ISSUE_CODES})
    counts.update(issue.code for issue in issues)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate executable SDD feature records")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to validate")
    parser.add_argument("--check", action="store_true", help="exit non-zero when issues are present")
    args = parser.parse_args(argv)

    issues = validate_sdd_root(args.root)
    if not issues:
        print("SDD artifact validation passed.")
        return 0

    for issue in issues:
        print(f"{issue.severity}: {issue.code}: {issue.path}: {issue.message}", file=sys.stderr)
    return 1 if args.check else 0


def _read_artifact(root: Path, path: Path, artifact_name: str) -> ArtifactRecord:
    if not path.exists():
        return ArtifactRecord(
            name=artifact_name,
            path=path,
            relative_path=_relative(root, path),
            text="",
            status="missing-file",
            fields={},
            missing=True,
        )
    text = path.read_text(encoding="utf-8")
    fields = _extract_fields(text)
    return ArtifactRecord(
        name=artifact_name,
        path=path,
        relative_path=_relative(root, path),
        text=text,
        status=_extract_status(text),
        fields=fields,
    )


def _feature_issues(feature: SddFeature) -> list[SddIssue]:
    issues: list[SddIssue] = []
    for artifact in feature.artifacts.values():
        issues.extend(_artifact_issues(feature, artifact))
    if feature.status.lower() == "superseded":
        return issues + _superseded_issues(feature)
    issues.extend(_task_issues(feature))
    if feature.status.lower() == "verified":
        issues.extend(_verified_issues(feature))
    return issues


def _artifact_issues(feature: SddFeature, artifact: ArtifactRecord) -> list[SddIssue]:
    issues: list[SddIssue] = []
    if artifact.missing:
        issues.append(_issue("missing-artifact", artifact, f"{artifact.name} is missing"))
        return issues
    normalized_status = artifact.status.lower()
    if normalized_status in {"unspecified", "missing-file"}:
        issues.append(_issue("missing-status", artifact, f"{artifact.name} has no Status field"))
    elif feature.state == "active" and normalized_status not in ACTIVE_STATUSES:
        issues.append(_issue("review-lifecycle", artifact, f"{artifact.status!r} is not valid for active lane"))
    elif feature.state == "completed" and normalized_status not in COMPLETED_STATUSES:
        issues.append(_issue("review-lifecycle", artifact, f"{artifact.status!r} is not valid for completed lane"))

    if normalized_status == "superseded":
        return issues

    missing_fields = [
        field for field in METADATA_REQUIREMENTS[artifact.name] if _is_placeholder(artifact.fields.get(field, ""))
    ]
    if missing_fields:
        issues.append(
            _issue("missing-approval-metadata", artifact, f"missing metadata fields: {', '.join(missing_fields)}")
        )

    missing_sections = [section for section in SECTION_REQUIREMENTS[artifact.name] if section not in artifact.text]
    if missing_sections:
        issues.append(_issue("missing-gate-section", artifact, f"missing sections: {', '.join(missing_sections)}"))
    return issues


def _task_issues(feature: SddFeature) -> list[SddIssue]:
    tasks_artifact = feature.artifacts["tasks.md"]
    if tasks_artifact.missing:
        return []
    if not feature.tasks:
        return [_issue("task-missing-coordination-fields", tasks_artifact, "tasks.md has no structured Task sections")]

    issues: list[SddIssue] = []
    for task in feature.tasks:
        missing_fields = [field for field in TASK_REQUIRED_FIELDS if _is_placeholder(task.fields.get(field, ""))]
        if missing_fields:
            issues.append(
                _issue(
                    "task-missing-coordination-fields",
                    tasks_artifact,
                    f"{task.title} missing fields: {', '.join(missing_fields)}",
                )
            )
        if feature.status.lower() == "verified" and task.fields.get("status", "").strip().lower() != "[x]":
            issues.append(
                _issue("task-incomplete-in-verified-feature", tasks_artifact, f"{task.title} is not complete")
            )
    return issues


def _verified_issues(feature: SddFeature) -> list[SddIssue]:
    artifact = feature.artifacts["verification.md"]
    if artifact.missing:
        return []
    normalized_text = artifact.text.lower()
    issues: list[SddIssue] = []
    if not CHECK_ALL_RE.search(artifact.text):
        issues.append(
            _issue("verified-missing-check-all", artifact, "Verified records require make check-all with exit code: 0")
        )
    if any(phrase in normalized_text for phrase in CONTRADICTION_PHRASES):
        issues.append(
            _issue(
                "verified-contradicts-evidence", artifact, "Verified record contains contradictory evidence language"
            )
        )
    skipped_match = SKIPPED_RE.search(artifact.text)
    if skipped_match and int(skipped_match.group("count")) > 0 and "acceptable" not in normalized_text:
        issues.append(
            _issue("verified-unexplained-skips", artifact, "Verified record has skipped tests without explanation")
        )
    return issues


def _superseded_issues(feature: SddFeature) -> list[SddIssue]:
    issues: list[SddIssue] = []
    for artifact in feature.artifacts.values():
        if artifact.missing:
            continue
        if "superseded by" not in artifact.text.lower():
            issues.append(
                _issue("superseded-missing-successor", artifact, "Superseded artifacts must name the successor record")
            )
    return issues


def _active_touch_conflicts(features: list[SddFeature]) -> list[SddIssue]:
    owners: dict[str, list[SddFeature]] = defaultdict(list)
    for feature in features:
        if feature.state != "active" or feature.status.lower() == "superseded":
            continue
        for touched_path in feature.touch_set:
            owners[touched_path].append(feature)

    issues: list[SddIssue] = []
    for touched_path, touching_features in owners.items():
        unique_features = {feature.slug: feature for feature in touching_features}
        if len(unique_features) <= 1:
            continue
        feature_names = ", ".join(sorted(unique_features))
        for feature in unique_features.values():
            conflict_text = " ".join(feature.conflict_set).lower()
            if "coordinate" not in conflict_text and not any(
                other in conflict_text for other in unique_features if other != feature.slug
            ):
                issues.append(
                    SddIssue(
                        code="active-touch-conflict",
                        path=feature.relative_path,
                        message=f"{touched_path} is touched by active features: {feature_names}",
                    )
                )
    return issues


def _extract_status(text: str) -> str:
    for line in text.splitlines()[:40]:
        match = STATUS_RE.match(line)
        if match:
            return _clean_value(match.group(1)) or "unspecified"
    return "unspecified"


def _extract_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines()[:80]:
        match = FIELD_RE.match(line)
        if match:
            fields[match.group("name").strip().lower()] = _clean_value(match.group("value"))
    return fields


def _parse_tasks(text: str) -> list[TaskRecord]:
    matches = list(TASK_RE.finditer(text))
    tasks: list[TaskRecord] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        title = block.splitlines()[0].strip("# ").strip()
        fields = {
            field_match.group("name").strip().lower(): _clean_value(field_match.group("value"))
            for field_match in TASK_FIELD_RE.finditer(block)
        }
        tasks.append(TaskRecord(title=title, fields=fields))
    return tasks


def _task_set(tasks: tuple[TaskRecord, ...], field_name: str) -> tuple[str, ...]:
    values: list[str] = []
    for task in tasks:
        raw = task.fields.get(field_name, "")
        if _is_placeholder(raw) or raw.lower() in {"none", "not delegated"}:
            continue
        candidates = re.split(r"[,;]", raw.replace("`", ""))
        values.extend(
            candidate.strip() for candidate in candidates if candidate.strip() and candidate.strip().lower() != "none"
        )
    return tuple(dict.fromkeys(values))


def _first_task_field(tasks: tuple[TaskRecord, ...], field_name: str) -> str | None:
    for task in tasks:
        value = task.fields.get(field_name)
        if value and not _is_placeholder(value):
            return value
    return None


def _is_placeholder(value: str) -> bool:
    cleaned = _clean_value(value).lower()
    return cleaned in PLACEHOLDER_VALUES or cleaned.startswith("<") or cleaned.endswith(">")


def _clean_value(value: str) -> str:
    return " ".join(value.strip().strip("`").split())


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _issue(code: str, artifact: ArtifactRecord, message: str) -> SddIssue:
    return SddIssue(code=code, path=artifact.relative_path, message=message)


if __name__ == "__main__":
    raise SystemExit(main())
