from __future__ import annotations

VALID_MODES = ("read-only", "write-allowed", "review-only")

MODE_CONSTRAINTS = {
    "read-only": (
        "- Read-only mode: do not edit files; report findings, required reading, and verification evidence only.",
    ),
    "write-allowed": ("- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.",),
    "review-only": ("- Review-only mode: do not edit files; review existing scope and report issues only.",),
}


def mode_constraint_lines(mode: str) -> tuple[str, ...]:
    return MODE_CONSTRAINTS[mode]
