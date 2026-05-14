# CLAUDE.md

Claude-specific router. Mirrors `AGENTS.md` for the routing table and adds the Claude-only Skills / Plan-mode / Worktree protocol below. When you change either router, update the other.

## What this is

`gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

The pipeline is Kappa/CQRS: PostgreSQL material facts (`events`,
`token_intents`, `token_intent_resolutions`, `asset_identity_*`,
`price_observations`) are the only business truth. Derived read models
(`token_radar_rows`, `pulse_candidates`, ...) each have exactly one
runtime writer and are rebuildable. `NOTIFY` is a wake hint; every
listener re-reads DB and runs a bounded `interval_seconds` catch-up.
Provider raw frames are inputs, not facts.

## Where to read what

| Need | File |
|------|------|
| Install, run, docker | `docs/SETUP.md` |
| Layer boundaries & data flow | `docs/ARCHITECTURE.md` |
| Frontend architecture | `docs/FRONTEND.md` |
| Public surfaces (config, WS, HTTP, CLI) | `docs/CONTRACTS.md` |
| Spec→plan→tasks→verification flow | `docs/WORKFLOW.md` |
| Design rules (audit, reuse, scoring) | `docs/DESIGN_DISCIPLINE.md` |
| Testing & completion gates | `docs/TESTING.md` |
| Secrets, config, authn changes | `docs/SECURITY.md` |
| Operational invariants | `docs/RELIABILITY.md` |
| Cross-domain worker inventory | `docs/WORKERS.md` |
| Module architecture maps | `src/gmgn_twitter_intel/domains/<domain>/ARCHITECTURE.md` (currently `token_intel`, `asset_market`, `pulse_lab`) |
| Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` |
| External references & papers | `docs/references/` |
| Auto-generated artefacts | `docs/generated/` |
| Tech debt log | `docs/TECH_DEBT.md` |

## Claude-only protocol

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

CLI surface: `uv run gmgn-twitter-intel --help` is the source of truth (snapshot at `docs/generated/cli-help.md`).
