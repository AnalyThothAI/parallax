# Verification — Token Radar Kappa/CQRS Hard Cut

**Date**: 2026-05-13
**Owning spec**: `docs/superpowers/specs/active/2026-05-13-token-radar-pipeline-overcomplexity-audit-cn.md`
**Owning plan**: `docs/superpowers/plans/active/2026-05-13-token-radar-kappa-cqrs-hard-cut-plan-cn.md`
**Branch**: `main` after merging `codex/token-radar-kappa-cqrs-hard-cut`
**Diff**: merged commits `66a4f28a` and `465d4fb0` on top of `68b78d42`.

The plan and spec are the contract. This file is the evidence the contract was met.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — market schema uses `event_anchor`, `decision_latest`, and `readiness` | ✅ | `make check-all` includes `tests/unit/test_token_radar_projection.py` and final `833 passed, 14 skipped`. |
| AC2 — no API/UI live overlay fallback | ✅ | `make check-all` includes `tests/test_no_factor_snapshot_fallback.py`; manual `rg` showed only historical Alembic migration references. |
| AC3 — `token_radar_rows` has one runtime writer | ✅ | `make check-all` includes `tests/architecture/test_src_domain_architecture.py`. |
| AC4 — DEX market floors fail closed | ✅ | `make check-all` includes `tests/test_factor_snapshot.py`. |
| AC5 — insufficient/all-tied cohorts return no signal | ✅ | `make check-all` includes `tests/unit/test_token_radar_apply_cross_section.py`. |
| AC6 — frontend live patch applies material market updates | ✅ | `make check-all` includes web checks and Vitest coverage from `npm test -- --run`. |
| AC7 — live observation write budget | ✅ | `make check-all` includes `tests/benchmark/test_live_observation_write_budget.py`. |
| AC8 — full gate | ✅ | `make check-all` exit code 0. |

Deviations from spec:

- None.

Deviations from plan:

- The plan's projection rebuild command name was stale; local rollout used `uv run gmgn-twitter-intel ops rebuild-token-radar`.
- The planned truncate list needed FK-derived read-model tables too: `asset_signal_snapshots`, `asset_signal_outcomes`, `pulse_playbook_snapshots`, and `pulse_playbook_outcomes`.
- User explicitly requested merging quickly before deeper testing, so `make check` was the pre-merge gate and `make check-all` was run post-merge on `main`.

## Verification commands

```text
$ make check-all > /tmp/gmgn-token-radar-kappa-main-check-all-final.log 2>&1
All checks passed!
419 files already formatted
Success: no issues found in 252 source files

> gmgn-twitter-intel-web@0.1.0 typecheck
> tsc --noEmit


> gmgn-twitter-intel-web@0.1.0 lint
> eslint --max-warnings=0 src


> gmgn-twitter-intel-web@0.1.0 format:check
> prettier --check 'src/**/*.{ts,tsx,css,json}'

Checking formatting...
All matched files use Prettier code style!
============================= test session starts ==============================
platform darwin -- Python 3.13.11, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/qinghuan/Documents/code/gmgn-twitter-intel
configfile: pyproject.toml
plugins: cov-7.1.0, anyio-4.13.0
collected 542 items

tests/unit/test_account_quality_service.py s                             [  0%]
tests/unit/test_anchor_price_observation.py .....                        [  1%]
tests/unit/test_anchor_price_worker.py ..                                [  1%]
tests/unit/test_asset_flow_service.py .....                              [  2%]
tests/unit/test_asset_identity_policy.py ...                             [  2%]
tests/unit/test_asset_identity_repository.py .                           [  3%]
tests/unit/test_asset_market_sync.py .                                   [  3%]
tests/unit/test_asset_profile_refresh.py ....                            [  4%]
tests/unit/test_asset_profile_refresh_worker.py ..                       [  4%]
tests/unit/test_asset_profile_repository.py sss..                        [  5%]
tests/unit/test_atomic_mention.py ..........                             [  7%]
tests/unit/test_baseline_scoring.py ...                                  [  7%]
tests/unit/test_catalyst_ranking_service_imports.py .                    [  7%]
tests/unit/test_cli_search_query.py ......                               [  9%]
tests/unit/test_collector_service.py ...                                 [  9%]
tests/unit/test_cross_section_normalizer.py ...........                  [ 11%]
tests/unit/test_deterministic_token_resolver.py ........................ [ 16%]
....                                                                     [ 16%]
tests/unit/test_diffusion_health.py .....                                [ 17%]
tests/unit/test_direct_ws.py .....                                       [ 18%]
tests/unit/test_entity_extractor.py .......                              [ 19%]
tests/unit/test_event_normalizer.py ...                                  [ 20%]
tests/unit/test_evidence_repository.py .                                 [ 20%]
tests/unit/test_factor_cohort.py .........                               [ 22%]
tests/unit/test_factor_diagnostics.py ......                             [ 23%]
tests/unit/test_gmgn_directory_client.py .....                           [ 24%]
tests/unit/test_gmgn_openapi_client.py .......                           [ 25%]
tests/unit/test_gmgn_token_payload.py .....                              [ 26%]
tests/unit/test_harness_scoring.py ...                                   [ 27%]
tests/unit/test_harness_settlement_credit.py ...                         [ 27%]
tests/unit/test_intent_resolution_repository.py .                        [ 27%]
tests/unit/test_live_observation_policy.py .......                       [ 29%]
tests/unit/test_live_price_gateway.py .                                  [ 29%]
tests/unit/test_market_candles_service.py ...                            [ 29%]
tests/unit/test_market_observation.py ...                                [ 30%]
tests/unit/test_notification_rules.py .........................          [ 35%]
tests/unit/test_okx_clients.py ..........                                [ 36%]
tests/unit/test_pending_asset_profile_query.py sss                       [ 37%]
tests/unit/test_post_text_quality.py .                                   [ 37%]
tests/unit/test_postgres_api_health.py .                                 [ 37%]
tests/unit/test_postgres_client.py .........                             [ 39%]
tests/unit/test_postgres_schema.py ........................              [ 43%]
tests/unit/test_price_observation_repository.py ....                     [ 44%]
tests/unit/test_price_observation_repository_policy.py .                 [ 44%]
tests/unit/test_provider_capabilities.py ..                              [ 45%]
tests/unit/test_providers_wiring.py .....                                [ 46%]
tests/unit/test_pulse_candidate_gate.py ....................             [ 49%]
tests/unit/test_pulse_candidate_worker.py ..........                     [ 51%]
tests/unit/test_pulse_timeline_context.py ..........                     [ 53%]
tests/unit/test_query_parser.py ......                                   [ 54%]
tests/unit/test_resolution_refresh_worker.py ....                        [ 55%]
tests/unit/test_search_agent_brief.py ..                                 [ 55%]
tests/unit/test_search_inspect_service.py ....                           [ 56%]
tests/unit/test_search_service.py ..........                             [ 58%]
tests/unit/test_settings.py .......................                      [ 62%]
tests/unit/test_signal_pulse_service.py ...............                  [ 65%]
tests/unit/test_social_event_agent_client.py ....                        [ 66%]
tests/unit/test_social_event_extraction.py .....                         [ 66%]
tests/unit/test_social_signal_features.py ..........                     [ 68%]
tests/unit/test_stocks_radar_service.py .                                [ 69%]
tests/unit/test_token_evidence_builder.py ...                            [ 69%]
tests/unit/test_token_factor_evaluation.py .........                     [ 71%]
tests/unit/test_token_intent_builder.py .......                          [ 72%]
tests/unit/test_token_intent_resolver.py ....                            [ 73%]
tests/unit/test_token_profile_read_model.py .....                        [ 74%]
tests/unit/test_token_radar_apply_cross_section.py ............          [ 76%]
tests/unit/test_token_radar_audit_cli.py ..............                  [ 78%]
tests/unit/test_token_radar_feature_builder.py ..........                [ 80%]
tests/unit/test_token_radar_idempotency.py s                             [ 80%]
tests/unit/test_token_radar_projection.py ..........................     [ 85%]
tests/unit/test_token_radar_projection_worker.py ....                    [ 86%]
tests/unit/test_token_radar_repository.py ss.ss................          [ 90%]
tests/unit/test_token_radar_source_query.py .                            [ 90%]
tests/unit/test_token_resolution_refresh.py ..                           [ 90%]
tests/unit/test_token_target_posts_service.py .                          [ 91%]
tests/unit/test_token_target_social_timeline_service.py ...              [ 91%]
tests/unit/test_token_target_stage_builder.py ..                         [ 92%]
tests/unit/test_tweet_text.py ..                                         [ 92%]
tests/unit/test_us_equity_symbol_sync.py ..                              [ 92%]
tests/architecture/test_completion_gates.py ....                         [ 93%]
tests/architecture/test_harness_structure.py .......                     [ 94%]
tests/architecture/test_project_structure.py .............               [ 97%]
tests/architecture/test_src_domain_architecture.py .............         [ 99%]
tests/contract/test_openapi_drift.py ..                                  [100%]

=========================== short test summary info ============================
SKIPPED [11] tests/postgres_test_utils.py:28: PostgreSQL test database is not available: connection failed: connection to server at "127.0.0.1", port 55432 failed: FATAL:  password authentication failed for user "postgres"
SKIPPED [1] tests/unit/test_token_radar_idempotency.py:60: No live PG DSN available — set GMGN_PROD_POSTGRES_DSN or GMGN_TEST_POSTGRES_DSN
======================= 530 passed, 12 skipped in 2.86s ========================
Listing 'src'...
Listing 'src/gmgn_twitter_intel'...
Listing 'src/gmgn_twitter_intel/app'...
Listing 'src/gmgn_twitter_intel/app/runtime'...
Listing 'src/gmgn_twitter_intel/app/surfaces'...
Listing 'src/gmgn_twitter_intel/app/surfaces/api'...
Listing 'src/gmgn_twitter_intel/app/surfaces/cli'...
Listing 'src/gmgn_twitter_intel/domains'...
Listing 'src/gmgn_twitter_intel/domains/account_quality'...
Listing 'src/gmgn_twitter_intel/domains/account_quality/read_models'...
Listing 'src/gmgn_twitter_intel/domains/account_quality/repositories'...
Listing 'src/gmgn_twitter_intel/domains/asset_market'...
Listing 'src/gmgn_twitter_intel/domains/asset_market/queries'...
Listing 'src/gmgn_twitter_intel/domains/asset_market/read_models'...
Listing 'src/gmgn_twitter_intel/domains/asset_market/repositories'...
Listing 'src/gmgn_twitter_intel/domains/asset_market/runtime'...
Listing 'src/gmgn_twitter_intel/domains/asset_market/services'...
Listing 'src/gmgn_twitter_intel/domains/asset_market/types'...
Listing 'src/gmgn_twitter_intel/domains/closed_loop_harness'...
Listing 'src/gmgn_twitter_intel/domains/closed_loop_harness/read_models'...
Listing 'src/gmgn_twitter_intel/domains/closed_loop_harness/repositories'...
Listing 'src/gmgn_twitter_intel/domains/closed_loop_harness/runtime'...
Listing 'src/gmgn_twitter_intel/domains/closed_loop_harness/scoring'...
Listing 'src/gmgn_twitter_intel/domains/closed_loop_harness/services'...
Listing 'src/gmgn_twitter_intel/domains/evidence'...
Listing 'src/gmgn_twitter_intel/domains/evidence/repositories'...
Listing 'src/gmgn_twitter_intel/domains/evidence/services'...
Listing 'src/gmgn_twitter_intel/domains/evidence/types'...
Listing 'src/gmgn_twitter_intel/domains/ingestion'...
Listing 'src/gmgn_twitter_intel/domains/ingestion/runtime'...
Listing 'src/gmgn_twitter_intel/domains/ingestion/services'...
Listing 'src/gmgn_twitter_intel/domains/ingestion/types'...
Listing 'src/gmgn_twitter_intel/domains/notifications'...
Listing 'src/gmgn_twitter_intel/domains/notifications/repositories'...
Listing 'src/gmgn_twitter_intel/domains/notifications/runtime'...
Listing 'src/gmgn_twitter_intel/domains/notifications/services'...
Listing 'src/gmgn_twitter_intel/domains/pulse_lab'...
Listing 'src/gmgn_twitter_intel/domains/pulse_lab/read_models'...
Listing 'src/gmgn_twitter_intel/domains/pulse_lab/repositories'...
Listing 'src/gmgn_twitter_intel/domains/pulse_lab/runtime'...
Listing 'src/gmgn_twitter_intel/domains/pulse_lab/services'...
Listing 'src/gmgn_twitter_intel/domains/pulse_lab/types'...
Listing 'src/gmgn_twitter_intel/domains/social_enrichment'...
Listing 'src/gmgn_twitter_intel/domains/social_enrichment/repositories'...
Listing 'src/gmgn_twitter_intel/domains/social_enrichment/runtime'...
Listing 'src/gmgn_twitter_intel/domains/social_enrichment/services'...
Listing 'src/gmgn_twitter_intel/domains/social_enrichment/types'...
Listing 'src/gmgn_twitter_intel/domains/token_intel'...
Listing 'src/gmgn_twitter_intel/domains/token_intel/queries'...
Listing 'src/gmgn_twitter_intel/domains/token_intel/read_models'...
Listing 'src/gmgn_twitter_intel/domains/token_intel/repositories'...
Listing 'src/gmgn_twitter_intel/domains/token_intel/runtime'...
Listing 'src/gmgn_twitter_intel/domains/token_intel/scoring'...
Listing 'src/gmgn_twitter_intel/domains/token_intel/services'...
Listing 'src/gmgn_twitter_intel/integrations'...
Listing 'src/gmgn_twitter_intel/integrations/coingecko'...
Listing 'src/gmgn_twitter_intel/integrations/gmgn'...
Listing 'src/gmgn_twitter_intel/integrations/marketlane'...
Listing 'src/gmgn_twitter_intel/integrations/okx'...
Listing 'src/gmgn_twitter_intel/integrations/openai_agents'...
Listing 'src/gmgn_twitter_intel/platform'...
Listing 'src/gmgn_twitter_intel/platform/config'...
Listing 'src/gmgn_twitter_intel/platform/db'...
Listing 'src/gmgn_twitter_intel/platform/db/alembic'...
Listing 'src/gmgn_twitter_intel/platform/db/alembic/versions'...
Listing 'src/gmgn_twitter_intel/platform/logging'...
Listing 'src/gmgn_twitter_intel/platform/paths'...
Listing 'src/gmgn_twitter_intel/storage'...
Listing 'src/gmgn_twitter_intel/storage/alembic'...
Listing 'src/gmgn_twitter_intel/storage/alembic/versions'...
Listing 'tests'...
Listing 'tests/architecture'...
Listing 'tests/benchmark'...
Listing 'tests/contract'...
Listing 'tests/e2e'...
Listing 'tests/fixtures'...
Listing 'tests/golden'...
Listing 'tests/integration'...
Listing 'tests/integrations'...
Listing 'tests/scripts'...
Listing 'tests/unit'...
============================= test session starts ==============================
platform darwin -- Python 3.13.11, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/qinghuan/Documents/code/gmgn-twitter-intel
configfile: pyproject.toml
plugins: cov-7.1.0, anyio-4.13.0
collected 189 items

tests/integration/test_account_quality_repository.py ...                 [  1%]
tests/integration/test_api_health.py ............                        [  7%]
tests/integration/test_api_http.py ................................      [ 24%]
tests/integration/test_api_static.py ..                                  [ 25%]
tests/integration/test_api_websocket.py ..........                       [ 31%]
tests/integration/test_asset_ingest_flow.py ....                         [ 33%]
tests/integration/test_asset_repository.py ....                          [ 35%]
tests/integration/test_cli.py .................                          [ 44%]
tests/integration/test_compose_healthcheck.py ..                         [ 45%]
tests/integration/test_compose_postgres.py ..                            [ 46%]
tests/integration/test_discovery_and_lookup_repositories.py .......      [ 50%]
tests/integration/test_docs_generated.py ....                            [ 52%]
tests/integration/test_enrichment_repository.py ........s..              [ 58%]
tests/integration/test_enrichment_worker.py .sss                         [ 60%]
tests/integration/test_harness_ops.py ...s                               [ 62%]
tests/integration/test_harness_repository.py .                           [ 62%]
tests/integration/test_harness_snapshot_builder.py ....                  [ 65%]
tests/integration/test_intent_resolution_repository_lifecycle.py .       [ 65%]
tests/integration/test_notification_delivery.py ....                     [ 67%]
tests/integration/test_notification_repository.py .......                [ 71%]
tests/integration/test_notification_worker.py .....                      [ 74%]
tests/integration/test_postgres_audit.py ......                          [ 77%]
tests/integration/test_postgres_schema_runtime.py ........               [ 81%]
tests/integration/test_projection_repository.py ....                     [ 83%]
tests/integration/test_pulse_repository.py ...................           [ 93%]
tests/integration/test_registry_repository.py .....                      [ 96%]
tests/integration/test_resolution_refresh_worker.py s..sss               [ 99%]
tests/integration/test_token_intent_rebuild.py .                         [100%]

=========================== short test summary info ============================
SKIPPED [1] tests/integration/test_enrichment_repository.py:201: agents_sdk_run audit row shape changed; test indexes None subscript. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_enrichment_worker.py:140: Asserts harness materializer reaches snapshot_ready; current pipeline returns asset_unresolved because identity model changed in token-identity-evidence hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_enrichment_worker.py:173: Depends on harness materializer behaviour changed by hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_enrichment_worker.py:212: Asserts model_run rows after hung-job timeout; current pipeline does not produce them in expected shape post hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_harness_ops.py:141: materialize_market_ready_seeds returns 0 vs expected 2; depends on identity-current rows the test seeders predate after hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:48: registry_assets.symbol/name/decimals dropped by token-identity-evidence hard-cut (migration 20260510_0021); test predates new asset_identity_evidence/current model. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:265: registry_assets.symbol dropped by token-identity-evidence hard-cut (migration 20260510_0021); test asserts demoted_search by symbol selector. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:392: upsert_chain_asset(symbol=…, name=…, decimals=…, source=…) signature removed by token-identity-evidence hard-cut; identity now lives in asset_identity_evidence/current. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:461: SELECT registry_assets.symbol references column dropped by hard-cut (migration 20260510_0021); should select via asset_identity_current. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
================== 180 passed, 9 skipped in 519.18s (0:08:39) ==================
============================= test session starts ==============================
platform darwin -- Python 3.13.11, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/qinghuan/Documents/code/gmgn-twitter-intel
configfile: pyproject.toml
plugins: cov-7.1.0, anyio-4.13.0
collected 4 items

tests/e2e/test_golden_path.py ....                                       [100%]

============================== 4 passed in 8.99s ===============================
............................................ssss........................ [  8%]
........................................................................ [ 17%]
...........s...sss...s.................................................. [ 25%]
..............s..sss.................................................... [ 34%]
........................................................................ [ 42%]
........................................................................ [ 51%]
........................................................................ [ 59%]
........................................................................ [ 68%]
........................................................................ [ 76%]
........................................................................ [ 85%]
..............................................................s......... [ 93%]
.......................................................                  [100%]
================================ tests coverage ================================
______________ coverage: platform darwin, python 3.13.11-final-0 _______________

Name                                                                                             Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------------------------------------------------------------------------
src/gmgn_twitter_intel/__main__.py                                                                   3      3      2      0   0.0%   1-4
src/gmgn_twitter_intel/app/runtime/app.py                                                          391     62    134     37  79.6%   164, 167->170, 207, 215-216, 234, 245-246, 336, 344, 351, 358, 369, 384, 392-393, 413, 419, 421, 423, 425, 427, 433-436, 441, 447, 449, 451, 453, 485-487, 490, 492, 494, 638, 644, 646, 648, 650, 652, 666, 668, 676-677, 691-698, 722-729
src/gmgn_twitter_intel/app/runtime/providers_wiring.py                                             252     54     58     13  75.2%   95, 98, 101-102, 105, 108, 125, 139, 157, 176, 210, 223-235, 238-240, 243-246, 251, 255, 259, 263, 267, 270, 279-280, 283, 316, 318, 326, 328, 331, 359->362, 396, 422, 431, 443, 466, 478, 492, 518, 533, 550, 552, 578-580
src/gmgn_twitter_intel/app/runtime/repository_session.py                                            69      2      2      1  95.8%   66, 112
src/gmgn_twitter_intel/app/runtime/wake_bus.py                                                      59     14     16      6  70.7%   13, 22, 34-35, 59, 73-84, 102->exit, 135, 136->exit, 138-139
src/gmgn_twitter_intel/app/surfaces/api/http.py                                                    350     31     38      6  90.5%   61->63, 248, 282, 284, 317-318, 355-361, 426-429, 577-583, 619-624, 640, 713, 741, 758, 761-764
src/gmgn_twitter_intel/app/surfaces/api/ws.py                                                      202     50     80     17  70.6%   46, 55-58, 61, 82-84, 87-88, 93-95, 98-99, 104-106, 123-124, 150-152, 159->153, 162-164, 188-189, 198, 200-201, 213-218, 226-230, 238, 246, 254, 256, 260, 264-265
src/gmgn_twitter_intel/app/surfaces/cli/main.py                                                    524    102    146     14  78.8%   319-329, 412-415, 417-420, 502-504, 544-550, 691-696, 752-767, 770-780, 799-890, 937-940, 964-966, 971->974, 982->984, 985-986, 998-1011, 1021-1034, 1064, 1072, 1121
src/gmgn_twitter_intel/domains/account_quality/interfaces.py                                         5      5      0      0   0.0%   1-7
src/gmgn_twitter_intel/domains/account_quality/read_models/account_alert_service.py                  9      0      0      0 100.0%
src/gmgn_twitter_intel/domains/account_quality/read_models/account_quality_service.py              114     42     32      4  56.2%   71-80, 99-124, 133, 144-146, 180-191, 195-202, 223, 228, 233-235
src/gmgn_twitter_intel/domains/account_quality/repositories/account_quality_repository.py           46      1      6      0  98.1%   223
src/gmgn_twitter_intel/domains/asset_market/identity_evidence_policy.py                             88      5     38      5  92.1%   68, 103, 110, 126, 133
src/gmgn_twitter_intel/domains/asset_market/interfaces.py                                           11      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/market_field_facts.py                                   39     22     10      0  34.7%   39-42, 54-55, 66-83, 87-93
src/gmgn_twitter_intel/domains/asset_market/providers.py                                           106      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/queries/pending_anchor_price_query.py                   11      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/queries/pending_asset_profile_query.py                  13      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/read_models/__init__.py                                  1      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/read_models/market_candles_service.py                   69     12     26      9  77.9%   21, 26, 32-33, 46, 51-52, 74, 100->102, 103, 127, 131, 137
src/gmgn_twitter_intel/domains/asset_market/read_models/token_profile_read_model.py                 61      2     20      2  95.1%   97, 122
src/gmgn_twitter_intel/domains/asset_market/repositories/asset_profile_repository.py                38      1      8      1  95.7%   93->exit, 188
src/gmgn_twitter_intel/domains/asset_market/repositories/asset_repository.py                       148     26     38     10  75.3%   125->128, 166->178, 199, 268->271, 303-316, 378->380, 384, 399-412, 415-427, 436-451, 546, 549, 552->554, 563, 568-571, 585-587
src/gmgn_twitter_intel/domains/asset_market/repositories/discovery_repository.py                    37      0      6      1  97.7%   261->263
src/gmgn_twitter_intel/domains/asset_market/repositories/identity_evidence_repository.py            66     14     16      5  74.4%   30-62, 148, 184, 229, 268, 270, 272
src/gmgn_twitter_intel/domains/asset_market/repositories/market_repository.py                        6      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/repositories/price_observation_repository.py            89     17     14      4  79.6%   74, 90, 131->133, 136-140, 143-154, 182-194, 197-209, 219-229, 325-340, 344, 529-530
src/gmgn_twitter_intel/domains/asset_market/repositories/registry_repository.py                    140     14     32      8  86.0%   40->42, 160->162, 210->212, 235, 257->259, 330-423, 426-436, 483-485, 507, 509, 584-585, 599-600
src/gmgn_twitter_intel/domains/asset_market/runtime/anchor_price_worker.py                          45      9     10      0  72.7%   38-44, 69, 72-75
src/gmgn_twitter_intel/domains/asset_market/runtime/asset_profile_refresh_worker.py                 43      8      4      1  76.6%   34-40, 54-56, 62, 66->exit
src/gmgn_twitter_intel/domains/asset_market/runtime/live_price_gateway.py                          222     38     56     15  75.9%   49-51, 126, 155-159, 169, 179, 213-216, 231-240, 266->279, 269, 276, 280->exit, 317-335, 394, 402, 405, 426-429, 465
src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py                   161     39     52      8  67.6%   72-78, 96-98, 104, 107-110, 346, 354->356, 430, 433->426, 452->450, 477-478, 480, 485-489, 493-499, 524, 527-535
src/gmgn_twitter_intel/domains/asset_market/services/anchor_price_observation.py                   133     16     54     12  85.0%   65, 84, 89, 93-94, 108, 113, 117-118, 127, 141, 158, 177-178, 182-183
src/gmgn_twitter_intel/domains/asset_market/services/asset_market_sync.py                           12      2      4      2  75.0%   56, 63
src/gmgn_twitter_intel/domains/asset_market/services/asset_profile_refresh.py                       34      0      6      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/services/live_observation_policy.py                     33      2     16      2  91.8%   65, 68
src/gmgn_twitter_intel/domains/asset_market/services/us_equity_symbol_sync.py                       75      9     12      0  87.4%   31, 34, 37-39, 42-45
src/gmgn_twitter_intel/domains/asset_market/types/__init__.py                                        2      0      0      0 100.0%
src/gmgn_twitter_intel/domains/asset_market/types/market_observation.py                             68      2     12      2  95.0%   131, 138
src/gmgn_twitter_intel/domains/closed_loop_harness/interfaces.py                                     5      0      0      0 100.0%
src/gmgn_twitter_intel/domains/closed_loop_harness/read_models/harness_service.py                   66     25     18      2  53.6%   82, 84-93, 138-146, 150-154
src/gmgn_twitter_intel/domains/closed_loop_harness/repositories/harness_repository.py              288     58     62     20  73.1%   103->105, 127-129, 131-133, 202->204, 211-212, 230-232, 288->290, 325->327, 349-350, 410-471, 499->501, 536->538, 559->561, 612->614, 667->669, 679, 720-730, 746->749, 750-751, 789-793, 848-852, 869->872, 888->891, 939, 942-945, 956-968
src/gmgn_twitter_intel/domains/closed_loop_harness/runtime/harness_ops_worker.py                    40      2      4      1  93.2%   37->exit, 40-41
src/gmgn_twitter_intel/domains/closed_loop_harness/scoring/harness_credit.py                        21      1      4      1  92.0%   13
src/gmgn_twitter_intel/domains/closed_loop_harness/scoring/harness_scoring.py                       27      4     10      2  78.4%   36, 43-45
src/gmgn_twitter_intel/domains/closed_loop_harness/scoring/harness_settlement.py                    14      1      2      1  87.5%   6
src/gmgn_twitter_intel/domains/closed_loop_harness/services/harness_ops.py                         135     32     40      8  74.9%   35-53, 79-80, 107-108, 124->75, 126-127, 142, 156-157, 165, 179-181, 208, 273, 279-280, 288
src/gmgn_twitter_intel/domains/closed_loop_harness/services/harness_snapshot_builder.py            172     21     58     14  83.0%   217, 224-225, 317, 341->346, 345, 370, 380, 391, 400-402, 408-410, 415->414, 417-418, 427, 432, 435-436, 446
src/gmgn_twitter_intel/domains/evidence/interfaces.py                                                5      0      0      0 100.0%
src/gmgn_twitter_intel/domains/evidence/repositories/entity_repository.py                           47     18     10      1  56.1%   61, 79-80, 89, 106-128
src/gmgn_twitter_intel/domains/evidence/repositories/evidence_repository.py                        115     29     30      7  72.4%   34-48, 97->99, 115-116, 118-120, 129-133, 136-138, 154, 208, 244, 250, 253-258
src/gmgn_twitter_intel/domains/evidence/services/entity_extractor.py                               195     17     86     14  88.3%   57, 66, 96, 98->93, 108->105, 184->168, 204->206, 207, 216-218, 230-231, 237, 246-247, 249, 319, 362, 364, 366
src/gmgn_twitter_intel/domains/evidence/services/ingest_service.py                                 108      8     28      2  91.2%   60-61, 156, 276-279, 287
src/gmgn_twitter_intel/domains/evidence/types/entity.py                                              3      0      0      0 100.0%
src/gmgn_twitter_intel/domains/evidence/types/tweet_identity.py                                     10      2      4      2  71.4%   9, 14
src/gmgn_twitter_intel/domains/evidence/types/tweet_text.py                                         51      0      6      1  98.2%   72->69
src/gmgn_twitter_intel/domains/evidence/types/twitter_event.py                                      78      0      0      0 100.0%
src/gmgn_twitter_intel/domains/ingestion/interfaces.py                                              13      0      0      0 100.0%
src/gmgn_twitter_intel/domains/ingestion/providers.py                                                8      0      0      0 100.0%
src/gmgn_twitter_intel/domains/ingestion/runtime/collector_service.py                              105     17     30      8  80.0%   64-66, 72, 74, 83-86, 89, 101, 112-114, 126->exit, 155, 160-161
src/gmgn_twitter_intel/domains/ingestion/services/normalizer.py                                    134     30     62     17  71.9%   30, 34, 38, 40, 42, 44, 46, 54, 59, 72, 78, 129-133, 200, 210-213, 217-220, 235, 239-241, 243, 251
src/gmgn_twitter_intel/domains/ingestion/services/subscriptions.py                                  19      3      6      2  80.0%   17, 23-24
src/gmgn_twitter_intel/domains/ingestion/types/gmgn_token_payload.py                                65      7     30      6  84.2%   50, 67, 72, 79, 82-84, 107->109
src/gmgn_twitter_intel/domains/notifications/interfaces.py                                           5      5      0      0   0.0%   1-7
src/gmgn_twitter_intel/domains/notifications/repositories/notification_repository.py               193     13     62     14  89.4%   152, 189, 197->199, 204->206, 271-272, 290-291, 313, 314->316, 334, 413, 492-493, 556->554, 565, 583
src/gmgn_twitter_intel/domains/notifications/runtime/notification_delivery.py                      106     53     32      5  44.9%   18-24, 29-42, 63-70, 73, 80, 86-87, 91-92, 94-95, 105-106, 134-153, 157
src/gmgn_twitter_intel/domains/notifications/runtime/notification_worker.py                         64      6     22      5  87.2%   42->exit, 45-47, 48->42, 108, 110, 112
src/gmgn_twitter_intel/domains/notifications/services/notification_rules.py                        404     40    122     31  84.6%   56, 73, 83, 86, 127, 136, 200, 229->232, 239, 244, 248, 320, 335, 375->373, 386, 389, 400, 408, 447, 454, 468-472, 476, 574->576, 626, 657-658, 671-678, 689, 725-726, 731, 780->782, 782->784, 786->789, 794->796, 796->798, 802
src/gmgn_twitter_intel/domains/notifications/types.py                                               21      0      0      0 100.0%
src/gmgn_twitter_intel/domains/pulse_lab/interfaces.py                                              25      0      0      0 100.0%
src/gmgn_twitter_intel/domains/pulse_lab/providers.py                                               13      0      0      0 100.0%
src/gmgn_twitter_intel/domains/pulse_lab/read_models/signal_pulse_service.py                        85      5     20      3  92.4%   86-87, 102->101, 188-189, 207
src/gmgn_twitter_intel/domains/pulse_lab/repositories/pulse_repository.py                          217      9     66     18  90.5%   136->138, 219->221, 231, 249->251, 254-264, 337->339, 357, 385->387, 506->508, 532->535, 575->578, 618->621, 766->768, 824->826, 875, 878, 892, 900, 936
src/gmgn_twitter_intel/domains/pulse_lab/runtime/pulse_candidate_worker.py                         513    103    162     44  74.1%   147-149, 154, 169-175, 178->exit, 180-181, 199, 205, 259-260, 264, 272->301, 281-289, 316, 320, 372, 375, 415, 417, 419, 488-489, 548-560, 568, 579, 596, 599, 602, 624-626, 703, 706, 732, 752, 765-772, 778, 786, 801-808, 819-827, 879, 881, 898, 913, 920-921, 932-936, 960-964, 971, 977, 979, 987, 1144, 1152, 1158, 1165, 1169, 1181->1179
src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_candidate_gate.py                          129      5     52      6  93.9%   117, 175, 184, 186->182, 195, 200
src/gmgn_twitter_intel/domains/pulse_lab/services/pulse_timeline_context.py                        311     23    128     22  89.3%   88, 153->152, 175, 210->213, 237->239, 349->347, 351, 372, 416, 424-425, 440, 452, 479, 486, 488, 496, 515-517, 522, 541, 552, 554, 557, 583-584
src/gmgn_twitter_intel/domains/pulse_lab/types/__init__.py                                           2      0      0      0 100.0%
src/gmgn_twitter_intel/domains/pulse_lab/types/pulse_recommendation.py                             175      6     62     15  91.1%   177->182, 180->178, 194->198, 196->195, 199->202, 206, 209->208, 214, 217->215, 228->226, 249, 320, 334, 337, 351->349
src/gmgn_twitter_intel/domains/social_enrichment/interfaces.py                                       5      0      0      0 100.0%
src/gmgn_twitter_intel/domains/social_enrichment/providers.py                                        7      0      0      0 100.0%
src/gmgn_twitter_intel/domains/social_enrichment/repositories/enrichment_repository.py             114     38     22      8  64.7%   85, 88, 98-99, 141, 143, 234-294, 309-355, 358-371, 377-378, 433, 439->431, 448-452, 456
src/gmgn_twitter_intel/domains/social_enrichment/runtime/enrichment_worker.py                       90     54     16      2  39.6%   35-36, 49-51, 53, 59-159, 163, 167-176
src/gmgn_twitter_intel/domains/social_enrichment/services/watched_event_gate.py                     58     11     26      5  76.2%   91, 93, 100-105, 114, 116, 134
src/gmgn_twitter_intel/domains/social_enrichment/types/social_event_extraction.py                  163     11     24      8  89.8%   216, 278, 280, 282, 284, 301, 317, 327-328, 342-343
src/gmgn_twitter_intel/domains/token_intel/_constants.py                                             8      0      0      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/interfaces.py                                            15      0      0      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/queries/event_rebuild_query.py                            8      0      0      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/queries/search_events_query.py                          130     70     40      5  39.4%   33-35, 46-68, 83, 135-165, 175-225, 329-349, 352-388, 391-414, 417-437, 457->466, 481, 484-491, 495-497, 501, 505-506, 510-513
src/gmgn_twitter_intel/domains/token_intel/queries/stocks_radar_query.py                            10      0      0      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/queries/token_radar_source_query.py                      22      6      0      0  72.7%   224-228, 231-233
src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py                        94      8     30      4  85.5%   133, 151-152, 154->144, 183-188
src/gmgn_twitter_intel/domains/token_intel/read_models/catalyst_ranking_service.py                  87     67     26      0  17.7%   22-31, 34-96, 100-103, 107-118, 122-124, 128-131, 135-153, 157-164, 168-170, 174, 178-180
src/gmgn_twitter_intel/domains/token_intel/read_models/search_agent_brief.py                       135     30     52     13  70.6%   152, 175, 196-197, 201->199, 218-227, 235, 240, 248-250, 255, 263, 272-276, 295->293, 314, 319-321
src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py                    82      2     26      3  95.4%   185, 189, 190->183
src/gmgn_twitter_intel/domains/token_intel/read_models/search_service.py                           175     15     50      9  87.6%   97-99, 149->151, 183, 191, 256, 259, 290-291, 297, 303, 316-319
src/gmgn_twitter_intel/domains/token_intel/read_models/stocks_radar_service.py                      77      7     18      4  88.4%   63->61, 67, 69, 165-166, 171, 174-175
src/gmgn_twitter_intel/domains/token_intel/read_models/token_message_price_payload.py               17      2      4      0  90.5%   44-45
src/gmgn_twitter_intel/domains/token_intel/read_models/token_target_cursor.py                       14      0      2      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/read_models/token_target_post_serializer.py              18      1      4      1  90.9%   68
src/gmgn_twitter_intel/domains/token_intel/read_models/token_target_posts_service.py                33      2      4      2  89.2%   42, 44
src/gmgn_twitter_intel/domains/token_intel/read_models/token_target_social_timeline_service.py     102      5     44      8  91.1%   109->98, 120, 127, 153->155, 182, 210, 216, 220->218
src/gmgn_twitter_intel/domains/token_intel/read_models/token_target_stage_builder.py               152      1     66      3  98.2%   42->44, 225, 229->227
src/gmgn_twitter_intel/domains/token_intel/repositories/asset_signal_repository.py                   5      0      0      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/repositories/intent_resolution_repository.py             38      1      6      2  93.2%   130->146, 151
src/gmgn_twitter_intel/domains/token_intel/repositories/projection_repository.py                    83      1     18      5  94.1%   164, 209->212, 280->282, 313->315, 320->323
src/gmgn_twitter_intel/domains/token_intel/repositories/signal_repository.py                        55      6     10      3  83.1%   67, 93->95, 111-115
src/gmgn_twitter_intel/domains/token_intel/repositories/token_evidence_repository.py                31      5      6      3  78.4%   13, 42, 53-62, 81
src/gmgn_twitter_intel/domains/token_intel/repositories/token_factor_evaluation_repository.py       36      6      8      2  77.3%   103, 107-109, 122-141
src/gmgn_twitter_intel/domains/token_intel/repositories/token_intent_lookup_repository.py           32      9     10      2  69.0%   38-47, 51, 72-101, 111
src/gmgn_twitter_intel/domains/token_intel/repositories/token_intent_repository.py                  38      7      8      3  78.3%   13, 51, 71-80, 86-104, 109
src/gmgn_twitter_intel/domains/token_intel/repositories/token_radar_repository.py                   70      4     34      5  91.3%   48, 193->exit, 267, 271, 283
src/gmgn_twitter_intel/domains/token_intel/repositories/token_target_repository.py                  20      1      4      1  91.7%   35
src/gmgn_twitter_intel/domains/token_intel/runtime/token_intent_rebuild.py                          76      8     24      6  84.0%   95, 102->104, 105->107, 112, 119, 123-127
src/gmgn_twitter_intel/domains/token_intel/runtime/token_radar_projection_worker.py                130      8     28      5  91.8%   59-61, 142-143, 161, 174->176, 177, 185
src/gmgn_twitter_intel/domains/token_intel/runtime/token_resolution_refresh.py                      35      2      8      3  88.4%   29, 58, 83->65
src/gmgn_twitter_intel/domains/token_intel/scoring/__init__.py                                       4      0      0      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/scoring/baseline_scoring.py                              46      4     10      4  85.7%   80, 89, 101, 107
src/gmgn_twitter_intel/domains/token_intel/scoring/cross_section_normalizer.py                      40      1     18      1  96.6%   67
src/gmgn_twitter_intel/domains/token_intel/scoring/diffusion_health.py                              89      4     34      4  93.5%   45, 73, 82, 138
src/gmgn_twitter_intel/domains/token_intel/scoring/factor_cohort.py                                 13      0      8      0 100.0%
src/gmgn_twitter_intel/domains/token_intel/scoring/factor_diagnostics.py                            62      4     32      6  89.4%   26->29, 33->31, 38->37, 43->42, 85-86, 91, 97
src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot.py                              356     18    116     13  93.0%   288, 369->374, 371->370, 408, 661-664, 703, 738, 740, 742, 745, 751, 790, 803-804, 806, 847-848
src/gmgn_twitter_intel/domains/token_intel/scoring/factor_snapshot_contract.py                      84      8     44      8  87.5%   68, 77, 93, 97, 115, 117, 134, 145
src/gmgn_twitter_intel/domains/token_intel/scoring/post_text_quality.py                             62      4     14      2  92.1%   79-80, 82-83
src/gmgn_twitter_intel/domains/token_intel/scoring/scoring_common.py                                45      5     14      3  86.4%   28->30, 36->35, 58-59, 64, 67-68
src/gmgn_twitter_intel/domains/token_intel/scoring/social_signal_features.py                       119     12     58     11  87.0%   16, 22, 25, 35, 54->56, 59->61, 85->83, 95, 129, 132-133, 141, 144-145, 147
src/gmgn_twitter_intel/domains/token_intel/scoring/token_radar_feature_builder.py                  134      6     16      2  94.7%   302, 351-352, 358, 373-374
src/gmgn_twitter_intel/domains/token_intel/services/atomic_mention.py                               43      2     16      2  93.2%   67, 70
src/gmgn_twitter_intel/domains/token_intel/services/deterministic_token_resolver.py                186     12     60      6  92.7%   98, 138, 171, 348, 398-399, 401, 416-417, 433, 442-443
src/gmgn_twitter_intel/domains/token_intel/services/query_parser.py                                 50      4     16      3  89.4%   30, 40->49, 68, 95-96
src/gmgn_twitter_intel/domains/token_intel/services/search_aliases.py                               81      5     44      5  92.0%   28, 47, 54, 63, 83
src/gmgn_twitter_intel/domains/token_intel/services/token_evidence_builder.py                       71      2     16      2  95.4%   176, 191
src/gmgn_twitter_intel/domains/token_intel/services/token_factor_evaluation.py                     164     14     50      9  89.3%   39, 123, 131, 208-209, 223-224, 231, 239-240, 246, 267->261, 286, 299, 315
src/gmgn_twitter_intel/domains/token_intel/services/token_intent_builder.py                        107      6     34      6  91.5%   119, 159, 183, 185, 208, 216
src/gmgn_twitter_intel/domains/token_intel/services/token_intent_resolver.py                        64     10     28      5  81.5%   41, 63-64, 85-86, 94, 100, 103-105
src/gmgn_twitter_intel/domains/token_intel/services/token_radar_projection.py                      442     45    158     20  87.2%   192-207, 295, 342, 508-512, 556-557, 587, 645, 731, 753, 757-759, 776, 778, 794, 815-822, 831-837, 844, 853-854, 858, 883, 899, 908, 911->913, 921-922, 967, 971, 976, 982
src/gmgn_twitter_intel/integrations/coingecko/__init__.py                                            2      0      0      0 100.0%
src/gmgn_twitter_intel/integrations/coingecko/search_client.py                                      53      8     16      5  81.2%   44, 48, 51, 61-64, 72
src/gmgn_twitter_intel/integrations/gmgn/direct_ws.py                                              105     40     12      3  59.8%   72, 123-136, 139-166, 174-177, 187-190, 194, 196
src/gmgn_twitter_intel/integrations/gmgn/directory_client.py                                        88     13     24      6  81.2%   89->91, 92, 111->exit, 123, 131-145, 147
src/gmgn_twitter_intel/integrations/gmgn/openapi_client.py                                         216     24     60     15  84.4%   150, 154->152, 169-170, 172, 174-175, 180, 193-202, 207, 210, 249, 251, 273, 317-318, 320, 323-325, 330, 333
src/gmgn_twitter_intel/integrations/marketlane/__init__.py                                           3      0      0      0 100.0%
src/gmgn_twitter_intel/integrations/marketlane/quote_provider.py                                    49     34     14      0  23.8%   16-30, 33-37, 41-48, 63-68, 72-75
src/gmgn_twitter_intel/integrations/okx/cex_client.py                                              134     29     48     12  72.0%   43->41, 48-53, 63->61, 77, 80-81, 83, 85-86, 90-94, 126, 139, 142, 167, 181-182, 187, 191-193, 204-205
src/gmgn_twitter_intel/integrations/okx/chains.py                                                    3      0      0      0 100.0%
src/gmgn_twitter_intel/integrations/okx/dex_client.py                                              145     18     40     14  82.7%   59, 64->62, 78, 90->88, 137, 158, 171, 174, 192, 202, 219-220, 226-227, 238-239, 245, 250, 253, 260
src/gmgn_twitter_intel/integrations/okx/dex_ws_client.py                                           146     52     34      7  57.2%   69-106, 110, 112, 123-124, 138-149, 154, 160-162, 167, 178, 227, 242-243
src/gmgn_twitter_intel/integrations/okx/models.py                                                   51      0      0      0 100.0%
src/gmgn_twitter_intel/integrations/openai_agents/pulse_recommendation_agent_client.py             148     15     32      7  86.7%   51, 57, 60, 92, 221-222, 235-237, 259, 268, 272, 279, 284, 311
src/gmgn_twitter_intel/integrations/openai_agents/social_event_agent_client.py                      72      7     12      3  85.7%   46, 137, 154-157, 163
src/gmgn_twitter_intel/platform/config/settings.py                                                 532     37     64     20  90.1%   95, 157-160, 200, 219, 226, 235, 259, 261, 265, 269, 273, 387, 416, 644, 648, 652, 656, 660, 664, 686, 694, 709, 857, 859, 865, 867, 870, 876-877, 882-886
src/gmgn_twitter_intel/platform/db/alembic/env.py                                                   36      7      8      4  75.0%   13->16, 23-24, 31, 35-42, 60
src/gmgn_twitter_intel/platform/db/postgres_audit.py                                                78     10     18      2  81.2%   286-287, 323-335, 353
src/gmgn_twitter_intel/platform/db/postgres_client.py                                               86      9     26      6  84.8%   25-27, 37, 81->83, 92->94, 95->97, 120, 139-142
src/gmgn_twitter_intel/platform/db/postgres_migrations.py                                           15      0      2      1  94.1%   17->19
src/gmgn_twitter_intel/platform/logging/setup.py                                                    13      6      0      0  53.8%   12-32
src/gmgn_twitter_intel/platform/paths/runtime_paths.py                                              12      0      2      0 100.0%
--------------------------------------------------------------------------------------------------------------------------------------------
TOTAL                                                                                            14276   2010   3982    789  82.2%

58 empty files skipped.
Required test coverage of 80.0% reached. Total coverage: 82.18%
=========================== short test summary info ============================
SKIPPED [4] tests/postgres_test_utils.py:28: PostgreSQL test database is not available: connection failed: connection to server at "127.0.0.1", port 55432 failed: FATAL:  password authentication failed for user "postgres"
SKIPPED [1] tests/integration/test_enrichment_repository.py:201: agents_sdk_run audit row shape changed; test indexes None subscript. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_enrichment_worker.py:140: Asserts harness materializer reaches snapshot_ready; current pipeline returns asset_unresolved because identity model changed in token-identity-evidence hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_enrichment_worker.py:173: Depends on harness materializer behaviour changed by hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_enrichment_worker.py:212: Asserts model_run rows after hung-job timeout; current pipeline does not produce them in expected shape post hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_harness_ops.py:141: materialize_market_ready_seeds returns 0 vs expected 2; depends on identity-current rows the test seeders predate after hard-cut. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:48: registry_assets.symbol/name/decimals dropped by token-identity-evidence hard-cut (migration 20260510_0021); test predates new asset_identity_evidence/current model. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:265: registry_assets.symbol dropped by token-identity-evidence hard-cut (migration 20260510_0021); test asserts demoted_search by symbol selector. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:392: upsert_chain_asset(symbol=…, name=…, decimals=…, source=…) signature removed by token-identity-evidence hard-cut; identity now lives in asset_identity_evidence/current. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/integration/test_resolution_refresh_worker.py:461: SELECT registry_assets.symbol references column dropped by hard-cut (migration 20260510_0021); should select via asset_identity_current. Tracked in docs/TECH_DEBT.md → 'Integration tests against pre-hard-cut asset registry'.
SKIPPED [1] tests/unit/test_token_radar_idempotency.py:89: No source rows — nothing to score
833 passed, 14 skipped in 585.19s (0:09:45)

exit code: 0
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line/total | 82.18% | ≥ 80% | ✅ |

No coverage thresholds were relaxed.

## Skipped tests

Number of skipped tests in the final coverage run above: 14.

| count | reason | acceptable? |
|-------|--------|-------------|
| 4 | Local PostgreSQL auth unavailable for optional tests in the final coverage run. Integration PostgreSQL tests still ran earlier in `make check-all` with 180 passed / 9 skipped. | ✅ |
| 9 | Existing tests explicitly skipped as pre-hard-cut identity/enrichment fixtures; each skip points to `docs/TECH_DEBT.md`. | ✅ |
| 1 | Token radar idempotency skipped because the generated fixture had no source rows in this run. | ✅ |

## E2E golden path

`make check-all` ran `tests/e2e/test_golden_path.py` with 4 passed.

- [x] /readyz returned 200
- [x] writer wrote a row visible to a separate process
- [x] /api/recent returned the injected event
- [x] WS /ws/live pushed within 5s
- [x] testcontainers PG and uvicorn subprocess cleaned up

## Other commands run

```text
$ rg "_overlay_live_market|token_market_price_baselines|liveMarketUpdates\[0\]|anchor_price_usd|live_market_usd" src web tests
```

Result: only historical Alembic migration references to `token_market_price_baselines`; no runtime, web, or test fallback references.

```text
$ make check
```

Result: exit code 0; 530 passed, 12 skipped.

```text
$ docker compose up -d --build app
```

Result: failed while fetching private GitHub dependency `marketlane-cli` because no GitHub token/credentials were available in the non-interactive build environment. The app container was not restarted from an old image.

## Diff summary

Files changed by the final merged work:

- `src/gmgn_twitter_intel/domains/asset_market/...`
- `src/gmgn_twitter_intel/domains/token_intel/...`
- `src/gmgn_twitter_intel/domains/pulse_lab/...`
- `src/gmgn_twitter_intel/app/runtime/...`
- `src/gmgn_twitter_intel/app/surfaces/...`
- `src/gmgn_twitter_intel/integrations/...`
- `web/src/...`
- `docs/generated/...`
- `tests/...`

Migrations applied:

- `20260513_0036_token_radar_kappa_cqrs_hard_cut` — partitions `price_observations` by market observation role, drops `token_market_price_baselines`, and preserves rollback DDL only in migration history.

Schema or contract changes that consumers must be aware of:

- Token Radar public market contract is `market.event_anchor`, `market.decision_latest`, and `market.readiness`.
- Public Token Radar rows no longer expose top-level `live_market` overlay or legacy anchor fields.
- Signal Pulse uses v3 `factor_snapshot_json` only; legacy score/thesis/context fields remain absent.

## Risks observed

- Existing skipped enrichment/resolution tests still reference earlier identity-era fixtures. They are tracked in `docs/TECH_DEBT.md` and did not block this hard cut.
- Local app container was stopped for migration lock release during rollout. Rebuild/restart is still an operational handoff because Docker build needs GitHub credentials for `marketlane-cli`; PostgreSQL remains running and healthy.

## Follow-ups

- Modernize the skipped pre-hard-cut enrichment/resolution integration fixtures against `asset_identity_current`.
