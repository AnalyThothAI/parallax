from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_mode_constraints import mode_constraint_lines  # noqa: E402
from scripts.subagent_report_contract import validate_subagent_report  # noqa: E402

SDD_FEATURES = ROOT / "docs" / "sdd" / "features"
ARTIFACTS = ("spec.md", "plan.md", "tasks.md", "verification.md")
ACTIVE_STATUSES = {"draft", "approved", "in progress", "review", "blocked"}
COMPLETED_STATUSES = {"verified", "superseded"}
MAX_ACTIVE_FEATURE_TASKS = 40
STATUS_RE = re.compile(r"^\s*(?:\*\*)?Status(?:\*\*)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<value>.+?)\s*$")
TASK_RE = re.compile(r"^###\s+Task\b", re.IGNORECASE | re.MULTILINE)
TASK_FIELD_RE = re.compile(r"^\s*-\s+\*\*(?P<name>[^*]+)\*\*\s*:\s*(?P<value>.*)$", re.MULTILINE)
TASKS_FINAL_VERIFICATION_HEADING_RE = re.compile(r"^##\s+Final verification\s*$", re.IGNORECASE | re.MULTILINE)
TEST_REFERENCE_RE = re.compile(r"(?P<path>(?:tests|web/tests)/[A-Za-z0-9._/\-]+\.(?:py|ts|tsx))(?:::[A-Za-z0-9_]+)?")
FENCED_BLOCK_RE = re.compile(r"```(?:[A-Za-z0-9_-]+)?\n(?P<body>[\s\S]*?)```", re.MULTILINE)
COMMAND_LINE_RE = re.compile(r"^\s*\$\s+(?P<command>.+?)\s*$")
EXIT_CODE_RE = re.compile(r"exit code:\s*(?P<code>-?\d+)\b", re.IGNORECASE)
SKIPPED_RE = re.compile(r"Number of skipped tests in the run above:\s*(?P<count>\d+)", re.IGNORECASE)
FEATURE_SLUG_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BRANCH_METADATA_RE = re.compile(r"^codex/(?P<slug>[a-z0-9][a-z0-9._-]*)$")
WORKTREE_METADATA_RE = re.compile(r"^\.worktrees/(?P<slug>[a-z0-9][a-z0-9._-]*)/?$")
LOCAL_CITATION_RE = re.compile(
    r"(?P<path>(?:AGENTS|CLAUDE|Makefile|Dockerfile)\.md|"
    r"(?:\.agents|docs|scripts|src|tests|web)/[A-Za-z0-9._/\-]+):(?P<line>\d+)"
)
URL_CITATION_RE = re.compile(r"https://[^\s`)>\]]+")
BACKTICK_TOKEN_RE = re.compile(r"`([^`]+)`")
SPEC_AC_RE = re.compile(r"^\s*-\s+AC(?P<number>\d+)\.", re.IGNORECASE | re.MULTILINE)
SPEC_COMPLIANCE_AC_RE = re.compile(r"\bAC(?P<number>\d+)\b", re.IGNORECASE)
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
LEGACY_SDD_LIFECYCLE_CHECK_RE = re.compile(
    r"scripts/(?:validate_sdd_artifacts|check_sdd_gate)\.py[^\n`|;&]*--check"
)
TASK_NUMBER_RE = re.compile(r"^Task\s+(?P<number>\d+)\b", re.IGNORECASE)
TASK_SELECTOR_RE = re.compile(r"^[1-9]\d*$")
TASK_SELECTOR_ERROR = "task selector must be a numeric task number without leading zeroes"
TASK_DEPENDENCY_RE = re.compile(r"\bTasks?\s+(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?\b", re.IGNORECASE)
HANDOFF_TITLE_RE = re.compile(
    r"^#\s+Subagent Handoff - (?P<feature>[^/\n]+?)\s*/\s*(?P<task>Task\s+\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
HANDOFF_MODE_RE = re.compile(
    r"^\s*Mode:\s*(?P<mode>read-only|write-allowed|review-only)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
HANDOFF_CONTEXT_PACKET_RE = re.compile(
    r"^#\s+Context Packet - (?P<feature>[^/\n]+?)\s*/\s*(?P<task>Task\s+\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

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
GATE_EVIDENCE_HEADERS = {
    "## Clarifications": ("Question", "Answer", "Approved by", "Approved at"),
    "## Requirement Checklist": ("Requirement", "Quality gate"),
    "## Analyze Gate": ("Check", "Result"),
    "## Gate Compliance": ("Gate", "Evidence"),
}
SPEC_COMPLIANCE_HEADER = ("Acceptance criterion", "Status", "Evidence")
COVERAGE_HEADER = ("metric", "value", "threshold", "status")
GATE_COMPLIANCE_GATES = ("Clarify", "Checklist", "Analyze", "Implement", "Verify")
E2E_GOLDEN_PATH_CHECKS = (
    "/readyz returned 200",
    "writer wrote a row visible to a separate process",
    "/api/recent returned the injected event",
    "WS /ws/live pushed within 5s",
    "testcontainers PG and uvicorn subprocess cleaned up",
)
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
VALID_FACTORY_LANES = {
    "Spec/plan",
    "Domain implementation",
    "Harness/tests",
    "Docs/contracts",
    "Risk radar",
    "Final integration",
}
VERIFICATION_TABLE_STATUSES = {
    "pass",
    "passed",
    "fail",
    "failed",
    "verified",
    "met",
    "complete",
    "completed",
    "blocked",
    "in progress",
    "not applicable",
    "superseded",
}
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
    "skip_golden=1",
)
ACTIVE_PLACEHOLDER_FINAL_EVIDENCE_PHRASES = (
    "pending final run",
    "exit code: pending",
    "<paste full stdout/stderr here>",
)
RUNTIME_SKIP_SWITCHES = ("SKIP_E2E=1", "SKIP_GOLDEN=1")
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
    "plan-analyze-gate-invalid",
    "artifact-owning-link-mismatch",
    "missing-gate-section",
    "duplicate-gate-section",
    "gate-evidence-missing",
    "metadata-date-invalid",
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
    "task-invalid-agent-loop-fields",
    "task-missing-review-fields",
    "task-invalid-review-fields",
    "task-complete-missing-review-evidence",
    "task-missing-subagent-handoff-artifact",
    "task-invalid-subagent-handoff-artifact",
    "task-missing-subagent-report-artifact",
    "task-invalid-subagent-report-artifact",
    "task-complete-missing-failing-test-evidence",
    "task-complete-missing-verification-evidence",
    "task-incomplete-in-verified-feature",
    "tasks-final-verification-duplicated",
    "verification-status-token-invalid",
    "verified-missing-check-all",
    "verified-extra-verification-command",
    "verified-extra-verification-output",
    "verified-missing-spec-compliance-evidence",
    "verified-incomplete-spec-compliance",
    "verified-coverage-incomplete",
    "verified-e2e-incomplete",
    "verified-contradicts-evidence",
    "verified-unexplained-skips",
    "superseded-missing-successor",
    "superseded-successor-mismatch",
    "active-touch-conflict",
    "active-feature-too-large",
    "active-sdd-lifecycle-check-flag-invalid",
    "active-placeholder-final-evidence",
    "active-skipped-count-without-final-evidence",
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
    issues.extend(_feature_lane_artifact_issues(root))
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


def is_task_number_selector(selector: str) -> bool:
    return bool(TASK_SELECTOR_RE.fullmatch(selector.strip()))


def find_task_by_number(feature: SddFeature, selector: str) -> TaskRecord | None:
    normalized_selector = selector.strip()
    if not is_task_number_selector(normalized_selector):
        return None
    selected_number = int(normalized_selector)
    for task in feature.tasks:
        if task_number(task) == selected_number:
            return task
    return None


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
    args = parser.parse_args(argv)

    issues = validate_sdd_root(args.root)
    if not issues:
        print("SDD artifact validation passed.")
        return 0

    for issue in issues:
        print(f"{issue.severity}: {issue.code}: {issue.path}: {issue.message}", file=sys.stderr)
    return 1


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


def _feature_lane_artifact_issues(root: Path) -> list[SddIssue]:
    issues: list[SddIssue] = []
    for lane in ("active", "completed"):
        lane_root = root / "docs" / "sdd" / "features" / lane
        if not lane_root.exists():
            continue
        for child in lane_root.iterdir():
            if child.name.startswith(".") or child.is_dir():
                continue
            issues.append(
                SddIssue(
                    code="unexpected-artifact",
                    path=_relative(root, child),
                    message="feature lanes must contain only feature directories; loose files are not SDD records",
                )
            )
    return issues


def _feature_issues(feature: SddFeature) -> list[SddIssue]:
    issues: list[SddIssue] = []
    issues.extend(_unexpected_artifact_issues(feature))
    issues.extend(_feature_identity_issues(feature))
    issues.extend(_worktree_metadata_issues(feature))
    for artifact in feature.artifacts.values():
        issues.extend(_artifact_issues(feature, artifact))
    issues.extend(_artifact_status_mismatch_issues(feature))
    if feature.status.lower() == "superseded":
        issues.extend(_superseded_issues(feature))
    issues.extend(_plan_preflight_issues(feature))
    issues.extend(_acceptance_command_issues(feature))
    issues.extend(_task_issues(feature))
    issues.extend(_active_feature_size_issues(feature))
    issues.extend(_active_sdd_lifecycle_check_flag_issues(feature))
    issues.extend(_active_placeholder_final_evidence_issues(feature))
    issues.extend(_active_skipped_count_without_final_evidence_issues(feature))
    if feature.status.lower() == "verified":
        issues.extend(_verified_issues(feature))
    return issues


def _active_feature_size_issues(feature: SddFeature) -> list[SddIssue]:
    if feature.state != "active" or len(feature.tasks) <= MAX_ACTIVE_FEATURE_TASKS:
        return []
    return [
        _issue(
            "active-feature-too-large",
            feature.artifacts["tasks.md"],
            f"active feature has {len(feature.tasks)} tasks; split or supersede before exceeding "
            f"{MAX_ACTIVE_FEATURE_TASKS} tasks",
        )
    ]


def _active_sdd_lifecycle_check_flag_issues(feature: SddFeature) -> list[SddIssue]:
    if feature.state != "active":
        return []
    offenders: list[str] = []
    for artifact in feature.artifacts.values():
        if artifact.missing:
            continue
        for line in artifact.text.splitlines():
            match = LEGACY_SDD_LIFECYCLE_CHECK_RE.search(line)
            if match is not None:
                offenders.append(f"{artifact.name}: {match.group(0)}")
    if not offenders:
        return []
    return [
        _issue(
            "active-sdd-lifecycle-check-flag-invalid",
            feature.artifacts["tasks.md"],
            "active SDD records must not advertise legacy SDD lifecycle --check flags: "
            + "; ".join(dict.fromkeys(offenders)),
        )
    ]


def _active_placeholder_final_evidence_issues(feature: SddFeature) -> list[SddIssue]:
    if feature.state != "active":
        return []
    artifact = feature.artifacts["verification.md"]
    if artifact.missing:
        return []
    section = _section_text(artifact.text, "## Verification commands").lower()
    placeholders = [phrase for phrase in ACTIVE_PLACEHOLDER_FINAL_EVIDENCE_PHRASES if phrase in section]
    if not placeholders:
        return []
    return [
        _issue(
            "active-placeholder-final-evidence",
            artifact,
            "active verification commands must not contain placeholder final transcript evidence: "
            + ", ".join(placeholders),
        )
    ]


def _active_skipped_count_without_final_evidence_issues(feature: SddFeature) -> list[SddIssue]:
    if feature.state != "active":
        return []
    artifact = feature.artifacts["verification.md"]
    if artifact.missing:
        return []
    skipped_section = _section_text(artifact.text, "## Skipped tests")
    if SKIPPED_RE.search(skipped_section) is None:
        return []
    make_check_all = _verification_make_check_all_block(artifact.text)
    make_check_all_exit_codes = _command_exit_codes(make_check_all) if make_check_all is not None else ()
    if make_check_all_exit_codes == (0,):
        return []
    return [
        _issue(
            "active-skipped-count-without-final-evidence",
            artifact,
            "active Skipped tests numeric run-above count requires successful final "
            "`make check-all` evidence in Verification commands; use non-final prose until that run exists",
        )
    ]


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
    issues.extend(_metadata_date_issues(artifact))
    issues.extend(_artifact_owning_link_issues(feature, artifact))

    missing_sections = [
        section for section in SECTION_REQUIREMENTS[artifact.name] if not has_markdown_section(artifact.text, section)
    ]
    if missing_sections:
        issues.append(_issue("missing-gate-section", artifact, f"missing sections: {', '.join(missing_sections)}"))
    duplicate_sections = _duplicate_required_sections(artifact)
    if duplicate_sections:
        issues.append(
            _issue(
                "duplicate-gate-section",
                artifact,
                "required sections must be unique: " + ", ".join(duplicate_sections),
            )
        )
    issues.extend(_gate_evidence_issues(artifact))
    if artifact.name == "plan.md":
        issues.extend(_plan_analyze_gate_issues(artifact))
    if artifact.name == "spec.md":
        issues.extend(_spec_background_issues(feature, artifact))
    if artifact.name == "tasks.md":
        issues.extend(_tasks_final_verification_issues(artifact))
    if artifact.name == "verification.md":
        issues.extend(_verification_status_token_issues(artifact))
    return issues


def _verification_status_token_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    invalid_rows: list[str] = []
    for cells in _section_table_rows(artifact.text, "## Spec compliance", SPEC_COMPLIANCE_HEADER):
        if len(cells) < len(SPEC_COMPLIANCE_HEADER):
            continue
        status = _clean_value(cells[1])
        if _valid_verification_table_status(status):
            continue
        criterion = _clean_value(cells[0]) or "<unnamed criterion>"
        invalid_rows.append(f"Spec compliance {criterion} => {status or '<missing status>'}")

    for cells in _section_table_rows(artifact.text, "## Coverage", COVERAGE_HEADER):
        if len(cells) < len(COVERAGE_HEADER):
            continue
        status = _clean_value(cells[3])
        if _valid_verification_table_status(status):
            continue
        metric = _clean_value(cells[0]) or "<unnamed metric>"
        invalid_rows.append(f"Coverage {metric} => {status or '<missing status>'}")

    if not invalid_rows:
        return []
    return [
        _issue(
            "verification-status-token-invalid",
            artifact,
            "verification table status cells must use machine-readable status words: " + "; ".join(invalid_rows),
        )
    ]


def _valid_verification_table_status(value: str) -> bool:
    return _clean_value(value).lower() in VERIFICATION_TABLE_STATUSES


def _tasks_final_verification_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    if TASKS_FINAL_VERIFICATION_HEADING_RE.search(artifact.text) is None:
        return []
    return [
        _issue(
            "tasks-final-verification-duplicated",
            artifact,
            "tasks.md must not maintain a Final verification checklist; put command evidence in verification.md",
        )
    ]


def _metadata_date_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    invalid_fields = [
        f"{artifact.name} {field}"
        for field in ("date", "approved at")
        if field in METADATA_REQUIREMENTS[artifact.name]
        and not _is_placeholder(artifact.fields.get(field, ""))
        and not _is_canonical_date_value(artifact.fields[field])
    ]
    if not invalid_fields:
        return []
    return [
        _issue(
            "metadata-date-invalid",
            artifact,
            "metadata date fields must use canonical YYYY-MM-DD real dates: " + ", ".join(invalid_fields),
        )
    ]


def _plan_analyze_gate_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    invalid_results = analyze_gate_invalid_results(artifact.text)
    if not invalid_results:
        return []
    return [
        _issue(
            "plan-analyze-gate-invalid",
            artifact,
            "Analyze Gate results must start with `Pass:` or `Blocked:`: " + "; ".join(invalid_results),
        )
    ]


def _acceptance_command_issues(feature: SddFeature) -> list[SddIssue]:
    spec_artifact = feature.artifacts["spec.md"]
    plan_artifact = feature.artifacts["plan.md"]
    if spec_artifact.missing or plan_artifact.missing:
        return []

    spec_number_sequence = _spec_acceptance_numbers(spec_artifact.text)
    plan_commands = _plan_acceptance_commands(plan_artifact.text)
    plan_number_sequence = [number for number, _command in plan_commands]
    issues: list[SddIssue] = []
    if not spec_number_sequence:
        issues.append(
            _issue(
                "acceptance-numbering-invalid",
                spec_artifact,
                "spec acceptance criteria must contain at least one current AC row",
            )
        )
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
        if not has_markdown_section(artifact.text, heading):
            continue
        if section_has_gate_evidence(artifact.text, heading):
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
        if _is_fence_line(line):
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
    cited_lines: list[str] = []
    for citation in citations:
        citation_path = citation.group("path")
        citation_line = int(citation.group("line"))
        path = root / citation_path
        if not path.is_file():
            invalid.append(f"{citation_path}:{citation_line} does not exist")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        line_count = len(lines)
        if citation_line < 1 or citation_line > line_count:
            invalid.append(f"{citation_path}:{citation_line} is outside 1..{line_count}")
            continue
        cited_lines.append(lines[citation_line - 1])
    missing_evidence_tokens = _missing_cited_evidence_tokens(block, cited_lines)
    invalid.extend(f"does not mention cited evidence token `{token}`" for token in missing_evidence_tokens)
    return ", ".join(invalid)


def _missing_cited_evidence_tokens(block: str, cited_lines: list[str]) -> list[str]:
    evidence_tokens = [
        token
        for token in (match.group(1).strip() for match in BACKTICK_TOKEN_RE.finditer(block))
        if token and not LOCAL_CITATION_RE.fullmatch(token) and not URL_CITATION_RE.fullmatch(token)
    ]
    if not evidence_tokens:
        return []
    cited_text = "\n".join(cited_lines).lower()
    return [token for token in evidence_tokens if token.lower() not in cited_text]


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
        invalid_fields = _invalid_task_fields(task, feature)
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
        invalid_agent_fields = _invalid_agent_loop_fields(task)
        if invalid_agent_fields:
            issues.append(
                _issue(
                    "task-invalid-agent-loop-fields",
                    tasks_artifact,
                    f"{task.title} invalid fields: {', '.join(invalid_agent_fields)}",
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
        issues.extend(_complete_task_failing_test_evidence_issues(feature, task))
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


def _invalid_task_fields(task: TaskRecord, feature: SddFeature) -> list[str]:
    invalid: list[str] = []
    for field_name in ("file(s)", "touch set"):
        value = task.fields.get(field_name, "")
        if _is_placeholder(value):
            continue
        if not _all_list_items(value, _is_repo_path):
            invalid.append(field_name)
            continue
        missing_paths = _missing_current_task_paths(feature, value)
        if missing_paths:
            invalid.append(f"{field_name} missing current paths: {', '.join(missing_paths)}")

    removed_files = task.fields.get("removed file(s)", "")
    if not _is_placeholder(removed_files):
        if not _all_list_items(removed_files, _is_repo_path):
            invalid.append("removed file(s)")
        else:
            still_present = _present_current_task_paths(feature, removed_files)
            if still_present:
                invalid.append(f"removed file(s) still present: {', '.join(still_present)}")

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


def _repo_root_for_feature(feature: SddFeature) -> Path:
    return feature.path.parents[4]


def _task_path_items(value: str) -> tuple[str, ...]:
    items = [item.strip() for item in re.split(r"[,;]", value.replace("`", "")) if item.strip()]
    return tuple(item for item in items if item.lower() not in {"none", "not delegated"})


def _missing_current_task_paths(feature: SddFeature, value: str) -> tuple[str, ...]:
    if feature.state != "active":
        return ()
    root = _repo_root_for_feature(feature)
    return tuple(path for path in _task_path_items(value) if not _repo_path_exists(root, path))


def _present_current_task_paths(feature: SddFeature, value: str) -> tuple[str, ...]:
    if feature.state != "active":
        return ()
    root = _repo_root_for_feature(feature)
    return tuple(path for path in _task_path_items(value) if _repo_path_exists(root, path))


def _repo_path_exists(root: Path, repo_path: str) -> bool:
    if any(character in repo_path for character in "*?[]"):
        return any(root.glob(repo_path))
    return (root / repo_path).exists()


def _invalid_agent_loop_fields(task: TaskRecord) -> list[str]:
    invalid: list[str] = []
    factory_lane = task.fields.get("factory lane", "").replace("`", "").strip()
    if factory_lane and factory_lane not in VALID_FACTORY_LANES:
        invalid.append("factory lane")
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
    report_mode = _extract_report_mode(report_text)
    if report_mode is None:
        return [
            _issue(
                "task-invalid-subagent-report-artifact",
                tasks_artifact,
                f"{task.title} subagent report has no Mode line: {report_value}",
            )
        ]

    expected_mode = _subagent_handoff_mode(feature, task) or report_mode
    report_issues = validate_subagent_report(report_text, mode=expected_mode, task_fields=task.fields)
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
        handoff_text = handoff_path.read_text(encoding="utf-8")
        handoff_issues = _subagent_handoff_contract_issues(feature, task, handoff_text)
        if handoff_issues:
            return [
                _issue(
                    "task-invalid-subagent-handoff-artifact",
                    tasks_artifact,
                    f"{task.title} invalid subagent handoff: {'; '.join(handoff_issues)}",
                )
            ]
        return []
    return [
        _issue(
            "task-missing-subagent-handoff-artifact",
            tasks_artifact,
            f"{task.title} missing subagent handoff artifact: {handoff_value}",
        )
    ]


def _subagent_handoff_contract_issues(feature: SddFeature, task: TaskRecord, text: str) -> list[str]:
    task_anchor = _task_anchor(task)
    if task_anchor is None:
        return ["task heading is not machine-readable"]

    top_level_text = _text_without_fenced_blocks(text)
    issues: list[str] = []
    title_match = HANDOFF_TITLE_RE.search(top_level_text)
    if title_match is None:
        issues.append("missing matching Subagent Handoff title")
    else:
        _append_handoff_binding_issues(issues, title_match, feature.slug, task_anchor, "handoff title")

    mode_match = HANDOFF_MODE_RE.search(top_level_text)
    mode = mode_match.group("mode").lower() if mode_match else ""
    if not mode:
        issues.append("missing valid Mode line")
    else:
        if "Mode constraints:" not in top_level_text:
            issues.append("missing Mode constraints")
        missing_constraints = [line for line in mode_constraint_lines(mode) if line not in top_level_text]
        if missing_constraints:
            issues.append("missing Mode constraints for mode: " + ", ".join(missing_constraints))

    context_match = HANDOFF_CONTEXT_PACKET_RE.search(text)
    if context_match is None:
        issues.append("missing matching embedded Context Packet title")
    else:
        _append_handoff_binding_issues(issues, context_match, feature.slug, task_anchor, "context packet title")
        context_text = _embedded_context_packet_text(text, feature.slug, task_anchor)
        if context_text is None:
            issues.append("missing matching embedded Context Packet fenced block")
        elif mode:
            _append_context_packet_mode_issues(issues, context_text, mode)

    if mode:
        expected_command = _expected_report_validation_command(feature.slug, task_anchor, mode)
        if expected_command not in _normalize_handoff_text(top_level_text):
            issues.append(f"report validation command must be exact: {expected_command}")
    return issues


def _expected_report_validation_command(feature_slug: str, task_anchor: str, mode: str) -> str:
    task_number_text = task_anchor.removeprefix("Task ")
    return (
        "uv run python scripts/validate_subagent_report.py "
        f"--feature {feature_slug} --task {task_number_text} --mode {mode} --report <report.md>"
    )


def _embedded_context_packet_text(text: str, expected_feature: str, expected_task: str) -> str | None:
    for block_match in FENCED_BLOCK_RE.finditer(text):
        body = block_match.group("body")
        context_match = HANDOFF_CONTEXT_PACKET_RE.search(body)
        if context_match is None:
            continue
        actual_feature = " ".join(context_match.group("feature").strip().split())
        actual_task = " ".join(context_match.group("task").strip().split())
        if actual_feature == expected_feature and actual_task.lower() == expected_task.lower():
            return body
    return None


def _append_context_packet_mode_issues(issues: list[str], context_text: str, mode: str) -> None:
    context_mode_match = HANDOFF_MODE_RE.search(context_text)
    if context_mode_match is None:
        issues.append("embedded Context Packet missing Mode line")
        return

    context_mode = context_mode_match.group("mode").lower()
    if context_mode != mode:
        issues.append(f"embedded Context Packet mode must match handoff mode: {mode}")

    if "Mode constraints:" not in context_text:
        issues.append("embedded Context Packet missing Mode constraints")
        return

    missing_constraints = [line for line in mode_constraint_lines(mode) if line not in context_text]
    if missing_constraints:
        issues.append("embedded Context Packet missing Mode constraints for mode: " + ", ".join(missing_constraints))


def _subagent_handoff_mode(feature: SddFeature, task: TaskRecord) -> str | None:
    handoff_value = task.fields.get("subagent handoff", "")
    if _is_not_delegated(handoff_value) or _is_placeholder(handoff_value) or not _is_repo_path(handoff_value):
        return None

    handoff_path = _repo_root(feature) / handoff_value.replace("`", "").strip()
    if not handoff_path.exists():
        return None

    mode_match = HANDOFF_MODE_RE.search(handoff_path.read_text(encoding="utf-8"))
    return mode_match.group("mode").lower() if mode_match else None


def _append_handoff_binding_issues(
    issues: list[str],
    match: re.Match[str],
    expected_feature: str,
    expected_task: str,
    label: str,
) -> None:
    actual_feature = " ".join(match.group("feature").strip().split())
    actual_task = " ".join(match.group("task").strip().split())
    if actual_feature != expected_feature or actual_task.lower() != expected_task.lower():
        issues.append(f"{label} expected {expected_feature} / {expected_task}, saw {actual_feature} / {actual_task}")


def _task_anchor(task: TaskRecord) -> str | None:
    number = task_number(task)
    return f"Task {number}" if number is not None else None


def _normalize_handoff_text(text: str) -> str:
    return " ".join(text.replace("`", " ").split())


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


def _complete_task_failing_test_evidence_issues(feature: SddFeature, task: TaskRecord) -> list[SddIssue]:
    if task.fields.get("status", "").strip().lower() != "[x]":
        return []

    expected_paths = _test_reference_paths(task.fields.get("failing test first", ""))
    if not expected_paths:
        return []

    artifact = feature.artifacts["verification.md"]
    missing_paths = [
        path
        for path in expected_paths
        if artifact.missing or not _has_successful_test_path_evidence(artifact.text, path)
    ]
    if not missing_paths:
        return []
    return [
        _issue(
            "task-complete-missing-failing-test-evidence",
            feature.artifacts["tasks.md"],
            f"{task.title} lacks exit code 0 evidence covering failing-test paths: {', '.join(missing_paths)}",
        )
    ]


def _test_reference_paths(value: str) -> tuple[str, ...]:
    paths = [match.group("path") for match in TEST_REFERENCE_RE.finditer(value.replace("`", ""))]
    return tuple(dict.fromkeys(paths))


def _has_successful_test_path_evidence(text: str, expected_path: str) -> bool:
    evidence = _command_evidence(_task_evidence_text(text))
    return any(expected_path in command and 0 in exit_codes for command, exit_codes in evidence.items())


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
    section = _text_without_fenced_blocks(_section_text(text, "## Acceptance criteria"))
    return [int(match.group("number")) for match in SPEC_AC_RE.finditer(section)]


def _invalid_acceptance_criterion_lines(text: str) -> list[str]:
    section = _text_without_fenced_blocks(_section_text(text, "## Acceptance criteria"))
    return [
        match.group(0).strip()
        for match in SPEC_AC_LINE_RE.finditer(section)
        if not SPEC_AC_FORMAT_RE.match(match.group(0))
    ]


def _plan_acceptance_commands(text: str) -> list[tuple[int, str]]:
    section = _text_without_fenced_blocks(_section_text(text, "## Acceptance test commands"))
    return [
        (int(match.group("number")), _clean_command(match.group("command")))
        for match in PLAN_AC_COMMAND_RE.finditer(section)
    ]


def _invalid_plan_acceptance_command_lines(text: str) -> list[str]:
    section = _text_without_fenced_blocks(_section_text(text, "## Acceptance test commands"))
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


def verify_gate_evidence_issues(feature: SddFeature) -> list[SddIssue]:
    return _verified_issues(feature)


def _verified_issues(feature: SddFeature) -> list[SddIssue]:
    artifact = feature.artifacts["verification.md"]
    if artifact.missing:
        return []
    normalized_text = artifact.text.lower()
    issues: list[SddIssue] = []
    make_check_all = _verification_make_check_all_block(artifact.text)
    make_check_all_exit_codes = _command_exit_codes(make_check_all) if make_check_all is not None else ()
    if make_check_all is None:
        issues.append(
            _issue("verified-missing-check-all", artifact, "Verified records require make check-all with exit code: 0")
        )
    elif make_check_all_exit_codes != (0,):
        issues.append(
            _issue(
                "verified-missing-check-all",
                artifact,
                "Verified records require final make check-all with exactly one exit code 0",
            )
        )
    verification_blocks = _verification_fenced_blocks(artifact.text)
    if len(verification_blocks) != 1:
        issues.append(
            _issue(
                "verified-extra-verification-output",
                artifact,
                f"Verified Verification commands must contain exactly one fenced transcript block; "
                f"found {len(verification_blocks)}",
            )
        )
    verification_commands = _verification_commands(artifact.text)
    if verification_commands != ["make check-all"]:
        issues.append(
            _issue(
                "verified-extra-verification-command",
                artifact,
                "Verified Verification commands must contain exactly one `make check-all`; found commands: "
                + (_format_command_list(verification_commands) if verification_commands else "<none>"),
            )
        )
    if any(phrase in normalized_text for phrase in CONTRADICTION_PHRASES):
        issues.append(
            _issue(
                "verified-contradicts-evidence", artifact, "Verified record contains contradictory evidence language"
            )
        )
    if make_check_all is not None and any(exit_code != 0 for exit_code in make_check_all_exit_codes):
        issues.append(
            _issue(
                "verified-contradicts-evidence",
                artifact,
                "Verified command block records non-zero exit code: " + _format_exit_codes(make_check_all_exit_codes),
            )
        )
    issues.extend(_verified_spec_compliance_issues(feature, artifact))
    issues.extend(_verified_coverage_issues(artifact))
    issues.extend(_verified_e2e_issues(artifact))
    skipped_section = _section_text(artifact.text, "## Skipped tests")
    skipped_match = SKIPPED_RE.search(skipped_section)
    if skipped_match is None:
        issues.append(
            _issue(
                "verified-unexplained-skips",
                artifact,
                "Verified Skipped tests section must include numeric skipped-test count",
            )
        )
    elif int(skipped_match.group("count")) > 0:
        issues.append(
            _issue(
                "verified-unexplained-skips",
                artifact,
                "Verified record must report zero skipped tests; "
                "positive skipped-test counts cannot serve as completion evidence",
            )
        )
    return issues


def _verified_e2e_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    section = _text_without_fenced_blocks(_section_text(artifact.text, "## E2E golden path"))
    for skip_switch in RUNTIME_SKIP_SWITCHES:
        if skip_switch in section:
            return [
                _issue(
                    "verified-e2e-incomplete",
                    artifact,
                    f"Verified E2E golden path cannot use {skip_switch} as completion evidence",
                )
            ]

    missing_or_unchecked = [
        check
        for check in E2E_GOLDEN_PATH_CHECKS
        if f"- [x] {check}" not in section and f"- [X] {check}" not in section
    ]
    unchecked = [line.strip() for line in section.splitlines() if line.strip().startswith("- [ ]")]
    if not missing_or_unchecked and not unchecked:
        return []

    parts: list[str] = []
    if missing_or_unchecked:
        parts.append("missing checked signals: " + ", ".join(missing_or_unchecked))
    if unchecked:
        parts.append("unchecked rows: " + "; ".join(unchecked))
    return [
        _issue(
            "verified-e2e-incomplete",
            artifact,
            "Verified E2E golden path must check every required runtime signal: " + "; ".join(parts),
        )
    ]


def _verified_coverage_issues(artifact: ArtifactRecord) -> list[SddIssue]:
    rows = _section_table_rows(artifact.text, "## Coverage", COVERAGE_HEADER)
    if not rows:
        return [
            _issue(
                "verified-coverage-incomplete",
                artifact,
                "Verified Coverage must contain at least one canonical metric row",
            )
        ]

    incomplete_rows: list[str] = []
    for cells in rows:
        metric = _clean_value(cells[0]) if cells else "<unnamed metric>"
        if len(cells) < len(COVERAGE_HEADER):
            incomplete_rows.append(f"{metric or '<unnamed metric>'} => malformed row")
            continue
        placeholder_columns = [
            COVERAGE_HEADER[index]
            for index, cell in enumerate(cells[: len(COVERAGE_HEADER)])
            if is_placeholder_table_cell(cell)
        ]
        if placeholder_columns:
            incomplete_rows.append(
                f"{metric or '<unnamed metric>'} => placeholder {', '.join(placeholder_columns)}"
            )
            continue
        if not _is_complete_compliance_status(cells[3]):
            incomplete_rows.append(f"{metric or '<unnamed metric>'} => {_clean_value(cells[3]) or '<missing status>'}")
    if not incomplete_rows:
        return []
    return [
        _issue(
            "verified-coverage-incomplete",
            artifact,
            "Verified Coverage rows must all be complete: " + ", ".join(incomplete_rows),
        )
    ]


def _verified_spec_compliance_issues(feature: SddFeature, artifact: ArtifactRecord) -> list[SddIssue]:
    command_evidence = _command_evidence(_task_evidence_text(artifact.text))
    rows = _section_table_rows(artifact.text, "## Spec compliance", SPEC_COMPLIANCE_HEADER)
    if not rows:
        return [
            _issue(
                "verified-incomplete-spec-compliance",
                artifact,
                "Verified Spec compliance must contain at least one canonical evidence row",
            )
        ]

    incomplete_rows: list[str] = []
    missing_commands: list[str] = []
    missing_command_evidence_rows: list[str] = []
    coverage_issue = _spec_compliance_coverage_issue(feature, rows)
    for cells in rows:
        if len(cells) < 3:
            continue
        criterion = _clean_value(cells[0]) or "<unnamed criterion>"
        status = _clean_value(cells[1]) or "<missing status>"
        if not _is_complete_compliance_status(cells[1]):
            incomplete_rows.append(f"{criterion} => {status}")
            continue
        if is_placeholder_table_cell(cells[2]):
            incomplete_rows.append(f"{criterion} => placeholder evidence")
            continue
        commands = [
            _clean_command(match.group(1))
            for match in re.finditer(r"`([^`]+)`", cells[2])
            if _looks_like_command(match.group(1))
        ]
        if not commands:
            missing_command_evidence_rows.append(criterion)
            continue
        missing_commands.extend(
            command
            for command in commands
            if not any(exit_code == 0 for exit_code in command_evidence.get(command, ()))
        )

    issues: list[SddIssue] = []
    if coverage_issue:
        issues.append(_issue("verified-incomplete-spec-compliance", artifact, coverage_issue))
    if incomplete_rows:
        issues.append(
            _issue(
                "verified-incomplete-spec-compliance",
                artifact,
                "Verified spec compliance rows must all be complete: " + ", ".join(incomplete_rows),
            )
        )
    if missing_commands:
        issues.append(
            _issue(
                "verified-missing-spec-compliance-evidence",
                artifact,
                "Verified spec compliance rows lack exit code 0 command evidence: "
                + ", ".join(dict.fromkeys(missing_commands)),
            )
        )
    if missing_command_evidence_rows:
        issues.append(
            _issue(
                "verified-missing-spec-compliance-evidence",
                artifact,
                "Verified spec compliance rows must cite command-shaped evidence: "
                + ", ".join(dict.fromkeys(missing_command_evidence_rows)),
            )
        )
    return issues


def _spec_compliance_coverage_issue(feature: SddFeature, rows: list[list[str]]) -> str:
    spec_artifact = feature.artifacts["spec.md"]
    if spec_artifact.missing:
        return ""
    expected_numbers = _spec_acceptance_numbers(spec_artifact.text)
    actual_numbers = [_spec_compliance_row_number(cells[0]) for cells in rows if cells]
    expected = tuple(expected_numbers)
    actual = tuple(number for number in actual_numbers if number is not None)
    if actual == expected and len(actual_numbers) == len(actual):
        return ""

    missing = [number for number in expected_numbers if number not in actual]
    extra = [number for number in actual if number not in expected]
    parts: list[str] = []
    if missing:
        parts.append("missing " + ", ".join(f"AC{number}" for number in missing))
    if extra:
        parts.append("extra " + ", ".join(f"AC{number}" for number in extra))
    if len(actual) != len(set(actual)):
        duplicates = [number for number, count in Counter(actual).items() if count > 1]
        parts.append("duplicate " + ", ".join(f"AC{number}" for number in sorted(duplicates)))
    unnumbered_count = len(actual_numbers) - len(actual)
    if unnumbered_count:
        parts.append(f"{unnumbered_count} row(s) without AC number")
    if not parts and actual != expected:
        parts.append(
            "expected "
            + ", ".join(f"AC{number}" for number in expected)
            + " in order, saw "
            + (", ".join(f"AC{number}" for number in actual) or "none")
        )
    return "Verified Spec compliance rows must match spec acceptance criteria: " + "; ".join(parts)


def _spec_compliance_row_number(value: str) -> int | None:
    match = SPEC_COMPLIANCE_AC_RE.search(_clean_value(value))
    if match is None:
        return None
    return int(match.group("number"))


def _is_complete_compliance_status(value: str) -> bool:
    cleaned = _clean_value(value).lower()
    return cleaned in {"pass", "passed", "verified", "met", "complete", "completed", "done"}


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
    return issues


def _active_touch_conflicts(features: list[SddFeature]) -> list[SddIssue]:
    touches: list[tuple[str, str, SddFeature]] = []
    for feature in features:
        if feature.state != "active" or feature.status.lower() == "superseded":
            continue
        for touched_path in feature.touch_set:
            normalized_path = _normalize_repo_path(touched_path)
            if normalized_path:
                touches.append((normalized_path, touched_path, feature))

    issues: list[SddIssue] = []
    reported: set[tuple[str, str, str, str]] = set()
    for index, (left_path, left_raw, left_feature) in enumerate(touches):
        for right_path, right_raw, right_feature in touches[index + 1 :]:
            if left_feature.slug == right_feature.slug:
                continue
            if not _repo_paths_overlap(left_path, right_path):
                continue
            pair_paths = tuple(sorted((left_path, right_path)))
            feature_names = ", ".join(sorted((left_feature.slug, right_feature.slug)))
            overlap_label = left_path if left_path == right_path else f"{left_raw} overlaps {right_raw}"
            for feature, other in ((left_feature, right_feature), (right_feature, left_feature)):
                report_key = (feature.slug, other.slug, pair_paths[0], pair_paths[1])
                if report_key in reported:
                    continue
                reported.add(report_key)
                if _coordination_covers_overlap(feature, other, pair_paths):
                    continue
                issues.append(
                    SddIssue(
                        code="active-touch-conflict",
                        path=feature.relative_path,
                        message=(
                            f"{overlap_label} is touched by active features: {feature_names}; "
                            f"{feature.slug} must coordinate with {other.slug} or the overlapping path"
                        ),
                    )
                )
    return issues


def _normalize_repo_path(value: str) -> str:
    cleaned = value.replace("`", "").strip().strip("/")
    return re.sub(r"/+", "/", cleaned)


def _repo_paths_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _coordination_covers_overlap(feature: SddFeature, other: SddFeature, overlapping_paths: tuple[str, str]) -> bool:
    for conflict_rule in feature.conflict_set:
        normalized_rule = _normalize_repo_path(conflict_rule).lower()
        if "coordinate with " not in normalized_rule:
            continue
        if other.slug.lower() in normalized_rule:
            return True
        if any(path.lower() in normalized_rule for path in overlapping_paths):
            return True
    return False


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
    tasks_section = _text_without_fenced_blocks(_section_text(text, "## Tasks"))
    matches = list(TASK_RE.finditer(tasks_section))
    tasks: list[TaskRecord] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(tasks_section)
        block = tasks_section[match.start() : end]
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
    make_check_all_segments = [
        segment for block in _verification_fenced_blocks(text) for segment in _command_segments(block, "make check-all")
    ]
    if len(make_check_all_segments) != 1:
        return None
    return make_check_all_segments[0]


def _verification_fenced_blocks(text: str) -> list[str]:
    section = _section_text(text, "## Verification commands")
    return [match.group("body").strip() for match in FENCED_BLOCK_RE.finditer(section)]


def _verification_commands(text: str) -> list[str]:
    section = _section_text(text, "## Verification commands")
    return [
        _clean_command(command_match.group("command"))
        for line in section.splitlines()
        if (command_match := COMMAND_LINE_RE.match(line))
    ]


def _format_command_list(commands: list[str]) -> str:
    counts = Counter(commands)
    return ", ".join(
        f"{command} x{count}" if count > 1 else command
        for command, count in counts.items()
    )


def _command_segments(block: str, command: str) -> list[str]:
    lines = block.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if (match := COMMAND_LINE_RE.match(line)) and _clean_command(match.group("command")) == command
    ]

    segments: list[str] = []
    for start in starts:
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if COMMAND_LINE_RE.match(lines[index]):
                end = index
                break
        segments.append("\n".join(lines[start:end]).strip())
    return segments


def _section_text(text: str, heading: str) -> str:
    return section_text(text, heading)


def section_text(text: str, heading: str) -> str:
    lines = text.splitlines()
    start_index = _section_heading_index(lines, heading)
    if start_index is None:
        return ""
    body: list[str] = []
    in_fenced_block = False
    for line in lines[start_index + 1 :]:
        if _is_fence_line(line):
            in_fenced_block = not in_fenced_block
            body.append(line)
            continue
        if not in_fenced_block and line.strip().startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _text_without_fenced_blocks(text: str) -> str:
    lines: list[str] = []
    in_fenced_block = False
    for line in text.splitlines():
        if _is_fence_line(line):
            in_fenced_block = not in_fenced_block
            continue
        if not in_fenced_block:
            lines.append(line)
    return "\n".join(lines)


def has_markdown_section(text: str, heading: str) -> bool:
    return _section_heading_index(text.splitlines(), heading) is not None


def _duplicate_required_sections(artifact: ArtifactRecord) -> list[str]:
    required_headings = SECTION_REQUIREMENTS.get(artifact.name, ())
    return [
        f"{heading} x{count}"
        for heading in required_headings
        if (count := _section_heading_count(artifact.text, heading)) > 1
    ]


def _section_heading_count(text: str, heading: str) -> int:
    count = 0
    in_fenced_block = False
    for line in text.splitlines():
        if _is_fence_line(line):
            in_fenced_block = not in_fenced_block
            continue
        if not in_fenced_block and line.strip() == heading:
            count += 1
    return count


def _section_heading_index(lines: list[str], heading: str) -> int | None:
    in_fenced_block = False
    for index, line in enumerate(lines):
        if _is_fence_line(line):
            in_fenced_block = not in_fenced_block
            continue
        if not in_fenced_block and line.strip() == heading:
            return index
    return None


def _is_fence_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _section_has_non_placeholder_table_row(text: str, heading: str) -> bool:
    return section_has_gate_evidence(text, heading)


def section_has_gate_evidence(text: str, heading: str) -> bool:
    if heading == "## Gate Compliance":
        blocks = section_gate_table_blocks(text, heading)
        return len(blocks) == 1 and gate_compliance_has_required_rows(blocks[0])
    rows = section_gate_table_rows(text, heading)
    return any(is_gate_evidence_row(heading, cells) for cells in rows)


def section_gate_table_rows(text: str, heading: str) -> list[list[str]]:
    return [row for block in section_gate_table_blocks(text, heading) for row in block]


def section_gate_table_blocks(text: str, heading: str) -> list[list[list[str]]]:
    expected_header = GATE_EVIDENCE_HEADERS[heading]
    section = _section_text(text, heading)
    return table_body_row_blocks(section, expected_header)


def analyze_gate_invalid_results(text: str) -> list[str]:
    invalid_results: list[str] = []
    for cells in section_gate_table_rows(text, "## Analyze Gate"):
        if len(cells) < 2:
            continue
        result = _clean_value(cells[1])
        if _is_placeholder_table_cell(result):
            continue
        if _analyze_result_has_status_evidence(result):
            continue
        check = _clean_value(cells[0]) or "<unnamed check>"
        invalid_results.append(f"{check} => {result}")
    return invalid_results


def _analyze_result_has_status_evidence(result: str) -> bool:
    for status in ("Pass:", "Blocked:"):
        if not result.startswith(status):
            continue
        evidence = result.removeprefix(status).strip()
        return not _is_placeholder_table_cell(evidence)
    return False


def _section_table_rows(text: str, heading: str, expected_header: tuple[str, ...] | None = None) -> list[list[str]]:
    section = _section_text(text, heading)
    return table_body_rows(section, expected_header)


def table_body_rows(section: str, expected_header: tuple[str, ...] | None = None) -> list[list[str]]:
    return [row for block in table_body_row_blocks(section, expected_header) for row in block]


def table_body_row_blocks(
    section: str,
    expected_header: tuple[str, ...] | None = None,
) -> list[list[list[str]]]:
    blocks: list[list[list[str]]] = []
    body_rows: list[list[str]] = []
    current_block: list[str] = []
    for line in _text_without_fenced_blocks(section).splitlines():
        stripped = line.rstrip()
        if _is_table_row_line(stripped):
            current_block.append(stripped)
            continue
        body_rows = _table_block_body_rows(current_block, expected_header)
        if body_rows:
            blocks.append(body_rows)
        current_block = []
    body_rows = _table_block_body_rows(current_block, expected_header)
    if body_rows:
        blocks.append(body_rows)
    return blocks


def _is_table_row_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and not line.startswith("||") and not line.endswith("||")


def _table_block_body_rows(
    table_lines: list[str],
    expected_header: tuple[str, ...] | None = None,
) -> list[list[str]]:
    if len(table_lines) < 3 or not _is_table_separator_row(table_lines[1]):
        return []
    header_cells = _table_cells(table_lines[0])
    if expected_header is not None and tuple(header_cells) != expected_header:
        return []
    separator_cells = _table_cells(table_lines[1])
    if any(_is_table_separator_row(line) for line in table_lines[2:]):
        return []
    body_rows = [_table_cells(line) for line in table_lines[2:]]
    if any(row == header_cells for row in body_rows):
        return []
    if not _table_rows_have_matching_arity([separator_cells, *body_rows], len(header_cells)):
        return []
    return body_rows


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip("|").split("|")]


def _table_rows_have_matching_arity(rows: list[list[str]], expected_count: int) -> bool:
    return expected_count > 0 and all(len(row) == expected_count for row in rows)


def _is_table_separator_row(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(_is_table_separator_cell(cell) for cell in cells)


def _is_table_separator_cell(cell: str) -> bool:
    stripped = cell.strip()
    if not stripped:
        return False
    return "-" in stripped and set(stripped) <= {"-", ":"}


def _is_placeholder_table_cell(value: str) -> bool:
    return is_placeholder_table_cell(value)


def is_table_evidence_row(cells: list[str]) -> bool:
    return len(cells) >= 2 and all(not _is_placeholder_table_cell(cell) for cell in cells)


def is_gate_evidence_row(heading: str, cells: list[str]) -> bool:
    if not is_table_evidence_row(cells):
        return False
    if heading == "## Clarifications":
        return len(cells) >= 4 and _is_canonical_date_value(cells[3])
    return True


def gate_compliance_has_required_rows(rows: list[list[str]]) -> bool:
    gates: list[str] = []
    for cells in rows:
        if not is_table_evidence_row(cells):
            return False
        gate = _clean_value(cells[0])
        gates.append(gate)
    return tuple(gates) == GATE_COMPLIANCE_GATES


def is_placeholder_table_cell(value: str) -> bool:
    cleaned = _clean_value(value).lower()
    normalized = cleaned.rstrip(".:")
    return (
        _is_placeholder(value)
        or normalized in PLACEHOLDER_VALUES
        or normalized.startswith("<")
        or normalized.endswith(">")
        or normalized in {"pass / fail", "yyyy-mm-dd"}
    )


def _is_canonical_date_value(value: str) -> bool:
    cleaned = _clean_value(value)
    if not ISO_DATE_RE.fullmatch(cleaned):
        return False
    try:
        date.fromisoformat(cleaned)
    except ValueError:
        return False
    return True


def _command_exit_codes(block: str) -> tuple[int, ...]:
    return tuple(int(match.group("code")) for match in EXIT_CODE_RE.finditer(block))


def _format_exit_codes(exit_codes: tuple[int, ...]) -> str:
    return ", ".join(str(exit_code) for exit_code in exit_codes) if exit_codes else "<none>"


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
