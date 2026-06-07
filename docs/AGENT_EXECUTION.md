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

## Domain-Local Harnesses

Some product agents may prepare bounded input evidence before submitting an
`AgentStageSpec`. The News item brief lane builds one deterministic packet from
the current news item, entity lanes, fact lanes, provider signal evidence,
market scope, agent admission, similarity, and material-delta context. It does
not run a News-local research tool loop or database retrieval tools at agent
time.

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
market-wide agent admission after claiming work and does not use
`analysis_admission_status` as the News Item Brief gate.

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
