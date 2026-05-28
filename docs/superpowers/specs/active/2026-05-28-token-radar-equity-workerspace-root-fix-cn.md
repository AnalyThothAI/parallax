# Spec — Token Radar / Equity Event / WorkerSpace Root Fix

**Status**: Active
**Date**: 2026-05-28
**Owner**: Codex
**Scope note**: News similarity / story grouping is explicitly excluded. Another
thread owns News.
**Related**:
- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/references/POSTGRES_PERFORMANCE.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-performance-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-25-runtime-worker-constraint-hard-cut-cn.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- `src/gmgn_twitter_intel/domains/equity_event_intel/ARCHITECTURE.md`

## Executive Summary

多轮 SQL 优化已经把部分明显慢查询、缺索引、过宽 catch-up 扫描压下去了，
但 PostgreSQL 仍然没有根修，因为根因不是单个 SQL 的 plan，而是三条热路径仍
违反同一个 Kappa/CQRS 约束：

1. Token Radar 把会自然变化的运行时字段写进 rebuildable projection payload，
   导致同一业务事实在每轮投影里都看起来像“变了”。
2. Equity Event 把事实表当处理队列，并在空轮询时装配宽 JSON / TOAST payload，
   导致“没有新工作”也要扫描和反序列化。
3. WorkerSpace 目前主要是 manifest/import-time contract 和测试对象，生产
   `run_once()` 路径没有被强制绑定到 claim/provider/DB transaction/read-model
   writer 边界。

KISS 根修不是再加一轮更复杂的索引，而是把三类状态切开：

- Facts answer what happened.
- Control rows answer what work is due.
- Read models answer what product reads.

正常 runtime 的工作量必须与 claimed dirty targets / leased jobs 成比例。未变化
projection 必须写零 serving rows。Provider IO 必须在 DB session/transaction 外，且
payload load 必须发生在 durable claim 之后。

## Current Evidence

实时 Docker PostgreSQL 诊断确认当前运行配置来自 operator-owned runtime config：

- `config_path=/Users/qinghuan/.gmgn-twitter-intel/config.yaml`
- `workers_config_path=/Users/qinghuan/.gmgn-twitter-intel/workers.yaml`

本 spec 不复制 secret 值，只记录路径和诊断事实。

Live PostgreSQL 证据：

- `token_radar_rank_source_events`: 约 40k live rows，但 rank-source population
  的两条 `raw_requested/jsonb_to_recordset` SQL 在 fresh delta 中仍占显著 CPU。
- `equity_event_documents`: live rows 统计为 0 附近，但累计 seq/read 工作量达
  391M+ row-equivalent；当前 process 查询在无结果时仍扫描 documents。
- `equity_event_evidence_artifacts`: live rows 只有 2，但 relation total 约
  6.6GB，其中几乎全是 TOAST/history bloat。
- `events`: 约 3.2GB，其中 TOAST 约 1.4GB。
- `market_ticks_default`: 约 2.5GB。
- `pg_stat_database` temp 文件累计约 4.5GB，`pg_stat_io` 显示 client backend
  relation read time 与 WAL fsync time 都很高。

源码证据：

- Token Radar source-edge SQL 在
  `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_rank_source_query.py`
  中通过 `jsonb_to_recordset(...)` 构造 request set，并把
  `market_tick_current latest_price_tick`、`projected_at_ms`、latest price fields
  写入 `token_radar_rank_source_events`。
- Token Radar source-edge upsert 使用稳定 business key，但 `ON CONFLICT DO UPDATE`
  无 payload-diff `WHERE` gate，且每轮更新 `projected_at_ms` 和 latest market
  fields。
- `token_radar_target_features` 已有 `payload_hash` no-op gate，但
  `_target_feature_hash(...)` 只排除了顶层 `last_scored_at_ms/created_at_ms/updated_at_ms`，
  没排除 nested `factor_snapshot_json.provenance.computed_at_ms`。
- `token_radar_current_rows` 已有 publication signature no-op 形状，但
  `_payload_hash(...)` / generation signature 仍会吃到完整 factor snapshot；如果不
  canonicalize nested freshness，current row publication 仍会被污染。
- Equity Event process worker 先调用
  `list_event_documents_for_processing(...)`，离开 session 后再处理；该查询的
  `FOR UPDATE OF documents SKIP LOCKED` 锁在 session 结束时释放，不是 durable claim。
- worker PostgreSQL 连接默认 autocommit；多处 `commit=False` 只是延迟 helper 内部
  commit，并不自动构成事务。Process persist 阶段如果不用 `unit_of_work()`，可能部分写入。
- `list_event_documents_for_processing(...)` 选择 `documents.*`、
  `provider.raw_payload_json`，并 lateral 聚合全部 `evidence_artifacts`。
- `replace_evidence_artifacts(...)` 先按 `event_document_id` 删除，再插入包含
  `content_text/content_json` 的宽 artifact，天然产生 TOAST churn。
- `upsert_provider_document(...)` 先 `SELECT *`，再无 no-op `WHERE` gate 地更新
  `raw_payload_json/fetched_at_ms`。
- `WorkerSpace` 和 `CurrentReadModelPublisher` 已存在，但 `WorkerBase` 仍直接持有
  raw `db`，`WorkerScheduler` 仍直接 `asyncio.create_task(worker.run())`，生产 worker
  session 仍返回完整 `RepositorySession`。
- `event_anchor_backfill_jobs.list_due(...)` 是普通 `SELECT *`，provider quote 在
  durable leased claim 前发生，属于 WorkerSpace contract 未落到生产路径的代表。
- `event_anchor_backfill` manifest 当前也未声明 provider IO / leased queue contract；
  仅靠 `queue_health_tables` 无法让 `contract_from_manifest(...)` 推出 claim discipline。

## Why Previous SQL Rounds Did Not Root-Fix

过去几轮优化主要改善了可见慢点：

- 给 broad scans 加索引或改 query shape。
- 删除部分 runtime catch-up。
- 给若干 read model 增加 payload hash gate。
- 把 Macro 的 WorkerSpace/identity/preserve-current hard-cut 做到了主路径。

这些都有效，但没有触碰这三条剩余根因：

- **Volatile payload problem**: 如果 payload 里包含“这轮几点算的”或“最新 tick 是
  哪个”，即使业务事实没变，每轮投影都会变。索引只能让更新更快，不能让 WAL 写入
  变成零。
- **Facts-as-queue problem**: 如果 worker 用事实表扫描来证明没有工作，空闲系统仍然
  消耗 CPU。索引只能让空扫描更快，不能让空扫描消失。
- **Contract-not-runtime problem**: 如果 WorkerSpace 只是测试 contract，生产 worker
  仍可绕过 claim/provider/read-model 边界。架构规则靠自律，下一轮改动还会重新引入
  同类问题。

结论：根修必须改状态边界和写入语义，不是再堆索引。

## First Principles / KISS Rules

1. Facts are material truth, not work queues.
2. Work queues are narrow control rows with lease, attempt, payload hash, and terminal reason.
3. Rebuildable read models have exactly one runtime writer.
4. Current read-model identity must use product/window keys only, never run/generation/attempt/timestamp/UUID.
5. Freshness timestamps can live in publication/job state; they must not decide whether serving payload changed.
6. Hot paths rank/filter/claim from scalar columns; wide JSON/TOAST loads happen only after exact IDs are claimed.
7. Provider IO happens outside DB sessions and outside DB transactions.
8. Missed `NOTIFY` is repaired by bounded interval claim or explicit ops repair, not by broad fact scans.
9. No compatibility branch for old runtime behavior. The old path is removed or turned into an explicit one-shot ops repair.

## Goals

- G1. Make Token Radar source-edge and target-feature writes zero-write when business payload is unchanged.
- G2. Separate Token Radar source-edge projection from latest market context.
- G3. Replace Equity Event process fact-table polling with durable process jobs.
- G4. Remove raw provider payload and broad evidence artifact aggregation from Equity Event process/page hot paths.
- G5. Stop wide evidence-artifact delete/insert churn; keep only stable, document-scoped artifacts in hot storage.
- G6. Wire WorkerSpace into production worker execution for the P0/P1 worker classes touched by this spec.
- G7. Enforce claim-before-payload, provider-outside-transaction, and current-read-model writer identity at runtime, not only tests.
- G8. Hard reset affected derived/control tables after migration; no dual readers and no old compatibility code.

## Non-goals

- N1. Do not handle News similarity/story grouping in this spec.
- N2. Do not hide CPU by increasing worker intervals or lowering concurrency as the primary fix.
- N3. Do not build a generic framework larger than the current service needs.
- N4. Do not preserve old derived rows, old artifact blobs, or old process states for compatibility.
- N5. Do not change Token Radar scoring meaning, Equity Event product meaning, or frontend surface contracts beyond removing accidental raw-payload dependencies.
- N6. Do not claim all PostgreSQL performance work is complete after this; `events`, `market_ticks`, and API health aggregation still need their own lifecycle passes.

## Root Cause 1 — Token Radar Volatile Projection Writes

### Current Shape

`TokenRadarProjectionWorker` claims dirty targets and calls
`TokenRadarProjection.rebuild_dirty_targets(...)`. The source-edge population query:

- expands request JSON through `jsonb_to_recordset(...)`;
- joins intent/resolution/event/account/profile/market tables;
- joins `market_tick_current` for latest price context;
- inserts/upserts `token_radar_rank_source_events`;
- updates `projected_at_ms` and latest-market columns on every conflict.

The current projection also treats every claimed target the same: source-affecting and
market-only claims both go through `populate_edges_for_requests(...)`. The dirty-target
table is keyed by `(target_type_key, identity_id)`, so a single string `dirty_reason`
can be overwritten by later enqueue calls. Generic dirty-target payload hashes also
include `dirty_at_ms`, which makes repeated equivalent enqueue operations look changed.

The source-edge table has a stable key, but its payload is not stable. It combines:

- source fact fields;
- resolution and identity fields;
- event-anchor market fields;
- latest market fields;
- projection run timestamp.

This turns `token_radar_rank_source_events` into a hybrid of:

- rebuildable source-edge cache;
- latest market cache;
- run audit.

That hybrid violates Kappa/CQRS because source edges should change only when their
source facts, resolution, identity, or event-anchor context changes.

### Why `jsonb_to_recordset` Is A Symptom

`jsonb_to_recordset` shows up because the query is large and frequent. But the deeper
problem is not that request JSON exists. The deeper problem is that the projection has
to do this work repeatedly because unchanged source edges are still rewritten.

KISS answer:

- Keep request expansion if it remains convenient.
- Make the request batch smaller only after write semantics are correct.
- Do not introduce a new request table unless the no-op gates still leave this SQL hot.

### Required Design

Split Token Radar runtime state into two independent packets:

1. **Source edge packet**
   - identity: `(projection_version, window, scope, lane, target_type_key, identity_id, source_kind, source_id)`
   - payload: source fact, intent, resolution, author/account, identity, event-anchor market snapshot
   - excludes: `projected_at_ms`, latest market current fields, worker run ids, generation ids
   - has: `source_payload_hash`
   - manifest identity must match the SQL conflict key; do not declare `intent_id` as
     an identity column unless it is also part of the physical uniqueness key

2. **Target scoring packet**
   - input: stable source edges plus target-level market context loaded once per target
   - output: `token_radar_target_features` and `token_radar_current_rows`
   - latest market context can affect score, but must not force source-edge rewrites

3. **Dirty target packet**
   - carries unioned dirty kinds such as `source_dirty`, `market_dirty`, and
     `repair_dirty`, or an equivalent `dirty_kinds_json`
   - coalescing does set union, not last-write-wins reason overwrite
   - payload hash excludes `dirty_at_ms`, lease fields, attempt fields, and updated time

### Token Radar Hard-Cut Requirements

- TR1. Add a canonical source-edge payload hash over source-edge business columns.
- TR2. Add `ON CONFLICT ... DO UPDATE ... WHERE source_payload_hash IS DISTINCT FROM excluded.source_payload_hash`.
- TR3. `projected_at_ms` is not part of the source-edge payload hash and is updated only when source payload changes.
- TR4. Latest market current fields are removed from source-edge payload semantics. They may be dropped from the table in the same hard cut, or left unused for one migration if immediate drop is risky, but no runtime branch may depend on them.
- TR5. Dirty-target reasons must distinguish source-affecting changes from market-only changes.
- TR6. Market-only dirty targets must recompute target features/current rows without repopulating source edges.
- TR7. `_target_feature_hash(...)`, current-row `_payload_hash(...)`, and
  `stable_generation_id(...)` must share a canonicalizer that excludes freshness-only
  nested fields such as `factor_snapshot_json.provenance.computed_at_ms`.
- TR8. Public `factor_snapshot_json.provenance.computed_at_ms` may remain in the product payload because the factor contract currently requires it, but it must not decide no-op/change status.
- TR9. `token_radar_current_rows` generation signature must be based on business payload, not publication time.
- TR10. Second run over identical facts must write zero source-edge rows, zero target-feature rows, and zero current rows; publication state may update readiness metadata only.
- TR11. Dirty-target coalescing must preserve source and market dirty kinds by union.
  A later market-only enqueue must not erase a pending source rebuild.
- TR12. Dirty-target payload hash must not include `dirty_at_ms` or any lease/attempt
  field; it represents business input state, not enqueue time.
- TR13. `token_radar_rank_source_events` manifest identity must match the runtime
  conflict key. The recommended hard cut is to remove `intent_id` from the declared
  identity unless the SQL key is intentionally widened.
- TR14. Wall-clock market freshness fields such as `market.readiness.latest_status`
  must be explicitly classified. If they are excluded from payload hashes, stale
  degradation must be driven by bounded recalculation policy; if included, they must
  not create unbounded timer-only row churn.

### Token Radar Migration / Reset

No compatibility:

1. Add `source_payload_hash` and any needed narrow scalar columns.
2. Remove runtime use of latest-market columns from source-edge assembly.
3. Truncate rebuildable Token Radar projection caches:
   - `token_radar_dirty_targets`
   - `token_radar_rank_source_events`
   - `token_radar_target_features`
   - `token_radar_current_rows`
   - affected `token_radar_publication_state` rows if generation signatures are incompatible
4. Seed bounded dirty targets through explicit ops repair or startup migration helper.
5. Rebuild current rows once.
6. Drop obsolete source-edge latest-market columns once the hard-cut path is live.

## Root Cause 2 — Equity Event Facts-As-Queue + Wide TOAST Path

### Current Shape

`EquityEventProcessWorker` currently does:

1. Open worker session.
2. `list_event_documents_for_processing(limit=...)`.
3. Close session.
4. Process returned documents in Python.
5. Reopen session per document and persist facts/read-model dirty targets.

The repository method:

- scans `equity_event_documents`;
- joins `equity_provider_documents`;
- selects `provider.raw_payload_json`;
- lateral-aggregates all evidence artifacts into JSON;
- uses `FOR UPDATE ... SKIP LOCKED`.

Because the session closes before processing, that row lock is not the claim. It only
protects the select statement. There is no durable running state, lease owner, attempt
token, or terminal evidence for the process phase.

There is a second correctness issue hidden behind the same shape: worker-pool
connections are autocommit by default. In the process persist block, a sequence of
repository calls with `commit=False` is not automatically transactional unless wrapped
in `repos.unit_of_work()` or an explicit transaction. A crash or exception can leave
company events, spans, candidates, document status, dirty targets, and process state
partially written.

### Current TOAST Problem

`equity_event_evidence_artifacts` is tiny logically but huge physically. The reason is
write pattern, not live row count:

- hydration stores wide `content_text` and `content_json`;
- schema/history allow `companyfacts` artifacts and old rows may contain very large
  provider-shaped JSON; current bloat should be attributed to wide artifact payloads
  and historical write pattern unless the current writer proves otherwise;
- replacing artifacts deletes all rows for a document and inserts new wide rows;
- PostgreSQL keeps old TOAST chunks until vacuum can reclaim them, and file size does
  not shrink without a rewrite/repack.

This is why SQL/index optimization did not shrink the table. The storage pattern has
to change first.

### Required Design

Introduce a process control plane:

- `equity_event_process_jobs`
  - key: `event_document_id`
  - status: `pending`, `running`, `done`, `failed_retryable`, `failed_terminal`
  - lease: `lease_owner`, `leased_until_ms`
  - attempts: `attempt_count`, `max_attempts`
  - idempotency: `input_payload_hash`
  - timing: `due_at_ms`, `started_at_ms`, `finished_at_ms`, `created_at_ms`, `updated_at_ms`
  - terminal evidence: `last_error`, `terminal_reason`
  - indexes: due partial index for pending/retryable jobs and running partial index
    for stale-lease expiry

Process worker flow:

1. Expire stale running jobs.
2. Claim due process jobs with `UPDATE ... RETURNING ... FOR UPDATE SKIP LOCKED` style leased transition.
3. Commit claim.
4. Load exact processing packets by claimed `event_document_id`.
5. Close DB session.
6. Run deterministic classification/fact extraction.
7. Open DB session.
8. Persist material facts, dirty targets, and job completion inside one explicit
   `unit_of_work()`.
9. Mark jobs done/failed with the same lease owner, attempt token, and
   `input_payload_hash`.

### Equity Processing Packet

The process packet must be narrow and explicit:

- `equity_event_documents` scalar normalized fields:
  - `event_document_id`
  - `provider_document_id`
  - `company_id`
  - `ticker`
  - `cik`
  - `source_id`
  - `source_role`
  - `document_type`
  - `form_type`
  - `accession_number`
  - `fiscal_period`
  - `document_url`
  - `event_time_ms`
  - `discovered_at_ms`
  - `content_hash`
  - `evidence_status`
  - `evidence_reason`
  - `evidence_ready_at_ms`
  - normalized title/summary/filing fields required by `classify_equity_event(...)`
- evidence artifacts selected by exact `event_document_id`, with only:
  - `evidence_artifact_id`
  - `artifact_kind`
  - `source_url`
  - `content_hash`
  - `excerpt_text`
  - small `content_text` only if actually consumed by fact extraction
  - no giant companyfacts JSON

Raw provider payload is not a process/page/public projection packet field. Evidence
hydration may still read raw provider payload after a durable evidence-job claim and by
exact document/job id. If the classifier needs a provider title, filing date, accession
number, or summary, normalize it into `equity_event_documents` at fetch time.

### Evidence Artifact Hard-Cut

Current `replace_evidence_artifacts(...)` must be replaced by idempotent upsert. The
existing code already has stable-looking artifact IDs; the hard cut is not inventing
identity from scratch, it is adding content hashing and no-op semantics:

- Stable artifact id from `(event_document_id, artifact_kind, source_url/content_hash)`.
- `artifact_payload_hash` over small artifact fields.
- `ON CONFLICT ... DO UPDATE ... WHERE artifact_payload_hash IS DISTINCT FROM excluded.artifact_payload_hash`.
- Delete stale artifacts only by comparing stable artifact ids after successful hydration, not delete-all-first.

Companyfacts payload handling:

- Recommended hard cut: do not store SEC companyfacts raw JSON in per-event evidence
  artifacts going forward.
- If companyfacts is still product-required, store it in a separate company/CIK cache:
  `equity_companyfacts_cache(cik, provider, payload_hash, fetched_at_ms, normalized_json)`
  with its own lifecycle. Event artifacts reference cache metadata, not duplicate the raw blob.
- Do not keep both old per-event companyfacts artifact and new cache reader.

### Provider Document Upsert Hard-Cut

`upsert_provider_document(...)` must become idempotent:

- Select only existing identity/hash columns, not `SELECT *`.
- Use `ON CONFLICT ... DO UPDATE ... WHERE payload_hash/document_url/company/ticker/cik IS DISTINCT FROM ...`.
- Do not update `fetched_at_ms` and `raw_payload_json` when payload hash is unchanged.
- If fetch freshness needs tracking, put it in fetch-run/source health state, not by rewriting the raw provider document row every poll.

### Equity Hard-Cut Requirements

- EE1. `EquityEventProcessWorker` never scans `equity_event_documents` to discover work.
- EE2. Empty process loop reads only the process-job claim index and returns without joining provider documents or artifacts.
- EE3. Process jobs are durable and leased; another worker cannot process the same document while the lease is valid.
- EE4. Payload load requires claimed `event_document_id`s and cannot be called with an empty/unclaimed worker space.
- EE5. `FOR UPDATE SKIP LOCKED` used only inside durable claim transitions, not as an ephemeral select lock.
- EE6. Raw provider payload is removed from process/page hot paths.
- EE7. Evidence artifact writes are stable upserts with payload hashes, not delete/insert replacement.
- EE8. New writes do not store companyfacts raw JSON in per-event artifact hot storage;
  if product-required, companyfacts moves to one company-level cache.
- EE9. Existing oversized artifact storage is hard reset after the new path is deployed; no compatibility reader keeps old blobs alive.
- EE10. Page/query code reads normalized facts/read models, not provider raw payloads.
- EE11. Process persist is atomic: facts, spans, candidates, document status, dirty
  targets, and process-job completion commit or roll back together.
- EE12. `equity_event_process` manifest, queue health, `docs/WORKERS.md`, and
  architecture tests declare it as a leased-job consumer of `equity_event_process_jobs`.

### Equity Migration / Reset

No compatibility:

1. Add `equity_event_process_jobs`.
2. Add normalized document fields required by classifier/process packet.
3. Replace event-document process discovery with process-job enqueue.
4. Replace `replace_evidence_artifacts(...)` with stable artifact upsert.
5. Stop future companyfacts raw JSON writes into per-event artifacts.
6. Truncate/rebuild derived or oversized tables as needed:
   - `equity_event_evidence_artifacts`
   - `equity_event_source_spans`
   - `equity_event_fact_candidates`
   - process lifecycle fields or process jobs for current documents
7. Re-enqueue process jobs for current event documents whose evidence is terminal.
8. Run `VACUUM FULL`/`pg_repack`/table rewrite only after write pattern is fixed.

## Root Cause 3 — WorkerSpace Contract Not On Production Execution Path

### Current Shape

`WorkerSpace` already has the right conceptual pieces:

- `WorkerSpaceContract`
- claim discipline
- provider IO contract
- current read-model contract
- `db_transaction()`
- `provider_io()`
- `mark_claimed(...)`
- `require_claim_before_payload_load()`

But production workers are not forced through it:

- `WorkerBase` stores raw `db`.
- `run_once()` is an abstract method with no `WorkerSpace` argument.
- `WorkerScheduler` starts worker tasks directly.
- `DBPoolBundle.worker_session(...)` returns a full `RepositorySession`.
- Most repository methods have no knowledge of worker ownership, claim state, or read-model writer identity.
- Some manifests do not yet describe the runtime truth needed by WorkerSpace. For
  example `event_anchor_backfill` needs provider IO plus a leased queue contract, and
  `equity_event_process` must become a leased-job consumer once `equity_event_process_jobs`
  exists.

So WorkerSpace currently proves that manifest declarations are sane, but does not
prevent a worker from:

- loading payload before claim;
- calling a provider inside an open DB session;
- writing another worker's read model;
- delete/reinserting current rows without a stable hash;
- using a fact table as a runtime queue.

### Required Design

Keep WorkerSpace small. Do not build a dependency injection framework. Add one runtime
context object and route worker operations through it.

Proposed runtime API:

```python
class RuntimeWorkerContext:
    worker_name: str
    space: WorkerSpace

    def claim_session(self) -> ContextManager[WorkerRepositories]: ...
    def payload_session(self) -> ContextManager[WorkerRepositories]: ...
    def persist_session(self) -> ContextManager[WorkerRepositories]: ...
    def provider_io(self) -> ContextManager[None]: ...
    def mark_claimed(self, count: int) -> None: ...
    def require_claimed_payload(self) -> None: ...
    def current_publisher(self, table_name: str) -> CurrentReadModelPublisher: ...
```

Minimal production wiring:

- Worker factory builds `WorkerSpaceContract` from manifest.
- `WorkerBase` receives `runtime_context` or `worker_space_contract`.
- `WorkerBase._create_run_once_task()` wraps each iteration with a fresh `WorkerSpace`.
- `DBPoolBundle.worker_session(...)` is still the low-level primitive, but P0/P1 workers touched by this spec must use context methods.
- Architecture tests ban direct raw `self.db.worker_session(...)` in those workers after migration.

### Worker-Scoped Repository Access

KISS version:

- Do not generate many repository subclasses.
- Add a thin facade that blocks only high-risk writes:
  - current read model writes not declared in manifest;
  - provider payload load before claim for claimed workers;
  - provider IO while DB session depth or DB transaction depth is nonzero.
- Keep read methods available unless they load wide payloads; wide payload loads require explicit context method names such as `load_claimed_process_packets(...)`.

This avoids a large framework while making the important violations impossible on the
hot paths.

### WorkerSpace Hard-Cut Requirements

- WS1. `WorkerBase` production iterations create a fresh `WorkerSpace` from the manifest contract.
- WS2. Claimed workers must call `space.mark_claimed(count=...)` before any payload loader.
- WS3. Payload-loader repository methods used by P0/P1 workers must call
  `space.require_claim_before_payload_load()`.
- WS4. Provider IO must be wrapped in `space.provider_io()` and must fail if any DB
  session or transaction guard is active. Transaction-depth-only checks are insufficient.
- WS5. Current read-model writes for P0/P1 workers must go through `CurrentReadModelPublisher` or an equivalent table-specific wrapper that enforces stable identity and no-op hash semantics.
- WS6. `token_radar_projection`, `equity_event_process`, `equity_event_evidence_hydration`,
  `equity_event_fetch`, and `event_anchor_backfill` are the first enforcement set.
- WS7. `event_anchor_backfill` must claim leased jobs before provider quote calls.
- WS8. `event_anchor_backfill` manifest must declare provider IO and
  `queue_depth_table="event_anchor_backfill_jobs"` after the lease hard cut.
- WS9. `equity_event_process` manifest must declare `equity_event_process_jobs` as
  control-plane/queue ownership after the process queue hard cut.
- WS10. Evidence hydration payload loaders, including `load_evidence_hydration_input(...)`,
  must be guarded by claim token, lease owner, and attempt count.
- WS11. Old helper paths that accept raw repositories and bypass WorkerSpace are removed
  or marked test-only; production code has no dual path. This includes raw
  event-document process discovery helpers such as `list_event_documents_for_processing(...)`
  and any legacy `list_unprocessed_event_documents(...)` equivalent.

## Cross-Cutting Architecture Changes

### Dirty Reasons

Dirty/control rows must say why work is needed:

- source-fact changed;
- resolution changed;
- identity changed;
- event-anchor market context changed;
- latest market changed;
- evidence ready;
- process failed retryable;
- explicit ops repair.

This lets Token Radar skip source-edge repopulation on market-only changes and lets
Equity Event enqueue process jobs only when evidence/document inputs are terminal.
For Token Radar specifically, dirty kind must be a unioned set or explicit booleans,
not one overwriteable reason string.

### Payload Hashes

Every hot derived/control row touched by this spec must have a content hash with clear
rules:

- Include business inputs and product-visible outputs.
- Exclude run ids, generation ids, attempt ids, lease owners, updated timestamps,
  publication timestamps, enqueue timestamps such as `dirty_at_ms`, and
  freshness-only nested fields.
- Use SHA-256 canonical JSON.
- Tests must pin a same-input second run as no-op.

### Narrow Hot Tables

Hot queue/read-model tables should stay scalar:

- identity columns;
- status/lease/attempt columns;
- payload hash;
- due/updated timestamps;
- small scores and product fields.

Wide provider JSON belongs in cold source caches with explicit lifecycle, not in every
poll/projection/process loop.

## Implementation Plan

### Phase 1 — Token Radar Write Stability

1. Add source-edge payload hashing.
2. Remove latest market fields from source-edge write semantics.
3. Add no-op `WHERE` gate to source-edge conflict update.
4. Canonicalize target-feature hash, current-row payload hash, and generation signature
   to exclude nested freshness-only fields.
5. Split source-affecting dirty kinds from market-only dirty kinds with union semantics.
6. Remove enqueue timestamps from dirty-target payload hashes.
7. Reset/rebuild Token Radar dirty targets and projection caches.
8. Add tests proving identical second run writes zero rows.

### Phase 2 — Equity Event Process Queue + Narrow Payload

1. Add `equity_event_process_jobs`.
2. Enqueue/reset process job when event document evidence reaches terminal state.
3. Replace `list_event_documents_for_processing(...)` with leased job claim.
4. Add exact-ID process packet loader.
5. Normalize classifier-needed raw provider fields into `equity_event_documents`.
6. Remove raw provider payload from process packet and page query.
7. Wrap process persist in explicit `unit_of_work()`.
8. Update worker manifest, queue health, docs, and architecture tests for the process queue.
9. Add tests for empty queue, double worker claim, stale lease expiry, atomic persist, and retry terminalization.

### Phase 3 — Evidence Artifact Storage Hard-Cut

1. Replace delete/insert artifact replacement with stable upsert.
2. Stop writing companyfacts raw JSON into per-event artifacts.
3. Add optional companyfacts cache only if current product actually consumes it.
4. Truncate/rebuild old oversized artifacts.
5. Run storage reclaim after the new write pattern is live.

### Phase 4 — WorkerSpace Runtime Enforcement

1. Build `RuntimeWorkerContext` around existing `WorkerSpace`.
2. Inject per-iteration WorkerSpace from manifest contract.
3. Convert Token Radar projection and Equity/Event Anchor workers to context sessions.
4. Track DB session depth as well as transaction depth for provider IO guards.
5. Fix enforcement-set manifest declarations, including `event_anchor_backfill` and
   `equity_event_process`.
6. Add architecture tests banning direct raw session/provider bypass in enforcement set.
7. Route current read-model writes through shared publisher or table-specific equivalent.
8. Remove production compatibility helpers.

## Acceptance Criteria

### Token Radar

- AC-TR1. `token_radar_rank_source_events` upsert has a payload-hash no-op gate.
- AC-TR2. Latest market-only updates do not rewrite source-edge rows.
- AC-TR3. `projected_at_ms` does not make an unchanged source edge dirty.
- AC-TR4. Same facts, same dirty target, second projection run writes zero source-edge rows.
- AC-TR5. Same facts, same score payload, second projection run writes zero target-feature rows.
- AC-TR6. Same visible current rows, second publication writes zero `token_radar_current_rows`.
- AC-TR7. `factor_snapshot_json.provenance.computed_at_ms` can exist in public payload but is excluded from change signatures.
- AC-TR8. `pg_stat_statements` no longer shows rank-source population as a top CPU consumer under idle/steady-state dirty-target replay.
- AC-TR9. Market-only dirty targets skip rank-source population and preserve existing source edges.
- AC-TR10. Source and market dirty kinds coalesce by union; later market-only enqueue cannot erase source rebuild.
- AC-TR11. `token_radar_dirty_targets` payload hash excludes `dirty_at_ms`.
- AC-TR12. `token_radar_rank_source_events` manifest identity matches its physical/runtime uniqueness key.

### Equity Event

- AC-EE1. `EquityEventProcessWorker` claims `equity_event_process_jobs` before loading documents.
- AC-EE2. Empty process loop does not scan/join `equity_event_documents`, `equity_provider_documents`, or `equity_event_evidence_artifacts`.
- AC-EE3. Process claim persists lease owner, lease deadline, attempt count, and input payload hash.
- AC-EE4. Two workers cannot claim the same process job while lease is valid.
- AC-EE5. Raw provider payload is not selected by process packet or page read methods.
- AC-EE6. Artifact writer uses stable upsert plus payload hash, not delete-all replace.
- AC-EE7. Companyfacts raw JSON is not duplicated per event artifact.
- AC-EE8. Old oversized artifact rows are hard reset and physical storage reclaim is scheduled after deploy.
- AC-EE9. Existing product facts/read models are rebuilt from normalized documents and artifacts.
- AC-EE10. Process persist uses an explicit transaction so facts, spans, candidates,
  document status, dirty targets, and process-job completion are atomic.
- AC-EE11. Process job finish/fail updates are guarded by status, lease owner,
  attempt count, and `input_payload_hash`.
- AC-EE12. Evidence hydration can read provider raw payload only after exact durable
  evidence-job claim; process/page/public projection cannot.
- AC-EE13. `equity_event_process` manifest and queue-health docs declare
  `equity_event_process_jobs`.

### WorkerSpace

- AC-WS1. Production worker iterations have a fresh WorkerSpace contract.
- AC-WS2. Claim-first workers fail if payload is loaded before `mark_claimed(count>0)`.
- AC-WS3. Provider IO fails if attempted inside a DB transaction/session guard.
- AC-WS4. P0/P1 current read-model writers use stable identity and payload-hash no-op semantics.
- AC-WS5. `event_anchor_backfill` provider calls happen only after leased job claim.
- AC-WS6. Architecture tests cover production worker paths, not only standalone WorkerSpace unit behavior.
- AC-WS7. No production compatibility path can bypass WorkerSpace for the enforcement set.
- AC-WS8. Provider IO guard tracks DB session depth, not only explicit transaction depth.
- AC-WS9. Enforcement-set manifests describe provider IO and queue/control ownership accurately.

### PostgreSQL / Ops

- AC-PG1. Re-run live diagnostic after deployment shows no repeated empty scan from Equity process.
- AC-PG2. Token rank-source SQL is not a top steady-state CPU query when no source facts changed.
- AC-PG3. `equity_event_evidence_artifacts` TOAST stops growing after repeated hydration runs.
- AC-PG4. After reset/repack, artifact table physical size reflects live data order of magnitude.
- AC-PG5. WAL/fsync pressure drops in idle steady-state because unchanged projections write zero rows.

## Test Plan

Unit tests:

- Canonical Token source-edge hash excludes `projected_at_ms` and latest-market fields.
- Canonical Token target-feature hash, current-row hash, and generation signature exclude nested freshness-only fields.
- Token dirty-target coalescing preserves both source and market dirty kinds.
- Equity process job claim transitions pending -> running with lease/attempt.
- Equity stale running jobs expire/retry/terminalize correctly.
- Evidence artifact upsert skips unchanged payload.
- Provider document upsert skips unchanged raw payload.

Integration tests with PostgreSQL:

- Token projection same input twice: second run has zero rows written in source edges,
  target features, and current rows.
- Token market-only dirty target: target features/current rows may change; source edges do not.
- Token source+market coalesced dirty target: source rebuild still runs once and market context recomputes once.
- Equity process empty queue: no scan of document/provider/artifact payload path.
- Equity process two-worker race: one claim wins; the other sees no due job.
- Equity process packet loader rejects unclaimed IDs.
- Equity process persist failure rolls back facts, dirty targets, and job completion together.
- Evidence hydration same artifact twice: second run does not rewrite TOAST payload.
- Event Anchor backfill two-worker race: provider quote called only by claimed worker.

Architecture tests:

- Enforcement-set workers do not call raw `self.db.worker_session(...)` directly.
- Enforcement-set provider calls are inside `runtime_context.provider_io()`.
- Enforcement-set payload loaders call `require_claim_before_payload_load()`.
- Enforcement-set manifests expose provider IO and queue/control ownership used by WorkerSpace.
- Current read-model identity declarations reject lifecycle columns.

Operational verification:

- Capture `pg_stat_statements` before/after for Token rank-source and Equity process SQL.
- Capture table size before/after for `equity_event_evidence_artifacts`.
- Confirm no active blockers, no long transactions, and no temp-file bursts from these paths.
- Confirm live config paths are operator-owned `~/.gmgn-twitter-intel/*`.

## Rollout Plan

1. Ship Token Radar write-stability hard cut first because it directly reduces repeated
   projection/WAL work and is mostly local to Token Radar.
2. Ship Equity process queue and narrow packet next because it removes idle broad scans
   and prepares storage cleanup.
3. Ship evidence artifact storage hard cut and table reset/reclaim.
4. Ship WorkerSpace runtime enforcement for the P0/P1 enforcement set.
5. Re-run live diagnostics and update `docs/references/POSTGRES_PERFORMANCE.md` with
   observed deltas.

If Phase 4 can be landed in parallel safely, do it for new code only; do not block the
Token/Equity hot-path fixes on a whole-repo WorkerSpace conversion.

## Open Decisions

1. Companyfacts: recommended decision is to stop writing companyfacts raw JSON into
   per-event artifacts. Add a separate companyfacts cache only when a product surface
   proves it needs companyfacts; do not preserve old artifact-reader compatibility.
2. Token source-edge latest-market columns: recommended decision is to drop them in the
   same hard cut if migrations are acceptable; otherwise leave columns unused for one
   release and drop immediately after verification. Do not keep runtime compatibility
   branches.
3. WorkerSpace facade width: recommended decision is a thin facade for the enforcement
   set, not a generated repository-per-worker framework.

## Done Definition

This spec is done when:

- Token Radar unchanged rebuilds write zero hot rows.
- Equity Event idle process loop is proportional to due process jobs, not documents.
- Equity Event process persist is atomic under autocommit worker connections.
- Wide evidence artifact TOAST churn is stopped and old bloat has a reclaim plan.
- WorkerSpace violations are impossible in the enforcement-set production paths,
  including provider IO inside open DB sessions.
- No old compatibility readers/writers remain for the cut-over paths.
