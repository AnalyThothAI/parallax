# Spec — US Equity Symbol Universe Root Fix

**Status**: Active
**Date**: 2026-05-12
**Owner**: Codex
**Related**:
- `docs/superpowers/specs/active/2026-05-12-symbol-only-resolution-gap-cn.md`
- `src/gmgn_twitter_intel/domains/token_intel/services/deterministic_token_resolver.py`
- `src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py`
- `src/gmgn_twitter_intel/domains/asset_market/runtime/token_discovery_worker.py`
- `src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py`

---

## 1. 背景

`symbol-only` 第一轮根因修复已经把“OKX DEX 有多个 crypto 候选但市场数据不足”的 AMBIGUOUS 问题降下来：resolver 增加 `RESOLVED_BY_PROVIDER_RANK` 后，已有 crypto 候选可以在没有完整 market fields 时选出 OKX 排名第一的候选。

但后续 1h 实时数据仍有大量 `NIL/SYMBOL_NOT_IN_REGISTRY`：

| 指标 | 值 |
|---|---:|
| 1h symbol-only NIL | 565 |
| 1h NIL symbols | 264 |
| 1h NIL reason | 100% `SYMBOL_NOT_IN_REGISTRY` |
| Discovery 状态 | 259 `not_found`, 4 `error`, 1 no row |
| 明确 equity context | 至少 115 intents / 74 symbols |

Top NIL symbols 里大量是美股 ticker，而不是 crypto token：

| symbol | 1h NIL intents | 样例语义 |
|---|---:|---|
| `STRC` | 82 | stock/news cashtag |
| `AAOI` | 18 | Applied Optoelectronics stock |
| `MRVL` | 9 | semiconductor stock |
| `NBIS` | 8 | public company ticker |
| `RKLB` | 7 | Rocket Lab stock |
| `COHR` | 6 | Coherent stock |
| `IREN` | 6 | public company ticker |

结论：剩余大头不是“crypto resolver 还不够聪明”，而是资产类别边界缺失。系统把所有 cashtag 都当 crypto token intent，导致美股 ticker 进入 OKX DEX discovery。OKX 返回 `not_found` 是正确结果，但系统把它记录成 crypto `NIL`，污染 token radar 和 unresolved 指标。

---

## 2. 根因

当前数据流只有两类可解析 target：

- `Asset`: 链上 token/contract
- `CexToken`: 中心化交易所 crypto base symbol

缺失第三类事实：`$AAOI` / `$MRVL` / `$RKLB` 这种符号本身是合法金融工具，但不是 crypto。因为没有本地 US equity universe，resolver 只能：

1. 查不到 CEX token；
2. 查不到 DEX asset；
3. 返回 `NIL/SYMBOL_NOT_IN_REGISTRY`；
4. discovery worker 继续用 `symbol:AAOI` 调 OKX DEX；
5. OKX 正确返回 `not_found`，但系统继续把它当 unresolved crypto。

这个问题不能靠增加 OKX 重试、扩大 discovery limit、接 marketlane quote 热路径解决。那只是把“股票 ticker 不是 crypto”这个确定性事实外包给慢接口，仍然会在高频 cashtag 下产生不必要 lookup。

---

## 3. 目标

新增本地 US equity symbol universe，像 CEX universe 一样先缓存，再由 resolver 同步读取。

必须满足：

1. 美股 ticker 不再落入 `NIL/SYMBOL_NOT_IN_REGISTRY`。
2. 美股 ticker 不再进入 OKX DEX discovery 队列。
3. 已有 crypto 业务逻辑不受影响：
   - CEX token 仍优先于 US equity。
   - 已有 DEX `Asset` 候选仍优先于 US equity。
   - 多 DEX 候选的 AMBIGUOUS 行为不变。
4. 不保留兼容性代码，不加 legacy fallback。
5. KISS：一个表、一个 sync 命令、resolver 一个明确分支、token radar 一个明确过滤边界。

---

## 4. 非目标

- 不把系统扩展成完整股票分析产品。
- 不引入 marketlane subprocess 到 ingest/resolver 热路径。
- 不增加行情订阅、股票价格、股票 UI。
- 不改 cashtag extractor 的基础行为；它仍然抽取 cashtag，后续由 resolver 分类。
- 不用复杂 NLP 判断每条推文是不是股票上下文。根因是 symbol universe 缺失，第一阶段用确定性本地事实表解决。

---

## 5. 设计

### 5.1 新表

`us_equity_symbols`

| 字段 | 含义 |
|---|---|
| `symbol` | 大写 ticker，主键 |
| `market_instrument_id` | `market_instrument:us_equity:<SYMBOL>` |
| `exchange` | Nasdaq Trader exchange code |
| `security_name` | 证券名 |
| `instrument_type` | `equity` / `etf` |
| `status` | `active` / `inactive` |
| `source` | `nasdaq_trader` |
| `source_updated_at_ms` | 本次 universe sync 时间 |
| `raw_payload_json` | 原始行 |
| `created_at_ms` / `updated_at_ms` | 本地写入时间 |

### 5.2 数据源

使用 Nasdaq Trader Symbol Directory：

- `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`
- `https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`

理由：

- 轻量、公开、无需 API key；
- 覆盖 Nasdaq listed 和 other listed symbols；
- 文件小，适合 daily/manual sync；
- 本地表读取可避免热路径网络调用。

### 5.3 Resolver 优先级

`_resolve_symbol(symbol)` 顺序改成：

1. `find_cex_token(symbol)` 命中：保持 `CexToken/UNIQUE_BY_CONTEXT/CONFIRMED_CEX_TOKEN`。
2. `find_assets_by_symbol_with_identity_metadata(symbol)` 有候选：完全走现有 DEX asset 逻辑。
3. 没有任何 crypto 候选时，`find_us_equity_symbol(symbol)` 命中：返回
   - `resolution_status = "NON_CRYPTO"`
   - `target_type = "MarketInstrument"`
   - `target_id = "market_instrument:us_equity:<SYMBOL>"`
   - `reason_codes = ["CONFIRMED_US_EQUITY"]`
   - `lookup_keys = []`
4. 否则保持现有 `NIL/SYMBOL_NOT_IN_REGISTRY`。

这个顺序保证已有 crypto registry 的解析结果不被股票表抢走。

### 5.4 Token Radar 边界

Token radar 是 crypto radar，不展示股票 instrument。

`TokenRadarSourceQuery` 只允许：

- unresolved crypto candidate: `target_type IS NULL`
- resolved crypto target: `target_type IN ('Asset', 'CexToken')`

`target_type = 'MarketInstrument'` 的 `NON_CRYPTO` 行从 token radar source 过滤掉。

### 5.5 Sync 命令

新增：

```bash
uv run gmgn-twitter-intel ops sync-us-equity-symbols
```

输出：

```json
{
  "ok": true,
  "data": {
    "source": "nasdaq_trader",
    "symbols_seen": 12345,
    "symbols_written": 12345,
    "symbols_deactivated": 12,
    "observed_at_ms": 1778...
  }
}
```

Sync 语义：

- 本次文件里存在的 symbol upsert 为 `active`。
- 本次文件里不存在、且 source 是 `nasdaq_trader` 的旧 symbol 标为 `inactive`。
- 单事务提交。

---

## 6. 验收标准

功能验收：

- `AAOI` / `MRVL` / `RKLB` 这类已同步美股 ticker 被 resolver 分类为 `NON_CRYPTO/MarketInstrument`。
- `PEPE` 这类 CEX crypto symbol 即使也存在于 equity 表，仍解析为 `CexToken`。
- 已有 DEX asset symbol 即使也存在于 equity 表，仍解析为 `Asset` 或现有 AMBIGUOUS。
- `NON_CRYPTO/MarketInstrument` 不进入 token radar source rows/count。
- Sync 命令可解析 Nasdaq Trader 两个文件并写表。

数据验收：

- 在同步 US equity universe 后，单独跑一次明确 `reprocess-token-intents` 或 `rebuild-token-intents`。
- 对比同一窗口内：
  - `NIL/SYMBOL_NOT_IN_REGISTRY` 显著下降；
  - `NON_CRYPTO/CONFIRMED_US_EQUITY` 增加；
  - top NIL 里 `AAOI/MRVL/RKLB/NBIS/COHR/IREN` 等美股 ticker 消失或明显下降。

工程验收：

- 新增 migration head。
- Unit/integration tests 覆盖 resolver、sync parser、CLI、repository。
- `make check` 或项目等价检查通过；如不能跑全量，记录原因和已跑命令。
