# CLAUDE.md

Claude-specific router. Mirrors `AGENTS.md` for the routing table and adds the Claude-only Skills / Plan-mode / Worktree protocol below. When you change either router, update the other.

## What this is

`gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

The pipeline is Kappa/CQRS: PostgreSQL material facts (`events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, `enriched_events`) are the only business truth. Derived read models (`token_radar_rows`, `pulse_candidates`, ...) each have exactly one runtime writer and are rebuildable. Current read models must use stable product/window keys, never run/generation/attempt/timestamp/UUID identity; unchanged projections must write zero serving rows. `NOTIFY` is a wake hint; every listener re-reads DB and runs a bounded `interval_seconds` catch-up. Provider raw frames are inputs, not facts.

## Runtime config for real data

Live-data runs use the operator-owned files in `~/.gmgn-twitter-intel/`: `config.yaml` for application/provider/credential/storage settings and `workers.yaml` for worker runtime knobs. Do not assume repository fixtures, example YAML, or `.env` files are the active runtime config. Before debugging provider data, Token Radar rows, asset profiles, or missing icons against real data, run `uv run gmgn-twitter-intel config` and confirm the reported `config_path` / `workers_config_path` point at `~/.gmgn-twitter-intel/`. Never print or copy secret values; report only redacted booleans, paths, and diagnostic command results.

## Frontend guardrails

Frontend CSS is harness-constrained, not convention-only. Before changing `web/src` UI code, read `docs/FRONTEND.md`. Do not recreate retired CSS buckets such as `cockpit.css`, `signalLab.css`, or `shared.css`; owner CSS must live beside the component or route that imports it. Feature CSS must use the owning feature namespace and must not restyle shared UI internals, notification internals, or Obsidian `.ods-*` selectors. `npm run lint` runs ESLint plus the frontend architecture harness; do not bypass it after CSS, responsive, route shell, or shared UI changes.

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
| Module architecture maps | `src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md`; discover current maps with `find src/gmgn_twitter_intel/domains -name ARCHITECTURE.md` |
| Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` are planning artefacts; verify against code and canonical docs before treating an old active file as current truth |
| External references & papers | `docs/references/` |
| Auto-generated artefacts | `docs/generated/` |
| Tech debt log | `docs/TECH_DEBT.md` |

## Claude-only protocol

When `superpowers:` skills are available, use this workflow chain: `brainstorming` → `writing-plans` → `using-git-worktrees` → `test-driven-development` → `executing-plans` / `subagent-driven-development` → `verification-before-completion` → `requesting-code-review` → `finishing-a-development-branch`. Process skills take priority.

CLI surface: `uv run gmgn-twitter-intel --help` is the source of truth (snapshot at `docs/generated/cli-help.md`).
