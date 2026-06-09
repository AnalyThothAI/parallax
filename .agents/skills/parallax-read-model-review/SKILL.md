---
name: parallax-read-model-review
description: Review or implement Parallax derived read model changes for stable keys, single writer ownership, idempotency, wake/catch-up behavior, and no compatibility shims. Use for "Read Model Change Review" tasks.
---

# Parallax Read Model Review

Use this skill for any change that touches a derived read model, projection writer, current-row identity, wake/catch-up behavior, or public read path over projected state.

## Required Reading

1. `AGENTS.md`
2. `docs/agent-playbook/task-reading-matrix.md`
3. `docs/agent-playbook/read-model-change-checklist.md`
4. `docs/ARCHITECTURE.md`
5. `docs/RELIABILITY.md`
6. `docs/WORKER_FLOW.md`
7. `docs/WORKERS.md`
8. The owning domain `src/parallax/domains/<domain>/ARCHITECTURE.md`

## Workflow

1. Classify the task as `Read Model Change Review`.
2. Name the fact source, read model, single runtime writer, public consumers, and wake channel.
3. Confirm stable product/window keys for current rows.
4. Reject run/generation/attempt/timestamp/UUID current-row identity.
5. Prove unchanged projections write zero serving rows.
6. Confirm `NOTIFY` is a wake hint and bounded `interval_seconds` catch-up re-reads PostgreSQL.
7. Confirm Provider raw frames are inputs, not facts.
8. Remove compatibility shims for retired tables, fields, identity schemes, or routes.
9. Add or update architecture, unit, or integration tests that prove the boundary.

## Verification Commands

- `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py`
- Domain-specific architecture test for the read model.
- Targeted unit or integration test for idempotent writes and stable row counts.

## Output

- Findings first, with file paths.
- Writer/consumer map.
- Identity and idempotency evidence.
- Verification command and exit status.
- Any remaining production-data verification gap.
