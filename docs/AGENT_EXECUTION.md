# Dormant Model Execution Library

> **Scope.** Defines the provider-neutral model-execution code retained as an
> isolated library. Development agents follow `AGENTS.md`, `CLAUDE.md`,
> `docs/WORKFLOW.md`, and `docs/agent-playbook/`; they are unrelated to this
> library.

Parallax production runtime has no model-backed product lane. Bootstrap,
worker factories, the worker manifest, status, Ops diagnostics, repositories,
domains, public API, CLI, and frontend instantiate no model consumer. No
product queue, run ledger, current read model, prompt, or knowledge catalog is
owned by the retained library.

## Retained boundary

The dormant library remains importable and independently unit tested:

- strict execution policy and request/result audit types;
- provider-family capability profiles and request options;
- deterministic JSON/text/artifact/trace hashing;
- structured JSON object strategy and output-schema validation;
- provider usage extraction;
- capacity, rate-limit, timeout, and circuit-breaker mechanics in the generic
  execution gateway.

These are infrastructure primitives, not current product configuration or
business truth. PostgreSQL material facts remain the only business truth and
the current service never publishes output from this library.

## Configuration boundary

`~/.parallax/config.yaml` may retain the dormant `llm.api_key` and
`llm.base_url` values. Bootstrap does not read them to construct a model
client, and redacted config output does not expose a model status lane.
`workers.yaml` has no model policy, lane map, model selector, token budget,
capacity limit, prompt version, or circuit-breaker block.

The library's `AgentRuntimePolicy` is a constructor-level type for isolated
callers and tests. It is not part of `WorkersSettings`, runtime snapshots, or
operator status.

## Library flow

When exercised in isolation, the generic gateway performs this bounded flow:

```text
typed stage packet
  -> deterministic request audit and artifact hash
  -> optional capacity/rate reservation
  -> one structured JSON provider call
  -> strict schema validation
  -> typed result or typed execution error
```

The gateway owns execution mechanics only. It does not access PostgreSQL,
domain repositories, application operations, HTTP routes, queues, prompts on
disk, or product publication state.

Provider/network work must remain outside a database transaction. Any future
product consumer requires a new approved spec that defines its evidence
contract, durable audit/state ownership, cost and retry policy, public
consumer, migration, and independent verification. Importability of this
library grants none of those product semantics.

## Owning files

| Concern | Source |
|---|---|
| Execution policy and audit types | `src/parallax/platform/agent_execution.py` |
| Provider capability profiles | `src/parallax/platform/agent_capabilities.py` |
| Deterministic hashes | `src/parallax/platform/agent_hashing.py` |
| Generic execution gateway | `src/parallax/integrations/model_execution/execution_gateway.py` |
| Strict output schema | `src/parallax/integrations/model_execution/output_schema.py` |
| Structured JSON strategy | `src/parallax/integrations/model_execution/structured_json_strategy.py` |
| Usage extraction | `src/parallax/integrations/model_execution/usage.py` |

## Hard boundaries

- Do not import or instantiate the gateway from production composition.
- Do not add a model worker, queue, table, status object, Ops section, API
  field, frontend field, prompt catalog, or domain adapter without a new spec.
- Do not treat request/result audit envelopes as material facts.
- Do not let a read route execute a provider call.
- Do not add domain-specific lanes or provider branches to the generic
  primitives.
- Do not load instructions or knowledge from the filesystem at execution time.

## Verification

```bash
uv run pytest tests/unit/integrations/model_execution -q
uv run pytest tests/architecture/test_product_ai_hard_delete.py -q
```

The first command proves the dormant primitives still work in isolation. The
second proves the production composition and supported contracts contain no
model-backed product consumer.
