from __future__ import annotations

import re
from collections.abc import Mapping

VALID_MODES = ("read-only", "write-allowed", "review-only")
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


def validate_subagent_report(text: str, *, mode: str, task_fields: Mapping[str, str] | None = None) -> list[str]:
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
    if task_fields is not None and changed_paths:
        issues.extend(_task_scope_issues(task_fields, changed_paths))

    verification = sections.get("verification evidence", "")
    command_blocks = _command_blocks(verification)
    if not command_blocks:
        issues.append("verification evidence requires a command block with exit code")
    elif not any(block[1] == 0 for block in command_blocks):
        issues.append("verification command exit code must be 0")
    if task_fields is not None and command_blocks:
        issues.extend(_task_verification_issues(task_fields, command_blocks))

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


def _task_scope_issues(task_fields: Mapping[str, str], changed_paths: tuple[str, ...]) -> list[str]:
    issues: list[str] = []
    touch_paths = _task_paths(task_fields, "touch set")
    outside_touch = [path for path in changed_paths if not any(_path_within(path, scope) for scope in touch_paths)]
    if outside_touch:
        issues.append("changed files must stay within task touch set")

    conflict_paths = _task_paths(task_fields, "conflict set")
    conflict_overlaps = [
        path for path in changed_paths if any(_paths_overlap(path, conflict_path) for conflict_path in conflict_paths)
    ]
    if conflict_overlaps:
        issues.append("changed files must not overlap task conflict set")
    return issues


def _task_verification_issues(task_fields: Mapping[str, str], command_blocks: list[tuple[str, int]]) -> list[str]:
    expected_command = _clean_command(task_fields.get("verification", ""))
    matching_blocks = [block for block in command_blocks if block[0] == expected_command]
    if not matching_blocks:
        return ["verification command must match task verification"]
    if not any(exit_code == 0 for _, exit_code in matching_blocks):
        return ["verification command exit code must be 0"]
    return []


def _task_paths(task_fields: Mapping[str, str], field_name: str) -> tuple[str, ...]:
    raw = task_fields.get(field_name, "")
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
