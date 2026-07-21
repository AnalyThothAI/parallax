# Agent Execution

> **Scope.** Defines the product LLM agent execution plane. Development agents such as Codex, Claude, Cursor, and subagents follow `AGENTS.md`, `CLAUDE.md`, `docs/WORKFLOW.md`, and `docs/agent-playbook/`.

Parallax uses the word "agent" in two different ways:

- **development agents**: coding tools that read this repository, write specs/plans/code, run tests, and hand work to subagents.
- **product LLM agents**: runtime workers that call models to produce bounded semantic outputs. The current production lane is the News story brief.

Do not mix these planes. Development agent traces, chat history, branch summaries, and subagent findings are engineering workflow evidence. They are not Parallax product truth.

## Product Runtime Boundary

PostgreSQL facts remain truth. Read models are rebuildable. Control-plane rows schedule work. Provider frames are inputs. Runtime LLM output becomes product state only through the owning domain worker's validation, ledger, and read-model write path.

There is no central durable `agent_tasks` queue. Domain workers own admission, claim, retry, finalize, run ledgers, and business validation. `AgentExecutionGateway` owns execution mechanics only:

- the fixed News story-brief model and capability policy
- one capacity gate
- RPM reservation
- timeout and circuit-breaker state
- structured JSON object dispatch
- application-side Pydantic validation
- trace metadata, usage, input/output hashes, and request/result audit envelopes

Domains submit typed `AgentStageSpec` packets with Pydantic output types. Domains must not branch on provider-specific response formats or call LiteLLM/OpenAI directly.
Capacity reservations release capacity resources through a synchronous
callback owned by `AgentExecutionGateway`. `AgentCapacityReservation.release()`
is async only because callers already await the public method; its internal
`_release()` callback must return `None`. Awaitable release results are
malformed execution-plane wiring, not an alternate lifecycle shape.
The gateway has one runtime purpose: `news.story_brief`. The lane string remains
a stable audit tag on `AgentStageSpec`; it is not a configurable selector or a
runtime policy lookup. Any other stage lane is malformed input. The single flat
`workers.agent_runtime` object owns model, capability overrides, token budget,
concurrency, RPM, timeout, and circuit-breaker policy. There are no global
limits, lane maps, defaults overlays, or provider-local timeout fallbacks.
`rate_units` reserves a bounded batch of calls before domain work is claimed.
One execution performs exactly one provider call and then validates once;
schema failure returns to the durable worker retry path instead of hiding an
uncounted paid call inside the client.

The operator-owned `~/.parallax/workers.yaml` uses the same flat shape:

```yaml
agent_runtime:
  model: deepseek-v4-flash
  provider_family: null
  max_tokens: 2200
  max_concurrency: 1
  rpm_limit: 60
  timeout_seconds: 180.0
  circuit_breaker:
    failure_threshold: 5
    window_seconds: 300
    open_seconds: 120
```

Domain adapters that build `AgentStageSpec` must carry validated request-audit
trace identity into the gateway. Missing or mismatched `run_id` trace metadata,
or a missing product group id from the stage input packet, is malformed
domain-runtime output and must fail before gateway request-audit or model
execution; adapters must not replace those fields with empty strings or
pipeline-local run-id fallbacks.
Workflow identity follows the same rule. A domain adapter may use its canonical
workflow name when the constructor argument is omitted, but an explicit blank or
`None` workflow name is malformed wiring and must not be restored to a default.

## Domain-Local Harnesses

The News story brief lane prepares one deterministic packet from the
representative item, bounded member evidence, and News-owned entity/fact
context before submitting an `AgentStageSpec`. It does not run a News-local
research tool loop or database retrieval tools at agent time.

Prompt text and the effective capability policy are part of the execution
artefact. The News client delegates its freshness hash to the same gateway
method used by request audit, so prompt, provider family, request options, model,
schema, or runtime changes cannot reuse an older brief.

There is no shared runtime tool loop. The shared `AgentExecutionGateway` runs
structured JSON model calls only. It does not receive `tools=`, execute domain
tools, hold database sessions, or become a lower-level application workflow
kernel.

Input evidence is not business truth by itself. PostgreSQL facts and
rebuildable read models remain truth, and model output becomes product state
only if the owning domain validation and writer path publishes a derived read
model.

`NewsStoryBriefWorker` is the only runtime writer for
`news_story_agent_runs` and `news_story_agent_briefs`; the retired item-brief
tables and worker have no compatibility path. The worker rechecks deterministic
market-wide `agent_admission` state and `market_scope_json` after claiming
work. Admission decides whether a brief may execute; dirty-target priority is
only a deterministic scheduling hint. Bounded packet builders keep context
intentionally narrow so repeated or low-value news does not consume the same
model budget as fresh material changes. Model output budgets live in
`workers.agent_runtime.max_tokens`.

## Knowledge Catalog

`src/parallax/platform/agent_knowledge.py` provides a small prompt knowledge
catalog. The index exposes stable ids and summaries only; full markdown bodies
load on demand and are appended to stage instructions through explicit
`AgentStageSpec.knowledge_refs`. This mirrors the useful shape of Claude Code
skills and lightweight prompt libraries while keeping prompt expansion
deterministic and auditable.

Knowledge refs must fail closed when unknown. Prompt text hashes include the
loaded knowledge body so edits invalidate agent artifacts without relying on a
manual version bump.

## Hooks Decision

Claude Code-style `PreToolUse` / `PostToolUse` hooks are not a product hot-path
requirement because Parallax models do not execute tools. The runtime does not
need shell-command guards, tool-permission callbacks, or generic post-tool
mutation hooks inside `AgentExecutionGateway`.

The justified observer seams are worker status, agent audit envelopes,
telemetry, and domain ledgers. Queue-depth sampling is an explicit
operator diagnostic, not a runtime hook or hot status-path dependency. New
observer seams must be typed, read-only unless owned by the domain writer, and
testable through the manifest/audit contract.

## Runtime Flow

```text
domain worker
  -> exact fact/read-model packet
  -> reserve agent capacity/RPM
  -> AgentStageSpec
  -> AgentExecutionGateway
  -> structured JSON model call
  -> Pydantic/schema validation
  -> domain business validation
  -> domain run ledger and read-model write
```

No-start backpressure does not claim business work, burn a provider attempt, or write a business run ledger. Once provider execution starts, validation/publication failures must be audited by the domain run ledger with `execution_started=true`.

## Owning Files

| Concern | Source |
|---------|--------|
| Shared runtime policy and audit types | `src/parallax/platform/agent_execution.py` |
| Model capability profiles | `src/parallax/platform/agent_capabilities.py` |
| LiteLLM execution gateway | `src/parallax/integrations/model_execution/execution_gateway.py` |
| Worker existence/kind manifest | `src/parallax/app/runtime/worker_manifest.py` |
| Cross-domain worker ownership | `docs/WORKERS.md` |
| System-level invariants | `docs/ARCHITECTURE.md` |

## Domain Responsibilities

- Build a bounded input packet from persisted facts/read models.
- Reserve agent capacity before claiming work that can burn business attempts.
- Persist request/result audit details in the domain ledger.
- Validate model claims against known evidence refs and domain rules.
- Abstain or mark degraded state when inputs are insufficient.
- Keep API, WebSocket, CLI, and frontend paths read-only over facts/read models.

## What Not To Do

- Do not treat model output as a fact before domain validation.
- Do not let public routes run product LLM agents inline.
- Do not use runtime agent audit rows as the only business truth.
- Do not create fallback runtime paths for old agent schemas.
- Do not add provider-specific branches in domain workers when the capability belongs in `AgentExecutionGateway`.

## Verification

Use these checks when editing the product LLM agent plane:

```bash
uv run pytest tests/architecture/test_kiss_runtime_invariants.py
uv run pytest tests/unit/integrations/model_execution/test_agent_execution_gateway.py
uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py
```

For a domain-specific product LLM agent, also run the affected worker/client unit tests and update the owning domain `ARCHITECTURE.md` when runtime ownership changes.
