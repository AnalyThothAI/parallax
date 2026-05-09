# CLAUDE.md

Guidance for Claude Code working in this repository. Project-wide rules shared with other agents (Codex, Cursor, generic LLM tooling) live in `AGENTS.md` — when one file changes the other must be updated. This file adds the Claude-specific workflow (Skills, Superpowers, plan mode, worktree, completion gates) that other agents do not load.

## Reference

`AGENTS.md` is the source of truth for setup commands, layered architecture, public contracts, and operational invariants. Read it first; the sections below add only Claude-specific protocol on top.

The CLI surface evolves: when you need a command list, run `uv run gmgn-twitter-intel --help` rather than copy a stale list from memory. The full subcommand groups are `db`, `ops`, plus query verbs (search, asset-flow, account-*, social-events, attention-seeds, harness-*, enrichment-jobs, notification-deliveries).

## Worktree Workflow

Coding work MUST happen in an isolated git worktree, not the main checkout.

- Default location: `.worktrees/<branch-slug>/` at the repo root. Already gitignored.
- Create with `git worktree add .worktrees/<slug> -b <branch> main`. Branch from `main` unless the user names a different base.
- Before any edit, verify with `git worktree list`, `git status --short`, and `git branch --show-current`.
- Trivial single-file low-risk doc edits may go direct in the main checkout. Anything touching `src/` or `tests/` uses a worktree.
- Existing worktrees in `.worktrees/` belong to other tasks — do not edit them unless explicitly asked.

## Spec Workflow

Non-trivial implementation follows the spec → plan → tasks → verification lane sequence. Templates live at `docs/superpowers/_templates/`.

| Lane | Path | When |
|------|------|------|
| Spec | `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` (or `…/<slug>/spec.md`) | Before implementation; answers *why & what* |
| Plan | `docs/superpowers/plans/YYYY-MM-DD-<slug>.md` (or `…/<slug>/plan.md`) | After spec approval; answers *how & when* |
| Tasks | `…/<slug>/tasks.md` | When the plan spans multiple PRs or parallel sub-agents |
| Verification | `…/<slug>/verification.md` | Before declaring complete or opening a PR |

Order: spec before plan, plan before code, code before verification claim. Get explicit user approval at each lane boundary; do not write the next lane until the prior is approved. Existing `docs/superpowers/specs/2026-*.md` and `docs/superpowers/plans/2026-*.md` files predate the templates and stay in their current single-file form — new work uses the templates.

## Superpowers Integration

When the `superpowers:` skills are available, use them in this order:

1. `brainstorming` — clarify intent before writing any spec.
2. `writing-plans` — produce the spec / plan; iterate with the user.
3. `using-git-worktrees` — set up `.worktrees/<slug>/` once the plan is approved.
4. `test-driven-development` — write the failing test before each implementation slice.
5. `executing-plans` or `subagent-driven-development` — drive the plan to completion.
6. `verification-before-completion` — run the verification commands and capture output.
7. `requesting-code-review` — surface the diff and the verification artefact for review.
8. `finishing-a-development-branch` — decide on merge / PR / cleanup.

Process skills take priority over implementation skills when both could apply.

## Completion Criteria

Do not claim a task is complete, fixed, or passing until all of the following are true and have been written into the verification artefact:

- The implementation matches the approved spec; deviations are documented.
- `uv run ruff check .`, `uv run pytest`, `uv run python -m compileall src tests` all passed in the worktree.
- The diff was reviewed against the plan.
- UI / live-WebSocket / docker compose flows that cannot be exercised by tests were exercised manually, or the gap is explicitly stated.
- Remaining risks and follow-ups are listed.

If any of the above cannot be satisfied, surface the gap rather than claiming completion.

## Design Discipline

These rules apply when writing specs, plans, or designing new services in this repository. They encode lessons from prior iterations and should be followed unless the user explicitly overrides.

### Spec vs Plan boundary

Specs (`docs/superpowers/specs/`) answer **why and what** at a level a reviewer can debate without reading code. Plans (`docs/superpowers/plans/`) answer **how and when** at a level an engineer can execute without further design.

A spec contains: background, current architecture audit, problem diagnosis, first principles, goals with falsifiable metrics, target architecture, conceptual data flow, core models, interface contracts at semantic level, out-of-scope, risks, evolution path.

A spec must NOT contain: file paths and line numbers as instruction, function signatures, SQL DDL/DML rewrites, Alembic migration code, pseudo-code beyond a 5-line formula, test names, PR sequence, "v1 vs v2" iteration history.

A plan contains: file:line edits, function signatures, exact SQL, migration code, test names, PR breakdown, rollout order, rollback procedure, acceptance test commands.

If the user asks for a spec, do not write a plan inside it. If the user asks for a plan, do not re-litigate the spec.

### Audit before design

Before writing any new service or scoring scheme, audit the existing implementation:

1. List all files in the relevant `src/gmgn_twitter_intel/<area>/` and `tests/` directories.
2. Read the existing `*_service.py` candidates end-to-end. Most "new" features here turn out to be 80% covered by an existing service plus a few missing joins.
3. Trace the data flow from `collector → ingest → enrichment → retrieval → api/http.py → web/`. Cite the actual files and line ranges as evidence in the spec, not as instructions to follow.
4. Identify which fields are already in the DB but unconsumed by retrieval services (e.g. `events.reference_json`, `social_event_extractions.event_type`, `account_token_alerts.is_first_seen_global`). These are usually the cheapest wins.

If a spec's "现状" or "background" section cannot cite specific existing files, the design is ungrounded — fix that before proposing changes.

### Reuse before create

Default to extending an existing service. Only create a new service when:
- the new responsibility is conceptually orthogonal (different input domain or different output contract), AND
- adding it to an existing service would more than double that service's surface area.

Default to deriving on demand. Only persist a new entity when:
- the derivation cannot complete inside one HTTP request budget, OR
- multiple downstream consumers need the same derivation, OR
- the derivation is required by a background settlement/eval that runs without user requests.

Default to extending existing tables. Only add a new table when:
- the new entity has a different lifecycle than any existing table, AND
- it cannot be expressed as a view or materialized view over existing tables.

### Avoid premature complexity

These additions require explicit justification (cite a current pain or a measured number) before appearing in any spec:

- New PostgreSQL tables, materialized views, or background workers.
- LLM calls outside the existing `enrichment_worker` boundary.
- Bayesian / probabilistic outputs (posterior distributions, credible intervals).
- Ground-truth datasets, human annotation workflows, dual-annotator review.
- Statistical inference on small samples (Granger causality, change-point tests with N < 200, control-group matched-pair analysis).
- Reinforcement learning, gradient-based weight tuning, online bandits.
- Cross-validation harnesses or holdout sets.
- New score versions invented without a corresponding bump of `score_version` strings and downstream evaluation filters.

For ranking and scoring proposals, prefer hand-tuned weighted combinations of well-defined deterministic features that can be unit-tested with fixtures. Stay there until a concrete measurement shows the limitation.

### Writing for delivery

Treat each spec and plan as a final artifact, not a diary:

- Do not mention "v1 / v2 / v3" or prior drafts in the document body. Iteration is in git history, not prose.
- Do not include `[ ]` evaluation checklists asking the reader to validate the document. Invite review in the chat reply, not in the file.
- Do not include "what we used to think" or "what we corrected" sections. State the current design as the design.
- Quantitative claims (latency, sample sizes, score thresholds) should either come with measurement evidence or be explicitly tagged as estimates.

### Scoring and ranking design

When proposing any post / event / token ranking signal:

- **Distinguish upstream identity from downstream observation.** A post's followers / first-seen / watched / attribution_confidence are upstream identity attributes; they are weak proxies and in crypto are bot-dominated (especially first-seen). Ranking signals should be defined on observable downstream effects within an explicit time window.
- **Cite literature when proposing aggregation formulas.** Burst detection (Kleinberg 2002), structural virality (Goel et al. 2016 Management Science), cascade prediction (Cheng et al. 2014 WWW), influencer effect refutation (Bakshy et al. 2011 WSDM), complex contagion (Centola 2010 Science), endogenous vs exogenous decay (Crane & Sornette 2008 PNAS) are the relevant base. Indicate which paper supports each component.
- **Make components transparent in the API response.** Every ranking score must be returned alongside its component breakdown so users can audit why the rank is what it is. Black-box scores are forbidden.
- **Test against bot patterns explicitly.** Any new ranking signal must have a unit test asserting that a single-author copy-pasta cluster scores significantly lower than a small set of independent organic responses. This is the minimum bar for crypto-domain robustness.
- **Use `score_version` strings as contracts.** Every change to a scoring formula bumps the version. Downstream evaluation services must filter by version, otherwise A/B comparisons silently mix populations.

### When the user pushes back

If a user says a design is over-engineered, half-baked, ungrounded, or doesn't follow KISS:

- Engage the critique substantively. Identify which specific claim of theirs is correct before agreeing.
- Do not capitulate by deleting everything; find what is genuinely worth keeping and articulate why.
- Do not over-correct in the opposite direction (e.g. responding to "too complex" with "too thin"). Aim for the minimum design that meets the actual goal stated, not the minimum design period.
- Re-read the existing code if the critique implies the prior design ignored it.
