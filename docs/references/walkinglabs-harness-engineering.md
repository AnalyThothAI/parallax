# walkinglabs/learn-harness-engineering — OpenAI Advanced

**Source:** https://github.com/walkinglabs/learn-harness-engineering/blob/main/docs/zh/resources/openai-advanced/index.md
**Fetched:** 2026-05-09
**Cited by:** `docs/WORKFLOW.md`

## Summary

Five design principles for organising an LLM-coding-agent harness in a repository:

1. **Short entry, deep links.** Entry files (`AGENTS.md`, `CLAUDE.md`) point; rules live in linked governance files.
2. **The repository is the only source of truth.** Avoid relying on chat history or operator memory.
3. **Mechanical structure beats verbal convention.** Directory layout and file naming enforce intent more reliably than prose rules.
4. **Plans, quality, and tech debt are versioned alongside code.** Use lane folders with lifecycle states.
5. **Cleanup and harness simplification are routine work**, not emergency rescue.

Recommended structure: short routers at the root, governance files under `docs/`, lane folders with `active/` and `completed/`, `references/` for external materials, `generated/` for derived artefacts, plus per-domain governance files (DESIGN, RELIABILITY, SECURITY, FRONTEND, QUALITY).

## How this repo applies it

- Routers: `AGENTS.md`, `CLAUDE.md` (≤ 60 lines each).
- Governance: nine `docs/*.md` files plus `TECH_DEBT.md` (see the routing table in either router).
- Lane lifecycle: `docs/sdd/features/{active,completed}/YYYY-MM-DD-<slug>/`.
- Support: `docs/references/`, `docs/generated/`.
- Source layout (`src/parallax/`) is independently aligned with the "mechanical structure" principle and is unchanged by this restructure.
