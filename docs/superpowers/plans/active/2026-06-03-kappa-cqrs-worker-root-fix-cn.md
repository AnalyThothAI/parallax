# Kappa/CQRS Worker Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治全 worker 审计发现的 Kappa/CQRS 漂移：真实 provider 协议错配、current read model unchanged 写入、无生产者 dirty queue、非持久 claim、idle broad scan、静默 disabled worker、以及半应用 runtime 抽象。

**Architecture:** 采用 hard-cut，不保留旧 runtime/compat path。先补架构测试和运行时可观测护栏，再按独立业务链路修 CEX、News、Token Radar/Capture、Narrative/Macro，最后移除或统一 WorkerSpace/allowlist 并同步 docs。所有改动遵循单一职责：provider adapter 在 provider wiring，claim/retry 在 repository，current-row publication 在 read-model repository，worker 只负责编排一个 `run_once`。

**Tech Stack:** Python 3.13, psycopg 3, PostgreSQL/Alembic, FastAPI runtime status, pytest unit/integration/architecture, ruff/mypy, `make check-all`.

---

## Detailed Summary

本轮审计确认系统的大方向是对的：事实入 PostgreSQL、read model 单 writer、wake 只是 hint、worker manifest 是 runtime inventory。但是几个局部已经偏离到会产生真实运行风险。

最硬的 P1 是 CEX provider wiring。`cex_oi_radar_board` 当前拿到的是 generic `CexMarketProvider`，真实 wrapper 只实现 `tickers/ticker/candles`，但 CEX OI builder 调用的是 raw Binance client 方法 `ticker_24hr/premium_index/open_interest_hist`。测试 fake provider 刚好长得像 worker 私有假设，所以没抓到。这个必须通过 domain-specific CEX OI adapter hard-cut 解决，而不是给 wrapper 偷偷加透传方法。

第二类是 current read model zero-write 破坏。CEX detail snapshots 在 board hash gate 前先写，Narrative admissions 每轮 timestamp rewrite，discussion digest 非 ready status 会被周期性 delete/insert。Token Radar 的 `generation_id` 本身不是问题，因为 repository 已经用 stable signature unchanged skip；真正的问题是 target edge repair 写入窗口和读取窗口不一致。

第三类是 worker 控制面不完整。`news_item_process` 没有持久 claim/lease/retry due，失败项可热循环；`token_capture_tier_dirty_targets` 有 consumer 没有 producer；`macro_sync` idle enqueue 前读取 facts 聚合；enabled worker 可以因为 provider/feature gate 缺失被静默替换成 disabled sentinel。结果是状态面不诚实，dirty queue 不能代表实际链路，运行时成本也不可控。

第四类是 KISS/单一职责债。`WorkerSpace` 是复杂抽象，但只应用在 Token Radar 和 Event Anchor；`LivePriceGateway` 特例 override `WorkerBase.run()`；worker factories 直接 import 第三方 client；几个 repository 混合 claim、projection、diagnostics、read query。这个 plan 不做全仓库风格重构，只在本次触碰的路径把责任拆清楚。

### Second-pass audit corrections

子 agent 复核结论：本 plan 的根因方向成立，但直接执行前必须收紧以下点，否则会把 root fix 做成新一层复杂度或半兼容路径。

- **Migration 必须按 PR/domain 拆分。** 不再使用单个跨 CEX、News、Narrative、Macro 的 `20260603_0142` migration。每个 schema PR 自带独立 revision、独立 DDL/backfill/verification，并在该 PR 合并时通过项目入口 `uv run parallax db migrate` 应用。已发布 migration 不允许被后续 PR 继续修改。
- **PR 必须独立 mergeable。** PR1 只实现 runtime availability/status 它自己能修好的 guardrail；CEX provider import tests、`live_price_gateway` run override tests、WorkerSpace 删除 tests 分别跟对应 PR 走，避免先加会失败的未来测试。
- **Worker availability 要区分四种状态。** `disabled` 是配置关闭；`intentionally_not_started` 是运行入口刻意不启动，例如 CLI ops 用 `start_collector=False`；`unavailable` 是配置启用但 provider/dependency/feature gate 缺失；`degraded` 是可运行但某个可选 capability 缺失。`collector` 的有意不启动不能被报成 unavailable。
- **CEX adapter 不能 raw-client-shaped。** CEX OI provider protocol 使用 Parallax-owned normalized DTO 和业务方法名；Binance raw 方法名只允许存在于 integration adapter 内部。测试断言 normalized shape，而不只是断言方法名。
- **CEX board/detail zero-write 要拆成同事务内两个决策。** `board_changed` 和 `detail_changed_count` 独立计算，避免 detail-only 变化重写 board，或 board unchanged 时误压 detail 更新。
- **News processed-unclassified 历史洞必须 hard-cut repair。** 新 claim 只处理 `raw/process_retryable` 前，migration/repair 必须把 `processed AND content_classification_json='{}'` 这类旧半处理事实迁回 `raw` 或 due `process_retryable`，否则会永久跳过。
- **Capture-tier dirty payload hash 必须 fingerprint rank set。** 不能只用 reason/source watermark；必须包含 target key、rank、tier-relevant score、quality、row payload hash 或 current generation identity、exited set、reason。source watermark 只能是附加 metadata。
- **WorkerSpace 删除是独立 hard-cut PR。** 方向正确，但 blast radius 大，必须列出 CLI ops、e2e/integration tests、旧 active plan/docs 的清理，并保留原来 guard 的等价测试：claim-before-payload、provider IO outside transaction、agent reservation-before-claim。
- **验收要覆盖真实 storage 和 residue grep。** Current read model zero-write 至少 CEX/Narrative 要有 real PostgreSQL integration 覆盖；AC18/AC19 要包含 WorkerSpace、News lifecycle、watchlist/account-quality stale text 的 grep 型检查。

---

## Pre-flight

- [ ] **Step 1: Create isolated worktree**

  Run from `/Users/qinghuan/Documents/code/parallax`:

  ```bash
  git worktree add .worktrees/kappa-cqrs-worker-root-fix -b codex/kappa-cqrs-worker-root-fix main
  git -C .worktrees/kappa-cqrs-worker-root-fix branch --show-current
  git -C .worktrees/kappa-cqrs-worker-root-fix status --short
  ```

  Expected:

  ```text
  codex/kappa-cqrs-worker-root-fix
  ```

  `status --short` should be empty before implementation files are edited.

- [ ] **Step 2: Confirm approved spec**

  Confirm this plan owns:

  ```text
  docs/superpowers/specs/active/2026-06-03-kappa-cqrs-worker-root-fix-cn.md
  ```

  Expected: status is `Approved`.

- [ ] **Step 3: Record redacted runtime config paths**

  Run:

  ```bash
  uv run parallax config
  ```

  Expected: output reports `config_path` and `workers_config_path`. If this is run against real data, report only paths and redacted booleans, never secret values.

- [ ] **Step 4: Record baseline gates**

  Run:

  ```bash
  uv run ruff check .
  uv run python -m pytest tests/architecture -m architecture
  uv run python -m pytest tests/unit/domains/cex_market_intel tests/unit/domains/news_intel tests/unit/domains/narrative_intel -q
  ```

  Expected: either pass, or record exact pre-existing failures before edits. This plan does not accept new failures.

---

## File-level Edits

### Runtime contracts and availability

- Modify `src/parallax/app/runtime/worker_factories/__init__.py:40-111`
  - Replace silent manifest pre-population with explicit sentinel workers:
    - `DisabledWorker` for config-disabled workers.
    - `UnavailableWorker` for config-enabled workers that a factory cannot construct.
    - `IntentionallyNotStartedWorker` or equivalent status metadata for runtime entrypoints that intentionally suppress a worker family, especially `start_collector=False`.
  - Keep `DisabledWorker` out of readiness failures.
  - Keep intentionally-not-started workers out of readiness failures and provider-unavailable counts.
  - Make `UnavailableWorker` appear in status and readiness as unavailable with redacted reason.
  - Factories may return `UnavailableWorker` for known dependency/provider gaps; unpopulated enabled workers become unavailable with reason `factory_not_constructed`.

- Modify `src/parallax/app/runtime/worker_scheduler.py:27-146`
  - Add helper `worker_effective_status(worker) -> str`.
  - Skip starting disabled, intentionally-not-started, and unavailable workers.
  - Include unavailable workers in `unhealthy_reasons()` as `worker:{name}:unavailable:{reason}`.
  - Keep stopped detection for enabled runnable workers.

- Modify `src/parallax/app/runtime/worker_base.py:24-42`
  - Extend status payload with `effective_status` and optional `unavailable_reason`.
  - Remove `worker_space_contract` from `WorkerBase.__init__` after WorkerSpace removal PR lands.

- Modify `src/parallax/app/runtime/worker_status.py`
  - Add effective-status counts per lane: `running`, `stopped`, `disabled`, `intentionally_not_started`, `unavailable`, `degraded`, and `failed`.
  - Keep `disabled` and `intentionally_not_started` separate so CLI diagnostics do not report intentional collector suppression as a provider/config fault.

- Modify `src/parallax/app/surfaces/api/schemas.py`
  - Add `effective_status`, `unavailable_reason`, and lane unavailable/degraded counts to the public status schema without exposing secrets.

- Modify `src/parallax/app/runtime/ops_diagnostics.py`
  - Stop recomputing worker health with a divergent disabled/degraded/idle heuristic.
  - Consume the same effective-status model as `/readyz`, `/api/status`, and CLI worker status.

- Modify `src/parallax/app/runtime/worker_manifest.py`
  - Keep worker inventory unchanged unless a worker is explicitly removed by this plan.
  - Ensure `live_price_gateway` remains classified as cache fanout and no longer needs a `run()` override allowlist.

- Modify `src/parallax/app/runtime/app.py:222-237`
  - Stop filtering away unavailable worker reasons.
  - Continue filtering intentionally disabled workers and pure stopped noise only where readiness already treats disabled as out of scope.

### Provider wiring and CEX OI adapters

- Create `src/parallax/domains/cex_market_intel/providers.py`
  - Define Parallax-owned DTOs and `CexOiMarketProvider` protocol with business method names:

    ```python
    @dataclass(frozen=True)
    class CexOiTicker24h:
        symbol: str
        quote_volume_24h: Decimal | None
        price_change_pct_24h: Decimal | None

    @dataclass(frozen=True)
    class CexFundingPremium:
        symbol: str
        mark_price: Decimal | None
        last_funding_rate: Decimal | None

    @dataclass(frozen=True)
    class CexOpenInterestPoint:
        symbol: str
        open_interest_value: Decimal | None
        observed_at_ms: int | None

    class CexOiMarketProvider(Protocol):
        def list_24h_tickers(self, *, symbol: str | None = None) -> Sequence[CexOiTicker24h]:
            raise NotImplementedError

        def list_funding_premium(self, *, symbol: str | None = None) -> Sequence[CexFundingPremium]:
            raise NotImplementedError

        def list_open_interest_history(
            self, *, symbol: str, period: str, limit: int
        ) -> Sequence[CexOpenInterestPoint]:
            raise NotImplementedError

        def close(self) -> None:
            raise NotImplementedError
    ```

  - Define `CoinglassDerivativesProvider` protocol with the five methods used by `coinglass_detail_enricher.py`.
  - Do not expose `ticker_24hr`, `premium_index`, `open_interest_hist`, raw response dicts, or `Any` at the domain service boundary.

- Modify `src/parallax/app/runtime/provider_wiring/types.py:1-89`
  - Add `CexMarketIntelProviders` with `oi_market` and `coinglass_derivatives`.
  - Add `cex_market_intel: CexMarketIntelProviders` to `WiredProviders`.
  - Keep `AssetMarketProviders.cex_market` as the generic quote/candle protocol.

- Create `src/parallax/app/runtime/provider_wiring/cex_market_intel.py`
  - Wire `BinanceUsdmFuturesOiProvider` from settings when Binance is enabled.
  - Wire `CoinglassDerivativesClientProvider` only when enrichment limit is positive and dependency import succeeds.
  - If `coinglass_enrichment_limit > 0` but dependency/config is missing, mark enrichment capability `degraded` with a redacted reason; do not silently pass `None`.
  - Return provider availability metadata without secret values.

- Modify `src/parallax/app/runtime/provider_wiring/binance.py:51-104`
  - Keep `BinanceUsdmFuturesMarketProvider` generic.
  - Add a separate OI provider adapter that wraps `BinanceUsdmFuturesClient` and implements `CexOiMarketProvider`.
  - Do not add raw-client pass-through methods to the generic market provider.

- Modify `src/parallax/app/runtime/provider_wiring/__init__.py:18-72`
  - Import and call `cex_market_intel.wire_cex_market_intel(settings)`.
  - Populate `WiredProviders.cex_market_intel`.

- Modify `src/parallax/app/runtime/providers_wiring.py:4-25`
  - Export `CexMarketIntelProviders`.

- Modify `src/parallax/app/runtime/worker_factories/cex_market_intel.py:13-36`
  - Replace `ctx.providers.asset_market.cex_market` with `ctx.providers.cex_market_intel.oi_market`.
  - Replace raw `coinglass_cli.client.CoinglassClient` import with `ctx.providers.cex_market_intel.coinglass_derivatives`.
  - Return `UnavailableWorker` when `settings.enabled` is true and no OI provider is available.

### CEX current read models

- Create migration `src/parallax/platform/db/alembic/versions/20260603_0142_cex_detail_payload_hash_hard_cut.py`
  - Add/backfill `cex_detail_snapshots.payload_hash`.
  - Use deterministic hashes over product-visible detail payload.
  - Enforce `NOT NULL` after backfill and use existing project conventions for lock timeout and index creation.

- Modify `src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py:100-150`
  - Build board rows and detail snapshots in memory.
  - Call a repository publication method that returns an independent decision object:
    - `board_changed: bool`
    - `board_rows_written: int`
    - `detail_changed_count: int`
    - `detail_rows_written: int`
  - Do not upsert `cex_detail_snapshots` before `publish_board()`.

- Modify `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:8-85`
  - Add product payload hash for detail snapshots.
  - Hash product fields only; explicitly exclude `computed_at_ms`, `updated_at_ms`, attempt/run metadata, and any `source_refs` timestamp derived solely from `computed_at_ms`.
  - Treat provider-observed timestamps as product payload only when they come from the provider frame and are visible as market freshness.
  - Upsert only when payload hash changes.
  - Use `ON CONFLICT ... DO UPDATE ... WHERE cex_detail_snapshots.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash`.
  - Return actual changed count from `upsert_many()`.

- Modify `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:68-110`
  - Provide the two-step decision object described above:
    - unchanged board and unchanged details writes zero serving rows;
    - changed board/details writes only changed serving rows.
  - Keep attempt metadata out of serving row identities.

- Modify `src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py:8-28`
  - Type `client` as `CexOiMarketProvider`.
  - Keep business scoring unchanged.

- Modify `src/parallax/domains/cex_market_intel/services/coinglass_detail_enricher.py:6-31`
  - Type `client` as `CoinglassDerivativesProvider | None`.
  - Keep unavailable enrichment as degraded row payload, not as worker construction failure unless the settings require enrichment.

### News item process claim/retry

- Create migration `src/parallax/platform/db/alembic/versions/20260603_0143_news_item_process_claim_hard_cut.py`
  - Add to `news_items`:

    ```sql
    ALTER TABLE news_items ADD COLUMN processing_lease_owner TEXT;
    ALTER TABLE news_items ADD COLUMN processing_leased_until_ms BIGINT;
    ALTER TABLE news_items ADD COLUMN processing_next_due_at_ms BIGINT NOT NULL DEFAULT 0;
    ALTER TABLE news_items ADD COLUMN processing_terminal_error TEXT;
    ```

  - Hard-cut statuses:

    ```sql
    UPDATE news_items
       SET lifecycle_status = 'process_retryable',
           processing_next_due_at_ms = 0
     WHERE lifecycle_status = 'process_failed';
    ```

  - Hard-cut old half-processed rows before new claim code ships:

    ```sql
    UPDATE news_items
       SET lifecycle_status = 'raw',
           processing_next_due_at_ms = 0,
           updated_at_ms = GREATEST(updated_at_ms, 0)
     WHERE lifecycle_status = 'processed'
       AND COALESCE(content_classification_json::text, '{}') = '{}';
    ```

    If migration cannot safely decide the target state for a row, enqueue/report an explicit bounded repair command before dropping the old processed-unclassified compatibility path.

  - Replace lifecycle check with allowed values:

    ```text
    raw, processing, processed, process_retryable, process_terminal_failed
    ```

  - Replace `ix_news_items_unprocessed_claim` with a claim index over `(lifecycle_status, processing_next_due_at_ms, published_at_ms, news_item_id)`.
  - Drop the old lifecycle check constraint and old unprocessed partial index explicitly before creating the replacement constraint/index.

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py:1674-1733`
  - Replace `list_unprocessed_items()` with `claim_unprocessed_items(limit, lease_owner, lease_ms, now_ms, commit=True)`.
  - Claim rows by setting `lifecycle_status='processing'`, `processing_lease_owner`, `processing_leased_until_ms`, incremented `processing_attempts`, and `updated_at_ms`.
  - Select `raw` and due `process_retryable` rows only.
  - Delete the old `processed AND empty classification` rescue predicate after the migration/repair above; do not keep it as compatibility logic.

- Modify `src/parallax/domains/news_intel/repositories/news_repository.py:1854-1940`
  - Update `mark_item_processed()` to clear lease, retry due, and errors.
  - Replace `mark_item_process_failed()` with:
    - `mark_item_process_retryable(news_item_id, error, next_due_at_ms, now_ms, commit=True)`.
    - `mark_item_process_terminal_failed(news_item_id, error, now_ms, commit=True)`.
  - Add `release_expired_processing_items(now_ms, commit=True)` that moves expired `processing` rows to `process_retryable`.

- Modify `src/parallax/domains/news_intel/runtime/news_item_process_worker.py:45-162`
  - Release expired processing rows at cycle start.
  - Claim items with `lease_owner=self.name` and worker settings `lease_ms`.
  - On exception, use `processing_attempts` and `settings.max_attempts` to choose retryable vs terminal failed.
  - Add retry delay from `settings.retry_delay_ms` or reuse `interval_seconds * 1000` if adding a new setting is not needed.

- Modify `src/parallax/platform/config/settings.py:1243-1252`
  - Add `retry_delay_ms` to `NewsItemProcessWorkerSettings` only if existing `PerWorkerSettings` cannot express the retry delay clearly.

### Token Radar, capture tier, and bounded edge repair

- Modify `src/parallax/domains/token_intel/services/token_radar_projection.py:754-792`
  - Add `_enqueue_token_capture_tier_for_rank_changes()`.
  - Enqueue global capture-tier work when default-venue publication changes any target membership or rank payload relevant to live-market targets.
  - Do not enqueue when `publish_current_generation()` returns `unchanged`.

- Modify `src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:11-67`
  - Make `payload_hash` a live-market rank-set fingerprint, not `now_ms`, reason, or source watermark alone.
  - Include target key, membership/rank, tier-relevant `rank_score`, quality flags, current row `payload_hash` or `current_generation_id`, exited set, and reason.
  - Store source watermark as metadata only; it must not be the sole identity for rank-set changes.
  - Return whether the dirty target row changed.

- Modify `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:69-181`
  - Count actual changed rows from `upsert_tier()` and `demote_hot_rows_outside_rank_set()`.
  - Return `rows_written=0` when all tier rows are unchanged.
  - Keep idle path as queue-depth-only.

- Modify `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:13-60`
  - Keep current `IS DISTINCT FROM` upsert gate.
  - Make `demote_hot_rows_outside_rank_set()` return actual changed row count if it does not already.

- Modify `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:121-147`
  - Change `populate_edges_for_targets()` signature to accept `analysis_since_ms`.
  - Add `events.received_at_ms >= %s` to `_POPULATE_RANK_SOURCE_EDGES_FOR_TARGETS_SQL`.
  - Keep stale-edge delete scoped to the same bounded repair window, including `stale_edges.event_received_at_ms >= analysis_since_ms`, so old edges outside retention are handled by prune, not per-target full-history repair.

- Modify `src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py:48-59`
  - Pass `analysis_since_ms`.

- Modify `src/parallax/domains/token_intel/services/token_radar_projection.py:187-195`
  - Compute repair lower bound from the maximum configured Token Radar analysis window plus safety margin.
  - Cover the existing 24h projection needing 48h lookback plus margin; do not derive the bound from display window alone.
  - Pass it to `populate_edges_for_targets()`.

- Add explicit repair/backfill enqueue path
  - Add a small CLI/ops command or existing ops subcommand action that enqueues bounded `token_capture_tier_dirty_targets` for current default-venue Token Radar rows.
  - The command reports target count, reason, fingerprint, bounded window, and skipped/no-op count.
  - This is required for live systems that already have current Token Radar rows but will not emit a new publication delta immediately after the hard cut.

### Narrative current read models

- Create migration `src/parallax/platform/db/alembic/versions/20260603_0144_narrative_zero_write_hashes.py`
  - Add payload hash columns for `narrative_admissions` and `token_discussion_digests`.
  - Follow project migration style for large/current tables: add nullable column, backfill deterministic product hashes, then enforce `NOT NULL` only when backfill is complete.
  - Use concurrent indexes where needed and set lock/statement timeout defensively.

- Modify `src/parallax/domains/narrative_intel/repositories/narrative_repository.py:90-140`
  - Add product payload hash for `narrative_admissions`.
  - Use an `ON CONFLICT DO UPDATE` clause guarded by `WHERE narrative_admissions.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash`.
  - Return actual changed count instead of selected count.
  - Keep `last_seen_at_ms` outside serving-row churn unless it is explicitly part of product-visible payload.

- Modify `src/parallax/domains/narrative_intel/runtime/narrative_admission_worker.py:199-208`
  - Treat `upserted` as actual serving rows written.
  - Keep semantic enqueue counts separate from admission rows written.

- Modify `src/parallax/domains/narrative_intel/repositories/narrative_repository.py:1450-1537`
  - Replace delete/insert `replace_current_digest()` with stable-key upsert and product payload hash.
  - Use the current stable key `(target_type, target_id, window, scope, schema_version)` for current-row publication. If `digest_id` remains the primary key, make it deterministic from that stable key plus status/fingerprint rather than from run/time metadata.
  - Make non-ready status digests reusable current rows when target/window/scope/schema/status/fingerprint are unchanged.

- Modify `src/parallax/domains/narrative_intel/repositories/narrative_repository.py:1561-1585`
  - Add a current digest lookup that can return the current row regardless of ready status for unchanged/status gating.
  - Keep the existing ready-only query if product reads need ready-only semantics.

- Modify `src/parallax/domains/narrative_intel/runtime/token_discussion_digest_worker.py:187-217`
  - Before writing a status digest, compare against current non-ready digest.
  - Report `rows_written=0` for unchanged status digest.

### Macro sync idle scan

- Create migration `src/parallax/platform/db/alembic/versions/20260603_0145_macro_sync_state_hard_cut.py`
  - Add `macro_sync_state`:

    ```sql
    CREATE TABLE IF NOT EXISTS macro_sync_state (
      source_name TEXT NOT NULL,
      bundle_name TEXT NOT NULL,
      max_observed_at DATE,
      updated_at_ms BIGINT NOT NULL,
      PRIMARY KEY(source_name, bundle_name)
    );
    ```

  - Seed it once from existing `macro_observations` during migration.

- Modify `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:656-663`
  - Replace broad `macro_observations_max_observed_at()` calls from runtime scheduler with `macro_sync_state_max_observed_at(source_name, bundle_name)`.
  - Update sync state after successful macro import in the same unit of work that records import/window success.
  - Do not advance sync state on failed imports.
  - For no-op successful imports, advance state from the importer/service `max_seen_observed_at` or equivalent observed watermark, not only from changed rows.
  - Add a bounded repair/rebuild method that can reconstruct `macro_sync_state` from facts for a named source/bundle during ops recovery.

- Modify `src/parallax/domains/macro_intel/services/macro_sync_scheduler.py:10-90`
  - Read sync state, not `MAX(observed_at)` from facts, during every idle enqueue cycle.
  - Keep due windows bounded by settings.

- Modify `src/parallax/domains/macro_intel/services/macro_sync_service.py:61-79`
  - Ensure `enqueue_due_windows()` does not touch broad fact tables during idle cycles.

### WorkerBase, LivePriceGateway, and WorkerSpace hard cut

- Modify `src/parallax/domains/asset_market/runtime/live_price_gateway.py:102-137`
  - Delete custom `run()`.
  - Delete local `_sleep()` if it is only used by custom `run()`.
  - Use `WorkerBase.run()` and existing `run_once()`.

- Modify `tests/architecture/test_worker_runtime_contracts.py:253-273`
  - Remove `live_price_gateway` allowlist.
  - Assert no manifest worker overrides `run()`.

- Delete runtime use of WorkerSpace after preceding behavior tests are green:
  - Delete `src/parallax/app/runtime/worker_space.py`.
  - Delete `src/parallax/app/runtime/runtime_worker_context.py`.
  - Remove `worker_space_contract` from `WorkerBase`.
  - Remove `contract_from_manifest()` injection in `src/parallax/app/runtime/worker_factories/token_intel.py:24-26`.
  - Remove `contract_from_manifest()` injection in `src/parallax/app/runtime/worker_factories/asset_market.py:96-102`.
  - Remove `contract_from_manifest()` import and one-shot `worker_space_contract` injection from `src/parallax/app/surfaces/cli/commands/ops.py`.
  - Replace `_runtime_context()` usage in `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py:116-337` with explicit worker sessions and existing repository methods.
  - Replace `_runtime_context()` usage in `src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:142-363` with explicit worker sessions and existing repository methods.
  - Update tests that import WorkerSpace, including architecture, e2e, and integration missed-wake tests, to assert manifest/static contracts instead.
  - Preserve the guarantees previously tested by WorkerSpace:
    - claim-before-payload-load;
    - provider IO outside DB transactions;
    - agent reservation before claim where applicable;
    - manifest current-read-model writer ownership.
  - Supersede or archive old active WorkerSpace plans so future agents do not reintroduce the partial abstraction.

### Docs and router sync

- Modify `AGENTS.md` and `CLAUDE.md`
  - Keep router text mirrored.
  - Confirm current read model invariant mentions stable product/window keys and zero-write unchanged projections.
  - Add no raw third-party client imports in worker factories.

- Modify `docs/ARCHITECTURE.md`
  - Update current read model invariant with this hard-cut result.
  - Document provider adapters and unavailable worker status.
  - Remove stale watchlist worker summary text if still present.

- Modify `docs/WORKERS.md`
  - Update worker inventory and no WorkerSpace/allowlist behavior.
  - Add dirty-target producer/consumer ownership table.
  - Add CEX OI adapter contract.

- Modify `docs/WORKER_FLOW.md`
  - Update Token Radar to capture-tier producer arrow.
  - Update News item process claim/retry state machine.
  - Remove stale watchlist summary queue language.
  - Add grep acceptance for removed `watchlist_handle_summary_jobs`, stale `account_quality` worker language, and old News `process_failed` lifecycle language where those terms are not historical migration names.

- Modify domain architecture docs:
  - `src/parallax/domains/cex_market_intel/ARCHITECTURE.md`
  - `src/parallax/domains/news_intel/ARCHITECTURE.md`
  - `src/parallax/domains/token_intel/ARCHITECTURE.md`
  - `src/parallax/domains/asset_market/ARCHITECTURE.md`
  - `src/parallax/domains/narrative_intel/ARCHITECTURE.md`
  - `src/parallax/domains/macro_intel/ARCHITECTURE.md`

- Clean planning artefact hygiene
  - Mark or move conflicting active plans that preserve behavior this plan removes, including old News hotpath, WorkerSpace, and already-implemented runtime-integrity active plans.
  - Do not treat stale active plans as source of truth after this hard cut; canonical docs and current code win.

---

## PR Breakdown

### PR 1 — Runtime availability and public status

- [ ] **Step 1: Add availability/status tests**
  - Modify `tests/unit/test_bootstrap_worker_runtime_wiring.py`.
  - Add case: worker enabled, provider missing -> `effective_status='unavailable'`, redacted reason, readiness failure.
  - Add case: worker disabled by config -> `effective_status='disabled'`, readiness ignored.
  - Add case: `start_collector=False` -> `effective_status='intentionally_not_started'`, not unavailable.
  - Add Asset Market cases: `market_tick_stream.enabled=True` without WS provider and `market_tick_poll.enabled=True` without quote provider surface unavailable.

- [ ] **Step 2: Add public status tests**
  - Modify `tests/unit/test_cli_worker_status_contract.py`, `tests/integration/test_api_health.py`, and ops diagnostics tests if present.
  - Assert lane counts include disabled, intentionally-not-started, unavailable, degraded, running, stopped, and failed.
  - Assert `/readyz`, `/api/status`, CLI worker status, and ops diagnostics consume the same effective-status model.

- [ ] **Step 3: Implement sentinel/effective status model**
  - Modify `worker_factories/__init__.py`, `worker_scheduler.py`, `worker_base.py`, `worker_status.py`, `app.py`, `api/schemas.py`, and `ops_diagnostics.py`.
  - Keep reasons redacted and stable, for example `missing_cex_oi_market_provider`.

- [ ] **Step 4: Verify PR 1**

  ```bash
  uv run python -m pytest tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  uv run python -m pytest tests/unit/test_cli_worker_status_contract.py tests/integration/test_api_health.py -q
  ```

### PR 2 — CEX provider adapter and CEX zero-write publication

- [ ] **Step 1: Write concrete provider wrapper tests**
  - Add `tests/unit/test_cex_market_intel_provider_wiring.py`.
  - Assert `wire_providers(settings).cex_market_intel.oi_market` returns normalized `CexOiTicker24h`, `CexFundingPremium`, and `CexOpenInterestPoint` objects.
  - Assert generic `asset_market.cex_market` is not passed to CEX OI worker.
  - Add architecture test that provider-IO worker factories do not import third-party clients directly; this PR removes the CEX raw import.

- [ ] **Step 2: Write CEX detail zero-write tests**
  - Modify `tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py`.
  - Add cases:
    - unchanged board + unchanged detail -> `rows_written=0`, no serving-row update;
    - changed board + unchanged detail -> only board rows change;
    - unchanged board + changed detail -> only detail rows change.
  - Modify `tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py`.
  - Assert `publish_board()` performs no serving-row write on unchanged board/detail payload.
  - Add real PostgreSQL integration coverage for `cex_detail_snapshots` unchanged projection preserving row cardinality and `updated_at`.

- [ ] **Step 3: Create CEX schema migration**
  - Create `src/parallax/platform/db/alembic/versions/20260603_0142_cex_detail_payload_hash_hard_cut.py`.
  - Add/backfill `cex_detail_snapshots.payload_hash`.
  - Use `NOT NULL` only after backfill, and add any required index with existing project migration conventions.
  - Verify with `uv run parallax db migrate`.

- [ ] **Step 4: Implement domain-specific CEX adapters**
  - Create `domains/cex_market_intel/providers.py`.
  - Create `provider_wiring/cex_market_intel.py`.
  - Modify provider wiring types and exports.
  - Modify CEX worker factory to consume the new provider bundle.
  - Remove raw `coinglass_cli.client.CoinglassClient` import from the factory.

- [ ] **Step 5: Implement detail snapshot payload hash**
  - Update repository upsert gating.
  - Move detail snapshot writes behind board/detail publication decision.

- [ ] **Step 6: Verify PR 2**

  ```bash
  uv run python -m pytest tests/unit/test_cex_market_intel_provider_wiring.py -q
  uv run python -m pytest tests/unit/domains/cex_market_intel -q
  uv run python -m pytest tests/integration/domains/cex_market_intel -q
  uv run python -m pytest tests/architecture/test_worker_runtime_contracts.py -m architecture -q
  ```

### PR 3 — News item process durable claim and retry

- [ ] **Step 1: Write repository claim tests**
  - Add or modify `tests/integration/domains/news_intel/test_news_repository.py`.
  - Assert claim sets `processing`, lease owner, lease deadline, attempts, and excludes row from immediate second claim.
  - Assert expired processing rows are released to `process_retryable`.
  - Assert max attempts terminalizes to `process_terminal_failed`.
  - Assert existing `processed AND empty classification` rows are handled by migration/repair and are not selected through an old compatibility predicate.

- [ ] **Step 2: Write worker retry tests**
  - Modify `tests/unit/domains/news_intel/test_news_workers.py`.
  - Add case: deterministic extraction failure marks retryable with `next_due_at_ms`.
  - Add case: last allowed attempt marks terminal failed.
  - Keep existing processed path and brief/page enqueue tests green.

- [ ] **Step 3: Implement news schema hard cut**
  - Add news claim columns and lifecycle check changes to `20260603_0143_news_item_process_claim_hard_cut.py`.
  - Backfill `process_failed` rows to due `process_retryable`.
  - Backfill or repair processed-unclassified rows before removing the legacy predicate.
  - Drop the old `process_failed` lifecycle value.
  - Replace unprocessed claim index.
  - Verify with `uv run parallax db migrate`.

- [ ] **Step 4: Implement repository and worker changes**
  - Replace `list_unprocessed_items()` with durable claim.
  - Update `NewsItemProcessWorker` to claim, process, retry, terminalize, and wake only processed rows.

- [ ] **Step 5: Verify PR 3**

  ```bash
  uv run python -m pytest tests/unit/domains/news_intel/test_news_workers.py -q
  uv run python -m pytest tests/integration/domains/news_intel/test_news_repository.py -q
  uv run python -m pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py -m architecture -q
  ```

### PR 4 — Token Radar capture-tier producer and bounded edge repair

- [ ] **Step 1: Write capture-tier producer tests**
  - Modify `tests/unit/test_token_radar_projection.py`.
  - Assert changed default-venue publication enqueues `token_capture_tier_dirty_targets`.
  - Assert unchanged publication does not enqueue capture-tier work.
  - Assert rank/quality/payload changes with unchanged source watermark still change the dirty-target fingerprint.

- [ ] **Step 2: Write capture-tier rows-written tests**
  - Modify `tests/unit/test_token_capture_tier_worker.py`.
  - Assert worker reports `rows_written=0` when tier repository returns no changed rows.
  - Assert dirty target is marked done after no-op projection.

- [ ] **Step 3: Write bounded edge repair tests**
  - Modify `tests/unit/test_token_radar_projection.py` and `tests/unit/domains/token_intel` query tests if present.
  - Assert `populate_edges_for_targets()` receives `analysis_since_ms`.
  - Assert SQL contains `events.received_at_ms >=`.
  - Assert stale delete also scopes by `event_received_at_ms >= analysis_since_ms`.
  - Assert window-outside old edges are retained and window-inside stale edges are deleted.
  - Assert the 24h projection uses the required 48h lookback plus safety margin.

- [ ] **Step 4: Implement producer and bounded repair**
  - Add capture-tier enqueue call in Token Radar rank-change side effects.
  - Stabilize capture-tier dirty payload hash as rank-set fingerprint.
  - Pass analysis lower bound into rank-source repair SQL.
  - Add explicit CLI/ops bounded repair enqueue path for existing current Token Radar rows.
  - Keep prune responsible for older retained edges.

- [ ] **Step 5: Verify PR 4**

  ```bash
  uv run python -m pytest tests/unit/test_token_radar_projection.py -q
  uv run python -m pytest tests/unit/test_token_capture_tier_worker.py tests/unit/domains/asset_market/test_token_capture_tier_repository.py -q
  uv run python -m pytest tests/integration/test_token_radar_repository.py -q
  ```

### PR 5 — Narrative zero-write

- [ ] **Step 1: Write Narrative unchanged tests**
  - Modify `tests/integration/test_narrative_repository.py`.
  - Assert `upsert_admissions()` unchanged payload returns zero changed rows and preserves row version.
  - Assert unchanged non-ready status digest does not delete/reinsert.
  - Add worker-level test: unchanged `insufficient`, `pending`, or `semantic_unavailable` digest does not call replace/upsert and does not increment `rows_written`.

- [ ] **Step 2: Implement Narrative payload hashes**
  - Add payload hash columns for `narrative_admissions` and `token_discussion_digests` in `20260603_0144_narrative_zero_write_hashes.py`.
  - Update upsert methods and worker row accounting.
  - Add current digest lookup for status gating.
  - Verify with `uv run parallax db migrate`.

- [ ] **Step 3: Verify PR 5**

  ```bash
  uv run python -m pytest tests/integration/test_narrative_repository.py -q
  uv run python -m pytest tests/unit/domains/narrative_intel -q
  ```

### PR 6 — Macro sync state and idle scan hard cut

- [ ] **Step 1: Write Macro idle tests**
  - Modify `tests/unit/domains/macro_intel/test_macro_sync_scheduler.py` or add it if absent.
  - Assert due-window enqueue reads `macro_sync_state`, not `MAX(observed_at)` from `macro_observations`.
  - Use a fake repo that fails if `macro_observations_max_observed_at()` is called during idle enqueue.
  - Add architecture test forbidding `SELECT MAX(observed_at)` in runtime scheduler code.

- [ ] **Step 2: Implement Macro sync state**
  - Add `macro_sync_state` to `20260603_0145_macro_sync_state_hard_cut.py`.
  - Seed it once from facts.
  - Update macro import success path to advance sync state in the same unit of work.
  - Do not advance state on failure; advance no-op successful imports from max seen observed date.
  - Change scheduler to read state.
  - Verify with `uv run parallax db migrate`.

- [ ] **Step 3: Verify PR 6**

  ```bash
  uv run python -m pytest tests/unit/domains/macro_intel -q
  uv run python -m pytest tests/architecture/test_worker_runtime_contracts.py -m architecture -q
  uv run parallax db health
  uv run parallax macro status
  ```

### PR 7 — LivePriceGateway lifecycle and architecture allowlist removal

- [ ] **Step 1: Remove LivePriceGateway run override**
  - Delete `LivePriceGateway.run()` and its private sleep helper.
  - Confirm `WorkerBase.run()` handles the lifecycle.
  - Remove architecture allowlist.

- [ ] **Step 2: Verify PR 7**

  ```bash
  uv run python -m pytest tests/unit/test_worker_base_runtime.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
  uv run python -m pytest tests/architecture/test_worker_runtime_contracts.py -m architecture -q
  ```

### PR 8 — WorkerSpace hard cut, docs, and stale plan cleanup

- [ ] **Step 1: Remove WorkerSpace runtime usage**
  - Delete `worker_space.py` and `runtime_worker_context.py`.
  - Remove `worker_space_contract` from worker constructors and tests.
  - Remove CLI ops `contract_from_manifest()` injection.
  - Replace runtime context calls in Token Radar and Event Anchor with explicit worker sessions.
  - Replace WorkerSpace tests with manifest/static tests that assert the same architecture rules.

- [ ] **Step 2: Update docs, routers, and active planning artefacts**
  - Update `AGENTS.md` and `CLAUDE.md` together.
  - Update canonical docs and domain architecture maps listed above.
  - Remove stale watchlist summary worker references and stale WorkerSpace language.
  - Mark/move stale active plans that conflict with this hard cut.

- [ ] **Step 3: Verify PR 8**

  ```bash
  uv run python -m pytest tests/unit/test_token_radar_projection_worker.py tests/unit/test_event_anchor_backfill_worker.py -q
  uv run python -m pytest tests/e2e/test_backend_hot_path.py tests/integration/test_worker_missed_wake_recovery.py -q
  uv run python -m pytest tests/architecture -m architecture -q
  rg -n "WorkerSpace|runtime_worker_context|worker_space_contract|watchlist_handle_summary_jobs|process_failed|list_unprocessed_items|mark_item_process_failed|account_quality" AGENTS.md CLAUDE.md docs src/parallax tests
  ```

  Expected `rg` output: only historical migration references, explicit superseded-plan notes, or tests that assert absence. No runtime compatibility shim remains.

---

## Rollout Order

1. Merge PR 1 first so runtime/status truthfulness is visible before business fixes.
2. Merge PR 2 and apply `20260603_0142_cex_detail_payload_hash_hard_cut.py` with `uv run parallax db migrate`.
3. Merge PR 3 and apply `20260603_0143_news_item_process_claim_hard_cut.py` with `uv run parallax db migrate`.
4. Merge PR 4, then run the explicit bounded capture-tier repair enqueue command for existing current Token Radar rows.
5. Merge PR 5 and apply `20260603_0144_narrative_zero_write_hashes.py` with `uv run parallax db migrate`.
6. Merge PR 6 and apply `20260603_0145_macro_sync_state_hard_cut.py` with `uv run parallax db migrate`; verify `uv run parallax db health` and `uv run parallax macro status`.
7. Merge PR 7 to remove the `LivePriceGateway.run()` lifecycle exception.
8. Merge PR 8 only after PRs 1-7 are green, because WorkerSpace removal touches runtime, CLI, e2e/integration tests, docs, and stale active plans.
9. Rebuild derived/control-plane state through bounded repair commands from the plan implementation. Material facts are not deleted.
10. Run final verification and write `docs/superpowers/plans/active/2026-06-03-kappa-cqrs-worker-root-fix-verification-cn.md`.

---

## Rollback

- Provider adapter code rollback: revert PR 2. If CEX current rows were rebuilt, rerun the previous known-good board projection after reverting.
- News claim migration rollback is not safely reversible as compatibility. Compensating action: keep facts, reset `processing` or `process_retryable` rows to `raw`, and rerun `news_item_process`.
- Token Radar/capture rollback: remove capture-tier enqueue call and truncate `token_capture_tier_dirty_targets`; `token_capture_tier` is derived and rebuildable.
- Narrative rollback: current read rows are derived; truncate affected current rows and re-enqueue admission/digest dirty targets from facts.
- Macro sync state rollback: drop `macro_sync_state` only if runtime is reverted to the old scheduler. This is not preferred because old scheduler violates idle-scan rules.
- LivePriceGateway rollback: revert PR 7 as a unit only if the base lifecycle cannot support cache fanout; do not reintroduce a run-override allowlist as a partial state.
- WorkerSpace removal rollback: revert PR 8 as a unit. Do not reintroduce allowlists or partial injections in a mixed state.

---

## Acceptance Test Commands

- AC1: `uv run python -m pytest tests/unit/test_cex_market_intel_provider_wiring.py -q`
- AC2: `uv run python -m pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_cli_worker_status_contract.py tests/integration/test_api_health.py -q`
- AC3: `uv run python -m pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py tests/integration/domains/cex_market_intel -q`
- AC4 and AC5: `uv run python -m pytest tests/unit/domains/news_intel/test_news_workers.py tests/integration/domains/news_intel/test_news_repository.py -q`
- AC6 and AC7: `uv run python -m pytest tests/unit/test_token_radar_projection.py tests/unit/test_token_capture_tier_worker.py -q`
- AC8: `uv run python -m pytest tests/unit/test_token_radar_projection.py tests/architecture/test_worker_runtime_contracts.py -q`
- AC9 and AC10: `uv run python -m pytest tests/integration/test_narrative_repository.py tests/unit/domains/narrative_intel -q`
- AC11 and AC12: `uv run python -m pytest tests/unit/test_bootstrap_worker_runtime_wiring.py tests/integration/test_api_health.py -q`
- AC13 through AC17: `uv run python -m pytest tests/architecture -m architecture -q`
- AC18 and AC19:

  ```bash
  uv run python -m pytest tests/architecture/test_macro_no_compatibility_contract.py tests/architecture/test_worker_runtime_contracts.py -q
  uv run python -m pytest tests/e2e/test_backend_hot_path.py tests/integration/test_worker_missed_wake_recovery.py -q
  rg -n "WorkerSpace|runtime_worker_context|worker_space_contract|watchlist_handle_summary_jobs|process_failed|list_unprocessed_items|mark_item_process_failed|account_quality" AGENTS.md CLAUDE.md docs src/parallax tests
  ```

  Expected `rg` output: only historical migration references, explicit superseded-plan notes, or tests that assert absence.

- AC20 final gate:

  ```bash
  make check-all
  ```

---

## Verification

Create `docs/superpowers/plans/active/2026-06-03-kappa-cqrs-worker-root-fix-verification-cn.md` from `docs/superpowers/_templates/verification-template.md` before declaring implementation complete.

The verification artefact must include:

- full `make check-all` output and exit code;
- coverage and skipped-test sections;
- E2E golden path status;
- per-PR `uv run parallax db migrate` output for the four schema revisions;
- `uv run parallax db health` and `uv run parallax macro status` outputs after Macro hard cut, with secrets redacted;
- targeted command outputs listed above;
- redacted `uv run parallax config` path confirmation;
- diff review against this plan;
- remaining risks and any follow-up entry added to `docs/TECH_DEBT.md`.
