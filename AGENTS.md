# AGENTS.md

Router for coding agents (Codex, Cursor, generic LLM tooling). Project-wide rules; mirrored to `CLAUDE.md`. When you change one router, update the other. Substantive rules live under `docs/`; this file does not duplicate them.

## What this is

`gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

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
| Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` |
| External references & papers | `docs/references/` |
| Auto-generated artefacts | `docs/generated/` |
| Tech debt log | `docs/TECH_DEBT.md` |

CLI surface: `uv run gmgn-twitter-intel --help` is the source of truth (snapshot at `docs/generated/cli-help.md`).
