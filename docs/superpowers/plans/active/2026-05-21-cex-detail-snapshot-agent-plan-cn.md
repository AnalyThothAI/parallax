# CEX Detail Snapshot + Agent Evidence 落地计划

> Spec: `docs/superpowers/specs/active/2026-05-21-cex-detail-snapshot-agent-cn.md`
> Date: 2026-05-21

## 目标

把 CEX 详情页和 Agent 分析统一接到一个可重建的 `cex_detail_snapshots` read model：worker 离线聚合 Binance USDT 永续基础行情与 CoinGlass 衍生指标，API/frontend/agent 只读数据库 snapshot，不在请求链路实时调用 Binance 或 CoinGlass。

## 架构原则

- `cex_oi_radar_board` 是 CEX 派生读模型的唯一运行时写入者之一，本次 v1 复用它的 Binance 全市场扫描结果生成 detail snapshot。
- `cex_detail_snapshots` 是面向单标的详情与 Agent 的 read model，可删除重建，不作为业务事实源。
- 请求路径只读 PostgreSQL；外部接口调用留在 worker。
- Snapshot 要携带 freshness、degraded reasons、source refs，Agent 只能引用 snapshot 中的 ref，不凭空生成 OI/CVD/level 结论。
- CoinGlass 暂不可用或字段缺失时，详情页展示 baseline Binance 数据并标记 partial；Agent gate 降级为 watch，不硬阻断基础 CEX 分析。

## 数据模型

- 新增 `cex_detail_snapshots`
  - key: `snapshot_id = cex-detail:binance:<native_market_id>`
  - target: `target_type = CexToken`, `target_id = cex_token:<base>`
  - market: exchange、native_market_id、base/quote、price、mark、funding、volume、open_interest
  - derivatives: `oi_change_pct_1h/4h/24h`、`cvd_delta_1h/4h/24h`、long/short、top trader ratio
  - levels: `level_bands_json`，bounded support/resistance/liquidation bands
  - quality: status、baseline_status、coinglass_status、degraded_reasons_json、source_refs_json、observed_at_ms、computed_at_ms

## 后端任务

1. 写失败测试：
   - worker 扫描后写入 `cex_detail_snapshots`，且 `period=5m` 不冒充 `oi_change_pct_1h`。
   - `TokenCaseService` 对 `CexToken` 返回 `cex_detail`，非 CEX 返回 `None`。
   - Pulse evidence packet 包含 `cex_snapshot`、derivatives、level refs；CoinGlass 缺失时 gate 只降级 partial。
2. 新增 Alembic 迁移 `20260521_0074_cex_detail_snapshots.py`。
3. 新增 repository 与 snapshot builder。
4. `CexOiRadarBoardWorker` 在 radar rows 写入成功后，对 top-K 做可选 CoinGlass enrichment 并同步 upsert detail snapshot。
5. `RepositorySession` 注入新 repository。
6. `/api/token-case` 返回 `cex_detail`；新增只读 `/api/cex/detail` 便于调试。
7. 更新 OpenAPI schema 与生成类型。

## Agent 任务

1. `MarketEvidence` 增加 `cex_snapshot`、`derivatives`、`levels`、`data_gaps`。
2. Pulse evidence source repository 从 `cex_detail_snapshots` 读取 CEX snapshot。
3. Evidence builder 输出 `metric:cex:*` 与 `level:cex:*` refs。
4. Completeness gate:
   - 无 fresh price/source/instrument 仍 hard block。
   - 有 Binance baseline 但 CoinGlass 缺失时 partial，最高 `token_watch`。
   - 有 baseline + derivative/level enrichment 时 complete。

## 前端任务

1. 更新 contracts/view model 类型，新增 `cexDetail`。
2. Token Case 侧栏增加 CEX Derivatives 面板：
   - price/mark/funding/OI/volume
   - OI 1h/4h/24h 变化
   - CVD 1h/4h/24h
   - Long/short、top trader ratio
   - support/resistance/liquidation levels
   - freshness/degraded reasons
3. CEX 数据不存在时不渲染面板；partial 时展示 degraded 状态。
4. 补 view model 与组件测试。

## 文档与验证

1. 更新 `docs/WORKERS.md` 和 CEX domain 架构说明。
2. 运行后端相关单测：
   - `uv run pytest tests/unit/domains/cex_market_intel tests/unit/test_token_case_service.py tests/unit/test_pulse_evidence_packet_builder.py tests/unit/test_pulse_evidence_completeness_gate.py`
3. 运行前端相关测试：
   - `cd web && npm run test -- --run web/tests/unit/features/token-case/model/buildTokenCaseViewModel.test.ts web/tests/component/shared/ui/case-file/TokenCasePanel.test.tsx`
4. 运行合约生成/漂移检查。

## 暂不做

- 不在详情页请求链路实时调用 CoinGlass。
- 不把全量 CVD/level 历史落库；v1 只存当前 snapshot 的 bounded bands。
- 不保留 OKX 兼容代码路径。
- 不把 Binance universe sync 做成常驻 worker；合约 universe 仍由离线脚本/price_feeds 表维护。
