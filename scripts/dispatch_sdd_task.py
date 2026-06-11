from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_mode_constraints import VALID_MODES, mode_constraint_lines  # noqa: E402
from scripts.build_agent_context_packet import (  # noqa: E402
    render_context_packet,
    task_dispatch_issues,
)
from scripts.validate_sdd_artifacts import (  # noqa: E402
    SddFeature,
    SddIssue,
    TaskRecord,
    find_task_by_number,
    scan_sdd_features,
    validate_sdd_root,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a dry-run subagent handoff from an active SDD task")
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

    feature = _find_feature(scan_sdd_features(root), args.feature)
    if feature is None:
        print(f"error: SDD feature not found: {args.feature}", file=sys.stderr)
        return 1
    if feature.state != "active":
        print(f"error: dispatch only accepts active SDD features: {args.feature}", file=sys.stderr)
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

    print(render_handoff(feature, task, args.mode))
    return 0


def render_handoff(feature: SddFeature, task: TaskRecord, mode: str) -> str:
    task_anchor = _task_anchor(task.title)
    task_selector = _task_selector(task.title)
    context_packet = render_context_packet(feature, task, mode)
    lines = [
        f"# Subagent Handoff - {feature.slug} / {task_anchor}",
        "",
        f"Mode: {mode}",
        "Mode constraints:",
        *mode_constraint_lines(mode),
        "",
        "Goal:",
        f"- {_field(task, 'implementation')}",
        "",
        "Owned scope:",
        *_bullet_lines(_split_list_field(task.fields.get("touch set", ""))),
        "",
        "Do not touch:",
        *_bullet_lines(_split_list_field(task.fields.get("conflict set", ""), split_commas=False)),
        "",
        "Must read:",
        "- `AGENTS.md`",
        "- `docs/agent-playbook/task-reading-matrix.md`",
        f"- {_field(task, 'on-demand context')}",
        "",
        "Context packet:",
        "",
        "```md",
        context_packet,
        "```",
        "",
        "Report contract:",
        "- Use headings: `## Findings`, `## Scope Adherence`, `## Changed Files`, "
        "`## Required Reading Evidence`, `## Verification Evidence`, and `## Remaining Risks`.",
        "- Include `Owned scope: pass`, `Conflict set: pass`, and command output with `exit code:`.",
        "- In `## Required Reading Evidence`, include `Task classification:`, `AGENTS.md`, "
        "`docs/agent-playbook/task-reading-matrix.md`, and all task on-demand context paths.",
        "- Required reading evidence must mention:",
        "- `AGENTS.md`",
        "- `docs/agent-playbook/task-reading-matrix.md`",
        *_bullet_lines(_split_list_field(task.fields.get("on-demand context", ""))),
        (
            "- Parent validates the report with "
            f"`uv run python scripts/validate_subagent_report.py --feature {feature.slug} "
            f"--task {task_selector} --mode {mode} --report <report.md>`."
        ),
        "",
        "Expected output:",
        "- Findings first, with file paths and evidence.",
        "- Task classification and required-reading evidence for task-bound reports.",
        "- Changed files only when mode is write-allowed.",
        "- Remaining risks and open questions.",
        "- Verification evidence, including command and exit status.",
        "",
        "Verification evidence:",
        f"- {_field(task, 'verification')}",
        "",
        "Constraints:",
        "- Work with existing user changes; never revert unrelated edits.",
        "- Never print credentials or private runtime values.",
        "- Treat subagent output as evidence, not authority.",
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


def _task_selector(title: str) -> str:
    match = re.match(r"Task\s+(\d+)", title, re.IGNORECASE)
    return match.group(1) if match else title


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
