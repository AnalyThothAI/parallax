# Spec — Agent Playbook Skill Hard Cut

**Status**: Superseded
**Superseded by**: `docs/ARCHITECTURE.md`
**Date**: 2026-06-09
**Owner**: Codex
**Approved by**: delegated goal
**Approved at**: 2026-06-09
**Related**: `docs/references/agent-coding-research-2026.md`, `docs/agent-playbook/task-reading-matrix.md`

## Background

The agent coding research document recommends source-backed task contracts, short `AGENTS.md` rules, skill packaging, verification gates, and bounded subagent/worktree lanes (`docs/references/agent-coding-research-2026.md:13`, `docs/references/agent-coding-research-2026.md:14`, `docs/references/agent-coding-research-2026.md:17`, `docs/references/agent-coding-research-2026.md:18`). The current task matrix routes agents to minimum source-backed context and playbook artifacts (`docs/agent-playbook/task-reading-matrix.md:3`, `docs/agent-playbook/task-reading-matrix.md:7`); the surviving read-model review contract is documented directly in `docs/agent-playbook/read-model-change-checklist.md:1`.

## Problem

The recommendations were still mostly prose. Agents could read the matrix, but the repository did not provide copyable task examples, repo-scoped skills for frequent workflows, or a dedicated read-model review checklist. During audit, `MacroIntelRepository.concept_history_counts` also retained a `series_rank = 1` filter that made history counts read only the latest projected point.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should this keep compatibility with old planning or macro generation paths? | No. Add current playbook/skills and remove the bad latest-only history filter. | delegated goal | 2026-06-09 |
| Should skills live in the repo rather than only user-global Codex config? | Yes. These are Parallax-specific workflows and should be discoverable from `.agents/skills`. | delegated goal | 2026-06-09 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Task examples are executable. | Architecture test requires examples for provider diagnostics, workers, frontend QA, and read-model review. |
| Frequent workflows are skills. | Architecture test requires four repo-scoped `SKILL.md` files with required trigger phrases. |
| UI QA has a fixed path. | Frontend skill requires `docs/FRONTEND.md`, lint, typecheck, targeted tests, and browser evidence for visible layout changes. |
| Read-model review is explicit. | Checklist names stable keys, single writer, zero unchanged writes, catch-up, and provider boundary. |
| Macro history counts use projected history rows. | Unit tests forbid `series_rank = 1` in `concept_history_counts`. |

## First principles

- Root routers stay concise; substantive development-agent workflows live under `docs/agent-playbook/`.
- Derived read models must use stable product/window keys and exactly one runtime writer.
- Current-row hard cuts delete old identity and compatibility paths rather than wrapping them.

## Goals

- G1. Agents have copyable task examples for the four high-frequency workflow families.
- G2. `.agents/skills` contains Parallax skills for worker debugging, provider diagnostics, frontend verification, and read-model review.
- G3. Read-model review has a dedicated checklist that rejects run/generation/attempt/timestamp/UUID current identity and compatibility shims.
- G4. Macro concept history counts read all projected lookback rows, not only `series_rank = 1`.

## Non-goals

- N1. This does not add a product LLM runtime tool loop.
- N2. This does not add a safety hook for live config, which was recommendation 3 and is intentionally out of scope.
- N3. This does not preserve retired planning lanes or macro generation compatibility paths.

## Target architecture

The agent playbook becomes the repository-local workflow surface. The reading matrix routes tasks, task examples provide copyable prompts, skills package repeated procedures, and architecture tests enforce their presence. Macro request paths continue to read projected `macro_observation_series_rows`, but history counts no longer collapse to latest-only rows.

## Conceptual data flow

```text
agent goal -> task-reading-matrix -> task examples / repo skill -> required docs/tests -> verified change
macro_observations -> MacroViewProjectionWorker -> macro_observation_series_rows -> concept_history_counts
```

## Core models

- Task example: a bounded prompt contract with Goal, Context, Required reading, Verification, and Done when sections.
- Repo skill: `.agents/skills/<name>/SKILL.md` with frontmatter and current Parallax workflow steps.
- Read-model checklist: a review contract for truth boundary, writer ownership, identity, idempotency, catch-up, and public consumers.

## Interface contracts

- Development-agent docs: `docs/agent-playbook/task-examples.md` and `docs/agent-playbook/read-model-change-checklist.md`.
- Skills: `.agents/skills/parallax-worker-debugging`, `.agents/skills/parallax-real-data-provider-diagnostics`, `.agents/skills/parallax-frontend-verification`, `.agents/skills/parallax-read-model-review`.
- Repository method: `MacroIntelRepository.concept_history_counts` returns projected history coverage using `macro_observation_series_rows`.

## Acceptance criteria

- AC1. WHEN architecture tests inspect the playbook THEN task examples and read-model checklist SHALL exist and include the required workflow phrases.
- AC2. WHEN architecture tests inspect `.agents/skills` THEN the four Parallax skills SHALL exist with trigger descriptions and required commands/docs.
- AC3. WHEN `concept_history_counts` SQL is inspected THEN it SHALL read `macro_observation_series_rows` and SHALL NOT filter to `series_rank = 1`.
- AC4. WHEN the SDD index is regenerated THEN this active work SHALL appear with owner, branch, worktree, touch set, and verification state.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Skills drift from canonical docs. | Medium | Skills point back to `task-reading-matrix.md` and canonical docs rather than duplicating product truth. |
| Checklist becomes another prose-only rule. | Medium | Architecture test requires its presence and required hard-cut phrases. |
| Macro history query regresses to raw facts. | High | Unit tests require projected rows and forbid raw `macro_observations`. |

## Evolution path

The next step is recommendation 3: a real-data safety hook that blocks secret-bearing config output. That should be a separate SDD feature because it changes command/tool lifecycle behavior.

## Alternatives considered

- Keep the research doc as the only artifact — rejected because it is not executable and agents would not discover it in normal task flow.
- Put skills in user-global Codex config — rejected because these workflows are Parallax-specific and should travel with the repo.
- Keep `series_rank = 1` for history count speed — rejected because it changes the metric from history coverage to latest-only coverage.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Add repo-scoped skills, examples, checklist, tests, and the macro history-count hard cut. |
| Ask first | Add command hooks or live secret scanners. |
| Never | Recreate legacy planning lanes or keep latest-only history count compatibility. |
