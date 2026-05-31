# Spec — CEX Detail Snapshot And Agent Context

> 2026-05-27 hard-cut update: CEX OI board run-ledger identity is retired.
> Detail snapshots may read the current board rows/publication state, but must
> not depend on `cex_oi_radar_runs` or run-id serving FKs.

**Status**: Draft
**Date**: 2026-05-21
**Owner**: qinghuan / Codex
**Related**: `docs/superpowers/plans/active/2026-05-21-cex-binance-hard-cut-plan-cn.md`, `docs/ARCHITECTURE.md`, `src/parallax/domains/pulse_lab/ARCHITECTURE.md`

## Background

项目已经把 CEX hard cut 到 Binance USDT 永续：`TokenTargetRepository.target_identity()` 对 `CexToken` 只选择 `provider='binance'`, `feed_type='cex_swap'`, `quote_symbol='USDT'`, `status='canonical'` 的 price feed（`src/parallax/domains/token_intel/repositories/token_target_repository.py:49`、`src/parallax/domains/token_intel/repositories/token_target_repository.py:66`、`src/parallax/domains/token_intel/repositories/token_target_repository.py:71`）。CEX 最新行情也按 Binance canonical price feed 查 `market_ticks.target_type='cex_symbol'` 和 `target_id=provider:native_market_id`（`src/parallax/domains/token_intel/repositories/token_target_repository.py:106`、`src/parallax/domains/token_intel/repositories/token_target_repository.py:125`、`src/parallax/domains/token_intel/repositories/token_target_repository.py:128`）。

现有 Token Case 详情页已经支持 `Asset` 和 `CexToken` 路由，并订阅该 target 的 live market updates（`web/src/features/token-case/ui/TokenCaseRoute.tsx:17`、`web/src/features/token-case/ui/TokenCaseRoute.tsx:23`、`web/src/features/token-case/ui/TokenCaseRoute.tsx:42`、`web/src/features/token-case/ui/TokenCaseRoute.tsx:97`）。前端通过 `/api/token-case` 拉 dossier，通过 `/api/target-posts` 拉分页帖子（`web/src/features/token-case/api/useTokenCase.ts:32`、`web/src/features/token-case/api/useTokenCase.ts:36`、`web/src/features/token-case/api/useTokenCase.ts:88`、`web/src/features/token-case/api/useTokenCase.ts:91`）。后端 `/api/token-case` 由 `TokenCaseService.dossier()` 组合 target identity、timeline、posts、profile 和 `market_live`（`src/parallax/app/surfaces/api/routes_search.py:120`、`src/parallax/app/surfaces/api/routes_search.py:141`、`src/parallax/domains/token_intel/read_models/token_case_service.py:39`、`src/parallax/domains/token_intel/read_models/token_case_service.py:77`）。当前 `market_live` 只从最新 tick 或 live gateway snapshot 取价格、volume、OI 等薄字段（`src/parallax/domains/token_intel/read_models/token_case_service.py:86`、`src/parallax/domains/token_intel/read_models/token_case_service.py:89`、`web/src/features/token-case/model/buildTokenCaseViewModel.ts:194`、`web/src/features/token-case/model/buildTokenCaseViewModel.ts:201`、`web/src/features/token-case/model/buildTokenCaseViewModel.ts:202`）。

项目已有 CEX OI radar foundation：`cex_derivative_series`, `cex_oi_radar_runs`, `cex_oi_radar_rows` 在 Alembic 中创建（`src/parallax/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py:16`、`src/parallax/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py:40`、`src/parallax/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py:65`）。`CexOiRadarBoardWorker` 以 Binance `price_feeds` universe 为输入，拉 ticker/premium/OI history 后写 board rows（`src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py:43`、`src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py:49`、`src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py:17`、`src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py:27`）。`/api/cex/radar-board` 只读最新成功或 partial board（`src/parallax/app/surfaces/api/routes_cex.py:15`、`src/parallax/app/surfaces/api/routes_cex.py:21`、`src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:142`）。

`coinglass-cli` 已作为 pinned Git dependency 打进项目（`pyproject.toml:20`、`pyproject.toml:177`、`pyproject.toml:178`）。它适合提供 CoinGlass 衍生品补充数据，但 live probe 已显示 history 类命令可能 timeout，因此不得进入页面请求路径。

Pulse Agent 当前是 evidence-first：先构建 sealed `PulseEvidencePacket`，LLM 只能引用 packet 内 refs（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:5`、`src/parallax/domains/pulse_lab/ARCHITECTURE.md:13`）。Packet 的 market contract 现在只暴露 price、venue、instrument、volume、open_interest、funding 等字段（`src/parallax/domains/pulse_lab/services/evidence_packet_builder.py:420`、`src/parallax/domains/pulse_lab/services/evidence_packet_builder.py:437`、`src/parallax/domains/pulse_lab/services/evidence_packet_builder.py:452`、`src/parallax/domains/pulse_lab/services/evidence_packet_builder.py:453`、`src/parallax/domains/pulse_lab/services/evidence_packet_builder.py:454`）。CEX completeness gate 目前只要求 fresh price、source、instrument 和 market/metric ref（`src/parallax/domains/pulse_lab/services/evidence_completeness_gate.py:51`、`src/parallax/domains/pulse_lab/services/evidence_completeness_gate.py:84`、`src/parallax/domains/pulse_lab/services/evidence_completeness_gate.py:89`）。

## Problem

CEX 详情页和 Agent 对 CEX 的理解仍停在“社交传播 + 最新价格/OI 薄字段”层面，无法解释一个 Binance 永续标的的衍生品状态：OI 24h 变化、CVD、funding、long/short、清算支撑压力位、数据新鲜度和缺口都没有被产品化，也没有作为 sealed snapshot 进入 Agent evidence packet。

## First Principles

1. **页面和 Agent 不直接打外部 provider。** Provider raw frames / CoinGlass responses 只能由 worker 采集后落入 PostgreSQL facts 或 rebuildable read models；HTTP/WS/API 只读数据库或 live gateway。现有架构已经要求 facts-first、append-only market facts 和 public projection read path（`docs/ARCHITECTURE.md:33`、`docs/ARCHITECTURE.md:42`、`docs/ARCHITECTURE.md:54`）。
2. **每个衍生品 read model 只有一个 runtime writer。** 新增 CEX snapshot / levels / board 必须声明 writer，不能让 API、Agent、前端各自写缓存。现有架构明确 one writer per read model（`docs/ARCHITECTURE.md:59`），`docs/WORKERS.md` 已把 `cex_oi_radar_board` 记录为当前 CEX OI board writer（`docs/WORKERS.md:112`）。
3. **Agent 只能分析 sealed snapshot。** Pulse 的 LLM 阶段不得主动获取事实，只能综合 packet refs；已有 Pulse architecture 明确“不让 LLM 获取 critical facts”（`src/parallax/domains/pulse_lab/ARCHITECTURE.md:13`、`src/parallax/domains/pulse_lab/ARCHITECTURE.md:85`）。

## Goals

- G1. CEX 详情页在 `CexToken` target 上展示一个完整的 Binance USDT 永续衍生品 snapshot：price/mark、funding、volume 24h、OI current、OI delta 1h/4h/24h、CVD delta 1h/4h/24h、long/short、top trader positioning、nearest liquidation/support/resistance bands、freshness 和 data gaps。
- G2. `/api/token-case` 对 `target_type=CexToken` 返回 bounded CEX detail snapshot；p95 API latency 在已有数据库数据可用时不超过 300 ms，且不会调用 Binance/CoinGlass。
- G3. CEX Agent evidence packet 包含同一份 snapshot 的 refs 和 freshness metadata；非 abstain CEX 决策必须引用至少一个 social ref、一个 market/metric ref，并在有 levels/flow 数据时引用对应 ref。
- G4. CoinGlass enrichment 失败或 timeout 时，详情页和 Agent 仍能用 Binance baseline 给出 degraded/partial 状态，不阻塞主实时流。
- G5. 数据规模受控：默认全 universe worker 只采集 Binance baseline；CoinGlass levels/CVD 只覆盖 radar top-K、recent Pulse candidates、operator-selected watchlist，不默认扫全 527 个 symbol 的重型数据。

## Non-goals

- N1. 不在 GET `/api/token-case`、`/api/cex/*` 或前端 render 中直接调用 `coinglass-cli`、Binance REST、浏览器 transport。
- N2. 不输出交易指令、入场位、止损、止盈、杠杆建议。支撑/压力 level 只能作为“清算密集区/风险带/观察条件”展示。
- N3. 不恢复 OKX CEX 兼容路径，不引入 `provider=okx` 的 CEX fallback。
- N4. 不把 CoinGlass raw heatmap 全量长期存储为产品事实；只保留 bounded normalized bands 和短 TTL raw payload for audit/debug。
- N5. 不把 CEX detail 做成独立于 Token Case 的第二套社交流水线；社交 timeline、posts、profile 继续由 Token Case / narrative read model 承担。

## Target Architecture

CEX 详情页是现有 Token Case 的 CEX-specialized detail surface。URL 仍以 `target_type=CexToken` 为 canonical target，CEX Radar Board 和 Token Radar 行都跳到同一个 token-case detail；页面根据 `target.target_type === "CexToken"` 展示 Derivatives Context 区块。

后台分成三层：

1. **Binance baseline layer**：覆盖全部 Binance USDT perpetual universe。它提供低成本、高覆盖的 price/mark、funding、volume、OI current、OI delta。当前 `cex_oi_radar_board` 可以演进为 baseline board writer，或拆出 `cex_derivatives_baseline` writer 后让 board 从 baseline snapshot 读。
2. **CoinGlass enrichment layer**：只覆盖 top-K / active targets。它提供 CVD history、long/short ratio、top trader positioning、liquidation levels / per-pair heatmap。它必须限流、超时、失败记账，并写入 normalized series / level bands。
3. **CEX detail snapshot read model**：每个 `binance:<SYMBOL>` 一条 latest snapshot，组合 baseline + enrichment + freshness + degraded reasons。它是 `/api/token-case`、`/api/cex/detail` 和 Pulse evidence packet 的共同读取对象。

前端布局：

- Hero：`$BTC · Binance USDT Perpetual`，显示 live price、mark、funding、OI、freshness。
- Metrics strip：`OI 24h`, `OI 4h`, `CVD 24h`, `Funding`, `Volume 24h`, `Data quality`。
- Main content：左侧保持 social propagation/timeline/bull-bear，右侧新增 Derivatives Context。
- Derivatives Context：`Leverage Context`、`Flow`、`Levels`、`Freshness` 四组。Levels 只展示价格带和相对当前价，不用“买/卖/止损”语言。
- Data gaps rail：明确显示 `CoinGlass CVD stale`, `levels unavailable`, `OI baseline fresh`, `Binance funding fresh` 等。

Agent 侧：

- `PulseEvidenceBuilder` 从 CEX detail snapshot 生成 `market_evidence` 和 `allowed_evidence_refs`。
- CEX route 的 `EvidenceCompletenessGate` 从“仅有 fresh price 就 complete”升级为“baseline complete + derivatives freshness 决定 max decision ceiling”。
- Prompt 输入不暴露 provider command 或 raw payload，只暴露 normalized snapshot、refs、freshness 和 data gaps。

## Conceptual Data Flow

```text
Binance USD-M REST
  -> cex_derivatives_baseline worker
  -> cex_derivative_series + cex_detail_snapshots
  -> /api/token-case(CexToken) + /api/cex/detail
  -> CEX detail page

CoinGlass browser/HTTP transport via coinglass-cli
  -> cex_coinglass_enrichment worker
  -> cex_derivative_series + cex_liquidation_level_bands + cex_detail_snapshots
  -> PulseEvidenceBuilder
  -> sealed PulseEvidencePacket
  -> tool-free Pulse Agent stages
```

Changed arrows:

- `CoinGlass -> worker -> DB` is new because CoinGlass can timeout and uses browser-like transport; existing API/read path cannot host it without causing page stalls.
- `cex_detail_snapshots -> PulseEvidenceBuilder` is new because Agent needs the same product snapshot the page sees, with refs and freshness, not a separate ad hoc market query.
- `/api/token-case -> CEX detail page` is extended, not replaced, because Token Case already owns `CexToken` identity, social timeline, posts, profile, and live market composition.

## Core Models

### CexDerivativePoint

Semantic time-series point for one symbol/metric/window.

- Identity: `provider`, `exchange`, `native_market_id`, `base_symbol`, `quote_symbol`, `metric`, `period`, `observed_at_ms`.
- Values: `value_numeric`, `value_usd`, optional `delta_abs`, optional `delta_pct`.
- Metrics: `open_interest`, `funding_rate`, `volume_24h`, `cvd`, `long_short_ratio`, `top_trader_long_short_ratio`.
- Invariant: point identity is unique by provider + symbol + metric + period + observed time.

### CexLiquidationLevelBand

Normalized support/resistance/liquidation pressure band derived from CoinGlass levels/heatmap.

- Identity: `provider='coinglass'`, `exchange='binance'`, `native_market_id`, `range`, `side`, `band_key`.
- Values: `price_low`, `price_high`, `mid_price`, `distance_pct_from_mark`, `size`, `intensity`, `level`, `observed_at_ms`.
- Semantics: `side` describes liquidation pressure side from source; product copy uses `upper_pressure`, `lower_support`, `nearby_cluster`, not trade commands.
- Invariant: page returns only top N nearest/significant bands, never an unbounded raw heatmap.

### CexDetailSnapshot

Latest bounded read model for one CEX instrument.

- Identity: `target_type='CexToken'`, `target_id`, `exchange='binance'`, `native_market_id`, `quote_symbol='USDT'`.
- Baseline: `price_usd`, `mark_price`, `funding_rate`, `volume_24h_usd`, `open_interest_usd`, `oi_change_pct_1h`, `oi_change_pct_4h`, `oi_change_pct_24h`.
- Enrichment: `cvd_delta_1h`, `cvd_delta_4h`, `cvd_delta_24h`, `long_short_ratio`, `top_trader_position_ratio`, `level_bands`.
- Quality: `baseline_status`, `coinglass_status`, `freshness_status`, `degraded_reasons`, `observed_at_ms`, `computed_at_ms`, `source_refs`.
- Invariant: snapshot is read-only for API/Agent; only the owning worker writes it.

### CexAgentSnapshot

Packet-safe projection of `CexDetailSnapshot`.

- Includes: normalized metrics, freshness, data gaps, and refs.
- Excludes: raw CoinGlass payload, command output, browser transport details, request signing details.
- Invariant: every claimable metric must have a stable ref id.

## Interface Contracts

### GET `/api/token-case`

For `target_type=CexToken`, response adds `cex_detail` while preserving existing `target`, `profile`, `timeline`, `posts`, and `market_live`.

Semantics:

- `market_live` remains the compact latest price snapshot for shared UI compatibility.
- `cex_detail` is the richer derivatives snapshot.
- If snapshot is missing, return `cex_detail.status='missing'` and data gaps; do not fail the whole dossier.
- If CoinGlass is stale/unavailable, return Binance baseline with `coinglass_status='stale' | 'unavailable'`.

### GET `/api/cex/detail`

Optional dedicated read endpoint for CEX-only consumers.

Inputs:

- `target_type=CexToken` + `target_id`, or `exchange=binance` + `symbol=BTCUSDT`.

Output:

- Same `CexDetailSnapshot` shape as `token-case.cex_detail`.
- Read-only. No provider calls, no refresh side effect.

### GET `/api/cex/radar-board`

Existing endpoint remains board-focused, but rows may include compact snapshot fields: OI 24h, CVD 24h, nearest level distance, freshness. It does not become the detail endpoint.

### Pulse Evidence Packet

For CEX route, packet adds:

- `market_evidence[0].cex_snapshot`
- `market_evidence[0].derivatives`
- `market_evidence[0].levels`
- refs such as `metric:cex:oi_24h:<target>`, `metric:cex:cvd_24h:<target>`, `level:cex:liquidation:<target>:<band_key>`.

Error modes:

- Missing baseline price => hard block / abstain.
- Fresh baseline but missing CoinGlass => partial evidence; decision ceiling should not exceed `token_watch` unless other route policy explicitly allows baseline-only CEX decisions.
- Stale levels/CVD => visible data gaps; LLM may mention missing/stale context but cannot infer it.

## Acceptance Criteria

- AC1. WHEN a user opens a `CexToken` detail page with a fresh Binance baseline snapshot THEN the page SHALL render price/mark, funding, volume 24h, OI current, OI 1h/4h/24h deltas, provider, and observed time without any external provider request from the HTTP handler.
- AC2. WHEN CoinGlass enrichment is fresh for that CEX target THEN the page SHALL render CVD 1h/4h/24h and nearest upper/lower liquidation level bands with freshness labels.
- AC3. WHEN CoinGlass enrichment times out or is stale THEN the page SHALL keep Binance baseline visible, mark CoinGlass fields degraded, and show explicit data gaps instead of spinners or blank cards.
- AC4. WHEN `/api/token-case?target_type=CexToken` is called THEN response SHALL include `cex_detail` with bounded arrays and SHALL complete from DB/read models only.
- AC5. WHEN Pulse builds a CEX evidence packet THEN `market_evidence` SHALL include `cex_snapshot` refs for every non-null CEX metric supplied to the Agent.
- AC6. WHEN a CEX Agent output claims OI, CVD, funding, or liquidation levels THEN `ClaimEvidenceVerifier` SHALL require the corresponding `metric:cex:*` or `level:cex:*` ref.
- AC7. WHEN baseline price is missing for CEX route THEN `EvidenceCompletenessGate` SHALL abstain before LLM execution.
- AC8. WHEN baseline is fresh but CVD/levels are missing THEN CEX route SHALL be partial, with decision ceiling no higher than watch/token-watch unless later policy explicitly changes this.
- AC9. WHEN CEX enrichment workers run across the default universe THEN CoinGlass-heavy commands SHALL be limited to configured top-K / active targets and SHALL not scan all Binance symbols by default.
- AC10. WHEN the worker is already running and a new interval fires THEN it SHALL skip or continue from a lease-safe checkpoint, never start overlapping CoinGlass/Binance fetch passes for the same writer.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| CoinGlass timeout stalls details | High | All CoinGlass calls live in worker; API returns stale/degraded snapshot. |
| DB grows from high-frequency series | Medium | Store hourly/delta points and bounded level bands; apply retention/downsampling. |
| Agent treats levels as trade instructions | High | Packet labels levels as observational liquidation bands; prompts and verifier ban entry/stop/target language. |
| Duplicate snapshot writers split truth | High | Declare one writer per read model in `docs/WORKERS.md` and local CEX architecture doc. |
| Full Binance OI scan overloads app/Postgres | Medium | Batch limit, local run lock, worker lease, per-run timeout, no overlap. |
| Page and Agent disagree | Medium | Both read the same `CexDetailSnapshot`; Agent receives a packet-safe projection, not a separate query. |
| Stale CoinGlass data creates false confidence | Medium | Every field carries observed/computed time and freshness; gate lowers decision ceiling on stale enrichment. |

## Evolution Path

The first version should ship with Binance baseline + CoinGlass levels/CVD for top-K. Later expansions can add per-exchange comparison, option-implied context, basis, liquidation heatmap visualization, and cross-venue OI divergence. The design should not foreclose multi-exchange support, but runtime defaults and target identity remain Binance USDT perpetual until a new hard-cut/spec changes that product decision.

## Alternatives Considered

- Direct CoinGlass call from CEX detail page — rejected because history/CVD commands can timeout and would make page latency depend on browser/provider transport.
- Full CoinGlass scan for all 527 Binance symbols every cycle — rejected because CVD/levels are heavier than Binance baseline and would create avoidable provider pressure and storage growth.
- Separate `/cex/:symbol` social page independent of Token Case — rejected because Token Case already owns `CexToken` identity, posts, social timeline, profile, and market live composition.
- Let Agent call CoinGlass as a tool — rejected because Pulse architecture is sealed evidence packet only; LLM fact acquisition would break replay and audit.
- Store every raw liquidation heatmap point forever — rejected because product needs nearest/significant bands, while raw provider payloads are bulky and provider-shaped.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use Binance USDT perpetual as canonical CEX identity; read CEX detail from DB/read models; include freshness and data gaps; keep Agent evidence packet sealed. |
| Ask first | Raising CEX decisions above watch/token-watch when CoinGlass enrichment is missing; enabling full-universe CoinGlass scans; adding non-Binance exchanges. |
| Never | Direct provider calls from page/API/Agent; OKX CEX fallback; unbounded raw heatmap response to frontend; trading instructions from levels. |
