# 同链同名 token 审计与物理去重设计

> 范围：审计 + 物理 DROP 一次性脚本。不动 resolver 主路径（上游 fix 单独立项）。

## 1. 问题

线上 PG 库存量 `assets=15,004`，其中：

- 1,259 个 `(chain, symbol)` 组合在同链下存在 ≥ 2 个 asset
- 这些组合涉及 5,473 个 asset；裁到每链每符号 1 个真品需要删 **4,214 个 asset**（≈28%）
- `asset_venues.chain` 同时使用 `"eth"`（149 行）与 `"ethereum"`（1,667 行）—— 同地址会生成两个不同 `asset_id`（TROLL `0xf8ebf…` 实测重复）

TROLL 实测样本（截至 2026-05-12）：

| chain | address | mcap | liq | holders | 判定 |
|---|---|---:|---:|---:|---|
| solana | `5UUH9RTDi…` | 51M | 3.1M | **52,267** | 真 |
| solana | `5uBUCFsK…` | 95M | 23K | 134 | 假（low-float pump）|
| ethereum | `0xf8ebf…` | 3M | 702K | **15,824** | 真 |
| eth | `0xf8ebf…` | 3M | NULL | NULL | 重复行（链名 bug）|
| bsc | 4 个 | <15K | <15K | <972 | 全假 |

核心洞察：**holders 是最强真伪信号**。mcap 可低流通量伪造，liq 可短期拉，holders 难刷。

## 2. 目标

1. 同链同名场景：每组选出 1 个真品保留，其余物理 DROP
2. 链名规范化：`eth → ethereum`，同地址重复 asset 合并
3. 全程 dry-run / apply 两阶段，可重跑、可审、可回滚

非目标：

- 不动 resolver / token_evidence_builder 的注册门槛（上游 fix 走另一个 spec）
- 不处理跨链同名（`solana/TROLL` 与 `bsc/TROLL` 都保留各自的"链 winner"，由前端按 chain 展示区分）
- 不处理 `cex_tokens`（CEX 没有 chain+address 的同名歧义，已由 OKX inst_id 唯一）

## 3. 架构

一次性 Python 脚本 `scripts/audit_duplicate_tokens.py`，**不进 service runtime**，不挂 alembic migration（这是数据清理不是 schema 变更）。

```
scripts/audit_duplicate_tokens.py
  ├── phase1_normalize_chain_names    # eth → ethereum
  ├── phase2_dedup_chain_symbol       # 每组选 winner，其余 DROP
  │     ├── select_winner_in_db        # holders/liq/mcap 排序 + 阈值
  │     └── external_arbiter            # winner 未过阈时调 OKX → CoinGecko
  ├── write_audit_report                # markdown
  └── apply_drops                       # 单事务 DELETE
```

两阶段独立、可分别 `--only-phase1` / `--only-phase2` 跑。

## 4. 命令行

```bash
# Dry-run（不写库，只出报告）
uv run python scripts/audit_duplicate_tokens.py \
    --dry-run \
    --report docs/generated/duplicate-token-audit.md

# 单链单符号试跑
uv run python scripts/audit_duplicate_tokens.py \
    --dry-run --chain solana --symbol TROLL \
    --report /tmp/troll-audit.md

# Apply（先 pg_dump 再 DELETE，单事务）
uv run python scripts/audit_duplicate_tokens.py \
    --apply \
    --report docs/generated/duplicate-token-audit-applied.md \
    --backup-dir docs/generated/backups/

# 单阶段
uv run python scripts/audit_duplicate_tokens.py --apply --only-phase1
uv run python scripts/audit_duplicate_tokens.py --apply --only-phase2
```

参数：`--threshold-holders` (默认 200)、`--threshold-liq-usd` (默认 5000)、`--no-external` (跳过 OKX/CoinGecko)、`--chain`、`--symbol`。

## 5. Phase 1：链名规范化

### 输入
所有 `asset_venues` 中 `chain='eth'` 的行（149 行）。

### 关键约束
线上 schema 对 `assets.asset_id` 和 `asset_venues.venue_id` 的所有外键都是 **`ON UPDATE NO ACTION`**（仅 `ON DELETE` 有 CASCADE/SET NULL）。所以**不能直接 `UPDATE asset_id`**——必须走"insert 目标 → reassign FK 列 → delete 旧行"模式。

### 逻辑（"merge" 模式，rename 与冲突合并共用同一流程）

对每个 `chain='eth'` 的 asset，目标 `asset_id` = `asset:dex:ethereum:<addr>`、目标 `venue_id` = `venue:dex:ethereum:<addr>`：

1. **确保目标 asset 存在**：若目标 `asset_id` 不在 `assets` 中 → INSERT 一行（copy `canonical_symbol`/`display_name`/`identity_status`/`confidence`/`first_seen_at_ms` 用较老者的值）；若已存在 → 取较老的 `first_seen_at_ms`、较高的 `confidence` merge 到目标行
2. **确保目标 venue 存在**：同上对 `asset_venues`（INSERT or merge），`chain='ethereum'`
3. **Reassign 7 张表的 `asset_id` 列**：
   - `asset_aliases`, `asset_market_snapshots`, `token_intent_resolutions`, `token_intent_resolution_candidates`, `token_radar_rows`, `asset_signal_snapshots` 的 `asset_id` 从 `eth` 改写到 `ethereum`
4. **Reassign 5 张表的 `venue_id` 列**：
   - `asset_market_snapshots`, `token_intent_resolutions.primary_venue_id`, `token_intent_resolution_candidates.venue_id`, `token_radar_rows.primary_venue_id`, `asset_signal_snapshots.primary_venue_id`
5. **DELETE 旧 venue**：`DELETE FROM asset_venues WHERE venue_id='venue:dex:eth:<addr>'`（CASCADE 清残余 market_snapshots —— 此时应为 0 行因为已 reassign）
6. **DELETE 旧 asset**：`DELETE FROM assets WHERE asset_id='asset:dex:eth:<addr>'`

合并时若两边都有同一时间窗的 market_snapshot（极小概率撞 `snapshot_id` PK），跳过冲突的，记入报告 conflict 列表。

孤儿链名（`evm`/`evm_unknown`/`tron`/`monad`，总计 6 行）：报告里列出，**不自动处理**，留给人决定。

### 报告输出

```
## Phase 1 — Chain normalization
- eth → ethereum: 149 venue rows
  - merged (same-address dup): N
  - renamed (no conflict): M
- orphan chains skipped (manual review needed):
  | chain | venue_count | asset_ids |
  | evm | 1 | ... |
  | evm_unknown | 2 | ... |
```

## 6. Phase 2：同名去重

### 6.1 数据采集

对每个 `(chain, symbol)` 组，先建一个"候选事实表"：

```sql
WITH latest_snap AS (
  SELECT DISTINCT ON (asset_id) asset_id, observed_at_ms,
         market_cap_usd, liquidity_usd, holders, volume_24h_usd, provider
  FROM asset_market_snapshots
  WHERE asset_id IN (SELECT asset_id FROM assets WHERE canonical_symbol = $1)
  ORDER BY asset_id, observed_at_ms DESC
)
SELECT a.asset_id, av.chain, av.address,
       ls.market_cap_usd, ls.liquidity_usd, ls.holders, ls.volume_24h_usd,
       ls.observed_at_ms
FROM assets a
JOIN asset_venues av ON av.asset_id = a.asset_id
LEFT JOIN latest_snap ls ON ls.asset_id = a.asset_id
WHERE a.canonical_symbol = $1 AND av.chain = $2 AND av.is_active = true;
```

### 6.2 Winner 选择

排序 key：

```
(COALESCE(holders, 0) DESC,
 COALESCE(liquidity_usd, 0) DESC,
 COALESCE(market_cap_usd, 0) DESC,
 first_seen_at_ms ASC)            -- tiebreaker：先发现的优先
```

阈值：`holders ≥ 200 AND liquidity_usd ≥ 5000`。

- top1 过阈 → winner = top1，其它全部 loser
- top1 不过阈 → 走外部仲裁

### 6.3 外部仲裁

按顺序调，**任一命中即采纳**：

1. **OKX DEX search**（复用 `integrations/okx/dex_client.py` 中现有的 `/api/v6/dex/market/token/search` endpoint）
   - 入参 chain + symbol，取 rank 1 的 contract address
   - 若该 address 在我们 DB 的候选里 → winner = 它（即使它 holders 低于阈值）
2. **CoinGecko search**（新增 `integrations/coingecko/search_client.py`）
   - GET `https://api.coingecko.com/api/v3/search?query={symbol}`
   - 过滤 `coin.platforms[<chain_to_coingecko_platform>]` 命中
   - 取第一个 platform address，若在 DB 候选里 → winner = 它

两者都没命中 → **整组 DROP**（标记 `group_status = "no_real_token"`）。

CoinGecko 平台名映射表（写死，不进 DB）：

```python
COINGECKO_PLATFORM = {
    "solana": "solana",
    "ethereum": "ethereum",
    "bsc": "binance-smart-chain",
    "base": "base",
    "tron": "tron",
}
```

### 6.4 DROP 执行

对每组 loser：

```sql
DELETE FROM assets WHERE asset_id = ANY($1);
```

依赖现有 schema 的 CASCADE / SET NULL 行为：

| 表 | FK 行为 | 影响 |
|---|---|---|
| `asset_venues` | CASCADE | 直接清掉 |
| `asset_aliases` | CASCADE | 直接清掉 |
| `asset_market_snapshots` | CASCADE | 直接清掉（TROLL fakes 实测影响 690 行）|
| `token_intent_resolutions` | SET NULL | 历史 resolution 保留但 asset_id=NULL；`candidate_ids_json` / `reasons_json` 仍可诊断 |
| `token_intent_resolution_candidates` | SET NULL | 同上 |
| `token_radar_rows` | SET NULL | 历史 radar row 失去 asset 链接，但 `target_id`/`target_type` 仍在 |
| `asset_signal_snapshots` | SET NULL | 同上 |

**`registry_assets` / `asset_identity_current/evidence` 用不同的 asset_id 命名（CAIP 格式）**，与 `assets.asset_id` 无 FK 关系，本次不动。

整个 `--apply` 全程包在单个 `platform.db.postgres_client.transaction()` 里，异常即 ROLLBACK。

## 7. Audit Report 格式

Markdown，每组一节：

```markdown
## solana / TROLL  (10 candidates, winner via in-db threshold)

| status | asset_id | address | holders | liq_usd | mcap_usd | reason |
|---|---|---|---:|---:|---:|---|
| KEEP | asset:dex:solana:5uuh9... | 5UUH... | 52267 | 3,112,572 | 51,436,410 | top by holders, ≥ threshold |
| DROP | asset:dex:solana:5ubucf... | 5uBUCF... | 134 | 22,883 | 94,741,531 | low holders, mcap-pump pattern |
| DROP | asset:dex:solana:hoxhi... | HoxhicKst... | 151 | 25,896 | 61,445,341 | low holders |
...

## bsc / TROLL  (4 candidates, GROUP DROPPED via external arbitration)

External arbitration:
- OKX DEX search(bsc, TROLL): no hit
- CoinGecko search(TROLL, platform=binance-smart-chain): no hit

| status | asset_id | address | holders | liq_usd | mcap_usd | reason |
|---|---|---|---:|---:|---:|---|
| DROP | asset:dex:bsc:0x27a2... | 0x27a2... | 972 | 14,412 | 15,077 | top1 below threshold, external no-hit |
...
```

文末 summary：

```
## Summary
- Phase 1: 149 venue rows normalized (X merged, Y renamed)
- Phase 2:
  - Groups processed: 1,259
  - In-db winners: P (top1 ≥ threshold)
  - External-arbitration winners: Q (OKX: q_okx, CoinGecko: q_cg)
  - No-real-token groups: R
  - Total assets KEPT: K
  - Total assets DROPPED: D  (expected ≈4,214)
- Cascading effect on apply:
  - asset_venues deleted: ...
  - asset_market_snapshots deleted: ...
  - token_intent_resolutions set NULL: ...
  - token_radar_rows set NULL: ...
```

## 8. 测试

`tests/scripts/test_audit_duplicate_tokens.py`：

1. **In-db winner**（`test_phase2_picks_winner_by_holders`）
   fixture：3 个同链同符号 asset，holders [52267, 151, 134]。断言 winner = holders=52267 那个，其它两个进 drop_set。
2. **External fallback hit OKX**（`test_phase2_external_arbiter_okx_hit`）
   fixture：3 个 asset 全部 holders<100。mock OKX client 返回某 address。断言 winner = 那个 address；CoinGecko 不被调到。
3. **External fallback hit CoinGecko**（`test_phase2_external_arbiter_coingecko_hit`）
   mock OKX 返回空、CoinGecko 返回某 address。断言 winner = 那个。
4. **External no hit → group drop**（`test_phase2_group_drop_when_no_external_hit`）
   mock 都返回空。断言整组进 drop_set。
5. **Phase 1 chain merge**（`test_phase1_merges_eth_into_ethereum`）
   fixture：`asset:dex:eth:0xabc` 和 `asset:dex:ethereum:0xabc` 各自带 1 个 snapshot。断言执行后：`eth` asset 不存在，snapshots 全归到 `ethereum` asset。
6. **Phase 1 chain rename**（`test_phase1_renames_when_no_conflict`）
   fixture：只有 `asset:dex:eth:0xdef`（ethereum 侧无）。断言执行后：asset_id 重命名为 `asset:dex:ethereum:0xdef`。
7. **Dry-run 不写库**（`test_dry_run_does_not_mutate`）
   跑完 `--dry-run` 后断言 `assets` 行数不变。
8. **Apply 单事务原子性**（`test_apply_rolls_back_on_error`）
   注入 mock 让中间一个 DELETE 抛错；断言事务回滚，行数不变。

集成测试用 Testcontainers PG（项目已有 fixture pattern），fixture 数据塞 ~20 组 (chain, symbol) 重复。

## 9. 备份与回滚

`--apply` 前自动跑：

```bash
pg_dump --data-only \
    --table=assets --table=asset_venues --table=asset_aliases \
    --table=asset_market_snapshots --table=token_intent_resolutions \
    --table=token_radar_rows --table=asset_signal_snapshots \
    --table=token_intent_resolution_candidates \
    -f docs/generated/backups/audit-backup-<ts>.sql
```

回滚：手工 `psql -f audit-backup-<ts>.sql`（先 `TRUNCATE` 受影响表，再 restore）。不在 apply 流程里做自动回滚 —— 异常时事务回滚已经够；备份是最后手段。

## 10. 文件清单

| 路径 | 用途 |
|---|---|
| `scripts/audit_duplicate_tokens.py` | 主脚本 |
| `integrations/coingecko/__init__.py` | 新模块 |
| `integrations/coingecko/search_client.py` | CoinGecko search async client |
| `tests/scripts/test_audit_duplicate_tokens.py` | 单测 + 集成测试 |
| `tests/integrations/test_coingecko_search.py` | CoinGecko client 单测 |
| `docs/generated/duplicate-token-audit.md` | dry-run 输出（首次 review）|
| `docs/generated/duplicate-token-audit-applied.md` | apply 后留痕 |

## 11. 验证计划

完成后跑：

```bash
# 单元/集成测试
uv run pytest tests/scripts/test_audit_duplicate_tokens.py -v
uv run pytest tests/integrations/test_coingecko_search.py -v

# 真实库 dry-run
uv run python scripts/audit_duplicate_tokens.py --dry-run \
    --report docs/generated/duplicate-token-audit.md

# 人审 docs/generated/duplicate-token-audit.md（看 TROLL / HANTA / SPACEXAI 是否选对）

# Apply
uv run python scripts/audit_duplicate_tokens.py --apply \
    --report docs/generated/duplicate-token-audit-applied.md \
    --backup-dir docs/generated/backups/

# Apply 后断言
psql ... -c "SELECT COUNT(*) FROM assets;"             # 应 ≈10,790
psql ... -c "SELECT chain, COUNT(*) FROM asset_venues GROUP BY chain;"  # 'eth' 应不再出现
psql ... -c "SELECT canonical_symbol, COUNT(DISTINCT a.asset_id) FROM assets a JOIN asset_venues av ON av.asset_id=a.asset_id GROUP BY av.chain, canonical_symbol HAVING COUNT(DISTINCT a.asset_id) > 1;"  # 应返回 0 行
```

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| winner 误判，删错真品 | dry-run 报告人审；阈值是中道值；外部仲裁兜底 |
| Solana meme winner 没在 CoinGecko 收录（pump.fun 多数不在）| 默认走库内阈值，外部仲裁只在 top1 不过阈触发，pump.fun 类的会保 1 个 holder 最多的 |
| `token_intent_resolutions.asset_id` 被 SET NULL，未来读模型缺数据 | `candidate_ids_json` / `reasons_json` 已保留诊断；只是 Radar 历史显示某 row 失去 asset 链接，是已知代价 |
| pg_dump 备份过大 | `--data-only`、只 dump 受影响表；初步估算 < 200MB |
| OKX/CoinGecko 速率限制 | dry-run 阶段并发限到 5 / s；fallback 路径理论上 ≪ 1259 次（多数组库内决出） |

## 13. 后续 follow-up（不在本 spec 内）

- 上游 fix（resolver 注册门槛）—— 另起 spec
- 持续 reconcile worker（看本次清完后重复增速决定要不要做）
- 跨链同名展示策略（前端按 chain 分组，不在后端清理范围）
