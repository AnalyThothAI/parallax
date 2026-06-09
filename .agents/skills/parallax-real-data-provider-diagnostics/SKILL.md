---
name: parallax-real-data-provider-diagnostics
description: Diagnose Parallax live provider data, missing Token Radar rows, asset profiles, news coverage, macro freshness, or icon gaps without exposing secrets. Use for "Real Data And Provider Debugging" tasks.
---

# Parallax Real Data Provider Diagnostics

Live-data runs use operator-owned files in `~/.parallax/`, not repository examples. Never print secrets, cookies, tokens, proxy URLs, DSNs, or API keys.

## Required Reading

1. `AGENTS.md`
2. `docs/agent-playbook/task-reading-matrix.md`
3. `docs/SECURITY.md`
4. `docs/WORKER_FLOW.md`
5. `docs/WORKERS.md`
6. The owning domain `src/parallax/domains/<domain>/ARCHITECTURE.md`

## Workflow

1. Classify the task as `Real Data And Provider Debugging`.
2. Run `uv run parallax config` and report only redacted paths, booleans, and diagnostic outcomes.
3. Confirm whether `config_path` and `workers_config_path` point at `~/.parallax/`.
4. Separate provider raw inputs, PostgreSQL facts, dirty/control-plane state, derived read models, cache/fan-out state, and UI/API symptoms.
5. Use `uv run parallax ops worker-status --help` before any live operation.
6. Use the smallest domain-specific `uv run parallax ops ... --help` command before executing a repair.
7. Do not treat repository fixtures, sample YAML, or `.env` files as active runtime config.

## Verification Commands

- `uv run parallax config`
- `uv run parallax ops worker-status --help`
- Domain-specific diagnostics from the owning CLI surface.

## Output

- Redacted config paths and booleans.
- Evidence grouped by truth boundary.
- Smallest safe repair command or a reason no live operation was run.
- Open questions that require operator access.
