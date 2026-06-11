from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_sdd_artifacts import SddFeature, scan_sdd_features, validate_sdd_root  # noqa: E402

GATES = ("clarify", "checklist", "analyze", "implement")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SDD lifecycle gates")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--feature", help="feature slug")
    parser.add_argument("--all-active", action="store_true", help="check all active feature gates")
    parser.add_argument("--gate", choices=GATES, help="gate to check")
    parser.add_argument("--check", action="store_true", help="non-mutating check mode")
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
    gates = (gate,) if gate else GATES
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
    return _implement_gate_issues(root, feature)


def _section_gate_issues(feature: SddFeature, artifact_name: str, heading: str, gate: str) -> list[str]:
    artifact = feature.artifacts[artifact_name]
    section = _section_text(artifact.text, heading)
    if not section.strip():
        return [f"missing-gate-section: {artifact.relative_path} missing {heading}"]
    if not _has_table_evidence(section):
        return [f"gate-evidence-missing: {artifact.relative_path} {gate} gate lacks evidence"]
    return []


def _analyze_gate_issues(feature: SddFeature) -> list[str]:
    artifact = feature.artifacts["plan.md"]
    section = _section_text(artifact.text, "## Analyze Gate")
    if not section.strip():
        return [f"missing-gate-section: {artifact.relative_path} missing ## Analyze Gate"]
    if not _has_table_evidence(section):
        return [f"gate-evidence-missing: {artifact.relative_path} analyze gate lacks evidence"]
    if any(_is_failed_result_row(line) for line in section.splitlines()):
        return [f"plan-analyze-gate-invalid: {artifact.relative_path} analyze gate contains failed result"]
    return []


def _implement_gate_issues(root: Path, feature: SddFeature) -> list[str]:
    feature_prefix = feature.relative_path + "/"
    return [
        f"{issue.code}: {issue.path}: {issue.message}"
        for issue in validate_sdd_root(root)
        if issue.path.startswith(feature_prefix) and _is_implement_gate_issue(issue.code)
    ]


def _is_implement_gate_issue(code: str) -> bool:
    if code.startswith("task-"):
        return True
    return code in {"tasks-final-verification-duplicated", "active-touch-conflict"}


def _section_text(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _has_table_evidence(section: str) -> bool:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= {"|", "-", " "}:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    for cells in rows[1:]:
        if cells and all(cell and cell.lower() not in {"pending", "tbd", "todo"} for cell in cells):
            return True
    return False


def _is_failed_result_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|") or set(stripped) <= {"|", "-", " "}:
        return False
    cells = [cell.strip().lower() for cell in stripped.strip("|").split("|")]
    if len(cells) < 2 or cells[0] in {"check", "gate", "requirement"}:
        return False
    return cells[1].startswith(("fail", "failed"))


if __name__ == "__main__":
    raise SystemExit(main())
