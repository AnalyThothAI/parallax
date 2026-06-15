# Agent Execution

> **Scope.** Defines the product LLM agent execution plane. Development agents such as Codex, Claude, Cursor, and subagents follow `AGENTS.md`, `CLAUDE.md`, `docs/WORKFLOW.md`, and `docs/agent-playbook/`.

Parallax uses the word "agent" in two different ways:

- **development agents**: coding tools that read this repository, write specs/plans/code, run tests, and hand work to subagents.
- **product LLM agents**: runtime workers that call models to produce bounded semantic outputs for product workflows such as Pulse, News item briefs, and Narrative Intelligence.

Do not mix these planes. Development agent traces, chat history, branch summaries, and subagent findings are engineering workflow evidence. They are not Parallax product truth.

## Product Runtime Boundary

PostgreSQL facts remain truth. Read models are rebuildable. Control-plane rows schedule work. Provider frames are inputs. Runtime LLM output becomes product state only through the owning domain worker's validation, ledger, and read-model write path.

There is no central durable `agent_tasks` queue. Domain workers own admission, claim, retry, finalize, run ledgers, and business validation. `AgentExecutionGateway` owns execution mechanics only:

- lane policy and model selection
- global and lane concurrency bulkheads
- RPM reservation
- timeout and circuit-breaker state
- structured JSON object dispatch
- application-side Pydantic validation
- trace metadata, usage, input/output hashes, and request/result audit envelopes

Domains submit typed `AgentStageSpec` packets with Pydantic output types. Domains must not branch on provider-specific response formats or call LiteLLM/OpenAI directly.
Capacity reservations release lane/global/RPM resources through a synchronous
callback owned by `AgentExecutionGateway`. `AgentCapacityReservation.release()`
is async only because callers already await the public method; its internal
`_release()` callback must return `None`. Awaitable release results are
malformed execution-plane wiring, not an alternate lifecycle shape.
Provider wiring for known product lanes reads the formal
`workers.agent_runtime.lanes` settings directly. For example, the Pulse
decision provider uses `workers.agent_runtime.lanes["pulse.decision"].timeout_seconds`;
missing lane settings are malformed runtime configuration, not a provider-local
120-second fallback.
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

Some product agents may prepare bounded input evidence before submitting an
`AgentStageSpec`. The News item brief lane builds one deterministic packet from
the current news item, token/entity evidence, fact lanes, provider signal
evidence, market-scope metadata, and host-computed agent admission/similarity
context. It does not run a News-local research tool loop or database retrieval
tools at agent time.

Prompt text is part of the execution artefact. The shared gateway hashes
`AgentStageSpec.instructions`, and the News item brief client includes the
current News prompt text hash in its artifact version hash. A prompt edit
therefore changes request audit/freshness even when a version constant was not
manually bumped.

There is no shared runtime tool loop. The shared `AgentExecutionGateway` runs
structured JSON model calls only. It does not receive `tools=`, execute domain
tools, hold database sessions, or become a lower-level application workflow
kernel.

Input evidence is not business truth by itself. PostgreSQL facts and
rebuildable read models remain truth, and model output becomes product state
only if the owning domain validation and writer path publishes a derived read
model.

`NewsItemBriefWorker` remains the only runtime writer for
`news_item_agent_runs` and `news_item_agent_briefs`. It rechecks deterministic
market-wide `agent_admission` state and `market_scope_json` after claiming work.

## Read-Only Context Registry

Parallax borrows the useful part of agent harness tool catalogs without adding
a model-driven tool loop. `src/parallax/platform/agent_read_tools.py` declares
read-only `ReadOnlySqlAgentTool` metadata over current read models such as
`news_item_agent_briefs`, `pulse_candidates`, and `token_radar_current_rows`.
These tools are not passed to models as callable tools. They are a typed
catalog for deterministic host-side context assembly, operator inspection, and
future reviewed retrieval code.

Tool SQL must be a single `SELECT`/`WITH` statement and the manifest must not
expose raw SQL. Mutating verbs, multiple statements, and writable tool metadata
fail validation. Product agents may reference tool ids through
`AgentStageSpec.read_only_tool_refs`, but the owning domain still decides what
data to load and remains responsible for all product writes.

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

The justified hooks are typed observer seams that already match the service:
worker status, queue health, wake hints, agent audit envelopes, telemetry, and
domain ledgers. New hook-like extension points must be typed, read-only unless
owned by the domain writer, and testable through the manifest/audit contract.

## Runtime Flow

```text
domain worker
  -> exact fact/read-model packet
  -> reserve agent lane capacity/RPM
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
| Worker existence/lane/kind manifest | `src/parallax/app/runtime/worker_manifest.py` |
| Cross-domain worker ownership | `docs/WORKERS.md` |
| System-level invariants | `docs/ARCHITECTURE.md` |

## Domain Responsibilities

- Build a bounded input packet from persisted facts/read models.
- Reserve lane capacity before claiming work that can burn business attempts.
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
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py
uv run pytest tests/architecture/test_agent_model_capability_contracts.py
uv run pytest tests/unit/integrations/model_execution/test_agent_execution_gateway.py
```

For a domain-specific product LLM agent, also run the affected worker/client unit tests and update the owning domain `ARCHITECTURE.md` when runtime ownership changes.
