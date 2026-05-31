# Spec — Harness Engineering Restructure

**Status**: Draft
**Date**: 2026-05-09
**Owner**: aaurix (with claude-opus-4-7)
**Related**: walkinglabs `learn-harness-engineering` (`docs/zh/resources/openai-advanced/index.md`); existing `AGENTS.md`, `CLAUDE.md`, `docs/superpowers/_templates/`

## Background

The repository's coding-agent harness today consists of three layers that are mutually inconsistent:

- **Thick router**. `AGENTS.md` (`AGENTS.md:1-199`) bundles ten heterogeneous concerns: setup, architecture, public contracts, code style, testing rules, security, the spec/plan/tasks/verification lane workflow, the worktree policy, completion gates, and operational invariants. `CLAUDE.md` (`CLAUDE.md:1-149`) mirrors the spec/plan/workflow rules and adds Claude-specific Skills/Plan/Worktree protocol. The two files duplicate ~80 lines of design-discipline prose verbatim and a change to one is silently allowed to drift from the other.
- **Lane templates without lifecycle**. `docs/superpowers/_templates/` provides spec / plan / tasks / verification templates. `docs/superpowers/specs/` holds 16 `.md` files and `docs/superpowers/plans/` holds 13 `.md` files (counted via `ls`). All sit at the lane root with no separation between in-flight and completed work; an agent looking for "what is currently active" must read every file.
- **Pre-template legacy at `docs/` root**. 14 `2026-05-04..07` and `token-radar-social-heat-*` Markdown files at the top level of `docs/` predate the templates. They mix specs, plans, audits, code reviews, and product research in one flat namespace. `AGENTS.md:113` acknowledges these stay in single-file form but provides no further organisation.

There is no router for external reference materials (the walkinglabs document itself, the academic citations the design-discipline section names — Kleinberg 2002, Goel et al. 2016, Cheng et al. 2014, Bakshy et al. 2011, Centola 2010, Crane & Sornette 2008 — the GMGN protocol notes that live only in collector code comments, the OKX/GMGN OpenAPI surfaces). There is no place for derived artefacts that should track code (database schema, CLI surface, score-version registry, WebSocket protocol). There is no shared technical-debt log; follow-ups land at the bottom of individual `verification.md` files and are forgotten.

The five-layer source structure under `src/parallax/` (`collector/`, `pipeline/`, `storage/`, `retrieval/`, `api/`, plus cross-cutting `market/`, `settings.py`, `runtime_paths.py`, `models.py`, `logging_setup.py`) is already aligned with the "mechanical layer constraints" pattern the reference document advocates. Source code is **out of scope** for this spec.

## Problem

A coding agent (Claude, Codex, Cursor, generic LLM tooling) opening this repository cold cannot answer four basic questions in one hop:

1. *Where do I find the rule that governs X?* — must scan all of `AGENTS.md`, all of `CLAUDE.md`, and risk missing duplicated content.
2. *What work is currently in flight?* — must read 29 spec/plan files at the superpowers root plus 14 at `docs/` root.
3. *What does the code actually expose right now (DB schema, CLI verbs, WS message types, active score versions)?* — must read source or run commands; the answer is never written down.
4. *Where is the literature behind this scoring rule?* — citations exist as inline prose in `AGENTS.md:162` and `CLAUDE.md:135-141`; the papers themselves are not in the repo.

The cost compounds: every new spec re-derives context that should be one link away, every duplicated rule between `AGENTS.md` and `CLAUDE.md` is a future drift, and every undeclared follow-up grows technical debt invisibly.

## First principles

These invariants the redesign must respect; each is already evidenced in the current repo.

1. **The repository is the only source of truth.** No agent should rely on chat history or operator memory. Today already enforced for application config (`AGENTS.md:96-98`: only `~/.parallax/config.yaml`) and CLI surface (`AGENTS.md:26`: `parallax --help`).
2. **Mechanical structure outranks prose convention.** Today already enforced by the `*_service.py` / `*_repository.py` naming (`AGENTS.md:79`) and by the worktree gate (`CLAUDE.md:23-29`).
3. **Public contracts are immutable until versioned.** Today already enforced by `score_version` strings (`AGENTS.md:162-165`) and by the WebSocket / HTTP / CLI public-contract section (`AGENTS.md:57-72`).
4. **Plans, quality, and tech-debt are versioned alongside code.** Today already enforced by the spec → plan → verification lane (`AGENTS.md:101-114`).

## Goals

- **G1.** A coding agent can locate any project rule in **at most two file reads**: `AGENTS.md` (or `CLAUDE.md`) → exactly one linked governance file. Falsifiable: open `AGENTS.md`, pick any of the 10 current concern areas, count reads to reach the authoritative paragraph.
- **G2.** `AGENTS.md` and `CLAUDE.md` together contain **zero duplicated rule prose**. Falsifiable: `diff` the two files' substantive content; only Claude-specific Skills/Plan-mode protocol may differ.
- **G3.** Every spec and plan file is unambiguously classified as `active/` or `completed/`. Falsifiable: `ls docs/superpowers/{specs,plans}/{active,completed}/` accounts for all `.md` files; the lane-root level holds none.
- **G4.** The four derived artefacts (DB schema, CLI help, score versions, WS protocol) live as committed Markdown under `docs/generated/` and are reproducible by `make docs-generated`. Falsifiable: a CI step `make docs-generated && git diff --exit-code docs/generated/` passes on a clean checkout.
- **G5.** External reference materials (the walkinglabs document, six academic papers cited by name in current design-discipline prose, GMGN protocol notes, OKX API notes) are present under `docs/references/` so specs cite a relative path, not a URL. Falsifiable: for each citation that today appears as inline text, a corresponding file exists.
- **G6.** Technical-debt entries that today scatter across individual `verification.md` files have a single canonical home at `docs/TECH_DEBT.md`. Falsifiable: future verification artefacts link debt items into `TECH_DEBT.md` rather than burying them.

## Non-goals

- **N1.** No changes to `src/parallax/` directory layout, module boundaries, or naming. The five-layer pipeline plus cross-cutting modules is already aligned with the reference document's principles.
- **N2.** No rewriting of legacy spec/plan/audit/research **content**. Files move with `git mv`; their Markdown bodies are preserved verbatim. Templates apply only to new work.
- **N3.** No change to the `~/.parallax/config.yaml` schema, the WebSocket protocol on `/ws`, the HTTP routes on `/api/*`, or the CLI verbs. This is documentation restructuring only.
- **N4.** No new automation beyond the `make docs-generated` regeneration pipeline. No commit hooks, no auto-classification of legacy specs into active/completed, no link-checker enforcement (these may follow in a separate iteration if pain materialises).
- **N5.** No introduction of `research/`, `design-docs/`, or `product-specs/` lanes from the reference document beyond what is enumerated below. Audit / code-review / product-research legacy files are absorbed into `docs/superpowers/specs/completed/` because they are upstream artefacts no longer evolving on their own.

## Target architecture

The harness is reorganised into three concentric rings and one auxiliary ring, with a single rule for each: **routers** point, **governance files** rule, **lane files** record decisions and execution, **support files** ground or derive.

### Ring 1 — Routers (repo root)

Two files, both ≤ 60 lines after the change. Each is a "what is this project + table of where to read what" and nothing else, except `CLAUDE.md` additionally carries the Claude-specific protocol block (Skills, Plan-mode, Worktree behaviour) that does not apply to other agents.

- `AGENTS.md` — generic-agent router. Project tagline plus the routing table; carries no rule prose.
- `CLAUDE.md` — Claude-specific router. Same routing table plus the Claude-specific protocol block.

The duplication hazard (G2) is resolved structurally: there is nothing to duplicate because the routers carry no rules.

### Ring 2 — Governance files (`docs/`)

Nine rule-owning governance files plus `TECH_DEBT.md` as a project-wide log. Each rule-owning file is the unique authoritative source for its topic; routers point to them, no rule lives in two places. `TECH_DEBT.md` is appendable rather than authoritative.

| File | Owns |
|------|------|
| `docs/ARCHITECTURE.md` | Five-layer Python pipeline boundaries, cross-cutting modules, conceptual data flow from collector to API. Frontend specifics live in `FRONTEND.md`. |
| `docs/CONTRACTS.md` | Config schema (`~/.parallax/config.yaml`), WebSocket auth/subscribe/push, HTTP route surface, CLI subcommand groups, `score_version` discipline. |
| `docs/SETUP.md` | `uv sync`, `uv run pytest`, `uv run ruff check`, `parallax init/serve/db migrate`, Docker Compose bring-up, `web/` install / dev / build commands. |
| `docs/WORKFLOW.md` | Spec → plan → tasks → verification lane mechanics, worktree policy, completion gates, what each lane document must and must not contain at the structural level. |
| `docs/DESIGN_DISCIPLINE.md` | Spec vs plan boundary, audit-before-design, reuse-before-create, avoid-premature-complexity list, writing-for-delivery, scoring/ranking design rules with literature citations, push-back handling. |
| `docs/TESTING.md` | Backend testing rules, regression-test requirement for bug fixes, real-PostgreSQL integration policy, frontend testing rules for `web/src/test/`, the completion-verification commands for both stacks. |
| `docs/SECURITY.md` | Secret/`.env` handling, the single-config-source rule, authn/authz change-confirmation rule, WebSocket token handling on the frontend. |
| `docs/RELIABILITY.md` | Operational invariants: single ASGI worker, no LaunchAgent / systemd, Docker-Compose volume pinning, `coverage=public_stream` semantic. |
| `docs/FRONTEND.md` | `web/` architecture: layer responsibilities (`api/`, `components/`, `domain/`, `lib/`, `store/`, `test/`), component conventions, state-management discipline, payload-contract dependency on `CONTRACTS.md`, build / preview / deployment expectations, UI verification gate (manual flow exercise before declaring complete). |
| `docs/TECH_DEBT.md` | Tracked debt items with severity and impact (see Core models). |

### Ring 3 — Lane files (`docs/superpowers/`)

```
docs/superpowers/
├── _templates/        unchanged
├── specs/
│   ├── active/        in-flight or paused work
│   └── completed/     implementation merged + verification recorded
└── plans/
    ├── active/
    └── completed/
```

Lane root holds no `.md` files. New work copies a template into the appropriate `active/` subfolder; completion moves the file to `completed/` (a documented step in the lane workflow, not automation).

### Ring 4 — Support files (`docs/`)

Three single-purpose folders, each with a `README.md` stating its rule and rebuild command.

- `docs/references/` — external materials cited by governance or spec files. Replaces inline citation prose. Subfolder `papers/` for academic summaries; flat for protocol notes; one file per source. Not regenerated; updated by hand on citation change.
- `docs/generated/` — derived artefacts that mirror code. Header comment in each file states "do not hand-edit". Regenerated by `make docs-generated`. CI verifies clean diff.
- `docs/mockups/`, `docs/prototypes/` — unchanged from today. Out of scope for this restructure.

### Migration mapping (one-time)

Conceptual classification, not a file:line plan. Counts are evidence the migration is bounded.

| Source | Destination | Count | Rule |
|--------|-------------|-------|------|
| `docs/*-spec-cn.md` and `docs/token-radar-social-heat-spec.md` | `docs/superpowers/specs/completed/` | 6 | All six describe features now merged to `main`. |
| `docs/*-plan-cn.md` | `docs/superpowers/plans/completed/` | 4 | Same. |
| `docs/*-audit-cn.md`, `*-code-review-cn.md`, `token-radar-social-heat-research.md` | `docs/superpowers/specs/completed/` | 4 | Upstream research / audit / review artefacts; absorbed here rather than creating a `research/` lane. |
| `docs/superpowers/specs/2026-05-*.md` | `…/specs/active/` or `…/specs/completed/` per implementation status | 16 | Per-file judgement during plan execution. |
| `docs/superpowers/plans/2026-05-*.md` | `…/plans/active/` or `…/plans/completed/` per implementation status | 13 | Same. |

All moves use `git mv`; file bodies are not edited.

## Conceptual data flow

The "data" here is how a coding agent navigates the repository to act on a request.

```
agent receives task
  ↓
reads AGENTS.md (or CLAUDE.md)              [router; ≤ 40 lines]
  ↓ follows one link from routing table
reads ONE governance file in docs/          [authoritative for that concern]
  ↓ if executing
copies _templates/spec-template.md into superpowers/specs/active/
  ↓ on lane transitions
moves file across active/ ↔ completed/
  ↓ on derived-artefact change
runs `make docs-generated`                  [updates docs/generated/*.md]
  ↓ on follow-up identification
appends to docs/TECH_DEBT.md
```

The arrow that changes most: **every prior path that previously involved "scan AGENTS.md or CLAUDE.md until you find the right paragraph"** becomes **"read the routing table, jump once"**. No source-code arrows change.

## Core models

Semantic definitions only — names, fields, invariants. No formats yet.

- **Router file**. Fields: project tagline (one sentence), routing table (concern → governance-file path). Invariant: contains no rule prose; an unresolved rule lookup is a router bug, not a content gap.
- **Governance file**. Fields: title, scope statement, rules. Invariant: each topic owned by exactly one governance file; cross-references allowed but no rule is duplicated.
- **Lane file (spec / plan / tasks / verification)**. Fields per template. Invariant: lives under `active/` or `completed/`, never at lane root after migration; classification reflects actual implementation state.
- **Generated artefact**. Fields: header comment ("auto-generated by `<command>`; do not hand-edit"), payload, regeneration command. Invariant: byte-identical to the output of its regeneration command on a clean checkout; CI enforces.
- **Reference material**. Fields: source citation, payload, last-fetched date. Invariant: cited by relative path from at least one governance or spec file; orphaned references are pruned during cleanup.
- **Tech-debt entry**. Fields: short description, introduction date (commit or spec slug), area (`collector|pipeline|storage|retrieval|api|web|harness|infra`), severity (`low|medium|high`), impact (one sentence). Invariant: every open entry has an owner stated or `unowned`.

## Interface contracts

The harness exposes contracts to two consumer classes: **coding agents** and **CI/operators**.

### Agent-facing contract

- **Router lookup**. An agent reading `AGENTS.md` (or `CLAUDE.md`) finds the routing table within the first screen and reaches the authoritative file for any concern in one further read.
- **Governance file uniqueness**. For any given concern (setup, security, workflow, etc.), exactly one governance file owns it; agents may rely on this for citations.
- **Lane state visibility**. `ls docs/superpowers/specs/active/` and `ls docs/superpowers/plans/active/` enumerate all in-flight work. `completed/` is read-only by convention; finished work moves there.
- **Template usage**. `docs/superpowers/_templates/` continues to be the canonical starting point for new lane files. Templates are stable across this restructure.

### CI / operator contract

- **`make docs-generated`** regenerates `docs/generated/*.md` deterministically; rerunning produces no diff on a clean checkout.
- **`docs/generated/*.md`** never contains hand-written content; the header comment communicates this.
- **`docs/TECH_DEBT.md`** is appendable by any contributor; ordering is by severity then date.

No HTTP, WebSocket, or CLI surface changes.

## Acceptance criteria

- **AC1.** WHEN a coding agent reads `AGENTS.md` THEN the file SHALL be ≤ 60 lines and contain only a project tagline plus a routing table. WHEN it reads `CLAUDE.md` THEN the file SHALL be ≤ 60 lines and contain only a project tagline, a routing table, and the Claude-specific protocol block (Skills / Plan-mode / Worktree).
- **AC2.** WHEN a contributor edits a governance file in `docs/` THEN no other governance file SHALL state the same rule (verifiable by spot-grep on representative phrases such as "single ASGI worker", "score_version", "real PostgreSQL").
- **AC3.** WHEN `ls docs/superpowers/specs/` and `ls docs/superpowers/plans/` are run THEN the only entries SHALL be `_templates/`, `active/`, and `completed/`; no loose `.md` files at lane root.
- **AC4.** WHEN `ls docs/*.md` is run THEN the result SHALL be exactly the nine rule-owning governance files plus `TECH_DEBT.md` (ten `.md` files: `ARCHITECTURE`, `CONTRACTS`, `SETUP`, `WORKFLOW`, `DESIGN_DISCIPLINE`, `TESTING`, `SECURITY`, `RELIABILITY`, `FRONTEND`, `TECH_DEBT`); no `2026-*-cn.md` or `token-radar-social-heat-*.md` legacy files at `docs/` root.
- **AC5.** WHEN `make docs-generated` is run on a clean checkout THEN `git diff --exit-code docs/generated/` SHALL succeed.
- **AC6.** WHEN any spec or governance file references a previously-inline academic citation THEN it SHALL link to a corresponding file under `docs/references/papers/`.
- **AC7.** WHEN a verification artefact identifies follow-up work THEN it SHALL append the item to `docs/TECH_DEBT.md` rather than only listing it inline.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Misclassifying an active spec as `completed/` (or vice versa) during migration. | Medium | Per-file judgement in the plan; for any uncertain case default to `active/` (over-flagging is recoverable, under-flagging hides work). |
| `git mv` rename history lost in tooling that does not follow renames. | Low | All moves are pure renames with no body edits; standard `git log --follow` and `git blame --follow` traverse them. |
| Regeneration of `docs/generated/db-schema.md` requires a live PostgreSQL connection (introspection from Alembic head). | Medium | Document the DB requirement in `docs/generated/README.md` and in the Make target's help text; CI must provision Postgres before running the check (CI already does for tests). |
| Routers drift apart again over time as concerns leak back in. | Medium | `AC1` and `AC2` are checkable in code review; if drift recurs, escalate to a lint script in a follow-up. |
| Contributors continue to write rules into `AGENTS.md`/`CLAUDE.md` instead of governance files. | Medium | Each governance file's opening paragraph names the concern it owns and explicitly states "rules for this concern live here, not in routers". |
| Existing inbound links (in old PRs, in Slack, in agent memories) point to the old `docs/` root paths. | Low | Acceptable; git history preserves the moves. No redirect file is added. |

## Evolution path

The next plausible expansion is **automation that mechanises what this spec leaves as convention**: a pre-commit hook checking router line-count and rule-uniqueness, a CI check enforcing `make docs-generated` clean diff, a script that flags `docs/superpowers/specs/active/` files older than N days for triage. None of these are needed before the structural change; they become cheap once the structure exists.

The structure also leaves room to lift `docs/references/papers/` into `llms.txt`-formatted files for direct LLM consumption (the walkinglabs convention), and to publish `docs/generated/` to a static-site preview if that pain materialises. Both are deferred.

What this design must not foreclose: the option to introduce additional governance files (e.g. `docs/PRODUCT_SENSE.md` if product-decision criteria need owning, `docs/OBSERVABILITY.md` if logging / metrics rules grow). The "one file per concern" rule scales by addition, not by re-bundling.

## Alternatives considered

- **Status frontmatter on flat lane files** (rejected). Adding `status: active|completed|superseded` to each spec/plan file and keeping them at lane root has the lowest migration cost but forces every "what's in flight" lookup through a grep or a generated index, and an index file would itself become a stale source of truth.
- **Three-block decomposition of `AGENTS.md`** (rejected). Splitting only into `ARCHITECTURE.md` + `WORKFLOW.md` + `OPERATIONS.md` reduces drift modestly but bundles concerns that change on different cadences (security policy, testing rules, design discipline). Each bundled file recreates the original problem at smaller scale.
- **Dedicated `research/` lane** (rejected on user input 2026-05-09). Would isolate audit / code-review / product-research artefacts from the spec/plan flow but adds a third lane shape. Absorbing them into `superpowers/specs/completed/` keeps the count of lane shapes at two; legacy artefacts no longer evolve so the conceptual mismatch is bounded.
- **Touching `src/` layout** (rejected). The `collector / pipeline / storage / retrieval / api` boundary already implements the reference document's "mechanical layer constraint" principle. No measurement points to a code-organisation pain.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Move legacy files with `git mv` (preserves history); keep `_templates/` content unchanged; keep `src/`, `tests/`, `web/`, `compose.yaml`, `alembic.ini`, `pyproject.toml`, `Dockerfile` untouched; add `make docs-generated` as an additive Makefile target. |
| Ask first | Per-file `active/` vs `completed/` classification when implementation status is ambiguous; whether any specific legacy file should be split or merged rather than relocated whole; whether to add a CI check enforcing `make docs-generated` clean diff in the same change or a follow-up. |
| Never | Edit the **content** of legacy spec/plan/audit/research/review files during migration; introduce auto-classification heuristics; change public WS/HTTP/CLI surfaces; add new production dependencies; collapse two governance files back into one to "keep things simple"; create a redirect file for old paths. |
