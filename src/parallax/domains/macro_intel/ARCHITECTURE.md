# Macro Intel Architecture

Macro Intel has one material-fact lane and one derived research lane.
PostgreSQL `macro_observations` are the only Macro evidence truth.
`MacroSyncWorker` is the normal ingest owner; `macro import-bundle` is an
offline replay/seed entrypoint into the same fact and attempt contracts.
`MacroResearchWorker` publishes one immutable DeepAgents-authored research
artifact per completed U.S. regular session.
Live evidence pages read bounded `macro_observations` directly; they own no
projection table, snapshot, judgment, queue, or worker.

## Ownership

| Object | Kind | Single runtime writer |
|---|---|---|
| `macro_observations` | Material fact | `MacroSyncWorker`; offline import may replay the same fact contract |
| `macro_sync_windows` | Scheduling/control state | `MacroSyncWorker` |
| `macro_sync_runs` | Sync/offline-import attempt ledger | `MacroSyncWorker` and the offline import command |
| `macro_research_runs` | Completed-session lease/retry/seal state | `MacroResearchWorker` |
| `macro_research_publications` | Immutable completed-session derived research | `MacroResearchWorker` |
| `checkpoint_migrations` | LangGraph checkpoint schema version | Alembic migration |
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` | Durable DeepAgents execution state | LangGraph `AsyncPostgresSaver` used by `MacroResearchWorker` |

Sync runs and research runs are control/audit state, not business truth.
Checkpoint rows are resumable graph state, not evidence, publications, or a
public read model. A publication is derived research whose stable product
identity is `session_date`.

## Data flow

```text
macro_sync_windows
  -> MacroSyncWorker bounded claims
  -> configured macrodata history bundles
  -> macro_observations + macro_sync_runs
  -> GET /api/macro/evidence/{view_id}
  -> /macro + six live data detail routes

latest completed U.S. session
  -> macro_research_runs durable claim and frozen scope
  -> one CompletedSessionMacro.run/read module
  -> one DeepAgents parent with native planning and scoped specialists
  -> immutable macro_research_publications
  -> GET /api/macro/research
  -> /macro/research
```

The provider boundary returns one exact `MacrodataBundleRunResult` containing
an envelope and redacted diagnostics. Runtime invokes the installed package
entrypoint through the current Python interpreter. Provider execution occurs
outside database transactions. Valid fact upserts, attempt recording, and
sync-window completion share one repository-session transaction.

The sync worker claims a bounded batch. A failed or timed-out window records
its own retry/failure state and does not stop the worker from attempting other
due windows in that batch. Restart recovery re-reads PostgreSQL; there is no
wake-plane or in-memory correctness dependency.

## Material fact identity

`macro_observations` preserves source/series/concept/date identity, numeric or
event value, unit/frequency/quality, provider provenance, source and ingestion
times, and the raw evidence payload. Its material identity is
concept/source/series/date. The fact payload hash excludes fetch and sync
identifiers, so identical replay writes nothing.

The offline importer validates and normalizes the complete envelope before it
opens the write transaction. It then writes facts and one `macro_sync_runs` row
atomically. Fact import does not enqueue or build a derived judgment.

## Completed-session research deep module

The common caller sees one small completed-session interface:

```python
class CompletedSessionMacro(Protocol):
    async def run(self, session_date: date | None = None) -> MacroSessionView: ...
    async def read(self, session_date: date | None = None) -> MacroSessionView | None: ...
```

Normal worker execution calls `run()` with no product-program arguments.
`session_date` exists only for explicit backfill or history. `read()` is
persisted-only. The caller cannot choose a tool list, research taxonomy,
section layout, direction schema, readiness state, review sequence, or prompt
program.

Internally, a run:

1. resolves the completed U.S. session and market-close cutoff;
2. creates or re-reads the durable session row and freezes its seal time;
3. claims the session under an owner-bound crash-recovery lease and renews it
   while the Agent invocation is alive;
4. invokes the Macro-owned DeepAgents adapter outside the write transaction;
5. mechanically verifies artifact session/cutoff identity and citation closure;
6. inserts the immutable publication and completes the run atomically.

Run states are `pending`, `running`, `retryable`, `failed`, and `published`.
The worker renews a live run every one-third of `lease_ms`; that lease prevents
concurrent graph/checkpoint writers but never limits total research time. A
failed owner compare-and-set cancels only that stale local invocation without a
publish/error transition. An expired running lease can be reclaimed while
attempts remain. A published session performs zero model calls and zero serving writes on replay.

## Frozen evidence scope and tools

Every run has one `FrozenMacroEvidenceScope`:

- `session_date`;
- exact market-close `market_cutoff_ms`;
- immutable `sealed_at_ms`;
- a deterministic scope ID derived from those fields.

The Agent receives pageable tools for:

- inspecting the in-scope evidence catalog;
- searching material Macro observations by text, concept, date, and offset;
- reading exact disclosed evidence references;
- searching eligible persisted News by query, source, and offset;
- paging prior immutable Macro publications as contextual comparison.

Search is a compact discovery surface and returns `next_offset` when the same
query can continue. Exact-reference reads preserve the complete typed evidence,
including observation raw payload and persisted News text. When an exact result
is large, native DeepAgents FilesystemMiddleware writes it under
`/large_tool_results/` in the checkpoint filesystem and the Agent continues
with `read_file`; Parallax does not truncate it or replace that native recovery
path with a payload-size failure.

Evidence visibility is mechanical point-in-time integrity, never a
concept/category allowlist. An exact timezone-bearing source timestamp is the
availability clock and must not exceed the market cutoff; ingestion may finish
during the frozen run's settle window but not after its seal. A date-only
source value is an observation/event date, not a publication time, so
`ingested_at_ms` is the conservative system-known clock and must not exceed the
market cutoff. This permits a future scheduled event that was already known
without treating its event date as availability. News must be both published
by the cutoff and persisted by the seal. These rules prevent hindsight; they
do not decide whether evidence is sufficient or what conclusion it supports.

## DeepAgents topology

One parent DeepAgent owns:

- native `write_todos` planning and replanning;
- checkpoint-backed virtual-filesystem notes, drafts, and large results;
- a shared `/workspace/` plus real `execute` for calculations and scripts;
- which evidence tools to call and in what order;
- dynamic `task` delegation;
- counterevidence and alternative explanations;
- section names, ordering, evidence gaps, review, and final Chinese narrative.

Declared specialists are an evidence analyst, cross-asset challenger, and
skeptical editor. They are capabilities available to the parent, not a
Parallax-authored sequence or pass/block workflow. Parallax exposes no generic
agent-program DSL and no second model gateway.

Parallax does not register a harness profile, permission table, or approval
middleware that removes or pauses DeepAgents tools. The production native
`CompositeBackend` routes ordinary files and `/large_tool_results/` to
checkpoint-backed `StateBackend`; `/workspace/` and `execute` share one stable
per-scope calculation directory. Market facts must still enter through the
frozen scoped evidence tools: direct provider access, live browsing, and
arbitrary database reads cannot establish publishable facts. That is an
evidence-lineage boundary, not a capability or investment-judgment gate.

## Durable graph state

Production composition opens LangGraph `AsyncPostgresSaver` through an async
context factory using the configured PostgreSQL DSN. The frozen scope ID is the
stable `thread_id`, so retries and process restarts resume the same graph state.
Native todo, ordinary virtual files, and large-result state therefore survive
through checkpoint persistence rather than a process-local memory saver.
Execution workspace files live under
`~/.parallax/macro-agent-workspaces/<scope>/`, which is mounted into the app
container and stable across process restarts; they remain scratch, not facts or
publication state.

Retries pass `None` to the graph for an existing thread, which resumes pending
native tasks without appending another user turn. Final cited references are
mechanically re-read from the same frozen scope so a parent can publish after
resuming even when specialist tool messages remain in their native `tools:*`
checkpoint namespace.

Alembic owns all checkpoint DDL and records its compatible migration versions
in `checkpoint_migrations`. Application startup does not call checkpointer
setup. Checkpoint payloads may contain messages and scratch research state;
they are never returned by the Macro API.

## Research artifact and publication

The structured envelope fixes only storage and citation integrity:

- schema version, session date, and market cutoff;
- Agent-authored title and executive summary;
- one authoritative dynamic ordered list of Agent-authored Markdown sections;
- Agent-authored evidence gaps and open questions;
- citations with stable IDs, material source references, provenance, dates,
  and URLs when available;
- reviewer notes and bounded sanitized audit metadata.

Production code checks exact session/cutoff identity, unique local IDs,
citation referential closure, and that cited sources re-read from the frozen
scope. A flat Markdown export is mechanically derived from the ordered
sections; it is not a second model-authored body. Production code does not
impose language ratios, fixed sections, asset lanes, forecast horizons,
direction labels, confidence, coverage thresholds, readiness, or semantic
conclusions.

The audit field `verified_source_refs` means every final citation reference was
mechanically re-read and canonicalized inside the frozen scope. It does not
claim that root checkpoint messages retain each specialist's internal tool
transcript; native specialist work remains in its LangGraph checkpoint
namespace.

`macro_research_publications` has one row per `session_date`. Publication
insertion and the run transition to `published` share one transaction. A
database trigger rejects update or delete, so history cannot be silently
rewritten. Model, prompt, workflow, artifact hash, publication time, and
sanitized audit remain explicit provenance.

## Public surface

Macro has one parameterized live-fact read and one research read:

```text
GET /api/macro/evidence/{view_id}?window=30d|90d|1y|5y
GET /api/macro/research
GET /api/macro/research?session_date=YYYY-MM-DD
```

The live endpoint accepts `dashboard` plus six canonical category IDs. It reads
bounded persisted observations, preserves source/observation and received
times, emits row-local missing state, and discloses formula/window/sample for
transparent calculations. The 108 concepts and six categories are presentation
metadata, not an Agent allowlist; uncatalogued latest facts remain visible.
The endpoint makes zero provider/model calls and zero writes.

With no parameter the target is the latest completed U.S. session. An explicit
date selects that persisted session. States are `current`, `historical`,
`generating`, `failed`, and `missing`. The response may include one publication
and its bounded run state. It never calls a provider/model, resumes a graph,
searches facts, or synthesizes an older fallback.

`/macro` renders the live dashboard; six named child routes render data details.
`/macro/research` renders the persisted Chinese research document, dynamic
sections, gaps, citations, session/cutoff, reviewer notes, audit, and
generation/error state. Other Macro paths are ordinary `404`s.

## Runtime configuration

Live execution uses operator-owned `~/.parallax/config.yaml` and
`~/.parallax/workers.yaml`; `uv run parallax config` is the resolved-path
authority.

- `workers.macro_sync` owns bundle names, provider timeout, window, claim
  lease, retry cadence, and batch size.
- `workers.macro_research` owns enabled state, cadence, settle delay, statement
  timeout, lease/retry/attempt bounds, `model`,
  `model_request_timeout_seconds`, and `max_tokens`. The model request timeout
  bounds one provider transport call; the checkpointed research workflow has
  no whole-run wall-clock timeout.
- `config.yaml.llm` provides only the API key and base URL.

Credentials are reported only as redacted configured state.
