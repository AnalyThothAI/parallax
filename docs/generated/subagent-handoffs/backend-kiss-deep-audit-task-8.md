# Subagent Handoff - 2026-07-22-backend-kiss-deep-audit / Task 8

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.

Goal:
- Atomically remove unused provider and PostgreSQL-private surfaces while retaining current adapters and evidence boundaries.

Context packet:

```md
# Context Packet - 2026-07-22-backend-kiss-deep-audit / Task 8

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.
```

Report validation:
- `uv run python scripts/validate_subagent_report.py --feature 2026-07-22-backend-kiss-deep-audit --task 8 --mode write-allowed --report <report.md>`
