# Development Agent Factory Operating Model

This file defines how Parallax uses coding agents and subagents for development work. It is not a product runtime design. Product LLM agents are not development-agent lanes, and development-agent traces are never product truth.

## Reference Alignment

This model follows these current external patterns:

- GitHub Spec Kit: spec-driven work flows through clarify, checklist, plan, tasks, analyze, and implement gates.
- OpenAI Codex: the harness owns the agent loop, context assembly, tool execution, observation, and repair path.
- GitHub Copilot cloud agent: delegated tasks need clear scope, acceptance criteria, and changed-file guidance.
- Claude Code: hooks carry deterministic lifecycle checks; subagents and worktrees carry bounded, isolated context.

References:

- [GitHub Spec Kit](https://github.com/github/spec-kit)
- [OpenAI Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)
- [GitHub Copilot task best practices](https://docs.github.com/en/enterprise-cloud@latest/copilot/tutorials/cloud-agent/get-the-best-results)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code advanced patterns](https://resources.anthropic.com/hubfs/Claude%20Code%20Advanced%20Patterns_%20Subagents%2C%20MCP%2C%20and%20Scaling%20to%20Real%20Codebases.pdf)

## Deterministic Constraints

Deterministic constraints are always loaded or enforced by harness:

- `AGENTS.md` / `CLAUDE.md` route agents to canonical docs without duplicating rules.
- `docs/WORKFLOW.md` owns SDD lane mechanics, worktree policy, and completion gates.
- `scripts/validate_sdd_artifacts.py --check` fails false completion claims, missing gate sections, missing task fields, and active touch conflicts.
- `scripts/regen_sdd_work_index.py --check` keeps the coordination board current.
- `scripts/build_agent_context_packet.py` generates bounded subagent context from a validated active SDD task.
- `make check-all` is the only completion command for a `Verified` SDD record.

Do not replace deterministic constraints with prompt instructions. If a rule must always hold, encode it in docs, templates, scripts, tests, generated indexes, or Makefile gates.

## On-Demand Context

On-demand context is loaded only when a task needs it:

- `docs/agent-playbook/task-reading-matrix.md` picks the minimum source-backed reading set.
- `docs/agent-playbook/context-packet-template.md` carries bounded facts to subagents.
- Domain `ARCHITECTURE.md` files define local ownership and truth boundaries.
- SDD active records explain current execution intent but must be checked against canonical docs and code.

Subagent output is evidence, not authority. The parent integrator must inspect source, diff, and verification before integrating.

## Lane Budget

Use a maximum of six active lanes for a feature:

| Lane | Purpose | Default owner |
|------|---------|---------------|
| Spec / plan | Clarify, checklist, analyze, and acceptance criteria. | Parent integrator |
| Domain implementation | One bounded domain or file family. | Worker subagent or parent |
| Harness / tests | Failing tests, validators, generated gates, and contract helpers. | Parent or reviewer |
| Docs / contracts | Router, templates, generated docs, public contracts. | Parent or docs worker |
| Risk radar | P0/P1 issues, flaky tests, conflict scan, stale work. | Read-only scout |
| Final integration | Diff review, verification, merge, and completion record. | Parent integrator |

More lanes are allowed only by splitting the feature into separate SDD records. Parallel lanes must have disjoint touch sets or an explicit conflict rule in `tasks.md`.

## Parent Integrator

The Parent integrator owns:

- Saying no to scope that violates the approved spec.
- Keeping work inside the SDD feature record and active coordination board.
- Assigning one owner per touch set.
- Reviewing every subagent diff and evidence line.
- Keeping product LLM agent runtime boundaries separate from development workflow.
- Refusing `Verified` until `make check-all` evidence exists.

## Kill / Defer Criteria

Stop or defer an agent lane when any of these happen:

- It edits outside its Touch set or ignores the Conflict set.
- It cannot explain the source-backed reason for its change.
- It proposes compatibility code, fallback paths, or old-file aliases after a hard cut.
- It reports success without command output and exit status.
- It repeats the same failed fix twice without a root-cause update.
- It needs integration/e2e/live evidence that the user explicitly deferred.

The parent integrator records the reason in the SDD task, verification record, or a follow-up spec. Do not hide stopped work behind green wording.

## Dispatch Protocol

Before dispatching a subagent:

- Fill `Factory lane`, `Touch set`, `Conflict set`, `Deterministic constraints`, `On-demand context`, `Kill/defer criteria`, and `Eval/repair signal` in `tasks.md`.
- Generate a bounded context packet with `uv run python scripts/build_agent_context_packet.py --feature <slug> --task <number> --mode <read-only|write-allowed|review-only>`.
- State whether the subagent is read-only, write-allowed, or review-only.
- Require verification evidence or a source-backed explanation for why verification cannot run.

After dispatch:

- Integrate only after parent review.
- Update `docs/generated/sdd-work-index.md` through the generator.
- Keep the active SDD record honest when a gate is skipped by user instruction.
