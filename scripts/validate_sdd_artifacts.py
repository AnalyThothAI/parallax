from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.subagent_report_contract import validate_subagent_report  # noqa: E402

SDD_FEATURES = ROOT / "docs" / "sdd" / "features"
ARTIFACTS = ("spec.md", "plan.md", "tasks.md", "verification.md")
ACTIVE_STATUSES = {"draft", "approved", "in progress", "review", "blocked"}
COMPLETED_STATUSES = {"verified", "superseded"}
STATUS_RE = re.compile(r"^\s*(?:\*\*)?Status(?:\*\*)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<value>.+?)\s*$")
TASK_RE = re.compile(r"^###\s+Task\b", re.IGNORECASE | re.MULTILINE)
TASK_FIELD_RE = re.compile(r"^\s*-\s+\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<value>.*)$", re.MULTILINE)
FENCED_BLOCK_RE = re.compile(r"```(?:[A-Za-z0-9_-]+)?\n(?P<body>[\s\S]*?)```", re.MULTILINE)
COMMAND_LINE_RE = re.compile(r"^\s*\$\s+(?P<command>.+?)\s*$")
EXIT_CODE_RE = re.compile(r"exit code:\s*(?P<code>-?\d+)\b", re.IGNORECASE)
SKIPPED_RE = re.compile(r"Number of skipped tests in the run above:\s*(?P<count>\d+)", re.IGNORECASE)
FEATURE_SLUG_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*$")
BRANCH_METADATA_RE = re.compile(r"^codex/(?P<slug>[a-z0-9][a-z0-9._-]*)$")
WORKTREE_METADATA_RE = re.compile(r"^\.worktrees/(?P<slug>[a-z0-9][a-z0-9._-]*)/?$")
LOCAL_CITATION_RE = re.compile(
    r"(?P<path>(?:AGENTS|CLAUDE|Makefile|Dockerfile)\.md|"
    r"(?:\.agents|docs|scripts|src|tests|web)/[A-Za-z0-9._/\-]+):(?P<line>\d+)"
)
URL_CITATION_RE = re.compile(r"https://[^\s`)>\]]+")
SPEC_AC_RE = re.compile(r"^\s*-\s+AC(?P<number>\d+)\.", re.IGNORECASE | re.MULTILINE)
SPEC_AC_LINE_RE = re.compile(r"^\s*-\s+AC(?P<number>\d+)\..+$", re.IGNORECASE | re.MULTILINE)
SPEC_AC_FORMAT_RE = re.compile(
    r"^\s*-\s+AC\d+\.\s+WHEN\s+.+\s+THEN\s+.+\bSHALL\b.+$",
    re.IGNORECASE,
)
PLAN_AC_COMMAND_RE = re.compile(
    r"^\s*-\s+AC(?P<number>\d+)\s*:\s*`(?P<command>[^`]+)`\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PLAN_ACCEPTANCE_BULLET_RE = re.compile(r"^\s*-\s+.+$", re.MULTILINE)
PLAN_PREFLIGHT_WORKTREE_RE = re.compile(
    r"^\s*-\s+\[x\]\s+Worktree exists at `(?P<worktree>[^`]+)` and "
    r"`git branch --show-current` matches `(?P<branch>[^`]+)`\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TASK_NUMBER_RE = re.compile(r"^Task\s+(?P<number>\d+)\b", re.IGNORECASE)
TASK_DEPENDENCY_RE = re.compile(r"\bTasks?\s+(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?\b", re.IGNORECASE)

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
GATE_EVIDENCE_SECTIONS = {
    "spec.md": ("## Clarifications", "## Requirement Checklist"),
    "plan.md": ("## Analyze Gate",),
    "tasks.md": ("## Gate Compliance",),
}
METADATA_REQUIREMENTS = {
    "spec.md": ("status", "date", "owner", "approved by", "approved at"),
    "plan.md": ("status", "date", "owning spec", "worktree", "branch", "approved by", "approved at"),
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
WORKTREE_METADATA_ARTIFACTS = ("plan.md", "tasks.md", "verification.md")
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
TASK_AGENT_LOOP_FIELDS = (
    "factory lane",
    "deterministic constraints",
    "on-demand context",
    "kill/defer criteria",
    "eval/repair signal",
)
TASK_REVIEW_FIELDS = ("subagent report", "review result")
TASK_STATUSES = {"[ ]", "[~]", "[x]", "[!]"}
TASK_REVIEW_RESULTS = {"not delegated", "parent-reviewed", "accepted", "needs-repair", "blocked"}
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
    "artifact-status-mismatch",
    "missing-status",
    "missing-artifact",
    "unexpected-artifact",
    "feature-slug-invalid",
    "spec-background-uncited",
    "worktree-metadata-invalid",
    "plan-preflight-metadata-mismatch",
    "artifact-owning-link-mismatch",
    "missing-gate-section",
    "gate-evidence-missing",
    "acceptance-numbering-invalid",
    "acceptance-criterion-format-invalid",
    "acceptance-command-invalid",
    "acceptance-command-mismatch",
    "missing-approval-metadata",
    "task-missing-coordination-fields",
    "task-invalid-coordination-fields",
    "task-invalid-numbering",
    "task-invalid-dependencies",
    "task-missing-agent-loop-fields",
    "task-missing-review-fields",
    "task-invalid-review-fields",
    "task-complete-missing-review-evidence",
    "task-missing-subagent-handoff-artifact",
    "task-missing-subagent-report-artifact",
    "task-invalid-subagent-report-artifact",
    "task-complete-missing-verification-evidence",
    "task-incomplete-in-verified-feature",
    "verified-missing-check-all",
    "verified-missing-spec-compliance-evidence",
    "verified-contradicts-evidence",
    "verified-unexplained-skips",
    "superseded-missing-successor",
    "superseded-successor-mismatch",
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
    def factory_lanes(self) -> tuple[str, ...]:
        return _task_set(self.tasks, "factory lane")

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


def task_number(task: TaskRecord) -> int | None:
    match = TASK_NUMBER_RE.match(task.title)
    return int(match.group("number")) if match else None


def task_dependency_numbers(task: TaskRecord) -> tuple[int, ...] | None:
    raw = task.fields.get("depends on", "")
    value = raw.replace("`", "").strip()
    if not value or value.lower() in {"none", "not delegated"}:
        return ()

    matches = list(TASK_DEPENDENCY_RE.finditer(value))
    if not matches:
        return None

    remainder = TASK_DEPENDENCY_RE.sub("", value)
    remainder = re.sub(r"\b(?:and)\b", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"[\s,;&+]+", "", remainder)
    if remainder:
        return None

    dependencies: list[int] = []
    for match in matches:
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        if end < start:
            return None
        dependencies.extend(range(start, end + 1))
    return tuple(dict.fromkeys(dependencies))


def task_unresolved_dependencies(feature: SddFeature, task: TaskRecord) -> tuple[int, ...]:
    dependencies = task_dependency_numbers(task)
    if dependencies is None:
        return ()

    current_number = task_number(task)
    tasks_by_number = _tasks_by_number(feature)
    return tuple(
        dependency
        for dependency in dependencies
        if dependency not in tasks_by_number or dependency == current_number
    )


def task_incomplete_dependencies(feature: SddFeature, task: TaskRecord) -> tuple[int, ...]:
    dependencies = task_dependency_numbers(task)
    if dependencies is None:
        return ()

    tasks_by_number = _tasks_by_number(feature)
    incomplete: list[int] = []
    for dependency in dependencies:
        dependency_task = tasks_by_number.get(dependency)
        if dependency_task is None:
            incomplete.append(dependency)
            continue
        if dependency_task.fields.get("status", "").strip().lower() != "[x]":
            incomplete.append(dependency)
    return tuple(dict.fromkeys(incomplete))


def task_dependencies_satisfied(feature: SddFeature, task: TaskRecord) -> bool:
    dependencies = task_dependency_numbers(task)
    return dependencies is not None and not task_incomplete_dependencies(feature, task)


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
    issues.extend(_unexpected_artifact_issues(feature))
    issues.extend(_feature_identity_issues(feature))
    issues.extend(_worktree_metadata_issues(feature))
    for artifact in feature.artifacts.values():
        issues.extend(_artifact_issues(feature, artifact))
    issues.extend(_artifact_status_mismatch_issues(feature))
    if feature.status.lower() == "superseded":
        return issues + _superseded_issues(feature)
    issues.extend(_plan_preflight_issues(feature))
    issues.extend(_acceptance_command_issues(feature))
    issues.extend(_task_issues(feature))
    if feature.status.lower() == "verified":
        issues.extend(_verified_issues(feature))
    return issues


def _unexpected_artifact_issues(feature: SddFeature) -> list[SddIssue]:
    repo_root = _repo_root(feature)
    unexpected_paths = sorted(path for path in feature.path.iterdir() if path.name not in ARTIFACTS)
    return [
        SddIssue(
            code="unexpected-artifact",
            path=_relative(repo_root, path),
            message=f"feature directories must contain only {', '.join(ARTIFACTS)}",
        )
        for path in unexpected_paths
    ]


def _feature_identity_issues(feature: SddFeature) -> list[SddIssue]:
    match = FEATURE_SLUG_RE.match(feature.slug)
    if not match:
        return [
            SddIssue(
                code="feature-slug-invalid",
                path=feature.relative_path,
                message="feature directory must match YYYY-MM-DD-kebab-slug",
            )
        ]

    expected_date = match.group("date")
    issues: list[SddIssue] = []
    for artifact_name in ("spec.md", "plan.md", "verification.md"):
        artifact = feature.artifacts[artifact_name]
        date = artifact.fields.get("date", "")
        if artifact.missing or _is_placeholder(date) or date == expected_date:
            continue
        issues.append(
            _issue(
                "feature-slug-invalid",
                artifact,
                f"{artifact.name} Date must match feature slug date {expected_date}, got {date}",
            )
        )
    return issues


def _worktree_metadata_issues(feature: SddFeature) -> list[SddIssue]:
    invalid_metadata: list[str] = []
    canonical_pairs: dict[str, tuple[str, str]] = {}
    for artifact_name in WORKTREE_METADATA_ARTIFACTS:
        artifact = feature.artifacts[artifact_name]
        branch = artifact.fields.get("branch", "")
        worktree = artifact.fields.get("worktree", "")
        if artifact.missing or _is_placeholder(branch) or _is_placeholder(worktree):
            continue
        metadata_error = _worktree_metadata_error(branch, worktree)
        if metadata_error:
            invalid_metadata.append(f"{artifact.name}: {metadata_error}")
            continue
        canonical_pairs[artifact.name] = _canonical_worktree_pair(branch, worktree)

    anchor = feature.artifacts["verification.md"]
    if invalid_metadata:
        return [_issue("worktree-metadata-invalid", anchor, "; ".join(invalid_metadata))]

    unique_pairs = set(canonical_pairs.values())
    if len(unique_pairs) <= 1:
        return []
    summary = ", ".join(
        f"{artifact_name}={branch}/{worktree}"
        for artifact_name, (branch, worktree) in sorted(canonical_pairs.items())
    )
    return [
        _issue(
            "worktree-metadata-invalid",
            anchor,
            f"Worktree/Branch metadata must match across plan.md, tasks.md, and verification.md: {summary}",
        )
    ]


def _worktree_metadata_error(branch: str, worktree: str) -> str:
    cleaned_branch, cleaned_worktree = _canonical_worktree_pair(branch, worktree)
    if cleaned_branch == "main" or cleaned_worktree == "main":
        if (cleaned_branch, cleaned_worktree) == ("main", "main"):
            return ""
        return f"main checkout metadata must be Branch=main and Worktree=main, got {cleaned_branch}/{cleaned_worktree}"

    branch_match = BRANCH_METADATA_RE.match(cleaned_branch)
    worktree_match = WORKTREE_METADATA_RE.match(cleaned_worktree)
    if not branch_match or not worktree_match:
        return (
            "expected Branch=codex/<slug> with Worktree=.worktrees/<slug>, "
            f"or Branch=main with Worktree=main, got {cleaned_branch}/{cleaned_worktree}"
        )
    if branch_match.group("slug") != worktree_match.group("slug"):
        return f"branch/worktree slug mismatch: {cleaned_branch}/{cleaned_worktree}"
    return ""


def _canonical_worktree_pair(branch: str, worktree: str) -> tuple[str, str]:
    cleaned_branch = _clean_value(branch)
    cleaned_worktree = _clean_value(worktree)
    if cleaned_worktree.startswith(".worktrees/"):
        cleaned_worktree = cleaned_worktree.rstrip("/")
    return cleaned_branch, cleaned_worktree


def _artifact_status_mismatch_issues(feature: SddFeature) -> list[SddIssue]:
    present_artifacts = [artifact for artifact in feature.artifacts.values() if not artifact.missing]
    statuses = {artifact.status.lower() for artifact in present_artifacts}
    if len(statuses) <= 1:
        return []

    status_summary = ", ".join(f"{artifact.name}={artifact.status}" for artifact in present_artifacts)
    anchor = feature.artifacts.get("verification.md") or present_artifacts[0]
    return [
        _issue(
            "artifact-status-mismatch",
            anchor,
            f"feature artifacts must share one Status value: {status_summary}",
        )
    ]


def _plan_preflight_issues(feature: SddFeature) -> list[SddIssue]:
    artifact = feature.artifacts["plan.md"]
    if artifact.missing:
        return []

    preflight = _section_text(artifact.text, "## Pre-flight")
    if not preflight:
        return []

    expected = _canonical_worktree_pair(artifact.fields.get("branch", ""), artifact.fields.get("worktree", ""))
    mismatches: list[str] = []
    for match in PLAN_PREFLIGHT_WORKTREE_RE.finditer(preflight):
        actual = _canonical_worktree_pair(match.group("branch"), match.group("worktree"))
        if actual != expected:
            mismatches.append(f"expected {expected[1]}/{expected[0]}, saw {actual[1]}/{actual[0]}")

    if not mismatches:
        return []
    return [
        _issue(
            "plan-preflight-metadata-mismatch",
            artifact,
            "checked plan pre-flight Worktree/Branch claim must match metadata: " + "; ".join(mismatches),
        )
    ]


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

    missing_fields = [
        field for field in METADATA_REQUIREMENTS[artifact.name] if _is_placeholder(artifact.fields.get(field, ""))
    ]
    if missing_fields:
        issues.append(
            _issue("missing-approval-metadata", artifact, f"missing metadata fields: {', '.join(missing_fields)}")
        )
    issues.extend(_artifact_owning_link_issues(feature, artifact))

    if normalized_status == "superseded":
        return issues

    missing_sections = [section for section in SECTION_REQUIREMENTS[artifact.name] if section not in artifact.text]
    if missing_sections:
        issues.append(_issue("missing-gate-section", artifact, f"missing sections: {', '.join(missing_sections)}"))
    issues.extend(_gate_evidence_issues(artifact))
    if artifact.name == "spec.md":
        issues.extend(_spec_background_issues(feature, artifact))
    return issues


def _acceptance_command_issues(feature: SddFeature) -> list[SddIssue]:
    spec_artifact = feature.artifacts["spec.md"]
    plan_artifact = feature.artifacts["plan.md"]
    if spec_artifact.missing or plan_artifact.missing:
        return []

    spec_number_sequence = _spec_acceptance_numbers(spec_artifact.text)
    plan_commands = _plan_acceptance_commands(plan_artifact.text)
    plan_number_sequence = [number for number, _command in plan_commands]
    issues: list[SddIssue] = []
    invalid_criteria = _invalid_acceptance_criterion_lines(spec_artifact.text)
    if invalid_criteria:
        issues.append(
            _issue(
                "acceptance-criterion-format-invalid",
                spec_artifact,
                "acceptance criteria must use WHEN ... THEN ... SHALL format: " + ", ".join(invalid_criteria),
            )
        )

    for artifact, label, numbers in (
        (spec_artifact, "spec acceptance criteria", spec_number_sequence),
        (plan_artifact, "plan acceptance commands", plan_number_sequence),
    ):
        numbering_message = _contiguous_numbering_error(label, numbers)
        if numbering_message:
            issues.append(_issue("acceptance-numbering-invalid", artifact, numbering_message))

    invalid_commands = _invalid_plan_acceptance_command_lines(plan_artifact.text)
    invalid_commands.extend(
        f"AC{number}={command!r}" for number, command in plan_commands if not _looks_like_command(command)
    )
    if invalid_commands:
        issues.append(
            _issue(
                "acceptance-command-invalid",
                plan_artifact,
                "plan acceptance entries must be command-shaped: " + ", ".join(invalid_commands),
            )
        )

    spec_numbers = set(spec_number_sequence)
    plan_numbers = set(plan_number_sequence)
    missing_numbers = sorted(spec_numbers - plan_numbers)
    extra_numbers = sorted(plan_numbers - spec_numbers)
    if not missing_numbers and not extra_numbers:
        return issues

    parts: list[str] = []
    if missing_numbers:
        parts.append("missing commands for " + ", ".join(f"AC{number}" for number in missing_numbers))
    if extra_numbers:
        parts.append("commands without spec criteria for " + ", ".join(f"AC{number}" for number in extra_numbers))
    issues.append(_issue("acceptance-command-mismatch", plan_artifact, "; ".join(parts)))
    return issues


def _artifact_owning_link_issues(feature: SddFeature, artifact: ArtifactRecord) -> list[SddIssue]:
    expected_links = {
        "plan.md": {"owning spec": f"{feature.relative_path}/spec.md"},
        "tasks.md": {"owning plan": f"{feature.relative_path}/plan.md"},
        "verification.md": {
            "owning spec": f"{feature.relative_path}/spec.md",
            "owning plan": f"{feature.relative_path}/plan.md",
        },
    }.get(artifact.name, {})
    issues: list[SddIssue] = []
    for field_name, expected_path in expected_links.items():
        actual_path = artifact.fields.get(field_name, "")
        if _is_placeholder(actual_path):
            continue
        if actual_path.replace("`", "").strip() != expected_path:
            issues.append(
                _issue(
                    "artifact-owning-link-mismatch",
                    artifact,
                    f"{artifact.name} {field_name} must be `{expected_path}`, got {actual_path}",
                )
            )
    return issues


def _gate_evidence_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    issues: list[SddIssue] = []
    for heading in GATE_EVIDENCE_SECTIONS.get(artifact.name, ()):
        if heading not in artifact.text:
            continue
        if _section_has_non_placeholder_table_row(artifact.text, heading):
            continue
        issues.append(
            _issue(
                "gate-evidence-missing",
                artifact,
                f"{artifact.name} {heading} must contain at least one non-placeholder evidence row",
            )
        )
    return issues


def _spec_background_issues(feature: SddFeature, artifact: ArtifactRecord) -> list[SddIssue]:
    background = _section_text(artifact.text, "## Background")
    if not background.strip():
        return [_issue("spec-background-uncited", artifact, "spec.md Background is missing or empty")]

    invalid_blocks: list[str] = []
    for block in _citation_blocks(background):
        citation_error = _citation_block_error(_repo_root(feature), block)
        if citation_error:
            invalid_blocks.append(citation_error)

    if not invalid_blocks:
        return []
    return [
        _issue(
            "spec-background-uncited",
            artifact,
            "spec.md Background claims require existing repo path:line citations or https sources: "
            + "; ".join(invalid_blocks),
        )
    ]


def _citation_blocks(section: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fenced_block = False
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        if not stripped:
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if stripped.startswith("|") and "---" in stripped:
            continue
        if stripped.startswith(("-", "*")):
            if current:
                blocks.append(" ".join(current))
                current = []
            blocks.append(stripped)
            continue
        current.append(stripped)
    if current:
        blocks.append(" ".join(current))
    return blocks


def _citation_block_error(root: Path, block: str) -> str:
    if URL_CITATION_RE.search(block):
        return ""
    citations = list(LOCAL_CITATION_RE.finditer(block))
    if not citations:
        return f"missing citation in {block!r}"
    invalid: list[str] = []
    for citation in citations:
        citation_path = citation.group("path")
        citation_line = int(citation.group("line"))
        path = root / citation_path
        if not path.is_file():
            invalid.append(f"{citation_path}:{citation_line} does not exist")
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if citation_line < 1 or citation_line > line_count:
            invalid.append(f"{citation_path}:{citation_line} is outside 1..{line_count}")
    return ", ".join(invalid)


def _task_issues(feature: SddFeature) -> list[SddIssue]:
    tasks_artifact = feature.artifacts["tasks.md"]
    if tasks_artifact.missing:
        return []
    if not feature.tasks:
        return [
            _issue("task-missing-coordination-fields", tasks_artifact, "tasks.md has no structured Task sections"),
            _issue("task-missing-agent-loop-fields", tasks_artifact, "tasks.md has no structured Task sections"),
        ]

    issues: list[SddIssue] = []
    issues.extend(_task_numbering_issues(feature))
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
        invalid_fields = _invalid_task_fields(task)
        if invalid_fields:
            issues.append(
                _issue(
                    "task-invalid-coordination-fields",
                    tasks_artifact,
                    f"{task.title} invalid fields: {', '.join(invalid_fields)}",
                )
            )
        dependency_numbers = task_dependency_numbers(task)
        if dependency_numbers is None:
            issues.append(
                _issue(
                    "task-invalid-dependencies",
                    tasks_artifact,
                    f"{task.title} has unsupported dependency syntax: {task.fields.get('depends on', '')}",
                )
            )
        else:
            unresolved_dependencies = task_unresolved_dependencies(feature, task)
            if unresolved_dependencies:
                dependencies = ", ".join(f"Task {dependency}" for dependency in unresolved_dependencies)
                issues.append(
                    _issue("task-invalid-dependencies", tasks_artifact, f"{task.title} unresolved: {dependencies}")
                )
            elif task.fields.get("status", "").strip().lower() == "[x]":
                incomplete_dependencies = task_incomplete_dependencies(feature, task)
                if incomplete_dependencies:
                    dependencies = ", ".join(f"Task {dependency}" for dependency in incomplete_dependencies)
                    issues.append(
                        _issue(
                            "task-invalid-dependencies",
                            tasks_artifact,
                            f"{task.title} complete before dependencies: {dependencies}",
                        )
                    )
        missing_agent_fields = [
            field for field in TASK_AGENT_LOOP_FIELDS if _is_placeholder(task.fields.get(field, ""))
        ]
        if missing_agent_fields:
            issues.append(
                _issue(
                    "task-missing-agent-loop-fields",
                    tasks_artifact,
                    f"{task.title} missing fields: {', '.join(missing_agent_fields)}",
                )
            )
        missing_review_fields = [field for field in TASK_REVIEW_FIELDS if _is_placeholder(task.fields.get(field, ""))]
        if missing_review_fields:
            issues.append(
                _issue(
                    "task-missing-review-fields",
                    tasks_artifact,
                    f"{task.title} missing fields: {', '.join(missing_review_fields)}",
                )
            )
        invalid_review_fields = _invalid_review_fields(task)
        if invalid_review_fields:
            issues.append(
                _issue(
                    "task-invalid-review-fields",
                    tasks_artifact,
                    f"{task.title} invalid fields: {', '.join(invalid_review_fields)}",
                )
            )
        issues.extend(_complete_task_review_issues(feature, task))
        issues.extend(_subagent_handoff_artifact_issues(feature, task))
        issues.extend(_subagent_report_artifact_issues(feature, task))
        issues.extend(_complete_task_verification_issues(feature, task))
        if feature.status.lower() == "verified" and task.fields.get("status", "").strip().lower() != "[x]":
            issues.append(
                _issue("task-incomplete-in-verified-feature", tasks_artifact, f"{task.title} is not complete")
            )
    return issues


def _task_numbering_issues(feature: SddFeature) -> list[SddIssue]:
    tasks_artifact = feature.artifacts["tasks.md"]
    task_numbers = [task_number(task) for task in feature.tasks]
    if any(number is None for number in task_numbers):
        return [
            _issue(
                "task-invalid-numbering",
                tasks_artifact,
                "Task headings must start with a machine-readable Task number",
            )
        ]

    present_numbers = [number for number in task_numbers if number is not None]
    expected_numbers = list(range(1, len(present_numbers) + 1))
    if sorted(present_numbers) == expected_numbers and len(set(present_numbers)) == len(present_numbers):
        return []

    present_summary = ", ".join(f"Task {number}" for number in present_numbers)
    expected_summary = f"Task 1..{len(present_numbers)}"
    return [
        _issue(
            "task-invalid-numbering",
            tasks_artifact,
            f"Task headings must be unique and contiguous: expected {expected_summary}, saw {present_summary}",
        )
    ]


def _invalid_task_fields(task: TaskRecord) -> list[str]:
    invalid: list[str] = []
    for field_name in ("file(s)", "touch set"):
        value = task.fields.get(field_name, "")
        if _is_placeholder(value):
            continue
        if not _all_list_items(value, _is_repo_path):
            invalid.append(field_name)

    conflict_set = task.fields.get("conflict set", "")
    if not _is_placeholder(conflict_set) and not _valid_conflict_set(conflict_set):
        invalid.append("conflict set")

    failing_test = task.fields.get("failing test first", "")
    if not _is_placeholder(failing_test) and not _looks_like_test_reference(failing_test):
        invalid.append("failing test first")

    verification = task.fields.get("verification", "")
    if not _is_placeholder(verification) and not _looks_like_command(verification):
        invalid.append("verification")

    status = task.fields.get("status", "").strip().lower()
    if status and status not in TASK_STATUSES:
        invalid.append("status")
    return invalid


def _invalid_review_fields(task: TaskRecord) -> list[str]:
    invalid: list[str] = []
    subagent_handoff = task.fields.get("subagent handoff", "")
    subagent_report = task.fields.get("subagent report", "")
    review_result = task.fields.get("review result", "")
    if _is_placeholder(subagent_report) or _is_placeholder(review_result):
        return invalid

    normalized_handoff = subagent_handoff.replace("`", "").strip().lower()
    if normalized_handoff != "not delegated" and not _is_repo_path(subagent_handoff):
        invalid.append("subagent handoff")

    delegated = not _is_not_delegated(subagent_handoff)
    normalized_report = subagent_report.replace("`", "").strip().lower()
    normalized_result = review_result.replace("`", "").strip().lower()
    if normalized_result not in TASK_REVIEW_RESULTS:
        invalid.append("review result")

    if delegated:
        if not _is_repo_path(subagent_report):
            invalid.append("subagent report")
        if normalized_result == "not delegated":
            invalid.append("review result")
    else:
        if normalized_report != "not delegated":
            invalid.append("subagent report")
        if normalized_result not in {"not delegated", "parent-reviewed"}:
            invalid.append("review result")

    status = task.fields.get("status", "").strip().lower()
    if status == "[x]" and normalized_result in {"needs-repair", "blocked"}:
        invalid.append("review result")
    return list(dict.fromkeys(invalid))


def _complete_task_review_issues(feature: SddFeature, task: TaskRecord) -> list[SddIssue]:
    if task.fields.get("status", "").strip().lower() != "[x]":
        return []

    review_result = task.fields.get("review result", "").replace("`", "").strip().lower()
    if review_result in {"parent-reviewed", "accepted"}:
        return []

    return [
        _issue(
            "task-complete-missing-review-evidence",
            feature.artifacts["tasks.md"],
            f"{task.title} complete task requires parent-reviewed or accepted review result",
        )
    ]


def _subagent_report_artifact_issues(feature: SddFeature, task: TaskRecord) -> list[SddIssue]:
    if _is_not_delegated(task.fields.get("subagent handoff", "")):
        return []

    report_value = task.fields.get("subagent report", "")
    if _is_placeholder(report_value) or not _is_repo_path(report_value):
        return []

    tasks_artifact = feature.artifacts["tasks.md"]
    report_path = _repo_root(feature) / report_value.replace("`", "").strip()
    if not report_path.exists():
        return [
            _issue(
                "task-missing-subagent-report-artifact",
                tasks_artifact,
                f"{task.title} missing subagent report artifact: {report_value}",
            )
        ]

    report_text = report_path.read_text(encoding="utf-8")
    mode = _extract_report_mode(report_text)
    if mode is None:
        return [
            _issue(
                "task-invalid-subagent-report-artifact",
                tasks_artifact,
                f"{task.title} subagent report has no Mode line: {report_value}",
            )
        ]

    report_issues = validate_subagent_report(report_text, mode=mode, task_fields=task.fields)
    if report_issues:
        return [
            _issue(
                "task-invalid-subagent-report-artifact",
                tasks_artifact,
                f"{task.title} invalid subagent report: {'; '.join(report_issues)}",
            )
        ]
    return []


def _subagent_handoff_artifact_issues(feature: SddFeature, task: TaskRecord) -> list[SddIssue]:
    handoff_value = task.fields.get("subagent handoff", "")
    if _is_not_delegated(handoff_value) or _is_placeholder(handoff_value) or not _is_repo_path(handoff_value):
        return []

    tasks_artifact = feature.artifacts["tasks.md"]
    handoff_path = _repo_root(feature) / handoff_value.replace("`", "").strip()
    if handoff_path.exists():
        return []
    return [
        _issue(
            "task-missing-subagent-handoff-artifact",
            tasks_artifact,
            f"{task.title} missing subagent handoff artifact: {handoff_value}",
        )
    ]


def _extract_report_mode(text: str) -> str | None:
    for line in text.splitlines()[:20]:
        match = re.match(r"^\s*Mode:\s*(read-only|write-allowed|review-only)\s*$", line, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def _repo_root(feature: SddFeature) -> Path:
    return feature.path.parents[4]


def _complete_task_verification_issues(feature: SddFeature, task: TaskRecord) -> list[SddIssue]:
    if task.fields.get("status", "").strip().lower() != "[x]":
        return []

    expected_command = _clean_command(task.fields.get("verification", ""))
    if not expected_command:
        return []

    artifact = feature.artifacts["verification.md"]
    if artifact.missing or not _has_successful_command_evidence(artifact.text, expected_command):
        return [
            _issue(
                "task-complete-missing-verification-evidence",
                feature.artifacts["tasks.md"],
                f"{task.title} lacks exit code 0 evidence for: {expected_command}",
            )
        ]
    return []


def _has_successful_command_evidence(text: str, expected_command: str) -> bool:
    evidence = _command_evidence(_task_evidence_text(text))
    return any(exit_code == 0 for exit_code in evidence.get(expected_command, ()))


def _task_evidence_text(text: str) -> str:
    return "\n".join(
        section
        for section in (
            _section_text(text, "## Verification commands"),
            _section_text(text, "## Other commands run"),
        )
        if section
    )


def _command_evidence(text: str) -> dict[str, tuple[int, ...]]:
    evidence: dict[str, list[int]] = defaultdict(list)
    for block_match in FENCED_BLOCK_RE.finditer(text):
        current_command: str | None = None
        for line in block_match.group("body").splitlines():
            command_match = COMMAND_LINE_RE.match(line)
            if command_match:
                current_command = _clean_command(command_match.group("command"))
                continue

            exit_match = EXIT_CODE_RE.search(line)
            if exit_match and current_command:
                evidence[current_command].append(int(exit_match.group("code")))
                current_command = None
    return {command: tuple(exit_codes) for command, exit_codes in evidence.items()}


def _spec_acceptance_numbers(text: str) -> list[int]:
    return [int(match.group("number")) for match in SPEC_AC_RE.finditer(text)]


def _invalid_acceptance_criterion_lines(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in SPEC_AC_LINE_RE.finditer(text)
        if not SPEC_AC_FORMAT_RE.match(match.group(0))
    ]


def _plan_acceptance_commands(text: str) -> list[tuple[int, str]]:
    return [
        (int(match.group("number")), _clean_command(match.group("command")))
        for match in PLAN_AC_COMMAND_RE.finditer(text)
    ]


def _invalid_plan_acceptance_command_lines(text: str) -> list[str]:
    section = _section_text(text, "## Acceptance test commands")
    return [
        line.strip()
        for line in PLAN_ACCEPTANCE_BULLET_RE.findall(section)
        if not PLAN_AC_COMMAND_RE.match(line)
    ]


def _contiguous_numbering_error(label: str, numbers: list[int]) -> str:
    expected = list(range(1, len(numbers) + 1))
    if numbers == expected:
        return ""
    expected_summary = f"AC1..AC{len(numbers)}"
    actual_summary = ", ".join(f"AC{number}" for number in numbers) or "none"
    return f"{label} must be unique and contiguous: expected {expected_summary}, saw {actual_summary}"


def _verified_issues(feature: SddFeature) -> list[SddIssue]:
    artifact = feature.artifacts["verification.md"]
    if artifact.missing:
        return []
    normalized_text = artifact.text.lower()
    issues: list[SddIssue] = []
    make_check_all = _verification_make_check_all_block(artifact.text)
    if make_check_all is None:
        issues.append(
            _issue("verified-missing-check-all", artifact, "Verified records require make check-all with exit code: 0")
        )
    elif _command_exit_code(make_check_all) != 0:
        issues.append(
            _issue("verified-missing-check-all", artifact, "Verified records require final make check-all exit code 0")
        )
    if any(phrase in normalized_text for phrase in CONTRADICTION_PHRASES):
        issues.append(
            _issue(
                "verified-contradicts-evidence", artifact, "Verified record contains contradictory evidence language"
            )
        )
    if make_check_all is not None and _command_exit_code(make_check_all) not in {0, None}:
        issues.append(
            _issue("verified-contradicts-evidence", artifact, "Verified command block records non-zero exit code")
        )
    issues.extend(_verified_spec_compliance_issues(artifact))
    skipped_match = SKIPPED_RE.search(artifact.text)
    if skipped_match and int(skipped_match.group("count")) > 0 and not _skipped_rows_are_acceptable(artifact.text):
        issues.append(
            _issue("verified-unexplained-skips", artifact, "Verified record has skipped tests without explanation")
        )
    return issues


def _verified_spec_compliance_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    command_evidence = _command_evidence(_task_evidence_text(artifact.text))
    missing_commands: list[str] = []
    for cells in _section_table_rows(artifact.text, "## Spec compliance"):
        if len(cells) < 3 or not _is_complete_compliance_status(cells[1]):
            continue
        commands = [
            _clean_command(match.group(1))
            for match in re.finditer(r"`([^`]+)`", cells[2])
            if _looks_like_command(match.group(1))
        ]
        missing_commands.extend(
            command
            for command in commands
            if not any(exit_code == 0 for exit_code in command_evidence.get(command, ()))
        )

    if not missing_commands:
        return []
    return [
        _issue(
            "verified-missing-spec-compliance-evidence",
            artifact,
            "Verified spec compliance rows lack exit code 0 command evidence: "
            + ", ".join(dict.fromkeys(missing_commands)),
        )
    ]


def _is_complete_compliance_status(value: str) -> bool:
    cleaned = _clean_value(value).lower()
    return "\u2705" in value or cleaned in {"pass", "passed", "verified", "met", "complete", "completed", "done"}


def _superseded_issues(feature: SddFeature) -> list[SddIssue]:
    issues: list[SddIssue] = []
    successor_paths: dict[str, list[str]] = defaultdict(list)
    for artifact in feature.artifacts.values():
        if artifact.missing:
            continue
        successor = artifact.fields.get("superseded by", "")
        if _is_placeholder(successor):
            issues.append(
                _issue(
                    "superseded-missing-successor",
                    artifact,
                    "Superseded artifacts must declare **Superseded by** metadata",
                )
            )
            continue
        if not _is_repo_path(successor):
            issues.append(
                _issue(
                    "superseded-missing-successor",
                    artifact,
                    f"Superseded successor must be a repo path: {successor}",
                )
            )
            continue
        successor_path = _repo_root(feature) / successor
        if not successor_path.exists():
            issues.append(
                _issue(
                    "superseded-missing-successor",
                    artifact,
                    f"Superseded successor path does not exist: {successor}",
                )
            )
            continue
        successor_paths[successor.rstrip("/")].append(artifact.name)
    if len(successor_paths) > 1:
        summary = ", ".join(
            f"{successor} ({', '.join(sorted(artifact_names))})"
            for successor, artifact_names in sorted(successor_paths.items())
        )
        issues.append(
            _issue(
                "superseded-successor-mismatch",
                feature.artifacts["verification.md"],
                f"Superseded artifacts must share one successor: {summary}",
            )
        )
    tasks_artifact = feature.artifacts["tasks.md"]
    if not tasks_artifact.missing and not feature.tasks:
        issues.append(
            _issue(
                "task-missing-coordination-fields",
                tasks_artifact,
                "Superseded tasks.md must retain structured Task sections",
            )
        )
    if feature.tasks:
        issues.extend(_task_numbering_issues(feature))
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
        separator = r";" if field_name == "conflict set" else r"[,;]"
        candidates = re.split(separator, raw.replace("`", ""))
        values.extend(
            candidate.strip() for candidate in candidates if candidate.strip() and candidate.strip().lower() != "none"
        )
    return tuple(dict.fromkeys(values))


def _tasks_by_number(feature: SddFeature) -> dict[int, TaskRecord]:
    numbered_tasks: dict[int, TaskRecord] = {}
    for task in feature.tasks:
        number = task_number(task)
        if number is not None:
            numbered_tasks[number] = task
    return numbered_tasks


def _all_list_items(value: str, predicate: Callable[[str], bool]) -> bool:
    items = [item.strip() for item in re.split(r"[,;]", value.replace("`", "")) if item.strip()]
    return bool(items) and all(predicate(item) for item in items)


def _valid_conflict_set(value: str) -> bool:
    stripped = value.replace("`", "").strip()
    if stripped.lower() in {"none", "not delegated"}:
        return False
    items = [item.strip() for item in re.split(r";", stripped) if item.strip()]
    return bool(items) and all(_is_coordination_rule(item) or _all_list_items(item, _is_repo_path) for item in items)


def _is_coordination_rule(value: str) -> bool:
    return bool(re.match(r"^coordinate with [a-z0-9][a-z0-9_.\-/]+ for .+", value, re.IGNORECASE))


def _is_not_delegated(value: str) -> bool:
    return value.replace("`", "").strip().lower() == "not delegated"


def _is_repo_path(value: str) -> bool:
    stripped = value.strip()
    if stripped.lower() in {"none", "not delegated"}:
        return False
    if any(character.isspace() for character in stripped):
        return False
    return (
        "/" in stripped
        or stripped.startswith(".")
        or "." in stripped
        or stripped in {"Makefile", "Dockerfile", "AGENTS.md", "CLAUDE.md"}
    )


def _looks_like_test_reference(value: str) -> bool:
    stripped = value.replace("`", "")
    return "tests/" in stripped and ("pytest" in stripped or "::" in stripped or stripped.endswith(".py"))


def _looks_like_command(value: str) -> bool:
    stripped = value.replace("`", "").strip()
    return bool(re.match(r"^(uv|make|cd|npm|python|pytest)\b", stripped))


def _clean_command(value: str) -> str:
    cleaned = value.strip().strip("`")
    if cleaned.startswith("$"):
        cleaned = cleaned[1:].strip()
    return " ".join(cleaned.split())


def _verification_make_check_all_block(text: str) -> str | None:
    section = _section_text(text, "## Verification commands")
    blocks = [match.group("body").strip() for match in FENCED_BLOCK_RE.finditer(section)]
    make_check_all_blocks = [block for block in blocks if re.search(r"^\$\s*make check-all\s*$", block, re.MULTILINE)]
    if len(make_check_all_blocks) != 1:
        return None
    return make_check_all_blocks[0]


def _section_text(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _section_has_non_placeholder_table_row(text: str, heading: str) -> bool:
    for cells in _section_table_rows(text, heading):
        if cells and all(not _is_placeholder_table_cell(cell) for cell in cells):
            return True
    return False


def _section_table_rows(text: str, heading: str) -> list[list[str]]:
    rows: list[list[str]] = []
    section = _section_text(text, heading)
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows[1:]


def _is_placeholder_table_cell(value: str) -> bool:
    cleaned = _clean_value(value).lower()
    return _is_placeholder(value) or cleaned in {"pass / fail", "yyyy-mm-dd"}


def _command_exit_code(block: str) -> int | None:
    matches = list(EXIT_CODE_RE.finditer(block))
    if not matches:
        return None
    return int(matches[-1].group("code"))


def _skipped_rows_are_acceptable(text: str) -> bool:
    skipped_match = SKIPPED_RE.search(text)
    if not skipped_match:
        return False
    skipped_count = int(skipped_match.group("count"))
    if skipped_count == 0:
        return True

    section = _section_text(text, "## Skipped tests")
    rows = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
    data_rows = rows[1:]
    total = 0
    for row in data_rows:
        cells = [cell.strip().lower() for cell in row.strip("|").split("|")]
        if len(cells) < 3:
            return False
        try:
            total += int(cells[0])
        except ValueError:
            return False
        if cells[-1] not in {"yes", "acceptable", "true"}:
            return False
    return total == skipped_count


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
