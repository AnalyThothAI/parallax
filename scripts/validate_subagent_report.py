from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_agent_context_packet import VALID_MODES  # noqa: E402
from scripts.validate_sdd_artifacts import (  # noqa: E402
    SddFeature,
    SddIssue,
    TaskRecord,
    scan_sdd_features,
    validate_sdd_root,
)

REQUIRED_SECTIONS = (
    "findings",
    "scope adherence",
    "changed files",
    "verification evidence",
    "remaining risks",
)
SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
FENCED_BLOCK_RE = re.compile(r"```(?:[A-Za-z0-9_-]+)?\n(?P<body>[\s\S]*?)```", re.MULTILINE)
COMMAND_RE = re.compile(r"^\$\s+(?P<command>(?:uv|make|cd|npm|python|pytest)\b.*)$", re.MULTILINE)
EXIT_CODE_RE = re.compile(r"exit code:\s*(?P<code>-?\d+)\b", re.IGNORECASE)
SECRET_PATTERNS = (
    re.compile(r"\b(?:token|cookie|password|secret|api[_-]?key)\s*=", re.IGNORECASE),
    re.compile(r"\bpostgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_]*dsn\s*=", re.IGNORECASE),
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
    issues = validate_subagent_report(text, mode=args.mode, task=task)
    if issues:
        for issue in issues:
            print(f"error: {issue}", file=sys.stderr)
        return 1

    print("Subagent report validation passed.")
    return 0


def validate_subagent_report(text: str, *, mode: str, task: TaskRecord | None = None) -> list[str]:
    sections = _sections(text)
    issues: list[str] = []

    if f"mode: {mode}" not in text.lower():
        issues.append(f"report mode must match handoff mode: {mode}")

    missing_sections = [
        section_name for section_name in REQUIRED_SECTIONS if not _section_has_content(sections.get(section_name, ""))
    ]
    issues.extend(f"missing or empty section: ## {section_name.title()}" for section_name in missing_sections)

    scope = sections.get("scope adherence", "")
    if not re.search(r"\bowned scope\s*:\s*pass\b", scope, re.IGNORECASE):
        issues.append("scope adherence requires `Owned scope: pass`")
    if not re.search(r"\bconflict set\s*:\s*pass\b", scope, re.IGNORECASE):
        issues.append("scope adherence requires `Conflict set: pass`")

    changed_files = sections.get("changed files", "")
    changed_paths = _changed_file_paths(changed_files)
    if mode in {"read-only", "review-only"} and changed_paths:
        issues.append(f"{mode} reports must not list changed files")
    if mode == "write-allowed" and not (_says_no_changes(changed_files) or changed_paths):
        issues.append("write-allowed reports must list changed files or explicitly say none")
    if task is not None and changed_paths:
        issues.extend(_task_scope_issues(task, changed_paths))

    verification = sections.get("verification evidence", "")
    command_blocks = _command_blocks(verification)
    if not command_blocks:
        issues.append("verification evidence requires a command block with exit code")
    elif not any(block[1] == 0 for block in command_blocks):
        issues.append("verification command exit code must be 0")
    if task is not None and command_blocks:
        issues.extend(_task_verification_issues(task, command_blocks))

    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        issues.append("report must not include secrets, cookies, tokens, passwords, API keys, or DSNs")

    return issues


def _sections(text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = " ".join(match.group("title").strip().lower().split())
        sections[title] = text[start:end].strip()
    return sections


def _section_has_content(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped not in {"-", "...", "<pending>", "<none>"}


def _command_blocks(value: str) -> list[tuple[str, int]]:
    blocks: list[tuple[str, int]] = []
    for match in FENCED_BLOCK_RE.finditer(value):
        block = match.group("body")
        command_match = COMMAND_RE.search(block)
        exit_matches = list(EXIT_CODE_RE.finditer(block))
        if command_match and exit_matches:
            blocks.append((_clean_command(command_match.group("command")), int(exit_matches[-1].group("code"))))
    return blocks


def _changed_file_paths(value: str) -> tuple[str, ...]:
    return tuple(path for line in value.splitlines() if (path := _repo_path_or_none(_clean_bullet(line))))


def _says_no_changes(value: str) -> bool:
    lowered = value.replace("`", "").lower()
    return "none" in lowered or "no files changed" in lowered


def _clean_bullet(value: str) -> str:
    return value.strip().removeprefix("-").strip().strip("`")


def _repo_path_or_none(value: str) -> str | None:
    cleaned = value.replace("`", "").strip()
    return cleaned if _looks_like_repo_path(cleaned) else None


def _looks_like_repo_path(value: str) -> bool:
    if not value or value.lower() in {"none", "no files changed"}:
        return False
    if any(character.isspace() for character in value):
        return False
    return "/" in value or value.startswith(".") or bool(re.search(r"\.[A-Za-z0-9]+$", value))


def _task_scope_issues(task: TaskRecord, changed_paths: tuple[str, ...]) -> list[str]:
    issues: list[str] = []
    touch_paths = _task_paths(task, "touch set")
    outside_touch = [path for path in changed_paths if not any(_path_within(path, scope) for scope in touch_paths)]
    if outside_touch:
        issues.append("changed files must stay within task touch set")

    conflict_paths = _task_paths(task, "conflict set")
    conflict_overlaps = [
        path for path in changed_paths if any(_paths_overlap(path, conflict_path) for conflict_path in conflict_paths)
    ]
    if conflict_overlaps:
        issues.append("changed files must not overlap task conflict set")
    return issues


def _task_verification_issues(task: TaskRecord, command_blocks: list[tuple[str, int]]) -> list[str]:
    expected_command = _clean_command(task.fields.get("verification", ""))
    matching_blocks = [block for block in command_blocks if block[0] == expected_command]
    if not matching_blocks:
        return ["verification command must match task verification"]
    if not any(exit_code == 0 for _, exit_code in matching_blocks):
        return ["verification command exit code must be 0"]
    return []


def _task_paths(task: TaskRecord, field_name: str) -> tuple[str, ...]:
    raw = task.fields.get(field_name, "")
    values = []
    for candidate in re.split(r"[,;]", raw.replace("`", "")):
        cleaned = candidate.strip()
        if _looks_like_repo_path(cleaned):
            values.append(cleaned)
    return tuple(dict.fromkeys(values))


def _path_within(path: str, scope: str) -> bool:
    scope_prefix = scope.rstrip("/")
    return path == scope_prefix or path.startswith(f"{scope_prefix}/")


def _paths_overlap(path: str, scope: str) -> bool:
    return _path_within(path, scope) or _path_within(scope, path)


def _clean_command(value: str) -> str:
    cleaned = value.strip().strip("`")
    if cleaned.startswith("$"):
        cleaned = cleaned[1:].strip()
    return " ".join(cleaned.split())


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
