# Token Radar Kappa/CQRS Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Token Radar 链路改成 material facts → projection read model → query/surface/UI 的 Kappa/CQRS hard cut，删除 anchor/live/projection/API/web 多重 market 合并和多 writer 协调。

**Architecture:** PostgreSQL material facts 是唯一业务事实源；provider raw frames 是高频输入，不等于必须持久化的事实。`token_radar_rows`、pulse candidates、API payload、前端 cache 都是可重建 read model。`MarketObservation` 是唯一市场事实类型，`MarketContext.event_anchor` 与 `MarketContext.decision_latest` 是两个显式时间角色。跨 worker `LISTEN/NOTIFY` 只作为 wake hint，正确性来自 DB material facts + projection/pulse periodic catch-up。

**Tech Stack:** Python 3.12, PostgreSQL, Alembic, pytest, ruff, React, TanStack Query, Vitest, TypeScript.

---

## Status

**Status**: Complete
**Date**: 2026-05-13
**Owning spec**: `docs/superpowers/specs/active/2026-05-13-token-radar-pipeline-overcomplexity-audit-cn.md`
**Worktree**: `.worktrees/token-radar-kappa-cqrs-hard-cut/`
**Branch**: `codex/token-radar-kappa-cqrs-hard-cut`

## Progress Log

- 2026-05-13 12:31 Asia/Shanghai — Started execution in isolated worktree `.worktrees/token-radar-kappa-cqrs-hard-cut` on branch `codex/token-radar-kappa-cqrs-hard-cut`. Plan and owning spec were copied into the worktree because they were untracked in the main checkout.
- 2026-05-13 13:53 Asia/Shanghai — Pre-flight baseline complete. `uv run ruff check .` passed. `uv run pytest` passed with 806 passed / 14 skipped in 598.72s. `cd web && npm test -- --run` passed with 25 files / 137 tests after installing existing web dependencies.
- 2026-05-13 13:58 Asia/Shanghai — Milestone 1 / Task 1 complete. Updated architecture role markers, Token Intel market-contract wording, public Token Radar market contract, and generated WS protocol docs. Validation: `uv run pytest tests/architecture/test_src_domain_architecture.py -q` passed with 13 tests. Extra generated-doc validation `uv run pytest tests/integration/test_docs_generated.py -q` passed with 4 tests.
- 2026-05-13 14:00 Asia/Shanghai — Task 2 complete. Added `MarketObservation`, `MarketContext`, `MarketReadiness`, serialization helpers, row conversion helper, and focused tests. Validation: `uv run pytest tests/unit/test_market_observation.py -q` passed with 3 tests.
- 2026-05-13 14:10 Asia/Shanghai — Task 3 complete. Added hard-cut `price_observations` partition migration, removed runtime baseline-table writes/backfill CLI, added `insert_market_observation` and target/anchor query helpers, and kept source-query reads off `token_market_price_baselines` after validation exposed the removed-table dependency. Validation: `uv run pytest tests/unit/test_price_observation_repository.py -q` passed with 4 tests; extra `uv run pytest tests/integration/test_cli.py -q` passed with 17 tests.
- 2026-05-13 14:14 Asia/Shanghai — Task 4 complete. Added market capability/health types, wired OKX through a small provider bundle with shared CEX provider instance, removed `dex_ws_enabled`, and made OKX DEX WS configured by URL plus credentials. Validation: `uv run pytest tests/unit/test_provider_capabilities.py tests/unit/test_settings.py -q` passed with 25 tests; extra `uv run pytest tests/unit/test_providers_wiring.py -q` passed with 5 tests.
- 2026-05-13 14:24 Asia/Shanghai — Task 5 complete. Added live observation persistence policy and write-budget benchmark, changed anchor/live workers to write `event_anchor`/`decision_latest` material facts, added `WakeBus`, removed anchor worker callback wiring, and removed resolution refresh inline anchor/projection rebuild. Validation: `uv run pytest tests/unit/test_anchor_price_worker.py tests/unit/test_live_observation_policy.py tests/unit/test_live_price_gateway.py tests/unit/test_resolution_refresh_worker.py tests/benchmark/test_live_observation_write_budget.py -q` passed with 15 tests. Extra affected tests `uv run pytest tests/test_live_price_gateway.py tests/unit/test_anchor_price_observation.py tests/unit/test_settings.py -q` passed with 32 tests; focused ruff check passed.
- 2026-05-13 14:33 Asia/Shanghai — Task 6 complete. Source query now reads `event_anchor` and `decision_latest` from `price_observations` LATERAL joins, projection emits `market.event_anchor` / `market.decision_latest` / `market.readiness`, and the factor snapshot contract enforces the new market shape. Validation: `uv run pytest tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py -q` passed with 27 tests; focused ruff check passed.
- 2026-05-13 14:39 Asia/Shanghai — Task 7 complete. DEX gate checks now read `market.decision_latest`, missing DEX floor fields add `*_unverified` blockers, cohort ranking returns no signal for cohorts below 10 or all tied, and normalization records `cohort_status`. Validation: `uv run pytest tests/unit/test_factor_snapshot.py tests/unit/test_token_radar_apply_cross_section.py -q` passed with 38 tests; focused ruff check passed.
- 2026-05-13 14:45 Asia/Shanghai — Task 8 complete. Projection worker now has no callback wake API, listens for market/resolution wake hints via injected `WakeListener`, keeps interval catch-up, remains the single runtime writer of `token_radar_rows`, and publishes `token_radar_updated` after successful window writes. Validation: `uv run pytest tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_idempotency.py tests/architecture/test_src_domain_architecture.py -q` passed with 17 tests / 1 skipped.
- 2026-05-13 14:52 Asia/Shanghai — Task 9 complete. Pulse candidate worker now runs as a normal asyncio task, listens to `token_radar_updated` through the shared wake listener, keeps poll catch-up, and gates candidates on `market.decision_latest` plus `normalization.cohort_status`. Validation: `uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_candidate_gate.py -q` passed with 30 tests.
- 2026-05-13 14:58 Asia/Shanghai — Task 10 complete. Asset flow rows now expose `market` directly from factor snapshots, HTTP no longer injects live gateway overlays, live WS updates carry only `market.decision_latest`, and repository/CLI validation helpers use the hard-cut market schema. Validation: `uv run pytest tests/unit/test_token_radar_repository.py tests/integration/test_cli.py -q` passed with 34 tests / 4 skipped. Extra affected validation `uv run pytest tests/unit/test_live_price_gateway.py tests/test_live_price_gateway.py -q` passed with 5 tests.
- 2026-05-13 15:11 Asia/Shanghai — Task 11 complete. Frontend Token Radar cache patching now uses socket callback material updates, rows patch `market.decision_latest`, TokenTargetPage shares the token radar query hook, and components/types use the hard-cut market context. Validation: `cd web && npm test -- --run src/features/live/liveMarketUpdatePatch.test.ts src/lib/tokenRadar.test.ts src/components/TokenRadarRow.test.tsx src/components/__tests__/TokenTargetPage.routing.test.tsx` passed with 25 tests.
- 2026-05-13 15:16 Asia/Shanghai — Task 12 complete. OKX DEX WS and GMGN direct WS now expose connection states with timestamps, collector status records snapshot gate outcomes, and `/api/status` exposes provider states plus snapshot gate counters. Validation: `uv run pytest tests/unit/test_okx_dex_ws_client.py tests/unit/test_gmgn_token_payload.py -q` passed with 11 tests. Extra affected validation `uv run pytest tests/unit/test_collector_service.py -q` passed with 3 tests.
- 2026-05-13 15:21 Asia/Shanghai — Task 13 complete. Regenerated CLI/WS docs, added hard-cut no-fallback guards for market overlay paths, and updated golden corpus assertions to the `market.event_anchor` / `market.decision_latest` / `market.readiness` schema. Validation: `uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py tests/golden/test_token_radar_corpus.py -q` passed with 10 tests / 4 skipped because the optional PostgreSQL golden database was unavailable.
- 2026-05-13 15:56 Asia/Shanghai — Task 14 local hard-cut operations partially complete before merge. Stopped running app container, applied Alembic head, truncated derived read models plus FK-dependent derived tables, rebuilt 5m/1h radar projections, removed stale `dex_ws_enabled` from local config with a timestamped backup, and passed pre-merge `make check`. Full `make check-all` verification artefact remains pending on `main` per latest user direction to merge first and deepen testing after.
- 2026-05-13 16:54 Asia/Shanghai — Merged `codex/token-radar-kappa-cqrs-hard-cut` into `main`, fixed post-merge hard-cut integration fixture drift, committed `465d4fb0`, and completed final audit. Validation: `make check-all` passed with exit code 0; final coverage run reported 833 passed / 14 skipped and total coverage 82.18%. Verification artefact created at `docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-verification-cn.md`.
- 2026-05-13 17:02 Asia/Shanghai — Attempted local `docker compose up -d --build app` after verification. Build failed while fetching private GitHub dependency `marketlane-cli` because no GitHub token/credentials were available in the non-interactive environment. PostgreSQL remains healthy; app container remains stopped rather than starting an old image.

## Decision Log

- 2026-05-13 12:31 Asia/Shanghai — Treat this plan file as `PLAN.md` for progress and decision logging. No separate root `PLAN.md` exists in this repository, and the user named `2026-05-13-token-radar-kappa-cqrs-hard-cut-plan-cn.md` as the source of truth.
- 2026-05-13 13:53 Asia/Shanghai — Installed existing frontend dependencies with `npm install` in the worktree because baseline Vitest initially failed with `vitest: command not found`. This did not add a new production dependency; `package-lock.json` was unchanged.
- 2026-05-13 13:58 Asia/Shanghai — Updated `docs/generated/ws-protocol.md` via `scripts/regen_ws_protocol.py` after adding non-behavioral class docstrings to `app/surfaces/api/ws.py`. The generated-docs cleanliness test checks unstaged diffs, so `docs/generated/ws-protocol.md` was staged before running that extra validation.
- 2026-05-13 14:10 Asia/Shanghai — Pulled the Task 6 source-query baseline removal forward because Task 3 deletes `token_market_price_baselines`, and CLI integration validation proved the old runtime join could no longer remain. Full Task 6 market-context projection work remains open.
- 2026-05-13 14:10 Asia/Shanghai — Created lookup indexes on concrete `price_observations` partitions rather than relying on a concurrent parent-table partitioned index. This keeps the hot query paths indexed while preserving the migration rule that concurrent index builds stay inside Alembic autocommit blocks.
- 2026-05-13 14:14 Asia/Shanghai — Provider health reports configured capabilities, not every capability the provider could theoretically support. This keeps health aligned with actual wiring and avoids a second per-capability config matrix.
- 2026-05-13 14:24 Asia/Shanghai — `live_market_update` is now published only for persisted material `decision_latest` observations. The process-local cache still updates on every valid live frame for direct snapshot/debug use, but business cache fan-out follows material facts.
- 2026-05-13 14:33 Asia/Shanghai — Kept `first_price_*` compatibility aliases in the source query for existing feature tests, but projection market output no longer reads them. The runtime market contract is exclusively `event_anchor`, `decision_latest`, and `readiness`.
- 2026-05-13 14:39 Asia/Shanghai — Cross-section ranking now has an explicit `cohort_status` separate from row `normalization.status`. This keeps "why no alpha rank" visible without overloading `status`.
- 2026-05-13 14:45 Asia/Shanghai — SQL `LISTEN` lives in app/runtime `WakeListener`, not the Token Intel domain runtime. The projection worker receives an injected wake listener, so domain code stays on orchestration semantics while app/runtime owns PostgreSQL notification mechanics.
- 2026-05-13 14:52 Asia/Shanghai — Pulse treats `token_radar_updated` as a wake hint only. The worker still polls at its configured interval, and the gate fails closed when target rows lack material `decision_latest` or have an insufficient/all-tied cohort status.
- 2026-05-13 14:58 Asia/Shanghai — Removed the old top-level `live_market` WS payload copy at its source in `LivePriceGateway`, even though the Task 10 file list names `ws.py`. The public WS contract is produced by the gateway payload and routed unchanged by `PublicWebSocketHub`.
- 2026-05-13 15:11 Asia/Shanghai — The Task 11 command in the plan uses `web/src/...` after `cd web`, which Vitest treats as nonexistent filters. The semantic validation was rerun with the same files as `src/...` relative paths and passed.
- 2026-05-13 15:16 Asia/Shanghai — Provider connection state is diagnostic only: it is exposed through `connection_state_payload()` and `/api/status`, while worker correctness still depends on persisted facts plus periodic catch-up.
- 2026-05-13 15:21 Asia/Shanghai — The no-fallback guard scans runtime source only and intentionally avoids banning the `live_market_update` event name or historical Alembic rollback references. The hard-cut ban targets runtime overlay/fallback paths, not the public WS event type.
- 2026-05-13 15:56 Asia/Shanghai — The plan's `gmgn-twitter-intel token-radar rebuild` command is stale; the equivalent current CLI command is `gmgn-twitter-intel ops rebuild-token-radar`. The user asked to merge quickly and continue deep testing after merge, so `make check` is the pre-merge gate and `make check-all` remains the post-merge final audit.
- 2026-05-13 15:56 Asia/Shanghai — PostgreSQL refused the exact Task 14 truncate because FK-derived tables reference `token_radar_rows` and `pulse_candidates`. Truncated `asset_signal_snapshots`, `asset_signal_outcomes`, `pulse_playbook_snapshots`, and `pulse_playbook_outcomes` alongside the planned derived tables because they are derived from the same radar/pulse read models.
- 2026-05-13 16:54 Asia/Shanghai — The hard-cut fallback `rg` command still reports historical Alembic migration references to the removed baseline table. These are allowed rollback/history references, not runtime/web/test fallback paths; guard tests now avoid embedding the banned literals directly.
- 2026-05-13 17:02 Asia/Shanghai — Do not restart the app from an old Docker image after a hard cut. Because rebuilding the image requires GitHub credentials for `marketlane-cli`, service restart is left as an operational handoff item rather than running stale code.

## Design Goals

- **DG1 facts first**: `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `price_observations` 是唯一业务事实源。
- **DG2 one material market fact type**: GMGN OpenAPI quote、OKX CEX ticker、OKX DEX WS material update 都标准化为 `MarketObservation`；provider raw frame 只是输入事件，不直接进入事实表。
- **DG3 two market time roles**: `event_anchor` 服务事件时刻/回测，`decision_latest` 服务当前决策/UI/pulse；二者不能互相覆盖。
- **DG4 one read-model writer**: `token_radar_rows` 只由 `TokenRadarProjectionWorker` 写。
- **DG5 wake is not truth**: `NOTIFY` payload 只发 target/window hint；消费端重读 DB。
- **DG6 no compatibility layer**: 删除旧 `anchor_price` / `live_market` runtime fallback、API overlay、前端重复 patch。
- **DG7 observable IO**: OKX/GMGN WS 有显式 connection state；snapshot gate 有 outcome metric。
- **DG8 hard cut deploy**: source facts 与 material market facts 保留，derived rows truncate/rebuild；不做旧 snapshot 解析分支。
- **DG9 write budget first**: live market 持久化必须先过写入预算；默认只落 material observations：first-seen、heartbeat、显著价格变化、gate 字段变化、provider 状态变化。

## Directory / File Role Map

| Path | Role | Target state |
|---|---|---|
| `src/gmgn_twitter_intel/integrations/gmgn/direct_ws.py` | `[ADAPTER]` | GMGN stream adapter；新增 connection state，不写业务事实。 |
| `src/gmgn_twitter_intel/integrations/gmgn/gmgn_token_payload.py` | `[ADAPTER]` | 明确 GMGN WS price fields intentionally ignored。 |
| `src/gmgn_twitter_intel/integrations/gmgn/openapi_client.py` | `[ADAPTER]` | GMGN exact-address quote/profile/candle adapter。 |
| `src/gmgn_twitter_intel/integrations/okx/cex_client.py` | `[ADAPTER]` | OKX CEX quote adapter。 |
| `src/gmgn_twitter_intel/integrations/okx/dex_client.py` | `[ADAPTER]` | OKX discovery adapter。 |
| `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py` | `[ADAPTER]` | OKX DEX live market adapter；新增 connection state。 |
| `src/gmgn_twitter_intel/domains/ingestion/runtime/collector_service.py` | `[COMMAND]` | 显式 snapshot gate outcome；不处理 market facts。 |
| `src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py` | `[COMMAND]` | 写 social/entity/intent/identity facts；不引入 market read model。 |
| `src/gmgn_twitter_intel/domains/asset_market/types/market_observation.py` | `[FACT]` | 新增 `MarketObservation`、`MarketContext`、`MarketReadiness`。 |
| `src/gmgn_twitter_intel/domains/asset_market/interfaces.py` | `[FACT]` | 暴露跨域可用的 market fact value types。 |
| `src/gmgn_twitter_intel/domains/asset_market/providers.py` | `[ADAPTER]` | 保留窄 capability contracts；补 provider capability metadata。 |
| `src/gmgn_twitter_intel/app/runtime/providers_wiring.py` | `[ADAPTER]` | OKX/GmGN adapter wire、provider-level health/cache/rate-limit。 |
| `src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py` | `[FACT]` | 持久化/query `MarketObservation`；删除 baseline backfill。 |
| `src/gmgn_twitter_intel/domains/asset_market/services/anchor_price_observation.py` | `[COMMAND][FACT]` | 写 `event_anchor` observations。 |
| `src/gmgn_twitter_intel/domains/asset_market/services/live_observation_policy.py` | `[COMMAND][FACT]` | 新增 material observation 写入策略；阻止 raw WS frame 全量落库。 |
| `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py` | `[COMMAND][FACT][WAKE]` | 内存接收高频 live frames；只写 material `decision_latest` observations；WS publish 只是 fan-out。 |
| `src/gmgn_twitter_intel/domains/asset_market/runtime/anchor_price_worker.py` | `[COMMAND][WAKE]` | 删除 callback，写完 facts 后 NOTIFY。 |
| `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py` | `[COMMAND][WAKE]` | 删除 inline anchor/projection；只写 resolution/discovery facts 后 NOTIFY。 |
| `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py` | `[QUERY][FACT]` | 用 lateral joins 从 `price_observations` 拉 `event_anchor` / `decision_latest`。 |
| `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py` | `[PROJECTION]` | 构造新 `MarketContext` schema；删除 anchor-only `_market()`。 |
| `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py` | `[PROJECTION][WAKE]` | LISTEN + catch-up；唯一写 `token_radar_rows`。 |
| `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py` | `[SCORING]` | 新 market schema、DEX floor fail-closed。 |
| `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py` | `[SCORING]` | 新 snapshot contract。 |
| `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py` | `[SCORING]` | insufficient/all-tied cohort 返回 no-signal。 |
| `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py` | `[QUERY][DELETE]` | 删除 `_overlay_live_market`；只序列化 projection row。 |
| `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py` | `[QUERY][WAKE]` | 主 event loop task；listen `token_radar_updated` hint + catch-up。 |
| `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py` | `[SCORING]` | 新 market/gate/no-signal 语义。 |
| `src/gmgn_twitter_intel/app/runtime/app.py` | `[SURFACE][WAKE][DELETE]` | Wire listeners；删除 threaded pulse wrapper。 |
| `src/gmgn_twitter_intel/app/surfaces/api/http.py` | `[SURFACE]` | `/api/token-radar` 返回新 market contract。 |
| `src/gmgn_twitter_intel/app/surfaces/api/ws.py` | `[SURFACE]` | WS live payload 与 new market contract 对齐。 |
| `src/gmgn_twitter_intel/app/surfaces/cli/main.py` | `[SURFACE][DELETE]` | 删除 price baseline backfill command；保留现有 projection rebuild 命令作为 smoke 入口。 |
| `web/src/api/types.ts` | `[UI]` | 新 market TypeScript contract。 |
| `web/src/api/useIntelSocket.ts` | `[UI]` | per-frame callback。 |
| `web/src/features/live/useLiveData.ts` | `[UI][DELETE]` | 删除 `liveMarketUpdates[0]` patch。 |
| `web/src/features/live/liveMarketUpdatePatch.ts` | `[UI]` | patch `market.decision_latest`。 |
| `web/src/store/useTraderStore.ts` | `[UI]` | Token Radar 单 cache/store 入口。 |
| `web/src/components/TokenRadarRow.tsx` | `[UI]` | 显示 `event_anchor` / `decision_latest`。 |
| `web/src/components/TokenTargetPage.tsx` | `[UI][DELETE]` | 删除页面级直调 `/api/token-radar`。 |
| `web/src/components/SearchIntelPage.tsx` | `[UI]` | 使用 shared market helpers。 |
| `web/src/domain/tokenTarget.ts` | `[UI]` | 统一 `isDexMarket` / target ref / market helpers。 |

## Target Data Flow

```text
GMGN/OKX adapters
  → command workers/services
  → material observation policy
  → PostgreSQL material facts
      events
      token_intents
      token_intent_resolutions
      asset_identity_evidence/current
      price_observations(kind=event_anchor|decision_latest)
  → NOTIFY wake hint
  → TokenRadarProjectionWorker catch-up
  → token_radar_rows.factor_snapshot_json.market
      event_anchor
      decision_latest
      readiness
  → AssetFlowService / SignalPulseService / TokenTarget read models
  → HTTP / WS / CLI
  → React single Token Radar cache
```

## Live Observation Persistence Policy

Provider live frames are not domain facts. A raw OKX DEX WS frame may update the in-process latest cache and may be fanned out for debug/recent display, but it is persisted to `price_observations` only when it becomes a material `decision_latest` observation.

Persist `decision_latest` only when at least one condition is true:

- `first_seen`: no previous persisted observation exists for `(target_type, target_id, provider, pricefeed_id)`.
- `heartbeat`: `now_ms - last_persisted.observed_at_ms >= live_observation_heartbeat_seconds * 1000`; default `60s`.
- `significant_price_change`: `abs(new_price_usd - last_price_usd) / last_price_usd >= live_observation_min_price_change_pct`; default `0.005`.
- `gate_field_change`: one of `holders`, `liquidity_usd`, `market_cap_usd`, `volume_24h_usd`, `open_interest_usd` changes missing/present status or crosses a DEX floor threshold used by Signal Pulse.
- `provider_state_change`: stream reconnect/recover status means the first fresh frame after recovery must be persisted.

Never persist a live frame only because it arrived. `per-target debounce` is allowed as an extra guard, but it is not the correctness rule. `NOTIFY market_observation_written` is emitted only after a persisted material observation. Token Radar cache patches use the persisted observation contract; raw frame fan-out must not mutate `factor_snapshot.market`.

Write budget target:

- Normal live market budget: `<= 5 persisted decision_latest rows/sec` on 84 subscribed DEX targets during flat markets.
- Synthetic flat-market benchmark: `100 targets * 5 frames/sec * 10 minutes = 300,000 raw frames`; expected persisted rows `<= 1,500` (`first_seen + 60s heartbeat + small jitter`).
- If benchmark exceeds budget, implementation must tighten `live_observation_min_price_change_pct`, heartbeat, or gate-field rules before Task 5 is complete.

## Must Delete

- `AssetFlowService._overlay_live_market`.
- `AnchorPriceWorker.on_observations_written`.
- `ResolutionRefreshWorker` inline `observe_anchor_prices()`.
- `ResolutionRefreshWorker` inline `rebuild_token_radar_windows()`.
- `TokenRadarProjectionWorker._wake_event` cross-thread set path.
- `_start_threaded_async_worker` and `_watch_threaded_worker` for pulse.
- `dex_ws_enabled` config flag and dependent conditionals.
- Runtime reads from `token_market_price_baselines`.
- CLI `backfill-price-baselines` command.
- Frontend `socket.liveMarketUpdates[0]` business patch.
- Component-local `isDexMarket` duplicates.
- Runtime fallback fields `anchor_price` / `live_market` in public Token Radar rows.

## Pre-flight

- [x] Create worktree:
  ```bash
  git worktree add .worktrees/token-radar-kappa-cqrs-hard-cut -b codex/token-radar-kappa-cqrs-hard-cut main
  ```
- [x] Verify worktree:
  ```bash
  git worktree list
  git -C .worktrees/token-radar-kappa-cqrs-hard-cut branch --show-current
  git -C .worktrees/token-radar-kappa-cqrs-hard-cut status --short
  ```
- [x] Run baseline:
  ```bash
  cd .worktrees/token-radar-kappa-cqrs-hard-cut
  uv run ruff check .
  uv run pytest
  cd web && npm test -- --run
  ```

Known-failing baseline tests: none expected.

## File-level Edits

### Task 1 — Architecture Markers And Contracts

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/generated/ws-protocol.md`

- [x] Add the role-marker legend from the spec to `docs/ARCHITECTURE.md`.
- [x] Update Token Intel architecture to say `factor_snapshot.market` is the runtime explanation source and has `event_anchor`, `decision_latest`, `readiness`.
- [x] Remove text saying "`live_market` comes from process-local gateway updates" from Token Intel architecture.
- [x] Update public HTTP/WS contract docs to remove old top-level `anchor_price` and `live_market` semantics.
- [x] Run:
  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py -q
  ```
  Expected: pass.

### Task 2 — MarketObservation Core Types

**Files:**
- Create: `src/gmgn_twitter_intel/domains/asset_market/types/market_observation.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/types/__init__.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/interfaces.py`
- Test: `tests/unit/test_market_observation.py`

- [x] Add frozen dataclasses:
  ```python
  @dataclass(frozen=True, slots=True)
  class MarketTargetRef:
      target_type: str
      target_id: str

  @dataclass(frozen=True, slots=True)
  class MarketObservation:
      target: MarketTargetRef
      observed_at_ms: int
      received_at_ms: int | None
      source: str
      provider: str | None
      pricefeed_id: str | None
      price_usd: float | None
      price_quote: float | None
      quote_symbol: str | None
      price_basis: str | None
      market_cap_usd: float | None
      liquidity_usd: float | None
      holders: int | None
      volume_24h_usd: float | None
      open_interest_usd: float | None
      raw_payload_hash: str | None

  @dataclass(frozen=True, slots=True)
  class MarketReadiness:
      anchor_status: str
      latest_status: str
      dex_floor_status: str
      missing_fields: Sequence[str]
      stale_fields: Sequence[str]

  @dataclass(frozen=True, slots=True)
  class MarketContext:
      event_anchor: MarketObservation | None
      decision_latest: MarketObservation | None
      readiness: MarketReadiness
  ```
- [x] Add helpers `market_observation_to_dict`, `market_context_to_dict`, `market_observation_from_row`.
- [x] Test serialization preserves absent fields as `None` and does not synthesize default prices.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_market_observation.py -q
  ```
  Expected: pass.

### Task 3 — Storage Hard Cut Migration And Live Partition Shape

**Files:**
- Create: `src/gmgn_twitter_intel/platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py`
- Modify: `src/gmgn_twitter_intel/platform/db/alembic/README.md` if it documents manual partition maintenance.
- Modify: `src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/cli/main.py`
- Delete runtime dependency: `token_market_price_baselines`
- Test: `tests/unit/test_price_observation_repository.py`

- [x] Migration upgrade uses a maintenance-window hard cut. Because PostgreSQL native partitioned tables cannot keep the old global `PRIMARY KEY(observation_id)` unless every unique key includes the partition key, the new parent keeps `observation_id TEXT NOT NULL` plus a non-unique lookup index. `observation_id` remains application-generated and deterministic; `event_anchor` uniqueness is enforced on the `event_anchor` partition.
- [x] Migration upgrade SQL shape. Run all `DROP INDEX CONCURRENTLY` and `CREATE INDEX CONCURRENTLY` statements inside Alembic `autocommit_block()`; table rename/create/copy/drop statements stay in the normal migration transaction.
  ```sql
  DROP INDEX CONCURRENTLY IF EXISTS uq_price_observations_message_anchor_resolution;
  DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_anchor_subject_time;
  DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_subject_kind_latest;
  DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_subject_latest_any;
  DROP INDEX CONCURRENTLY IF EXISTS idx_token_market_price_baselines_resolution;

  ALTER TABLE price_observations RENAME TO price_observations_legacy;

  CREATE TABLE price_observations (
    observation_id TEXT NOT NULL,
    pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    observed_at_ms BIGINT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    price_usd NUMERIC,
    price_quote NUMERIC,
    quote_symbol TEXT,
    price_basis TEXT NOT NULL DEFAULT 'unavailable',
    market_cap_usd NUMERIC,
    liquidity_usd NUMERIC,
    volume_24h_usd NUMERIC,
    open_interest_usd NUMERIC,
    holders BIGINT,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at_ms BIGINT NOT NULL,
    source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL,
    source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL,
    source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL,
    observation_kind TEXT NOT NULL,
    event_received_at_ms BIGINT,
    observation_lag_ms BIGINT
  ) PARTITION BY LIST (observation_kind);

  CREATE TABLE price_observations_event_anchor
    PARTITION OF price_observations
    FOR VALUES IN ('event_anchor');

  CREATE TABLE price_observations_decision_latest
    PARTITION OF price_observations
    FOR VALUES IN ('decision_latest')
    PARTITION BY RANGE (observed_at_ms);

  CREATE TABLE price_observations_other
    PARTITION OF price_observations
    DEFAULT;

  INSERT INTO price_observations (
    observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
    price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
    volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms,
    source_event_id, source_intent_id, source_resolution_id, observation_kind,
    event_received_at_ms, observation_lag_ms
  )
  SELECT
    observation_id, pricefeed_id, provider, observed_at_ms, subject_type, subject_id,
    price_usd, price_quote, quote_symbol, price_basis, market_cap_usd, liquidity_usd,
    volume_24h_usd, open_interest_usd, holders, raw_payload_json, created_at_ms,
    source_event_id, source_intent_id, source_resolution_id,
    CASE WHEN observation_kind = 'message_anchor' OR observation_kind IS NULL
      THEN 'event_anchor'
      ELSE observation_kind
    END AS observation_kind,
    event_received_at_ms, observation_lag_ms
  FROM price_observations_legacy;

  DROP TABLE price_observations_legacy;
  DROP TABLE IF EXISTS token_market_price_baselines;
  ```
- [x] Alembic computes month partitions from existing min/max `observed_at_ms`, the current month, and the next month, then creates monthly live partitions before the `INSERT`:
  ```sql
  CREATE TABLE price_observations_decision_latest_YYYY_MM
    PARTITION OF price_observations_decision_latest
    FOR VALUES FROM (:month_start_ms) TO (:next_month_start_ms);

  CREATE TABLE price_observations_decision_latest_default
    PARTITION OF price_observations_decision_latest
    DEFAULT;
  ```
- [x] Add hot-path indexes after copy:
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_observation_id
    ON price_observations(observation_id);

  CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_price_observations_event_anchor_resolution
    ON price_observations_event_anchor(source_resolution_id)
    WHERE source_resolution_id IS NOT NULL;

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_event_anchor_subject_latest
    ON price_observations_event_anchor(subject_type, subject_id, observed_at_ms DESC, observation_id DESC);

  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_decision_latest_subject_latest
    ON price_observations_decision_latest(subject_type, subject_id, observed_at_ms DESC, observation_id DESC);
  ```
- [x] Remove `ON CONFLICT(source_resolution_id)` from anchor insert code. `insert_market_observation` with `observation_kind="event_anchor"` first queries by `source_resolution_id`; if found, it updates that row by `observation_id`; otherwise it inserts. This avoids relying on a global unique index that native partitioning cannot provide.
- [x] Migration downgrade recreates `token_market_price_baselines` shape from `20260511_0025_token_radar_production_read_models.py` and renames `event_anchor` back to `message_anchor`.
- [x] Remove `backfill_token_price_baselines()` from `price_observation_repository.py`.
- [x] Remove CLI parser/handler for `backfill-price-baselines`.
- [x] Add repository methods:
  ```python
  def insert_market_observation(self, observation: MarketObservation, *, observation_kind: str, source_event_id: str | None, source_intent_id: str | None, source_resolution_id: str | None, event_received_at_ms: int | None, commit: bool = True) -> str
  def event_anchor_for_resolution(self, *, resolution_id: str) -> MarketObservation | None
  def latest_for_target(self, *, target_type: str, target_id: str, now_ms: int, max_age_ms: int | None) -> MarketObservation | None
  def first_after(self, *, target_type: str, target_id: str, at_ms: int) -> MarketObservation | None
  def latest_before(self, *, target_type: str, target_id: str, at_ms: int) -> MarketObservation | None
  ```
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_price_observation_repository.py -q
  ```
  Expected: pass.

### Task 4 — Provider Capability Routing Without God Interface

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/providers.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/providers_wiring.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Test: `tests/unit/test_provider_capabilities.py`

- [x] Add:
  ```python
  class MarketCapability(StrEnum):
      QUOTE_CEX = "quote_cex"
      QUOTE_DEX_EXACT = "quote_dex_exact"
      STREAM_DEX = "stream_dex"
      SEARCH_DEX = "search_dex"
      PROFILE_DEX_EXACT = "profile_dex_exact"
      CANDLES_DEX_EXACT = "candles_dex_exact"

  @dataclass(frozen=True, slots=True)
  class ProviderHealth:
      provider: str
      capabilities: frozenset[MarketCapability]
      configured: bool
      last_error: str | None = None
  ```
- [x] Keep narrow protocols; do not replace them with one `MarketDataSource`.
- [x] In `providers_wiring.py`, wrap OKX clients in a provider bundle that exposes health/capabilities and shares OKX CEX ticker cache between anchor/live paths.
- [x] Remove `dex_ws_enabled` field, property, default config line, and validation branch. `okx_dex_ws_configured` becomes true when URL + credentials exist.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_provider_capabilities.py tests/unit/test_settings.py -q
  ```
  Expected: pass.

### Task 5 — Live Write Budget, Command Workers Write Material Facts, And Notify

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/asset_market/services/anchor_price_observation.py`
- Create: `src/gmgn_twitter_intel/domains/asset_market/services/live_observation_policy.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/anchor_price_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py`
- Modify: `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py`
- Create: `src/gmgn_twitter_intel/app/runtime/wake_bus.py`
- Modify: `src/gmgn_twitter_intel/platform/config/settings.py`
- Test: `tests/unit/test_anchor_price_worker.py`
- Test: `tests/unit/test_live_observation_policy.py`
- Test: `tests/unit/test_live_price_gateway.py`
- Test: `tests/unit/test_resolution_refresh_worker.py`
- Test: `tests/benchmark/test_live_observation_write_budget.py`

- [x] `observe_anchor_prices()` writes `observation_kind="event_anchor"` via `insert_market_observation`.
- [x] Add config defaults:
  ```python
  live_observation_heartbeat_seconds: float = 60.0
  live_observation_min_price_change_pct: float = 0.005
  live_observation_min_write_interval_seconds: float = 5.0
  ```
- [x] Create `live_observation_policy.py`:
  ```python
  from dataclasses import dataclass
  from typing import Literal

  from gmgn_twitter_intel.domains.asset_market.types.market_observation import MarketObservation


  _GATE_FIELDS = (
      "holders",
      "liquidity_usd",
      "market_cap_usd",
      "volume_24h_usd",
      "open_interest_usd",
  )


  @dataclass(frozen=True, slots=True)
  class LiveObservationPersistDecision:
      should_persist: bool
      reason: Literal[
          "first_seen",
          "heartbeat",
          "significant_price_change",
          "gate_field_change",
          "provider_state_change",
          "debounced",
          "not_material",
      ]


  def should_persist_live_observation(
      *,
      previous: MarketObservation | None,
      candidate: MarketObservation,
      now_ms: int,
      heartbeat_ms: int = 60_000,
      min_price_change_pct: float = 0.005,
      min_write_interval_ms: int = 5_000,
      provider_state_changed: bool = False,
      dex_floor_fields_changed: bool = False,
  ) -> LiveObservationPersistDecision:
      if previous is None:
          return LiveObservationPersistDecision(True, "first_seen")
      if provider_state_changed:
          return LiveObservationPersistDecision(True, "provider_state_change")
      if dex_floor_fields_changed or _gate_field_presence_changed(previous, candidate):
          return LiveObservationPersistDecision(True, "gate_field_change")

      elapsed_ms = max(0, int(now_ms) - int(previous.observed_at_ms))
      if elapsed_ms < min_write_interval_ms:
          return LiveObservationPersistDecision(False, "debounced")
      if elapsed_ms >= heartbeat_ms:
          return LiveObservationPersistDecision(True, "heartbeat")
      if _price_change_pct(previous, candidate) >= min_price_change_pct:
          return LiveObservationPersistDecision(True, "significant_price_change")
      return LiveObservationPersistDecision(False, "not_material")


  def _gate_field_presence_changed(previous: MarketObservation, candidate: MarketObservation) -> bool:
      for field in _GATE_FIELDS:
          if (getattr(previous, field) is None) != (getattr(candidate, field) is None):
              return True
      return False


  def _price_change_pct(previous: MarketObservation, candidate: MarketObservation) -> float:
      if previous.price_usd is None or candidate.price_usd is None:
          return 0.0
      previous_price = float(previous.price_usd)
      if previous_price <= 0:
          return 0.0
      return abs(float(candidate.price_usd) - previous_price) / previous_price
  ```
- [x] Policy rules:
  - `previous is None` returns `first_seen`.
  - `provider_state_changed` returns `provider_state_change`.
  - Gate field missing/present changes and caller-detected DEX floor crossings return `gate_field_change`.
  - If `now_ms - previous.observed_at_ms < min_write_interval_ms`, return `debounced` unless provider state or gate fields changed.
  - If `now_ms - previous.observed_at_ms >= heartbeat_ms`, return `heartbeat`.
  - If both prices exist and previous price is positive, persist only when relative change is `>= min_price_change_pct`.
  - Otherwise return `not_material`.
- [x] Unit tests in `tests/unit/test_live_observation_policy.py` cover these exact behaviors:
  - `test_first_seen_persists`: previous observation is absent, decision is `should_persist=True`, reason is `first_seen`.
  - `test_flat_frame_inside_heartbeat_is_not_material`: same price, same gate field presence, elapsed time below heartbeat, decision is `should_persist=False`.
  - `test_sub_threshold_price_change_is_not_material`: price moves by `0.0049`, threshold is `0.005`, decision is `should_persist=False`.
  - `test_price_change_at_threshold_persists`: price moves by `0.005`, elapsed time is above `min_write_interval_ms`, decision reason is `significant_price_change`.
  - `test_heartbeat_persists_even_without_price_change`: elapsed time is `>= heartbeat_ms`, decision reason is `heartbeat`.
  - `test_missing_to_present_gate_field_persists`: previous `holders=None`, candidate `holders=10`, decision reason is `gate_field_change`.
  - `test_provider_state_change_bypasses_debounce`: elapsed time is below `min_write_interval_ms`, `provider_state_changed=True`, decision reason is `provider_state_change`.
- [x] Benchmark test in `tests/benchmark/test_live_observation_write_budget.py` simulates `100 targets * 5 fps * 10 minutes` with sub-threshold jitter and asserts:
  ```python
  assert raw_frame_count == 300_000
  assert persisted_count <= 1_500
  assert persisted_count / raw_frame_count <= 0.005
  ```
- [x] Run the benchmark before wiring live writes:
  ```bash
  uv run pytest tests/unit/test_live_observation_policy.py tests/benchmark/test_live_observation_write_budget.py -q
  ```
  Expected: pass and persisted rows stay within budget.
- [x] `LivePriceGateway._payload_from_dex()` and `_payload_from_cex()` update the in-process latest cache on every valid frame, build a `MarketObservation` candidate, call `should_persist_live_observation` with the configured heartbeat, price-change, and debounce values, and call `insert_market_observation` with `observation_kind="decision_latest"` only when the returned decision has `should_persist=True`.
- [x] `LivePriceGateway` emits `wake_bus.notify_market_observation_written()` only after a persisted material observation.
- [x] Raw WS fan-out may remain available for debug/recent display, but Token Radar business cache patches must use the persisted `decision_latest` payload shape only.
- [x] `AnchorPriceWorker` constructor takes `wake_bus: WakeBus | None`; remove `on_observations_written`.
- [x] `ResolutionRefreshWorker` removes inline `observe_anchor_prices()` and `rebuild_token_radar_windows()` calls; after resolution write it calls `wake_bus.notify_resolution_updated(lookup_keys=sorted(affected_lookup_keys))`.
- [x] `wake_bus.py` exposes:
  ```python
  class WakeBus:
      def __init__(self, conn_factory: Callable[[], Any]) -> None
      def notify_market_observation_written(self, *, target_type: str, target_id: str) -> None
      def notify_resolution_updated(self, *, lookup_keys: Sequence[str]) -> None
      def notify_token_radar_updated(self, *, window: str, scope: str) -> None
  ```
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_anchor_price_worker.py tests/unit/test_live_observation_policy.py tests/unit/test_live_price_gateway.py tests/unit/test_resolution_refresh_worker.py tests/benchmark/test_live_observation_write_budget.py -q
  ```
  Expected: pass.

### Task 6 — Projection Reads Facts And Builds MarketContext

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py`
- Test: `tests/unit/test_token_radar_source_query.py`
- Test: `tests/unit/test_token_radar_projection.py`

- [x] Replace `token_market_price_baselines` join with LATERAL joins:
  ```sql
  LEFT JOIN LATERAL (
    SELECT *
    FROM price_observations
    WHERE price_observations.source_resolution_id = token_intent_resolutions.resolution_id
      AND price_observations.observation_kind = 'event_anchor'
    ORDER BY observed_at_ms DESC, observation_id DESC
    LIMIT 1
  ) event_anchor_observation ON true

  LEFT JOIN LATERAL (
    SELECT *
    FROM price_observations
    WHERE price_observations.subject_type = token_intent_resolutions.target_type
      AND price_observations.subject_id = token_intent_resolutions.target_id
      AND price_observations.observation_kind = 'decision_latest'
      AND price_observations.observed_at_ms <= %s
    ORDER BY observed_at_ms DESC, observation_id DESC
    LIMIT 1
  ) decision_latest_observation ON true
  ```
- [x] Rename `_market()` to `_market_context()` and return:
  ```python
  {
      "event_anchor": {"target_type": "Asset", "target_id": "asset-1"} | None,
      "decision_latest": {"target_type": "Asset", "target_id": "asset-1"} | None,
      "readiness": {
          "anchor_status": "ready" | "missing",
          "latest_status": "live" | "fresh" | "stale" | "missing",
          "dex_floor_status": "ready" | "missing_fields" | "below_floor",
          "missing_fields": ["holders"],
          "stale_fields": ["decision_latest"]
      }
  }
  ```
- [x] Remove `price_status="anchor_only"`, `live_price_persisted`, and old split `anchor_*` fields from runtime snapshot output.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_token_radar_source_query.py tests/unit/test_token_radar_projection.py -q
  ```
  Expected: pass.

### Task 7 — Scoring Fail-Closed And Cohort No-Signal

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py`
- Test: `tests/unit/test_factor_snapshot.py`
- Test: `tests/unit/test_token_radar_apply_cross_section.py`

- [x] `_gates()` reads DEX floors from `market.decision_latest`; missing `holders`, `liquidity_usd`, or `market_cap_usd` appends blocker reason `<field>_unverified`.
- [x] `risk_reasons` keeps `market_metadata_missing`, but high alert eligibility is false when required fields are missing.
- [x] Add `MIN_COHORT_SIZE = 10`.
- [x] `rank_within_cohort()` returns all `None` when rankable cohort size is below 10 or all scores tie.
- [x] Add `normalization.cohort_status` values `ready`, `insufficient`, `all_tied`.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_factor_snapshot.py tests/unit/test_token_radar_apply_cross_section.py -q
  ```
  Expected: pass.

### Task 8 — Projection Worker LISTEN/Catch-up And One Writer

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/runtime/token_resolution_refresh.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/repositories/projection_repository.py`
- Test: `tests/unit/test_token_radar_projection_worker.py`
- Test: `tests/unit/test_token_radar_idempotency.py`

- [x] Remove `_wake_event` and `request_rebuild()`.
- [x] Add a listener loop that wakes on `market_observation_written` and `resolution_updated`.
- [x] Keep `interval_seconds` catch-up so missed NOTIFY cannot stall projection.
- [x] `rebuild_token_radar_windows()` remains available for CLI/manual rebuild but no runtime worker other than projection worker calls it.
- [x] After each successful window write, call `wake_bus.notify_token_radar_updated(window, scope)`.
- [x] Architecture test asserts `resolution_refresh_worker.py` does not import `rebuild_token_radar_windows`.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_idempotency.py tests/architecture/test_src_domain_architecture.py -q
  ```
  Expected: pass.

### Task 9 — Pulse Candidate Worker Main Loop

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py`
- Modify: `src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Test: `tests/unit/test_pulse_candidate_worker.py`
- Test: `tests/unit/test_pulse_candidate_gate.py`

- [x] Run `PulseCandidateWorker.run()` as normal `asyncio.create_task`.
- [x] Delete `_start_threaded_async_worker` and `_watch_threaded_worker`.
- [x] Pulse worker listens to `token_radar_updated` and also polls at configured interval.
- [x] Gate reads `market.decision_latest` and `normalization.cohort_status`.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/test_pulse_candidate_gate.py -q
  ```
  Expected: pass.

### Task 10 — Query/SURFACE Hard Cut

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py`
- Modify: `src/gmgn_twitter_intel/domains/token_intel/read_models/token_target_social_timeline_service.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/ws.py`
- Test: `tests/unit/test_token_radar_repository.py`
- Test: `tests/integration/test_cli.py`

- [x] Delete `_overlay_live_market`.
- [x] `_public_row()` returns `market` from factor snapshot directly.
- [x] Top-level `anchor_price` and `live_market` are removed from `/api/token-radar` rows.
- [x] WS `live_market_update` payload carries material `market.decision_latest` shape for cache patching.
- [x] Update CLI output keys to `market.event_anchor` and `market.decision_latest`.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_token_radar_repository.py tests/integration/test_cli.py -q
  ```
  Expected: pass.

### Task 11 — Frontend Single Cache And Material Live Updates

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/useIntelSocket.ts`
- Modify: `web/src/features/live/useLiveData.ts`
- Modify: `web/src/features/live/liveMarketUpdatePatch.ts`
- Modify: `web/src/store/useTraderStore.ts`
- Modify: `web/src/domain/tokenTarget.ts`
- Modify: `web/src/components/TokenRadarRow.tsx`
- Modify: `web/src/components/TokenTargetPage.tsx`
- Modify: `web/src/components/SearchIntelPage.tsx`
- Test: `web/src/features/live/liveMarketUpdatePatch.test.ts`
- Test: `web/src/lib/tokenRadar.test.ts`
- Test: `web/src/components/TokenRadarRow.test.tsx`
- Test: `web/src/components/__tests__/TokenTargetPage.routing.test.tsx`

- [x] `useIntelSocket` accepts `onLiveMarketUpdate?: (payload: LiveMarketUpdatePayload) => void` and calls it for every material `live_market_update` frame emitted by the backend.
- [x] Keep `liveMarketUpdates` array only for debug/recent display; business patch uses callback.
- [x] `useLiveData` passes callback to patch query cache; it no longer reads `socket.liveMarketUpdates[0]`.
- [x] `TokenTargetPage` uses shared token radar store/query hook; delete direct `getApi("/api/token-radar")`.
- [x] Move `isDexMarket` to `web/src/domain/tokenTarget.ts`.
- [x] Components read `item.market.event_anchor` and `item.market.decision_latest`.
- [x] Run:
  ```bash
  cd web
  npm test -- --run web/src/features/live/liveMarketUpdatePatch.test.ts web/src/lib/tokenRadar.test.ts web/src/components/TokenRadarRow.test.tsx web/src/components/__tests__/TokenTargetPage.routing.test.tsx
  ```
  Expected: pass.

### Task 12 — IO State And Snapshot Gate Observability

**Files:**
- Modify: `src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py`
- Modify: `src/gmgn_twitter_intel/integrations/gmgn/direct_ws.py`
- Modify: `src/gmgn_twitter_intel/domains/ingestion/runtime/collector_service.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Test: `tests/unit/test_okx_dex_ws_client.py`
- Test: `tests/unit/test_gmgn_token_payload.py`

- [x] Add WS connection states `disconnected`, `connecting`, `authenticating`, `subscribed`, `streaming`, `failed`.
- [x] Add `last_state_change_at_ms` and structured log on state transition.
- [x] Add snapshot gate outcomes `immediate_complete`, `debounced_complete`, `debounced_timeout`, `non_tw_channel`.
- [x] `/api/status` exposes provider states and snapshot gate counters.
- [x] Run:
  ```bash
  uv run pytest tests/unit/test_okx_dex_ws_client.py tests/unit/test_gmgn_token_payload.py -q
  ```
  Expected: pass.

### Task 13 — Generated Docs And Contract Tests

**Files:**
- Modify: `docs/CONTRACTS.md`
- Modify: `docs/generated/cli-help.md`
- Modify: `docs/generated/ws-protocol.md`
- Modify: `tests/architecture/test_no_factor_snapshot_fallback.py`
- Modify: `tests/golden/test_token_radar_corpus.py`

- [x] Regenerate CLI help:
  ```bash
  uv run gmgn-twitter-intel --help > docs/generated/cli-help.md
  ```
- [x] Update no-fallback test to ban runtime references to `_overlay_live_market`, `token_market_price_baselines`, `liveMarketUpdates[0]`, and old top-level `live_market` fallback.
- [x] Update golden corpus expected snapshot to new market schema.
- [x] Run:
  ```bash
  uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py tests/golden/test_token_radar_corpus.py -q
  ```
  Expected: pass.

### Task 14 — Hard Cut Rebuild And Verification

**Files:**
- Create: `docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-verification-cn.md`
- Modify: `docs/TECH_DEBT.md` only if verification leaves explicit follow-up.

- [x] Apply migration locally:
  ```bash
  uv run alembic upgrade head
  ```
- [x] Truncate/rebuild derived read models on seeded local DB:
  ```sql
  TRUNCATE TABLE token_radar_rows, projection_runs, projection_offsets, pulse_candidates;
  ```
- [x] Rebuild projections:
  ```bash
  uv run gmgn-twitter-intel token-radar rebuild --window 5m --scope all --limit 100
  uv run gmgn-twitter-intel token-radar rebuild --window 1h --scope all --limit 100
  ```
- [x] Check no old runtime fallback remains:
  ```bash
  rg "_overlay_live_market|token_market_price_baselines|liveMarketUpdates\\[0\\]|anchor_price_usd|live_market_usd" src web tests
  ```
  Expected: no runtime matches; migration/docs matches allowed only when explicitly named in verification.
- [x] Run full verification:
  ```bash
  make check-all
  ```
  Expected: exit code 0.
- [x] Record full output in verification artefact before declaring complete.

## Storage / Migration Detail

### Source And Material Facts Preserved

- `events`
- `event_entities`
- `token_evidence`
- `token_intents`
- `token_intent_resolutions`
- `token_intent_lookup_keys`
- `registry_assets`
- `asset_identity_evidence`
- `asset_identity_current`
- `price_observations`

### Derived State Rebuilt

- `token_radar_rows`
- `projection_runs`
- `projection_offsets`
- `pulse_candidates`

### Runtime Read Removed

- `token_market_price_baselines`

## PR / Commit Breakdown

This is one hard-cut plan. Use multiple commits for reviewability, but merge only after all commits pass together.

1. **Commit 1 — docs and markers**: Task 1.
2. **Commit 2 — market fact model and migration**: Tasks 2 and 3.
3. **Commit 3 — providers, write budget, and fact writers**: Tasks 4 and 5.
4. **Commit 4 — projection and scoring schema**: Tasks 6 and 7.
5. **Commit 5 — wake/catch-up and pulse main loop**: Tasks 8 and 9.
6. **Commit 6 — API/WS/UI hard cut**: Tasks 10 and 11.
7. **Commit 7 — observability and generated docs**: Tasks 12 and 13.
8. **Commit 8 — verification artefact**: Task 14.

## Rollout Order

1. Stop service workers.
2. Confirm `tests/benchmark/test_live_observation_write_budget.py` passes with production-like target count and configured thresholds.
3. Apply Alembic migration, including `price_observations` kind/month partition shape.
4. Deploy code.
5. Truncate derived read models.
6. Rebuild hot Token Radar windows.
7. Start service workers.
8. Verify `/readyz`, `/api/token-radar`, material WS live update, Signal Pulse overview, and frontend TokenTarget page.
9. Run production smoke SQL from the verification section.

## Rollback

This hard cut does not preserve old runtime compatibility. Rollback is operational:

1. Stop service workers.
2. Restore previous application version.
3. Run Alembic downgrade for revision `20260513_0036`.
4. Rebuild old derived read models using the previous version's projection command.
5. Restart service workers.

Source/social facts and material market facts are preserved across rollback. Derived rows may be regenerated by either version.

## Acceptance Test Commands

- AC1 market schema:
  ```bash
  uv run pytest tests/unit/test_token_radar_projection.py::test_projection_emits_market_context_event_anchor_and_decision_latest -q
  ```
- AC2 no API overlay:
  ```bash
  uv run pytest tests/architecture/test_no_factor_snapshot_fallback.py::test_no_runtime_market_overlay_fallbacks -q
  ```
- AC3 one writer:
  ```bash
  uv run pytest tests/architecture/test_src_domain_architecture.py::test_token_radar_rows_has_single_runtime_writer -q
  ```
- AC4 DEX fail-closed:
  ```bash
  uv run pytest tests/unit/test_factor_snapshot.py::test_dex_missing_market_fields_block_high_alert -q
  ```
- AC5 cohort no-signal:
  ```bash
  uv run pytest tests/unit/test_token_radar_apply_cross_section.py::test_small_or_all_tied_cohort_returns_no_signal -q
  ```
- AC6 frontend material live patch:
  ```bash
  cd web && npm test -- --run web/src/features/live/liveMarketUpdatePatch.test.ts
  ```
- AC7 live write budget:
  ```bash
  uv run pytest tests/benchmark/test_live_observation_write_budget.py -q
  ```
- AC8 full gate:
  ```bash
  make check-all
  ```

## Verification

Create `docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-verification-cn.md` from `docs/superpowers/_templates/verification-template.md`. The work is not complete until `make check-all` full output is pasted there with exit code 0.
