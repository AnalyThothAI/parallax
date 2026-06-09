from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.subagent_report_contract import VALID_MODES, validate_subagent_report  # noqa: E402
from scripts.validate_sdd_artifacts import (  # noqa: E402
    SddFeature,
    SddIssue,
    TaskRecord,
    scan_sdd_features,
    validate_sdd_root,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a bounded subagent report before parent integration")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--feature", help="optional SDD feature slug for task-bound validation")
    parser.add_argument("--task", help="optional task number or title substring for task-bound validation")
    parser.add_argument("--mode", choices=VALID_MODES, required=True, help="mode used for the subagent handoff")
    parser.add_argument("--report", type=Path, required=True, help="markdown report file to validate")
    args = parser.parse_args(argv)

    if bool(args.feature) != bool(args.task):
        parser.error("--feature and --task must be provided together")

    task: TaskRecord | None = None
    if args.feature and args.task:
        root = args.root.resolve()
        sdd_issues = validate_sdd_root(root)
        if sdd_issues:
            _print_sdd_issues(sdd_issues)
            return 1

        feature = _find_feature(scan_sdd_features(root), args.feature)
        if feature is None:
            print(f"error: SDD feature not found: {args.feature}", file=sys.stderr)
            return 1
        if feature.state != "active":
            print(f"error: subagent reports bind only to active SDD features: {args.feature}", file=sys.stderr)
            return 1

        task = _find_task(feature, args.task)
        if task is None:
            print(f"error: task not found in {feature.slug}: {args.task}", file=sys.stderr)
            return 1

    text = args.report.read_text(encoding="utf-8")
    issues = validate_subagent_report(text, mode=args.mode, task_fields=task.fields if task else None)
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 1

    print("Subagent report validation passed.")
    return 0


def _find_feature(features: list[SddFeature], slug: str) -> SddFeature | None:
    for feature in features:
        if feature.slug == slug:
            return feature
    return None


def _find_task(feature: SddFeature, selector: str) -> TaskRecord | None:
    normalized_selector = selector.strip().lower()
    if normalized_selector.isdigit():
        prefix = f"task {normalized_selector}"
        for task in feature.tasks:
            if task.title.lower().startswith(prefix):
                return task
    for task in feature.tasks:
        if normalized_selector in task.title.lower():
            return task
    return None


def _print_sdd_issues(issues: list[SddIssue]) -> None:
    for issue in issues:
        print(f"error: {issue.code}: {issue.path}: {issue.message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
