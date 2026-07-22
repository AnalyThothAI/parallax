# Subagent Handoff - 2026-07-22-backend-kiss-deep-audit / Task 4

Mode: read-only
Mode constraints:
- Read-only mode: do not edit files; report findings, required reading, and verification evidence only.

Goal:
- Audit provider adapters and the PostgreSQL execution plane while preserving migration and provenance boundaries.

Context packet:

```md
# Context Packet - 2026-07-22-backend-kiss-deep-audit / Task 4

Mode: read-only
Mode constraints:
- Read-only mode: do not edit files; report findings, required reading, and verification evidence only.
```

Report validation:
- `uv run python scripts/validate_subagent_report.py --feature 2026-07-22-backend-kiss-deep-audit --task 4 --mode read-only --report <report.md>`
