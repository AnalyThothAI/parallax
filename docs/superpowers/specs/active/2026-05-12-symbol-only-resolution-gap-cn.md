# Spec — Symbol-Only Resolution Gap

**Status**: Active
**Date**: 2026-05-12
**Owner**: Claude
**Related**:
- `src/parallax/domains/token_intel/services/deterministic_token_resolver.py`
- `src/parallax/domains/asset_market/repositories/registry_repository.py`
- `src/parallax/domains/asset_market/repositories/discovery_repository.py`
- `src/parallax/domains/asset_market/runtime/token_discovery_worker.py`

---

## 0. 通俗版（先讲清问题是啥、不是啥）

把这套系统想象成一家"加密币情报餐厅"。它从推特上收到信号，要做两件事：

```
推文 "$WIF 起飞了"
   │
   ├── 翻译员 (Resolver)
   │   作用：把 "$WIF" 翻译成 "Solana 链上 EKpQGSJ... 这个具体合约"
   │   产出：token_intent_resolutions（每条 = "这次提及 = 哪个 target"）
   │
   └── 价格员 (LivePriceGateway)
       作用：盯着翻译好的合约的实时价格
       产出：WS 推送 live_market_update 给前端
```

用户最近反馈两件事，看起来都"灰灰的、卡住的"，**但实际是两个独立问题**：

| 用户感受 | UI 文字 | 根因模块 | 本 spec 是否涵盖 |
|---|---|---|---|
| "代币价格 pending" | `market pending` | 价格员订阅上限 100，多出的 token 永远收不到实时价 | **不**，由 `2026-05-12-live-price-target-cap-cn.md` 处理（未立） |
| "很多 symbol-only 没解析到 CA" | `market unavailable` / 无 target | 翻译员的"市场主导度门槛"过严，93.7% 候选不达标 | **是** |

本 spec 只解 **后者**——symbol-only intent 大量卡在 AMBIGUOUS/NIL。

通俗版根因：翻译员有个规矩——"要看清候选币的市值、流动性、持币数 **三项里至少 2 项**，并且 24 小时内更新过，我才敢翻译"。但 OKX 给的候选 evidence 里 **93.7% 只填了 1 项**（通常只有 holders），翻译员就只能说"我搞不定，AMBIGUOUS"。不是翻译员坏了，是规矩跟现实对不上。

---

## 1. Background

### 1.1 用户视角现象

用户在 token radar 上长期看到大量行：

- `display_symbol` 显示了（比如 `WOJAK` `TROLL`），但 `target` 为空 / 显示 "ambiguous" / "unresolved"
- 行的市场单元格显示 `market unavailable`（前端 `TokenRadarRow.tsx:255`）或 `market_status = "missing"`
- 同一个 symbol 反复在不同推文里出现，每次都解析失败

用户的心智："`$WIF` 这种 symbol 我们调 OKX search 就能精确匹配 CA，为啥还卡住？"

但实际：调 OKX search 后拿到的是**多个候选**（10 个 WOJAK、20 个 TROLL），不是一个精确答案。Resolver 设计为"用市场主导度选出最大的那一个"，这个判定大概率失败，于是退到 `AMBIGUOUS`。

### 1.2 技术视角数据流

```
推文进来
  → entity_extractor 抽出 ($symbol 或 chain+address)
  → token_intents 写入 (display_symbol, chain_hint, address_hint)
  → token_intent_lookup_keys 写入 ("symbol:WOJAK" 等等)
  → 同步 resolver.resolve()
      ├─ 有 chain+address → 查 registry_assets(chain, address) → EXACT
      ├─ 只有 address → _resolve_address_without_chain → 多链冲突？AMBIGUOUS
      └─ 只有 symbol → find_assets_by_symbol_with_identity_metadata
                       → 0 候选 → NIL ["SYMBOL_NOT_IN_REGISTRY"]
                       → 1 候选 → UNIQUE_BY_CONTEXT
                       → 多候选 → _market_dominant_asset()
                                  ├─ 能选出主导 → UNIQUE_BY_CONTEXT
                                  └─ 不能 → AMBIGUOUS ["NO_MARKET_DOMINANT_CHAIN_ASSET"]
  → token_intent_resolutions 写入 (is_current=true)

异步 (30 秒一轮):
TokenDiscoveryWorker.run_once()
  → 扫 due_lookup_keys (resolution=NIL/AMBIGUOUS + next_refresh_at_ms<=now)
  → 调 OKX dex_market.search_tokens(symbol or address)
  → 写 token_discovery_results (found / not_found / error)
  → 写 asset_identity_evidence (provider=okx, kind=symbol_candidate / exact_address)
  → 触发 reprocess_recent_token_intents (24h 窗内同 lookup_key 的 intent 重解析)
```

### 1.3 与 LivePriceGateway "live price missing" 的边界（重申）

- "live price missing" 来自 `LivePriceGateway._cache` 没有该 target 的快照——可能是 gateway 没订阅该 target，或者订阅了但 OKX 还没推。任何 target（包括已 EXACT 解析的）都可能出现。
- "symbol-only 卡住" 来自 `token_intent_resolutions.resolution_status IN (NIL, AMBIGUOUS)`——target 根本就没生成出来。
- **如果一行 `target` 是空的，那一定是本 spec 的问题（resolver），不是 gateway 问题。**
- **如果一行 `target` 有值、但 `live_market.status === "missing"`，那是 gateway 问题，不在本 spec 范围内。**

---

## 2. Current State（2026-05-12 抓自生产 Postgres）

### 2.1 全局 resolution 状态

```sql
SELECT resolution_status, COUNT(*) AS n
FROM token_intent_resolutions
WHERE is_current = true
GROUP BY resolution_status;
```

| status | count | 占比 |
|---|---|---|
| UNIQUE_BY_CONTEXT | 37507 | 47.5% |
| EXACT | 27232 | 34.5% |
| NIL | 7050 | 8.9% |
| AMBIGUOUS | 6176 | 7.8% |

### 2.2 resolution × hint 类型矩阵

| | has_address | symbol_only |
|---|---|---|
| EXACT | 27236 | 0 |
| UNIQUE_BY_CONTEXT | 5199 | **32312** |
| AMBIGUOUS | 349 | **5831** |
| NIL | 1907 | **5144** |

Symbol-only 总计 43287，成功率 74.6%，AMBIGUOUS 13.5%，NIL 11.9%。

### 2.3 最近 24h 情况（更糟）

| status | symbol_only |
|---|---|
| UNIQUE_BY_CONTEXT | 4087 (60%) |
| AMBIGUOUS | **2119 (31%)** |
| NIL | 569 (8.4%) |

**最近 24h symbol-only 失败率 39.4%**——比全局历史（25.4%）更高，说明问题在恶化。

### 2.4 AMBIGUOUS 5831 的 reason

```sql
SELECT tir.reason_codes_json::text, COUNT(*)
FROM token_intent_resolutions tir
JOIN token_intents ti USING (intent_id)
WHERE tir.is_current = true AND tir.resolution_status = 'AMBIGUOUS'
  AND ti.address_hint IS NULL
GROUP BY 1;
```

```
["NO_MARKET_DOMINANT_CHAIN_ASSET"] | 5831    ← 100% 一种原因
```

### 2.5 NIL 5144 的 reason

```
["SYMBOL_NOT_IN_REGISTRY"]      | 4691
["DEMOTED_SEARCH_ASSET_PURGED"] |  243
["SYMBOL_CANDIDATES_STALE"]     |  210
```

注：后两个 reason code 字符串在 Python 源码里搜不到（grep `*.py` 0 hits）——可能由未合并 worktree 或直接 SQL 写入。**这条独立子问题待查 git log。**

### 2.6 has_address 异常

```sql
SELECT tir.resolution_status, ti.chain_hint, COUNT(*)
FROM token_intent_resolutions tir
JOIN token_intents ti USING (intent_id)
WHERE tir.is_current = true AND ti.address_hint IS NOT NULL
  AND tir.resolution_status IN ('NIL','AMBIGUOUS')
GROUP BY 1,2 ORDER BY 1;
```

| status | chain_hint | n |
|---|---|---|
| AMBIGUOUS | (any) | 349（全部 `ADDRESS_EXISTS_ON_MULTIPLE_CHAINS`） |
| NIL | (empty) | 1412 |
| NIL | solana | 469 |
| NIL | bsc | 14 |
| NIL | eth | 8 |
| NIL | base | 4 |

1412 个无 chain 的 NIL：entity_extractor 提取到 EVM `0x...` 格式但推文里没足够上下文（链名 / explorer URL）确定链，被 normalize 成 `chain_hint = NULL`。

### 2.7 Discovery worker 健康度

```sql
SELECT to_timestamp(MAX(last_lookup_at_ms)/1000) AT TIME ZONE 'UTC' AS last_call,
       (EXTRACT(EPOCH FROM NOW()) * 1000)::bigint - MAX(last_lookup_at_ms) AS age_ms
FROM token_discovery_results;
```

```
last_call: 2026-05-12 00:13:27 UTC
age_ms:    56311  ← 不到 1 分钟前调用过 OKX
```

discovery_results 状态分布：

| lookup_type | status | count |
|---|---|---|
| address_lookup | found | 1302 |
| address_lookup | not_found | 872 |
| address_lookup | error | **107** |
| dex_symbol_lookup | found | 2583 |
| dex_symbol_lookup | not_found | 1211 |
| dex_symbol_lookup | error | **146** |

Worker 在跑、有写入、有 error。107 + 146 = 253 个 lookup 卡在 error 状态（大多是 OKX HTTP 429 限流）。

---

## 3. Problem / Root Cause

### 3.1 `_market_dominant_asset` 算法（精确版）

`src/parallax/domains/token_intel/services/deterministic_token_resolver.py:301-317`：

```python
def _market_dominant_asset(rows):
    eligible = [row for row in rows if _dominance_eligible(row)]
    if not eligible:
        return None                                # ← 退路 1：5466/5831 死在这里
    ranked = sorted(eligible, key=_dominance_score, reverse=True)
    top = ranked[0]
    top_score = _dominance_score(top)
    second_score = _dominance_score(ranked[1]) if len(ranked) > 1 else Decimal("-1")
    if len(ranked) > 1 and top_score <= second_score:
        return None                                # ← 退路 2：tie
    if (
        _decimal(top.get("market_cap_usd")) < MIN_DOMINANT_MARKET_CAP_USD     # $250K
        and _decimal(top.get("holders")) < MIN_DOMINANT_HOLDERS               # 1000
        and _decimal(top.get("liquidity_usd")) < MIN_DOMINANT_LIQUIDITY_USD   # $100K
    ):
        return None                                # ← 退路 3：三项都不过 floor
    return top
```

### 3.2 `_dominance_eligible` 算法

`deterministic_token_resolver.py:324-332`：

```python
def _dominance_eligible(row):
    present = sum(
        1
        for key in ("market_cap_usd", "holders", "liquidity_usd")
        if row.get(key) is not None and _decimal(row.get(key)) > 0
    )
    if present < 2:
        return False
    return _fresh_resolution_market_fields(row) >= 2
```

`_fresh_resolution_market_fields` 用 `decision_time_ms - observed_at_ms <= 24h`。

**双重门槛**：
1. ≥2 of {mc, liq, holders} 非空 > 0
2. **且** 同样这 ≥2 个字段的 observed_at_ms 在 24h 内

### 3.3 实际数据完整度（关键证据）

用 5831 AMBIGUOUS intent 的全部 32016 个候选 row 反查 OKX evidence：

```sql
WITH ambiguous_candidates AS (
  SELECT jsonb_array_elements_text(tir.candidate_ids_json) AS asset_id
  FROM token_intent_resolutions tir
  WHERE tir.is_current = true AND tir.resolution_status = 'AMBIGUOUS'
    AND tir.reason_codes_json::text LIKE '%NO_MARKET_DOMINANT%'
),
evidence_join AS (
  SELECT ac.asset_id, aie.observed_at_ms,
         COALESCE(NULLIF(aie.raw_payload_json->>'marketCap',''),
                  NULLIF(aie.raw_payload_json->>'market_cap_usd',''))::numeric AS mc,
         COALESCE(NULLIF(aie.raw_payload_json->>'liquidity',''),
                  NULLIF(aie.raw_payload_json->>'liquidity_usd',''))::numeric AS liq,
         NULLIF(aie.raw_payload_json->>'holders','')::numeric AS holders
  FROM ambiguous_candidates ac
  LEFT JOIN LATERAL (
    SELECT raw_payload_json, observed_at_ms FROM asset_identity_evidence
    WHERE asset_id = ac.asset_id AND provider = 'okx'
    ORDER BY observed_at_ms DESC LIMIT 1
  ) aie ON true
)
SELECT
  COUNT(*) AS total_candidate_rows,
  COUNT(*) FILTER (WHERE observed_at_ms IS NOT NULL) AS has_evidence,
  COUNT(*) FILTER (WHERE observed_at_ms >= now_ms - 86400000) AS fresh_24h,
  COUNT(*) FILTER (WHERE 2 fields populated AND positive) AS has_2_of_3_positive
FROM evidence_join;
```

| 指标 | rows | 占比 |
|---|---|---|
| 候选 row 总数 | 32016 | 100% |
| 有 OKX evidence | 20833 | **65%** |
| evidence fresh 24h 内 | 1829 | **5.7%** |
| ≥2 of 3 字段填齐 | 2724 | **8.5%** |

**只有 5.7% 的候选有 fresh evidence，只有 8.5% 有 ≥2 填齐字段。** 双重门槛交集后能 eligible 的比例极低。

### 3.4 按 intent 分组的 eligible 分布

```sql
-- 每个 AMBIGUOUS intent 有多少个 eligible 候选
SELECT eligible_count, COUNT(*) AS n_intents FROM ... GROUP BY eligible_count;
```

| eligible 候选数 | intent 数 | 占比 |
|---|---|---|
| **0** | **5466** | **93.7%** |
| 1 | 107 | 1.8% |
| 2-10 | 258 | 4.4% |

**93.7% 的 AMBIGUOUS intent 一个 eligible 候选都没有**——这是头号根因。剩下 6.3% 是 eligible 但平分或不过 floor。

### 3.5 为什么 evidence 不齐？

抽 TROLL 一个 AMBIGUOUS intent 的 20 个候选：

```
12 个 EVM 候选：marketCap=NULL, liquidity=NULL, holders=有  ← 只有 1 字段
                （只有 1 个 0xf8eb... 是 3 字段齐的）
8 个 Solana `*pump` 候选：完全没有 OKX evidence
                          （pump.fun 死币，OKX 不收录）
```

OKX `dex_market/token/search` 返回的 payload 里 `marketCap` 和 `liquidity` 经常是空字符串。Discovery worker 把空字符串原样写入 raw_payload_json（`registry_repository.py:470-479` 的 `_metadata_number` 会跳过空字符串），所以下游读到的就是 `None`。

加上：部分候选是历史推文带 CA 留下的 `mention_only` 鬼候选（registry 有这个 asset_id 但 OKX 根本没数据），它们永远无法 eligible。

### 3.6 结论：根因不止一个

| 子问题 | 影响 intent 数 | 性质 |
|---|---|---|
| A. dominance 双门槛过严 + OKX payload 字段不齐 | **5466 (93.7%)** | 算法-数据失配 |
| B. EVM 跨链同址 → 直接 AMBIGUOUS 不消歧 | 349 (5.7%) | 算法缺消歧规则 |
| C. EVM 0x... 缺 chain 上下文 → 全链查 OKX 找不到 | 1412 (NIL) | 数据本身没有 |
| D. discovery error 卡住（OKX 429 等 transient error）| 253 (lookup 层) | `fail_lookup` 已维护 `error_count`，但 worker 失败分支固定用 15min retry，且 `due_lookup_keys` 未把 `error_count` 带回 runtime，无法做指数退避 |
| E. DEMOTED_SEARCH_ASSET_PURGED + SYMBOL_CANDIDATES_STALE reason 代码不可追溯 | 453 | 来源待查 |
| F. SYMBOL_NOT_IN_REGISTRY = 真的不在 OKX | 4691 | by design（非 crypto symbol）|

A 是头号目标。B/D 是值得一并处理的独立子问题。C 里"无 chain 且 registry 也没有命中"仍不修；只有"无 chain 但 registry 命中多链"可用默认链优先级消歧。E 需要先溯源。F 不修。

---

## 4. Investigation / Reproduction（任何人都能跑）

### 4.1 准备

```bash
# 容器名 + 凭证（compose.yaml + ~/.parallax/postgres_password）
CONTAINER=parallax-postgres-1
DB=parallax
USER=parallax_app

# 进 psql 用：
docker exec $CONTAINER psql -U $USER -d $DB
```

### 4.2 Step 1：确认 worker 是活的

```sql
SELECT to_timestamp(MAX(last_lookup_at_ms)/1000) AS last_call,
       (EXTRACT(EPOCH FROM NOW()) * 1000)::bigint - MAX(last_lookup_at_ms) AS age_ms
FROM token_discovery_results;
```

**预期**：age_ms < 60000（最近 1 分钟内有 OKX 调用）。如果 age_ms 远大于 30 秒，先看 `~/.parallax/logs/parallax.log` 检查 worker 异常。

### 4.3 Step 2：confirm reason 分布

```sql
SELECT tir.resolution_status,
       CASE WHEN ti.address_hint IS NOT NULL THEN 'has_address' ELSE 'symbol_only' END AS hint_kind,
       tir.reason_codes_json::text AS reasons,
       COUNT(*) AS n
FROM token_intent_resolutions tir
JOIN token_intents ti USING (intent_id)
WHERE tir.is_current = true AND tir.resolution_status IN ('NIL','AMBIGUOUS')
GROUP BY 1,2,3 ORDER BY n DESC;
```

**预期主要分布**：
- `AMBIGUOUS / symbol_only / NO_MARKET_DOMINANT_CHAIN_ASSET` 占大头
- `NIL / symbol_only / SYMBOL_NOT_IN_REGISTRY` 次之
- `NIL / has_address / ADDRESS_NOT_IN_REGISTRY` 第三

### 4.4 Step 3：抽样观察一个 AMBIGUOUS intent 全貌

```sql
SELECT ti.intent_id, ti.display_symbol, tir.candidate_ids_json
FROM token_intents ti
JOIN token_intent_resolutions tir USING (intent_id)
WHERE tir.is_current = true AND tir.resolution_status = 'AMBIGUOUS'
  AND ti.display_symbol = 'WOJAK'
LIMIT 1;
```

记下返回的 `intent_id` 和 candidate 列表。

### 4.5 Step 4：查每个候选的 OKX evidence 完整度

```sql
WITH one_intent AS (
  SELECT candidate_ids_json FROM token_intent_resolutions
  WHERE intent_id = '<上一步 intent_id>'
),
candidates AS (
  SELECT jsonb_array_elements_text(candidate_ids_json) AS asset_id FROM one_intent
)
SELECT c.asset_id,
       aie.observed_at_ms,
       NULLIF(aie.raw_payload_json->>'marketCap','') AS mc,
       NULLIF(aie.raw_payload_json->>'liquidity','') AS liq,
       NULLIF(aie.raw_payload_json->>'holders','') AS holders
FROM candidates c
LEFT JOIN LATERAL (
  SELECT raw_payload_json, observed_at_ms FROM asset_identity_evidence
  WHERE asset_id = c.asset_id AND provider = 'okx'
  ORDER BY observed_at_ms DESC LIMIT 1
) aie ON true;
```

**预期**：大部分候选只有 `holders` 字段，`mc` 和 `liq` 是 NULL 或空字符串。少数候选完全没 evidence。

### 4.6 Step 5：全局量化 eligible 缺口

```sql
WITH ambiguous_intents AS (
  SELECT tir.intent_id, tir.candidate_ids_json
  FROM token_intent_resolutions tir
  WHERE tir.is_current = true AND tir.resolution_status = 'AMBIGUOUS'
    AND tir.reason_codes_json::text LIKE '%NO_MARKET_DOMINANT%'
),
ic AS (
  SELECT intent_id, jsonb_array_elements_text(candidate_ids_json) AS asset_id
  FROM ambiguous_intents
),
enriched AS (
  SELECT ic.intent_id, aie.observed_at_ms,
         COALESCE(NULLIF(aie.raw_payload_json->>'marketCap',''),
                  NULLIF(aie.raw_payload_json->>'market_cap_usd',''))::numeric AS mc,
         COALESCE(NULLIF(aie.raw_payload_json->>'liquidity',''),
                  NULLIF(aie.raw_payload_json->>'liquidity_usd',''))::numeric AS liq,
         NULLIF(aie.raw_payload_json->>'holders','')::numeric AS holders
  FROM ic
  LEFT JOIN LATERAL (
    SELECT raw_payload_json, observed_at_ms FROM asset_identity_evidence
    WHERE asset_id = ic.asset_id AND provider = 'okx'
    ORDER BY observed_at_ms DESC LIMIT 1
  ) aie ON true
),
per_intent AS (
  SELECT intent_id,
         COUNT(*) FILTER (
           WHERE observed_at_ms >= (EXTRACT(EPOCH FROM NOW())*1000)::bigint - 86400000
             AND ((CASE WHEN mc > 0 THEN 1 ELSE 0 END)
                + (CASE WHEN liq > 0 THEN 1 ELSE 0 END)
                + (CASE WHEN holders > 0 THEN 1 ELSE 0 END)) >= 2
         ) AS eligible_count
  FROM enriched GROUP BY intent_id
)
SELECT eligible_count, COUNT(*) AS n_intents
FROM per_intent GROUP BY eligible_count ORDER BY eligible_count;
```

**预期**：`eligible_count = 0` 这一行占总 intent 数的 >90%。

### 4.7 Step 6：复现 resolver 逻辑（无需调代码）

如果想确认任意 intent 的 resolver 输出，跑：

```bash
docker exec parallax-app-1 python -c "
from parallax.app.runtime import boot
runtime = boot()
result = runtime.resolver.resolve(intent_id='<intent_id>')
print(result)
" 2>&1
```

（具体入口可能要看 app runtime 的内部 API，必要时直接读 `_market_dominant_asset` 输入。）

### 4.8 Step 7：直接看 OKX 原始 payload

```sql
SELECT raw_payload_json
FROM asset_identity_evidence
WHERE provider = 'okx'
ORDER BY observed_at_ms DESC LIMIT 3;
```

确认 keys 是 `marketCap` / `liquidity` / `holders`（camelCase）—— `registry_repository.py:424-432` 的 `_metadata_number` alias COALESCE 是对的，**字段名不是 bug**。

---

## 5. 已排除的假设（避免重复走弯路）

| 假设 | 排除依据 |
|---|---|
| Discovery worker 没在跑 | Step 1 显示 56s 前刚调过 OKX |
| Worker 写不进 evidence | discovery_results 有 2583 found，evidence 表有 20833 行 OKX 记录 |
| `marketCap` / `market_cap_usd` 字段名拼错 | `registry_repository.py:424-432` 已 COALESCE 所有 alias |
| reprocess loop 缺失 | `token_discovery_worker.py:166-177` discovery 成功后同步触发 |
| reprocess 没复盖老 intent | 复盖 24h 窗。**这是真问题**，但跟当前 5466 个 0-eligible 无关——存量历史会被新 reprocess 重新跑，前提是新 evidence 写进来 |
| `live_market.status === "missing"` 是 resolver 问题 | 不是。那是 LivePriceGateway 独立问题，本 spec 不涵盖 |

---

## 6. First Principles

1. **多候选 symbol 解析需要外部信号来排序，不能纯靠数量阈值。** 当前 `_dominance_eligible` 的 "≥2 of 3 fresh fields" 假设 OKX 总会给齐数据；事实是 OKX `dex_market/token/search` 对很多 token 只返回 `holders`。算法应该容忍数据稀疏。

2. **当 dominance 无法成立时，应当有一个稳定 fallback 而不是直接放弃。** AMBIGUOUS 意味着用户体验失败。最低限度的 fallback 是"OKX 自己给的 search ranking 第一个"——OKX 内部排序已包含其市场判断。

3. **EVM 跨链同地址不应该是 AMBIGUOUS。** 同一 0x 地址在多链上的部署绝大多数是 fork/clone，主链（部署活跃度最高）通常是答案。`_resolve_address_without_chain` 应该有默认链优先级。

4. **discovery error 不应该和 not_found 共享退避策略。** OKX 429 是 retryable transient 错误，应该指数退避；not_found 是 stable negative，5min 重试合理。混用会让限流期间的 lookup 永远卡死。

5. **不该让"数据不全"和"算法保守"叠加成黑洞。** 当前体验：候选少了 → AMBIGUOUS（保守）；候选数据不全 → AMBIGUOUS（更保守）。两层叠加导致 13.5% symbol-only 永远卡住。任何一层放松都能大幅改善。

---

## 7. Goals

- G1. WHEN symbol-only intent 的某个候选拥有 ≥1 个 fresh（24h 内）市场字段，AND 任一 floor 成立（mc ≥ $250K OR holders ≥ 1000 OR liq ≥ $100K），THEN resolver SHALL allow that candidate into market-dominance ranking. 当前 `top_score > second_score` 与 floor 检查仍保留。
- G2. WHEN address 有效但 chain 缺失，AND registry 命中多个 chain asset，THEN `_resolve_address_without_chain` SHALL 按 `solana > eip155:1 > eip155:8453 > eip155:56 > eip155:42161 > eip155:43114 > ton > unknown(asset_id stable sort)` 选定 target，并写 `RESOLVED_BY_CHAIN_PRIORITY`。
- G3. WHEN discovery lookup 失败，THEN worker SHALL 使用已有 `error_count` 做指数退避：30s → 1min → 5min → 30min → 1h。`found` / `not_found` 的原刷新节奏不变。
- G4. WHEN `deterministic_token_resolver` 只需要 resolver policy 常量，THEN it SHALL import from `token_intel._constants` rather than `token_intel.interfaces`，避免 `interfaces → runtime → token_intent_resolver → deterministic_token_resolver` 的导入环。
- G5. WHEN OKX symbol search returns ordered candidates, THEN `TokenDiscoveryWorker` SHALL save the true response index as `raw_payload_json.provider_rank` for retained symbol-search candidates.
- G6. WHEN market dominance cannot resolve a multi-candidate symbol, AND at least one candidate has fresh `provider_rank`, THEN resolver SHALL select the lowest rank as `UNIQUE_BY_CONTEXT / RESOLVED_BY_PROVIDER_RANK`.
- G7. WHEN 本 spec 跑 24h，THEN AMBIGUOUS symbol-only 占比 SHALL 从最近 24h 的 31% 降至 ≤10%，且 NIL symbol-only 占比不得明显上升。

---

## 8. Selected Refactor

本轮落地 **A + C + D + provider-rank fallback**。KISS 约束：只保存一个 exact key `provider_rank`，只认新 evidence，不猜旧数据，不做 backfill，不加 schema migration。

### 8.1 Resolver dominance eligibility

Current code root cause:

```python
present < 2 or fresh_field_count < 2  -> ineligible
```

Selected rule:

```python
present >= 1 and fresh_field_count >= 1 -> eligible
```

保留不变的保护：
- `_market_dominant_asset` 仍要求 `top_score > second_score`。
- top candidate 仍必须至少满足一个 floor：`market_cap_usd >= 250000`、`holders >= 1000`、`liquidity_usd >= 100000`。
- stale field 仍不可刷新 dominance；price-only row 不会让 identity evidence 变 fresh。

### 8.2 Address-without-chain priority

当前多链同地址直接返回 `AMBIGUOUS / ADDRESS_EXISTS_ON_MULTIPLE_CHAINS`。本轮改为：

```text
1. registry.find_assets_by_address(chain_id=None, address=...)
2. 过滤无 asset_id row
3. 单候选：保留 ADDRESS_UNIQUE_ACROSS_TRACKED_CHAINS
4. 多候选：按默认链优先级排序，返回 UNIQUE_BY_CONTEXT / RESOLVED_BY_CHAIN_PRIORITY
```

`candidate_ids` 按实际决策顺序写入，第一项即 selected target。

### 8.3 Discovery error backoff

当前 `token_discovery_results.error_count` 已存在且 `fail_lookup()` 会递增，但 runtime 没法用它：
- `DiscoveryRepository.due_lookup_keys()` 没有 SELECT `error_count`。
- `TokenDiscoveryWorker` exception branch 固定用 `DEFAULT_RETRY_DELAY_MS = 15min`。

本轮改为：
- `due_lookup_keys()` 输出 `COALESCE(error_count, 0) AS error_count`。
- exception branch 用当前 lookup 的 previous `error_count` 计算下一次 retry delay。
- `finish_lookup()` 成功后仍清零 `error_count`。

### 8.4 Provider-rank fallback

旧版 spec 假设 OKX 原始 search ranking 可得。对照当前代码后，必须先保存这个事实：
- `TokenDiscoveryWorker._process_dex_symbol_lookup()` 先过滤 symbol exact match。
- `_retained_symbol_candidates()` 再按 chain 分桶、去重，并用内部 `_candidate_quality_score()` 排序。
- 如果不保存 provider response index，后续 fallback 会把内部 quality rank 伪装成 provider rank。

本轮改为：
- symbol lookup 收到 provider candidates 后，先按原始 response list 建立 `(chain_id, address) -> provider_rank`。
- 只给 retained symbol-search candidates 写 `raw_payload_json.provider_rank`。
- `RegistryRepository.find_assets_by_symbol_with_identity_metadata()` 只读取 exact key `provider_rank`，并暴露 `provider_rank_observed_at_ms`。
- dominance 失败后，resolver 只在 `provider_rank_observed_at_ms` fresh（24h 内）时选最低 rank，写 `RESOLVED_BY_PROVIDER_RANK`。
- 没有 `provider_rank` 的旧 evidence 不参与 fallback；不做兼容推断。

---

## 9. Non-goals

- N1. 不修 `SYMBOL_NOT_IN_REGISTRY` 的 4691 个 NIL；这些 symbol 可能不是 crypto，不应该强行解析。
- N2. 不修 `live_market.status = "missing"`；那是 `LivePriceGateway` 订阅/推送问题。
- N3. 不引入新 provider（CoinGecko / GeckoTerminal 等）补 OKX 数据稀疏。
- N4. 不重写 `TokenDiscoveryWorker` 主循环；只调整失败 refresh 策略。
- N5. 不做存量 AMBIGUOUS 全量 backfill；新事件与 due lookup 自然回收。需要存量回填时另开 backfill spec。
- N6. 不溯源 `DEMOTED_SEARCH_ASSET_PURGED` / `SYMBOL_CANDIDATES_STALE` 两个历史 reason code。
- N7. 不兼容旧 evidence：没有 `raw_payload_json.provider_rank` 的候选不会走 provider-rank fallback。

---

## 10. Acceptance Criteria

落地前 PR 验收：
- Unit: dominance eligibility 覆盖 1/2/3 字段 × fresh/stale 组合。
- Unit: address-without-chain 覆盖 solana 优先、eip155:1 优先、unknown stable fallback。
- Unit: discovery `_refresh_ms(status="error")` 覆盖 `error_count = 0/1/3/10`，并确认 found/not_found cadence 不变。
- Integration: `due_lookup_keys()` 返回 error lookup 的 `error_count`，供 worker 计算下一次 retry。
- Unit: symbol discovery 写入真实 `provider_rank` 到 identity evidence raw payload。
- Integration: registry symbol lookup 暴露 `provider_rank` 与 `provider_rank_observed_at_ms`。
- Unit: resolver dominance 失败后用 fresh provider rank fallback；stale provider rank 保持 AMBIGUOUS。
- Existing resolver tests still pass, including stale-field dominance rejection.

落地后 24h 观测：
- AMBIGUOUS symbol-only intent 占当日 symbol-only 总数 ≤15%。
- NIL symbol-only 占比无明显上升。
- `RESOLVED_BY_CHAIN_PRIORITY` 出现在 has-address/no-chain 多候选 resolution 中。
- `RESOLVED_BY_PROVIDER_RANK` 出现在新 symbol-search evidence 覆盖后的多候选 resolution 中。
- `token_discovery_results.status = 'error'` 的堆积速度下降；429 时不再固定 15min 重试。
- 抽样 100 个新 `MARKET_DOMINANT_CHAIN_ASSET` / `RESOLVED_BY_PROVIDER_RANK`，人工判断准确率 ≥85%；重点标记 holders-only 和 provider-rank case。

---

## 11. Rollback

- Resolver dominance 放宽可通过恢复 `_dominance_eligible` 的 `2 of 3` 门槛回滚。
- Address priority 可通过恢复多候选 `AMBIGUOUS / ADDRESS_EXISTS_ON_MULTIPLE_CHAINS` 回滚。
- Discovery backoff 可通过恢复 exception branch 的固定 15min retry 回滚。
- Provider-rank fallback 可通过删除 resolver 的 `_provider_rank_asset()` 分支回滚；已写入 raw payload 的 `provider_rank` 可保留为 harmless evidence metadata。
- 本轮无 schema migration；只读取已有 `error_count` 列和 JSONB raw payload key。

---

## 12. Follow-up Triggers

- AMBIGUOUS symbol-only 24h 后仍 >10%：检查 OKX provider rank 覆盖率；若覆盖率低，再开 backfill / provider coverage spec。
- holders-only dominance 出现明显误解析：开 dominance margin / dominance_signal spec。
- provider-rank fallback 出现明显误解析：开 provider rank guardrail spec，例如 rank gap 或 chain allowlist。
- discovery error 仍快速堆积：开 OKX provider rate-limit governance spec。
