# CLAUDE.md

Claude-specific router. Mirrors `AGENTS.md` for the routing table and adds the Claude-only Skills / Plan-mode / Worktree protocol below. When you change either router, update the other.

<!-- BEGIN SHARED AGENT ROUTER -->

## What this is

`Parallax Market Research System`: a single Python service and CLI named `parallax` that ingests social, news, macro, DEX/CEX market, and provider evidence, extracts crypto entities, scores and audits research signals, and serves results over HTTP / WebSocket / CLI to a React operator console. GMGN's anonymous public WebSocket is one source adapter, not the product boundary. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

The pipeline is Kappa/CQRS: PostgreSQL material facts (`events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, `enriched_events`) are the only business truth. Derived read models (`token_radar_rows`, `narrative_admissions`, ...) each have exactly one runtime writer and are rebuildable. Current read models must use stable product/window keys, never run/generation/attempt/timestamp/UUID identity; unchanged projections must write zero serving rows. `NOTIFY` is a wake hint; every listener re-reads DB and runs a bounded `interval_seconds` catch-up. Provider raw frames are inputs, not facts.

## Runtime config for real data

Live-data runs use the operator-owned files in `~/.parallax/`: `config.yaml` for application/provider/credential/storage settings and `workers.yaml` for worker runtime knobs. Do not assume repository fixtures, example YAML, or `.env` files are the active runtime config. Before debugging provider data, Token Radar rows, asset profiles, or missing icons against real data, run `uv run parallax config` and confirm the reported `config_path` / `workers_config_path` point at `~/.parallax/`. Never print or copy secret values; report only redacted booleans, paths, and diagnostic command results.

## Frontend guardrails

Frontend CSS is harness-constrained, not convention-only. Before changing `web/src` UI code, read `docs/FRONTEND.md`. Do not recreate retired CSS buckets such as `cockpit.css`, `macro.css`, `macroResponsive.css`, `shared.css`, or `signalLab.css`; owner CSS must live beside the component or route that imports it. Feature CSS must use the owning feature namespace and must not restyle shared UI internals, notification internals, or Obsidian `.ods-*` selectors. `npm run lint` runs ESLint plus the frontend architecture harness; do not bypass it after CSS, responsive, route shell, or shared UI changes.

## Where to read what

| Need | File |
|------|------|
| Install, run, docker | `docs/SETUP.md` |
| Layer boundaries & data flow | `docs/ARCHITECTURE.md` |
| Frontend architecture | `docs/FRONTEND.md` |
| Public surfaces (config, WS, HTTP, CLI) | `docs/CONTRACTS.md` |
| Spec→plan→tasks→verification flow | `docs/WORKFLOW.md` |
| Design rules (audit, reuse, scoring) | `docs/DESIGN_DISCIPLINE.md` |
| Testing & completion gates, including worker development gates | `docs/TESTING.md` |
| Secrets, config, authn changes | `docs/SECURITY.md` |
| Operational invariants | `docs/RELIABILITY.md` |
| PostgreSQL performance & queue diagnostics | `docs/references/POSTGRES_PERFORMANCE.md` |
| Worker flow, lifecycle, state-machine debugging, and review checklist | `docs/WORKER_FLOW.md` |
| Cross-domain worker inventory, runtime ownership, and worker best practices | `docs/WORKERS.md` |
| Agent task reading matrix and sub-agent handoffs | `docs/agent-playbook/task-reading-matrix.md` |
| Product LLM agent execution plane | `docs/AGENT_EXECUTION.md` |
| Module architecture maps | `src/parallax/domains/<domain>/ARCHITECTURE.md`; discover current maps with `find src/parallax/domains -name ARCHITECTURE.md` |
| SDD feature workflow | `docs/sdd/` contains current spec→plan→tasks→verification templates and feature records; old planning archives are not canonical truth |
| External references & papers | `docs/references/` |
| Auto-generated artefacts | `docs/generated/` |
| Tech debt log | `docs/TECH_DEBT.md` |

CLI surface: `uv run parallax --help` is the source of truth (snapshot at `docs/generated/cli-help.md`).

<!-- END SHARED AGENT ROUTER -->

## Claude-only protocol

When `superpowers:` skills are available, use this workflow chain: `brainstorming` → `writing-plans` → `using-git-worktrees` → `test-driven-development` → `executing-plans` / `subagent-driven-development` → `verification-before-completion` → `requesting-code-review` → `finishing-a-development-branch`. Process skills take priority.
