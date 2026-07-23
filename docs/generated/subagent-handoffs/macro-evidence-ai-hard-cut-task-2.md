# Subagent Handoff - 2026-07-23-macro-evidence-ai-hard-cut / Task 2

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.

Goal:
- Delete real/pseudo AI producers, workers, policies, consumers, and factor wiring within owned backend scope; retain raw facts, watched-account behavior, and dormant provider-neutral primitives.

Owned scope:
- `src/parallax/domains/news_intel/**`
- `src/parallax/domains/token_intel/**`
- `src/parallax/domains/notifications/**`
- `src/parallax/app/runtime/**`
- `src/parallax/app/operations/news.py`
- `src/parallax/platform/agent_*.py`
- `src/parallax/integrations/model_execution/**`
- `tests/unit/domains/news_intel/**`
- `tests/unit/domains/token_intel/**`
- `tests/unit/domains/notifications/**`
- `tests/unit/integrations/model_execution/**`

Do not touch:
- `src/parallax/app/surfaces/api/**`
- `src/parallax/platform/db/alembic/versions/**`
- `src/parallax/domains/macro_intel/**`
- `web/**`
- `docs/generated/**`

Must read:
- `AGENTS.md`
- `docs/agent-playbook/task-reading-matrix.md`
- `docs/AGENT_EXECUTION.md`
- `docs/WORKERS.md`
- `docs/WORKER_FLOW.md`
- News, Token, and Notifications domain architecture maps
- current worker manifest and bootstrap

Context packet:

```md
# Context Packet - 2026-07-23-macro-evidence-ai-hard-cut / Task 2

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.
Factory lane: Domain implementation

Current objective:
- Execute Task 2 for the approved hard cut without expanding the active SDD scope.

Truth boundary:
- Facts: News items/sources/entities/dedupe/market facts, Token events/rank/market facts, and notification source facts are retained.
- Read models: News page and Token current projections survive only with fact-derived fields.
- Control plane: News story-brief work/ledgers are retired; watched-account notification delivery remains.
- Cache/fan-out: semantic-catalyst and agent-derived caches are retired.
- Provider raw inputs: provider frames remain inputs, not facts.

Known symptoms:
- Production still declares the News story-brief worker and current tables; deterministic Token/Search AI-labelled consumers remain.

Canonical docs/code already checked:
- `AGENTS.md` - Kappa/CQRS and no-compat rules.
- `docs/AGENT_EXECUTION.md` - current News model lane.
- `docs/WORKERS.md` and `docs/WORKER_FLOW.md` - worker ownership and recovery.
- News/Token/Notifications architecture maps - domain truth and read-model ownership.

Relevant active planning artefacts:
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/plan.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/tasks.md`

Unknowns:
- Exact supported consumers of each candidate deletion must be rechecked before edits.

Redactions:
- Credentials and private runtime values are omitted.

Suggested verification:
- `uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q`
```

Report contract:
- Use headings: `## Findings`, `## Scope Adherence`, `## Changed Files`, `## Required Reading Evidence`, `## Verification Evidence`, and `## Remaining Risks`.
- Include `Owned scope: pass`, `Conflict set: pass`, and command output with `exit code:`.
- In `## Required Reading Evidence`, include `Task classification:`, `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, and all Task 2 on-demand context.
- Parent validates the report with `uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 2 --mode write-allowed --report <report.md>`.

Expected output:
- Findings first with source evidence.
- Changed files inside Owned scope only.
- Exact residual risks and verification output.

Verification evidence:
- `uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q`

Constraints:
- Work with existing changes; never revert unrelated edits.
- Never print credentials or private runtime values.
- Treat subagent output as evidence, not authority.
