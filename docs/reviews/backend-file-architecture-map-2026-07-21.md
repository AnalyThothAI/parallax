# Parallax 后端逐文件架构全景图

> 快照：`main@8f00c551`，生成日期 `2026-07-21`。范围是 Git 跟踪的 `src/parallax`：580 个 Python 文件、11 个架构/知识说明。当前运行时代码与不可变迁移历史分开列示。

## 阅读方法

- `角色` 表示文件承担的主要职责；`入口符号` 只列前三个顶层类/函数。
- `直接依赖` 是静态 AST 解析得到的仓内模块，最多列三个；`入度` 是被其他仓内模块直接引用的文件数。
- 依赖为空不代表无运行时作用：配置、反射装载、SQL 表和 provider 回调可能形成动态边。
- Alembic 历史必须保持可重放，但它不应进入当前运行时设计的日常认知负担。

## 目录规模

| 根目录 | Python 文件 | LOC |
|---|---:|---:|
| `app` | 71 | 14,549 |
| `domains` | 272 | 81,639 |
| `integrations` | 29 | 5,418 |
| `platform` | 205 | 24,808 |
| `root` | 3 | 10 |

## 当前运行时代码（逐文件，共 396 个）

| 区域 | 文件 | LOC | 角色 | 入口符号 | 直接依赖（最多 3） | 入度 |
|---|---|---:|---|---|---|---:|
| `root` | `src/parallax/__init__.py` | 1 | package/export | — | — | 0 |
| `root` | `src/parallax/__main__.py` | 4 | module | — | `parallax.cli` | 0 |
| `app/__init__.py` | `src/parallax/app/__init__.py` | 0 | package/export | — | — | 0 |
| `app/runtime` | `src/parallax/app/runtime/__init__.py` | 3 | package/export | — | `parallax.app.runtime.worker_base` | 0 |
| `app/runtime` | `src/parallax/app/runtime/app.py` | 317 | runtime/control | C:FrontendStaticFiles<br>F:create_app<br>F:_mount_frontend | `parallax.app.runtime.bootstrap`<br>`parallax.app.runtime.telemetry`<br>`parallax.app.runtime.worker_status` | 1 |
| `app/runtime` | `src/parallax/app/runtime/bootstrap.py` | 389 | runtime/control | C:Runtime<br>F:bootstrap<br>F:_assemble_runtime | `parallax.app.runtime.db_pool_bundle`<br>`parallax.app.runtime.llm_gateway`<br>`parallax.app.runtime.provider_wiring.model_execution` | 2 |
| `app/runtime` | `src/parallax/app/runtime/db_pool_bundle.py` | 378 | runtime/control | C:_SyncClosePool<br>C:DBPoolBundle<br>C:AdvisoryLockConnection | `parallax.app.runtime.repository_session`<br>`parallax.app.runtime.telemetry`<br>`parallax.app.runtime.wake_bus` | 3 |
| `app/runtime` | `src/parallax/app/runtime/job_queue.py` | 29 | runtime/control | C:JobQueueDescriptor | — | 1 |
| `app/runtime` | `src/parallax/app/runtime/llm_gateway.py` | 39 | runtime/control | C:LLMGateway<br>F:_model_base | `parallax.platform.config.settings` | 1 |
| `app/runtime` | `src/parallax/app/runtime/ops_cli_queries.py` | 98 | runtime/control | F:token_radar_source_count<br>F:token_radar_max_resolution_ms<br>F:token_radar_max_market_tick_observed_at_ms | — | 1 |
| `app/runtime` | `src/parallax/app/runtime/ops_diagnostics.py` | 868 | runtime/control | F:ops_diagnostics_payload<br>F:ops_queue_payload<br>F:redact_diagnostics | `parallax.app.runtime.job_queue`<br>`parallax.app.runtime.worker_status`<br>`parallax.domains.asset_market.providers` | 1 |
| `app/runtime` | `src/parallax/app/runtime/projection_dirty_targets.py` | 260 | runtime/control | F:enqueue_projection_dirty_targets<br>F:_enqueue_news_targets<br>F:_selected_projections | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.runtime.news_projection_work`<br>`parallax.domains.news_intel.services.news_item_agent_policy` | 2 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/__init__.py` | 67 | package/export | F:wire_providers<br>F:wire_asset_market_providers<br>F:_require_agent_execution_gateway | `parallax.app.runtime.provider_wiring.types`<br>`parallax.platform.config.settings`<br>`parallax.app.runtime.provider_wiring.asset_market` | 3 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/asset_market.py` | 220 | runtime/control | C:_SyncCloseProvider<br>C:FallbackDexQuoteProvider<br>F:wire_asset_market | `parallax.app.runtime.provider_wiring`<br>`parallax.app.runtime.provider_wiring.binance`<br>`parallax.app.runtime.provider_wiring.gmgn` | 1 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/binance.py` | 235 | runtime/control | C:BinanceWeb3DexProfileProvider<br>C:BinanceUsdmFuturesMarketProvider<br>C:BinanceUsdmFuturesOiProvider | `parallax.domains.asset_market.providers`<br>`parallax.domains.cex_market_intel.providers`<br>`parallax.integrations.binance.usdm_futures_client` | 2 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/cex_market_intel.py` | 39 | runtime/control | F:wire_cex_market_intel<br>F:_coinglass_derivatives | `parallax.app.runtime.provider_wiring`<br>`parallax.app.runtime.provider_wiring.binance`<br>`parallax.app.runtime.provider_wiring.types` | 1 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/gmgn.py` | 183 | runtime/control | C:GmgnDexMarketProvider<br>F:gmgn_dex_market<br>F:gmgn_provider_health | `parallax.app.runtime.provider_wiring.types`<br>`parallax.domains.asset_market.providers`<br>`parallax.domains.ingestion.providers` | 2 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/model_execution.py` | 49 | runtime/control | F:litellm_news_item_brief_provider<br>F:build_agent_execution_gateway<br>F:_require_llm_gateway | `parallax.integrations.model_execution.execution_gateway`<br>`parallax.integrations.model_execution.news_item_brief_agent_client`<br>`parallax.platform.agent_execution` | 2 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/news.py` | 127 | runtime/control | F:news_feed_client<br>C:RegistryBackedNewsSourceProvider<br>F:_observation_from_entry | `parallax.domains.news_intel.providers`<br>`parallax.domains.news_intel.services.feed_item_normalizer`<br>`parallax.domains.news_intel.types.source_provider` | 1 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/okx.py` | 315 | runtime/control | C:_SyncCloseProvider<br>C:OkxDexDiscoveryProvider<br>C:OkxDexQuoteProvider | `parallax.app.runtime.provider_wiring.types`<br>`parallax.domains.asset_market.providers`<br>`parallax.integrations.okx.chains` | 1 |
| `app/runtime` | `src/parallax/app/runtime/provider_wiring/types.py` | 157 | type/contract | C:_SyncClosable<br>C:_AsyncClosable<br>C:IngestionProviders | `parallax.domains.asset_market.providers`<br>`parallax.domains.cex_market_intel.providers`<br>`parallax.domains.ingestion.providers` | 6 |
| `app/runtime` | `src/parallax/app/runtime/providers_wiring.py` | 22 | runtime/control | — | `parallax.app.runtime.provider_wiring`<br>`parallax.app.runtime.provider_wiring.types` | 5 |
| `app/runtime` | `src/parallax/app/runtime/queue_health.py` | 821 | runtime/control | C:StatusQueueSpec<br>C:QueueHealthAdapterSpec<br>F:queue_health_adapter_specs | `parallax.app.runtime.worker_manifest` | 2 |
| `app/runtime` | `src/parallax/app/runtime/repository_session.py` | 222 | runtime/control | C:RepositorySession<br>F:repositories_for_connection<br>F:repository_session | `parallax.domains.asset_market.interfaces`<br>`parallax.domains.asset_market.queries.token_profile_source_query`<br>`parallax.domains.asset_market.repositories.asset_profile_refresh_target_repository` | 10 |
| `app/runtime` | `src/parallax/app/runtime/telemetry.py` | 173 | runtime/control | C:TelemetryRegistry<br>F:_label<br>F:_p99 | — | 5 |
| `app/runtime` | `src/parallax/app/runtime/wake_bus.py` | 106 | runtime/control | C:WakeBus<br>F:_require_connection_context<br>F:_execute_notify | — | 2 |
| `app/runtime` | `src/parallax/app/runtime/wake_waiter.py` | 130 | runtime/control | C:WakeWaiterConnectionContractError<br>C:WakeWaiter<br>F:_normalize_channel | — | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_base.py` | 590 | worker | C:WorkerStatus<br>C:WorkerRunSoftTimeout<br>C:WorkerRunHardTimeout | `parallax.app.runtime.worker_result`<br>`parallax.platform.cancellation` | 35 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/__init__.py` | 296 | package/export | C:WorkerFactoryContext<br>C:WorkerFactorySpec<br>F:construct_workers | `parallax.app.runtime.db_pool_bundle`<br>`parallax.app.runtime.providers_wiring`<br>`parallax.app.runtime.telemetry` | 9 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/asset_market.py` | 139 | worker wiring | F:construct_asset_market_workers | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/cex_market_intel.py` | 37 | worker wiring | F:construct_cex_market_intel_workers | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/ingestion.py` | 21 | worker wiring | F:construct_ingestion_workers | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/macro_intel.py` | 56 | worker wiring | F:construct_macro_intel_workers | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/narrative_intel.py` | 30 | worker wiring | F:construct_narrative_intel_workers | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/news_intel.py` | 214 | worker wiring | F:construct_news_intel_workers<br>C:_RuntimeTokenIdentityLookup<br>F:_lookup_result | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/notifications.py` | 95 | worker wiring | F:construct_notification_workers<br>F:_notification_rule_engine<br>C:_LocalWakeWaiter | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_factories/token_intel.py` | 26 | worker wiring | F:construct_token_intel_workers | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_factories`<br>`parallax.app.runtime.worker_manifest` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_manifest.py` | 1468 | worker | C:WorkerKind<br>C:WorkerLane<br>C:WorkerRuntimeConstraint | — | 16 |
| `app/runtime` | `src/parallax/app/runtime/worker_result.py` | 13 | worker | C:WorkerResult | — | 27 |
| `app/runtime` | `src/parallax/app/runtime/worker_scheduler.py` | 199 | worker | C:WorkerScheduler<br>F:_worker_startable<br>F:_nonnegative_timeout_seconds | `parallax.app.runtime.worker_manifest`<br>`parallax.app.runtime.worker_status` | 1 |
| `app/runtime` | `src/parallax/app/runtime/worker_status.py` | 284 | worker | C:WorkerLaneStatus<br>F:workers_status_payload<br>F:_runtime_worker_statuses | `parallax.app.runtime.queue_health`<br>`parallax.app.runtime.worker_manifest` | 5 |
| `app/surfaces` | `src/parallax/app/surfaces/__init__.py` | 0 | package/export | — | — | 0 |
| `app/surfaces` | `src/parallax/app/surfaces/api/__init__.py` | 0 | package/export | — | — | 9 |
| `app/surfaces` | `src/parallax/app/surfaces/api/dependencies.py` | 57 | HTTP/WS surface | F:_runtime<br>F:_authenticated_runtime<br>F:_request_token | `parallax.app.runtime.worker_manifest`<br>`parallax.app.runtime.worker_status`<br>`parallax.app.surfaces.api.exceptions` | 11 |
| `app/surfaces` | `src/parallax/app/surfaces/api/exceptions.py` | 28 | HTTP/WS surface | C:ApiUnauthorized<br>C:ApiBadRequest<br>F:api_unauthorized_response | `parallax.app.surfaces.api.responses` | 9 |
| `app/surfaces` | `src/parallax/app/surfaces/api/http.py` | 36 | HTTP/WS surface | F:create_api_router | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.routes_cex`<br>`parallax.app.surfaces.api.routes_events` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/responses.py` | 23 | HTTP/WS surface | F:_json<br>F:_finite_json | — | 11 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_cex.py` | 128 | HTTP/WS surface | F:cex_radar_board<br>F:cex_detail<br>F:_cex_detail_target_query | `parallax.app.surfaces.api.dependencies`<br>`parallax.app.surfaces.api.exceptions`<br>`parallax.app.surfaces.api.responses` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_events.py` | 155 | HTTP/WS surface | F:recent<br>F:events_by_ids<br>F:_payloads_for_events | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_macro.py` | 356 | HTTP/WS surface | F:macro<br>F:macro_asset_correlation<br>F:macro_series | `parallax.app.surfaces.api.dependencies`<br>`parallax.app.surfaces.api.exceptions`<br>`parallax.app.surfaces.api.responses` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_news.py` | 163 | HTTP/WS surface | F:list_news<br>F:get_news_item<br>F:get_news_fact | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_notifications.py` | 541 | HTTP/WS surface | F:account_alerts<br>F:account_quality<br>F:notifications | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_ops.py` | 59 | HTTP/WS surface | F:ops_diagnostics<br>F:ops_queue | `parallax.app.runtime.ops_diagnostics`<br>`parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_radar.py` | 119 | HTTP/WS surface | F:token_radar<br>F:stocks_radar<br>F:live_market | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_search.py` | 249 | HTTP/WS surface | F:search<br>F:search_inspect<br>F:token_case | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_status.py` | 41 | HTTP/WS surface | F:bootstrap<br>F:create_router | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_token_images.py` | 64 | HTTP/WS surface | F:token_image<br>F:_valid_image_id<br>F:_token_image_cache_dir | `parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/routes_watchlist.py` | 111 | HTTP/WS surface | F:watchlist_handles_overview<br>F:watchlist_handle_overview<br>F:watchlist_handle_timeline | `parallax.app.surfaces.api`<br>`parallax.app.surfaces.api.schemas`<br>`parallax.app.surfaces.api.dependencies` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/api/schemas.py` | 542 | HTTP/WS surface | C:ApiSchema<br>C:ApiEnvelope<br>C:BootstrapData | — | 9 |
| `app/surfaces` | `src/parallax/app/surfaces/api/validators.py` | 79 | HTTP/WS surface | F:_limit<br>F:_positive_limit<br>F:_api_limit_int | `parallax.app.surfaces.api.exceptions` | 8 |
| `app/surfaces` | `src/parallax/app/surfaces/api/ws.py` | 338 | HTTP/WS surface | C:ClientSubscription<br>C:PublicWebSocketHub<br>F:_json_message | `parallax.domains.evidence.interfaces`<br>`parallax.domains.ingestion.services.subscriptions` | 2 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/__init__.py` | 0 | package/export | — | — | 0 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/__init__.py` | 8 | package/export | — | — | 2 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/config.py` | 139 | CLI surface | F:handle_init<br>F:handle_config<br>F:_ensure_postgres_password_file | `parallax.platform.config.settings`<br>`parallax.platform.paths.runtime_paths` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/db.py` | 46 | CLI surface | F:handle_db | `parallax.app.surfaces.cli.dependencies`<br>`parallax.domains.token_intel.interfaces`<br>`parallax.platform.config.settings` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/macro.py` | 411 | CLI surface | F:handle_macro<br>F:_handle_import_bundle<br>F:_handle_sync | `parallax.app.runtime.wake_bus`<br>`parallax.app.surfaces.cli.dependencies`<br>`parallax.domains.macro_intel._constants` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/ops.py` | 1110 | CLI surface | F:handle_ops<br>F:_enqueue_token_radar_dirty_targets<br>F:_enqueue_token_capture_tier_rank_set | `parallax.app.runtime.bootstrap`<br>`parallax.app.runtime.db_pool_bundle`<br>`parallax.app.runtime.ops_cli_queries` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/queue_ops.py` | 532 | CLI surface | F:handle_queue_inspect<br>F:handle_queue_resolve<br>F:handle_queue_resolve_bucket | `parallax.app.runtime.queue_health`<br>`parallax.app.runtime.worker_manifest`<br>`parallax.domains.asset_market.repositories.discovery_repository` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/read_models.py` | 121 | CLI surface | F:handle_read_model<br>F:_handle_set<br>F:_now_ms | `parallax.app.surfaces.cli.dependencies`<br>`parallax.domains.account_quality.read_models.account_alert_service`<br>`parallax.domains.account_quality.read_models.account_quality_service` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/commands/serve.py` | 21 | CLI surface | F:handle_serve | `parallax.app.runtime.app`<br>`parallax.platform.config.settings`<br>`parallax.platform.logging.setup` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/dependencies.py` | 28 | CLI surface | F:postgres_connection<br>F:repositories | `parallax.app.runtime.repository_session`<br>`parallax.platform.db.postgres_client` | 4 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/main.py` | 54 | CLI surface | F:main<br>F:_finish<br>F:_emit | `parallax.app.surfaces.cli.parser`<br>`parallax.app.surfaces.cli.commands`<br>`parallax.app.surfaces.cli.commands.config` | 1 |
| `app/surfaces` | `src/parallax/app/surfaces/cli/parser.py` | 275 | CLI surface | F:_positive_int<br>F:_nonnegative_int<br>F:_positive_float | `parallax.app.runtime.projection_dirty_targets` | 1 |
| `root` | `src/parallax/cli.py` | 5 | module | — | `parallax.app.surfaces.cli.main` | 1 |
| `domains/__init__.py/root` | `src/parallax/domains/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/account_quality/__init__.py` | `src/parallax/domains/account_quality/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/account_quality/read_models` | `src/parallax/domains/account_quality/read_models/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/account_quality/read_models` | `src/parallax/domains/account_quality/read_models/account_alert_service.py` | 33 | module | C:AccountAlertService | — | 3 |
| `domains/account_quality/read_models` | `src/parallax/domains/account_quality/read_models/account_quality_service.py` | 70 | module | C:AccountQualityService<br>F:_account_quality_payload<br>F:_handle | `parallax.domains.account_quality.repositories.account_quality_repository` | 3 |
| `domains/account_quality/repositories` | `src/parallax/domains/account_quality/repositories/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/account_quality/repositories` | `src/parallax/domains/account_quality/repositories/account_quality_repository.py` | 639 | repository | C:AccountQualityRepository<br>F:_handle<br>F:_unique_handles | — | 3 |
| `domains/account_quality/services` | `src/parallax/domains/account_quality/services/__init__.py` | 5 | package/export | — | `parallax.domains.account_quality.services.account_quality_backfill_service` | 0 |
| `domains/account_quality/services` | `src/parallax/domains/account_quality/services/account_quality_backfill_service.py` | 206 | domain service | C:AccountQualityBackfillService<br>F:_price_change_at<br>F:_max_drawdown | `parallax.domains.token_intel.interfaces`<br>`parallax.domains.account_quality.repositories.account_quality_repository` | 2 |
| `domains/asset_market/__init__.py` | `src/parallax/domains/asset_market/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/asset_market/identity_evidence_policy.py` | `src/parallax/domains/asset_market/identity_evidence_policy.py` | 162 | module | F:select_current_identity<br>F:_select_evidence<br>F:_evidence_sort_key | — | 5 |
| `domains/asset_market/interfaces.py` | `src/parallax/domains/asset_market/interfaces.py` | 64 | port/interface | — | `parallax.domains.asset_market.identity_evidence_policy`<br>`parallax.domains.asset_market.read_models.message_price_payload`<br>`parallax.domains.asset_market.repositories.asset_profile_repository` | 7 |
| `domains/asset_market/profile_source_selection.py` | `src/parallax/domains/asset_market/profile_source_selection.py` | 93 | module | F:select_gmgn_stream_source<br>F:select_okx_dex_source<br>F:_has_gmgn_stream_metadata | `parallax.domains.asset_market.identity_evidence_policy` | 1 |
| `domains/asset_market/providers.py` | `src/parallax/domains/asset_market/providers.py` | 197 | module | C:MarketCapability<br>C:ProviderHealth<br>C:DexProviderTemporarilyUnavailable | — | 12 |
| `domains/asset_market/queries` | `src/parallax/domains/asset_market/queries/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/asset_market/queries` | `src/parallax/domains/asset_market/queries/token_profile_source_query.py` | 127 | query | C:TokenProfileSourceQuery<br>F:_dedupe | `parallax.domains.asset_market.identity_evidence_policy`<br>`parallax.domains.asset_market.profile_source_selection` | 1 |
| `domains/asset_market/read_models` | `src/parallax/domains/asset_market/read_models/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/asset_market/read_models` | `src/parallax/domains/asset_market/read_models/market_candles_service.py` | 66 | module | C:MarketCandlesService<br>F:_cex_anchor_candles<br>F:_dex_anchor_candles | — | 1 |
| `domains/asset_market/read_models` | `src/parallax/domains/asset_market/read_models/message_price_payload.py` | 45 | module | F:message_price_payload<br>F:_number | — | 1 |
| `domains/asset_market/read_models` | `src/parallax/domains/asset_market/read_models/token_profile_read_model.py` | 182 | module | C:TokenProfileReadModel<br>F:_block_from_row<br>F:_pending_block | — | 3 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py` | 606 | repository | C:AssetProfileRefreshTargetRepository<br>F:_transaction<br>F:_run_repository_write | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.json_safety` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/asset_profile_repository.py` | 219 | repository | C:AssetProfileRepository<br>F:_optional_text<br>F:_required_text | `parallax.platform.db.json_safety` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py` | 150 | repository | F:_cursor_rowcount<br>F:_optional_returning_row<br>C:CexTokenProfileRepository | `parallax.platform.db.json_safety` | 2 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/discovery_repository.py` | 839 | repository | C:DiscoveryRepository<br>F:_lookup_key_records<br>F:_lookup_type | `parallax.platform.db.queue_terminal` | 3 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/enriched_event_repository.py` | 184 | repository | C:EnrichedEventRepository<br>F:_single_row_mutation_applied | `parallax.domains.asset_market.types` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py` | 663 | repository | C:EventAnchorBackfillJobRepository<br>F:_cursor_rowcount<br>F:_returned_rowcount | `parallax.domains.asset_market.types`<br>`parallax.platform.db.queue_terminal` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/identity_evidence_repository.py` | 292 | repository | C:IdentityEvidenceRepository<br>F:_evidence_id<br>F:_transaction | `parallax.domains.asset_market.identity_evidence_policy` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py` | 522 | repository | C:MarketTickCurrentDirtyTargetRepository<br>F:_target_records<br>F:_target_key | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.queue_terminal` | 2 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/market_tick_current_repository.py` | 171 | repository | C:MarketTickCurrentRepository<br>F:_current_params<br>F:_cursor_rowcount | `parallax.platform.db.json_safety` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/market_tick_repository.py` | 300 | repository | F:_cursor_rowcount<br>F:_optional_returning_id<br>C:MarketTickRepository | `parallax.domains.asset_market.types`<br>`parallax.domains.asset_market.types.market_tick_id`<br>`parallax.platform.db.json_safety` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/registry_repository.py` | 932 | repository | C:RegistryRepository<br>F:_transaction<br>F:_cursor_rowcount | — | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py` | 568 | repository | C:TokenCaptureTierDirtyTargetRepository<br>F:_transaction<br>F:_run_repository_write | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.queue_terminal` | 2 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py` | 235 | repository | C:TokenCaptureTierRepository<br>F:_cursor_rowcount<br>F:_required_nonnegative_int | — | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py` | 392 | repository | C:TokenImageAssetRepository<br>F:_cursor_rowcount<br>F:_single_rowcount | `parallax.platform.db.json_safety` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py` | 713 | repository | C:TokenImageSourceDirtyTargetRepository<br>F:_target_records<br>F:_target_identity_records | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.json_safety`<br>`parallax.platform.db.queue_terminal` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py` | 599 | repository | C:TokenProfileCurrentDirtyTargetRepository<br>F:_target_records<br>F:_target_key | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.queue_terminal` | 1 |
| `domains/asset_market/repositories` | `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py` | 228 | repository | C:TokenProfileCurrentRepository<br>F:_dedupe_targets<br>F:_optional_text | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.json_safety` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py` | 294 | worker | C:AssetProfileRefreshWorker<br>F:_enqueue_profile_current<br>F:_required_source_watermark_ms | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.providers` | 2 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py` | 540 | worker | C:_AttachOutcome<br>C:_TerminalOutcome<br>C:_RescheduleOutcome | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.services.event_market_capture` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/live_price_gateway.py` | 337 | worker | C:LiveMarketSnapshot<br>C:LiveMarketEmit<br>C:LivePriceGateway | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py` | 176 | worker | C:MarketTickCurrentProjectionWorker<br>C:_ClaimResult<br>F:_error_text | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/market_tick_poll_worker.py` | 539 | worker | C:MarketTickPollWorker<br>C:_ChainTarget<br>C:_CexTarget | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.providers` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py` | 388 | worker | C:_AsyncCloseIterator<br>C:MarketTickStreamWorker<br>C:_TargetParts | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.providers` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py` | 795 | worker | C:ResolutionRefreshWorker<br>F:_fetch_lookup_provider_result<br>F:_fetch_dex_symbol_lookup_result | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.providers` | 2 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py` | 320 | worker | C:TokenCaptureTierWorker<br>F:project_once<br>C:_Candidate | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.token_intel.interfaces` | 1 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py` | 341 | worker | C:TokenImageMirrorWorker<br>C:_TokenImageAssetSessionRepository<br>F:_record_mirror_result | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.services.token_image_mirror` | 2 |
| `domains/asset_market/runtime` | `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py` | 373 | worker | C:TokenProfileCurrentWorker<br>F:rebuild_token_profile_current_once<br>C:_ClaimedTokenProfileSources | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.asset_market.services.token_image_source_admission` | 2 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/asset_market_sync.py` | 124 | domain service | C:BinanceUsdtPerpRoute<br>F:sync_binance_usdt_perp_routes<br>F:_normalized_routes | — | 1 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/asset_profile_refresh.py` | 126 | domain service | F:fetch_asset_profile<br>F:write_ready_asset_profile<br>F:write_missing_asset_profile | `parallax.domains.asset_market.providers` | 1 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/cex_token_profile_sync.py` | 109 | domain service | F:sync_cex_token_profiles<br>F:_formal_profile<br>F:_optional_text | `parallax.domains.asset_market.repositories.cex_token_profile_repository` | 1 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/event_market_capture.py` | 454 | domain service | C:TickLookup<br>C:CaptureResult<br>C:_CaptureRequest | `parallax.domains.asset_market.providers`<br>`parallax.domains.asset_market.types`<br>`parallax.domains.asset_market.types.market_tick_id` | 3 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/market_tick_persistence.py` | 56 | domain service | C:MarketTickPersistenceResult<br>C:MarketTickPersistenceService | `parallax.domains.asset_market.types` | 4 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/token_image_mirror.py` | 249 | domain service | C:TokenImageMirrorService<br>F:is_allowed_token_image_source_url<br>F:validated_token_image_source_url | — | 2 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/token_image_source_admission.py` | 418 | domain service | C:TokenImageSourceCandidate<br>C:TokenImageSourceAdmissionResult<br>F:image_source_candidates_for_target | `parallax.domains.asset_market.services.token_image_mirror` | 1 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/token_profile_current_projection.py` | 537 | domain service | F:project_token_profile_current<br>F:_gmgn_openapi_row<br>F:_asset_profile_row | — | 1 |
| `domains/asset_market/services` | `src/parallax/domains/asset_market/services/us_equity_symbol_sync.py` | 158 | domain service | C:NasdaqTraderSymbol<br>C:NasdaqTraderSymbolClient<br>F:sync_us_equity_symbols | — | 1 |
| `domains/asset_market/types` | `src/parallax/domains/asset_market/types/__init__.py` | 21 | package/export | — | `parallax.domains.asset_market.types.market_tick`<br>`parallax.domains.asset_market.types.market_tick_id` | 9 |
| `domains/asset_market/types` | `src/parallax/domains/asset_market/types/market_tick.py` | 51 | type/contract | C:MarketTick<br>C:EnrichedEventCapture | — | 1 |
| `domains/asset_market/types` | `src/parallax/domains/asset_market/types/market_tick_id.py` | 9 | type/contract | F:market_tick_id | — | 5 |
| `domains/cex_market_intel/__init__.py` | `src/parallax/domains/cex_market_intel/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/cex_market_intel/providers.py` | `src/parallax/domains/cex_market_intel/providers.py` | 63 | module | C:CexOiTicker24h<br>C:CexFundingPremium<br>C:CexOpenInterestPoint | — | 6 |
| `domains/cex_market_intel/repositories` | `src/parallax/domains/cex_market_intel/repositories/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/cex_market_intel/repositories` | `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py` | 323 | repository | C:CexDetailSnapshotRepository<br>F:_public_snapshot<br>F:_required_persisted_snapshot_list | `parallax.platform.current_read_model_payload_hash` | 1 |
| `domains/cex_market_intel/repositories` | `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py` | 582 | repository | C:CexBoardPublicationResult<br>C:CexOiRadarRepository<br>F:_board_key | `parallax.platform.current_read_model_payload_hash` | 1 |
| `domains/cex_market_intel/runtime` | `src/parallax/domains/cex_market_intel/runtime/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/cex_market_intel/runtime` | `src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py` | 269 | worker | C:CexOiRadarBoardWorker<br>F:_now_ms<br>F:_positive_worker_setting_int | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.cex_market_intel.providers` | 1 |
| `domains/cex_market_intel/scoring` | `src/parallax/domains/cex_market_intel/scoring/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/cex_market_intel/scoring` | `src/parallax/domains/cex_market_intel/scoring/oi_radar_scoring.py` | 43 | scoring | F:score_oi_radar_row<br>F:_float | — | 1 |
| `domains/cex_market_intel/services` | `src/parallax/domains/cex_market_intel/services/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/cex_market_intel/services` | `src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py` | 244 | domain service | F:build_binance_oi_radar_rows<br>F:_tickers_by_symbol<br>F:_premiums_by_symbol | `parallax.domains.cex_market_intel.providers`<br>`parallax.domains.cex_market_intel.scoring.oi_radar_scoring` | 1 |
| `domains/cex_market_intel/services` | `src/parallax/domains/cex_market_intel/services/cex_detail_snapshot_builder.py` | 332 | domain service | F:build_cex_detail_snapshot<br>F:_target_id<br>F:_oi_delta_slots | — | 1 |
| `domains/cex_market_intel/services` | `src/parallax/domains/cex_market_intel/services/coinglass_detail_enricher.py` | 212 | domain service | F:enrich_rows_with_coinglass<br>F:enrich_row_with_coinglass<br>F:_lookback | `parallax.domains.cex_market_intel.providers` | 1 |
| `domains/evidence/__init__.py` | `src/parallax/domains/evidence/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/evidence/interfaces.py` | `src/parallax/domains/evidence/interfaces.py` | 44 | port/interface | — | `parallax.domains.evidence.repositories.evidence_repository`<br>`parallax.domains.evidence.services.entity_extractor`<br>`parallax.domains.evidence.types.entity` | 13 |
| `domains/evidence/repositories` | `src/parallax/domains/evidence/repositories/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/evidence/repositories` | `src/parallax/domains/evidence/repositories/entity_repository.py` | 194 | repository | C:EntityRepository<br>F:_entity_id<br>F:_now_ms | `parallax.domains.evidence.types.entity`<br>`parallax.domains.evidence.types.twitter_event` | 3 |
| `domains/evidence/repositories` | `src/parallax/domains/evidence/repositories/evidence_repository.py` | 435 | repository | C:EvidenceRepository<br>F:_token_filter_keysets<br>F:event_to_row | `parallax.domains.evidence.types.entity`<br>`parallax.domains.evidence.types.tweet_identity`<br>`parallax.domains.evidence.types.tweet_text` | 4 |
| `domains/evidence/services` | `src/parallax/domains/evidence/services/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/evidence/services` | `src/parallax/domains/evidence/services/entity_extractor.py` | 292 | domain service | C:TextSurface<br>F:extract_entities_from_surfaces<br>F:_extract_surface_entities | `parallax.domains.evidence.types.entity`<br>`parallax.domains.evidence.types.tweet_text` | 1 |
| `domains/evidence/services` | `src/parallax/domains/evidence/services/ingest_service.py` | 624 | domain service | C:PreparedIngest<br>C:IngestService<br>F:_event_surfaces | `parallax.domains.asset_market.interfaces`<br>`parallax.domains.evidence.interfaces`<br>`parallax.domains.evidence.repositories.entity_repository` | 1 |
| `domains/evidence/types` | `src/parallax/domains/evidence/types/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/evidence/types` | `src/parallax/domains/evidence/types/entity.py` | 77 | type/contract | C:ExtractedEntity<br>F:normalize_ca<br>F:is_valid_ton_friendly_address | — | 4 |
| `domains/evidence/types` | `src/parallax/domains/evidence/types/tweet_identity.py` | 15 | type/contract | F:logical_dedup_key<br>F:canonical_tweet_url | `parallax.domains.evidence.types.twitter_event` | 1 |
| `domains/evidence/types` | `src/parallax/domains/evidence/types/tweet_text.py` | 75 | type/contract | C:TextProjection<br>F:build_text_projection<br>F:extract_cashtags | — | 2 |
| `domains/evidence/types` | `src/parallax/domains/evidence/types/twitter_event.py` | 100 | type/contract | C:Source<br>C:Author<br>C:Media | — | 4 |
| `domains/ingestion/__init__.py` | `src/parallax/domains/ingestion/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/ingestion/interfaces.py` | `src/parallax/domains/ingestion/interfaces.py` | 16 | port/interface | C:IngestedEvent | `parallax.domains.evidence.interfaces` | 2 |
| `domains/ingestion/providers.py` | `src/parallax/domains/ingestion/providers.py` | 33 | module | C:IngestStoreProtocol<br>C:EventPublisherProtocol<br>C:UpstreamClientProtocol | `parallax.domains.evidence.interfaces`<br>`parallax.domains.ingestion.interfaces` | 3 |
| `domains/ingestion/runtime` | `src/parallax/domains/ingestion/runtime/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/ingestion/runtime` | `src/parallax/domains/ingestion/runtime/collector_service.py` | 227 | worker | C:CollectorStatus<br>C:CollectorService<br>F:_now_ms | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.ingestion.providers` | 1 |
| `domains/ingestion/services` | `src/parallax/domains/ingestion/services/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/ingestion/services` | `src/parallax/domains/ingestion/services/normalizer.py` | 270 | domain service | F:parse_gmgn_frame<br>F:normalize_gmgn_payload<br>F:_normalize_twitter_item | `parallax.domains.evidence.interfaces`<br>`parallax.domains.ingestion.types.gmgn_token_payload` | 1 |
| `domains/ingestion/services` | `src/parallax/domains/ingestion/services/subscriptions.py` | 28 | domain service | F:normalize_handles<br>F:event_matches_handles | `parallax.domains.evidence.interfaces` | 2 |
| `domains/ingestion/types` | `src/parallax/domains/ingestion/types/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/ingestion/types` | `src/parallax/domains/ingestion/types/gmgn_token_payload.py` | 109 | type/contract | F:parse_gmgn_token_payload<br>F:_normalize_chain<br>F:_normalize_address | `parallax.domains.evidence.interfaces` | 1 |
| `domains/macro_intel/__init__.py` | `src/parallax/domains/macro_intel/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/macro_intel/_constants.py` | `src/parallax/domains/macro_intel/_constants.py` | 1378 | module | — | — | 12 |
| `domains/macro_intel/observation_identity.py` | `src/parallax/domains/macro_intel/observation_identity.py` | 119 | module | F:normalize_macro_date<br>F:macro_observation_id<br>F:macro_observation_fact_payload_hash | `parallax.platform.current_read_model_payload_hash` | 7 |
| `domains/macro_intel/repositories` | `src/parallax/domains/macro_intel/repositories/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/macro_intel/repositories` | `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py` | 2450 | repository | C:MacroSeriesRefreshResult<br>C:MacroObservationUpsertOutcome<br>C:MacroIntelRepository | `parallax.domains.macro_intel._constants`<br>`parallax.domains.macro_intel.observation_identity`<br>`parallax.platform.current_read_model_payload_hash` | 1 |
| `domains/macro_intel/runtime` | `src/parallax/domains/macro_intel/runtime/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/macro_intel/runtime` | `src/parallax/domains/macro_intel/runtime/macro_daily_brief_projection_worker.py` | 69 | worker | C:MacroDailyBriefProjectionWorker<br>F:_now_ms | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.macro_intel._constants` | 1 |
| `domains/macro_intel/runtime` | `src/parallax/domains/macro_intel/runtime/macro_sync_worker.py` | 122 | worker | C:MacroSyncWorker<br>F:_now_ms<br>F:_required_positive_int | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.macro_intel.services.macro_sync_service` | 1 |
| `domains/macro_intel/runtime` | `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py` | 298 | worker | C:MacroViewProjectionWorker<br>F:_now_ms<br>F:_required_positive_int | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.macro_intel._constants` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_asset_correlation.py` | 366 | domain service | F:build_macro_asset_correlation<br>F:correlation_query_bounds<br>F:_price_series_by_asset | `parallax.domains.macro_intel.observation_identity` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_daily_brief.py` | 241 | domain service | F:build_macro_daily_brief<br>F:_missing_blocks<br>F:_risk_label | — | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_feature_engine.py` | 402 | domain service | F:build_macro_features<br>F:_features_for_series<br>F:_history_points | `parallax.domains.macro_intel._constants`<br>`parallax.domains.macro_intel.observation_identity`<br>`parallax.domains.macro_intel.services.macro_gap_payloads` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_gap_payloads.py` | 146 | domain service | F:build_macro_data_gaps<br>F:_gap_payload<br>F:_gap_concept_key | `parallax.domains.macro_intel._constants` | 5 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_module_catalog.py` | 909 | domain service | C:UnsupportedMacroModuleError<br>C:MacroChartSpec<br>C:MacroTableSpec | `parallax.domains.macro_intel._constants` | 2 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_module_views.py` | 7733 | domain service | F:build_macro_module_view<br>F:_macro_module_view_snapshot_sections<br>F:_module_feature_map | `parallax.domains.macro_intel._constants`<br>`parallax.domains.macro_intel.services.macro_gap_payloads`<br>`parallax.domains.macro_intel.services.macro_module_catalog` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_regime_engine.py` | 1246 | domain service | F:build_macro_view_snapshot<br>F:_build_panels<br>F:_build_chain | `parallax.domains.macro_intel._constants`<br>`parallax.domains.macro_intel.services.macro_feature_engine`<br>`parallax.domains.macro_intel.services.macro_gap_payloads` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_scenario_engine.py` | 973 | domain service | F:build_macro_scenario<br>F:_current_regime<br>F:_confirmations | `parallax.domains.macro_intel.services.macro_gap_payloads` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_series_view.py` | 197 | domain service | C:UnsupportedMacroConceptError<br>C:UnsupportedMacroSeriesWindowError<br>F:macro_series_query_bounds | `parallax.domains.macro_intel._constants` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_sync_scheduler.py` | 139 | domain service | F:ensure_due_macro_sync_windows<br>F:_split_windows<br>F:_required_positive_int | `parallax.app.runtime.repository_session` | 1 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_sync_service.py` | 608 | domain service | C:MacrodataBundleRunnerProtocol<br>C:_StaleMacroSyncClaimError<br>C:MacroSyncService | `parallax.domains.macro_intel.observation_identity`<br>`parallax.domains.macro_intel.services.macro_sync_scheduler`<br>`parallax.domains.macro_intel.services.macro_sync_types` | 2 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macro_sync_types.py` | 42 | domain service | C:MacroSyncRunSummary<br>C:MacrodataBundleImport | — | 4 |
| `domains/macro_intel/services` | `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py` | 304 | domain service | F:parse_macrodata_bundle<br>F:write_macrodata_bundle_import<br>F:import_macrodata_bundle | `parallax.domains.macro_intel._constants`<br>`parallax.domains.macro_intel.observation_identity`<br>`parallax.domains.macro_intel.services.macro_sync_types` | 2 |
| `domains/narrative_intel/__init__.py` | `src/parallax/domains/narrative_intel/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/narrative_intel/_constants.py` | `src/parallax/domains/narrative_intel/_constants.py` | 3 | module | — | — | 2 |
| `domains/narrative_intel/interfaces.py` | `src/parallax/domains/narrative_intel/interfaces.py` | 5 | port/interface | — | `parallax.domains.narrative_intel._constants` | 1 |
| `domains/narrative_intel/read_models` | `src/parallax/domains/narrative_intel/read_models/__init__.py` | 3 | package/export | — | `parallax.domains.narrative_intel.read_models.narrative_read_model` | 0 |
| `domains/narrative_intel/read_models` | `src/parallax/domains/narrative_intel/read_models/narrative_read_model.py` | 127 | module | C:NarrativeReadModel<br>F:_extract_targets<br>F:_target_identity | `parallax.domains.narrative_intel._constants` | 3 |
| `domains/narrative_intel/repositories` | `src/parallax/domains/narrative_intel/repositories/__init__.py` | 9 | package/export | — | `parallax.domains.narrative_intel.repositories.narrative_admission_dirty_target_repository`<br>`parallax.domains.narrative_intel.repositories.narrative_repository` | 0 |
| `domains/narrative_intel/repositories` | `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py` | 843 | repository | C:_NarrativeDirtyTargetRepository<br>C:NarrativeAdmissionDirtyTargetRepository<br>F:_transaction | `parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.queue_terminal` | 2 |
| `domains/narrative_intel/repositories` | `src/parallax/domains/narrative_intel/repositories/narrative_repository.py` | 573 | repository | C:NarrativeRepository<br>F:_admission_state<br>F:admission_payload_hash | `parallax.domains.narrative_intel.types.fingerprints`<br>`parallax.domains.narrative_intel.types.narrative_currentness`<br>`parallax.domains.narrative_intel.types.narrative_epoch_policy` | 2 |
| `domains/narrative_intel/runtime` | `src/parallax/domains/narrative_intel/runtime/__init__.py` | 3 | package/export | — | `parallax.domains.narrative_intel.runtime.narrative_admission_worker` | 0 |
| `domains/narrative_intel/runtime` | `src/parallax/domains/narrative_intel/runtime/narrative_admission_worker.py` | 312 | worker | C:NarrativeAdmissionWorker<br>F:_now_ms<br>F:_error_text | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.narrative_intel.services.narrative_admission` | 2 |
| `domains/narrative_intel/services` | `src/parallax/domains/narrative_intel/services/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/narrative_intel/services` | `src/parallax/domains/narrative_intel/services/narrative_admission.py` | 141 | domain service | C:NarrativeAdmissionDecision<br>C:NarrativeAdmissionService<br>F:_admission_reason | — | 1 |
| `domains/narrative_intel/types` | `src/parallax/domains/narrative_intel/types/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/narrative_intel/types` | `src/parallax/domains/narrative_intel/types/fingerprints.py` | 16 | type/contract | F:source_fingerprint<br>F:_hash_payload | — | 1 |
| `domains/narrative_intel/types` | `src/parallax/domains/narrative_intel/types/narrative_currentness.py` | 33 | type/contract | F:unsupported_admission_sentinel | — | 1 |
| `domains/narrative_intel/types` | `src/parallax/domains/narrative_intel/types/narrative_epoch_policy.py` | 6 | type/contract | — | — | 1 |
| `domains/news_intel/__init__.py` | `src/parallax/domains/news_intel/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/news_intel/_constants.py` | `src/parallax/domains/news_intel/_constants.py` | 15 | module | — | — | 13 |
| `domains/news_intel/providers.py` | `src/parallax/domains/news_intel/providers.py` | 74 | module | C:NewsSourceProvider<br>C:NewsItemBriefProvider | `parallax.domains.news_intel.types.news_item_brief`<br>`parallax.domains.news_intel.types.news_story_brief`<br>`parallax.domains.news_intel.types.source_provider` | 3 |
| `domains/news_intel/queries` | `src/parallax/domains/news_intel/queries/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/news_intel/queries` | `src/parallax/domains/news_intel/queries/news_page_query.py` | 57 | query | C:NewsPageQuery<br>F:_public_news_row<br>F:_required_positive_int | `parallax.domains.news_intel.repositories.news_repository` | 2 |
| `domains/news_intel/repositories` | `src/parallax/domains/news_intel/repositories/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/news_intel/repositories` | `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py` | 799 | repository | C:NewsProjectionDirtyTargetRepository<br>F:_dirty_records<br>F:_dirty_record_text | `parallax.platform.db.json_safety`<br>`parallax.platform.db.queue_terminal` | 1 |
| `domains/news_intel/repositories` | `src/parallax/domains/news_intel/repositories/news_repository.py` | 7606 | repository | F:_news_repository_transaction<br>F:_news_repository_write<br>C:NewsRepository | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.types`<br>`parallax.domains.news_intel.types.news_canonical_identity` | 2 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_fetch_worker.py` | 526 | worker | C:NewsFetchWorker<br>F:_payload_hash<br>F:_notify_news_page_dirty | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.news_intel.providers` | 1 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py` | 1419 | worker | C:NewsItemBriefWorker<br>C:_CandidateOutcome<br>F:_packet_from_candidate | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.news_intel.runtime.news_projection_work` | 1 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_item_process_worker.py` | 542 | worker | C:NewsItemProcessWorker<br>F:_required_text<br>F:_text | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.news_intel.runtime.news_projection_work` | 1 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py` | 351 | worker | C:NewsPageProjectionWorker<br>F:_projection_parts<br>F:_member_news_item_ids | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.news_intel._constants` | 1 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_projection_work.py` | 466 | module | F:enqueue_page_reprojection<br>F:enqueue_story_brief_work<br>F:enqueue_source_quality_refresh | — | 7 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_runtime_settings.py` | 26 | module | F:positive_worker_setting_int<br>F:required_positive_int<br>F:required_nonnegative_int | — | 6 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py` | 341 | worker | C:NewsSourceQualityProjectionWorker<br>F:_notes<br>F:_ordered_windows | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.news_intel.runtime.news_projection_work` | 1 |
| `domains/news_intel/runtime` | `src/parallax/domains/news_intel/runtime/news_story_brief_worker.py` | 1065 | worker | C:NewsStoryBriefWorker<br>C:_NoStartBackpressure<br>F:_packet_from_candidate | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.news_intel.runtime.news_projection_work` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/feed_item_normalizer.py` | 210 | domain service | F:normalize_feed_entry<br>F:_first_text<br>F:_first_value | `parallax.domains.news_intel.types`<br>`parallax.domains.news_intel.types.news_url_identity`<br>`parallax.domains.news_intel.types.text_normalization` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_content_classification.py` | 160 | domain service | F:classify_news_item_content<br>F:_first_fact_event_match<br>F:_first_text_match | `parallax.domains.news_intel.types.content_classification` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_entity_extraction.py` | 73 | domain service | F:extract_news_entities<br>F:_dedupe_by_repository_identity<br>F:_stable_id | `parallax.domains.evidence.interfaces`<br>`parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.types.news_extraction` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_fact_candidates.py` | 178 | domain service | F:build_fact_candidates<br>F:_affected_targets<br>F:_required_slots | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.services.source_authority`<br>`parallax.domains.news_intel.types.news_extraction` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_item_agent_admission.py` | 301 | domain service | F:decide_news_item_agent_admission<br>F:_base_gate<br>F:_provider_rating_gate | `parallax.domains.news_intel.services.news_market_scope`<br>`parallax.domains.news_intel.services.news_material_delta`<br>`parallax.domains.news_intel.services.news_story_similarity` | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_item_agent_policy.py` | 166 | domain service | F:news_item_agent_brief_priority<br>F:_admission_payload<br>F:_has_material_delta | `parallax.domains.news_intel.types.news_item_agent_admission` | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_item_brief_entity_support.py` | 1148 | domain service | C:EntitySupportDecision<br>C:_SourceBackedEntityKeySupport<br>F:_packet_news_item | `parallax.domains.news_intel.types.news_item_brief`<br>`parallax.domains.news_intel.types.news_story_brief` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_item_brief_input.py` | 603 | domain service | F:build_news_item_brief_input_packet<br>F:news_item_brief_material_input_payload<br>F:news_item_brief_material_input_hash | `parallax.domains.news_intel.types.news_item_brief`<br>`parallax.platform.agent_hashing` | 3 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_item_brief_stage.py` | 68 | domain service | F:news_item_brief_instructions<br>F:news_item_brief_stage_instructions<br>F:news_item_brief_prompt_text_hash | `parallax.domains.news_intel.services.news_item_brief_input`<br>`parallax.domains.news_intel.types.news_item_brief`<br>`parallax.platform.agent_execution` | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_item_brief_validation.py` | 340 | domain service | C:NewsItemBriefValidationResult<br>F:validate_news_item_brief_output<br>F:_unexpected_action_errors | `parallax.domains.news_intel.services.news_item_brief_entity_support`<br>`parallax.domains.news_intel.types.news_item_brief`<br>`parallax.domains.news_intel.types.news_story_brief` | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_market_scope.py` | 339 | domain service | F:classify_news_market_scope<br>F:_add_token_scopes<br>F:_add_fact_scopes | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.types.news_market_scope` | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_material_delta.py` | 133 | domain service | C:NewsMaterialDelta<br>F:decide_news_material_delta<br>F:_source_role_delta | `parallax.domains.news_intel.types.news_source_role_rank` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_page_projection.py` | 857 | domain service | F:build_news_page_row<br>F:_search_document_payload<br>F:_provider_rating_payload | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.types.news_page_search` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_provider_contract.py` | 116 | domain service | C:NewsProviderContractError<br>F:validate_news_provider_contract<br>F:configured_news_provider_types | — | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_story_brief_input.py` | 273 | domain service | F:build_news_story_brief_input_packet<br>F:news_story_brief_material_input_payload<br>F:news_story_brief_material_input_hash | `parallax.domains.news_intel.services.news_item_brief_input`<br>`parallax.domains.news_intel.types.news_item_brief`<br>`parallax.domains.news_intel.types.news_story_brief` | 2 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_story_brief_stage.py` | 65 | domain service | F:news_story_brief_stage_instructions<br>F:news_story_brief_prompt_text_hash<br>F:build_news_story_brief_stage | `parallax.domains.news_intel.services.news_item_brief_stage`<br>`parallax.domains.news_intel.services.news_story_brief_input`<br>`parallax.domains.news_intel.types.news_item_brief` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_story_identity.py` | 443 | domain service | F:build_news_story_identity<br>F:_normalized_material_title<br>F:_material_tokens | `parallax.domains.news_intel.types.news_story_identity`<br>`parallax.domains.news_intel.types.text_normalization` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_story_similarity.py` | 197 | domain service | C:NewsSimilarityEvidence<br>F:decide_news_story_similarity<br>F:_exact_duplicate | — | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/news_token_mentions.py` | 143 | domain service | F:build_news_token_mentions<br>F:_status_from_identity<br>F:_mention | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.types.news_extraction`<br>`parallax.domains.token_intel.interfaces` | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/opennews_provider_signal.py` | 96 | domain service | F:provider_signal_from_opennews_payload<br>F:provider_token_impacts_from_opennews_payload<br>F:_direction | — | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/source_authority.py` | 170 | domain service | C:SourceAuthorityDecision<br>F:validate_source_authority<br>F:_normalized_set | — | 1 |
| `domains/news_intel/services` | `src/parallax/domains/news_intel/services/source_quality_projection.py` | 222 | domain service | F:quality_score<br>F:quality_status<br>F:build_source_quality_row | — | 1 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/__init__.py` | 42 | package/export | C:NewsSourceConfig<br>C:NormalizedNewsItem | `parallax.domains.news_intel.types.source_classification` | 2 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/content_classification.py` | 28 | type/contract | C:NewsContentClassification | — | 1 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_canonical_identity.py` | 197 | type/contract | C:CanonicalIdentity<br>F:provider_global_article_key<br>F:canonical_identity_for_observation | `parallax.domains.news_intel.types.news_material_identity`<br>`parallax.domains.news_intel.types.news_url_identity`<br>`parallax.domains.news_intel.types.text_normalization` | 1 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_extraction.py` | 60 | type/contract | C:NewsEntity<br>C:NewsTokenMention<br>C:NewsFactCandidate | — | 4 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_item_agent_admission.py` | 82 | type/contract | C:NewsItemAgentAdmissionContext<br>C:NewsItemAgentAdmission<br>F:_optional_context_mapping_list | `parallax.domains.news_intel._constants` | 5 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_item_brief.py` | 277 | type/contract | C:NewsItemBriefSideView<br>C:AffectedEntity<br>C:TransmissionPath | `parallax.domains.news_intel._constants` | 10 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_item_brief_contract.py` | 43 | type/contract | F:current_news_item_brief_sql_predicate<br>F:_sql_literal | `parallax.domains.news_intel._constants` | 1 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_market_scope.py` | 43 | type/contract | C:NewsMarketScope | `parallax.domains.news_intel._constants` | 3 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_material_identity.py` | 79 | type/contract | F:material_title_fingerprint<br>F:material_title_is_eligible<br>F:provider_symbol_set | `parallax.domains.news_intel.types.text_normalization` | 2 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_page_search.py` | 80 | type/contract | F:build_news_page_search_text<br>F:_optional_json_object<br>F:_required_json_mapping | — | 2 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_source_role_rank.py` | 44 | type/contract | F:source_role_rank<br>F:source_role_rank_case_sql | `parallax.domains.news_intel.types.source_classification` | 2 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_story_brief.py` | 111 | type/contract | C:NewsStoryBriefMember<br>C:NewsStoryBriefInputPacket<br>C:NewsStoryBriefAgentConfig | `parallax.domains.news_intel._constants`<br>`parallax.domains.news_intel.types.news_item_brief`<br>`parallax.platform.agent_hashing` | 7 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_story_identity.py` | 17 | type/contract | C:NewsStoryIdentity | — | 3 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/news_url_identity.py` | 213 | type/contract | F:url_identity_kind<br>C:PublicUrlIdentityPolicy<br>F:public_url_identity_policy | `parallax.domains.news_intel.types.text_normalization` | 3 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/source_classification.py` | 88 | type/contract | F:normalize_string_tuple<br>F:_normalize_parts | — | 3 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/source_provider.py` | 75 | type/contract | C:NewsSourceSnapshot<br>C:NewsSourceHttpCache<br>C:NewsProviderObservation | — | 3 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/source_quality_policy.py` | 19 | type/contract | F:window_ms_for_label | — | 2 |
| `domains/news_intel/types` | `src/parallax/domains/news_intel/types/text_normalization.py` | 174 | type/contract | F:clean_news_text<br>F:canonicalize_url<br>F:title_fingerprint | — | 6 |
| `domains/notifications/__init__.py` | `src/parallax/domains/notifications/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/notifications/repositories` | `src/parallax/domains/notifications/repositories/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/notifications/repositories` | `src/parallax/domains/notifications/repositories/notification_repository.py` | 1139 | repository | C:NotificationInsertOutcome<br>C:NotificationRepository<br>F:_json | — | 3 |
| `domains/notifications/runtime` | `src/parallax/domains/notifications/runtime/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/notifications/runtime` | `src/parallax/domains/notifications/runtime/notification_delivery.py` | 246 | module | C:AppriseNotificationAdapter<br>C:PushDeerNotificationAdapter<br>C:DeliveryClaim | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.notifications.runtime.notification_runtime_settings` | 1 |
| `domains/notifications/runtime` | `src/parallax/domains/notifications/runtime/notification_runtime_settings.py` | 19 | module | F:positive_worker_setting_int<br>F:positive_int | — | 2 |
| `domains/notifications/runtime` | `src/parallax/domains/notifications/runtime/notification_worker.py` | 206 | worker | C:NotificationProcessResult<br>C:NotificationWorker<br>F:_now_ms | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.notifications.runtime.notification_runtime_settings` | 1 |
| `domains/notifications/services` | `src/parallax/domains/notifications/services/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/notifications/services` | `src/parallax/domains/notifications/services/notification_rules.py` | 899 | domain service | C:NotificationRuleEngine<br>F:_cooldown_bucket<br>F:_required_nonnegative_int | `parallax.platform.config.settings`<br>`parallax.domains.notifications.types` | 1 |
| `domains/notifications/types.py` | `src/parallax/domains/notifications/types.py` | 25 | type/contract | C:NotificationCandidate | — | 2 |
| `domains/token_intel/__init__.py` | `src/parallax/domains/token_intel/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/token_intel/_constants.py` | `src/parallax/domains/token_intel/_constants.py` | 25 | module | — | — | 14 |
| `domains/token_intel/interfaces.py` | `src/parallax/domains/token_intel/interfaces.py` | 102 | port/interface | C:TokenIdentityLookupResult<br>C:TokenIdentityLookup | `parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.queries.event_token_projection_query`<br>`parallax.domains.token_intel.read_models.token_target_stage_builder` | 19 |
| `domains/token_intel/queries` | `src/parallax/domains/token_intel/queries/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/token_intel/queries` | `src/parallax/domains/token_intel/queries/event_rebuild_query.py` | 32 | query | C:EventRebuildQuery<br>F:_required_nonnegative_int | — | 1 |
| `domains/token_intel/queries` | `src/parallax/domains/token_intel/queries/event_token_projection_query.py` | 210 | query | C:EventTokenProjectionQuery<br>F:_project_token_resolution<br>F:_resolution_symbol | `parallax.domains.asset_market.interfaces` | 1 |
| `domains/token_intel/queries` | `src/parallax/domains/token_intel/queries/search_events_query.py` | 611 | query | C:SearchEventsQuery<br>F:_candidate<br>F:_hit | `parallax.domains.evidence.interfaces`<br>`parallax.domains.token_intel.interfaces` | 2 |
| `domains/token_intel/queries` | `src/parallax/domains/token_intel/queries/stocks_radar_query.py` | 110 | query | C:StocksRadarQuery | `parallax.domains.token_intel.interfaces` | 1 |
| `domains/token_intel/queries` | `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py` | 940 | query | C:TokenRadarSourceEdgeRequest<br>C:TokenRadarFeatureSourceRequest<br>C:TokenRadarRankSourceQuery | `parallax.domains.token_intel._constants` | 2 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/asset_flow_service.py` | 332 | module | C:AssetFlowService<br>F:_public_row<br>F:_hydrate_profiles | `parallax.domains.token_intel.interfaces` | 6 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/search_agent_brief.py` | 75 | module | F:build_topic_agent_brief<br>F:_author_posts<br>F:_dict | — | 1 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/search_inspect_service.py` | 177 | module | C:SearchInspectService<br>F:_result_kind<br>F:_resolver_confidence | `parallax.domains.token_intel.read_models.search_agent_brief`<br>`parallax.domains.token_intel.read_models.search_service`<br>`parallax.domains.token_intel.read_models.token_case_service` | 1 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/search_service.py` | 353 | module | C:SearchPage<br>C:SearchCursorError<br>C:SearchScopeError | `parallax.domains.token_intel.services.query_parser`<br>`parallax.domains.token_intel.services.search_aliases`<br>`parallax.domains.token_intel.read_models.asset_flow_service` | 3 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/stocks_radar_service.py` | 126 | module | C:StocksRadarService<br>F:_public_row<br>F:_unavailable_quote | `parallax.domains.token_intel.queries.stocks_radar_query`<br>`parallax.domains.token_intel.read_models.asset_flow_service` | 1 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/token_case_service.py` | 197 | module | C:TokenCaseTargetNotFound<br>C:TokenCaseInvalidScope<br>F:normalize_token_case_scope | `parallax.domains.token_intel.read_models.token_target_posts_service`<br>`parallax.domains.token_intel.read_models.token_target_social_timeline_service` | 2 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/token_target_cursor.py` | 21 | module | C:TokenTargetCursorError<br>F:encode_target_cursor<br>F:decode_target_cursor | — | 3 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/token_target_post_serializer.py` | 71 | module | F:token_target_post_payload<br>F:_reference | `parallax.domains.asset_market.interfaces`<br>`parallax.domains.token_intel.scoring.post_text_quality` | 2 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/token_target_posts_service.py` | 118 | module | C:TokenTargetPostsCursorError<br>C:TokenTargetPostsRangeError<br>C:TokenTargetPostsSortError | `parallax.domains.token_intel.read_models.asset_flow_service`<br>`parallax.domains.token_intel.read_models.token_target_cursor`<br>`parallax.domains.token_intel.read_models.token_target_post_serializer` | 2 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/token_target_social_timeline_service.py` | 262 | module | C:TokenTargetSocialTimelineScopeError<br>C:TokenTargetSocialTimelineWindowError<br>C:TokenTargetSocialTimelineService | `parallax.domains.asset_market.interfaces`<br>`parallax.domains.token_intel.read_models.asset_flow_service`<br>`parallax.domains.token_intel.read_models.token_target_cursor` | 2 |
| `domains/token_intel/read_models` | `src/parallax/domains/token_intel/read_models/token_target_stage_builder.py` | 239 | module | C:TokenTargetStageBuild<br>F:build_token_target_stages<br>F:_stage | `parallax.domains.asset_market.interfaces` | 3 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/intent_resolution_repository.py` | 247 | repository | C:IntentResolutionRepository<br>F:_payload<br>F:token_intent_resolution_id | `parallax.domains.token_intel.types.token_fact_inputs` | 2 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/projection_repository.py` | 321 | repository | C:ProjectionRepository<br>F:_id<br>F:_now_ms | `parallax.domains.token_intel.interfaces` | 3 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/signal_repository.py` | 199 | repository | C:SignalAlert<br>C:SignalRepository<br>F:_id | — | 1 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_evidence_repository.py` | 194 | repository | C:TokenEvidenceRepository<br>F:_payload<br>F:_unique_ids | `parallax.domains.token_intel.types.token_fact_inputs` | 2 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py` | 181 | repository | C:TokenIntentLookupRepository<br>F:_transaction<br>F:_cursor_rowcount | — | 2 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_intent_repository.py` | 231 | repository | C:TokenIntentRepository<br>F:_payload<br>F:_evidence_links | `parallax.domains.token_intel.types.token_fact_inputs` | 2 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py` | 1142 | repository | F:dirty_kind_flags<br>F:dirty_payload_hash<br>C:TokenRadarDirtyTargetRepository | `parallax.domains.token_intel._constants`<br>`parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.queue_terminal` | 1 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_radar_rank_source_repository.py` | 100 | repository | C:TokenRadarRankSourceRepository<br>F:_transaction<br>F:_run_repository_write | `parallax.domains.token_intel.queries.token_radar_rank_source_query` | 1 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_radar_repository.py` | 1521 | repository | C:PublicationResult<br>C:TokenRadarRepository<br>F:_runtime_row_payload | `parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.scoring.factor_snapshot_contract`<br>`parallax.domains.token_intel.types.token_radar_payload_hash` | 2 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py` | 623 | repository | F:source_dirty_event_payload_hash<br>C:TokenRadarSourceDirtyEventRepository<br>F:_source_event_records | `parallax.domains.token_intel._constants`<br>`parallax.platform.current_read_model_payload_hash`<br>`parallax.platform.db.queue_terminal` | 2 |
| `domains/token_intel/repositories` | `src/parallax/domains/token_intel/repositories/token_target_repository.py` | 481 | repository | C:TokenTargetRepository<br>F:_public_row<br>F:_target_identity_payload | `parallax.domains.token_intel.interfaces` | 1 |
| `domains/token_intel/runtime` | `src/parallax/domains/token_intel/runtime/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/token_intel/runtime` | `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py` | 157 | module | F:rebuild_recent_token_intents<br>F:_rebuild_event_token_intents<br>F:_surfaces | `parallax.domains.asset_market.interfaces`<br>`parallax.domains.evidence.interfaces`<br>`parallax.domains.token_intel._constants` | 1 |
| `domains/token_intel/runtime` | `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py` | 558 | worker | C:TokenRadarProjectionWorker<br>F:_now_ms<br>F:_idle_result | `parallax.app.runtime.worker_base`<br>`parallax.app.runtime.worker_result`<br>`parallax.domains.token_intel._constants` | 2 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/__init__.py` | 15 | package/export | — | `parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.scoring.factor_snapshot` | 0 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/baseline_scoring.py` | 108 | scoring | F:token_baseline_v2<br>F:baseline_health<br>F:robust_z_score | — | 1 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/cross_section_normalizer.py` | 69 | scoring | F:rank_within_cohort<br>F:rank_factors_within_cohort<br>F:weighted_rank_score | — | 1 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/diffusion_health.py` | 154 | scoring | F:text_fingerprint<br>F:diffusion_health<br>F:_top_authors | `parallax.domains.token_intel.scoring.social_signal_features` | 1 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/factor_cohort.py` | 42 | scoring | F:is_active_cohort_member | — | 1 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/factor_diagnostics.py` | 88 | scoring | F:factor_distribution_report<br>F:_number<br>F:_share_at_100 | `parallax.domains.token_intel.interfaces` | 1 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/factor_snapshot.py` | 878 | scoring | F:build_token_factor_snapshot<br>F:_social_heat_family<br>F:_social_propagation_family | `parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.scoring.scoring_common` | 2 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/factor_snapshot_contract.py` | 202 | scoring | F:require_token_factor_snapshot<br>F:is_token_factor_snapshot<br>F:_required_dict | `parallax.domains.token_intel._constants` | 3 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/post_text_quality.py` | 93 | scoring | F:post_text_features<br>F:post_quality_score | `parallax.domains.token_intel.scoring.scoring_common` | 2 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/scoring_common.py` | 84 | scoring | F:score_payload<br>F:apply_risk_caps<br>F:contribution | — | 3 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/social_signal_features.py` | 152 | scoring | F:source_weighted_effective_authors<br>F:time_to_nth_independent_author_ms<br>F:public_followup_author_count | — | 2 |
| `domains/token_intel/scoring` | `src/parallax/domains/token_intel/scoring/token_radar_feature_builder.py` | 382 | scoring | C:RadarFeatureSet<br>F:build_radar_features<br>F:_attention | `parallax.domains.token_intel.scoring.baseline_scoring`<br>`parallax.domains.token_intel.scoring.diffusion_health`<br>`parallax.domains.token_intel.scoring.post_text_quality` | 1 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/__init__.py` | 0 | package/export | — | — | 0 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/atomic_mention.py` | 70 | domain service | F:tweet_quality<br>F:mention_confidence_from_status<br>F:_select_followers | — | 2 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/deterministic_token_resolver.py` | 480 | domain service | C:DeterministicTokenResolver<br>F:_market_dominant_asset<br>F:_candidate_ids | `parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.types.token_fact_inputs` | 2 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/query_parser.py` | 100 | domain service | C:SearchIntent<br>F:parse_search_query<br>F:_parse_chain_prefixed_ca | `parallax.domains.evidence.interfaces` | 2 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/search_aliases.py` | 100 | domain service | F:canonical_symbol_for_query<br>F:fuzzy_canonical_symbol_for_query<br>F:target_symbols_for_or_query | `parallax.domains.token_intel.services.query_parser` | 1 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/token_evidence_builder.py` | 176 | domain service | F:build_token_evidence<br>F:_from_ca_entity<br>F:_from_symbol_entity | `parallax.domains.evidence.interfaces`<br>`parallax.domains.token_intel.types.token_fact_inputs` | 2 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/token_intent_builder.py` | 204 | domain service | F:build_token_intents<br>F:_intent<br>F:_intent_key | `parallax.domains.token_intel.types.token_fact_inputs` | 2 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/token_intent_resolver.py` | 135 | domain service | C:TokenIntentResolver<br>F:_mention_keys<br>F:_cex_pricefeed_id | `parallax.domains.token_intel.services.deterministic_token_resolver`<br>`parallax.domains.token_intel.types.token_fact_inputs` | 3 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/token_radar_projection.py` | 3090 | domain service | C:TokenRadarProjectionWindowError<br>C:TokenRadarProjection<br>F:_cohort_rank_status | `parallax.domains.narrative_intel.interfaces`<br>`parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.queries.token_radar_rank_source_query` | 2 |
| `domains/token_intel/services` | `src/parallax/domains/token_intel/services/token_resolution_refresh.py` | 130 | domain service | F:reprocess_recent_token_intents<br>F:_reprocess_recent_token_intents<br>F:deferred_token_radar_projection | `parallax.domains.token_intel._constants`<br>`parallax.domains.token_intel.services.token_intent_resolver` | 3 |
| `domains/token_intel/types` | `src/parallax/domains/token_intel/types/__init__.py` | 17 | package/export | — | `parallax.domains.token_intel.types.token_fact_inputs` | 0 |
| `domains/token_intel/types` | `src/parallax/domains/token_intel/types/token_fact_inputs.py` | 85 | type/contract | C:TokenEvidenceInput<br>C:TokenIntentEvidenceLink<br>C:TokenIntentInput | — | 8 |
| `domains/token_intel/types` | `src/parallax/domains/token_intel/types/token_radar_payload_hash.py` | 81 | type/contract | F:canonical_token_radar_payload<br>F:stable_token_radar_payload_hash<br>F:_canonical_value | `parallax.platform.current_read_model_payload_hash` | 2 |
| `domains/watchlist_intel/__init__.py` | `src/parallax/domains/watchlist_intel/__init__.py` | 1 | package/export | — | — | 0 |
| `domains/watchlist_intel/repositories` | `src/parallax/domains/watchlist_intel/repositories/__init__.py` | 3 | package/export | — | `parallax.domains.watchlist_intel.repositories.watchlist_intel_repository` | 0 |
| `domains/watchlist_intel/repositories` | `src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py` | 412 | repository | C:WatchlistIntelRepository<br>F:_decode_timeline_row<br>F:_decode_handle_overview_row | `parallax.domains.evidence.interfaces`<br>`parallax.domains.token_intel.interfaces`<br>`parallax.domains.watchlist_intel.types` | 2 |
| `domains/watchlist_intel/services` | `src/parallax/domains/watchlist_intel/services/__init__.py` | 6 | package/export | — | `parallax.domains.watchlist_intel.services.watchlist_read_service` | 0 |
| `domains/watchlist_intel/services` | `src/parallax/domains/watchlist_intel/services/watchlist_read_service.py` | 117 | domain service | C:WatchlistReadWindowConfig<br>C:WatchlistHandleReadService<br>F:_configured_handle | `parallax.domains.watchlist_intel.types` | 2 |
| `domains/watchlist_intel/types` | `src/parallax/domains/watchlist_intel/types/__init__.py` | 57 | package/export | C:WatchlistTimelineCursorError<br>F:normalize_watchlist_handle<br>F:encode_watchlist_timeline_cursor | — | 3 |
| `integrations/__init__.py` | `src/parallax/integrations/__init__.py` | 0 | package/export | — | — | 0 |
| `integrations/binance` | `src/parallax/integrations/binance/__init__.py` | 1 | package/export | — | — | 0 |
| `integrations/binance` | `src/parallax/integrations/binance/cex_profile_client.py` | 91 | provider adapter | C:BinanceCexProfileClient<br>F:_symbol<br>F:_name | — | 1 |
| `integrations/binance` | `src/parallax/integrations/binance/usdm_futures_client.py` | 349 | provider adapter | C:BinanceUsdmFuturesClientError<br>C:BinanceUsdmRoute<br>C:BinanceUsdmTicker24hr | — | 2 |
| `integrations/binance` | `src/parallax/integrations/binance/web3_token_client.py` | 172 | provider adapter | C:BinanceWeb3TokenMetadata<br>C:BinanceWeb3TokenClient<br>F:binance_chain_id_for_domain_chain | — | 1 |
| `integrations/gmgn` | `src/parallax/integrations/gmgn/__init__.py` | 0 | package/export | — | — | 0 |
| `integrations/gmgn` | `src/parallax/integrations/gmgn/direct_ws.py` | 216 | provider adapter | C:UpstreamIdleTimeoutError<br>F:build_gmgn_ws_url<br>F:build_subscribe_message | — | 1 |
| `integrations/gmgn` | `src/parallax/integrations/gmgn/directory_client.py` | 167 | provider adapter | C:GmgnDirectoryError<br>C:GmgnDirectoryEntry<br>C:GmgnDirectoryPage | — | 1 |
| `integrations/gmgn` | `src/parallax/integrations/gmgn/openapi_client.py` | 453 | provider adapter | C:GmgnTokenInfo<br>C:GmgnTokenKlineCandle<br>C:GmgnTokenInfoLookup | — | 2 |
| `integrations/gmgn` | `src/parallax/integrations/gmgn/openapi_gateway.py` | 235 | provider adapter | C:GmgnOpenApiRoute<br>C:GmgnOpenApiGateway<br>C:_WeightedLeakyBucket | `parallax.integrations.gmgn.openapi_client` | 1 |
| `integrations/macrodata` | `src/parallax/integrations/macrodata/__init__.py` | 17 | package/export | — | `parallax.integrations.macrodata.runner` | 1 |
| `integrations/macrodata` | `src/parallax/integrations/macrodata/runner.py` | 326 | provider adapter | C:MacrodataBundleRunResult<br>C:MacrodataBundleRunner<br>C:MacrodataRunnerError | — | 2 |
| `integrations/model_execution` | `src/parallax/integrations/model_execution/__init__.py` | 0 | package/export | — | — | 0 |
| `integrations/model_execution` | `src/parallax/integrations/model_execution/execution_gateway.py` | 845 | provider adapter | C:_LaneState<br>C:_RateLimitState<br>C:_RateLimitReservationResult | `parallax.integrations.model_execution.output_schema`<br>`parallax.integrations.model_execution.structured_json_strategy`<br>`parallax.integrations.model_execution.usage` | 1 |
| `integrations/model_execution` | `src/parallax/integrations/model_execution/news_item_brief_agent_client.py` | 125 | provider adapter | C:LiteLLMNewsItemBriefClient<br>F:_coerce_news_item_brief_payload | `parallax.domains.news_intel.services.news_item_brief_stage`<br>`parallax.domains.news_intel.services.news_story_brief_stage`<br>`parallax.domains.news_intel.types.news_item_brief` | 1 |
| `integrations/model_execution` | `src/parallax/integrations/model_execution/output_schema.py` | 107 | provider adapter | C:StrictJsonOutputSchema<br>F:_strip_defs<br>F:_coerce_dict_additional_properties_to_false | — | 3 |
| `integrations/model_execution` | `src/parallax/integrations/model_execution/structured_json_strategy.py` | 164 | provider adapter | C:StructuredOutputContext<br>C:StructuredOutputOutcome<br>C:ChatJsonObjectStrategy | `parallax.integrations.model_execution.output_schema`<br>`parallax.integrations.model_execution.usage`<br>`parallax.platform.agent_capabilities` | 1 |
| `integrations/model_execution` | `src/parallax/integrations/model_execution/usage.py` | 49 | provider adapter | F:_json_safe<br>F:extract_model_usage | — | 2 |
| `integrations/news_feeds` | `src/parallax/integrations/news_feeds/__init__.py` | 1 | package/export | — | — | 0 |
| `integrations/news_feeds` | `src/parallax/integrations/news_feeds/cryptopanic_client.py` | 220 | provider adapter | C:CryptopanicFeedClient<br>F:_parse_options<br>F:_post_to_feed_entry | `parallax.integrations.news_feeds.feed_client` | 2 |
| `integrations/news_feeds` | `src/parallax/integrations/news_feeds/feed_client.py` | 107 | provider adapter | C:FeedFetchResult<br>C:FeedClient<br>F:_required_positive_int | — | 4 |
| `integrations/news_feeds` | `src/parallax/integrations/news_feeds/opennews_client.py` | 555 | provider adapter | C:_OpenNewsPostJson<br>C:OpenNewsFeedClient<br>F:_default_post_json | `parallax.domains.news_intel.services.opennews_provider_signal`<br>`parallax.integrations.news_feeds.feed_client` | 2 |
| `integrations/news_feeds` | `src/parallax/integrations/news_feeds/provider_registry.py` | 228 | provider adapter | C:NewsFeedClient<br>C:RegistryNewsFeedProvider<br>C:OpenNewsClient | `parallax.integrations.news_feeds.cryptopanic_client`<br>`parallax.integrations.news_feeds.feed_client`<br>`parallax.integrations.news_feeds.opennews_client` | 1 |
| `integrations/okx` | `src/parallax/integrations/okx/__init__.py` | 0 | package/export | — | — | 0 |
| `integrations/okx` | `src/parallax/integrations/okx/chains.py` | 22 | provider adapter | — | — | 1 |
| `integrations/okx` | `src/parallax/integrations/okx/dex_client.py` | 264 | provider adapter | C:OkxDexClient<br>F:_candidate_from_row<br>F:_price_from_row | `parallax.integrations.okx.http_utils`<br>`parallax.integrations.okx.models` | 2 |
| `integrations/okx` | `src/parallax/integrations/okx/dex_ws_client.py` | 606 | provider adapter | C:OkxDexWsClientError<br>C:_OkxDexWsMissingPong<br>C:_OkxDexWsReconnectFailed | `parallax.integrations.okx.dex_client` | 1 |
| `integrations/okx` | `src/parallax/integrations/okx/http_utils.py` | 56 | provider adapter | C:OkxClientError<br>C:OkxPaymentRequiredError<br>F:items_from_response | — | 2 |
| `integrations/okx` | `src/parallax/integrations/okx/models.py` | 42 | type/contract | C:OkxCandle<br>C:OkxDexTokenCandidate<br>C:OkxDexTokenPrice | — | 1 |
| `platform/__init__.py` | `src/parallax/platform/__init__.py` | 0 | package/export | — | — | 0 |
| `platform/agent_capabilities.py` | `src/parallax/platform/agent_capabilities.py` | 95 | module | C:AgentProviderFamily<br>F:_normalized<br>C:AgentRequestOptions | — | 2 |
| `platform/agent_execution.py` | `src/parallax/platform/agent_execution.py` | 366 | module | C:AgentExecutionErrorClass<br>C:AgentExecutionStatus<br>C:AgentCircuitBreakerPolicy | `parallax.platform.agent_capabilities`<br>`parallax.platform.agent_hashing` | 9 |
| `platform/agent_hashing.py` | `src/parallax/platform/agent_hashing.py` | 65 | module | F:_json_ready<br>F:json_sha256<br>F:text_sha256 | — | 11 |
| `platform/agent_knowledge.py` | `src/parallax/platform/agent_knowledge.py` | 95 | module | C:AgentKnowledgeRef<br>C:AgentKnowledgeCatalog<br>F:render_agent_instructions | — | 2 |
| `platform/cancellation.py` | `src/parallax/platform/cancellation.py` | 17 | module | F:cancellation_reason<br>F:is_worker_hard_timeout_cancelled | — | 2 |
| `platform/config` | `src/parallax/platform/config/__init__.py` | 0 | package/export | — | — | 0 |
| `platform/config` | `src/parallax/platform/config/news_provider_types.py` | 5 | configuration | — | — | 3 |
| `platform/config` | `src/parallax/platform/config/settings.py` | 1957 | configuration | C:ApiConfig<br>C:PostgresConfig<br>C:StorageConfig | `parallax.platform.paths.runtime_paths` | 23 |
| `platform/current_read_model_payload_hash.py` | `src/parallax/platform/current_read_model_payload_hash.py` | 102 | module | F:stable_current_payload_hash<br>F:stable_dirty_target_payload_hash<br>F:_validate_payload_hash_keys | — | 16 |
| `platform/db` | `src/parallax/platform/db/__init__.py` | 0 | package/export | — | — | 0 |
| `platform/db` | `src/parallax/platform/db/alembic/env.py` | 62 | DB infrastructure | F:_database_url<br>F:_sqlalchemy_database_url<br>F:run_migrations_offline | `parallax.platform.config.settings`<br>`parallax.platform.db.postgres_client` | 0 |
| `platform/db` | `src/parallax/platform/db/json_safety.py` | 19 | DB infrastructure | F:postgres_safe_json<br>F:postgres_safe_text | — | 11 |
| `platform/db` | `src/parallax/platform/db/postgres_audit.py` | 351 | DB infrastructure | C:PostgresOperationalAudit<br>C:PostgresQueryAudit<br>C:ProjectionValidationAudit | `parallax.platform.db.postgres_migrations` | 2 |
| `platform/db` | `src/parallax/platform/db/postgres_client.py` | 215 | DB infrastructure | F:with_password_from_file<br>F:local_docker_host_dsn<br>F:create_pool | — | 9 |
| `platform/db` | `src/parallax/platform/db/postgres_migrations.py` | 23 | DB infrastructure | F:alembic_config<br>F:upgrade_head<br>F:latest_migration_version | — | 5 |
| `platform/db` | `src/parallax/platform/db/queue_terminal.py` | 545 | DB infrastructure | F:terminalize_source_row<br>F:inspect_terminal_events<br>F:list_terminal_event_ids | `parallax.platform.db.json_safety` | 12 |
| `platform/logging` | `src/parallax/platform/logging/__init__.py` | 0 | package/export | — | — | 0 |
| `platform/logging` | `src/parallax/platform/logging/setup.py` | 32 | module | F:setup_logging | — | 1 |
| `platform/paths` | `src/parallax/platform/paths/__init__.py` | 0 | package/export | — | — | 0 |
| `platform/paths` | `src/parallax/platform/paths/runtime_paths.py` | 24 | module | F:app_home<br>F:app_log_path<br>F:config_path | — | 3 |

## Alembic 历史迁移（逐文件，共 184 个）

> 184 个迁移、20,835 LOC。这里保留逐文件索引；架构审计只把 `head -> current schema` 的重放契约视为约束，不把旧 revision 的实现风格复制进新代码。

| 文件 | LOC | revision | down_revision |
|---|---:|---|---|
| `src/parallax/platform/db/alembic/versions/20260506_0001_initial_postgresql.py` | 740 | `20260506_0001` | `—` |
| `src/parallax/platform/db/alembic/versions/20260506_0002_postgres_queue_claims.py` | 46 | `20260506_0002` | `20260506_0001` |
| `src/parallax/platform/db/alembic/versions/20260506_0003_enrichment_stale_running_claims.py` | 32 | `20260506_0003` | `20260506_0002` |
| `src/parallax/platform/db/alembic/versions/20260506_0004_projection_operations.py` | 209 | `20260506_0004` | `20260506_0003` |
| `src/parallax/platform/db/alembic/versions/20260506_0005_asset_identity_resolution.py` | 401 | `20260506_0005` | `20260506_0004` |
| `src/parallax/platform/db/alembic/versions/20260507_0006_asset_market_sync_indexes.py` | 31 | `20260507_0006` | `20260506_0005` |
| `src/parallax/platform/db/alembic/versions/20260507_0007_token_radar_v3_intents.py` | 301 | `20260507_0007` | `20260507_0006` |
| `src/parallax/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py` | 268 | `20260507_0008` | `20260507_0007` |
| `src/parallax/platform/db/alembic/versions/20260507_0009_token_discovery_results.py` | 70 | `20260507_0009` | `20260507_0008` |
| `src/parallax/platform/db/alembic/versions/20260507_0010_agents_sdk_model_run_audit.py` | 55 | `20260507_0010` | `20260507_0009` |
| `src/parallax/platform/db/alembic/versions/20260508_0011_event_price_observations.py` | 78 | `20260508_0011` | `20260507_0010` |
| `src/parallax/platform/db/alembic/versions/20260508_0012_prune_legacy_token_radar_projection.py` | 46 | `20260508_0012` | `20260508_0011` |
| `src/parallax/platform/db/alembic/versions/20260508_0013_retire_legacy_token_resolutions.py` | 27 | `20260508_0013` | `20260508_0012` |
| `src/parallax/platform/db/alembic/versions/20260508_0014_prune_token_radar_v6_projection.py` | 46 | `20260508_0014` | `20260508_0013` |
| `src/parallax/platform/db/alembic/versions/20260508_0015_signal_pulse_agent_hard_cut.py` | 224 | `20260508_0015` | `20260508_0014` |
| `src/parallax/platform/db/alembic/versions/20260509_0016_account_profile_gmgn_directory_columns.py` | 41 | `20260509_0016` | `20260508_0015` |
| `src/parallax/platform/db/alembic/versions/20260509_0017_demote_search_only_registry_assets.py` | 91 | `20260509_0017` | `20260509_0016` |
| `src/parallax/platform/db/alembic/versions/20260509_0018_demote_search_tail_candidate_audit_refs.py` | 85 | `20260509_0018` | `20260509_0017` |
| `src/parallax/platform/db/alembic/versions/20260509_0019_demote_symbol_search_tail_targets.py` | 89 | `20260509_0019` | `20260509_0018` |
| `src/parallax/platform/db/alembic/versions/20260509_0020_sweep_symbol_search_tail_assets.py` | 89 | `20260509_0020` | `20260509_0019` |
| `src/parallax/platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py` | 207 | `20260510_0021` | `20260509_0020` |
| `src/parallax/platform/db/alembic/versions/20260510_0022_token_radar_factor_snapshot_hard_cut.py` | 66 | `20260510_0022` | `20260510_0021` |
| `src/parallax/platform/db/alembic/versions/20260510_0023_drop_signal_pulse_legacy_json_fields.py` | 26 | `20260510_0023` | `20260510_0022` |
| `src/parallax/platform/db/alembic/versions/20260511_0024_price_observation_field_indexes.py` | 109 | `20260511_0024` | `20260510_0023` |
| `src/parallax/platform/db/alembic/versions/20260511_0025_token_radar_production_read_models.py` | 112 | `20260511_0025` | `20260511_0024` |
| `src/parallax/platform/db/alembic/versions/20260511_0026_token_factor_eval_diagnostics.py` | 91 | `20260511_0026` | `20260511_0025` |
| `src/parallax/platform/db/alembic/versions/20260511_0027_prune_legacy_pulse_factor_snapshots.py` | 31 | `20260511_0027` | `20260511_0026` |
| `src/parallax/platform/db/alembic/versions/20260511_0028_prune_gmgn_payload_market_data.py` | 89 | `20260511_0028` | `20260511_0027` |
| `src/parallax/platform/db/alembic/versions/20260511_0029_anchor_live_hard_cut.py` | 70 | `20260511_0029` | `20260511_0028` |
| `src/parallax/platform/db/alembic/versions/20260511_0030_prune_pulse_snapshots_without_market.py` | 32 | `20260511_0030` | `20260511_0029` |
| `src/parallax/platform/db/alembic/versions/20260512_0031_prune_legacy_pulse_factor_contracts.py` | 31 | `20260512_0031` | `20260511_0030` |
| `src/parallax/platform/db/alembic/versions/20260512_0032_search_v2_hard_cut.py` | 51 | `20260512_0032` | `20260512_0031` |
| `src/parallax/platform/db/alembic/versions/20260512_0033_reconcile_search_v2_local_revision.py` | 16 | `20260512_0033` | `20260512_0032` |
| `src/parallax/platform/db/alembic/versions/20260512_0034_us_equity_symbol_universe.py` | 49 | `20260512_0034` | `20260512_0033` |
| `src/parallax/platform/db/alembic/versions/20260513_0035_asset_profiles.py` | 58 | `20260513_0035` | `20260512_0034` |
| `src/parallax/platform/db/alembic/versions/20260513_0036_token_radar_kappa_cqrs_hard_cut.py` | 344 | `20260513_0036` | `20260513_0035` |
| `src/parallax/platform/db/alembic/versions/20260514_0037_unified_agent_runtime_phase0b.py` | 142 | `20260514_0037` | `20260513_0036` |
| `src/parallax/platform/db/alembic/versions/20260514_0038_pulse_agent_runtime_eval_ledger.py` | 107 | `20260514_0038` | `20260514_0037` |
| `src/parallax/platform/db/alembic/versions/20260514_0039_reconcile_local_agent_harness_revision.py` | 16 | `20260514_0039` | `20260514_0038` |
| `src/parallax/platform/db/alembic/versions/20260514_0040_repair_pulse_agent_job_cooldown.py` | 39 | `20260514_0040` | `20260514_0039` |
| `src/parallax/platform/db/alembic/versions/20260514_0041_pulse_worker_edge_notifications_hard_cut.py` | 184 | `20260514_0041` | `20260514_0040` |
| `src/parallax/platform/db/alembic/versions/20260514_0042_harden_pulse_agent_run_outcome.py` | 18 | `20260514_0042` | `20260514_0041` |
| `src/parallax/platform/db/alembic/versions/20260514_0043_token_radar_listed_lookup_index.py` | 32 | `20260514_0043` | `20260514_0042` |
| `src/parallax/platform/db/alembic/versions/20260514_0044_pulse_runtime_hash_history.py` | 45 | `20260514_0044` | `20260514_0043` |
| `src/parallax/platform/db/alembic/versions/20260514_0045_watchlist_handle_intel.py` | 96 | `20260514_0045` | `20260514_0044` |
| `src/parallax/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py` | 177 | `20260515_0046` | `20260514_0045` |
| `src/parallax/platform/db/alembic/versions/20260516_0047_market_ticks_gmgn_dex_quote_provider.py` | 30 | `20260516_0047` | `20260515_0046` |
| `src/parallax/platform/db/alembic/versions/20260516_0048_agent_safety_net_audit.py` | 52 | `20260516_0048` | `20260516_0047` |
| `src/parallax/platform/db/alembic/versions/20260516_0049_enriched_event_async_backfill.py` | 89 | `20260516_0049` | `20260516_0048` |
| `src/parallax/platform/db/alembic/versions/20260516_0050_drop_legacy_asset_stack.py` | 78 | `20260516_0050` | `20260516_0049` |
| `src/parallax/platform/db/alembic/versions/20260516_0051_pulse_agent_desk_redesign.py` | 60 | `20260516_0051` | `20260516_0050` |
| `src/parallax/platform/db/alembic/versions/20260517_0052_token_profile_current.py` | 68 | `20260517_0052` | `20260516_0051` |
| `src/parallax/platform/db/alembic/versions/20260517_0053_reconcile_legacy_asset_stack_drop.py` | 54 | `20260517_0053` | `20260517_0052` |
| `src/parallax/platform/db/alembic/versions/20260517_0054_token_radar_materialized_listed_at.py` | 59 | `20260517_0054` | `20260517_0053` |
| `src/parallax/platform/db/alembic/versions/20260517_0055_public_read_path_indexes.py` | 73 | `20260517_0055` | `20260517_0054` |
| `src/parallax/platform/db/alembic/versions/20260517_0056_recent_payload_batch_indexes.py` | 61 | `20260517_0056` | `20260517_0055` |
| `src/parallax/platform/db/alembic/versions/20260517_0057_cex_token_static_icons.py` | 30 | `20260517_0057` | `20260517_0056` |
| `src/parallax/platform/db/alembic/versions/20260517_0058_binance_profile_sources.py` | 109 | `20260517_0058` | `20260517_0057` |
| `src/parallax/platform/db/alembic/versions/20260517_0059_pulse_control_plane_kiss.py` | 50 | `20260517_0059` | `20260517_0058` |
| `src/parallax/platform/db/alembic/versions/20260518_0060_event_anchor_backfill_jobs.py` | 202 | `20260518_0060` | `20260517_0059` |
| `src/parallax/platform/db/alembic/versions/20260518_0061_drop_closed_loop_harness.py` | 88 | `20260518_0061` | `20260518_0060` |
| `src/parallax/platform/db/alembic/versions/20260518_0062_pulse_evidence_first_recovery.py` | 240 | `20260518_0062` | `20260518_0061` |
| `src/parallax/platform/db/alembic/versions/20260518_0063_narrative_intel_read_models.py` | 248 | `20260518_0063` | `20260518_0062` |
| `src/parallax/platform/db/alembic/versions/20260519_0064_narrative_admission_source_sets.py` | 44 | `20260519_0064` | `20260518_0063` |
| `src/parallax/platform/db/alembic/versions/20260519_0065_news_intel_kappa_cqrs.py` | 369 | `20260519_0065` | `20260519_0064` |
| `src/parallax/platform/db/alembic/versions/20260519_0066_pulse_backpressure_run_outcomes.py` | 52 | `20260519_0066` | `20260519_0065` |
| `src/parallax/platform/db/alembic/versions/20260520_0067_pulse_research_committee_checks.py` | 101 | `20260520_0067` | `20260519_0066` |
| `src/parallax/platform/db/alembic/versions/20260520_0068_news_item_agent_brief.py` | 142 | `20260520_0068` | `20260520_0067` |
| `src/parallax/platform/db/alembic/versions/20260520_0069_token_radar_retention_watchlist_stats.py` | 121 | `20260520_0069` | `20260520_0068` |
| `src/parallax/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py` | 38 | `20260520_0070` | `20260520_0069` |
| `src/parallax/platform/db/alembic/versions/20260521_0071_market_tick_open_interest.py` | 18 | `20260521_0071` | `20260520_0070` |
| `src/parallax/platform/db/alembic/versions/20260521_0072_cex_binance_source_provider_additive.py` | 44 | `20260521_0072` | `20260521_0071` |
| `src/parallax/platform/db/alembic/versions/20260521_0073_cex_oi_radar_board.py` | 107 | `20260521_0073` | `20260521_0072` |
| `src/parallax/platform/db/alembic/versions/20260521_0074_cex_detail_snapshots.py` | 72 | `20260521_0074` | `20260521_0073` |
| `src/parallax/platform/db/alembic/versions/20260521_0075_news_source_cryptopanic_provider.py` | 33 | `20260521_0075` | `20260521_0074` |
| `src/parallax/platform/db/alembic/versions/20260521_0076_macro_views.py` | 74 | `20260521_0076` | `20260521_0075` |
| `src/parallax/platform/db/alembic/versions/20260521_0077_macro_regime_70.py` | 60 | `20260521_0077` | `20260521_0076` |
| `src/parallax/platform/db/alembic/versions/20260521_0078_token_image_assets.py` | 96 | `20260521_0078` | `20260521_0077` |
| `src/parallax/platform/db/alembic/versions/20260521_0079_token_profile_local_logo_hard_cut.py` | 54 | `20260521_0079` | `20260521_0078` |
| `src/parallax/platform/db/alembic/versions/20260521_0080_macro_concept_key_hard_cut.py` | 120 | `20260521_0080` | `20260521_0079` |
| `src/parallax/platform/db/alembic/versions/20260522_0081_news_source_chain_classification.py` | 157 | `20260522_0081` | `20260521_0080` |
| `src/parallax/platform/db/alembic/versions/20260522_0082_news_source_quality_rows.py` | 48 | `20260522_0082` | `20260522_0081` |
| `src/parallax/platform/db/alembic/versions/20260523_0083_equity_event_intel.py` | 611 | `20260523_0083` | `20260522_0082` |
| `src/parallax/platform/db/alembic/versions/20260523_0084_equity_event_fact_candidate_shape.py` | 70 | `20260523_0084` | `20260523_0083` |
| `src/parallax/platform/db/alembic/versions/20260523_0085_token_radar_storage_root_fix.py` | 191 | `20260523_0085` | `20260523_0084` |
| `src/parallax/platform/db/alembic/versions/20260523_0086_equity_event_runtime_indexes.py` | 40 | `20260523_0086` | `20260523_0085` |
| `src/parallax/platform/db/alembic/versions/20260523_0087_news_content_classification.py` | 54 | `20260523_0087` | `20260523_0086` |
| `src/parallax/platform/db/alembic/versions/20260523_0088_news_page_filter_indexes.py` | 65 | `20260523_0088` | `20260523_0087` |
| `src/parallax/platform/db/alembic/versions/20260523_0089_token_image_unsupported_cleanup.py` | 39 | `20260523_0089` | `20260523_0088` |
| `src/parallax/platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py` | 503 | `20260523_0090` | `20260523_0089` |
| `src/parallax/platform/db/alembic/versions/20260524_0091_token_radar_target_feature_freshness_index.py` | 30 | `20260524_0091` | `20260523_0090` |
| `src/parallax/platform/db/alembic/versions/20260524_0092_equity_projection_payload_hashes.py` | 130 | `20260524_0092` | `20260524_0091` |
| `src/parallax/platform/db/alembic/versions/20260524_0093_token_radar_target_projection_coverage.py` | 50 | `20260524_0093` | `20260524_0092` |
| `src/parallax/platform/db/alembic/versions/20260524_0094_projection_dirty_targets_hard_cut.py` | 165 | `20260524_0094` | `20260524_0093` |
| `src/parallax/platform/db/alembic/versions/20260524_0095_market_tick_current_dirty_targets.py` | 66 | `20260524_0095` | `20260524_0094` |
| `src/parallax/platform/db/alembic/versions/20260525_0096_token_discovery_dirty_lookup_keys.py` | 69 | `20260525_0096` | `20260524_0095` |
| `src/parallax/platform/db/alembic/versions/20260525_0097_agent_brief_dirty_targets.py` | 148 | `20260525_0097` | `20260525_0096` |
| `src/parallax/platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py` | 451 | `20260525_0098` | `20260525_0097` |
| `src/parallax/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py` | 344 | `20260526_0099` | `20260525_0098` |
| `src/parallax/platform/db/alembic/versions/20260526_0100_worker_queue_terminal_events.py` | 221 | `20260526_0100` | `20260526_0099` |
| `src/parallax/platform/db/alembic/versions/20260526_0101_postgres_runtime_root_cause_hard_cut.py` | 154 | `20260526_0101` | `20260526_0100` |
| `src/parallax/platform/db/alembic/versions/20260526_0102_macro_observation_series_source_ts_text.py` | 36 | `20260526_0102` | `20260526_0101` |
| `src/parallax/platform/db/alembic/versions/20260526_0103_normalize_terminal_reason_buckets.py` | 73 | `20260526_0103` | `20260526_0102` |
| `src/parallax/platform/db/alembic/versions/20260526_0104_equity_event_evidence_hard_cut.py` | 286 | `20260526_0104` | `20260526_0103` |
| `src/parallax/platform/db/alembic/versions/20260526_0105_opennews_provider_signal.py` | 134 | `20260526_0105` | `20260526_0104` |
| `src/parallax/platform/db/alembic/versions/20260526_0106_runtime_rank_source_edges.py` | 173 | `20260526_0106` | `20260526_0105` |
| `src/parallax/platform/db/alembic/versions/20260526_0107_macro_generation_equity_evidence_jobs.py` | 193 | `20260526_0107` | `20260526_0106` |
| `src/parallax/platform/db/alembic/versions/20260526_0108_runtime_perf_lifecycle_indexes.py` | 122 | `20260526_0108` | `20260526_0107` |
| `src/parallax/platform/db/alembic/versions/20260526_0109_rank_source_identity_confidence_text.py` | 35 | `20260526_0109` | `20260526_0108` |
| `src/parallax/platform/db/alembic/versions/20260526_0110_equity_fetch_run_reaper.py` | 88 | `20260526_0110` | `20260526_0109` |
| `src/parallax/platform/db/alembic/versions/20260527_0111_token_radar_publication_state.py` | 82 | `20260527_0111` | `20260526_0110` |
| `src/parallax/platform/db/alembic/versions/20260527_0112_macro_sync_worker.py` | 146 | `20260527_0112` | `20260527_0111` |
| `src/parallax/platform/db/alembic/versions/20260527_0113_token_radar_stable_publication.py` | 51 | `20260527_0113` | `20260527_0112` |
| `src/parallax/platform/db/alembic/versions/20260527_0114_runtime_db_performance_hard_cut.py` | 150 | `20260527_0114` | `20260527_0113` |
| `src/parallax/platform/db/alembic/versions/20260527_0115_next_runtime_lifecycle_hard_cut.py` | 390 | `20260527_0115` | `20260527_0114` |
| `src/parallax/platform/db/alembic/versions/20260528_0116_macro_workerspace_root_fix.py` | 463 | `20260528_0116` | `20260527_0115` |
| `src/parallax/platform/db/alembic/versions/20260528_0117_news_intel_canonical_dedup_hard_cut.py` | 671 | `20260528_0117` | `20260528_0116` |
| `src/parallax/platform/db/alembic/versions/20260528_0118_news_realtime_postgres_hotpath_hard_cut.py` | 103 | `20260528_0118` | `20260528_0117` |
| `src/parallax/platform/db/alembic/versions/20260528_0119_news_source_status_hotpath_indexes.py` | 50 | `20260528_0119` | `20260528_0118` |
| `src/parallax/platform/db/alembic/versions/20260528_0120_drop_news_token_presence_filter_index.py` | 23 | `20260528_0120` | `20260528_0119` |
| `src/parallax/platform/db/alembic/versions/20260528_0121_token_equity_workerspace_root_fix.py` | 162 | `20260528_0121` | `20260528_0120` |
| `src/parallax/platform/db/alembic/versions/20260528_0122_token_radar_runtime_not_null_guardrails.py` | 38 | `20260528_0122` | `20260528_0121` |
| `src/parallax/platform/db/alembic/versions/20260529_0123_news_public_url_hard_identity.py` | 284 | `20260529_0123` | `20260528_0122` |
| `src/parallax/platform/db/alembic/versions/20260529_0124_token_pulse_equity_cpu_hard_cut.py` | 84 | `20260529_0124` | `20260529_0123` |
| `src/parallax/platform/db/alembic/versions/20260529_0125_drop_equity_event_intel.py` | 47 | `20260529_0125` | `20260529_0124` |
| `src/parallax/platform/db/alembic/versions/20260529_0126_token_radar_venue_source_width_hard_cut.py` | 162 | `20260529_0126` | `20260529_0125` |
| `src/parallax/platform/db/alembic/versions/20260529_0127_token_radar_drop_prevenue_current_uniques.py` | 74 | `20260529_0127` | `20260529_0126` |
| `src/parallax/platform/db/alembic/versions/20260529_0128_litellm_execution_audit_hard_cut.py` | 70 | `20260529_0128` | `20260529_0127` |
| `src/parallax/platform/db/alembic/versions/20260530_0129_drop_legacy_5min_notifications.py` | 26 | `20260530_0129` | `20260529_0128` |
| `src/parallax/platform/db/alembic/versions/20260530_0130_drop_social_watchlist_agent_tables.py` | 26 | `20260530_0130` | `20260530_0129` |
| `src/parallax/platform/db/alembic/versions/20260531_0131_news_story_projection_hard_cut.py` | 28 | `20260531_0131` | `20260530_0130` |
| `src/parallax/platform/db/alembic/versions/20260531_0132_news_rebuild_brief_backlog_hard_cut.py` | 31 | `20260531_0132` | `20260531_0131` |
| `src/parallax/platform/db/alembic/versions/20260531_0133_news_public_url_identity_index_scope.py` | 40 | `20260531_0133` | `20260531_0132` |
| `src/parallax/platform/db/alembic/versions/20260531_0134_token_image_magic_policy_retry.py` | 36 | `20260531_0134` | `20260531_0133` |
| `src/parallax/platform/db/alembic/versions/20260531_0136_okx_symbol_candidate_profile_icons.py` | 82 | `20260531_0136` | `20260531_0134` |
| `src/parallax/platform/db/alembic/versions/20260531_0137_news_dirty_projection_hard_cut.py` | 133 | `20260531_0137` | `20260531_0136` |
| `src/parallax/platform/db/alembic/versions/20260531_0138_news_page_projection_version_hard_cut.py` | 26 | `20260531_0138` | `20260531_0137` |
| `src/parallax/platform/db/alembic/versions/20260601_0139_news_item_brief_lightweight_contract.py` | 112 | `20260601_0139` | `20260531_0138` |
| `src/parallax/platform/db/alembic/versions/20260601_0140_news_item_brief_requeue_nonready.py` | 112 | `20260601_0140` | `20260601_0139` |
| `src/parallax/platform/db/alembic/versions/20260601_0141_news_intel_kiss_simplification.py` | 22 | `20260601_0141` | `20260601_0140` |
| `src/parallax/platform/db/alembic/versions/20260603_0142_news_context_and_filter_hard_cut.py` | 94 | `20260603_0142` | `20260601_0141` |
| `src/parallax/platform/db/alembic/versions/20260603_0143_cex_detail_payload_hash_hard_cut.py` | 225 | `20260603_0143` | `20260603_0142` |
| `src/parallax/platform/db/alembic/versions/20260603_0144_news_item_process_claim_hard_cut.py` | 200 | `20260603_0144` | `20260603_0143` |
| `src/parallax/platform/db/alembic/versions/20260603_0145_narrative_zero_write_hashes.py` | 230 | `20260603_0145` | `20260603_0144` |
| `src/parallax/platform/db/alembic/versions/20260603_0146_macro_sync_state_hard_cut.py` | 66 | `20260603_0146` | `20260603_0145` |
| `src/parallax/platform/db/alembic/versions/20260603_0147_news_research_index_support.py` | 48 | `20260603_0147` | `20260603_0146` |
| `src/parallax/platform/db/alembic/versions/20260604_0148_news_material_duplicate_hard_cut.py` | 57 | `20260604_0148` | `20260603_0147` |
| `src/parallax/platform/db/alembic/versions/20260605_0149_news_analysis_story_hard_cut.py` | 78 | `20260605_0149` | `20260604_0148` |
| `src/parallax/platform/db/alembic/versions/20260605_0150_news_agent_requirement_contract.py` | 73 | `20260605_0150` | `20260605_0149` |
| `src/parallax/platform/db/alembic/versions/20260606_0151_news_agent_market_admission_hard_cut.py` | 62 | `20260606_0151` | `20260605_0150` |
| `src/parallax/platform/db/alembic/versions/20260606_0152_news_page_search_document.py` | 115 | `20260606_0152` | `20260606_0151` |
| `src/parallax/platform/db/alembic/versions/20260607_0152_news_market_scope_hard_cut.py` | 56 | `20260607_0152` | `20260606_0152` |
| `src/parallax/platform/db/alembic/versions/20260608_0153_macro_sync_freshness_claim_order.py` | 39 | `20260608_0153` | `20260607_0152` |
| `src/parallax/platform/db/alembic/versions/20260608_0154_account_quality_snapshot_identity.py` | 55 | `20260608_0154` | `20260608_0153` |
| `src/parallax/platform/db/alembic/versions/20260608_0155_pulse_candidate_serving_row_audit_identity_hard_cut.py` | 25 | `20260608_0155` | `20260608_0154` |
| `src/parallax/platform/db/alembic/versions/20260608_0156_pulse_candidate_product_identity_hard_cut.py` | 208 | `20260608_0156` | `20260608_0155` |
| `src/parallax/platform/db/alembic/versions/20260608_0157_token_radar_current_rows_product_identity.py` | 32 | `20260608_0157` | `20260608_0156` |
| `src/parallax/platform/db/alembic/versions/20260608_0158_pulse_single_decision_stage.py` | 55 | `20260608_0158` | `20260608_0157` |
| `src/parallax/platform/db/alembic/versions/20260609_0159_macro_daily_briefs.py` | 47 | `20260609_0159` | `20260608_0158` |
| `src/parallax/platform/db/alembic/versions/20260609_0160_postgres_observability_extensions.py` | 33 | `20260609_0160` | `20260609_0159` |
| `src/parallax/platform/db/alembic/versions/20260609_0161_news_agent_admission_candidate_indexes.py` | 40 | `20260609_0161` | `20260609_0160` |
| `src/parallax/platform/db/alembic/versions/20260609_0162_news_page_member_lookup_index.py` | 27 | `20260609_0162` | `20260609_0161` |
| `src/parallax/platform/db/alembic/versions/20260609_0163_news_page_alert_ready_index.py` | 37 | `20260609_0163` | `20260609_0162` |
| `src/parallax/platform/db/alembic/versions/20260609_0164_news_page_display_score_index.py` | 27 | `20260609_0164` | `20260609_0163` |
| `src/parallax/platform/db/alembic/versions/20260609_0165_news_page_remove_display_score_index.py` | 21 | `20260609_0165` | `20260609_0164` |
| `src/parallax/platform/db/alembic/versions/20260609_0166_news_agent_run_artifact_hash_canonical.py` | 32 | `20260609_0166` | `20260609_0165` |
| `src/parallax/platform/db/alembic/versions/20260609_0167_news_story_identity_v2.py` | 203 | `20260609_0167` | `20260609_0166` |
| `src/parallax/platform/db/alembic/versions/20260609_0168_news_story_identity_v2_remaining_opennews.py` | 156 | `20260609_0168` | `20260609_0167` |
| `src/parallax/platform/db/alembic/versions/20260609_0169_news_page_rows_retired_projection_purge.py` | 27 | `20260609_0169` | `20260609_0168` |
| `src/parallax/platform/db/alembic/versions/20260609_0170_news_agent_admission_retired_policy_reprocess.py` | 91 | `20260609_0170` | `20260609_0169` |
| `src/parallax/platform/db/alembic/versions/20260609_0171_news_page_rows_require_story_identity.py` | 49 | `20260609_0171` | `20260609_0170` |
| `src/parallax/platform/db/alembic/versions/20260609_0172_news_page_rows_require_agent_eligible.py` | 47 | `20260609_0172` | `20260609_0171` |
| `src/parallax/platform/db/alembic/versions/20260609_0173_news_page_rows_serving_invariants.py` | 58 | `20260609_0173` | `20260609_0172` |
| `src/parallax/platform/db/alembic/versions/20260609_0174_news_page_provider_rating.py` | 50 | `20260609_0174` | `20260609_0173` |
| `src/parallax/platform/db/alembic/versions/20260609_0175_news_agent_provider_rating_gate.py` | 159 | `20260609_0175` | `20260609_0174` |
| `src/parallax/platform/db/alembic/versions/20260609_0176_news_provider_rating_gate_finalize.py` | 170 | `20260609_0176` | `20260609_0175` |
| `src/parallax/platform/db/alembic/versions/20260612_0177_news_brief_duplicate_cost_hard_cut.py` | 200 | `20260612_0177` | `20260609_0176` |
| `src/parallax/platform/db/alembic/versions/20260612_0178_notification_delivery_stale_claim_index.py` | 34 | `20260612_0178` | `20260612_0177` |
| `src/parallax/platform/db/alembic/versions/20260612_0179_pulse_public_search_trgm_indexes.py` | 64 | `20260612_0179` | `20260612_0178` |
| `src/parallax/platform/db/alembic/versions/20260616_0180_macro_event_text_series_nullable.py` | 21 | `20260616_0180` | `20260612_0179` |
| `src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py` | 146 | `20260618_0181` | `20260616_0180` |
| `src/parallax/platform/db/alembic/versions/20260623_0182_news_page_macro_event_flow.py` | 122 | `20260623_0182` | `20260618_0181` |
| `src/parallax/platform/db/alembic/versions/20260713_0183_backend_kappa_cqrs_hard_cut.py` | 389 | `20260713_0183` | `20260623_0182` |
| `src/parallax/platform/db/alembic/versions/20260721_0184_signal_pulse_hard_delete.py` | 54 | `20260721_0184` | `20260713_0183` |

## 架构 / 知识说明文件

| 文件 | LOC |
|---|---:|
| `src/parallax/agent_knowledge/market_research_harness.md` | 13 |
| `src/parallax/domains/account_quality/ARCHITECTURE.md` | 104 |
| `src/parallax/domains/asset_market/ARCHITECTURE.md` | 239 |
| `src/parallax/domains/cex_market_intel/ARCHITECTURE.md` | 165 |
| `src/parallax/domains/macro_intel/ARCHITECTURE.md` | 312 |
| `src/parallax/domains/narrative_intel/ARCHITECTURE.md` | 83 |
| `src/parallax/domains/news_intel/ARCHITECTURE.md` | 318 |
| `src/parallax/domains/news_intel/prompts/news_item_brief.md` | 69 |
| `src/parallax/domains/notifications/ARCHITECTURE.md` | 72 |
| `src/parallax/domains/token_intel/ARCHITECTURE.md` | 373 |
| `src/parallax/domains/watchlist_intel/ARCHITECTURE.md` | 31 |

## 重要边界说明

- 本图是导航索引，不是合理性结论；结论、删除候选、目标数据流和迁移顺序见同目录的后端 KISS 架构审计。
- “高入度”只意味着改动传播范围大，不等于设计错误；“低入度”也可能由动态装载、SQL 或 HTTP 路由使用。
- 文件拆分不能自动降低复杂度。审计优先删除无消费者的能力、重复控制面和重复契约，再考虑物理拆分。

<!-- file-map-complete -->

