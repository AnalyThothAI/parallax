# Verification - LiteLLM Native Agent and News High-Score Alert Hard Cut

**Date:** 2026-05-29
**Worktree:** `.worktrees/litellm-native-agent-news-alert-hard-cut/`
**Branch:** `codex/litellm-native-agent-news-alert-hard-cut`

## Result

- LiteLLM-native execution plane unit/architecture checks passed.
- News high-signal brief and notification rule checks passed.
- Narrative bulk gate and Token Radar repair chain checks passed.
- Notification repository/worker/delivery integration checks passed.
- Missed-wake Token Radar -> Pulse recovery integration checks passed after venue-aware dirty publication and realistic `market_tick_current` seed alignment.

## Commands

```bash
uv run pytest tests/unit/integrations/model_execution tests/unit/test_llm_gateway.py tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_providers_wiring.py -q
# 76 passed
```

```bash
uv run pytest tests/architecture/test_agent_execution_plane_contracts.py tests/architecture/test_agent_model_capability_contracts.py tests/architecture/test_project_structure.py tests/architecture/test_src_domain_architecture.py tests/architecture/test_runtime_lifecycle_hard_cut.py tests/architecture/test_pulse_no_compat.py tests/architecture/test_token_radar_publication_state_hard_cut.py -q
# 74 passed
```

```bash
uv run pytest tests/unit/domains/news_intel tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_notification_rules.py -q
# 206 passed
```

```bash
uv run pytest tests/integration/test_notification_repository.py tests/integration/test_notification_worker.py tests/integration/test_notification_delivery.py -q
# 22 passed
```

```bash
uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_narrative_mention_and_digest_wake_waiters tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_hard_gates_narrative_bulk_queue_producers tests/unit/test_token_radar_projection.py::test_projection_runtime_gate_suppresses_narrative_admission_dirty_targets tests/unit/test_token_radar_projection_worker.py::test_projection_worker_calls_dirty_incremental_projection_not_window_rebuild -q
# 4 passed
```

```bash
uv run pytest tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_marks_claim_done_with_payload_hash tests/unit/test_token_radar_projection.py::test_projection_runtime_gate_suppresses_narrative_admission_dirty_targets tests/unit/domains/token_intel/test_token_radar_rank_source_query.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py -q
# 14 passed
```

```bash
uv run pytest tests/integration/test_worker_missed_wake_recovery.py tests/golden/test_token_radar_corpus.py tests/integration/test_token_radar_idempotency.py tests/integration/test_cli.py::CliTests::test_recent_search_asset_flow_social_enrichment_and_alerts_use_postgres_runtime_store -q
# 8 passed
```

```bash
uv run ruff check src/parallax/domains/token_intel/services/token_radar_projection.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py tests/integration/test_worker_missed_wake_recovery.py tests/golden/test_token_radar_corpus.py
# All checks passed
```

```bash
uv run python -m compileall -q src/parallax/app/runtime src/parallax/integrations/model_execution src/parallax/platform src/parallax/domains/news_intel src/parallax/domains/pulse_lab src/parallax/domains/token_intel
# exit 0
```

```bash
rg -n "from openai|import openai|from agents|import agents|integrations\.openai_agents|OpenAIAgents|openai_agents_sdk|openai_compatible|provider=\"openai\"|AsyncOpenAI|Runner\.run|RunConfig\(|Agent\(|ModelBehaviorError" src tests pyproject.toml --glob '!src/parallax/platform/db/alembic/versions/202605*_*.py'
# no matches
```
