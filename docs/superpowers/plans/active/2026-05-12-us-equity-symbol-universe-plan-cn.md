# Plan — US Equity Symbol Universe Root Fix

**Status**: Active
**Date**: 2026-05-12
**Spec**: `docs/superpowers/specs/active/2026-05-12-us-equity-symbol-universe-cn.md`

## 目标

用一个本地 US equity symbol universe 表彻底切开 crypto token intent 和美股 ticker：股票 ticker 解析为 `NON_CRYPTO/MarketInstrument`，不再进入 OKX DEX discovery，也不进入 token radar；已有 CEX/DEX crypto 解析顺序保持不变。

## 任务清单

- [ ] TDD：新增 resolver 测试
  - `tests/unit/test_deterministic_token_resolver.py`
  - 覆盖 CEX 优先、DEX Asset 优先、无 crypto 候选时 US equity -> `NON_CRYPTO`。

- [ ] TDD：新增 sync parser 测试
  - `tests/unit/test_us_equity_symbol_sync.py`
  - 覆盖 `nasdaqlisted.txt` / `otherlisted.txt` 解析、test issue 过滤、ETF 类型。

- [ ] TDD：新增 repository/CLI 边界测试
  - `tests/integration/test_registry_repository.py`
  - `tests/integration/test_cli.py`
  - 覆盖 `upsert/find/deactivate_us_equity_symbol` 和 `ops sync-us-equity-symbols` parser 注册。

- [ ] Schema
  - 新增 `src/parallax/platform/db/alembic/versions/20260512_0033_us_equity_symbol_universe.py`
  - 建 `us_equity_symbols` 表和 active lookup index。

- [ ] Repository
  - `src/parallax/domains/asset_market/repositories/registry_repository.py`
  - 新增 `upsert_us_equity_symbol`、`find_us_equity_symbol`、`deactivate_missing_us_equity_symbols`。

- [ ] Sync service/client
  - 新增 `src/parallax/domains/asset_market/services/us_equity_symbol_sync.py`
  - 新增 Nasdaq Trader parser、HTTP client、`sync_us_equity_symbols()`。

- [ ] Resolver
  - `src/parallax/domains/token_intel/services/deterministic_token_resolver.py`
  - 在 CEX 和现有 DEX asset 逻辑之后、NIL 之前加入 US equity 分支。

- [ ] Token radar crypto 边界
  - `src/parallax/domains/token_intel/queries/token_radar_source_query.py`
  - source rows/count 排除 `target_type = 'MarketInstrument'`。

- [ ] CLI
  - `src/parallax/app/surfaces/cli/main.py`
  - 注册并实现 `ops sync-us-equity-symbols`。

- [ ] 验证与落地
  - 跑新增单测和相关集成测试。
  - 跑 migration。
  - 跑 `ops sync-us-equity-symbols`。
  - 单独跑一次明确的 `ops reprocess-token-intents --window 1h` 或 `ops rebuild-token-intents --window 1h`。
  - 查询并记录 reprocess 前后 `NIL/SYMBOL_NOT_IN_REGISTRY`、`NON_CRYPTO/CONFIRMED_US_EQUITY`、top NIL symbols。
  - 提交 feature 分支，合并回 main 并提交。
