# AGENTS.md

> This file mirrors the project rules in `CLAUDE.md` so any coding agent
> (Codex, Cursor, generic LLM tooling) discovers them without reading
> Claude-specific instructions. **When you change one, update the other.**
> Claude-specific operating protocol (Skills, Superpowers, plan mode,
> permission rules) lives only in `CLAUDE.md`.

## Setup

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Bring up the service:

```bash
uv run gmgn-twitter-intel init      # create ~/.gmgn-twitter-intel/config.yaml
uv run gmgn-twitter-intel serve     # run collector + API in one ASGI worker
uv run gmgn-twitter-intel db migrate
```

The full CLI surface (subcommand groups: query, harness, ops, db) is documented by `gmgn-twitter-intel --help`. Treat that output as the source of truth — do not enumerate every command here.

## Architecture

A single Python service organised as a five-stage pipeline writing to one PostgreSQL store.

```
GMGN public WS  →  collector/  →  pipeline/  →  storage/  ←  retrieval/  →  api/  →  WS / HTTP / CLI consumers
```

| Layer | Directory | Responsibility |
|------|-----------|---------------|
| Collector | `src/gmgn_twitter_intel/collector/` | GMGN anonymous-WebSocket adapter, frame parsing, `cp=0/cp=1` snapshot gate, handle filter, store-first publish, subscription bookkeeping. |
| Pipeline  | `src/gmgn_twitter_intel/pipeline/`  | Deterministic entity extraction, token-intent resolution, async LLM enrichment for watched accounts, closed-loop harness materialisation (snapshot → settlement → credit → scoring), token-radar feature build & projection, notification rules / delivery, pulse candidate evaluation & thesis agent, asset-market & message-market sync workers. |
| Storage   | `src/gmgn_twitter_intel/storage/`   | Single PostgreSQL store. One repository per aggregate (evidence, entity, signal, asset, harness, notification, pulse, projection, registry, token-radar, token-target, intent-resolution, account-quality, market, price-observation, enrichment, discovery). Alembic migrations + `repository_session` helper. |
| Retrieval | `src/gmgn_twitter_intel/retrieval/` | Read services for HTTP / WebSocket / CLI: search, asset-flow, asset-search, account-alert, account-quality, harness, signal-pulse, token-target (posts, social timeline, stage builder, message price payload), plus the scoring components (heat, propagation, opportunity, catalyst, baseline, tradeability, timing, post-text quality, discussion quality, diffusion health, timeline features). |
| API       | `src/gmgn_twitter_intel/api/`       | FastAPI HTTP routes (`/healthz`, `/readyz`, `/api/...`) and the authenticated public WebSocket hub at `/ws`. |
| CLI       | `src/gmgn_twitter_intel/cli.py`     | Argparse front-end exposing the same data as the API plus operator subcommands (`db`, `ops`). |

Cross-cutting:

- `src/gmgn_twitter_intel/market/` — OKX CEX/DEX clients and the GMGN OpenAPI client used by the asset and price-observation pipelines.
- `src/gmgn_twitter_intel/settings.py` — single config loader (`~/.gmgn-twitter-intel/config.yaml`).
- `src/gmgn_twitter_intel/runtime_paths.py`, `models.py`, `logging_setup.py` — shared runtime utilities.
- `tests/` mirrors the package layout. Schema and Docker assets are pinned by `tests/test_postgres_schema*.py` and `tests/test_compose_*.py`.
- `docs/superpowers/specs/` — `why & what` artefacts (one per active feature).
- `docs/superpowers/plans/` — `how & when` artefacts.
- `docs/superpowers/_templates/` — spec / plan / tasks / verification templates.

To find code, prefer `ls src/gmgn_twitter_intel/<layer>/` over a memorised file list. This file pins the layer boundaries and stable contracts; per-file responsibilities live in the code and its tests.

## Public Contracts

These surfaces change only with a versioned spec — refactors must preserve them.

- **Config** (`~/.gmgn-twitter-intel/config.yaml`, the only config source):
  - `handles` — watched Twitter handles.
  - `ws_token` — public WebSocket API token.
  - `api` — FastAPI bind address and replay settings.
  - `storage.postgres` — DSN, password file, pool, timeout.
  - `llm.openai_api_key` / `llm.openai_model` — optional, only for watched-account social-event extraction.
  - Optional market-related groups (OKX, GMGN OpenAPI) for the asset / price pipelines.
- **WebSocket** at `/ws`: auth `{"type":"auth","token":"..."}`, subscribe `{"type":"subscribe","handles":[...],"replay":N}`. Push payloads include `event`, `entities`, `alerts`, `enrichment`, and harness updates after store commit.
- **HTTP**: `/healthz`, `/readyz`, `/api/*`. Each endpoint owns its own response schema; `score_version` is bumped on any scoring change.
- **CLI**: `gmgn-twitter-intel <verb>` plus the `db` and `ops` subcommand groups.

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.

## Code Style

- Python 3, ruff-formatted. `uv run ruff check .` must pass before completion.
- Prefer small, composable functions and existing service / repository helpers.
- Do not introduce new production dependencies without explicit user approval.
- Follow existing naming and folder conventions (`*_service.py`, `*_repository.py`, `pipeline/`, `retrieval/`, `storage/`).
- Keep public HTTP / WebSocket payload contracts backward-compatible unless the spec explicitly says otherwise.
- Default to writing no comments. Only add a comment when a hidden constraint, invariant, or workaround is non-obvious from the code itself.

## Testing Rules

- Every behaviour change must include a test in `tests/`.
- Bug fixes must include a regression test that fails before the fix and passes after it.
- Integration tests should hit a real PostgreSQL instance (Docker Compose), not mocks, when the change touches storage or query paths.
- Before claiming work is complete, run:
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run python -m compileall src tests`

## Security and Privacy

- Never print or log secrets, tokens, cookies, or `.env` values.
- Never commit `.env`, credentials, private keys, or generated config files.
- The only application config source is `~/.gmgn-twitter-intel/config.yaml`. Do not invent alternative config paths.
- Ask before changing authentication, authorisation, billing, or data-deletion behaviour.

## Spec-Driven Workflow

Trivial single-file low-risk edits may go direct. Everything else uses the lane sequence below.

| Lane | Path | When |
|------|------|------|
| Spec | `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` (or `…/<slug>/spec.md` for very large work) | Before any non-trivial implementation; answers *why & what* |
| Plan | `docs/superpowers/plans/YYYY-MM-DD-<slug>.md` (or `…/<slug>/plan.md`) | After spec approval; answers *how & when* with file:line edits |
| Tasks | `…/<slug>/tasks.md` | When a plan needs ordered TDD checklists across multiple PRs |
| Verification | `…/<slug>/verification.md` | Before declaring completion or opening a PR |

Templates live at `docs/superpowers/_templates/`. Copy a template into the appropriate lane and rename to the dated slug. Naming: `YYYY-MM-DD-<kebab-slug>` matching today's date; keep slugs short and intent-focused (`gmgn-account-directory-sync`, not `improve-things`).

The existing `docs/superpowers/specs/2026-*.md` and `docs/superpowers/plans/2026-*.md` files predate the templates and stay in their current single-file form. New work uses the templates.

### Spec vs Plan boundary

A spec contains: background, current architecture audit, problem diagnosis, first principles, goals with falsifiable metrics, target architecture, conceptual data flow, core models, interface contracts at semantic level, out-of-scope, risks, evolution path.

A spec must NOT contain: file paths and line numbers as instruction, function signatures, SQL DDL/DML rewrites, Alembic migration code, pseudo-code beyond a 5-line formula, test names, PR sequence, or "v1 vs v2" iteration history.

A plan contains: file:line edits, function signatures, exact SQL, migration code, test names, PR breakdown, rollout order, rollback procedure, acceptance test commands.

If the user asks for a spec, do not write a plan inside it. If the user asks for a plan, do not re-litigate the spec.

### Audit before design

Before writing any new service or scoring scheme:

1. List all files in the relevant `src/gmgn_twitter_intel/<area>/` and `tests/` directories.
2. Read existing `*_service.py` candidates end to end. Most "new" features here are 80 % covered by an existing service plus a few missing joins.
3. Trace the data flow from `collector → ingest → enrichment → retrieval → api/http.py → web/`. Cite the actual files and line ranges as evidence in the spec, not as instructions.
4. Identify fields already in the DB but unconsumed by retrieval services (e.g. `events.reference_json`, `social_event_extractions.event_type`, `account_token_alerts.is_first_seen_global`). These are usually the cheapest wins.

If a spec's background section cannot cite specific existing files, the design is ungrounded — fix that before proposing changes.

### Reuse before create

Default to extending an existing service, deriving on demand, and extending existing tables. Only create a new service / persisted entity / table when the conceptual responsibility, lifecycle, or compute budget genuinely differs from what is already there. Document the trigger in the spec's "Alternatives Considered" section.

### Avoid premature complexity

The following additions require explicit justification (cite a current pain or a measured number) before appearing in any spec:

- New PostgreSQL tables, materialised views, or background workers.
- LLM calls outside the existing `enrichment_worker` boundary.
- Bayesian / probabilistic outputs.
- Ground-truth datasets, human annotation workflows, dual-annotator review.
- Statistical inference on small samples (N < 200).
- Reinforcement learning, gradient-based weight tuning, online bandits.
- Cross-validation harnesses or holdout sets.
- New score versions without a corresponding `score_version` bump and downstream evaluation filter.

Prefer hand-tuned weighted combinations of deterministic features unit-tested with fixtures until a concrete measurement shows the limitation.

### Writing for delivery

Each spec and plan is a final artefact, not a diary. No "v1 / v2 / v3" prose, no in-document review checklists, no "what we used to think" sections. Quantitative claims either come with measurement evidence or are explicitly tagged as estimates.

### Scoring and ranking design

- Distinguish upstream identity from downstream observation; ranking signals operate on observable downstream effects within an explicit time window.
- Cite literature when proposing aggregation formulas (Kleinberg 2002 burst, Goel et al. 2016 structural virality, Cheng et al. 2014 cascades, Bakshy et al. 2011 influencer refutation, Centola 2010 complex contagion, Crane & Sornette 2008 endogenous vs exogenous).
- Every ranking score returned by the API must include its component breakdown. No black-box scores.
- Every new ranking signal needs a unit test asserting a single-author copy-pasta cluster scores significantly lower than a small set of independent organic responses.
- Bump `score_version` on every formula change so downstream evaluation services do not silently mix populations.

### Pushback handling

If a user says a design is over-engineered, half-baked, ungrounded, or doesn't follow KISS: engage the critique substantively, identify which specific claim is correct, do not capitulate by deleting everything, do not over-correct in the opposite direction, and re-read the existing code if the critique implies prior design ignored it.

## Worktree Policy

Coding agents MUST work in an isolated git worktree, not the main checkout.

- Default location: `.worktrees/<branch-slug>/` at the repo root. The directory is already gitignored.
- Create with: `git worktree add .worktrees/<slug> -b <branch> main` (branch from `main` unless the user names a different base).
- Before any edit verify: `git worktree list`, `git status --short`, `git branch --show-current`.
- Never modify source files from the main checkout.
- Existing worktrees in `.worktrees/` belong to other tasks; do not edit them unless explicitly asked.

## Verification

Run before claiming work is complete or opening a PR:

- `uv run ruff check .`
- `uv run pytest`
- `uv run python -m compileall src tests`
- Review the diff against the approved spec and plan.
- Write a verification artefact at `…/<slug>/verification.md` (or append a "Verification" section to a single-file plan) covering: commands run with results, diff summary, risks, follow-ups.
- Do not say "done", "fixed", or "passing" without the corresponding command output as evidence. Type-checking and tests verify code correctness, not feature correctness — UI / live-WebSocket flows must be exercised manually.

## Operational Invariants

- One ASGI worker. Multiple workers duplicate the upstream collector. If collector and API must scale separately, split them into distinct processes.
- `~/.gmgn-twitter-intel/config.yaml` is the only application config source. There is no macOS LaunchAgent, systemd unit, or `service` subcommand — run via foreground CLI or Docker Compose.
- Docker Compose bind-mounts the host config directory into the container and pins PostgreSQL data to the `gmgn-twitter-intel-postgres` named volume. Local foreground and Docker share the same config; query Docker data via `/api/*`, `/ws`, or `docker compose exec app gmgn-twitter-intel ...`.
- `coverage=public_stream` flags events as filtered from GMGN's anonymous public stream — not a full Twitter firehose guarantee. Do not advertise broader coverage in payloads or docs.
- MCP / FastMCP is optional control / query infrastructure only. `/ws` is the production live push channel; do not route real-time events through MCP.
