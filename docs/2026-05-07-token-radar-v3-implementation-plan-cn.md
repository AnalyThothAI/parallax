# Token Radar V3 Hard-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut Token Radar from mention-level attribution to event-level token intent, so `$VERSA 0x2cc0db4f8977accadb5b7da59c5923e14328eba3` resolves as one explainable token row, market failures are diagnosable, unresolved attention cannot become `driver`, and price/outcome closure uses the same asset/venue identity.

**Architecture:** `events -> span-aware entities -> token_evidence -> token_intents -> token_intent_resolutions -> assets/venues -> market_provider_observations -> asset_market_snapshots -> token_radar_rows -> backend decision -> frontend render -> asset_signal_outcomes`.

**Tech Stack:** Python 3.13, FastAPI, psycopg/PostgreSQL/Alembic, pytest, TypeScript, React, Vite, Vitest.

---

## 推演结论

对照当前前后端源码后，V3 spec 的方向可以彻底解决问题，但只有硬切完整链路才成立。局部修复会继续留下结构性水位。

当前 runtime 路径是：

```text
GMGN frame
-> collector/normalizer
-> IngestService.ingest_event()
-> extract_entities()
-> event_entities
-> build_asset_mentions()
-> AssetResolver.resolve_many()
-> asset_attributions
-> AssetRepository.asset_flow_rows()
-> AssetFlowService.asset_flow()
-> /api/asset-flow
-> web assetFlowRowToTokenItem()
-> TokenRadarRow
```

V3 runtime 路径必须变成：

```text
GMGN frame
-> collector/normalizer
-> IngestService.ingest_event()
-> span-aware entities
-> token_evidence
-> token_intents
-> token_intent_resolutions
-> market_provider_observations
-> asset_market_snapshots
-> token_radar_rows
-> /api/asset-flow
-> TokenRadarRow render-only
```

核心判断：

- 只修 `AssetResolver._resolve_ca()` 不够：VERSA 的 CA 可能能同步解析，但 `$VERSA` 仍会作为 `asset:ambiguous:VERSA` 单独进入 Radar。
- 只做同事件 symbol+CA merge 不够：当前 `ExtractedEntity` 没有 span、surface、sentence/locality，merge 只能靠同 event 猜测，遇到多个 symbol/CA 会错配。
- 只改 worker backfill 不够：worker 现在按 symbol job/CA job 重写 mention class，不能重跑整个 event intent。
- 只改 `asset_flow_rows()` 不够：`asset_posts`、timeline、trading attention、notifications 仍读 `asset_attributions`，会继续双算或错误关联。
- 只改 frontend decision 不够：后端 API 仍 request-time 聚合原始 attribution，market status 仍被压扁。
- 只加 projection 表不够：当前 `asset_flow_window_snapshots` 没有 writer/read path，生产 API 仍读即时 SQL。
- 只留旧 `TokenRepository` outcome 不够：Radar 用 `asset_market_snapshots`，结算用 `token_market_snapshots`，价格闭环会分叉。

因此修复是否彻底，取决于这些硬门槛：

- Radar 的业务主语是 `token_intents.intent_id`，不是 mention、asset alias、token_id 或 frontend object。
- 一个 event-intent 在一个 window 内只贡献一次。
- unresolved/ambiguous 是 resolution 状态，不是 fake asset。
- provider backfill 写 observation/candidate 后重跑 intent resolver。
- market status 区分 identity、venue、provider、refresh、history。
- score/decision 只在 backend projection 写入。
- frontend 删除 Radar scoring synthesis。
- live outcome settlement 只读 asset/venue market snapshots。

## 当前源码问题地图

### Ingest And Extraction

当前文件：

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- `src/gmgn_twitter_intel/pipeline/tweet_text.py`
- `src/gmgn_twitter_intel/pipeline/asset_mention_builder.py`
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`

观察：

- EVM CA 使用 `finditer()`，但 `ExtractedEntity` 不保存 `span_start/span_end`。
- cashtag 使用 `CASHTAG_RE.findall()`，span 已经丢失。
- `_event_text()` 把 primary/reference 拼接成一个 string，surface 边界也丢失。
- `build_asset_mentions()` 把 CA 和 cashtag 变成独立 mention。
- `IngestService` 在同一个事务中直接持久化 `asset_attributions`，把 mention 级解析变成生产主路径。

V3 影响：

- 必须新增 span-aware extractor 和 token evidence builder。
- runtime ingest 必须停止把 mention-level attribution 作为 Radar source。

### Identity Resolution

当前文件：

- `src/gmgn_twitter_intel/pipeline/asset_resolver.py`
- `src/gmgn_twitter_intel/pipeline/asset_resolution_worker.py`
- `src/gmgn_twitter_intel/storage/asset_repository.py`

观察：

- `_resolve_ca()` 只有 chain/address 都存在时才 `_resolve_direct_dex()`；无链 CA 直接 `upsert_unresolved_ca()` 并 queue job。
- `AssetRepository.candidates_for_ca()` 已支持 no-chain exact address lookup，但 `_resolve_ca()` 没调用。
- `_process_ca_job()` 只调用 `reassign_ca_attributions()`。
- `_process_symbol_job()` 只调用 `reassign_symbol_attributions()`。
- `reassign_*` 按 mention 改 attribution，不会合并同一 intent 的显示证据。

V3 影响：

- Resolver 输入必须是 `token_intent`。
- CA exact local lookup 必须在 provider 前执行。
- Provider worker 必须写 `market_provider_observations` 和 `token_intent_resolution_candidates`，再重跑 intent resolution。

### Market And Projection

当前文件：

- `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py`
- `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- `src/gmgn_twitter_intel/storage/asset_repository.py`
- `src/gmgn_twitter_intel/storage/projection_repository.py`

观察：

- `asset_market_snapshots` 是 venue-aware，这是可复用基础。
- `_market()` 缺 snapshot 时固定返回 `market_observation_status=provider_not_found`，混淆 no venue、未配置、查无结果、错误、刷新中。
- `asset_flow_rows()` 直接从 `asset_attributions` group by `asset_id`，没有 event-intent dedupe。
- migration 已建 `asset_attention_buckets`、`asset_flow_window_snapshots`，但 `ops rebuild-asset-flow` 只是调用 request-time `AssetFlowService`，没有写 read model。

V3 影响：

- 保留 `asset_market_snapshots`，新增 provider observation 和 token_radar_rows。
- `AssetFlowService` 改为只读 `token_radar_rows`。
- `ProjectionRepository` 保留通用 offset/run 机制，新增真实 `TokenRadarProjection` writer。

### API, WS, Notifications

当前文件：

- `src/gmgn_twitter_intel/api/http.py`
- `src/gmgn_twitter_intel/api/ws.py`
- `src/gmgn_twitter_intel/api/app.py`
- `src/gmgn_twitter_intel/pipeline/notification_rules.py`

观察：

- `/api/asset-flow` 暴露 `asset-flow-v1`，source 是 `asset_attributions`。
- WS replay/live payload 仍包含 `asset_attributions`。
- status type 前端没有 `asset_resolution` 和 `asset_market_sync`。
- notification token rules 又在 `_asset_scores()` 重算一套简化 score。
- `TokenRepository` 和 `TokenSignalRepository` 仍作为 runtime dependency 挂载。

V3 影响：

- API/WS payload 必须暴露 token intents/resolutions。
- Notifications 必须读 `token_radar_rows.score_json/decision`，不能重算。
- app runtime 要把旧 token repos 移到 archive/debug/ops，不参与 live Radar/outcome。

### Frontend

当前文件：

- `web/src/App.tsx`
- `web/src/api/types.ts`
- `web/src/components/TokenRadarRow.tsx`
- `web/src/components/TokenRadarTable.tsx`
- `web/src/components/DecisionTag.tsx`
- `web/src/lib/format.ts`
- `web/src/lib/venue.ts`

观察：

- `Decision = "driver" | "watch" | "discard"`，缺 `investigate`。
- `AssetFlowRow.decision` 接受 `"watch" | "investigate" | string`，但转换为 `TokenFlowItem` 时丢失语义。
- `assetFlowRowToTokenItem()` 重算 heat、quality、propagation、tradeability、timing、opportunity、decision。
- unresolved/ambiguous attention 因 heat 足够高可以被 UI 标成 driver。
- `TokenRadarRow` 展示 `TokenFlowItem`，不是 backend Radar row。

V3 影响：

- 删除 runtime `assetFlowRowToTokenItem()` scoring。
- UI 使用 `TokenRadarRowData` 直接渲染后端 `score/decision/data_health`。
- `investigate` 成为一等 decision。

## Implementation Tasks

### Task 1: Add Golden Corpus First

- [ ] Create `tests/golden/test_token_radar_v3_corpus.py`.
- [ ] Add fixtures for:
  - VERSA cashtag plus Base CA.
  - VERSA symbol-only.
  - HANTA unresolved attention.
  - BTC CEX symbol-only.
  - EVM CA no chain with local venue.
  - EVM CA no chain without provider hit.
  - multiple symbols plus one CA.
  - one symbol plus multiple CAs.
  - GMGN payload with chain/address.
  - provider not configured.
  - provider error/rate limit.
- [ ] Create shared helpers in `tests/factories_token_radar_v3.py`.
- [ ] Mark corpus tests with deterministic timestamps and no network.

Required first regression:

```python
def test_versa_symbol_and_ca_build_one_intent(open_repos):
    event = make_event(
        "event-versa",
        text="很不错的一个项目，挺有格局的dev， $VERSA 0x2cc0db4f8977accadb5b7da59c5923e14328eba3",
        received_at_ms=1_777_800_000_000,
    )
    result = open_repos.ingest.ingest_event(event, is_watched=True)

    intents = open_repos.token_intents.intents_for_event("event-versa")
    assert len(intents) == 1
    assert intents[0]["display_symbol"] == "VERSA"
    assert intents[0]["address_hint"].lower() == "0x2cc0db4f8977accadb5b7da59c5923e14328eba3"
    assert result.token_resolutions[0]["identity_status"] == "resolved"
```

Exit:

- These tests fail on the current code path for structural reasons, not due to fixture wiring.

### Task 2: Add V3 Schema Migration

- [ ] Create `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0006_token_radar_v3_intents.py`.
- [ ] Add columns to `event_entities`:
  - `text_surface TEXT`
  - `span_start BIGINT`
  - `span_end BIGINT`
  - `sentence_id BIGINT`
  - `local_group_key TEXT`
- [ ] Create:
  - `token_evidence`
  - `token_intents`
  - `token_intent_evidence`
  - `token_intent_resolutions`
  - `token_intent_resolution_candidates`
  - `market_provider_observations`
  - `token_radar_rows`
  - `asset_signal_snapshots`
  - `asset_signal_outcomes`
- [ ] Add uniqueness constraints:
  - one active resolution per intent by partial unique index on `token_intent_resolutions(intent_id)` where status is not `superseded`.
  - one active radar row per projection/window/scope/lane/rank/computed time.
  - one evidence row per `event_id/source_kind/source_id/evidence_type/raw_value/span_start/span_end`.
- [ ] Add indexes for:
  - `token_evidence(event_id)`
  - `token_evidence(normalized_symbol)`
  - `token_evidence(lower(address_hint))`
  - `token_intents(event_id)`
  - `token_intent_resolutions(intent_id, decision_time_ms DESC)`
  - `market_provider_observations(provider, request_kind, request_key, observed_at_ms DESC)`
  - `token_radar_rows(projection_version, window, scope, lane, computed_at_ms DESC, rank ASC)`

Migration test updates:

- [ ] Update `tests/test_postgres_schema.py` to assert the new DDL names.
- [ ] Update `tests/test_postgres_schema_runtime.py` to assert runtime table presence.
- [ ] Add a migration downgrade assertion for new indexes and tables.

Exit:

```bash
uv run pytest tests/test_postgres_schema.py tests/test_postgres_schema_runtime.py
```

### Task 3: Split Repositories By Context

- [ ] Create `src/gmgn_twitter_intel/storage/token_evidence_repository.py`.
- [ ] Create `src/gmgn_twitter_intel/storage/token_intent_repository.py`.
- [ ] Create `src/gmgn_twitter_intel/storage/intent_resolution_repository.py`.
- [ ] Create `src/gmgn_twitter_intel/storage/market_repository.py`.
- [ ] Create `src/gmgn_twitter_intel/storage/token_radar_repository.py`.
- [ ] Create `src/gmgn_twitter_intel/storage/asset_signal_repository.py`.
- [ ] Update `src/gmgn_twitter_intel/storage/repository_session.py` to expose:
  - `token_evidence`
  - `token_intents`
  - `intent_resolutions`
  - `market`
  - `token_radar`
  - `asset_signals`
- [ ] Keep `AssetRepository` responsible only for asset registry methods used by V3:
  - `upsert_dex_asset`
  - `upsert_cex_instrument`
  - `candidates_for_ca`
  - `candidates_for_symbol`
  - `get_asset`
  - `get_venue`
  - `venue_for_cex_instrument`
- [ ] Move V3 market snapshot methods to `MarketRepository`:
  - `insert_market_snapshot`
  - `market_snapshot_at_or_before`
  - `market_snapshot_at_or_after`
  - `market_snapshots_between`
  - `nearest_market_snapshot`
  - `dex_venues_needing_market_refresh`

Repository tests:

- [ ] Add `tests/test_token_evidence_repository.py`.
- [ ] Add `tests/test_token_intent_repository.py`.
- [ ] Add `tests/test_intent_resolution_repository.py`.
- [ ] Add `tests/test_market_repository.py`.
- [ ] Add `tests/test_token_radar_repository.py`.

Exit:

```bash
uv run pytest tests/test_token_evidence_repository.py tests/test_token_intent_repository.py tests/test_intent_resolution_repository.py tests/test_market_repository.py tests/test_token_radar_repository.py
```

### Task 4: Make Entity Extraction Span-Aware

- [ ] Add a `TextSurface` dataclass in `src/gmgn_twitter_intel/pipeline/entity_extractor.py`:

```python
@dataclass(frozen=True, slots=True)
class TextSurface:
    surface: str
    text: str
```

- [ ] Extend `ExtractedEntity` with:
  - `text_surface`
  - `span_start`
  - `span_end`
  - `sentence_id`
  - `local_group_key`
- [ ] Replace cashtag `findall()` with `finditer()`.
- [ ] Add deterministic sentence/local group assignment:
  - sentence increments on `.`, `!`, `?`, `。`, `！`, `？`, newline.
  - local group key is `"{surface}:{sentence_id}"`.
- [ ] Add `extract_entities_from_surfaces(surfaces: Sequence[TextSurface])`.
- [ ] Keep `extract_entities(text)` as a non-runtime wrapper used only by old tests and debug commands.
- [ ] Update `src/gmgn_twitter_intel/storage/entity_repository.py` to persist span fields.
- [ ] Update `_entity_payload()` in `src/gmgn_twitter_intel/pipeline/ingest_service.py`.

Tests:

- [ ] Update `tests/test_entity_extractor.py`.
- [ ] Add assertions that `$VERSA` and `0x2cc0...` share `local_group_key`.
- [ ] Add assertions that primary/reference surfaces do not share offsets.

Exit:

```bash
uv run pytest tests/test_entity_extractor.py
```

### Task 5: Build Token Evidence

- [ ] Create `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`.
- [ ] Convert span-aware entities to token evidence:
  - CA -> `evidence_type="ca"`, `strength="strong"`.
  - cashtag -> `evidence_type="cashtag"`, `strength="medium"`.
  - exact provider URL -> `evidence_type="provider_url"`, `strength="strong"`.
  - GMGN payload -> `evidence_type="gmgn_token_payload"`, `strength="strong"`.
- [ ] Include `source_kind/source_id/text_surface/span/local_group_key`.
- [ ] Derive payload evidence id from `event_id + token_snapshot.chain + token_snapshot.address`.
- [ ] Persist via `TokenEvidenceRepository.insert_many()`.

Tests:

- [ ] Add `tests/test_token_evidence_builder.py`.
- [ ] Verify VERSA text yields one CA evidence and one cashtag evidence in the same local group.
- [ ] Verify GMGN payload adds one strong payload evidence even if text is empty.

Exit:

```bash
uv run pytest tests/test_token_evidence_builder.py
```

### Task 6: Build Event Token Intents

- [ ] Create `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`.
- [ ] Implement deterministic clustering:
  - GMGN payload chain/address creates one intent.
  - CA-only creates one intent per CA.
  - cashtag-only creates one symbol-only intent.
  - cashtag plus CA in same `local_group_key` creates one intent with CA as primary and cashtag as display alias.
  - multiple symbols plus one CA attaches only after exact symbol match to resolved/provider candidate.
  - one symbol plus multiple CAs remains separate unless local grouping is one-to-one.
- [ ] Write `token_intents` and `token_intent_evidence`.
- [ ] Make intent ids stable from event id plus sorted primary evidence ids.

Tests:

- [ ] Add `tests/test_token_intent_builder.py`.
- [ ] Cover all golden corpus clustering cases.

Exit:

```bash
uv run pytest tests/test_token_intent_builder.py tests/golden/test_token_radar_v3_corpus.py::test_versa_symbol_and_ca_build_one_intent
```

### Task 7: Implement Intent Resolver V3

- [ ] Create `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`.
- [ ] Resolver input is one intent plus its evidence rows.
- [ ] Implement decision priority:
  - GMGN payload chain/address.
  - exact CA with chain hint.
  - exact CA without chain hint, local exact CA lookup through `AssetRepository.candidates_for_ca(chain=None, address=...)`.
  - exact CA without local hit, queue provider exact contract search.
  - symbol-only local CEX/DEX conservative selection.
  - provider candidates with margin.
  - ambiguous/unresolved/rejected.
- [ ] Write one active `token_intent_resolutions` row.
- [ ] Write `token_intent_resolution_candidates`.
- [ ] Supersede previous active resolution for the same intent inside one transaction.
- [ ] Never create `asset:unresolved:*` or `asset:ambiguous:*` assets for V3.

Tests:

- [ ] Add `tests/test_token_intent_resolver.py`.
- [ ] Add local no-chain CA exact lookup test for Base VERSA.
- [ ] Add symbol-only conservative selection tests.
- [ ] Add ambiguous tests for multiple candidates.

Exit:

```bash
uv run pytest tests/test_token_intent_resolver.py tests/golden/test_token_radar_v3_corpus.py
```

### Task 8: Rewrite Ingest To Intent Runtime

- [ ] Update `src/gmgn_twitter_intel/pipeline/ingest_service.py`.
- [ ] Build surfaces:
  - `primary` from `event.content.text`.
  - `reference` from `event.reference.text`.
  - `payload` from `event.token_snapshot`.
- [ ] Runtime write order inside one transaction:

```text
events
event_entities
token_evidence
token_intents
token_intent_evidence
token_intent_resolutions
asset_market_snapshots from GMGN payload when resolved
account alerts from active token intent resolutions
enrichment job
```

- [ ] Return `token_intents` and `token_resolutions` from `IngestedEvent`.
- [ ] Stop returning runtime `asset_attributions` except under archive/debug code paths outside collector publish.
- [ ] Update collector publish payload to include `token_intents` and `token_resolutions`.
- [ ] Update `tests/test_api_websocket.py` and ingest tests.

Exit:

```bash
uv run pytest tests/test_ingest_service.py tests/test_api_websocket.py tests/golden/test_token_radar_v3_corpus.py
```

### Task 9: Provider Observation And Re-Resolution Worker

- [ ] Create `src/gmgn_twitter_intel/pipeline/token_resolution_worker.py`.
- [ ] Replace mention-oriented jobs with intent-oriented jobs:
  - `intent_exact_contract_resolution`
  - `intent_symbol_resolution`
  - `intent_market_refresh`
- [ ] Create `MarketRepository.insert_provider_observation()`.
- [ ] On provider result:
  - write observation status.
  - upsert real asset/venue.
  - write candidates for affected intent.
  - rerun `TokenIntentResolver`.
  - write market snapshot when provider includes market data.
- [ ] Preserve provider adapter isolation:
  - OKX DEX calls remain in `market/okx_dex_client.py`.
  - OKX CEX calls remain in `market/okx_cex_client.py`.
- [ ] `not_configured` status is written when credentials are absent.
- [ ] `not_found` status is written only after configured provider returns no matching result.

Tests:

- [ ] Add `tests/test_token_resolution_worker.py`.
- [ ] Cover CA provider hit merging display symbol evidence through intent resolution.
- [ ] Cover provider not configured, not found, error, rate limited.

Exit:

```bash
uv run pytest tests/test_token_resolution_worker.py tests/test_asset_resolution_worker.py
```

### Task 10: Market Semantics And Venue-Specific Tradeability

- [ ] Create `src/gmgn_twitter_intel/pipeline/asset_market_observer.py` or extend `asset_market_sync.py` through `MarketRepository`.
- [ ] Keep OKX CEX universe sync but write through `MarketRepository`.
- [ ] Keep OKX DEX price refresh but write provider observations and market snapshots through `MarketRepository`.
- [ ] Add `market_status_for_resolution()`:
  - unresolved/ambiguous/rejected -> `no_venue`.
  - resolved without active venue -> `no_venue`.
  - provider missing config -> `provider_not_configured`.
  - job queued or stale beyond policy -> `pending_refresh`.
  - provider exact not found -> `provider_not_found`.
  - provider error -> `provider_error`.
  - rate limit -> `rate_limited`.
  - fresh snapshot -> `ready`.
  - stale usable snapshot -> `stale`.
  - current snapshot with missing baseline -> `insufficient_history`.
- [ ] Split tradeability features by venue:
  - DEX requires chain/address/price/liquidity when available.
  - CEX spot requires exchange/inst_id/price/volume.
  - CEX swap requires exchange/inst_id/price/volume/open_interest when available.

Tests:

- [ ] Add `tests/test_market_status_v3.py`.
- [ ] Add venue-specific tradeability tests.
- [ ] Keep existing CEX freshness tests and update expected status names.

Exit:

```bash
uv run pytest tests/test_market_status_v3.py tests/test_tradeability_scoring.py tests/test_asset_market_sync.py
```

### Task 11: Implement Token Radar Projection V3

- [ ] Create `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`.
- [ ] Create `src/gmgn_twitter_intel/retrieval/token_radar_service.py`.
- [ ] Projection builder reads:
  - active token intents.
  - active token intent resolutions.
  - events and author fields.
  - market snapshots.
  - provider observations.
  - previous radar rows for baseline.
- [ ] Projection builder writes `token_radar_rows`.
- [ ] Use existing scoring modules where possible:
  - `social_heat_scoring.py`
  - `discussion_quality_scoring.py`
  - `propagation_scoring.py`
  - `tradeability_scoring.py`
  - `timing_scoring.py`
  - `opportunity_scoring.py`
- [ ] Add hard gate before decision persistence:

```python
if identity_status in {"unresolved", "ambiguous", "rejected"} and decision == "driver":
    decision = "investigate"
```

- [ ] Projection dedupe key:

```text
window + scope + intent_id + event_id
```

- [ ] `token_radar_rows.source_event_ids_json` stores unique event ids per row.
- [ ] Projection source in API is `token_radar_rows`.

Tests:

- [ ] Add `tests/test_token_radar_projection.py`.
- [ ] Verify same event with VERSA symbol+CA creates one row.
- [ ] Verify unresolved attention row decision is `investigate`.
- [ ] Verify projection rows include market data health.

Exit:

```bash
uv run pytest tests/test_token_radar_projection.py tests/test_opportunity_scoring.py tests/test_timing_scoring.py
```

### Task 12: Hard-Cut HTTP And WS Contracts

- [ ] Update `src/gmgn_twitter_intel/retrieval/asset_flow_service.py` to become a wrapper over `TokenRadarService` or replace its use with `TokenRadarService`.
- [ ] `/api/asset-flow` reads `token_radar_rows`.
- [ ] Response projection:
  - `version="token-radar-v3"`
  - `source="token_radar_rows"`
- [ ] Row shape includes:
  - `intent`
  - `asset`
  - `primary_venue`
  - `attention`
  - `resolution`
  - `market`
  - `score`
  - `decision`
  - `data_health`
- [ ] Update `/api/search` through `TokenIntentSearchService`.
- [ ] Update `/api/asset-posts` and `/api/asset-social-timeline` to query by `intent_id` or resolved `asset_id` with event-intent dedupe.
- [ ] Update `PublicWebSocketHub`:
  - replay includes `token_intents`.
  - replay includes `token_resolutions`.
  - token filters match evidence/resolution, not only raw entities.
- [ ] Update `/api/status` to expose:
  - `token_resolution`
  - `asset_market_sync`
  - `token_radar_projection`
  - provider observation counts.

Tests:

- [ ] Update `tests/test_api_http.py`.
- [ ] Update `tests/test_api_websocket.py`.
- [ ] Add regression that `/api/asset-flow` projection source is not `asset_attributions`.

Exit:

```bash
uv run pytest tests/test_api_http.py tests/test_api_websocket.py
```

### Task 13: Frontend Render-Only Migration

- [ ] Update `web/src/api/types.ts`:
  - `Decision = "driver" | "watch" | "investigate" | "discard"`.
  - add `TokenRadarRowData`.
  - add `TokenRadarScoreBlock`.
  - add `TokenRadarMarketBlock`.
  - add `TokenRadarDataHealth`.
- [ ] Delete runtime score synthesis from `web/src/App.tsx`.
- [ ] Replace `assetFlowRowToTokenItem()` with a small mapper that only normalizes nullable fields for rendering, without changing score or decision.
- [ ] Update `sortTokenItems()` to sort by server score:
  - opportunity -> `row.score.opportunity.score`.
  - heat -> `row.score.heat.score`.
  - quality -> `row.score.quality.score`.
  - propagation -> `row.score.propagation.score`.
  - timing -> `row.score.timing.score`.
- [ ] Update `countDecisions()` to include `investigate`.
- [ ] Update `DecisionTag` and `formatDecision()` to render `investigate`.
- [ ] Update `TokenRadarRow` to display:
  - `intent.display_symbol` first.
  - `asset.symbol` second.
  - short venue address last.
  - market status from backend.
  - timing status from backend.
  - decision from backend.
- [ ] Update venue links to use `primary_venue`.
- [ ] Keep drawer and selection keyed by `intent_id` when present, then `asset_id`, then venue address.

Frontend tests:

- [ ] Add an API row with `decision="investigate"`, unresolved identity, high heat. Assert UI renders `investigate`, not `driver`.
- [ ] Add VERSA row. Assert only one row label `$VERSA` is rendered.
- [ ] Add CEX BTC row. Assert OKX link still works without chain/address.
- [ ] Add DEX resolved row. Assert GMGN link uses chain/address.

Exit:

```bash
npm test -- --run
```

### Task 14: Notifications Read Server Decisions

- [ ] Update `src/gmgn_twitter_intel/pipeline/notification_rules.py`.
- [ ] Delete `_asset_scores()` from the notification runtime path.
- [ ] Notification rules read from `token_radar_rows.score_json` and `decision`.
- [ ] Rules can filter on:
  - heat score.
  - quality score.
  - opportunity score.
  - decision.
  - data health.
- [ ] Notification payload includes `intent_id`, `asset_id`, `venue_id`, `score_version`, and `decision`.

Tests:

- [ ] Update notification rule tests to ensure unresolved `investigate` rows do not fire tradeable-token alerts.
- [ ] Add test that notification uses backend score exactly.

Exit:

```bash
uv run pytest tests/test_notification_rules.py
```

### Task 15: Asset/Venue Outcome Closure

- [ ] Create `src/gmgn_twitter_intel/pipeline/asset_signal_settlement.py`.
- [ ] Create `AssetSignalRepository`.
- [ ] Projection writes `asset_signal_snapshots` for rows that cross configured decision thresholds.
- [ ] Settlement selects entry/exit from `asset_market_snapshots` by `asset_id + primary_venue_id`.
- [ ] Replace live CLI/API outcome paths with asset signal equivalents:
  - `asset-signal-snapshots`
  - `asset-signal-outcomes`
  - `asset-signal-evaluations`
- [ ] Keep old token signal reads under archive/debug command names only.
- [ ] Update `account_quality_service.py` to read asset outcomes.

Tests:

- [ ] Add `tests/test_asset_signal_settlement.py`.
- [ ] Add entry/exit venue-specific tests for DEX and CEX.
- [ ] Add missing entry/exit status tests.

Exit:

```bash
uv run pytest tests/test_asset_signal_settlement.py tests/test_account_quality_service.py
```

### Task 16: Quarantine Old Runtime Paths

- [ ] Update `src/gmgn_twitter_intel/api/app.py`:
  - remove `TokenRepository` and `TokenSignalRepository` from normal runtime dataclass fields.
  - mount old repos only for archive/debug routes when explicitly invoked.
- [ ] Update `src/gmgn_twitter_intel/storage/repository_session.py`:
  - V3 normal session exposes V3 repositories.
  - old token repos are not available to hot path services.
- [ ] Move `MarketObservationWorker` old token-market path to archive/debug package or remove from runtime task startup.
- [ ] Move `token_signal_settlement.py` out of live ops command set.
- [ ] Add project-structure test:

```python
def test_token_radar_v3_runtime_does_not_import_old_token_market_paths():
    forbidden = {
        "TokenRepository",
        "TokenSignalRepository",
        "token_market_snapshots",
        "token_signal_snapshots",
    }
    runtime_files = [
        ROOT / "src/gmgn_twitter_intel/api/app.py",
        ROOT / "src/gmgn_twitter_intel/api/http.py",
        ROOT / "src/gmgn_twitter_intel/pipeline/ingest_service.py",
        ROOT / "src/gmgn_twitter_intel/pipeline/token_radar_projection.py",
    ]
    text = "\n".join(path.read_text() for path in runtime_files)
    for item in forbidden:
        assert item not in text
```

Exit:

```bash
uv run pytest tests/test_project_structure.py
```

### Task 17: CLI And Ops Trace

- [ ] Add CLI commands in `src/gmgn_twitter_intel/cli.py`:
  - `ops audit-token-intent --event-id ...`
  - `ops audit-token-intent --intent-id ...`
  - `ops token-intent-health --window 24h`
  - `ops provider-health`
  - `ops rebuild-token-radar --window 1h --scope all`
  - `ops trace-token-radar-row --row-id ...`
- [ ] `rebuild-token-radar` writes `token_radar_rows` and updates `projection_offsets`.
- [ ] `trace-token-radar-row` prints:

```text
event
entities
token_evidence
token_intent
resolution candidates
active resolution
asset
venue
provider observations
market snapshots
radar row
asset signal snapshot
outcome
```

Tests:

- [ ] Update `tests/test_cli.py`.
- [ ] Verify `ops rebuild-token-radar` changes row count.
- [ ] Verify `ops audit-token-intent` prints VERSA evidence and resolution in one trace.

Exit:

```bash
uv run pytest tests/test_cli.py tests/test_projection_repository.py
```

### Task 18: End-To-End Verification

- [ ] Run backend full checks:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

- [ ] Run frontend checks:

```bash
npm test -- --run
npm run build
```

- [ ] Run targeted VERSA scenario against local app:
  - initialize database.
  - ingest VERSA event.
  - run token radar projection.
  - query `/api/asset-flow?window=1h&scope=all`.
  - assert exactly one VERSA row.
  - assert row decision is not `driver` unless identity, venue, and market gates pass.
  - assert market status is not collapsed to `provider_not_found`.
- [ ] Run `rg` gates:

```bash
rg "assetFlowRowToTokenItem|opportunityScore|const decision: Decision" web/src
rg "asset_attributions" src/gmgn_twitter_intel/retrieval src/gmgn_twitter_intel/api src/gmgn_twitter_intel/pipeline
rg "TokenRepository|TokenSignalRepository|token_market_snapshots|token_signal_snapshots" src/gmgn_twitter_intel
```

Acceptable `rg` results:

- frontend has no runtime opportunity score synthesis.
- `asset_attributions` appears only in archive/debug/migration/parity code.
- old token repos appear only in archive/debug/migration tests or removed commands.

## Rollout Sequence

1. Land schema and repositories with no runtime switch.
2. Land span-aware extraction and evidence builder behind V3 ingest call path in tests.
3. Land intent builder and resolver with golden corpus.
4. Land provider observation and worker re-resolution.
5. Land token radar projection writer.
6. Switch `/api/asset-flow` to V3 read model.
7. Switch frontend to render-only Radar row.
8. Switch notifications and outcome settlement.
9. Remove or archive old token runtime paths.
10. Run full verification and inspect VERSA trace.

## Production Gates

The implementation is not complete until all gates pass:

- `$VERSA 0x2cc0db4f8977accadb5b7da59c5923e14328eba3` creates one intent and one Radar row.
- Same-event symbol+CA uses locality evidence, not blind event-level merge.
- No-chain CA checks local exact venue before provider.
- Provider backfill re-runs intent resolver.
- `asset_flow-v1` is not the production API source.
- `/api/asset-flow` reports `projection.version=token-radar-v3`.
- `/api/asset-flow` reports `projection.source=token_radar_rows`.
- Unresolved/ambiguous rows can only be `investigate` or `discard`.
- Frontend renders `investigate`.
- Frontend does not compute opportunity or decision.
- Notifications do not compute token opportunity independently.
- Market status distinguishes `no_venue`, `provider_not_configured`, `provider_not_found`, `provider_error`, `rate_limited`, `pending_refresh`, `ready`, `stale`, and `insufficient_history`.
- Outcome settlement uses `asset_market_snapshots`.
- Old token market/signal runtime is removed from live Radar and outcome closure.

## Concrete File Checklist

Create:

- `src/gmgn_twitter_intel/storage/alembic/versions/20260507_0006_token_radar_v3_intents.py`
- `src/gmgn_twitter_intel/storage/token_evidence_repository.py`
- `src/gmgn_twitter_intel/storage/token_intent_repository.py`
- `src/gmgn_twitter_intel/storage/intent_resolution_repository.py`
- `src/gmgn_twitter_intel/storage/market_repository.py`
- `src/gmgn_twitter_intel/storage/token_radar_repository.py`
- `src/gmgn_twitter_intel/storage/asset_signal_repository.py`
- `src/gmgn_twitter_intel/pipeline/token_evidence_builder.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_builder.py`
- `src/gmgn_twitter_intel/pipeline/token_intent_resolver.py`
- `src/gmgn_twitter_intel/pipeline/token_resolution_worker.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_observer.py`
- `src/gmgn_twitter_intel/pipeline/token_radar_projection.py`
- `src/gmgn_twitter_intel/pipeline/asset_signal_settlement.py`
- `src/gmgn_twitter_intel/retrieval/token_radar_service.py`
- `src/gmgn_twitter_intel/retrieval/token_intent_search_service.py`
- `src/gmgn_twitter_intel/retrieval/token_intent_trace_service.py`
- `tests/factories_token_radar_v3.py`
- `tests/golden/test_token_radar_v3_corpus.py`
- `tests/test_token_evidence_builder.py`
- `tests/test_token_intent_builder.py`
- `tests/test_token_intent_resolver.py`
- `tests/test_token_resolution_worker.py`
- `tests/test_market_status_v3.py`
- `tests/test_token_radar_projection.py`
- `tests/test_asset_signal_settlement.py`

Modify:

- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`
- `src/gmgn_twitter_intel/storage/entity_repository.py`
- `src/gmgn_twitter_intel/storage/asset_repository.py`
- `src/gmgn_twitter_intel/storage/repository_session.py`
- `src/gmgn_twitter_intel/retrieval/asset_flow_service.py`
- `src/gmgn_twitter_intel/retrieval/asset_posts_service.py`
- `src/gmgn_twitter_intel/retrieval/asset_social_timeline_service.py`
- `src/gmgn_twitter_intel/retrieval/asset_search_service.py`
- `src/gmgn_twitter_intel/api/http.py`
- `src/gmgn_twitter_intel/api/ws.py`
- `src/gmgn_twitter_intel/api/app.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync.py`
- `src/gmgn_twitter_intel/pipeline/asset_market_sync_worker.py`
- `src/gmgn_twitter_intel/pipeline/notification_rules.py`
- `src/gmgn_twitter_intel/cli.py`
- `web/src/api/types.ts`
- `web/src/App.tsx`
- `web/src/components/TokenRadarRow.tsx`
- `web/src/components/TokenRadarTable.tsx`
- `web/src/components/DecisionTag.tsx`
- `web/src/lib/format.ts`
- `web/src/lib/venue.ts`
- `web/src/App.test.tsx`

Archive or remove from live runtime:

- `src/gmgn_twitter_intel/pipeline/asset_mention_builder.py`
- mention-level Radar use in `src/gmgn_twitter_intel/pipeline/asset_attribution.py`
- live worker use of `src/gmgn_twitter_intel/pipeline/market_observation_worker.py`
- live settlement use of `src/gmgn_twitter_intel/pipeline/token_signal_settlement.py`
- live endpoint use of old token signal commands.

## Final Readiness Check

Use these commands before claiming completion:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
npm test -- --run
npm run build
```

Use this product trace before shipping:

```bash
uv run gmgn-twitter-intel ops audit-token-intent --event-id event-versa
uv run gmgn-twitter-intel ops rebuild-token-radar --window 1h --scope all
uv run gmgn-twitter-intel asset-flow --window 1h --scope all --limit 20
```

Expected VERSA result:

- one intent;
- display symbol `VERSA`;
- one active resolution;
- one Radar row;
- market status explains exact reason;
- decision follows backend hard gate;
- frontend displays the same decision.
