# Event Anchor Capture Redesign 验证记录

日期：2026-05-15
分支：`codex/event-anchor-capture-redesign`
HEAD：本验证文件所在提交
Base：`e7d28e821a1557a41979cf0ba5959355907eaf83`

## 范围

本轮验证覆盖 `docs/superpowers/specs/active/2026-05-15-event-anchor-capture-redesign-cn.md`
和执行计划的硬切实现：

- active 代码、测试、文档不保留旧 `price_observations` / AnchorPriceWorker / message-anchor runtime 语义。
- 新事实表为 append-only `enriched_events` 与 `market_ticks`。
- Token Radar、Factor、Signal Pulse、Asset Flow 从 persisted ticks / factor snapshot market 读取市场事实。
- worker registry/settings/docs/generated 与新 worker key 一致。
- 不保留兼容性 fallback。

## 本地验证

| 命令 | 结果 |
| --- | --- |
| `uv run ruff check .` | PASS，`All checks passed!` |
| `uv run pytest` | PASS，`1092 passed, 14 skipped in 333.45s` |
| hard-cut `rg`：`message anchor|message-anchor|message_anchor|anchor price|anchor_price|price_observations|market_observation_written|AnchorPriceWorker|should_persist_live_observation`，扫描 `web src tests docs AGENTS.md CLAUDE.md`，排除 historical Alembic 与 `docs/superpowers` | PASS，无命中 |
| `uv run pytest tests/architecture/test_event_anchor_capture_redesign_contracts.py -q` | PASS，hard-cut guard 覆盖 `.html`、`.ts`、`.tsx` 与空格形式 legacy 文案 |
| temp `HOME` 下 `uv run alembic upgrade head` | PASS，exit 0 |
| temp `HOME` 下 `uv run parallax ops worker-status` | PASS，`ok: true`，返回 14 个 canonical workers |
| temp `HOME` 下 `make docs-generated` | PASS，exit 0 |
| `git diff --exit-code docs/generated` | PASS，无 diff |
| `cd web && npm ci` | PASS，568 packages installed，0 vulnerabilities |
| `cd web && npm run lint` | PASS，exit 0 |
| `cd web && npm test` | PASS，53 files / 163 tests passed |

全量 pytest 的 14 个 skipped 中，`test_docs_generated` 的 soft skip 来自用户当前
`~/.parallax/workers.yaml` 仍含旧 worker 字段；已用 temp `HOME` 单独验证
`make docs-generated` 为 clean。其余 skips 为既有 TECH_DEBT 标注或无 source rows 场景。

## DB 抽样

执行的 join 抽样：

```sql
SELECT e.event_id, e.resolution_id, e.target_type, e.target_id, e.t_event_ms,
       e.tick_id AS anchor_tick_id, mt.tick_id AS joined_tick_id,
       mt.source_tier, mt.source_provider, mt.price_usd, mt.observed_at_ms
FROM enriched_events e
LEFT JOIN market_ticks mt ON mt.tick_id = e.tick_id
ORDER BY e.created_at_ms DESC
LIMIT 5;
```

当前本地数据库返回 `[]`，说明本地没有可展示的 recent enriched rows；schema 与迁移已由
`docs/generated/db-schema.md`、`test_postgres_schema.py`、`test_postgres_schema_runtime.py`
覆盖。

## 子代理复审

- Task 16 spec reviewer：PASS（确认 legacy runtime strings、source table、Signal Pulse、schema default、跨域边界均满足硬切要求）。
- Task 16 code-quality reviewer：PASS（确认 Signal Pulse latest precedence/top-level fallback removal、HTML hard-cut guard、schema default 修复）。
- Final blocker-only reviewer：PASS；指出 `web/tests` 中两个旧 worker-status mock key 作为 residual risk。
  已修复为 `token_capture_tier` / `market_tick_stream` / `market_tick_poll`，并把 hard-cut guard 扩展到 `.ts` / `.tsx`。
  Residual re-check：PASS。

## 风险备注

- `event_anchor` 与 `decision_latest` 仍是 public adapter payload keys，但来源被限定为
  `enriched_events` / `market_ticks` / `factor_snapshot.market`，不是旧 runtime fallback。
- `docs/generated/token-case-redesign-ui-mockup.html` 是 generated 下的静态 UI mockup；本轮为
  清理 active generated docs 中的旧 message-anchor 文案而更新。
