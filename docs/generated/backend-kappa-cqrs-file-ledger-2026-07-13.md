# Backend Kappa/CQRS Per-file Ledger, 2026-07-13

本 ledger 覆盖当前工作树中所有 Git 跟踪或新增且实际存在的 `src/parallax/**/*.py` 文件。
它是逐文件审计的机械证据层：角色、Kappa/CQRS 链路职责、跨领域依赖、静态 SQL 表、
内部入/出依赖数、LOC 与 SHA-256 内容指纹。业务结论和修复记录见
`backend-kappa-cqrs-audit-2026-07-13.md`。

- 文件数：637
- Python LOC：144800
- Alembic 迁移按 schema 历史保留，未误判为运行时兼容代码。
- `入/出依赖` 仅统计可解析的 `parallax.*` 静态 import；运行时注册、SQL、协议回调仍由主审计补充。
- 生成命令：`uv run python scripts/regen_backend_architecture_ledger.py`

## 分层分布

| 分类 | 文件数 |
|---|---:|
| `adapter` | 30 |
| `composition` | 10 |
| `contract` | 7 |
| `domain` | 77 |
| `domain-runtime` | 39 |
| `entrypoint` | 2 |
| `package` | 2 |
| `platform` | 21 |
| `port` | 8 |
| `projection` | 27 |
| `query` | 13 |
| `repository` | 63 |
| `runtime` | 29 |
| `schema-history` | 183 |
| `service` | 92 |
| `surface` | 34 |

## 逐文件链路清单

| 文件 | 角色 | 链路责任 | 依赖领域 | 静态 SQL 表 | 入/出依赖 | LOC | 读取指纹 |
|---|---|---|---|---|---:|---:|---|
| `src/parallax/__init__.py` | 包声明 | Python 包边界 | - | - | 0 / 0 | 1 | `bde6a3e6ab7a` |
| `src/parallax/__main__.py` | 入口 | 服务/CLI 包入口 | - | - | 0 / 0 | 4 | `307299fda7b7` |
| `src/parallax/app/__init__.py` | 包声明 | Python 包边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/app/runtime/__init__.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 0 / 1 | 3 | `8ddf19f9d8e1` |
| `src/parallax/app/runtime/app.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | news_intel | - | 1 / 11 | 327 | `8de73426b7db` |
| `src/parallax/app/runtime/bootstrap.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market, evidence, ingestion, notifications, token_intel | - | 2 / 18 | 389 | `81c5808afb31` |
| `src/parallax/app/runtime/db_pool_bundle.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 3 / 6 | 382 | `387720bddd30` |
| `src/parallax/app/runtime/job_queue.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 1 / 0 | 37 | `9421b76e25b6` |
| `src/parallax/app/runtime/llm_gateway.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 1 / 1 | 41 | `34e3f1fbddbe` |
| `src/parallax/app/runtime/ops_cli_queries.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | events, market_tick_current, token_intent_resolutions, token_intents, token_profile_current | 1 / 0 | 98 | `8a28d1c2cabc` |
| `src/parallax/app/runtime/ops_diagnostics.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market, pulse_lab, token_intel | - | 1 / 8 | 924 | `7961279dfe66` |
| `src/parallax/app/runtime/projection_dirty_targets.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | news_intel | news_items, news_sources | 2 / 3 | 260 | `001156460f94` |
| `src/parallax/app/runtime/provider_wiring/__init__.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 0 / 2 | 81 | `94cb6e9514cb` |
| `src/parallax/app/runtime/provider_wiring/asset_market.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market | - | 0 / 4 | 220 | `837ca8183b39` |
| `src/parallax/app/runtime/provider_wiring/binance.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market, cex_market_intel | - | 1 / 5 | 235 | `8be11a825f9b` |
| `src/parallax/app/runtime/provider_wiring/cex_market_intel.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | cex_market_intel | - | 0 / 3 | 39 | `e265caa7c5f1` |
| `src/parallax/app/runtime/provider_wiring/gmgn.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market, ingestion | - | 0 / 7 | 183 | `c6c346af0a2d` |
| `src/parallax/app/runtime/provider_wiring/model_execution.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | pulse_lab | - | 1 / 8 | 183 | `a6309390f506` |
| `src/parallax/app/runtime/provider_wiring/news.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | news_intel | - | 0 / 8 | 127 | `f34a2f535737` |
| `src/parallax/app/runtime/provider_wiring/okx.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market | - | 0 / 7 | 315 | `893f025f28cb` |
| `src/parallax/app/runtime/provider_wiring/types.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market, cex_market_intel, ingestion, news_intel, pulse_lab | - | 6 / 5 | 173 | `e7b25088ddb9` |
| `src/parallax/app/runtime/providers_wiring.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 5 / 1 | 24 | `d6fe3ea51b0e` |
| `src/parallax/app/runtime/queue_health.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | worker_queue_terminal_events | 2 / 1 | 826 | `05ce6c79c82a` |
| `src/parallax/app/runtime/repository_session.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | asset_market, cex_market_intel, evidence, macro_intel, narrative_intel, news_intel, notifications, pulse_lab, token_intel, watchlist_intel | - | 10 / 42 | 264 | `9304338a2454` |
| `src/parallax/app/runtime/telemetry.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 5 / 0 | 173 | `2dc72ac6c2ed` |
| `src/parallax/app/runtime/wake_bus.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 2 / 0 | 106 | `284d8edef801` |
| `src/parallax/app/runtime/wake_waiter.py` | 应用运行时 | 进程组装、worker 注册、队列健康或运行控制 | - | - | 1 / 0 | 130 | `563aa9c38f6d` |
| `src/parallax/app/runtime/worker_base.py` | worker 运行时 | worker 生命周期、wake/catch-up 或运行清单 | - | - | 37 / 2 | 590 | `ee8a4dd215b8` |
| `src/parallax/app/runtime/worker_factories/__init__.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | - | - | 0 / 17 | 303 | `8434f266d5f3` |
| `src/parallax/app/runtime/worker_factories/asset_market.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | asset_market, token_intel | - | 1 / 13 | 139 | `59924c106b20` |
| `src/parallax/app/runtime/worker_factories/cex_market_intel.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | cex_market_intel | - | 1 / 3 | 37 | `efdacaae4ed7` |
| `src/parallax/app/runtime/worker_factories/ingestion.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | - | - | 1 / 2 | 21 | `0cd01619c1ca` |
| `src/parallax/app/runtime/worker_factories/macro_intel.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | macro_intel | - | 1 / 6 | 56 | `4946387580f1` |
| `src/parallax/app/runtime/worker_factories/narrative_intel.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | narrative_intel | - | 1 / 3 | 30 | `e7687863e326` |
| `src/parallax/app/runtime/worker_factories/news_intel.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | news_intel, token_intel | - | 1 / 10 | 214 | `0cda6003650d` |
| `src/parallax/app/runtime/worker_factories/notifications.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | account_quality, notifications | - | 1 / 7 | 96 | `b91769dc30bc` |
| `src/parallax/app/runtime/worker_factories/pulse.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | pulse_lab | - | 1 / 3 | 29 | `4fcd32853c63` |
| `src/parallax/app/runtime/worker_factories/token_intel.py` | worker 工厂 | 配置/manifest 到唯一运行时 owner 的组装 | token_intel | - | 1 / 3 | 26 | `bb053eae3333` |
| `src/parallax/app/runtime/worker_manifest.py` | worker 运行时 | worker 生命周期、wake/catch-up 或运行清单 | - | - | 17 / 0 | 1526 | `2c39b8d28f71` |
| `src/parallax/app/runtime/worker_result.py` | worker 运行时 | worker 生命周期、wake/catch-up 或运行清单 | - | - | 28 / 0 | 13 | `c6a25aaa117e` |
| `src/parallax/app/runtime/worker_scheduler.py` | worker 运行时 | worker 生命周期、wake/catch-up 或运行清单 | - | - | 1 / 2 | 210 | `f98c35118914` |
| `src/parallax/app/runtime/worker_status.py` | worker 运行时 | worker 生命周期、wake/catch-up 或运行清单 | - | - | 5 / 2 | 288 | `e0b96bd458bb` |
| `src/parallax/app/surfaces/__init__.py` | __init__.py 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/app/surfaces/api/__init__.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/app/surfaces/api/dependencies.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 12 / 3 | 57 | `abaecea5940a` |
| `src/parallax/app/surfaces/api/exceptions.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 9 / 1 | 28 | `7a42382d5542` |
| `src/parallax/app/surfaces/api/http.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 1 / 0 | 38 | `fad527b1df3a` |
| `src/parallax/app/surfaces/api/responses.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 12 / 0 | 23 | `59c3321e3e24` |
| `src/parallax/app/surfaces/api/routes_cex.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 4 | 128 | `92d15050e00b` |
| `src/parallax/app/surfaces/api/routes_events.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | account_quality | - | 0 / 4 | 155 | `777626cbac2b` |
| `src/parallax/app/surfaces/api/routes_macro.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | macro_intel, news_intel | - | 0 / 11 | 358 | `d83de0740096` |
| `src/parallax/app/surfaces/api/routes_news.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | news_intel | - | 0 / 6 | 163 | `6b513d1cee3d` |
| `src/parallax/app/surfaces/api/routes_notifications.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | account_quality | - | 0 / 5 | 541 | `9103c631bba2` |
| `src/parallax/app/surfaces/api/routes_ops.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 4 | 65 | `71fbfbfe8406` |
| `src/parallax/app/surfaces/api/routes_pulse.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | pulse_lab | - | 0 / 5 | 115 | `2d50c601aaca` |
| `src/parallax/app/surfaces/api/routes_radar.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | asset_market, narrative_intel, token_intel | - | 0 / 8 | 120 | `e8b58698b917` |
| `src/parallax/app/surfaces/api/routes_search.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | asset_market, narrative_intel, token_intel | - | 0 / 14 | 257 | `db0410f5abdf` |
| `src/parallax/app/surfaces/api/routes_status.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 2 | 41 | `7a618ca83fb5` |
| `src/parallax/app/surfaces/api/routes_token_images.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 1 | 64 | `b73a6f380f02` |
| `src/parallax/app/surfaces/api/routes_watchlist.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | watchlist_intel | - | 0 / 5 | 111 | `f064636533ca` |
| `src/parallax/app/surfaces/api/schemas.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 1 / 0 | 668 | `28ff12f8107e` |
| `src/parallax/app/surfaces/api/validators.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | pulse_lab | - | 9 / 2 | 119 | `4a7c8de9e2dc` |
| `src/parallax/app/surfaces/api/ws.py` | api 表面 | 只读/命令边界；不得成为 read model 第二写者 | evidence, ingestion | - | 2 / 2 | 338 | `8c79525720fa` |
| `src/parallax/app/surfaces/cli/__init__.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/app/surfaces/cli/commands/__init__.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 0 | 8 | `a5c03095590c` |
| `src/parallax/app/surfaces/cli/commands/config.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 2 | 139 | `d1e35e881009` |
| `src/parallax/app/surfaces/cli/commands/db.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | token_intel | - | 0 / 6 | 46 | `27d5c54b5a89` |
| `src/parallax/app/surfaces/cli/commands/macro.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | macro_intel | - | 0 / 8 | 411 | `26c17ac8493a` |
| `src/parallax/app/surfaces/cli/commands/ops.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | account_quality, asset_market, token_intel | - | 0 / 31 | 1134 | `fb3b443d5775` |
| `src/parallax/app/surfaces/cli/commands/pulse_replay.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | pulse_lab | - | 0 / 3 | 54 | `c473704e4ccc` |
| `src/parallax/app/surfaces/cli/commands/queue_ops.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | asset_market | - | 0 / 4 | 582 | `2ea9de639f62` |
| `src/parallax/app/surfaces/cli/commands/read_models.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | account_quality, asset_market, token_intel | - | 0 / 9 | 121 | `ca364ed96ad0` |
| `src/parallax/app/surfaces/cli/commands/serve.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 3 | 21 | `f9ec4291f3c5` |
| `src/parallax/app/surfaces/cli/dependencies.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 5 / 2 | 29 | `e9b56cf76812` |
| `src/parallax/app/surfaces/cli/main.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | - | - | 0 / 0 | 56 | `e9084a32c486` |
| `src/parallax/app/surfaces/cli/parser.py` | cli 表面 | 只读/命令边界；不得成为 read model 第二写者 | pulse_lab | - | 0 / 2 | 297 | `de3b8d4ca4cf` |
| `src/parallax/cli.py` | 入口 | 服务/CLI 包入口 | - | - | 0 / 0 | 5 | `c54225713477` |
| `src/parallax/domains/__init__.py` | __init__.py 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/account_quality/__init__.py` | account_quality 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/account_quality/read_models/__init__.py` | account_quality 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/account_quality/read_models/account_alert_service.py` | account_quality 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 3 / 0 | 33 | `2a6706d8abaf` |
| `src/parallax/domains/account_quality/read_models/account_quality_service.py` | account_quality 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 3 / 0 | 70 | `5fca029aeede` |
| `src/parallax/domains/account_quality/repositories/__init__.py` | account_quality repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/account_quality/repositories/account_quality_repository.py` | account_quality repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | account_profiles, account_quality_snapshots, account_token_call_stats, events, market_ticks, price_feeds, registry_assets, token_intent_resolutions | 1 / 0 | 639 | `722027df5646` |
| `src/parallax/domains/account_quality/services/__init__.py` | account_quality service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 5 | `d3836282e147` |
| `src/parallax/domains/account_quality/services/account_quality_backfill_service.py` | account_quality service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 1 / 1 | 206 | `827f9fa00e2d` |
| `src/parallax/domains/asset_market/__init__.py` | asset_market 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/asset_market/identity_evidence_policy.py` | asset_market 模块 | 领域逻辑、模型或辅助边界 | - | - | 3 / 0 | 162 | `28f3e15d76a5` |
| `src/parallax/domains/asset_market/interfaces.py` | asset_market 契约 | 稳定领域类型、公开常量或协议 | - | - | 7 / 0 | 64 | `816adc019623` |
| `src/parallax/domains/asset_market/profile_source_selection.py` | asset_market 模块 | 领域逻辑、模型或辅助边界 | asset_market | - | 1 / 1 | 93 | `cda6b8100483` |
| `src/parallax/domains/asset_market/providers.py` | asset_market provider port | 领域所需 provider 能力契约 | - | - | 12 / 0 | 197 | `4c6a7bb4629c` |
| `src/parallax/domains/asset_market/queries/__init__.py` | asset_market query | 无副作用查询/投影输入读取 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/asset_market/queries/token_profile_source_query.py` | asset_market query | 无副作用查询/投影输入读取 | asset_market | asset_identity_evidence, asset_profiles, cex_token_profiles, cex_tokens | 1 / 2 | 127 | `05d1ec60af35` |
| `src/parallax/domains/asset_market/read_models/__init__.py` | asset_market 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 0 / 0 | 1 | `5384bfdb2df3` |
| `src/parallax/domains/asset_market/read_models/market_candles_service.py` | asset_market 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 66 | `ad0792e45997` |
| `src/parallax/domains/asset_market/read_models/message_price_payload.py` | asset_market 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 0 / 0 | 45 | `d1fce13a4f88` |
| `src/parallax/domains/asset_market/read_models/token_profile_read_model.py` | asset_market 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 3 / 0 | 182 | `6a96e3d83d94` |
| `src/parallax/domains/asset_market/repositories/__init__.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | asset_profile_refresh_targets, asset_profiles, token_radar_current_rows | 1 / 2 | 606 | `7a96d19ac1da` |
| `src/parallax/domains/asset_market/repositories/asset_profile_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | asset_profiles | 0 / 1 | 219 | `da7c2ee636c5` |
| `src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | cex_tokens | 1 / 1 | 150 | `976292a41a0b` |
| `src/parallax/domains/asset_market/repositories/discovery_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | token_discovery_dirty_lookup_keys, token_discovery_results | 1 / 1 | 839 | `d129486beb4a` |
| `src/parallax/domains/asset_market/repositories/enriched_event_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | asset_market | enriched_events, market_ticks | 0 / 0 | 184 | `39ae13f3114c` |
| `src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | asset_market | enriched_events, event_anchor_backfill_jobs | 0 / 1 | 663 | `8494c3555c84` |
| `src/parallax/domains/asset_market/repositories/identity_evidence_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | asset_market | asset_identity_evidence, registry_assets | 0 / 1 | 411 | `343600cdda79` |
| `src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | market_tick_current_dirty_targets | 1 / 2 | 522 | `b5f0f0190646` |
| `src/parallax/domains/asset_market/repositories/market_tick_current_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | market_ticks | 1 / 1 | 171 | `e9c1662021e6` |
| `src/parallax/domains/asset_market/repositories/market_tick_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | asset_market | market_ticks, requested | 0 / 1 | 300 | `a830e1b37193` |
| `src/parallax/domains/asset_market/repositories/registry_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | asset_identity_current, asset_identity_evidence, cex_tokens, market_ticks, price_feeds, registry_assets, token_capture_tier, token_radar_current_rows, token_radar_publication_state, us_equity_symbols | 0 / 0 | 945 | `bcde5d38e763` |
| `src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | token_capture_tier_dirty_targets | 2 / 2 | 568 | `c2dcdcb28560` |
| `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | market_ticks, token_capture_tier | 0 / 0 | 235 | `db2c57aeba0d` |
| `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | token_image_assets | 1 / 1 | 392 | `648c1f5eb3d2` |
| `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | token_image_source_dirty_targets, worker_queue_terminal_events | 1 / 3 | 713 | `b68f5671e658` |
| `src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | token_profile_current_dirty_targets | 1 / 2 | 599 | `3eb489a154e5` |
| `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py` | asset_market repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | token_profile_current | 0 / 2 | 228 | `f005e2283ddb` |
| `src/parallax/domains/asset_market/runtime/__init__.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market | - | 2 / 4 | 294 | `f2d7eda8d011` |
| `src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market | - | 1 / 5 | 540 | `50ba4fbc3e35` |
| `src/parallax/domains/asset_market/runtime/live_price_gateway.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 1 / 2 | 337 | `4340a9597ba3` |
| `src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 1 / 2 | 176 | `c92bdf7d97c0` |
| `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market | - | 1 / 4 | 539 | `c3d069f07e31` |
| `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market | - | 1 / 4 | 388 | `3ba125274de3` |
| `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market, token_intel | - | 2 / 4 | 795 | `d33f8334fad1` |
| `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | token_intel | - | 1 / 3 | 320 | `e6965ee5da64` |
| `src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market | - | 2 / 3 | 341 | `dd0a873150f4` |
| `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py` | asset_market worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market | - | 2 / 4 | 373 | `5f10b6dd9662` |
| `src/parallax/domains/asset_market/services/__init__.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/asset_market/services/asset_market_sync.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 125 | `7a376d6dc7e7` |
| `src/parallax/domains/asset_market/services/asset_profile_refresh.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | asset_market | - | 1 / 1 | 126 | `0e7d3e543806` |
| `src/parallax/domains/asset_market/services/cex_token_profile_sync.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | asset_market | - | 1 / 1 | 109 | `55052850e167` |
| `src/parallax/domains/asset_market/services/event_market_capture.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | asset_market | - | 2 / 2 | 454 | `d12348515a7a` |
| `src/parallax/domains/asset_market/services/market_tick_persistence.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | asset_market | - | 3 / 0 | 56 | `6b9fcce8c58d` |
| `src/parallax/domains/asset_market/services/token_image_mirror.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | - | - | 2 / 0 | 249 | `7a04a70dd874` |
| `src/parallax/domains/asset_market/services/token_image_source_admission.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | asset_market | - | 1 / 1 | 418 | `d8c261f5623b` |
| `src/parallax/domains/asset_market/services/token_profile_current_projection.py` | asset_market 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 537 | `1a82bc548306` |
| `src/parallax/domains/asset_market/services/us_equity_symbol_sync.py` | asset_market service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 158 | `b9403942d8aa` |
| `src/parallax/domains/asset_market/types/__init__.py` | asset_market 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 21 | `4be0f1743837` |
| `src/parallax/domains/asset_market/types/market_tick.py` | asset_market 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 51 | `c132ba4fa25b` |
| `src/parallax/domains/asset_market/types/market_tick_id.py` | asset_market 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 9 | `d12f2d124751` |
| `src/parallax/domains/cex_market_intel/__init__.py` | cex_market_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `f675f1b52a2c` |
| `src/parallax/domains/cex_market_intel/providers.py` | cex_market_intel provider port | 领域所需 provider 能力契约 | - | - | 6 / 0 | 63 | `2420ad401d26` |
| `src/parallax/domains/cex_market_intel/repositories/__init__.py` | cex_market_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 1 | `019fda78b8a5` |
| `src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py` | cex_market_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 1 / 0 | 141 | `3e2119130d13` |
| `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py` | cex_market_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | cex_detail_snapshots | 1 / 1 | 323 | `f826196fd922` |
| `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py` | cex_market_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | cex_oi_radar_publication_state, cex_oi_radar_rows, price_feeds | 1 / 1 | 582 | `386c154d0584` |
| `src/parallax/domains/cex_market_intel/runtime/__init__.py` | cex_market_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 1 | `6776a65496e3` |
| `src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py` | cex_market_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | cex_market_intel | - | 1 / 6 | 269 | `ef6d5d396e3a` |
| `src/parallax/domains/cex_market_intel/scoring/__init__.py` | cex_market_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `f4d5893646bb` |
| `src/parallax/domains/cex_market_intel/scoring/oi_radar_scoring.py` | cex_market_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 43 | `96feed572940` |
| `src/parallax/domains/cex_market_intel/services/__init__.py` | cex_market_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 1 | `9177e4a12aa9` |
| `src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py` | cex_market_intel service | 领域用例/事务编排；不绕过 repository owner | cex_market_intel | - | 1 / 2 | 244 | `b7fee585a88b` |
| `src/parallax/domains/cex_market_intel/services/cex_detail_snapshot_builder.py` | cex_market_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 332 | `d76b76e36793` |
| `src/parallax/domains/cex_market_intel/services/coinglass_detail_enricher.py` | cex_market_intel service | 领域用例/事务编排；不绕过 repository owner | cex_market_intel | - | 1 / 1 | 212 | `70c06326fd47` |
| `src/parallax/domains/evidence/__init__.py` | evidence 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/evidence/interfaces.py` | evidence 契约 | 稳定领域类型、公开常量或协议 | - | - | 13 / 0 | 44 | `88209db19fee` |
| `src/parallax/domains/evidence/repositories/__init__.py` | evidence repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/evidence/repositories/entity_repository.py` | evidence repository | PostgreSQL 事实、控制状态或读模型持久化边界 | evidence | event_entities | 3 / 2 | 211 | `006b06f7f68f` |
| `src/parallax/domains/evidence/repositories/evidence_repository.py` | evidence repository | PostgreSQL 事实、控制状态或读模型持久化边界 | evidence | event_entities, events, raw_frames | 3 / 5 | 435 | `e82fee7b2321` |
| `src/parallax/domains/evidence/services/__init__.py` | evidence service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/evidence/services/entity_extractor.py` | evidence service | 领域用例/事务编排；不绕过 repository owner | evidence | - | 0 / 2 | 292 | `6fb0dad9d5a3` |
| `src/parallax/domains/evidence/services/ingest_service.py` | evidence service | 领域用例/事务编排；不绕过 repository owner | asset_market, evidence, ingestion, token_intel | - | 1 / 6 | 631 | `6c066d5a7e77` |
| `src/parallax/domains/evidence/types/__init__.py` | evidence 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/evidence/types/entity.py` | evidence 模块 | 领域逻辑、模型或辅助边界 | - | - | 3 / 0 | 77 | `29138568baa2` |
| `src/parallax/domains/evidence/types/tweet_identity.py` | evidence 模块 | 领域逻辑、模型或辅助边界 | evidence | - | 1 / 1 | 15 | `a7f730d7d17e` |
| `src/parallax/domains/evidence/types/tweet_text.py` | evidence 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 75 | `e616714011af` |
| `src/parallax/domains/evidence/types/twitter_event.py` | evidence 模块 | 领域逻辑、模型或辅助边界 | - | - | 3 / 0 | 100 | `2a79c674b839` |
| `src/parallax/domains/ingestion/__init__.py` | ingestion 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/ingestion/interfaces.py` | ingestion 契约 | 稳定领域类型、公开常量或协议 | evidence | - | 2 / 1 | 16 | `1d6327626747` |
| `src/parallax/domains/ingestion/providers.py` | ingestion provider port | 领域所需 provider 能力契约 | evidence, ingestion | - | 3 / 2 | 33 | `08b612b62660` |
| `src/parallax/domains/ingestion/runtime/__init__.py` | ingestion worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/ingestion/runtime/collector_service.py` | ingestion worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | ingestion | - | 1 / 5 | 227 | `c311e339506c` |
| `src/parallax/domains/ingestion/services/__init__.py` | ingestion service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/ingestion/services/normalizer.py` | ingestion service | 领域用例/事务编排；不绕过 repository owner | evidence, ingestion | - | 1 / 2 | 270 | `895e58f05ff1` |
| `src/parallax/domains/ingestion/services/subscriptions.py` | ingestion service | 领域用例/事务编排；不绕过 repository owner | evidence | - | 2 / 1 | 28 | `a18bdee58a29` |
| `src/parallax/domains/ingestion/types/__init__.py` | ingestion 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/ingestion/types/gmgn_token_payload.py` | ingestion 模块 | 领域逻辑、模型或辅助边界 | evidence | - | 1 / 1 | 109 | `6ce0b2191865` |
| `src/parallax/domains/macro_intel/__init__.py` | macro_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `98b85d41fa12` |
| `src/parallax/domains/macro_intel/_constants.py` | macro_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 12 / 0 | 1378 | `93a4a36e685c` |
| `src/parallax/domains/macro_intel/observation_identity.py` | macro_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 7 / 1 | 119 | `a81c4095ace5` |
| `src/parallax/domains/macro_intel/repositories/__init__.py` | macro_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 1 | `db6d9e499b5c` |
| `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py` | macro_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | macro_intel | macro_daily_briefs, macro_import_runs, macro_observation_series_publication_state, macro_observation_series_rows, macro_observations, macro_projection_dirty_targets, macro_sync_runs, macro_sync_state, macro_sync_windows, macro_view_snapshots | 1 / 5 | 2467 | `7b61dcf32785` |
| `src/parallax/domains/macro_intel/runtime/__init__.py` | macro_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 1 | `57e75968a922` |
| `src/parallax/domains/macro_intel/runtime/macro_daily_brief_projection_worker.py` | macro_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | macro_intel | - | 1 / 5 | 69 | `b16223cbb290` |
| `src/parallax/domains/macro_intel/runtime/macro_sync_worker.py` | macro_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | macro_intel | - | 1 / 4 | 122 | `144578148ec4` |
| `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py` | macro_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | macro_intel | - | 1 / 5 | 298 | `31d2e2faaa7a` |
| `src/parallax/domains/macro_intel/services/__init__.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 1 | `c30fb6bdea96` |
| `src/parallax/domains/macro_intel/services/macro_asset_correlation.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 1 / 1 | 366 | `71d0ffaeb991` |
| `src/parallax/domains/macro_intel/services/macro_daily_brief.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 241 | `659719d659a4` |
| `src/parallax/domains/macro_intel/services/macro_feature_engine.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 1 / 3 | 402 | `e4005bded59b` |
| `src/parallax/domains/macro_intel/services/macro_gap_payloads.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 5 / 1 | 146 | `e7f6e241e1a7` |
| `src/parallax/domains/macro_intel/services/macro_module_catalog.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 2 / 1 | 914 | `b0c3ffa841ae` |
| `src/parallax/domains/macro_intel/services/macro_module_views.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 1 / 3 | 8249 | `5d9b0a9d554a` |
| `src/parallax/domains/macro_intel/services/macro_regime_engine.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 1 / 4 | 1249 | `3e0666d38095` |
| `src/parallax/domains/macro_intel/services/macro_scenario_engine.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 1 / 1 | 973 | `cda0e11599ea` |
| `src/parallax/domains/macro_intel/services/macro_series_view.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 1 / 1 | 197 | `205ca277980a` |
| `src/parallax/domains/macro_intel/services/macro_sync_scheduler.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 1 | 148 | `a3cac72ece76` |
| `src/parallax/domains/macro_intel/services/macro_sync_service.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 2 / 5 | 608 | `68e6f2c14d3d` |
| `src/parallax/domains/macro_intel/services/macro_sync_types.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 4 / 0 | 56 | `dd12a10abfff` |
| `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py` | macro_intel service | 领域用例/事务编排；不绕过 repository owner | macro_intel | - | 2 / 4 | 304 | `9f5cc61dc576` |
| `src/parallax/domains/narrative_intel/__init__.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `3b54027cfd42` |
| `src/parallax/domains/narrative_intel/_constants.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 5 | `11d3d0b8b8fa` |
| `src/parallax/domains/narrative_intel/interfaces.py` | narrative_intel 契约 | 稳定领域类型、公开常量或协议 | narrative_intel | - | 1 / 1 | 28 | `6757c825eabd` |
| `src/parallax/domains/narrative_intel/read_models/__init__.py` | narrative_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | narrative_intel | - | 0 / 1 | 3 | `1b662546db5a` |
| `src/parallax/domains/narrative_intel/read_models/narrative_read_model.py` | narrative_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | narrative_intel | - | 3 / 2 | 344 | `988be90f7059` |
| `src/parallax/domains/narrative_intel/repositories/__init__.py` | narrative_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | narrative_intel | - | 0 / 2 | 9 | `c937ae430f56` |
| `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py` | narrative_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 2 / 2 | 843 | `ab5d6e7c1d58` |
| `src/parallax/domains/narrative_intel/repositories/narrative_repository.py` | narrative_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | narrative_intel | events, narrative_admissions, token_discussion_digests, token_intent_resolutions, token_mention_semantics, token_radar_current_rows, token_radar_publication_state | 2 / 4 | 744 | `8d3459bb9002` |
| `src/parallax/domains/narrative_intel/runtime/__init__.py` | narrative_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | narrative_intel | - | 0 / 1 | 3 | `ff7e0f59146d` |
| `src/parallax/domains/narrative_intel/runtime/narrative_admission_worker.py` | narrative_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | narrative_intel | - | 2 / 3 | 312 | `017dfea9eb5e` |
| `src/parallax/domains/narrative_intel/services/__init__.py` | narrative_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 1 | `30eb1adb921f` |
| `src/parallax/domains/narrative_intel/services/narrative_admission.py` | narrative_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 141 | `ad6b8e161b93` |
| `src/parallax/domains/narrative_intel/types/__init__.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | narrative_intel | - | 0 / 1 | 5 | `b2cf0e5190ca` |
| `src/parallax/domains/narrative_intel/types/evidence_refs.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 33 | `166c517a9f22` |
| `src/parallax/domains/narrative_intel/types/fingerprints.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 47 | `3140b5e96944` |
| `src/parallax/domains/narrative_intel/types/narrative_currentness.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | narrative_intel | - | 2 / 1 | 317 | `2da8982d381b` |
| `src/parallax/domains/narrative_intel/types/narrative_epoch_policy.py` | narrative_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 6 | `2181b89213f3` |
| `src/parallax/domains/news_intel/__init__.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `37d0b7c61ae1` |
| `src/parallax/domains/news_intel/_constants.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 13 / 0 | 15 | `655694571cfd` |
| `src/parallax/domains/news_intel/providers.py` | news_intel provider port | 领域所需 provider 能力契约 | news_intel | - | 3 / 4 | 96 | `f83c40c459be` |
| `src/parallax/domains/news_intel/queries/__init__.py` | news_intel query | 无副作用查询/投影输入读取 | - | - | 0 / 0 | 1 | `b86dc1f63462` |
| `src/parallax/domains/news_intel/queries/news_page_query.py` | news_intel query | 无副作用查询/投影输入读取 | news_intel | - | 2 / 1 | 57 | `830a33d37573` |
| `src/parallax/domains/news_intel/repositories/__init__.py` | news_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 1 | `290ccf1dda90` |
| `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py` | news_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | news_projection_dirty_targets | 1 / 2 | 799 | `284939bdbcb9` |
| `src/parallax/domains/news_intel/repositories/news_repository.py` | news_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | news_intel | news_fact_candidates, news_fetch_runs, news_item_agent_briefs, news_item_agent_runs, news_item_entities, news_item_observation_edges, news_items, news_page_rows, news_projection_dirty_targets, news_provider_items, news_source_quality_rows, news_sources, news_story_agent_briefs, news_story_agent_runs, news_token_mentions, pg_constraint | 2 / 14 | 7618 | `160e50a67383` |
| `src/parallax/domains/news_intel/runtime/__init__.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 1 | `9ac6ab8bf4b8` |
| `src/parallax/domains/news_intel/runtime/news_fetch_worker.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | news_intel | - | 1 / 9 | 526 | `baa027c45652` |
| `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | news_intel | - | 1 / 11 | 1419 | `4fe65f56a064` |
| `src/parallax/domains/news_intel/runtime/news_item_process_worker.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | news_intel, token_intel | - | 1 / 16 | 542 | `3b64322553e2` |
| `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | news_intel | - | 1 / 6 | 353 | `3924782dec19` |
| `src/parallax/domains/news_intel/runtime/news_projection_work.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 7 / 0 | 497 | `29e1c7bd19f4` |
| `src/parallax/domains/news_intel/runtime/news_runtime_settings.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 6 / 0 | 26 | `6d3a511ca9e4` |
| `src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | news_intel | - | 1 / 6 | 341 | `96e6ae7fb0ea` |
| `src/parallax/domains/news_intel/runtime/news_story_brief_worker.py` | news_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | news_intel | - | 1 / 9 | 1065 | `87d263e4f507` |
| `src/parallax/domains/news_intel/services/__init__.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 1 | `5fcba48c396b` |
| `src/parallax/domains/news_intel/services/feed_item_normalizer.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 2 | 210 | `8808f85e3e7f` |
| `src/parallax/domains/news_intel/services/news_content_classification.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 1 | 160 | `2fe4545abf3d` |
| `src/parallax/domains/news_intel/services/news_entity_extraction.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | evidence, news_intel | - | 1 / 3 | 73 | `23716a02ae93` |
| `src/parallax/domains/news_intel/services/news_fact_candidates.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 3 | 178 | `082a72ba35d1` |
| `src/parallax/domains/news_intel/services/news_item_agent_admission.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 2 / 4 | 301 | `5ad7c67e8bad` |
| `src/parallax/domains/news_intel/services/news_item_agent_policy.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 2 / 1 | 166 | `11453ac72a4e` |
| `src/parallax/domains/news_intel/services/news_item_brief_entity_support.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 2 | 1153 | `10942b781430` |
| `src/parallax/domains/news_intel/services/news_item_brief_input.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 3 / 2 | 607 | `9eb5e95ff5e5` |
| `src/parallax/domains/news_intel/services/news_item_brief_stage.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 2 / 5 | 68 | `0cdf4c6dc9c7` |
| `src/parallax/domains/news_intel/services/news_item_brief_validation.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 2 / 4 | 340 | `3629772644f5` |
| `src/parallax/domains/news_intel/services/news_market_scope.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 2 / 2 | 339 | `63f0e71d13a1` |
| `src/parallax/domains/news_intel/services/news_material_delta.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 1 | 133 | `d6fb689642d3` |
| `src/parallax/domains/news_intel/services/news_page_projection.py` | news_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | news_intel | - | 1 / 2 | 857 | `4d84cf334231` |
| `src/parallax/domains/news_intel/services/news_provider_contract.py` | news_intel provider port | 领域所需 provider 能力契约 | - | - | 2 / 0 | 116 | `eb5c6ad6a896` |
| `src/parallax/domains/news_intel/services/news_story_brief_input.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 2 / 4 | 273 | `52a45a1dc48f` |
| `src/parallax/domains/news_intel/services/news_story_brief_stage.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 7 | 65 | `64197fdf00e0` |
| `src/parallax/domains/news_intel/services/news_story_identity.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel | - | 1 / 2 | 443 | `d43ab2f7e41b` |
| `src/parallax/domains/news_intel/services/news_story_similarity.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 197 | `a026ff8632b9` |
| `src/parallax/domains/news_intel/services/news_token_mentions.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | news_intel, token_intel | - | 1 / 3 | 143 | `e174ad48605f` |
| `src/parallax/domains/news_intel/services/opennews_provider_signal.py` | news_intel provider port | 领域所需 provider 能力契约 | - | - | 1 / 0 | 96 | `63a96b329095` |
| `src/parallax/domains/news_intel/services/source_authority.py` | news_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 170 | `58945662dc8b` |
| `src/parallax/domains/news_intel/services/source_quality_projection.py` | news_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 222 | `48ba38ff63a4` |
| `src/parallax/domains/news_intel/types/__init__.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 0 / 1 | 54 | `83abefa63077` |
| `src/parallax/domains/news_intel/types/content_classification.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 45 | `bd44ea175b57` |
| `src/parallax/domains/news_intel/types/news_canonical_identity.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 1 / 3 | 197 | `3cfcfa89a9f7` |
| `src/parallax/domains/news_intel/types/news_extraction.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 4 / 0 | 60 | `bd5e8ddae510` |
| `src/parallax/domains/news_intel/types/news_item_agent_admission.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 5 / 1 | 82 | `b792c3c49a90` |
| `src/parallax/domains/news_intel/types/news_item_brief.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 10 / 1 | 277 | `df77d5e7e9f9` |
| `src/parallax/domains/news_intel/types/news_item_brief_contract.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 1 / 1 | 43 | `812ded640644` |
| `src/parallax/domains/news_intel/types/news_market_scope.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 3 / 1 | 43 | `0e99c4ee604e` |
| `src/parallax/domains/news_intel/types/news_material_identity.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 2 / 1 | 79 | `d4bea457af91` |
| `src/parallax/domains/news_intel/types/news_page_search.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 80 | `09b1b4b1f271` |
| `src/parallax/domains/news_intel/types/news_source_role_rank.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 2 / 1 | 44 | `54013f26d5bc` |
| `src/parallax/domains/news_intel/types/news_story_brief.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 7 / 3 | 111 | `7a3dd0b361d8` |
| `src/parallax/domains/news_intel/types/news_story_identity.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 3 / 0 | 17 | `848a2d7b86cf` |
| `src/parallax/domains/news_intel/types/news_url_identity.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | news_intel | - | 3 / 1 | 216 | `7b4c6599e468` |
| `src/parallax/domains/news_intel/types/source_classification.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 3 / 0 | 88 | `df2bf9aa5759` |
| `src/parallax/domains/news_intel/types/source_provider.py` | news_intel provider port | 领域所需 provider 能力契约 | - | - | 3 / 0 | 75 | `edefd8371008` |
| `src/parallax/domains/news_intel/types/source_quality_policy.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 19 | `97673cbde40d` |
| `src/parallax/domains/news_intel/types/text_normalization.py` | news_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 6 / 0 | 174 | `7a8778d3db03` |
| `src/parallax/domains/notifications/__init__.py` | notifications 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/notifications/repositories/__init__.py` | notifications repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/notifications/repositories/notification_repository.py` | notifications repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | notification_deliveries, notification_reads, notifications | 3 / 0 | 1145 | `3ae4f1e210a4` |
| `src/parallax/domains/notifications/runtime/__init__.py` | notifications worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/notifications/runtime/notification_delivery.py` | notifications worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | notifications | - | 1 / 5 | 246 | `87d9aff67ef0` |
| `src/parallax/domains/notifications/runtime/notification_runtime_settings.py` | notifications worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 2 / 0 | 19 | `7fca70dae7d8` |
| `src/parallax/domains/notifications/runtime/notification_worker.py` | notifications worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | notifications | - | 1 / 7 | 206 | `dd8bf1b91179` |
| `src/parallax/domains/notifications/services/__init__.py` | notifications service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/notifications/services/notification_rules.py` | notifications service | 领域用例/事务编排；不绕过 repository owner | notifications, pulse_lab, token_intel | - | 1 / 4 | 1298 | `05987ae63f0d` |
| `src/parallax/domains/notifications/services/pulse_surface_card.py` | notifications service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 1 | 256 | `e4258edbd403` |
| `src/parallax/domains/notifications/types.py` | notifications 契约 | 稳定领域类型、公开常量或协议 | - | - | 1 / 0 | 25 | `9956cca834fc` |
| `src/parallax/domains/pulse_lab/__init__.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/pulse_lab/interfaces.py` | pulse_lab 契约 | 稳定领域类型、公开常量或协议 | pulse_lab | - | 10 / 1 | 88 | `60d26cc9a628` |
| `src/parallax/domains/pulse_lab/prompts/__init__.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `24956a4377c7` |
| `src/parallax/domains/pulse_lab/providers.py` | pulse_lab provider port | 领域所需 provider 能力契约 | pulse_lab | - | 6 / 4 | 163 | `99d0abc7f264` |
| `src/parallax/domains/pulse_lab/queries/pulse_agent_cost_report.py` | pulse_lab query | 无副作用查询/投影输入读取 | - | pulse_agent_eval_cases, pulse_agent_eval_results, pulse_agent_jobs, pulse_agent_run_steps, pulse_agent_runs | 0 / 0 | 456 | `dd54a3e6b7ba` |
| `src/parallax/domains/pulse_lab/queries/pulse_freshness_health_queries.py` | pulse_lab query | 无副作用查询/投影输入读取 | - | pulse_agent_jobs, pulse_agent_runs, pulse_candidates, pulse_evidence_packets | 3 / 0 | 156 | `483b8aff94b7` |
| `src/parallax/domains/pulse_lab/queries/pulse_policy_evaluator.py` | pulse_lab query | 无副作用查询/投影输入读取 | pulse_lab, token_intel | pulse_agent_jobs, pulse_agent_runs, pulse_candidates, token_radar_current_rows, token_radar_publication_state | 0 / 2 | 769 | `56ff9ab4dc56` |
| `src/parallax/domains/pulse_lab/read_models/__init__.py` | pulse_lab 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py` | pulse_lab 投影 | 从事实重建派生状态；稳定键且无变化零写入 | token_intel | - | 1 / 1 | 391 | `998ca2a7a27f` |
| `src/parallax/domains/pulse_lab/repositories/__init__.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | - | 0 / 10 | 27 | `712ce91a8865` |
| `src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 10 / 0 | 152 | `7ee391153db0` |
| `src/parallax/domains/pulse_lab/repositories/pulse_admission_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_agent_jobs, pulse_agent_runs, pulse_candidate_edge_state, pulse_candidate_run_budget, pulse_target_run_budget | 2 / 1 | 546 | `6ec35aace8cb` |
| `src/parallax/domains/pulse_lab/repositories/pulse_agent_eval_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_agent_eval_cases, pulse_agent_eval_results, pulse_agent_runtime_versions | 2 / 1 | 218 | `5851c51fde80` |
| `src/parallax/domains/pulse_lab/repositories/pulse_candidates_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_candidates | 2 / 2 | 343 | `70a2a21a275e` |
| `src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_agent_runs, pulse_evidence_packets | 2 / 1 | 153 | `e16ac876a7b1` |
| `src/parallax/domains/pulse_lab/repositories/pulse_evidence_source_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | asset_identity_current, cex_detail_snapshots, cex_token_profiles, enriched_events, events, market_ticks, narrative_admissions, token_discussion_digests, token_mention_semantics, token_profile_current | 2 / 2 | 553 | `35fce2ccd5ad` |
| `src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_agent_jobs, pulse_agent_runs | 2 / 2 | 753 | `29a2a81f8a7d` |
| `src/parallax/domains/pulse_lab/repositories/pulse_playbooks_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | - | 2 / 1 | 120 | `867e6b530254` |
| `src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_agent_jobs, pulse_candidates | 2 / 3 | 428 | `663bc67c3b50` |
| `src/parallax/domains/pulse_lab/repositories/pulse_runs_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_agent_run_steps, pulse_agent_runs | 2 / 1 | 356 | `889a5e491787` |
| `src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py` | pulse_lab repository | PostgreSQL 事实、控制状态或读模型持久化边界 | pulse_lab | pulse_trigger_dirty_targets | 2 / 3 | 699 | `2ed6a9acee41` |
| `src/parallax/domains/pulse_lab/runtime/__init__.py` | pulse_lab worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py` | pulse_lab worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | pulse_lab, token_intel | - | 1 / 12 | 1289 | `ccdb73af3336` |
| `src/parallax/domains/pulse_lab/services/__init__.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/pulse_lab/services/agent_eval.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 3 | 291 | `1d204da64ff3` |
| `src/parallax/domains/pulse_lab/services/agent_output_normalization.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 2 | 215 | `e856842cf761` |
| `src/parallax/domains/pulse_lab/services/agent_routing.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 1 | 128 | `cfd56faede23` |
| `src/parallax/domains/pulse_lab/services/agent_runtime.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 3 / 1 | 128 | `94bc528eb828` |
| `src/parallax/domains/pulse_lab/services/claim_evidence_verifier.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 2 / 2 | 104 | `84b9b85b08e6` |
| `src/parallax/domains/pulse_lab/services/decision_mapping.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 1 | 35 | `0f25ec40c9b7` |
| `src/parallax/domains/pulse_lab/services/evidence_completeness_gate.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 5 / 1 | 186 | `5c8cdbbe6f9a` |
| `src/parallax/domains/pulse_lab/services/evidence_packet_builder.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 2 | 664 | `880de6a6f35c` |
| `src/parallax/domains/pulse_lab/services/prompt_loader.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 3 | 95 | `b6c8550354ca` |
| `src/parallax/domains/pulse_lab/services/pulse_admission_policy.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | - | - | 1 / 0 | 153 | `ae270452e666` |
| `src/parallax/domains/pulse_lab/services/pulse_agent_cost_guard.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 4 | 190 | `90d85a00c7d0` |
| `src/parallax/domains/pulse_lab/services/pulse_candidate_gate.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab, token_intel | - | 6 / 2 | 211 | `a984a9a3d3a8` |
| `src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 20 | 1263 | `6c6357bf3d0d` |
| `src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 6 | 380 | `f35322ac9ff0` |
| `src/parallax/domains/pulse_lab/services/pulse_edge_events.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 1 | 187 | `8ec7746ff3d2` |
| `src/parallax/domains/pulse_lab/services/pulse_freshness_health.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 2 | 69 | `51dcf490cc39` |
| `src/parallax/domains/pulse_lab/services/pulse_horizon_policy.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | - | - | 3 / 0 | 36 | `b41b4c323dea` |
| `src/parallax/domains/pulse_lab/services/pulse_source_quality.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 3 / 1 | 94 | `8f9ef2d0e7e8` |
| `src/parallax/domains/pulse_lab/services/pulse_timeline_context.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 1 / 1 | 627 | `0662ee9144ff` |
| `src/parallax/domains/pulse_lab/services/recommendation_clipper.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 3 | 176 | `f5f0b3ef2168` |
| `src/parallax/domains/pulse_lab/services/write_gate.py` | pulse_lab service | 领域用例/事务编排；不绕过 repository owner | pulse_lab | - | 1 / 6 | 154 | `df44c9bc146c` |
| `src/parallax/domains/pulse_lab/types/__init__.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | pulse_lab | - | 0 / 3 | 65 | `03f04dffdea1` |
| `src/parallax/domains/pulse_lab/types/agent_decision.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | - | - | 15 / 0 | 258 | `fb2a794a72d0` |
| `src/parallax/domains/pulse_lab/types/evidence_packet.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | pulse_lab | - | 8 / 1 | 171 | `c8e50d0aa3e2` |
| `src/parallax/domains/pulse_lab/types/pulse_candidate_context.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | pulse_lab | - | 5 / 1 | 52 | `34f4f44f8e7a` |
| `src/parallax/domains/pulse_lab/types/pulse_freshness_health.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 96 | `f6b150feacf0` |
| `src/parallax/domains/pulse_lab/types/pulse_state.py` | pulse_lab 模块 | 领域逻辑、模型或辅助边界 | - | - | 5 / 0 | 89 | `ffb7d7e0229d` |
| `src/parallax/domains/token_intel/__init__.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/token_intel/_constants.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 14 / 0 | 25 | `088cfdecbc81` |
| `src/parallax/domains/token_intel/interfaces.py` | token_intel 契约 | 稳定领域类型、公开常量或协议 | token_intel | - | 26 / 15 | 102 | `d08975517b6c` |
| `src/parallax/domains/token_intel/queries/__init__.py` | token_intel query | 无副作用查询/投影输入读取 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/token_intel/queries/event_rebuild_query.py` | token_intel query | 无副作用查询/投影输入读取 | - | events | 1 / 0 | 32 | `bec4e79ff7d8` |
| `src/parallax/domains/token_intel/queries/event_token_projection_query.py` | token_intel query | 无副作用查询/投影输入读取 | asset_market | asset_identity_current, cex_tokens, enriched_events, events, market_ticks, price_feeds, registry_assets, token_intent_resolutions | 1 / 1 | 210 | `83cf83f08173` |
| `src/parallax/domains/token_intel/queries/search_events_query.py` | token_intel query | 无副作用查询/投影输入读取 | evidence, token_intel | asset_identity_current, cex_tokens, events, registry_assets, target_candidates, token_intent_resolutions | 2 / 2 | 611 | `d564cb038751` |
| `src/parallax/domains/token_intel/queries/stocks_radar_query.py` | token_intel query | 无副作用查询/投影输入读取 | token_intel | events, token_intent_resolutions, token_intents, us_equity_symbols | 1 / 1 | 110 | `f01e45695282` |
| `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py` | token_intel query | 无副作用查询/投影输入读取 | token_intel | account_profiles, asset_identity_current, cex_tokens, enriched_events, events, market_tick_current, market_ticks, price_feeds, registry_assets, token_intent_resolutions, token_intents, token_radar_rank_source_events | 2 / 1 | 940 | `f6ebacf8c2b8` |
| `src/parallax/domains/token_intel/read_models/__init__.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/token_intel/read_models/asset_flow_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | token_intel | - | 2 / 1 | 332 | `6795d3e903c6` |
| `src/parallax/domains/token_intel/read_models/search_agent_brief.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 0 / 0 | 75 | `935ebac95219` |
| `src/parallax/domains/token_intel/read_models/search_inspect_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 177 | `88eee7ae1a40` |
| `src/parallax/domains/token_intel/read_models/search_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | token_intel | - | 2 / 2 | 353 | `efb9367d9ad5` |
| `src/parallax/domains/token_intel/read_models/stocks_radar_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | token_intel | - | 1 / 1 | 126 | `a348a70d5726` |
| `src/parallax/domains/token_intel/read_models/token_case_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 197 | `e6e4df017012` |
| `src/parallax/domains/token_intel/read_models/token_target_cursor.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 21 | `3ca2fc8ad13e` |
| `src/parallax/domains/token_intel/read_models/token_target_post_serializer.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | asset_market, token_intel | - | 0 / 2 | 71 | `61f169676b58` |
| `src/parallax/domains/token_intel/read_models/token_target_posts_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | - | - | 1 / 0 | 118 | `dd30dea66fa1` |
| `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | asset_market | - | 1 / 1 | 262 | `d3f357064d7b` |
| `src/parallax/domains/token_intel/read_models/token_target_stage_builder.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | asset_market | - | 1 / 1 | 239 | `2407349048ca` |
| `src/parallax/domains/token_intel/repositories/__init__.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/token_intel/repositories/intent_resolution_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | events, token_intent_resolutions | 2 / 1 | 247 | `9dbe41e3fb66` |
| `src/parallax/domains/token_intel/repositories/projection_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | projection_dirty_ranges, projection_offsets, projection_runs | 3 / 1 | 450 | `2efd1ab2166e` |
| `src/parallax/domains/token_intel/repositories/signal_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | account_token_alerts | 1 / 0 | 199 | `4c8bf13e229d` |
| `src/parallax/domains/token_intel/repositories/token_evidence_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | token_evidence, token_intent_evidence | 2 / 1 | 206 | `490ddd8c85e1` |
| `src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | - | events, token_intent_lookup_keys, token_intent_resolutions, token_intents | 2 / 0 | 181 | `a65b9ad86b22` |
| `src/parallax/domains/token_intel/repositories/token_intent_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | events, token_intent_evidence, token_intent_resolutions, token_intents | 2 / 1 | 231 | `2f8cc0fb9677` |
| `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | events, market_tick_current, price_feeds, registry_assets, token_intent_resolutions, token_intents, token_radar_dirty_targets, token_radar_target_features | 1 / 3 | 1142 | `33c790084a83` |
| `src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | - | 1 / 1 | 100 | `11b33d09bd67` |
| `src/parallax/domains/token_intel/repositories/token_radar_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | token_radar_current_rows, token_radar_publication_state, token_radar_target_features, token_radar_target_first_seen | 2 / 3 | 1538 | `ad041a721111` |
| `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | events, recent, token_intent_resolutions, token_intents, token_radar_source_dirty_events | 2 / 3 | 623 | `01ac5a5bafd9` |
| `src/parallax/domains/token_intel/repositories/token_target_repository.py` | token_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | token_intel | asset_identity_current, cex_tokens, enriched_events, events, market_tick_current, market_ticks, price_feeds, registry_assets, token_intent_resolutions | 1 / 1 | 481 | `774c764c2638` |
| `src/parallax/domains/token_intel/runtime/__init__.py` | token_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py` | token_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | asset_market, evidence, token_intel | - | 1 / 8 | 157 | `7753181f0f06` |
| `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py` | token_intel worker | 消费事实/控制队列并写该域唯一事实或读模型 owner | token_intel | - | 2 / 4 | 567 | `ebc80ced6c2b` |
| `src/parallax/domains/token_intel/scoring/__init__.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 0 / 2 | 15 | `e545fae8e07f` |
| `src/parallax/domains/token_intel/scoring/baseline_scoring.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 108 | `f20c57f95af0` |
| `src/parallax/domains/token_intel/scoring/cross_section_normalizer.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 69 | `176ef2f060ea` |
| `src/parallax/domains/token_intel/scoring/diffusion_health.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 1 / 1 | 154 | `b01712098842` |
| `src/parallax/domains/token_intel/scoring/factor_cohort.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 1 / 0 | 42 | `af267fa97a81` |
| `src/parallax/domains/token_intel/scoring/factor_diagnostics.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 1 / 1 | 98 | `cfc676d13200` |
| `src/parallax/domains/token_intel/scoring/factor_snapshot.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 2 / 2 | 878 | `bd44e9a4d39b` |
| `src/parallax/domains/token_intel/scoring/factor_snapshot_contract.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 3 / 1 | 206 | `0a3deff72a37` |
| `src/parallax/domains/token_intel/scoring/post_text_quality.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 93 | `dd90d18772ba` |
| `src/parallax/domains/token_intel/scoring/scoring_common.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 84 | `ad0dfbef99a1` |
| `src/parallax/domains/token_intel/scoring/social_signal_features.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 0 | 152 | `74f61755f003` |
| `src/parallax/domains/token_intel/scoring/token_radar_feature_builder.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 1 / 5 | 382 | `492ace6799a7` |
| `src/parallax/domains/token_intel/services/__init__.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/domains/token_intel/services/atomic_mention.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | - | - | 2 / 0 | 70 | `c27114e60196` |
| `src/parallax/domains/token_intel/services/deterministic_token_resolver.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 2 / 2 | 480 | `da88a15f4f98` |
| `src/parallax/domains/token_intel/services/query_parser.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | evidence | - | 2 / 1 | 100 | `3e2038302d2a` |
| `src/parallax/domains/token_intel/services/search_aliases.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 1 / 1 | 100 | `ef6b901f2a4b` |
| `src/parallax/domains/token_intel/services/token_evidence_builder.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | evidence, token_intel | - | 2 / 2 | 176 | `7d03894d025e` |
| `src/parallax/domains/token_intel/services/token_intent_builder.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 2 / 1 | 204 | `f84244fa9044` |
| `src/parallax/domains/token_intel/services/token_intent_resolver.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 3 / 2 | 135 | `d5d5639782da` |
| `src/parallax/domains/token_intel/services/token_radar_projection.py` | token_intel 投影 | 从事实重建派生状态；稳定键且无变化零写入 | narrative_intel, token_intel | - | 2 / 12 | 3266 | `d8ca482ec156` |
| `src/parallax/domains/token_intel/services/token_resolution_refresh.py` | token_intel service | 领域用例/事务编排；不绕过 repository owner | token_intel | - | 3 / 2 | 130 | `964801c2222f` |
| `src/parallax/domains/token_intel/types/__init__.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | token_intel | - | 0 / 1 | 17 | `009161f465d6` |
| `src/parallax/domains/token_intel/types/token_fact_inputs.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 8 / 0 | 85 | `9770f26badd8` |
| `src/parallax/domains/token_intel/types/token_radar_payload_hash.py` | token_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 2 / 1 | 83 | `a38fa341bbe5` |
| `src/parallax/domains/watchlist_intel/__init__.py` | watchlist_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 1 | `acff8ba83b06` |
| `src/parallax/domains/watchlist_intel/repositories/__init__.py` | watchlist_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | watchlist_intel | - | 0 / 1 | 3 | `1ec5d166b30b` |
| `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py` | watchlist_intel repository | PostgreSQL 事实、控制状态或读模型持久化边界 | evidence, token_intel, watchlist_intel | events | 2 / 2 | 412 | `8eb007603b7a` |
| `src/parallax/domains/watchlist_intel/services/__init__.py` | watchlist_intel service | 领域用例/事务编排；不绕过 repository owner | watchlist_intel | - | 0 / 1 | 6 | `b949dba063d3` |
| `src/parallax/domains/watchlist_intel/services/watchlist_read_service.py` | watchlist_intel service | 领域用例/事务编排；不绕过 repository owner | watchlist_intel | - | 2 / 0 | 117 | `2f965fea3295` |
| `src/parallax/domains/watchlist_intel/types/__init__.py` | watchlist_intel 模块 | 领域逻辑、模型或辅助边界 | - | - | 0 / 0 | 65 | `61c81bc234bb` |
| `src/parallax/integrations/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/integrations/binance/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 1 | `fecbae4d84f8` |
| `src/parallax/integrations/binance/cex_profile_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 91 | `9a4370bcfb4e` |
| `src/parallax/integrations/binance/usdm_futures_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 2 / 0 | 349 | `831974cae2e5` |
| `src/parallax/integrations/binance/web3_token_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 172 | `e84df5d7c4bb` |
| `src/parallax/integrations/gmgn/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/integrations/gmgn/direct_ws.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 216 | `d589262f1c17` |
| `src/parallax/integrations/gmgn/directory_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 167 | `d33e69377834` |
| `src/parallax/integrations/gmgn/openapi_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 2 / 0 | 453 | `6e43b64df7de` |
| `src/parallax/integrations/gmgn/openapi_gateway.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 1 | 235 | `fc2e0f505e34` |
| `src/parallax/integrations/macrodata/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 17 | `12e71f46ad94` |
| `src/parallax/integrations/macrodata/runner.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 326 | `4fb8909cd3d7` |
| `src/parallax/integrations/model_execution/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/integrations/model_execution/execution_gateway.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 6 | 845 | `b6aa9452a200` |
| `src/parallax/integrations/model_execution/news_item_brief_agent_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | news_intel | - | 1 / 7 | 125 | `6b6d4e95768a` |
| `src/parallax/integrations/model_execution/output_schema.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 3 / 0 | 107 | `ac2d8d269fc8` |
| `src/parallax/integrations/model_execution/pulse_decision_agent_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | pulse_lab | - | 1 / 5 | 756 | `74b0f8fda2b7` |
| `src/parallax/integrations/model_execution/structured_json_strategy.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 4 | 169 | `28bbe654c95d` |
| `src/parallax/integrations/model_execution/usage.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 2 / 0 | 49 | `9af4fc829a12` |
| `src/parallax/integrations/news_feeds/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 1 | `03cc432edb8f` |
| `src/parallax/integrations/news_feeds/cryptopanic_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 2 / 1 | 220 | `1ec8a268e4cd` |
| `src/parallax/integrations/news_feeds/feed_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 4 / 0 | 107 | `6e429819924d` |
| `src/parallax/integrations/news_feeds/opennews_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | news_intel | - | 2 / 2 | 555 | `568169d4af82` |
| `src/parallax/integrations/news_feeds/provider_registry.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 3 | 228 | `e3645ce119f5` |
| `src/parallax/integrations/okx/__init__.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/integrations/okx/chains.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 22 | `a31934dcc4d4` |
| `src/parallax/integrations/okx/dex_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 2 / 2 | 264 | `f91a9f09b48b` |
| `src/parallax/integrations/okx/dex_ws_client.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 1 | 606 | `adedf1f235b3` |
| `src/parallax/integrations/okx/http_utils.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 2 / 0 | 56 | `8f0a161f8cdd` |
| `src/parallax/integrations/okx/models.py` | 外部适配器 | provider 输入/输出边界；不得拥有业务事实语义 | - | - | 1 / 0 | 42 | `86066cf1da0c` |
| `src/parallax/platform/__init__.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/platform/agent_capabilities.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 2 / 0 | 95 | `f13bf06c5556` |
| `src/parallax/platform/agent_execution.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 14 / 2 | 367 | `a060b9283f44` |
| `src/parallax/platform/agent_hashing.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 13 / 0 | 65 | `729138d516a4` |
| `src/parallax/platform/agent_knowledge.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 3 / 0 | 95 | `2c65e4b97a78` |
| `src/parallax/platform/cancellation.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 3 / 0 | 17 | `95a3e45d7c41` |
| `src/parallax/platform/config/__init__.py` | 配置平台 | 正式运行配置 schema 与加载边界 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/platform/config/news_provider_types.py` | 配置平台 | 正式运行配置 schema 与加载边界 | - | - | 3 / 0 | 5 | `eeb8f0bdacb9` |
| `src/parallax/platform/config/settings.py` | 配置平台 | 正式运行配置 schema 与加载边界 | - | - | 24 / 2 | 2236 | `e9c99d2824cb` |
| `src/parallax/platform/current_read_model_payload_hash.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 17 / 0 | 102 | `07eb9220500c` |
| `src/parallax/platform/db/__init__.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/platform/db/alembic/env.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | - | 0 / 2 | 62 | `c659bbc9321b` |
| `src/parallax/platform/db/alembic/versions/20260506_0001_initial_postgresql.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 740 | `af5075f7cf85` |
| `src/parallax/platform/db/alembic/versions/20260506_0002_postgres_queue_claims.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 46 | `367398b57e71` |
| `src/parallax/platform/db/alembic/versions/20260506_0003_enrichment_stale_running_claims.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 32 | `b7aca1a04626` |
| `src/parallax/platform/db/alembic/versions/20260506_0004_projection_operations.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 209 | `4537abe7350f` |
| `src/parallax/platform/db/alembic/versions/20260506_0005_asset_identity_resolution.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 401 | `ab47e1c9d516` |
| `src/parallax/platform/db/alembic/versions/20260507_0006_asset_market_sync_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 31 | `a1df76309a25` |
| `src/parallax/platform/db/alembic/versions/20260507_0007_token_radar_v3_intents.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 301 | `c3230e6c2324` |
| `src/parallax/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 268 | `f975672e973a` |
| `src/parallax/platform/db/alembic/versions/20260507_0009_token_discovery_results.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 70 | `0d17c39a6d55` |
| `src/parallax/platform/db/alembic/versions/20260507_0010_agents_sdk_model_run_audit.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 55 | `be051d352a75` |
| `src/parallax/platform/db/alembic/versions/20260508_0011_event_price_observations.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 78 | `2b843c3f5e1c` |
| `src/parallax/platform/db/alembic/versions/20260508_0012_prune_legacy_token_radar_projection.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 46 | `73a409a8b732` |
| `src/parallax/platform/db/alembic/versions/20260508_0013_retire_legacy_token_resolutions.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 27 | `926505873cf4` |
| `src/parallax/platform/db/alembic/versions/20260508_0014_prune_token_radar_v6_projection.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 46 | `330306ed9092` |
| `src/parallax/platform/db/alembic/versions/20260508_0015_signal_pulse_agent_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 224 | `b4e962b34ce5` |
| `src/parallax/platform/db/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 41 | `582a915c958d` |
| `src/parallax/platform/db/alembic/versions/20260509_0017_demote_search_only_registry_assets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 91 | `5ca4ed90109a` |
| `src/parallax/platform/db/alembic/versions/20260509_0018_demote_search_tail_candidate_audit_refs.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 85 | `141e544ba334` |
| `src/parallax/platform/db/alembic/versions/20260509_0019_demote_symbol_search_tail_targets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 89 | `45319768533f` |
| `src/parallax/platform/db/alembic/versions/20260509_0020_sweep_symbol_search_tail_assets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 89 | `db1c960adc71` |
| `src/parallax/platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 207 | `bae53f434da4` |
| `src/parallax/platform/db/alembic/versions/20260510_0022_token_radar_factor_snapshot_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 66 | `2c2c86d40a42` |
| `src/parallax/platform/db/alembic/versions/20260510_0023_drop_signal_pulse_legacy_json_fields.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 26 | `4e19d652fc75` |
| `src/parallax/platform/db/alembic/versions/20260511_0024_price_observation_field_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 109 | `92350c4d9184` |
| `src/parallax/platform/db/alembic/versions/20260511_0025_token_radar_production_read_models.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 112 | `7e4c42490864` |
| `src/parallax/platform/db/alembic/versions/20260511_0026_token_factor_eval_diagnostics.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 91 | `862e7cd05e55` |
| `src/parallax/platform/db/alembic/versions/20260511_0027_prune_legacy_pulse_factor_snapshots.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 31 | `9149d3e1b0f8` |
| `src/parallax/platform/db/alembic/versions/20260511_0028_prune_gmgn_payload_market_data.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 89 | `5c1d943c550e` |
| `src/parallax/platform/db/alembic/versions/20260511_0029_anchor_live_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 70 | `74995637ed23` |
| `src/parallax/platform/db/alembic/versions/20260511_0030_prune_pulse_snapshots_without_market.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 32 | `1e622d94fd3d` |
| `src/parallax/platform/db/alembic/versions/20260512_0031_prune_legacy_pulse_factor_contracts.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 31 | `dad468491d47` |
| `src/parallax/platform/db/alembic/versions/20260512_0032_search_v2_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 51 | `26f820b98a81` |
| `src/parallax/platform/db/alembic/versions/20260512_0033_reconcile_search_v2_local_revision.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 16 | `8413fc40fdb4` |
| `src/parallax/platform/db/alembic/versions/20260512_0034_us_equity_symbol_universe.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 49 | `5d9c958f3ca8` |
| `src/parallax/platform/db/alembic/versions/20260513_0035_asset_profiles.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 58 | `215e5dfc4fb3` |
| `src/parallax/platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 344 | `19bb02057f2c` |
| `src/parallax/platform/db/alembic/versions/20260514_0037_unified_agent_runtime_phase0b.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 142 | `97e2c409456b` |
| `src/parallax/platform/db/alembic/versions/20260514_0038_pulse_agent_runtime_eval_ledger.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 107 | `436d51501d35` |
| `src/parallax/platform/db/alembic/versions/20260514_0039_reconcile_local_agent_harness_revision.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 16 | `804724f42d8c` |
| `src/parallax/platform/db/alembic/versions/20260514_0040_repair_pulse_agent_job_cooldown.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 39 | `15434ad138a1` |
| `src/parallax/platform/db/alembic/versions/20260514_0041_pulse_worker_edge_notifications_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 184 | `8fd65f7d8a77` |
| `src/parallax/platform/db/alembic/versions/20260514_0042_harden_pulse_agent_run_outcome.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 18 | `0d69b6fec592` |
| `src/parallax/platform/db/alembic/versions/20260514_0043_token_radar_listed_lookup_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 32 | `46f143ed80f2` |
| `src/parallax/platform/db/alembic/versions/20260514_0044_pulse_runtime_hash_history.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 45 | `a12b346afe00` |
| `src/parallax/platform/db/alembic/versions/20260514_0045_watchlist_handle_intel.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 96 | `f37ae2480da0` |
| `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 177 | `bc21eed1b920` |
| `src/parallax/platform/db/alembic/versions/20260516_0047_market_ticks_gmgn_dex_quote_provider.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 30 | `363e6de3452d` |
| `src/parallax/platform/db/alembic/versions/20260516_0048_agent_safety_net_audit.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 52 | `392308176e6d` |
| `src/parallax/platform/db/alembic/versions/20260516_0049_enriched_event_async_backfill.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 89 | `9e4ef8c3d4e4` |
| `src/parallax/platform/db/alembic/versions/20260516_0050_drop_legacy_asset_stack.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 78 | `3ddcace69b0c` |
| `src/parallax/platform/db/alembic/versions/20260516_0051_pulse_agent_desk_redesign.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 60 | `53195333f9e3` |
| `src/parallax/platform/db/alembic/versions/20260517_0052_token_profile_current.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 68 | `47b648464177` |
| `src/parallax/platform/db/alembic/versions/20260517_0053_reconcile_legacy_asset_stack_drop.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 54 | `133ff69d28bc` |
| `src/parallax/platform/db/alembic/versions/20260517_0054_token_radar_materialized_listed_at.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 59 | `966f87b1fd5d` |
| `src/parallax/platform/db/alembic/versions/20260517_0055_public_read_path_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 73 | `c6e5aa3bb72f` |
| `src/parallax/platform/db/alembic/versions/20260517_0056_recent_payload_batch_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 61 | `4244e5df1bd0` |
| `src/parallax/platform/db/alembic/versions/20260517_0057_cex_token_static_icons.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 30 | `117634b0d84e` |
| `src/parallax/platform/db/alembic/versions/20260517_0058_binance_profile_sources.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 109 | `95c2a881fe18` |
| `src/parallax/platform/db/alembic/versions/20260517_0059_pulse_control_plane_kiss.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 50 | `176893f18f38` |
| `src/parallax/platform/db/alembic/versions/20260518_0060_event_anchor_backfill_jobs.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 202 | `3220b229c1bc` |
| `src/parallax/platform/db/alembic/versions/20260518_0061_drop_closed_loop_harness.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 88 | `556fa0e88c70` |
| `src/parallax/platform/db/alembic/versions/20260518_0062_pulse_evidence_first_recovery.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 240 | `65f4b03f570b` |
| `src/parallax/platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 248 | `80e8e3cbb5bb` |
| `src/parallax/platform/db/alembic/versions/20260519_0064_narrative_admission_source_sets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 44 | `3d970df34f0c` |
| `src/parallax/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 369 | `2809f243c789` |
| `src/parallax/platform/db/alembic/versions/20260519_0066_pulse_backpressure_run_outcomes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 52 | `fb1a8d22471f` |
| `src/parallax/platform/db/alembic/versions/20260520_0067_pulse_research_committee_checks.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 101 | `5a55bb0355bb` |
| `src/parallax/platform/db/alembic/versions/20260520_0068_news_item_agent_brief.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 142 | `3ec5da95d8ad` |
| `src/parallax/platform/db/alembic/versions/20260520_0069_token_radar_retention_watchlist_stats.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 121 | `00ee7c838ad9` |
| `src/parallax/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 38 | `e72222cf2d53` |
| `src/parallax/platform/db/alembic/versions/20260521_0071_market_tick_open_interest.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 18 | `61bc013c6564` |
| `src/parallax/platform/db/alembic/versions/20260521_0072_cex_binance_source_provider_additive.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 44 | `b6be834aa51d` |
| `src/parallax/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 107 | `106f3772d0a1` |
| `src/parallax/platform/db/alembic/versions/20260521_0074_cex_detail_snapshots.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 72 | `ed79e5b72abd` |
| `src/parallax/platform/db/alembic/versions/20260521_0075_news_source_cryptopanic_provider.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 33 | `de6bc65aac1d` |
| `src/parallax/platform/db/alembic/versions/20260521_0076_macro_views.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 74 | `1a2dc1d63cec` |
| `src/parallax/platform/db/alembic/versions/20260521_0077_macro_regime_70.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 60 | `2fe41059bd42` |
| `src/parallax/platform/db/alembic/versions/20260521_0078_token_image_assets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 96 | `0926c4932ea3` |
| `src/parallax/platform/db/alembic/versions/20260521_0079_token_profile_local_logo_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 54 | `b1b12e1dcfaf` |
| `src/parallax/platform/db/alembic/versions/20260521_0080_macro_concept_key_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 120 | `ab8a62f3fc84` |
| `src/parallax/platform/db/alembic/versions/20260522_0081_news_source_chain_classification.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 157 | `bfcb5f031e04` |
| `src/parallax/platform/db/alembic/versions/20260522_0082_news_source_quality_rows.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 48 | `389bc4c2085e` |
| `src/parallax/platform/db/alembic/versions/20260523_0083_equity_event_intel.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 611 | `f681b0e28cf5` |
| `src/parallax/platform/db/alembic/versions/20260523_0084_equity_event_fact_candidate_shape.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 70 | `94fb60531ad2` |
| `src/parallax/platform/db/alembic/versions/20260523_0085_token_radar_storage_root_fix.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 191 | `f6a8b84db102` |
| `src/parallax/platform/db/alembic/versions/20260523_0086_equity_event_runtime_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 40 | `7105005ee002` |
| `src/parallax/platform/db/alembic/versions/20260523_0087_news_content_classification.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 54 | `406a9474444d` |
| `src/parallax/platform/db/alembic/versions/20260523_0088_news_page_filter_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 65 | `0e8ac21d7655` |
| `src/parallax/platform/db/alembic/versions/20260523_0089_token_image_unsupported_cleanup.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 39 | `889996150c8a` |
| `src/parallax/platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 503 | `d2af42b29cf9` |
| `src/parallax/platform/db/alembic/versions/20260524_0091_token_radar_target_feature_freshness_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 30 | `b2c24edc72ac` |
| `src/parallax/platform/db/alembic/versions/20260524_0092_equity_projection_payload_hashes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 130 | `117e251daf31` |
| `src/parallax/platform/db/alembic/versions/20260524_0093_token_radar_target_projection_coverage.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 50 | `74c41c11c667` |
| `src/parallax/platform/db/alembic/versions/20260524_0094_projection_dirty_targets_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 165 | `543569049ca2` |
| `src/parallax/platform/db/alembic/versions/20260524_0095_market_tick_current_dirty_targets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 66 | `61878f62a4c2` |
| `src/parallax/platform/db/alembic/versions/20260525_0096_token_discovery_dirty_lookup_keys.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 69 | `a5f271650ce6` |
| `src/parallax/platform/db/alembic/versions/20260525_0097_agent_brief_dirty_targets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 148 | `aff9dcbaf76b` |
| `src/parallax/platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 451 | `6abe0119ef35` |
| `src/parallax/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 344 | `02d0ba69f8eb` |
| `src/parallax/platform/db/alembic/versions/20260526_0100_worker_queue_terminal_events.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 221 | `e1e1cb7a95eb` |
| `src/parallax/platform/db/alembic/versions/20260526_0101_postgres_runtime_root_cause_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 154 | `c4d4cb31a8e5` |
| `src/parallax/platform/db/alembic/versions/20260526_0102_macro_observation_series_source_ts_text.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 36 | `2deab01ede57` |
| `src/parallax/platform/db/alembic/versions/20260526_0103_normalize_terminal_reason_buckets.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 73 | `44ce6e342d75` |
| `src/parallax/platform/db/alembic/versions/20260526_0104_equity_event_evidence_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 286 | `0a48a73b7a11` |
| `src/parallax/platform/db/alembic/versions/20260526_0105_opennews_provider_signal.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 134 | `4fa6d8f94c97` |
| `src/parallax/platform/db/alembic/versions/20260526_0106_runtime_rank_source_edges.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 173 | `b72438b8813d` |
| `src/parallax/platform/db/alembic/versions/20260526_0107_macro_generation_equity_evidence_jobs.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 193 | `bf6e47d9e0c5` |
| `src/parallax/platform/db/alembic/versions/20260526_0108_runtime_perf_lifecycle_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 122 | `ee6da620b3a0` |
| `src/parallax/platform/db/alembic/versions/20260526_0109_rank_source_identity_confidence_text.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 35 | `359de096de13` |
| `src/parallax/platform/db/alembic/versions/20260526_0110_equity_fetch_run_reaper.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 88 | `a13b5dab0781` |
| `src/parallax/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 82 | `0f9f209e726e` |
| `src/parallax/platform/db/alembic/versions/20260527_0112_macro_sync_worker.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 146 | `99fcbe780857` |
| `src/parallax/platform/db/alembic/versions/20260527_0113_token_radar_stable_publication.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 51 | `f15c6af9388b` |
| `src/parallax/platform/db/alembic/versions/20260527_0114_runtime_db_performance_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 150 | `3ba4c2694e54` |
| `src/parallax/platform/db/alembic/versions/20260527_0115_next_runtime_lifecycle_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 390 | `b9fc2149c88c` |
| `src/parallax/platform/db/alembic/versions/20260528_0116_macro_workerspace_root_fix.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 7 historical table refs | 0 / 0 | 463 | `872ea32f23cb` |
| `src/parallax/platform/db/alembic/versions/20260528_0117_news_intel_canonical_dedup_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 8 historical table refs | 0 / 0 | 671 | `9094fc4aab1c` |
| `src/parallax/platform/db/alembic/versions/20260528_0118_news_realtime_postgres_hotpath_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 103 | `94c6dbd03bd0` |
| `src/parallax/platform/db/alembic/versions/20260528_0119_news_source_status_hotpath_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 50 | `312c4dbd596c` |
| `src/parallax/platform/db/alembic/versions/20260528_0120_drop_news_token_presence_filter_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 23 | `8e64dfa5618e` |
| `src/parallax/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 162 | `4fe0feb5df6b` |
| `src/parallax/platform/db/alembic/versions/20260528_0122_token_radar_runtime_not_null_guardrails.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 38 | `9f91c1f5724e` |
| `src/parallax/platform/db/alembic/versions/20260529_0123_news_public_url_hard_identity.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 8 historical table refs | 0 / 0 | 284 | `f580c30891c2` |
| `src/parallax/platform/db/alembic/versions/20260529_0124_token_pulse_equity_cpu_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 84 | `27ada07b5379` |
| `src/parallax/platform/db/alembic/versions/20260529_0125_drop_equity_event_intel.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 47 | `678ee8791d35` |
| `src/parallax/platform/db/alembic/versions/20260529_0126_token_radar_venue_source_width_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 162 | `b7e4b566fe86` |
| `src/parallax/platform/db/alembic/versions/20260529_0127_token_radar_drop_prevenue_current_uniques.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 6 historical table refs | 0 / 0 | 74 | `c943a97557b4` |
| `src/parallax/platform/db/alembic/versions/20260529_0128_litellm_execution_audit_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 70 | `5619aaf9647b` |
| `src/parallax/platform/db/alembic/versions/20260530_0129_drop_legacy_5min_notifications.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 26 | `dd87d1db2009` |
| `src/parallax/platform/db/alembic/versions/20260530_0130_drop_social_watchlist_agent_tables.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 26 | `fd632ac69a21` |
| `src/parallax/platform/db/alembic/versions/20260531_0131_news_story_projection_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 28 | `61733265e878` |
| `src/parallax/platform/db/alembic/versions/20260531_0132_news_rebuild_brief_backlog_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 31 | `216066fbb27d` |
| `src/parallax/platform/db/alembic/versions/20260531_0133_news_public_url_identity_index_scope.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 40 | `322c99c6e56c` |
| `src/parallax/platform/db/alembic/versions/20260531_0134_token_image_magic_policy_retry.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 36 | `b8cef8549b03` |
| `src/parallax/platform/db/alembic/versions/20260531_0136_okx_symbol_candidate_profile_icons.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 82 | `bde28cc002a0` |
| `src/parallax/platform/db/alembic/versions/20260531_0137_news_dirty_projection_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 133 | `2fc12e518d8f` |
| `src/parallax/platform/db/alembic/versions/20260531_0138_news_page_projection_version_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 26 | `db5f63439ce8` |
| `src/parallax/platform/db/alembic/versions/20260601_0139_news_item_brief_lightweight_contract.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 112 | `4f0c0e6cc95b` |
| `src/parallax/platform/db/alembic/versions/20260601_0140_news_item_brief_requeue_nonready.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 112 | `150898f6f362` |
| `src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 22 | `817aa3607d72` |
| `src/parallax/platform/db/alembic/versions/20260603_0142_news_context_and_filter_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 5 historical table refs | 0 / 0 | 94 | `a3733ac99a84` |
| `src/parallax/platform/db/alembic/versions/20260603_0143_cex_detail_payload_hash_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 225 | `8da8c33c707a` |
| `src/parallax/platform/db/alembic/versions/20260603_0144_news_item_process_claim_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 200 | `bd2bd029e3d3` |
| `src/parallax/platform/db/alembic/versions/20260603_0145_narrative_zero_write_hashes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 230 | `3f6d9a3062b1` |
| `src/parallax/platform/db/alembic/versions/20260603_0146_macro_sync_state_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 66 | `3283d9959981` |
| `src/parallax/platform/db/alembic/versions/20260603_0147_news_research_index_support.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 48 | `7e6201655017` |
| `src/parallax/platform/db/alembic/versions/20260604_0148_news_material_duplicate_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 57 | `3a6fe64c1feb` |
| `src/parallax/platform/db/alembic/versions/20260605_0149_news_analysis_story_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 78 | `9584ca50243b` |
| `src/parallax/platform/db/alembic/versions/20260605_0150_news_agent_requirement_contract.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 73 | `f0c436afcc9e` |
| `src/parallax/platform/db/alembic/versions/20260606_0151_news_agent_market_admission_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 62 | `bb488c86843a` |
| `src/parallax/platform/db/alembic/versions/20260606_0152_news_page_search_document.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 115 | `a8b76eef0c98` |
| `src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 56 | `cef20c8a01fb` |
| `src/parallax/platform/db/alembic/versions/20260608_0153_macro_sync_freshness_claim_order.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 39 | `a5138c28a8be` |
| `src/parallax/platform/db/alembic/versions/20260608_0154_account_quality_snapshot_identity.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 55 | `e7fdada4e484` |
| `src/parallax/platform/db/alembic/versions/20260608_0155_pulse_candidate_serving_row_audit_identity_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 25 | `e9724225e480` |
| `src/parallax/platform/db/alembic/versions/20260608_0156_pulse_candidate_product_identity_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 9 historical table refs | 0 / 0 | 208 | `9da79c92bde3` |
| `src/parallax/platform/db/alembic/versions/20260608_0157_token_radar_current_rows_product_identity.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 32 | `d38fcde23e55` |
| `src/parallax/platform/db/alembic/versions/20260608_0158_pulse_single_decision_stage.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 55 | `fb240b0f7041` |
| `src/parallax/platform/db/alembic/versions/20260609_0159_macro_daily_briefs.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 47 | `9dbb2a55b57c` |
| `src/parallax/platform/db/alembic/versions/20260609_0160_postgres_observability_extensions.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 33 | `02a9578663e9` |
| `src/parallax/platform/db/alembic/versions/20260609_0161_news_agent_admission_candidate_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 40 | `797e4dfe70c0` |
| `src/parallax/platform/db/alembic/versions/20260609_0162_news_page_member_lookup_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 27 | `0a3dd42d3657` |
| `src/parallax/platform/db/alembic/versions/20260609_0163_news_page_alert_ready_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 37 | `e2ae7351fd49` |
| `src/parallax/platform/db/alembic/versions/20260609_0164_news_page_display_score_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 27 | `567659b2402b` |
| `src/parallax/platform/db/alembic/versions/20260609_0165_news_page_remove_display_score_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 21 | `e86aad651319` |
| `src/parallax/platform/db/alembic/versions/20260609_0166_news_agent_run_artifact_hash_canonical.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 32 | `542374d6cfc3` |
| `src/parallax/platform/db/alembic/versions/20260609_0167_news_story_identity_v2.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 203 | `b0078d1a1ef8` |
| `src/parallax/platform/db/alembic/versions/20260609_0168_news_story_identity_v2_remaining_opennews.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 156 | `03a005ffbe69` |
| `src/parallax/platform/db/alembic/versions/20260609_0169_news_page_rows_retired_projection_purge.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 27 | `2b03bc8dd89c` |
| `src/parallax/platform/db/alembic/versions/20260609_0170_news_agent_admission_retired_policy_reprocess.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 91 | `e3affa01b4d7` |
| `src/parallax/platform/db/alembic/versions/20260609_0171_news_page_rows_require_story_identity.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 49 | `e02cb1de143b` |
| `src/parallax/platform/db/alembic/versions/20260609_0172_news_page_rows_require_agent_eligible.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 47 | `36923c76bcf1` |
| `src/parallax/platform/db/alembic/versions/20260609_0173_news_page_rows_serving_invariants.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 58 | `81f3ae588513` |
| `src/parallax/platform/db/alembic/versions/20260609_0174_news_page_provider_rating.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 2 historical table refs | 0 / 0 | 50 | `814b96e07392` |
| `src/parallax/platform/db/alembic/versions/20260609_0175_news_agent_provider_rating_gate.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 159 | `64b00b0e4028` |
| `src/parallax/platform/db/alembic/versions/20260609_0176_news_provider_rating_gate_finalize.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 3 historical table refs | 0 / 0 | 170 | `22ba44084cd0` |
| `src/parallax/platform/db/alembic/versions/20260612_0177_news_brief_duplicate_cost_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 4 historical table refs | 0 / 0 | 200 | `5659393b3cef` |
| `src/parallax/platform/db/alembic/versions/20260612_0178_notification_delivery_stale_claim_index.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 34 | `f21dd4579f4b` |
| `src/parallax/platform/db/alembic/versions/20260612_0179_pulse_public_search_trgm_indexes.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 64 | `2de317f45d61` |
| `src/parallax/platform/db/alembic/versions/20260616_0180_macro_event_text_series_nullable.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 21 | `4c1ff8d14378` |
| `src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | - | 0 / 0 | 146 | `eaa8ce79548d` |
| `src/parallax/platform/db/alembic/versions/20260623_0182_news_page_macro_event_flow.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 1 historical table refs | 0 / 0 | 122 | `8992f4f41c96` |
| `src/parallax/platform/db/alembic/versions/20260713_0183_backend_kappa_cqrs_hard_cut.py` | 迁移历史 | PostgreSQL schema 演进；不属于运行时兼容分支 | - | 10 historical table refs | 0 / 0 | 376 | `664e7b56f434` |
| `src/parallax/platform/db/json_safety.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | - | 11 / 0 | 19 | `e36ff17256df` |
| `src/parallax/platform/db/postgres_audit.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | alembic_version, event_entities, events, information_schema, registry_assets, token_evidence, token_intent_resolutions, token_intents, token_radar_current_rows | 2 / 1 | 352 | `825fa2a3bb28` |
| `src/parallax/platform/db/postgres_client.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | alembic_version | 9 / 0 | 215 | `99ef4e3fed9f` |
| `src/parallax/platform/db/postgres_migrations.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | - | 5 / 0 | 23 | `58fdb3c26759` |
| `src/parallax/platform/db/queue_terminal.py` | 数据库平台 | 连接、事务、schema 或跨域队列基础设施 | - | worker_queue_terminal_events | 14 / 1 | 548 | `7e1890894775` |
| `src/parallax/platform/logging/__init__.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/platform/logging/setup.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 1 / 0 | 32 | `0da6fd5a8b8d` |
| `src/parallax/platform/paths/__init__.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 0 / 0 | 0 | `e3b0c44298fc` |
| `src/parallax/platform/paths/runtime_paths.py` | 平台能力 | 跨域基础设施；不得承载领域决策 | - | - | 3 / 0 | 25 | `f264d16f2b0f` |
