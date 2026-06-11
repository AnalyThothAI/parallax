from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_sdd_artifacts import (  # noqa: E402
    SddFeature,
    SddIssue,
    analyze_gate_invalid_results,
    scan_sdd_features,
    section_has_gate_evidence,
    validate_sdd_root,
    verify_gate_evidence_issues,
)
from scripts.validate_sdd_artifacts import (  # noqa: E402
    section_text as validated_section_text,
)

PRE_VERIFY_GATES = ("clarify", "checklist", "analyze", "implement")
GATES = (*PRE_VERIFY_GATES, "verify")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SDD lifecycle gates")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--feature", help="feature slug")
    parser.add_argument("--all-active", action="store_true", help="check all active feature gates")
    parser.add_argument("--gate", choices=GATES, help="gate to check")
    args = parser.parse_args()

    if bool(args.feature) == args.all_active:
        parser.error("provide exactly one of --feature or --all-active")
    if args.feature and not args.gate:
        parser.error("--feature requires --gate")

    if args.all_active:
        return _check_all_active(args.root, args.gate)

    feature = _find_feature(args.root, args.feature or "")
    if feature is None:
        print(f"feature not found: {args.feature}", file=sys.stderr)
        return 1

    gate = args.gate or ""
    issues = _gate_issues(args.root, feature, gate)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1

    print(f"{gate} gate passed: {feature.slug}")
    return 0


def _check_all_active(root: Path, gate: str | None) -> int:
    features = [feature for feature in scan_sdd_features(root) if feature.state == "active"]
    gates = (gate,) if gate else PRE_VERIFY_GATES
    issues = [
        f"{feature.slug} {gate_name}: {issue}"
        for feature in features
        for gate_name in gates
        for issue in _gate_issues(root, feature, gate_name)
    ]
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1

    slugs = ", ".join(feature.slug for feature in features) or "<none>"
    gate_summary = gate or "clarify/checklist/analyze/implement"
    print(f"all active SDD gates passed ({gate_summary}): {slugs}")
    return 0


def _find_feature(root: Path, slug: str) -> SddFeature | None:
    for feature in scan_sdd_features(root):
        if feature.slug == slug:
            return feature
    return None


def _gate_issues(root: Path, feature: SddFeature, gate: str) -> list[str]:
    if gate == "clarify":
        return _section_gate_issues(feature, "spec.md", "## Clarifications", "clarify")
    if gate == "checklist":
        return _section_gate_issues(feature, "spec.md", "## Requirement Checklist", "checklist")
    if gate == "analyze":
        return _analyze_gate_issues(feature)
    if gate == "verify":
        return _verify_gate_issues(root, feature)
    return _implement_gate_issues(root, feature)


def _section_gate_issues(feature: SddFeature, artifact_name: str, heading: str, gate: str) -> list[str]:
    artifact = feature.artifacts[artifact_name]
    section = _section_text(artifact.text, heading)
    if not section.strip():
        return [f"missing-gate-section: {artifact.relative_path} missing {heading}"]
    if not section_has_gate_evidence(artifact.text, heading):
        return [f"gate-evidence-missing: {artifact.relative_path} {gate} gate lacks evidence"]
    return []


def _analyze_gate_issues(feature: SddFeature) -> list[str]:
    artifact = feature.artifacts["plan.md"]
    section = _section_text(artifact.text, "## Analyze Gate")
    if not section.strip():
        return [f"missing-gate-section: {artifact.relative_path} missing ## Analyze Gate"]
    if not section_has_gate_evidence(artifact.text, "## Analyze Gate"):
        return [f"gate-evidence-missing: {artifact.relative_path} analyze gate lacks evidence"]
    invalid_results = analyze_gate_invalid_results(artifact.text)
    if invalid_results:
        return [
            f"plan-analyze-gate-invalid: {artifact.relative_path} "
            f"analyze gate results must start with Pass: or Blocked: {', '.join(invalid_results)}"
        ]
    return []


def _implement_gate_issues(root: Path, feature: SddFeature) -> list[str]:
    return [
        f"{issue.code}: {issue.path}: {issue.message}"
        for issue in _feature_validation_issues(root, feature)
        if _is_implement_gate_issue(feature, issue)
    ]


def _is_implement_gate_issue(feature: SddFeature, issue: SddIssue) -> bool:
    code = issue.code
    if code.startswith("task-"):
        return True
    if issue.path == f"{feature.relative_path}/tasks.md" and code in {"missing-gate-section", "gate-evidence-missing"}:
        return True
    return code in {"tasks-final-verification-duplicated", "active-touch-conflict"}


def _verify_gate_issues(root: Path, feature: SddFeature) -> list[str]:
    structural_issues = _feature_validation_issues(root, feature)
    evidence_issues = verify_gate_evidence_issues(feature)
    completion_issues = _completion_task_issues(feature)
    return [_format_issue(issue) for issue in (*structural_issues, *evidence_issues)] + completion_issues


def _completion_task_issues(feature: SddFeature) -> list[str]:
    incomplete_tasks = [
        task.title for task in feature.tasks if task.fields.get("status", "").strip().lower() != "[x]"
    ]
    if not incomplete_tasks:
        return []
    return [
        "task-incomplete-in-completion-gate: "
        f"{feature.relative_path}/tasks.md: completion gate requires every task status [x]: "
        + ", ".join(incomplete_tasks)
    ]


def _feature_validation_issues(root: Path, feature: SddFeature) -> list[SddIssue]:
    feature_prefix = feature.relative_path + "/"
    return [
        issue
        for issue in validate_sdd_root(root)
        if issue.path == feature.relative_path or issue.path.startswith(feature_prefix)
    ]


def _format_issue(issue: SddIssue) -> str:
    return f"{issue.code}: {issue.path}: {issue.message}"


def _section_text(text: str, heading: str) -> str:
    return validated_section_text(text, heading)

if __name__ == "__main__":
    raise SystemExit(main())
