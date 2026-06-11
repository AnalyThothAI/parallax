from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_mode_constraints import VALID_MODES, mode_constraint_lines  # noqa: E402
from scripts.validate_sdd_artifacts import (  # noqa: E402
    SddFeature,
    SddIssue,
    TaskRecord,
    find_task_by_number,
    scan_sdd_features,
    task_incomplete_dependencies,
    validate_sdd_root,
)

DISPATCHABLE_STATUSES = {"[ ]", "[~]"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a bounded subagent context packet from an SDD task")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--feature", required=True, help="SDD feature slug")
    parser.add_argument("--task", required=True, help="numeric task number")
    parser.add_argument("--mode", choices=VALID_MODES, default="read-only", help="subagent operating mode")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    issues = validate_sdd_root(root)
    if issues:
        _print_issues(issues)
        return 1

    features = scan_sdd_features(root)
    feature = _find_feature(features, args.feature)
    if feature is None:
        print(f"error: SDD feature not found: {args.feature}", file=sys.stderr)
        return 1
    if feature.state != "active":
        print(f"error: context packets can only be built from active features: {args.feature}", file=sys.stderr)
        return 1

    if not args.task.strip().isdigit():
        print(f"error: task selector must be a numeric task number: {args.task}", file=sys.stderr)
        return 1

    task = find_task_by_number(feature, args.task)
    if task is None:
        print(f"error: task not found in {feature.slug}: {args.task}", file=sys.stderr)
        return 1

    dispatch_issues = task_dispatch_issues(feature, task)
    if dispatch_issues:
        for issue in dispatch_issues:
            print(f"error: {issue}", file=sys.stderr)
        return 1

    print(render_context_packet(feature, task, args.mode))
    return 0


def task_dispatch_issues(feature: SddFeature, task: TaskRecord) -> list[str]:
    status = task.fields.get("status", "").strip().lower()
    if status == "[x]":
        return [f"task is already complete and cannot be dispatched: {task.title}"]
    if status not in DISPATCHABLE_STATUSES:
        return [f"task status is not dispatchable ({status or 'missing'}): {task.title}"]

    incomplete_dependencies = task_incomplete_dependencies(feature, task)
    if incomplete_dependencies:
        dependencies = ", ".join(f"Task {dependency}" for dependency in incomplete_dependencies)
        return [f"dependencies are not complete for {task.title}: {dependencies}"]
    return []


def render_context_packet(feature: SddFeature, task: TaskRecord, mode: str) -> str:
    task_anchor = _task_anchor(task.title)
    touch_set = _split_list_field(task.fields.get("touch set", ""))
    conflict_set = _split_list_field(task.fields.get("conflict set", ""), split_commas=False)

    lines = [
        f"# Context Packet - {feature.slug} / {task_anchor}",
        "",
        f"Mode: {mode}",
        "Mode constraints:",
        *mode_constraint_lines(mode),
        f"Factory lane: {_field(task, 'factory lane')}",
        "",
        "Current objective:",
        f"- Execute `{task.title}` for `{feature.slug}` without expanding scope beyond the active SDD record.",
        "",
        "Owned scope:",
        *_bullet_lines(touch_set),
        "",
        "Do not touch:",
        *_bullet_lines(conflict_set),
        "",
        "Truth boundary:",
        "- Facts: canonical source files and SDD artifacts listed in this packet.",
        "- Read models: only the read-model paths explicitly named by the selected task.",
        "- Control plane: active SDD records, generated SDD work index, and command exit status.",
        "- Cache/fan-out: generated docs are rebuildable and must be refreshed by their generator.",
        "- Provider raw inputs: omitted unless the selected task explicitly names a provider diagnostic.",
        "- Product LLM agents are not development-agent lanes.",
        "",
        "Deterministic constraints:",
        f"- {_field(task, 'deterministic constraints')}",
        "",
        "On-demand context:",
        f"- {_field(task, 'on-demand context')}",
        "",
        "Kill/defer criteria:",
        f"- {_field(task, 'kill/defer criteria')}",
        "",
        "Eval/repair signal:",
        f"- {_field(task, 'eval/repair signal')}",
        "",
        "Relevant active planning artefacts:",
        f"- `{feature.relative_path}/tasks.md` - selected task and lane metadata.",
        f"- `{feature.relative_path}/plan.md` - file-level edits and verification commands.",
        f"- `{feature.relative_path}/spec.md` - approved goals and acceptance criteria.",
        "",
        "Verification evidence:",
        f"- {_field(task, 'verification')}",
        "",
        "Unknowns:",
        "- Re-check canonical docs and source before editing; SDD artifacts are execution records, not runtime truth.",
        "",
        "Redactions:",
        "- Credentials and private runtime values are omitted.",
    ]
    return "\n".join(lines)

def _find_feature(features: list[SddFeature], slug: str) -> SddFeature | None:
    for feature in features:
        if feature.slug == slug:
            return feature
    return None


def _task_anchor(title: str) -> str:
    match = re.match(r"Task\s+\d+", title, re.IGNORECASE)
    return match.group(0) if match else title


def _field(task: TaskRecord, name: str) -> str:
    value = task.fields.get(name, "").strip()
    return value.replace("`", "") or "unspecified"


def _split_list_field(value: str, *, split_commas: bool = True) -> list[str]:
    stripped = value.replace("`", "").strip()
    if not stripped:
        return ["unspecified"]
    separator = r"[,;]" if split_commas else r";"
    return [item.strip() for item in re.split(separator, stripped) if item.strip()]


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- `{value}`" if _looks_like_path(value) else f"- {value}" for value in values]


def _looks_like_path(value: str) -> bool:
    return "/" in value or value.startswith(".") or bool(re.search(r"\.[A-Za-z0-9]+$", value))


def _print_issues(issues: list[SddIssue]) -> None:
    for issue in issues:
        print(f"error: {issue.code}: {issue.path}: {issue.message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
