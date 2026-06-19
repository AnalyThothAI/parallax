# Verification — News Story Agent Hard Cut

**Status**: In Progress
**Date**: 2026-06-18
**Owning spec**: `docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut/plan.md`
**Branch**: `codex/news-trading-agent-architecture-research`
**Worktree**: `.worktrees/news-trading-agent-architecture-research/`
**Approved by**: delegated goal
**Approved at**: 2026-06-18
**Diff**: Backend story-current implementation, runtime wiring, architecture docs, and SDD artifacts. No frontend files changed.

The plan and spec are the contract. This file records completed non-integration implementation evidence for the current backend slice and calls out deferred integration/runtime gates separately.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — same canonical item enqueues story work at most once per story watermark. | Pass | `uv run pytest tests/integration/domains/news_intel/test_news_story_agent_repository.py::test_same_canonical_item_enqueues_one_story_brief_target -q` passed after the migration was fixed to drop the stale `news_projection_dirty_targets_target_kind_check` constraint. |
| AC2 — similar story without material delta does not call model. | Pass | `uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py::test_similar_story_without_material_delta_skips_model -q` passed; `uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_similar_story_without_material_delta_enqueues_page_only -q` passed and proves item processing enqueues page work only, with no `brief_input` or `story_brief` model work. `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_admission_representative_current_state_uses_story_briefs tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_admission_representative_current_state_uses_story_current -q` passed and proves admission duplicate/same-story representative current-state joins use story-current rows, not item-current rows. |
| AC3 — material story delta refreshes one current story brief. | Pass | `uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py::test_material_delta_refreshes_one_story_current_brief -q` passed; `uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_material_story_delta_enqueues_one_story_brief_refresh -q` passed and proves one stable `story_brief/story` refresh target is enqueued. `tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_admitted_crypto_row_enqueues_page_and_story_brief_with_story_key` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_enqueues_story_brief_not_item_brief_after_hard_cut` prove item processing no longer auto-enqueues `brief_input` item-brief work or wakes the item-brief worker from `news_item_processed`. `tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_rejects_market_scope_aliases` proves story packet input requires formal `market_scope_json.scope` / `primary` context instead of accepting retired top-level aliases, nested aliases, or bare list/string payloads. `tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_rejects_context_aliases` and `tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_does_not_restore_material_or_similarity_from_agent_admission_basis` prove story packets require formal story context JSON fields and do not repair material/similarity context from admission-basis compatibility payloads. Current-row uniqueness is covered by `tests/integration/domains/news_intel/test_news_story_agent_repository.py::test_story_current_brief_key_is_stable_story_identity`. |
| AC4 — matching current/completed run skips model call. | Pass | `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_restores_completed_story_run_without_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_restores_failed_current_from_started_failed_story_run_without_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_current_story_brief_missing_status_before_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_current_story_brief_missing_input_hash_before_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_response_before_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_input_hash_before_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_ready_payload_missing_summary_before_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_ready_payload_summary_missing_without_market_read_fallback`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_run_id_before_restore_or_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_story_brief_key_before_restore_or_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_outcome_before_second_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_outcome_before_restore_or_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_finished_at_without_clock_fallback`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_error_class_before_restore_or_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_error_before_restore_or_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_execution_started_before_restore_or_model_call`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_latency_without_zero_default`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_usage_without_empty_default`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_trace_metadata_without_empty_default`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_claim_missing_story_target_id_without_marking_done`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_provider_error_audit_output_hash_does_not_repair_missing_explicit_output_hash`; `tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_rejects_ready_without_publishable_summary`; `tests/architecture/test_news_intel_kiss_simplification.py::test_news_brief_workers_do_not_restore_missing_output_hash_from_audit_payload`; `tests/architecture/test_news_intel_kiss_simplification.py::test_news_brief_validation_publishable_text_requires_current_summary_field`; `tests/unit/domains/news_intel/test_news_story_brief_worker.py` also proves request-audit/no-start backpressure requeues without a business ledger or attempt burn, provider-started failures write a failed run ledger, story result audit requires explicit latency, usage, and trace metadata, current story brief reuse requires explicit current identity/status/hash/version fields, completed/failed latest-run reuse requires explicit run status/story identity/hash/version fields, completed-run restore and fresh ready validation require explicit publishable `summary_zh` without a `market_read_zh` fallback, completed/failed run restore requires explicit ledger `outcome`, `finished_at_ms`, and failed-run `execution_started`, provider-error audit payloads cannot repair a missing explicit run `output_hash`, completed-run status accounting reads explicit persisted `outcome`, failed-run restore requires explicit `error_class` and `error`, and malformed story dirty-target claims are marked error rather than silently completed. `tests/unit/domains/news_intel/test_news_story_brief_stage.py` proves the story stage reserves `news.story_brief` and references only the story-current read context. |
| AC5 — page/detail rows read story current without old item fallback. | Pass | `tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_page_rows_read_story_brief_without_item_brief_fallback`; `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_detail_reads_agent_current_from_projected_page_row_only -q` passed and proves item detail reads projected `page_agent_brief` only. `uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_load_items_for_page_projection_filters_target_items_before_projection_joins -q` passed and proves the page projection item loader does not join or return item-current brief state. `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_text_identity_before_write`, `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_agent_brief_status_before_write`, `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_rejects_agent_status_mismatch_before_write`, `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_summary_fields_before_write`, `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_display_strings_before_write`, `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_agent_admission_fields_before_write`, `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_rejects_agent_admission_mismatch_before_write`, `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults`, `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_summary_fields_require_explicit_payload_without_defaults`, and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_has_no_retired_agent_admission_public_payload_repair` prove page-row writes fail missing serving/display/summary/admission identity instead of repairing it from raw item, admission payload fields, or repository defaults. `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_rejects_claim_missing_target_id_without_marking_done` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_worker_requires_claim_contract_without_target_id_filtering` prove the page projection writer fails malformed claimed dirty-target identity instead of filtering it out and marking the row done. `tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_current_agent_brief` proves missing current brief is the only pending path; malformed present story-current brief state fails instead of being downgraded to pending. `tests/unit/domains/news_intel/test_news_page_projection.py::test_ready_brief_without_summary_zh_does_not_use_market_read_for_external_push` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_external_push_publishable_summary_requires_current_summary_field` prove external push publishability requires explicit current `summary_zh` and does not fall back to legacy `market_read_zh`. `tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_missing_required_item_projection_context`, `tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_required_item_projection_context`, `tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_requires_item_content_projection_fields`, `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope`, and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback` prove page projection fails missing or mismatched `market_scope_json` / `agent_admission_json` context, item content projection fields, and story projection member/source/timing/story-identity fields instead of defaulting to `{}`, `[]`, `0`, `source_id`, or `source_domain`. `tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_does_not_restore_from_legacy_alias_fields` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_has_no_legacy_alias_fallbacks` prove derived page search text uses current projected `*_json` fields only and does not restore source/token/fact search terms from legacy aliases. `tests/unit/test_api_news_contract.py::test_news_public_agent_brief_requires_status_without_pending_default`, `tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields`, and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate` prove public shaping allowlists projected brief fields without downgrading story-current payloads through the old item-brief schema gate or defaulting missing projected status to pending. `tests/unit/test_api_notifications_contract.py` and `tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads` prove News high-signal notification shaping rejects malformed or missing `payload_json` plus malformed present `agent_brief`, `affected_entities`, and `token_impacts` sections instead of repairing them to empty public payloads. `tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback` prove high-signal notification candidates require explicit projected `news_item_id` and `representative_news_item_id` instead of deriving either identity from the other. `tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current` proves page projection listens to story-current updates, not audit-only item-brief updates. |
| AC6 — old item outputs remain audit-only. | Pass | `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q` passed and proves story projection/current serving paths plus the read-only agent context registry read `news_story_agent_briefs`, not `news_item_agent_briefs`; `uv run pytest tests/unit/platform/test_agent_read_tools.py tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/domains/news_intel/test_news_story_brief_stage.py tests/architecture/test_agent_harness_cleanup_contracts.py -q` passed and proves `news.current_briefs` is not a runtime tool name while `news.story_current_briefs` is story-current only; `uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_detail_requires_projected_page_row_contract_without_raw_item_fallbacks -q` passed and prevents item detail from querying item brief/run audit tables as public current state. `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_writes_ready_brief_and_emits_wake` plus `tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_current_write_does_not_dirty_page_projection` prove item-brief current writes no longer enqueue page reprojection. `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_claim_missing_target_id_without_marking_done` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_requires_claim_contract_without_target_id_fallback` prove explicit item-brief audit targets fail malformed claimed identity instead of being completed through empty target-id fallback. `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_loaded_candidate_missing_item_identity_without_marking_target_done`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback`, `tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_market_scope_from_agent_admission_basis`, `tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_similarity_or_material_delta_from_agent_admission_basis`, `tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_context_from_legacy_item_aliases`, `tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_context_objects`, `tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_rejects_malformed_present_context_objects`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_does_not_restore_packet_context_from_admission_basis`, `tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_does_not_restore_status_from_scalar_alias`, `tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_does_not_restore_scope_from_legacy_aliases`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_execute_no_start_rate_limit_does_not_write_business_ledger`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_publishable_validation_missing_payload_without_empty_default`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_current_brief_missing_identity_before_second_model_call`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_failed_run_missing_identity_before_restore_or_model_call`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_missing_outcome_before_restore_or_model_call`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_missing_finished_at_without_clock_fallback`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_invalid_completed_run_missing_source_identity_before_audit_repair`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_agent_run_audit_without_request_audit_fallback`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_latency_without_zero_default`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_usage_without_empty_default`, `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_trace_metadata_without_empty_default`, and `tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_audit_identity_without_defaults` prove the retained audit-only item-brief lane also fails closed instead of completing malformed candidate targets as missing, repairing malformed repository admission context from candidate sidecars, restoring packet context from admission basis or legacy item aliases, accepting malformed present packet context as `{}`, injecting admission-basis context back into packet fields, treating scalar admission status or market-scope aliases as priority inputs, treating malformed current/failed run rows as stale model work, writing `{}` for missing publishable validation payloads, repairing completed-run `outcome` to `ready`, using current time for missing completed-run `finished_at_ms`, defaulting invalid source audit identity or failed-run error details, falling back from missing result audit to request audit, defaulting result audit fields to `0` / `{}`, or restoring audit identity scalar fields from provider/config/packet defaults. `tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_admission_representative_current_state_uses_story_briefs` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_admission_representative_current_state_uses_story_current` prove old item-current rows no longer drive admission representative current-state decisions. `tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_enqueues_story_brief_not_item_brief_after_hard_cut` proves new item processing does not produce item-brief audit work automatically. |
| AC7 — retired story tables/projection names are not recreated and denormalization is cache/index only. | Pass | Migration/test coverage adds `story_brief` dirty targets and rejects retired `story`; no `news_story_groups` or `news_story_members` tables were added. `tests/unit/test_postgres_schema.py::test_news_story_agent_hard_cut_migration_requires_explicit_story_agent_payloads` proves new story agent tables do not carry DB defaults that would bypass explicit run/current payload contracts. `tests/unit/domains/news_intel/test_news_repository_queries.py::test_insert_news_story_agent_run_requires_explicit_audit_scalar_fields` and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_payloads_require_explicit_audit_json_inputs` prove story run repository writes require explicit audit `backend` and `latency_ms` instead of defaulting to `litellm_sdk` / `0`. `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_requires_target_identity_before_sql`, `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_window_for_windowless_targets_before_sql`, and `tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_enqueue_requires_target_identity_without_silent_drop` prove dirty-target enqueue fails closed instead of silently dropping malformed target identity rows. |

Additional AC6 evidence: `tests/unit/test_ops_projection_dirty_targets.py` and `tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset` prove ops dirty-target repair reads formal `agent_admission_json` and does not restore brief eligibility or priority from scalar `agent_admission_status`.

Deviations from spec:

- Frontend/UI files were not touched in this backend slice.
- Full `make check-all`, `make test-integration`, and runtime golden-path checks are deferred by explicit user instruction on 2026-06-18. This active SDD record stays `In Progress` rather than `Verified`.

Deviations from plan:

- The first AC1 integration run exposed a real schema issue: migration `20260618_0181` added the composite story-aware dirty-target check but did not drop the original `news_projection_dirty_targets_target_kind_check`. The migration now drops that stale check before accepting `story_brief/story` targets.

## Verification commands

Artifact and implementation checks run from the worktree root:

```text
$ python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ wc -m docs/references/news-agent-trading-research-2026-06-18.md
   32477 docs/references/news-agent-trading-research-2026-06-18.md
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_retired_story_projection_name tests/unit/domains/news_intel/test_news_repository_queries.py -q
270 passed in 2.95s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_requires_target_identity_before_sql tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_window_for_windowless_targets_before_sql tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_enqueue_requires_target_identity_without_silent_drop -q
14 passed in 0.48s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py -q
108 passed in 0.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
84 passed in 2.49s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5769 passed, 2 skipped in 50.09s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_loads_only_claimed_news_item_targets_and_marks_done_with_tokens tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_rejects_claim_missing_target_id_without_marking_done tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_worker_requires_claim_contract_without_target_id_filtering -q
3 passed in 0.54s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_page_projection_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
mypy failed: `_required_page_claim_news_item_ids` accepted `list[Mapping[str, Any]]`; caller passed `list[dict[str, Any]]`.
exit code: 2

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_loads_only_claimed_news_item_targets_and_marks_done_with_tokens tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_rejects_claim_missing_target_id_without_marking_done tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_worker_requires_claim_contract_without_target_id_filtering -q
3 passed in 0.35s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_page_projection_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5771 passed, 2 skipped in 42.19s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_requires_repository_session_transaction_for_policy_skip_completion tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_claim_missing_target_id_without_marking_done tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_policy_skip_exact_duplicate_does_not_call_model tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_requires_claim_contract_without_target_id_fallback -q
4 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
31 passed in 0.24s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
86 passed in 2.95s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py -q
96 passed in 0.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
85 passed in 2.29s
exit code: 0

$ rg -n "news_market_reaction|reaction_snapshot|news_event_signals|news_trading|NewsTrading|trading brief" docs/references/news-agent-trading-research-2026-06-18.md docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut/spec.md docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut/plan.md docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut/tasks.md
exit code: 1

$ rg -n "[ \t]$" docs/references/news-agent-trading-research-2026-06-18.md docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
docs/generated/sdd-work-index.md is stale; run `uv run python scripts/regen_sdd_work_index.py`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_cli_help.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_ws_protocol.py --check
exit code: 0

$ git diff --check
exit code: 0

$ make check-all
SDD artifact validation passed.
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
All checks passed!
1077 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5718 passed, 2 skipped in 42.47s.
Stopped at integration setup: `make test-integration` collected 492 items and all errored with "Integration tests require a reachable Postgres but none was found."
exit code: 2

$ make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5730 passed, 2 skipped in 42.10s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py -q
9 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
10 passed in 0.24s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_requires_claim_contract_without_target_id_fallback -q
11 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
Would reformat: tests/architecture/test_news_intel_kiss_simplification.py
1 file would be reformatted, 1077 files already formatted
exit code: 2

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format tests/architecture/test_news_intel_kiss_simplification.py
1 file reformatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_requires_claim_contract_without_target_id_fallback -q
11 passed in 0.24s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5755 passed, 2 skipped in 45.84s.
compileall completed for src and tests.
exit code: 0

$ rg -n 'target\.get\("target_id"\)|str\(target\.get\("target_id"\)' src/parallax/domains/news_intel/runtime/news_story_brief_worker.py
exit code: 1

$ rg -n 'fallback|compat|legacy|hasattr|getattr|or \{\}|or \[\]' src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/services/news_story_brief_stage.py src/parallax/domains/news_intel/types/news_story_brief.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_text_identity_before_write tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults -q
7 passed in 0.46s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields tests/unit/test_api_news_contract.py::test_news_item_detail_hides_agent_runtime_audit_fields tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
3 passed in 1.79s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_fetch_by_default tests/unit/test_worker_settings.py::test_news_workers_have_defaults tests/architecture/test_worker_inventory_contract.py::test_documented_wake_inputs_match_default_worker_settings tests/architecture/test_worker_inventory_contract.py::test_wake_bus_notify_channels_are_documented_as_wake_outputs tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current -q
5 passed in 3.71s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/runtime/worker_manifest.py src/parallax/platform/config/settings.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_brief_worker_does_not_enqueue_page_dirty_after_current_brief_write tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_writes_ready_brief_and_emits_wake tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_current_write_does_not_dirty_page_projection -q
3 passed in 0.38s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
110 passed in 2.36s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ make test-integration
collected 492 items
492 errors: Integration tests require a reachable Postgres but none was found.
exit code: 2

$ rg -n 'fallback|compat|legacy|hasattr|getattr|or \{\}|or \[\]' src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/services/news_story_brief_stage.py src/parallax/domains/news_intel/types/news_story_brief.py
exit code: 1

$ rg -n 'news_story_groups|news_story_members|projection_name = '\''story'\''|projection_name = "story"' src/parallax/domains/news_intel src/parallax/app src/parallax/platform/config src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py tests/architecture tests/unit/test_postgres_schema.py tests/unit/domains/news_intel tests/integration/domains/news_intel/test_news_story_agent_repository.py tests/integration/domains/news_intel/test_news_page_rows_read_path.py docs/ARCHITECTURE.md docs/WORKERS.md docs/CONTRACTS.md docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut
matches only docs/architecture notes and tests that assert the retired names stay absent; no runtime recreation.
exit code: 0
```

Executed acceptance commands added in this pass:

```text
$ uv run pytest tests/integration/domains/news_intel/test_news_story_agent_repository.py::test_same_canonical_item_enqueues_one_story_brief_target -q
1 passed in 11.29s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py::test_similar_story_without_material_delta_skips_model -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py::test_material_delta_refreshes_one_story_current_brief -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_similar_story_without_material_delta_enqueues_page_only tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_material_story_delta_enqueues_one_story_brief_refresh -q
2 passed in 0.64s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
1 passed in 0.13s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
73 passed in 2.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut
Offender: fallback_item
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
1 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
73 passed in 2.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/integration/domains/news_intel/test_news_story_agent_repository.py::test_same_canonical_item_enqueues_one_story_brief_target -q
ERROR at setup: Integration tests require a reachable Postgres but none was found.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_page_rows_read_story_brief_without_item_brief_fallback -q
ERROR at setup: Integration tests require a reachable Postgres but none was found.
exit code: 1

$ make docker-check
Docker daemon is not reachable from this shell.
Start Docker Desktop or grant this terminal access to the Docker socket, then rerun make docker-up.
exit code: 2

$ command -v postgres || true; command -v initdb || true; command -v pg_ctl || true; command -v psql || true
exit code: 0, no paths printed

$ find /opt/homebrew/Cellar /usr/local/Cellar -maxdepth 4 -type f \( -name postgres -o -name initdb -o -name pg_ctl \) -print
exit code: 0, no paths printed

$ DOCKER_HOST=unix:///var/run/docker.sock docker info
Server: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: connect: operation not permitted
exit code: 0 for the captured diagnostic pipeline; Docker server remained unavailable
```

The failed integration reruns above are prior environment availability checks, not current feature verification evidence. Integration and runtime golden-path checks are not rerun in this closeout because the user explicitly deferred them on 2026-06-18.

Targeted pytest and compile checks:

```text
$ uv run pytest tests/architecture/test_projection_worker_idle_cost_contract.py::test_agent_brief_workers_claim_dirty_targets_instead_of_scanning_candidates -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py -q
3 passed in 0.08s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py \
  tests/unit/domains/news_intel/test_news_projection_work.py \
  tests/unit/domains/news_intel/test_news_story_brief_worker.py \
  tests/unit/domains/news_intel/test_news_story_agent_admission.py \
  tests/integration/domains/news_intel/test_news_story_agent_repository.py \
  tests/integration/domains/news_intel/test_news_page_rows_read_path.py::test_page_rows_read_story_brief_without_item_brief_fallback \
  tests/unit/test_postgres_schema.py::test_alembic_revision_graph_has_single_head \
  tests/unit/test_postgres_schema.py::test_news_story_agent_hard_cut_migration_adds_story_current_without_retired_membership \
  tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_agent_run_and_brief_returning_rows_require_cursor_rowcount_match -q
27 passed in 16.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/unit/platform/test_agent_read_tools.py tests/unit/domains/news_intel/test_news_page_projection.py -q
188 passed in 7.60s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_accepts_story_brief_story_targets tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_story_brief_item_targets tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_retired_story_projection_name tests/unit/domains/news_intel/test_news_workers.py -q
45 passed in 0.70s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_agent_admission.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_accepts_story_brief_story_targets tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_story_brief_item_targets tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_retired_story_projection_name tests/unit/domains/news_intel/test_news_workers.py -q
65 passed in 0.39s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_worker_runtime_contracts.py tests/unit/platform/test_agent_read_tools.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_api_news_contract.py -q
270 passed in 6.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_worker_manifest_static_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
237 passed in 0.95s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_accepts_story_brief_story_targets tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_dirty_target_repository_rejects_story_brief_item_targets -q
59 passed in 0.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_input.py -q
5 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
1 passed in 0.06s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/domains/news_intel/test_news_item_brief_types.py tests/unit/domains/news_intel/test_news_item_brief_input.py -q
82 passed in 0.37s
exit code: 0

$ uv run pytest tests/unit/test_api_news_contract.py -q
9 passed in 1.18s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_detail_reads_agent_current_from_projected_page_row_only -q
1 passed in 0.15s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_detail_requires_projected_page_row_contract_without_raw_item_fallbacks -q
1 passed in 0.16s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py tests/unit/test_api_news_contract.py -q
352 passed in 3.54s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_load_items_for_page_projection_filters_target_items_before_projection_joins -q
1 passed in 0.41s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py tests/unit/test_api_news_contract.py -q
434 passed in 3.58s
exit code: 0

$ python -m compileall -q src/parallax/domains/news_intel src/parallax/app/runtime src/parallax/integrations/model_execution src/parallax/platform/config
exit code: 0

$ rg -n "news\\.current_briefs" src/parallax tests/unit tests/architecture -g '*.py'
matches only architecture assertions that reject the retired tool name.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/platform/test_agent_read_tools.py tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/domains/news_intel/test_news_story_brief_stage.py tests/architecture/test_agent_harness_cleanup_contracts.py tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
13 passed in 0.60s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_worker_settings.py::test_agent_runtime_settings_default_lanes tests/unit/test_worker_settings.py::test_agent_runtime_settings_partial_lane_override_preserves_default_lanes tests/unit/test_worker_settings.py::test_agent_runtime_settings_accepts_news_story_brief_lane_override tests/unit/test_worker_settings.py::test_agent_runtime_capability_fields_default_to_model_registry tests/unit/test_settings.py::test_agent_runtime_lane_model_can_override_default_model tests/architecture/test_agent_harness_cleanup_contracts.py::test_narrative_llm_workers_are_hard_removed_from_runtime_contract tests/unit/test_provider_wiring_agent_execution_gateway.py::test_wire_providers_passes_one_agent_execution_gateway_to_model_execution_factories tests/unit/test_providers_wiring.py::test_litellm_providers_receive_agent_execution_gateway -q
8 passed in 4.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py -q
5 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
273 passed in 0.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
74 passed in 2.32s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_api_news_contract.py -q
315 passed in 1.83s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
75 passed in 2.72s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/runtime/news_page_projection_worker.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_stage.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_stage.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/platform/test_agent_read_tools.py tests/unit/test_settings.py tests/unit/test_worker_settings.py tests/unit/test_providers_wiring.py tests/unit/test_provider_wiring_agent_execution_gateway.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_postgres_schema.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_agent_harness_cleanup_contracts.py -q
783 passed in 8.51s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback -q
15 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py -q
151 passed in 0.45s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_api_news_contract.py -q
302 passed in 1.49s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
78 passed in 2.28s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_stage.py::test_story_stage_uses_story_current_read_tool tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current -q
2 passed after regenerating `docs/generated/sdd-work-index.md`; the earlier parallel run raced with index regeneration and failed the index-current assertion before the writer completed.
exit code: 0

$ python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5749 passed, 2 skipped in 42.48s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_admission_representative_current_state_uses_story_briefs tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_admission_representative_current_state_uses_story_current -q
2 passed in 0.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
280 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
81 passed in 2.66s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_news_story_agent_admission.py tests/unit/domains/news_intel/test_news_story_similarity.py -q
16 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_similar_story_without_material_delta_enqueues_page_only tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_material_story_delta_enqueues_one_story_brief_refresh -q
2 passed in 0.41s
exit code: 0

$ python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5751 passed, 2 skipped in 45.77s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_item_brief_when_configured tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_story_brief_when_configured tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_enqueues_story_brief_not_item_brief_after_hard_cut -q
38 passed in 4.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_worker_manifest_static_contracts.py tests/architecture/test_worker_runtime_contracts.py::test_news_item_brief_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults tests/unit/test_bootstrap_worker_runtime_wiring.py tests/unit/test_worker_settings.py -q
111 passed in 3.80s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py -q
206 passed in 2.41s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_process_worker.py src/parallax/app/runtime/worker_manifest.py src/parallax/platform/config/settings.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/test_worker_settings.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5753 passed, 2 skipped in 43.08s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
10 passed in 0.63s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ rg -n 'fallback|compat|legacy|hasattr|getattr|or \{\}|or \[\]' src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/services/news_story_brief_stage.py src/parallax/domains/news_intel/types/news_story_brief.py
exit code: 1

$ rg -n "NewsStoryAgentWorker|-> news_story_agent" docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut docs/ARCHITECTURE.md docs/WORKERS.md docs/CONTRACTS.md docs/AGENT_EXECUTION.md src/parallax/domains/news_intel/ARCHITECTURE.md
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5753 passed, 2 skipped in 59.10s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_requires_repository_session_transaction_for_policy_skip_completion tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_claim_missing_target_id_without_marking_done tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_policy_skip_exact_duplicate_does_not_call_model tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_requires_claim_contract_without_target_id_fallback -q
4 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ rg -n 'target\.get\("target_id"\)|str\(target\.get\("target_id"\)' src/parallax/domains/news_intel/runtime/news_item_brief_worker.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5773 passed, 2 skipped in 45.58s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_postgres_schema.py::test_news_story_agent_hard_cut_migration_adds_story_current_without_retired_membership tests/unit/test_postgres_schema.py::test_news_story_agent_hard_cut_migration_requires_explicit_story_agent_payloads tests/architecture/test_news_intel_kiss_simplification.py -q
390 passed in 2.98s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_postgres_schema.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ rg -n "DEFAULT '\\[\\]'::jsonb|DEFAULT '\\{\\}'::jsonb|DEFAULT false|DEFAULT 0" src/parallax/platform/db/alembic/versions/20260618_0181_news_story_agent_hard_cut.py
exit code: 1

$ rg -n 'agent_brief\.get\("status"\) or brief_json\.get\("status"\)|agent_brief\.get\("direction"\) or brief_json\.get\("direction"\)|agent_brief\.get\("decision_class"\) or brief_json\.get\("decision_class"\)|return payload or \{"status": "pending"\}' src/parallax/domains/news_intel/services/news_page_projection.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5776 passed, 2 skipped in 43.73s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_missing_required_item_projection_context tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_required_item_projection_context -q
9 failed as expected before hard-cut implementation; old code did not raise for missing or malformed page projection context.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback -q
33 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_postgres_schema.py::test_news_story_agent_hard_cut_migration_adds_story_current_without_retired_membership tests/unit/test_postgres_schema.py::test_news_story_agent_hard_cut_migration_requires_explicit_story_agent_payloads tests/architecture/test_news_intel_kiss_simplification.py -q
400 passed in 2.74s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ rg -n "item\.get\(\"agent_admission_status\"\) or \"needs_review\"|item\.get\(\"agent_admission_reason\"\) or \"\"|_json_object\(item\.get\(\"market_scope_json\"\)\)|_json_object\(item\.get\(\"agent_admission_json\"\)\)|payload\.get\(\"status\"\) or status or \"needs_review\"|payload\.get\(\"representative_news_item_id\"\) or representative_news_item_id" src/parallax/domains/news_intel/services/news_page_projection.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_loads_only_claimed_news_item_targets_and_marks_done_with_tokens tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_reads_formal_settings_for_claim_session_and_retry tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_deletes_missing_claimed_items_without_fallback_scan tests/unit/domains/news_intel/test_news_workers.py::test_news_page_projection_worker_replaces_rows_without_emitting_wake tests/unit/domains/news_intel/test_news_workers.py::test_news_page_projection_worker_projects_same_story_once tests/unit/domains/news_intel/test_news_workers.py::test_news_page_projection_worker_reports_deleted_story_member_rows tests/unit/domains/news_intel/test_news_workers.py::test_news_page_projection_worker_reports_unchanged_story_projection -q
7 passed in 0.41s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope -q
170 passed in 0.42s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/architecture/test_news_intel_kiss_simplification.py
5 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5786 passed, 2 skipped in 42.65s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_text_identity_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_agent_admission_fields_before_write -q
9 failed as expected before hard-cut implementation; old code continued into page-row INSERT instead of rejecting missing top-level or nested admission fields.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_has_no_retired_agent_admission_public_payload_repair -q
1 failed as expected before removing `_agent_admission_public_payload`; the helper still contained `needs_review` and default-version repair.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_text_identity_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_agent_admission_fields_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_rejects_agent_admission_mismatch_before_write -q
18 passed in 0.16s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_has_no_retired_agent_admission_public_payload_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope -q
326 passed in 0.83s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ rg -n 'def _agent_admission_public_payload|row\.get\("agent_admission_status"\) or payload\.get\("status"\) or "needs_review"|row\.get\("agent_admission_reason"\) or payload\.get\("reason"\) or ""|row\.get\("agent_representative_news_item_id"\)\s*or payload\.get\("representative_news_item_id"\)' src/parallax/domains/news_intel/repositories/news_repository.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5799 passed, 2 skipped in 45.59s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_text_identity_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_agent_brief_status_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_rejects_agent_status_mismatch_before_write -q
6 failed, 10 passed as expected before hard-cut implementation; old code repaired missing `content_class` / `agent_status`, ignored missing nested `agent_brief.status`, and continued into page-row INSERT.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_summary_fields_before_write -q
10 failed as expected before hard-cut implementation; old `_apply_page_row_summary` repaired missing cache/index summary fields to empty strings, `1`, or empty arrays.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_display_strings_before_write -q
8 failed as expected before hard-cut implementation; old `_page_row_payload` stringified or defaulted missing display fields before INSERT.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_text_identity_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_agent_brief_status_before_write tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_rejects_agent_status_mismatch_before_write -q
16 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_summary_fields_before_write -q
10 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_display_strings_before_write -q
8 passed in 0.13s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_summary_fields_require_explicit_payload_without_defaults -q
2 passed in 0.23s
exit code: 0

$ rg -n 'str\(payload\.get\("content_class"\) or "low_signal"\)|str\(payload\.get\("agent_status"\) or "pending"\)|payload\["(headline|canonical_url|summary|search_text)"\] = str\(payload\.get|payload\.get\("canonical_item_key"\) or summary\.get|payload\.get\("duplicate_count"\) or summary\.get|payload\.get\("source_ids_json"\) or summary\.get|payload\.get\("source_domains_json"\) or summary\.get|payload\.get\("provider_article_keys_json"\) or summary\.get' src/parallax/domains/news_intel/repositories/news_repository.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_has_no_retired_agent_admission_public_payload_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_summary_fields_require_explicit_payload_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope -q
351 passed in 0.57s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5824 passed, 2 skipped in 49.56s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback -q
1 failed as expected before hard-cut implementation; `_required_agent_signal_status` did not exist and page projection still contained secondary `or "pending"` agent-status repair.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_similar_story_context_requires_story_identity_version_without_default -q
1 failed as expected before hard-cut implementation; `_agent_similar_story_context` defaulted missing `story_identity_version` to `NEWS_STORY_IDENTITY_VERSION` and continued into SQL.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_admission_representative_current_state_uses_story_current tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_similar_story_context_requires_story_identity_version_without_default -q
3 passed in 0.12s
exit code: 0

$ rg -n 'str\(agent_payload\.get\("status"\) or "pending"\)|str\(agent_signal\.get\("status"\) or "pending"\)|item\.get\("story_identity_version"\) or NEWS_STORY_IDENTITY_VERSION' src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_admission_representative_current_state_uses_story_current -q
351 passed in 0.37s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
4 files already formatted
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5826 passed, 2 skipped in 42.21s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_requires_status_without_pending_default -q
1 failed as expected before hard-cut implementation; `_public_agent_brief_payload` defaulted missing projected public status to pending.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_requires_item_content_projection_fields -q
3 failed as expected before hard-cut implementation; page projection accepted missing `content_class`, `content_tags_json`, and `content_classification_json`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_requires_status_without_pending_default tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields -q
2 passed in 0.90s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_requires_item_content_projection_fields tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_copies_item_level_content_classification -q
4 passed in 0.07s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py -q
138 passed in 0.84s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
7 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5830 passed, 2 skipped in 46.39s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_rejects_market_scope_aliases -q
3 failed as expected before hard-cut implementation; packet construction accepted top-level and nested market-scope aliases instead of requiring formal story context.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_finished_at_without_clock_fallback -q
1 failed as expected before hard-cut implementation; completed-run restore used the worker clock fallback for missing `finished_at_ms`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_error_class_before_restore_or_model_call -q
1 failed as expected before hard-cut implementation; failed-run restore defaulted missing `error_class` to `story_brief_failed`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
24 passed in 0.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
5 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5835 passed, 2 skipped in 44.42s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
1 failed as expected before hard-cut implementation; completed-run restore status accounting still allowed a `ready` outcome fallback.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_error_before_restore_or_model_call -q
1 failed as expected before hard-cut implementation; failed-run current restore used `error_class` as the fallback failure message.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
14 passed in 0.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_missing_outcome_before_restore_or_model_call -q
1 failed as expected before hard-cut implementation; missing completed item-run `outcome` triggered a second model request through an empty/ready fallback path.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_latency_without_zero_default -q
1 failed as expected before hard-cut implementation; missing item result audit latency wrote an item run with default zero latency.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_usage_without_empty_default tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_trace_metadata_without_empty_default -q
2 failed as expected before hard-cut implementation; missing item result audit usage/trace metadata wrote item runs with empty audit objects.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
35 passed in 0.28s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.09s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5836 passed, 2 skipped in 53.70s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_insert_news_story_agent_run_requires_explicit_audit_scalar_fields -q
2 failed as expected before hard-cut implementation; story run repository writes defaulted missing `backend` to `litellm_sdk` and missing `latency_ms` to `0`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_insert_news_story_agent_run_requires_explicit_audit_scalar_fields tests/unit/domains/news_intel/test_news_repository_queries.py::test_insert_news_story_agent_run_requires_explicit_audit_json_fields tests/unit/domains/news_intel/test_news_repository_queries.py::test_insert_news_story_agent_run_requires_non_empty_member_ids tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_payloads_require_explicit_audit_json_inputs -q
5 passed in 0.24s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5838 passed, 2 skipped in 45.39s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback -q
1 failed as expected before hard-cut implementation; story projection payload construction accepted missing member/source/timing/story identity fields through item/source fallback defaults.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_summary_fields_require_explicit_payload_without_defaults tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_detail_reads_agent_current_from_projected_page_row_only -q
37 passed in 0.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/architecture/test_news_intel_kiss_simplification.py
2 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5838 passed, 2 skipped in 46.14s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_outcome_before_second_model_call tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_outcome_before_restore_or_model_call -q
2 failed as expected before hard-cut implementation; missing persisted `outcome` on matching completed/failed runs fell through to a second agent request.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
16 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5840 passed, 2 skipped in 44.57s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_current_story_brief_missing_status_before_second_model_call tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_current_story_brief_missing_input_hash_before_second_model_call -q
2 failed as expected before hard-cut implementation; malformed matching current story brief rows fell through to a second agent request.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
18 passed in 0.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5842 passed, 2 skipped in 42.91s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_response_before_second_model_call tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_ready_payload_missing_summary_before_second_model_call -q
2 failed as expected before hard-cut implementation; malformed matching completed story run responses fell through to a second agent request.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
20 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5844 passed, 2 skipped in 44.37s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_missing_input_hash_before_second_model_call tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_story_brief_key_before_restore_or_model_call -q
2 failed as expected before hard-cut implementation; malformed matching latest story run identity/hash fields fell through to a second agent request.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
22 passed in 0.32s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5846 passed, 2 skipped in 44.34s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_latency_without_zero_default -q
1 failed as expected before hard-cut implementation; missing result audit latency wrote a story run with a default zero latency.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
23 passed in 0.38s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5847 passed, 2 skipped in 42.37s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_rejects_context_aliases tests/unit/domains/news_intel/test_news_story_brief_input.py::test_story_packet_does_not_restore_material_or_similarity_from_agent_admission_basis -q
5 failed as expected before hard-cut implementation; story packet builder accepted legacy context aliases and restored material/similarity context from admission basis.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback -q
16 passed in 0.14s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_usage_without_empty_default tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_trace_metadata_without_empty_default -q
2 failed as expected before hard-cut implementation; missing result audit usage/trace metadata wrote story runs with empty audit objects.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_latency_without_zero_default tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_usage_without_empty_default tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_story_result_missing_trace_metadata_without_empty_default -q
3 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
25 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_execution_started_before_restore_or_model_call -q
1 failed as expected before hard-cut implementation; missing failed-run `execution_started` triggered a second model request through `run.get(...)` fallback.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_failed_story_run_missing_execution_started_before_restore_or_model_call -q
1 passed in 0.21s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
26 passed in 0.43s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5859 passed, 2 skipped in 44.80s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_audit_identity_without_defaults -q
9 failed as expected before hard-cut implementation; missing item-brief result audit identity fields were repaired from provider/config/packet defaults and wrote run/current state.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_audit_identity_without_defaults -q
9 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
44 passed in 0.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5868 passed, 2 skipped in 42.79s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_agent_run_audit_without_request_audit_fallback -q
1 failed as expected before hard-cut implementation; missing result `agent_run_audit` fell back to request audit and failed later as missing result latency.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_result_missing_agent_run_audit_without_request_audit_fallback -q
1 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
45 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
Would reformat: tests/architecture/test_news_intel_kiss_simplification.py
1 file would be reformatted, 2 files already formatted
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format tests/architecture/test_news_intel_kiss_simplification.py
1 file reformatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
45 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.08s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5869 passed, 2 skipped in 43.46s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_current_brief_missing_identity_before_second_model_call -q
6 failed as expected before hard-cut implementation; malformed item-brief current rows were treated as stale and triggered a second model request.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_current_brief_missing_identity_before_second_model_call -q
6 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
51 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
E501 line too long in tests/unit/domains/news_intel/test_news_item_brief_worker.py:76 before formatting.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
1 file would be reformatted, 2 files already formatted
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format tests/unit/domains/news_intel/test_news_item_brief_worker.py
1 file reformatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_current_brief_missing_identity_before_second_model_call -q
6 passed in 0.21s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5875 passed, 2 skipped in 42.11s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_failed_run_missing_identity_before_restore_or_model_call -q
10 failed as expected before hard-cut implementation; malformed failed latest-run rows either triggered a second model request or defaulted failed-run error details into current state.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_failed_run_missing_identity_before_restore_or_model_call -q
10 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_restores_failed_current_from_started_failed_run_without_second_model_call tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_failed_run_missing_run_id_before_restore_or_model_call tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_missing_outcome_before_restore_or_model_call tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_restores_current_from_completed_run_without_second_model_call -q
4 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
61 passed in 0.28s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.08s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5885 passed, 2 skipped in 43.25s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_missing_finished_at_without_clock_fallback -q
1 failed as expected before hard-cut implementation; missing completed-run `finished_at_ms` was repaired with the current worker clock and wrote current state.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_missing_finished_at_without_clock_fallback -q
1 passed in 0.18s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_invalid_completed_run_missing_source_identity_before_audit_repair -q
2 failed as expected before hard-cut implementation; invalid completed-run audit repaired missing source provider/model from deterministic defaults or agent config.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_invalid_completed_run_missing_source_identity_before_audit_repair -q
2 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_revalidates_completed_run_before_restoring_current -q
1 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
64 passed in 0.35s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.09s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5888 passed, 2 skipped in 45.43s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_publishable_validation_missing_payload_without_empty_default -q
1 failed as expected before hard-cut implementation; publishable validation results with missing payload wrote completed run/current rows with an empty payload object.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_publishable_validation_missing_payload_without_empty_default -q
1 passed in 0.20s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_writes_ready_brief_and_emits_wake -q
1 passed in 0.20s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
65 passed in 0.28s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.08s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5889 passed, 2 skipped in 42.42s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_loaded_candidate_missing_item_identity_without_marking_target_done -q
1 failed as expected before hard-cut implementation; malformed loaded candidates with blank item identity marked the claimed target done as missing.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_loaded_candidate_missing_item_identity_without_marking_target_done tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_policy_skips_claimed_target_with_low_provider_rating -q
2 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_execute_no_start_rate_limit_does_not_write_business_ledger -q
1 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
66 passed in 0.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_reused_run_identity_requires_run_id_without_empty_fallback -q
1 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5890 passed, 2 skipped in 43.84s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_policy.py -q
437 passed in 0.68s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
90 passed in 3.47s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/services/news_item_agent_policy.py src/parallax/domains/news_intel/runtime/news_page_projection_worker.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/services/news_item_agent_policy.py src/parallax/domains/news_intel/runtime/news_page_projection_worker.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py
8 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5906 passed, 2 skipped in 46.23s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_source_quality_projection.py -q
158 passed in 0.54s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
91 passed in 3.13s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/runtime/news_projection_work.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/runtime/news_projection_work.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
7 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_claim_missing_target_id_without_marking_done tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_claim_missing_story_target_id_without_marking_done -q
2 passed in 0.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
182 passed in 3.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/runtime/news_projection_work.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/runtime/news_projection_work.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
9 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5930 passed, 2 skipped in 47.88s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q
131 passed in 3.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5936 passed, 2 skipped in 44.08s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py -q
424 passed in 4.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5938 passed, 2 skipped in 45.10s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
132 passed in 2.88s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5939 passed, 2 skipped in 44.08s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
134 passed in 3.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1078 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5941 passed, 2 skipped in 44.09s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py -q
20 passed in 0.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
91 passed in 3.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py -q
5 passed in 0.55s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/unit/test_notification_worker_runtime.py -q
126 passed in 1.44s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
115 passed in 2.82s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py -q
25 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py tests/unit/test_api_notifications_contract.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/unit/test_notification_worker_runtime.py tests/architecture/test_notifications_hard_cut.py -q
286 passed in 4.42s
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
7 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5948 passed, 2 skipped in 42.23s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py -q
8 passed in 0.57s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
9 passed in 0.64s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/unit/test_notification_worker_runtime.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
244 passed in 3.96s
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5951 passed, 2 skipped in 44.24s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_explicit_item_admission_and_market_scope tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_compact_agent_brief_does_not_emit_audit_identity_fields -q
49 passed in 0.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5957 passed, 2 skipped in 45.90s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback -q
326 passed in 0.36s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5960 passed, 2 skipped in 45.40s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_loader_requires_explicit_arrays_without_json_list_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_input_loaders_require_explicit_arrays_without_json_list_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_detail_requires_projected_page_row_contract_without_raw_item_fallbacks tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_payloads_require_explicit_audit_json_inputs tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback -q
356 passed in 0.68s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5988 passed, 2 skipped in 43.94s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback -q
27 passed in 0.15s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5994 passed, 2 skipped in 43.68s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_ready_payload_summary_missing_without_market_read_fallback -q
1 failed as expected before hard-cut implementation; completed ready-run restore accepted a market-read-only payload and wrote a current story brief.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
1 failed as expected before hard-cut implementation; the worker still had a generic `_dict` helper that could return `{}` for malformed objects.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
27 passed in 0.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5995 passed, 2 skipped in 42.61s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_ready_brief_without_summary_zh_does_not_use_market_read_for_external_push tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_external_push_publishable_summary_requires_current_summary_field -q
Expected RED: both tests failed before implementation because `market_read_zh` still made external push ready and `_agent_publishable_summary` did not require `summary_zh`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_ready_brief_without_summary_zh_does_not_use_market_read_for_external_push tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_external_push_publishable_summary_requires_current_summary_field -q
2 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q
141 passed in 3.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5997 passed, 2 skipped in 43.66s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_provider_error_audit_output_hash_does_not_repair_missing_explicit_output_hash tests/architecture/test_news_intel_kiss_simplification.py::test_news_brief_workers_do_not_restore_missing_output_hash_from_audit_payload -q
Expected RED: both tests failed before implementation because provider-error audit `output_hash` repaired a missing explicit output hash and both workers still used `output_hash or audit.get("output_hash")`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_provider_error_audit_output_hash_does_not_repair_missing_explicit_output_hash tests/architecture/test_news_intel_kiss_simplification.py::test_news_brief_workers_do_not_restore_missing_output_hash_from_audit_payload -q
2 passed in 0.15s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
188 passed in 3.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
4 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 5999 passed, 2 skipped in 45.47s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_rejects_ready_without_publishable_summary tests/architecture/test_news_intel_kiss_simplification.py::test_news_brief_validation_publishable_text_requires_current_summary_field -q
Expected RED: both tests failed before implementation because validation still accepted `market_read_zh` as publishable text for ready payloads.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py::test_validation_rejects_ready_without_publishable_summary tests/architecture/test_news_intel_kiss_simplification.py::test_news_brief_validation_publishable_text_requires_current_summary_field -q
2 passed in 0.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
252 passed in 3.80s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_brief_validation.py tests/unit/domains/news_intel/test_news_item_brief_validation.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6000 passed, 2 skipped in 44.02s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_requires_repository_admission_contexts -q
Expected RED: both tests failed before implementation because `news_item_brief` repaired malformed admission-context evidence from candidate sidecar fields and continued to model execution.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_requires_repository_admission_contexts -q
2 passed in 0.23s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
163 passed in 3.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6001 passed, 2 skipped in 42.14s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_market_scope_from_agent_admission_basis tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_uses_formal_market_scope_without_admission_basis_fallback -q
Expected RED: both tests failed before implementation because item-brief packet construction restored `market_scope` from admission basis / legacy `market_scope` alias.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_market_scope_from_agent_admission_basis tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_uses_formal_market_scope_without_admission_basis_fallback -q
2 passed in 0.09s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_similarity_or_material_delta_from_agent_admission_basis tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_does_not_restore_context_from_admission_basis -q
Expected RED: both tests failed before implementation because item-brief packet construction restored similarity/material-delta context from admission payload fields.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_similarity_or_material_delta_from_agent_admission_basis tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_does_not_restore_context_from_admission_basis -q
2 passed in 0.09s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_context_from_legacy_item_aliases tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_does_not_restore_context_from_admission_basis -q
Expected RED: both tests failed before implementation because item-brief packet construction restored context from legacy item aliases.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_does_not_restore_context_from_legacy_item_aliases tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_does_not_restore_context_from_admission_basis -q
2 passed in 0.09s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
176 passed in 3.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py -q
135 passed in 3.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6005 passed, 2 skipped in 44.76s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py -k malformed_present_context -q
Expected RED: 10 tests failed before implementation because malformed present item/story packet context fields were silently converted to empty objects.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py -k malformed_present_context -q
14 passed, 37 deselected in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_does_not_restore_packet_context_from_admission_basis -q
Expected RED: failed before implementation because the worker copied admission-basis similarity/material-delta context into formal packet fields.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_does_not_restore_context_from_admission_basis -q
Expected RED: failed before implementation because `_candidate_with_agent_admission` still wrote admission-basis `similarity_json` / `material_delta_json`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_does_not_restore_packet_context_from_admission_basis -q
1 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_does_not_restore_context_from_admission_basis -q
1 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py -q
217 passed in 3.48s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_does_not_restore_from_legacy_alias_fields -q
Expected RED: failed before implementation because page search text restored source/token/fact terms from legacy aliases.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_has_no_legacy_alias_fallbacks -q
Expected RED: failed before implementation because page search text still contained legacy alias fallback expressions.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_does_not_restore_from_legacy_alias_fields -q
1 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_has_no_legacy_alias_fallbacks -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py -q
497 passed in 3.76s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback -q
Expected RED: failed before implementation because News notification candidates derived missing projected representative identity from `news_item_id`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
Expected RED: failed before implementation because the News notification rule still contained projected identity fallback expressions.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback -q
1 passed in 0.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py -q
154 passed in 3.53s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_brief_input.py src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/domains/news_intel/types/news_page_search.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_brief_input.py src/parallax/domains/news_intel/services/news_story_brief_input.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/domains/news_intel/types/news_page_search.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
11 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py -q
321 passed in 3.93s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6024 passed, 2 skipped in 44.16s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_does_not_restore_status_from_scalar_alias tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_does_not_restore_scope_from_legacy_aliases -q
Expected RED: both tests failed before implementation because item-brief priority restored admission status from scalar aliases and market scope from legacy alias fields.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission -q
Expected RED: failed before implementation because policy still contained scalar admission status and market-scope alias fallback expressions.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_does_not_restore_status_from_scalar_alias tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_does_not_restore_scope_from_legacy_aliases -q
2 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
295 passed in 3.38s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_agent_policy.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_agent_policy.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
Expected RED: failed after removing scalar admission priority fallback because ops dirty-target repair still read `items.agent_admission_status` for brief eligibility.
Python unit/architecture/contract lane: 2 failed, 6024 passed, 2 skipped in 43.11s.
exit code: 2

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission -q
11 passed in 0.14s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/runtime/projection_dirty_targets.py tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/app/runtime/projection_dirty_targets.py tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6026 passed, 2 skipped in 44.63s.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset -q
Expected RED: failed before docs were updated because the ops repair docs did not require formal `agent_admission_json` and still described scalar admission-status repair wording.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset -q
10 passed in 0.20s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check tests/architecture/test_news_intel_kiss_simplification.py
1 file already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6026 passed, 2 skipped in 46.03s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_repository_query_uses_narrow_item_and_fact_hotpaths -q
Expected RED: failed before implementation because source-quality aggregation still selected the narrow item hot path without story identity and joined `news_item_agent_briefs` as current readiness evidence.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py -q
21 passed in 0.28s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py::test_page_projection_loader_reads_source_payload_for_claimed_targets tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_admission_representative_current_state_uses_story_briefs tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
24 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
350 passed in 0.20s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
100 passed in 3.03s
exit code: 0

$ rg -n "source_quality.*news_item_agent_briefs|news_source_quality_projection.*news_item_agent_briefs|news_item_agent_briefs by source|JOIN news_item_agent_briefs AS briefs" src/parallax docs tests/unit tests/architecture --glob '!docs/sdd/features/active/2026-06-18-news-trading-agent-hard-cut/verification.md'
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
Expected RED: failed before implementation because the unused `_current_brief_for_item` helper still queried `news_item_agent_briefs` as an easy-to-reuse item-current path.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut tests/unit/domains/news_intel/test_news_repository_queries.py -q
351 passed in 0.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/architecture/test_news_intel_kiss_simplification.py
2 files already formatted
exit code: 0

$ rg -n "def _current_brief_for_item" src/parallax/domains/news_intel/repositories/news_repository.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6026 passed, 2 skipped in 43.01s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_agent_admission_context_loader_does_not_read_target_item_current_brief_audit_rows -q
Expected RED before implementation: failed because `load_agent_admission_contexts` still joined `news_item_agent_briefs AS current_brief` for the target item.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_preserves_item_current_from_target_loader_when_admission_context_has_no_current_brief -q
Expected RED before implementation: failed because `NewsItemBriefWorker._load_candidates` required and copied `current_brief` from admission context instead of preserving the item-brief target loader audit-current row.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_item_brief_worker.py -q
420 passed in 0.43s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_page_dirty_uses_latest_item_watermark_not_worker_now -q
Expected RED before implementation: failed because source-quality status page-dirty fanout used worker `now` (`1779000000000`) instead of `latest_item_published_at_ms` (`1778999960000`).
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_source_watermarks_have_no_zero_or_runtime_fallback -q
23 passed in 0.24s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_metadata_dirty_uses_persisted_item_watermarks_not_worker_now -q
Expected RED before implementation: failed because source metadata page-dirty fanout used `NOW_MS` instead of persisted item source watermarks from `published_at_ms` / `fetched_at_ms`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_metadata_dirty_uses_persisted_item_watermarks_not_worker_now tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_source_watermarks_for_sources_reads_persisted_item_times tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_source_watermarks_have_no_zero_or_runtime_fallback -q
3 passed in 0.52s
exit code: 0

$ rg -n "source_watermark_ms_by_news_item_id=\{[^\n]*now|news_item_id: now|str\(news_item_id\): now|: now for news_item_id|now for news_item_id" src/parallax/domains/news_intel/runtime src/parallax/app/runtime/projection_dirty_targets.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_fetch_worker_enqueues_page_and_source_quality_dirty_for_material_source_metadata_changes_only tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_fetch_worker_requires_news_page_dirty_wake_contract_after_metadata_dirty_enqueue tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_source_quality_worker_enqueues_page_dirty_when_source_quality_status_changes tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_requires_repository_admission_contexts -q
4 passed in 0.53s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
Expected RED before cleanup: PERF401 in `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:1822`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6031 passed, 2 skipped in 42.18s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_enqueues_dirty_targets_for_all_affected_news_items -q
Expected RED before implementation: failed because normal `news_item_written` page-dirty fanout used worker `fetched_at_ms` (`1779000000000`) instead of persisted item source watermarks from `news_items.published_at_ms` / `news_items.fetched_at_ms`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_enqueues_dirty_targets_for_all_affected_news_items tests/unit/domains/news_intel/test_news_workers.py::test_news_fetch_worker_metadata_dirty_uses_persisted_item_watermarks_not_worker_now tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_source_watermarks_reads_persisted_item_times_without_worker_clock tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_source_watermarks_for_sources_reads_persisted_item_times tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_fetch_worker_enqueues_news_item_and_source_quality_dirty_for_inserted_and_updated_news_items_only tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_source_watermarks_have_no_zero_or_runtime_fallback -q
6 passed in 0.45s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
6 files already formatted
exit code: 0

$ rg -n "source_watermark_ms_by_news_item_id=\{[^\n]*(now|fetched_at_ms)|news_item_id: now|str\(news_item_id\): now|: now for news_item_id|now for news_item_id|news_item_id: fetched_at_ms|fetched_at_ms for news_item_id" src/parallax/domains/news_intel/runtime src/parallax/app/runtime/projection_dirty_targets.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6032 passed, 2 skipped in 42.87s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py::test_enqueue_projection_dirty_targets_execute_enqueues_only_dirty_targets tests/unit/test_ops_projection_dirty_targets.py::test_enqueue_projection_dirty_targets_can_scope_story_brief_repair tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset -q
Expected RED before implementation: failed because ops projection dirty repair still accepted/enqueued `brief_input` item targets, did not accept `story_brief`, and did not read `story_key` / `fetched_at_ms` for story-current repair watermarks.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py::test_enqueue_projection_dirty_targets_execute_enqueues_only_dirty_targets tests/unit/test_ops_projection_dirty_targets.py::test_enqueue_projection_dirty_targets_can_scope_story_brief_repair tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset -q
3 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_backfill_commands.py::test_rebuild_news_canonical_items_execute_reads_and_writes_inside_transaction -q
Expected RED before implementation: failed because `rebuild-news-canonical-items` still called `list_news_item_ids_for_canonical_rebuild(...)` and hand-built `brief_input` item targets without source watermarks.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_backfill_commands.py::test_rebuild_news_canonical_items_execute_reads_and_writes_inside_transaction -q
1 passed in 4.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py -q
118 passed in 0.36s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_ops_backfill_commands.py -q
33 passed in 4.00s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
100 passed in 3.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_cli.py -q
10 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/runtime/projection_dirty_targets.py src/parallax/app/surfaces/cli/commands/ops.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_ops_backfill_commands.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/app/runtime/projection_dirty_targets.py src/parallax/app/surfaces/cli/commands/ops.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_ops_backfill_commands.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
7 files already formatted
exit code: 0

$ rg -n "projection=\"brief_input\"" src/parallax/app src/parallax/domains/news_intel tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_ops_backfill_commands.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
exit code: 1

$ rg -n "source_watermark_ms_by_news_item_id=\{[^\n]*(now|fetched_at_ms)|news_item_id: now|str\(news_item_id\): now|: now for news_item_id|now for news_item_id|news_item_id: fetched_at_ms|fetched_at_ms for news_item_id|source_watermark_ms\": 0|source_watermark_ms = 0" src/parallax/domains/news_intel/runtime src/parallax/app/runtime/projection_dirty_targets.py src/parallax/app/surfaces/cli/commands/ops.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6032 passed, 2 skipped in 42.75s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0
```

### 2026-06-18 canonical rebuild current-story servable keyset

`rebuild-news-canonical-items` no longer accepts a raw `news_items` keyset for current projection repair. The repository list now returns only processed items with current story identity, non-empty story keys, positive persisted producer watermarks, and enabled observation edges. The ops target helper requires `story_key` and positive source watermark before enqueueing page plus coalesced `story_brief` work, so malformed page-only rebuild rows fail closed.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_canonical_rebuild_list_reads_only_current_servable_news_items -q
Expected RED before implementation: failed because `list_news_items_for_canonical_rebuild(...)` still selected directly from `news_items` without current-story, enabled-edge, or positive-watermark filtering.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_backfill_commands.py::test_rebuild_news_canonical_targets_require_story_key -q
Expected RED before implementation: failed because `_news_canonical_rebuild_targets(...)` silently accepted an empty `story_key` and produced a page-only target.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_canonical_rebuild_list_reads_only_current_servable_news_items tests/unit/test_ops_backfill_commands.py::test_rebuild_news_canonical_targets_require_story_key tests/unit/test_ops_backfill_commands.py::test_rebuild_news_canonical_items_execute_reads_and_writes_inside_transaction tests/architecture/test_news_intel_kiss_simplification.py::test_ops_news_canonical_rebuild_reads_current_servable_story_keyset -q
4 passed in 4.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
354 passed in 0.47s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_backfill_commands.py -q
25 passed in 5.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
101 passed in 5.28s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_ops_backfill_commands.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_ops_backfill_commands.py tests/architecture/test_news_intel_kiss_simplification.py
5 files already formatted
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6035 passed, 2 skipped in 47.27s.
compileall completed for src and tests.
exit code: 0
```

### 2026-06-18 ops dirty repair current-story keyset

`enqueue-projection-dirty-targets` News item repair now reads only processed current-story items with non-empty `story_key` and the current `NEWS_STORY_IDENTITY_VERSION` before constructing page/story repair targets. This keeps story-brief repair from failing on legacy storyless migration rows or enqueueing story work for rows outside the current story model; the keyset remains minimal and does not join source, token, fact, provider-signal, or content-classification payloads.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py::test_enqueue_projection_dirty_targets_can_scope_story_brief_repair -q
Expected RED before implementation: failed because `_fetch_news_item_rows(...)` selected from `news_items` without `lifecycle_status`, non-empty `story_key`, or current story identity filtering.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_ops_projection_dirty_targets.py -q
9 passed in 0.13s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_ops_projection_repair_enqueues_provider_signal_story_brief_dirty_target tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_ops_projection_repair_enqueues_eligible_refresh_story_brief_dirty_target -q
2 passed in 0.78s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_ops_projection_dirty_repair_reads_minimal_news_item_keyset -q
1 passed in 0.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py -q
219 passed in 4.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/runtime/projection_dirty_targets.py tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/app/runtime/projection_dirty_targets.py tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6035 passed, 2 skipped in 54.47s.
compileall completed for src and tests.
exit code: 0
```

### 2026-06-18 notification external-push summary hard cut

News high-signal notification external push no longer treats legacy `market_read_zh` as a publishable summary. Notification body and push readiness now require the current projected `agent_brief.summary_zh`, matching the page projection external-push contract; market-read-only story-current rows remain in-app only with `agent_brief_missing_summary`.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_current_summary_without_market_read_fallback -q
Expected RED before implementation: failed because a ready agent brief containing only `market_read_zh` still received external channels (`in_app`, `pushdeer`).
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
Expected RED before implementation: failed because `_news_agent_summary(...)` still read `agent_brief.get("market_read_zh")`.
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_current_summary_without_market_read_fallback tests/unit/test_notification_rules.py::test_news_high_signal_uses_projection_external_push_readiness tests/unit/test_notification_rules.py::test_news_high_signal_ignores_legacy_brief_json_for_display_payload_and_push tests/unit/test_notification_rules.py::test_news_high_signal_uses_ready_agent_brief_for_display_and_builds_push_signatures -q
4 passed in 0.96s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_external_push_publishable_summary_requires_current_summary_field tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
3 passed in 0.07s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
173 passed in 3.76s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ rg -n 'agent_brief\.get\("summary_zh"\) or agent_brief\.get\("market_read_zh"\)|market_read_zh.*external_push|external_push.*market_read_zh' src/parallax/domains/notifications/services/notification_rules.py src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6037 passed, 2 skipped in 46.90s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 repository agent-brief publishable summary hard cut

News item/story agent-brief repository writes no longer treat legacy `market_read_zh` as publishable text for `ready` current rows. The write-time guard now accepts only current `summary_zh` from the payload/top-level brief JSON, matching worker validation, page projection, and notification external-push publishability.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_news_item_agent_brief_ready_payload_requires_summary_without_market_read_fallback tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_news_story_agent_brief_ready_payload_requires_summary_without_market_read_fallback -q
FAILED tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_news_item_agent_brief_ready_payload_requires_summary_without_market_read_fallback
FAILED tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_news_story_agent_brief_ready_payload_requires_summary_without_market_read_fallback
2 failed in 0.32s
exit code: 1
```

Expected RED before implementation: both tests failed because item/story current brief writes accepted a ready payload containing only `market_read_zh`.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_agent_brief_publishable_summary_requires_current_summary_field -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_agent_brief_publishable_summary_requires_current_summary_field
1 failed in 0.09s
exit code: 1
```

Expected RED before implementation: the repository publishable-summary helper still read `market_read_zh` and used `summary_zh or ...` fallback logic.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_news_item_agent_brief_ready_payload_requires_summary_without_market_read_fallback tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_news_story_agent_brief_ready_payload_requires_summary_without_market_read_fallback -q
2 passed in 0.14s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_agent_brief_publishable_summary_requires_current_summary_field -q
1 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
356 passed in 0.18s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
103 passed in 3.64s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6040 passed, 2 skipped in 45.35s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 page-row ready agent-brief signal-field guard

`news_page_rows` write payload validation now requires ready `agent_brief` rows to carry formal `direction` and `decision_class` fields before SQL. Pending rows remain allowed with only explicit pending status, but malformed ready rows can no longer be repaired later by notification/display-signal fallback paths.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write -q
FAILED tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write[direction-None]
FAILED tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write[direction-]
FAILED tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write[decision_class-None]
FAILED tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write[decision_class-]
4 failed in 0.43s
exit code: 1
```

Expected RED before implementation: malformed ready `agent_brief` payloads were not rejected before SQL and therefore reached the fake insert path instead of failing at the page-row payload boundary.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults
1 failed in 0.31s
exit code: 1
```

Expected RED before implementation: `_page_row_payload(...)` did not require `agent_brief.direction` or `agent_brief.decision_class` for ready rows.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_ready_agent_brief_requires_formal_signal_fields_before_write -q
4 passed in 0.16s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults -q
1 passed in 0.21s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
360 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
103 passed in 4.61s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6044 passed, 2 skipped in 59.79s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 notification external-push signal-field hard cut

News high-signal external pushes no longer repair a malformed ready `agent_brief` from `signal.display_signal` or alert eligibility when building external delivery eligibility/signatures. External push now requires the ready projected brief to carry `summary_zh`, `direction`, and `decision_class`; malformed ready rows remain in-app only with a specific suppression reason.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_ready_brief_signal_fields_without_display_signal_fallback -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_ready_brief_signal_fields_without_display_signal_fallback[direction-agent_brief_missing_direction]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_ready_brief_signal_fields_without_display_signal_fallback[decision_class-agent_brief_missing_decision_class]
2 failed in 0.45s
exit code: 1
```

Expected RED before implementation: rows with ready summary but missing ready-brief `direction` or `decision_class` still received external channels because notification external-push logic repaired them from projected display/eligibility fields.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback
1 failed in 0.16s
exit code: 1
```

Expected RED before implementation: `_news_external_push_signature(...)` still used `display_signal.get("direction")`, and `_news_external_push_readiness(...)` did not require formal ready-brief signal fields.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_ready_brief_signal_fields_without_display_signal_fallback -q
2 passed in 0.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback -q
1 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
177 passed in 4.73s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6047 passed, 2 skipped in 55.19s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 notification public signal-field hard cut

News high-signal notification payloads and semantic signatures no longer repair malformed ready `agent_brief.direction` or `agent_brief.decision_class` from `signal.display_signal`, `signal.direction`, or alert eligibility. Pending / not-ready in-app candidates may still use projected signal fields for semantic grouping, but once a ready current brief exists, public notification fields trust only that current brief.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_external_push_and_payload_require_ready_brief_signal_fields_without_display_signal_fallback -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_external_push_and_payload_require_ready_brief_signal_fields_without_display_signal_fallback[direction-agent_brief_missing_direction]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_external_push_and_payload_require_ready_brief_signal_fields_without_display_signal_fallback[decision_class-agent_brief_missing_decision_class]
2 failed in 0.48s
exit code: 1
```

Expected RED before implementation: ready rows missing `direction` or `decision_class` still published fallback `bullish` / `driver` values in the notification payload.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks
1 failed in 0.19s
exit code: 1
```

Expected RED before implementation: the notification rule had no centralized helper that could hard-cut ready-brief signal fields before applying pending-row projection fallbacks.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_external_push_and_payload_require_ready_brief_signal_fields_without_display_signal_fallback -q
2 passed in 0.39s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
1 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
178 passed in 3.79s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 public ready agent-brief signal-field hard cut

Projected public `agent_brief` shaping now requires ready rows to carry explicit top-level `direction` and `decision_class`. Nested `brief_json` fields cannot repair missing ready signal fields, so API/detail/notification consumers fail on malformed projected ready rows instead of silently serving incomplete current state.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_ready_agent_brief_requires_signal_fields_without_projection_repair -q
FAILED tests/unit/test_api_news_contract.py::test_news_public_ready_agent_brief_requires_signal_fields_without_projection_repair[direction]
FAILED tests/unit/test_api_news_contract.py::test_news_public_ready_agent_brief_requires_signal_fields_without_projection_repair[decision_class]
2 failed in 0.87s
exit code: 1
```

Expected RED before implementation: `_public_agent_brief_payload(...)` accepted ready rows missing top-level `direction` or `decision_class`, even when nested `brief_json` carried those fields.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate
1 failed in 0.20s
exit code: 1
```

Expected RED before implementation: the public agent-brief helper had no ready-specific signal-field guard.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_ready_agent_brief_requires_signal_fields_without_projection_repair -q
2 passed in 0.97s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
1 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py tests/unit/test_api_notifications_contract.py tests/unit/test_notification_rules.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
560 passed in 4.98s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
5 files already formatted
exit code: 0
```

## 2026-06-18 page signal ready-field hard cut

Page projection signal shaping now fails malformed ready `agent_signal` payloads missing `direction` or `decision_class` instead of defaulting `direction` to `neutral` or treating a missing decision class as a non-notifiable state. Partial / pending signals remain explicit non-ready states.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_page_signal_ready_agent_signal_requires_signal_fields_without_fallback -q
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_page_signal_ready_agent_signal_requires_signal_fields_without_fallback[direction]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_page_signal_ready_agent_signal_requires_signal_fields_without_fallback[decision_class]
2 failed in 0.08s
exit code: 1
```

Expected RED before implementation: `_page_signal(...)` repaired missing ready `direction` to `neutral` and let missing `decision_class` become a non-notifiable state.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback
1 failed in 0.21s
exit code: 1
```

Expected RED before implementation: page projection had no `_required_agent_signal_text(...)` guard and still contained ready-field fallback expressions.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_page_signal_ready_agent_signal_requires_signal_fields_without_fallback -q
2 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback -q
1 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_api_news_contract.py tests/unit/test_api_notifications_contract.py tests/unit/test_notification_rules.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
610 passed in 10.90s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
7 files already formatted
exit code: 0
```

## 2026-06-18 non-integration repository check after public signal guards

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6052 passed, 2 skipped in 60.80s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 page projection lane-array hard cut

Page projection token/fact lanes no longer repair malformed present lane arrays to empty lists. Missing optional lane arrays still project as `[]`, but present scalar/object values for `reason_codes_json`, `candidate_targets_json`, `rejection_reasons_json`, or `affected_targets_json` fail visibly at projection build time.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_lane_lists -q
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_lane_lists[token-reason_codes_json-SYMBOL_NOT_IN_REGISTRY]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_lane_lists[token-candidate_targets_json-value1]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_lane_lists[fact-rejection_reasons_json-target_identity_not_production_eligible]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_lane_lists[fact-affected_targets_json-value3]
4 failed in 0.10s
exit code: 1
```

Expected RED before implementation: `_token_lane(...)` and `_fact_lane(...)` called `_json_list(row.get(...))`, so malformed present scalar/object lane fields were silently projected as `[]`.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_lane_arrays_reject_malformed_present_values -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_lane_arrays_reject_malformed_present_values
1 failed in 0.19s
exit code: 1
```

Expected RED before implementation: the strict `_optional_lane_list(...)` helper did not exist and the lane builders still had direct `_json_list(row.get(...))` repair paths.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_lane_lists -q
4 passed in 0.06s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_lane_arrays_reject_malformed_present_values -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_api_news_contract.py tests/unit/test_api_notifications_contract.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
615 passed in 6.15s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6057 passed, 2 skipped in 44.80s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 item/story brief packet lane-array hard cut

Item and story agent input packets no longer repair malformed present token/fact evidence arrays before model execution. Missing optional `candidate_targets_json`, `affected_targets_json`, and `rejection_reasons_json` fields still mean no lane evidence, but present non-array values and malformed target members now fail before packet hashing.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays -q
FAILED tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays[entity_candidate_targets_object]
FAILED tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays[token_candidate_targets_object]
FAILED tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays[token_candidate_targets_scalar_member]
FAILED tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays[fact_affected_targets_object]
FAILED tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays[fact_rejection_reasons_string]
5 failed in 0.18s
exit code: 1
```

Expected RED before implementation: item/story packet lane builders still used `_json_list(row.get(...))` plus `_json_object(value)`, so malformed present lane arrays became empty arrays or empty target objects.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_lane_arrays_reject_malformed_present_values -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_lane_arrays_reject_malformed_present_values
1 failed in 0.19s
exit code: 1
```

Expected RED before implementation: the strict packet lane helpers did not exist.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_lane_arrays -q
5 passed in 0.22s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_lane_arrays_reject_malformed_present_values -q
1 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_lane_arrays_reject_malformed_present_values -q
153 passed in 0.41s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_api_news_contract.py tests/unit/test_api_notifications_contract.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
768 passed in 6.80s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6063 passed, 2 skipped in 65.89s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-18 page search projected JSON hard cut

Page search text now fails malformed present projected JSON fields instead of silently treating them as empty search evidence. Missing optional projected fields remain absent so the pre-repository build path can still compute a partial row, but present malformed `source_json`, `source_ids_json`, `source_domains_json`, `token_lanes_json`, or `fact_lanes_json` fail before page-row payload hashing and serving-row writes.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields -q
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[source_json-example.test]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[source_ids_json-value1]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[source_domains_json-example.test]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[token_lanes_json-value3]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[token_lanes_json-value4]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[fact_lanes_json-value5]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields[fact_lanes_json-value6]
7 failed in 0.09s
exit code: 1
```

Expected RED before implementation: page search helpers returned `{}` or `[]` for malformed present projected fields and malformed lane members.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_rejects_malformed_present_projection_fields -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_rejects_malformed_present_projection_fields
1 failed in 0.12s
exit code: 1
```

Expected RED before implementation: the strict projected JSON helpers did not exist.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_search_text_rejects_malformed_present_projection_fields -q
7 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_rejects_malformed_present_projection_fields -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_has_no_legacy_alias_fallbacks tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_search_text_rejects_malformed_present_projection_fields -q
423 passed in 0.43s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/types/news_page_search.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/types/news_page_search.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 News high-signal notification projected payload hard cut

News high-signal notification candidate generation now rejects malformed present projected payload sections instead of repairing them through generic `_dict` / `_list` helpers. The candidate row must supply formal projected `signal`, `alert_eligibility`, `agent_brief`, `market_scope`, `agent_admission`, and `token_impacts` shapes before public notification payload construction. Optional story and affected-entity sections may be absent, but malformed present values fail visibly.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[signal_scalar-news_high_signal_signal_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[alert_eligibility_scalar-news_high_signal_alert_eligibility_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[agent_brief_scalar-news_high_signal_agent_brief_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[agent_brief_affected_entities_object-news_high_signal_agent_brief_affected_entities_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[agent_brief_affected_entities_member-news_high_signal_agent_brief_affected_entities_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[token_impacts_object-news_high_signal_token_impacts_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[token_impacts_member-news_high_signal_token_impacts_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[story_scalar-news_high_signal_story_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[market_scope_scalar-news_high_signal_market_scope_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[agent_admission_scalar-news_high_signal_agent_admission_required]
10 failed in 0.64s
exit code: 1
```

Expected RED before implementation: candidate generation converted malformed projected sections to `{}` or `[]` and continued emitting degraded notification candidates.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections
1 failed in 0.22s
exit code: 1
```

Expected RED before implementation: the News-specific required projected payload helpers did not exist.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
10 passed in 0.48s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
1 passed in 0.07s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
95 passed in 0.75s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 story similarity provider-key evidence hard cut

Story similarity now uses only formal provider-key arrays supplied by the repository admission context: `provider_article_keys_json` on target items and `provider_article_keys` / `provider_article_keys_json` on candidates. Scalar `provider_article_key` and JSON-string parsing no longer drive duplicate grouping, and malformed present provider-key arrays fail before admission similarity decisions.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_similarity.py::test_scalar_provider_article_key_does_not_drive_story_similarity tests/unit/domains/news_intel/test_news_story_similarity.py::test_story_similarity_rejects_malformed_present_provider_key_arrays -q
FAILED tests/unit/domains/news_intel/test_news_story_similarity.py::test_scalar_provider_article_key_does_not_drive_story_similarity
FAILED tests/unit/domains/news_intel/test_news_story_similarity.py::test_story_similarity_rejects_malformed_present_provider_key_arrays
2 failed in 0.04s
exit code: 1
```

Expected RED before implementation: scalar `provider_article_key` still matched exact duplicates, and malformed present provider-key arrays were repaired to no evidence.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_similarity_uses_formal_provider_key_arrays_without_scalar_or_json_string_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_similarity_uses_formal_provider_key_arrays_without_scalar_or_json_string_fallback
1 failed in 0.18s
exit code: 1
```

Expected RED before implementation: the formal provider-key array helper did not exist.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_similarity.py::test_same_opennews_article_id_is_exact_duplicate tests/unit/domains/news_intel/test_news_story_similarity.py::test_scalar_provider_article_key_does_not_drive_story_similarity tests/unit/domains/news_intel/test_news_story_similarity.py::test_story_similarity_rejects_malformed_present_provider_key_arrays -q
3 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_similarity_uses_formal_provider_key_arrays_without_scalar_or_json_string_fallback -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_similarity.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_news_story_agent_admission.py tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_similar_story_without_material_delta_enqueues_page_only tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_material_story_delta_enqueues_one_story_brief_refresh tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_provider_article_duplicate_lookup_uses_edges_not_jsonb_expansion tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_similarity_uses_formal_provider_key_arrays_without_scalar_or_json_string_fallback -q
22 passed in 0.48s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_story_similarity.py tests/unit/domains/news_intel/test_news_story_similarity.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_story_similarity.py tests/unit/domains/news_intel/test_news_story_similarity.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 source-status coverage-tags hard cut

News source-status diagnostics now reject malformed present `coverage_tags_json` instead of repairing scalars, objects, or mixed arrays to empty public coverage. Missing configured coverage still remains an explicit empty list when the repository query supplies `[]`; malformed present rows fail before `/api/news/sources/status` can publish degraded source hygiene.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_coverage_tags -q
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_coverage_tags[crypto_market]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_coverage_tags[coverage_tags_json1]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_coverage_tags[coverage_tags_json2]
3 failed in 0.18s
exit code: 1
```

Expected RED before implementation: source-status payload shaping converted malformed present coverage tags to `[]`.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_coverage_tags -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_coverage_tags
1 failed in 0.20s
exit code: 1
```

Expected RED before implementation: the strict source-status coverage-tags helper did not exist.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_uses_plain_quality_diagnostics tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_coverage_tags tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_marks_disabled_and_api_backed_capabilities -q
5 passed in 0.36s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_coverage_tags -q
1 passed in 0.13s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/test_api_news_contract.py::test_news_api_source_status_includes_provider_diagnostics_without_postgres tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_coverage_tags -q
27 passed in 2.74s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 agent-policy formal JSON hard cut

News agent brief priority now rejects malformed present formal policy fields instead of parsing JSON strings or treating bad admission/material-delta/market-scope values as empty. Missing optional policy fields still remain non-eligible or unscoped, but present malformed `agent_admission_json`, `basis`, `material_delta.changed_fields`, and `market_scope_json` surfaces fail before dirty-target priority can silently downgrade damaged rows.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields -q
FAILED tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields[admission_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields[basis_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields[changed_fields_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields[market_scope_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_policy.py::test_news_item_agent_brief_priority_rejects_malformed_present_policy_fields[market_scope_scope_string]
5 failed in 0.06s
exit code: 1
```

Expected RED before implementation: the priority helper parsed JSON strings and collapsed malformed present formal fields to empty policy state.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_rejects_malformed_present_policy_fields -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_rejects_malformed_present_policy_fields
1 failed in 0.21s
exit code: 1
```

Expected RED before implementation: the typed policy helpers did not exist and JSON string parsing was still present.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py -q
14 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_rejects_malformed_present_policy_fields tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission -q
2 passed in 0.16s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/test_ops_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py -q
164 passed in 4.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_agent_policy.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_agent_policy.py tests/unit/domains/news_intel/test_news_item_agent_policy.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 agent-admission formal JSON hard cut

News item agent admission now rejects malformed present formal item/context fields instead of parsing JSON strings or collapsing bad mappings/lists into missing classification, provider rating, source policy, or representative evidence. Missing optional fields still follow the existing `needs_review`/empty-evidence branches, but present malformed `content_classification_json`, `source_policy_json`, `provider_signal_json`, and representative context arrays fail before the decision can silently skip story-brief work.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_agent_admission_rejects_malformed_present_item_json_fields tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_agent_admission_rejects_malformed_present_context_arrays -q
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_agent_admission_rejects_malformed_present_item_json_fields[classification_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_agent_admission_rejects_malformed_present_item_json_fields[source_policy_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_agent_admission_rejects_malformed_present_item_json_fields[provider_signal_string]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_agent_admission_rejects_malformed_present_context_arrays
4 failed in 0.20s
exit code: 1
```

Expected RED before implementation: admission parsed JSON strings or treated malformed present fields as absent.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_rejects_malformed_present_json_fields -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_rejects_malformed_present_json_fields
1 failed in 0.22s
exit code: 1
```

Expected RED before implementation: typed admission helpers did not exist and JSON string parsing was still present.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_news_story_agent_admission.py -q
16 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_rejects_malformed_present_json_fields tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_policy_does_not_gate_on_legacy_analysis_admission tests/architecture/test_news_intel_kiss_simplification.py::test_news_runtime_product_paths_do_not_use_legacy_analysis_admission_gate -q
3 passed in 0.18s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_admitted_crypto_row_enqueues_page_and_story_brief_with_story_key tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_material_story_delta_enqueues_one_story_brief_refresh tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_similar_story_without_material_delta_enqueues_page_only tests/unit/test_ops_projection_dirty_targets.py -q
12 passed in 0.90s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_item_agent_admission.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_item_agent_admission.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 market-scope formal array hard cut

News market-scope classification now rejects malformed present formal arrays instead of parsing JSON strings or silently treating bad `coverage_tags_json`, token `reason_codes`, or fact `affected_targets` as absent. This keeps deterministic market scope and downstream agent admission from masking damaged item/evidence rows as merely unknown or non-colliding.

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py::test_market_scope_rejects_malformed_present_json_arrays -q
FAILED tests/unit/domains/news_intel/test_news_market_scope.py::test_market_scope_rejects_malformed_present_json_arrays[coverage_tags_string]
FAILED tests/unit/domains/news_intel/test_news_market_scope.py::test_market_scope_rejects_malformed_present_json_arrays[reason_codes_string]
FAILED tests/unit/domains/news_intel/test_news_market_scope.py::test_market_scope_rejects_malformed_present_json_arrays[affected_targets_string]
3 failed in 0.06s
exit code: 1
```

Expected RED before implementation: market-scope helper parsed JSON strings or collapsed malformed present arrays to `[]`.

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_market_scope_rejects_malformed_present_json_arrays -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_market_scope_rejects_malformed_present_json_arrays
1 failed in 0.18s
exit code: 1
```

Expected RED before implementation: typed scope-list helper did not exist and JSON string parsing was still present.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_news_story_agent_admission.py -q
22 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_market_scope_rejects_malformed_present_json_arrays tests/architecture/test_news_intel_kiss_simplification.py::test_opennews_provider_signal_is_not_news_agent_prompt_evidence_or_priority -q
2 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_market_scope.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_news_story_agent_admission.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_market_scope_rejects_malformed_present_json_arrays -q
23 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_market_scope.py tests/unit/domains/news_intel/test_news_market_scope.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_market_scope.py tests/unit/domains/news_intel/test_news_market_scope.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-18 worker/provider/payload JSON repair hard cut follow-up

### RED

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_news_item_process_worker_rejects_malformed_agent_admission_context_fields -q
4 failed in 0.66s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_opennews_fetch_since_requires_formal_fetch_policy_json_mapping_without_alias_or_string_repair -q
FAILED ... assert 16400000 is None
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/integrations/news_feeds/test_opennews_client.py::test_opennews_fetch_policy_rejects_malformed_present_json_contract -q
FAILED ... DID NOT RAISE <class 'ValueError'>
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_context_objects tests/unit/domains/news_intel/test_news_item_brief_input.py::test_packet_rejects_malformed_present_market_scope_json -q
6 failed, 6 passed in 0.12s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
FAILED ... 'json.loads' is contained here: payload = json.loads(value)
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_material_identity.py::test_provider_symbol_set_accepts_mapping_values_and_rejects_json_strings -q
FAILED ... DID NOT RAISE <class 'ValueError'>
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_news_item_brief_worker_packet_rejects_malformed_candidate_arrays -q
3 failed in 0.30s
exit code: 1
```

Expected RED before implementation: worker/provider/payload helpers were still parsing JSON strings, accepting legacy aliases, or silently converting malformed candidate arrays to empty lists.

### GREEN

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_story_brief_input.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_material_identity.py tests/unit/test_api_notifications_contract.py -q
227 passed in 0.90s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_fetch_worker_fetch_policy_requires_formal_jsonb_mapping_without_alias_or_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_opennews_source_fetch_policy_rejects_malformed_present_json_contract tests/architecture/test_news_intel_kiss_simplification.py::test_news_material_identity_rejects_provider_token_impacts_json_strings_without_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_agent_admission_context_rejects_malformed_present_shapes tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_input_rejects_malformed_present_json_fields_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_rejects_malformed_candidate_arrays_without_empty_defaults tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
7 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check <touched worker/provider/payload files and tests>
All checks passed!
exit code: 0
```

## 2026-06-18 non-integration regression after hard-cut follow-up slices

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6130 passed, 2 skipped in 44.40s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0
```

## 2026-06-19 page/notification projected-field hard cut follow-up

Page projection now rejects malformed present `coverage_tags_json` and `provider_signal_json` instead of repairing them to empty source/provider-rating payloads. News high-signal notification candidates now require explicit projected `latest_at_ms` and `row_id`; occurrence/source identity no longer falls back to agent completion time, `now_ms`, or `news_item_id`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_source_coverage_tags -q
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_source_coverage_tags[crypto_exchange]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_source_coverage_tags[coverage_tags_json1]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_source_payload_rejects_malformed_present_coverage_tags -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_source_payload_rejects_malformed_present_coverage_tags
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_provider_signal -q
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_provider_signal[bullish]
FAILED tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_present_provider_signal[provider_signal_json1]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_provider_rating_rejects_malformed_present_provider_signal -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_provider_rating_rejects_malformed_present_provider_signal
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[latest_at_ms_missing-news_high_signal_latest_at_ms_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[latest_at_ms_string-news_high_signal_latest_at_ms_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[row_id_missing-news_high_signal_row_id_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[row_id_blank-news_high_signal_row_id_required]
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py -q
137 passed in 0.59s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_source_payload_rejects_malformed_present_coverage_tags tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_provider_rating_rejects_malformed_present_provider_signal tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
4 passed in 0.07s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/notifications/services/notification_rules.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after projected-field follow-up

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6140 passed, 2 skipped in 43.37s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 news high-signal story-identity hard cut

News high-signal notification candidates now require explicit projected `story_key` and always publish `news_story` entity identity. Candidate identity, semantic signatures, and external push signatures no longer keep an item-entity fallback branch for missing story identity.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[story_key_missing-news_high_signal_story_key_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[story_key_blank-news_high_signal_story_key_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_notification_rules.py::test_news_high_signal_same_story_variants_emit_one_candidate_without_item_identity -q
17 passed in 0.39s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
1 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
79 passed in 0.76s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after story-identity notification hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6142 passed, 2 skipped in 43.68s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 news high-signal story-envelope hard cut

News high-signal notification candidates now require the projected `story` envelope instead of treating it as optional. Missing story payload fails visibly as projected row damage rather than publishing an empty story section.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[story_missing-news_high_signal_story_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
17 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
1 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
78 passed in 0.82s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after story-envelope notification hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6143 passed, 2 skipped in 42.39s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 news high-signal projected identity hard cut

News high-signal notification candidates now require explicit projected `news_item_id` and `representative_news_item_id` identity fields. Missing or blank identities fail visibly, and the external push asset bucket no longer uses an `"unknown"` fallback when no asset symbol is available.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[news_item_id_missing-news_high_signal_news_item_id_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[news_item_id_blank-news_high_signal_news_item_id_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[representative_news_item_id_missing-news_high_signal_representative_news_item_id_required]
FAILED tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections[representative_news_item_id_blank-news_high_signal_representative_news_item_id_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback -q
1 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_notification_rules.py::test_news_high_signal_same_story_variants_emit_one_candidate_without_item_identity -q
23 passed in 0.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_uses_explicit_projected_identity_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
82 passed in 0.68s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after projected identity notification hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6147 passed, 2 skipped in 43.50s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 admission repository context hard cut

`NewsItemAgentAdmissionContext.from_repository_context` now treats missing optional repository context sections as absent, but rejects malformed present `exact_duplicate_candidates`, `story_candidates`, and `material_delta` sections. This prevents item-process and retained item-brief audit paths from silently repairing damaged repository context into empty candidate/material state.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_allows_absent_optional_sections tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections -q
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections[repository_context0-news_item_agent_admission_context_exact_duplicate_candidates_required]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections[repository_context1-news_item_agent_admission_context_exact_duplicate_candidates_required]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections[repository_context2-news_item_agent_admission_context_story_candidates_required]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections[repository_context3-news_item_agent_admission_context_story_candidates_required]
FAILED tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections[repository_context4-news_item_agent_admission_context_material_delta_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_context_rejects_malformed_present_repository_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_context_rejects_malformed_present_repository_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_allows_absent_optional_sections tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_repository_context_rejects_malformed_present_sections -q
6 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_context_rejects_malformed_present_repository_sections -q
1 passed in 0.01s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_news_story_agent_admission.py tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_malformed_admission_context_evidence_without_candidate_fallback tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_does_not_restore_packet_context_from_admission_basis tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_rejects_malformed_present_json_fields tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_agent_admission_context_rejects_malformed_present_repository_sections -q
26 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/types/news_item_agent_admission.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/architecture/test_news_intel_kiss_simplification.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/types/news_item_agent_admission.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after admission context hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6154 passed, 2 skipped in 43.12s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-status diagnostics hard cut

News source-status payload shaping now treats missing optional diagnostic sections as absent, but rejects malformed present `latest_quality_json`, `latest_fetch_run_json`, `sync_diagnostics_json`, `dedup_diagnostics_json`, and nested latest-quality `diagnostics_json`. This prevents `/api/news/sources/status` from silently publishing repaired empty provider/source diagnostics when the read model row is damaged.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics -q
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections[latest_quality_json-ready-news_source_status_latest_quality_json_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections[latest_fetch_run_json-value1-news_source_status_latest_fetch_run_json_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections[sync_diagnostics_json-{}-news_source_status_sync_diagnostics_json_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections[dedup_diagnostics_json-value3-news_source_status_dedup_diagnostics_json_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics[latest_quality_json0-news_source_status_latest_quality_diagnostics_json_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics[latest_quality_json1-news_source_status_latest_quality_diagnostics_json_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics -q
6 passed in 0.15s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.24s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/test_api_news_contract.py::test_news_api_source_status_includes_provider_diagnostics_without_postgres tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_source_payload_rejects_malformed_present_coverage_tags -q
34 passed in 1.08s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
1 file reformatted, 2 files left unchanged
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-status diagnostics hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6160 passed, 2 skipped in 42.46s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-hygiene provider health hard cut

News source hygiene now requires projected `provider_health.status` and no longer repairs missing or malformed provider health from `source_quality_status`. Malformed source-status rows fail visibly before `/api/news/sources/status` can publish degraded-source warnings from a fallback field.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback -q
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback[None-news_source_status_provider_health_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback[degraded-news_source_status_provider_health_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback[provider_health2-news_source_status_provider_health_status_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback[provider_health3-news_source_status_provider_health_status_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_api_source_hygiene_requires_projected_provider_health_without_quality_status_fallback -q
4 passed in 1.66s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
1 passed in 0.16s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
20 passed in 1.95s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/app/surfaces/api/routes_news.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/surfaces/api/routes_news.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-hygiene provider health hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6165 passed, 2 skipped in 47.00s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-status provider fields hard cut

News source-status provider capabilities and source hygiene now require projected `provider_type` and list-shaped `coverage_tags`. Malformed or blank projected provider fields fail visibly instead of being repaired to empty provider capabilities or incomplete source-hygiene warnings.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags -q
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags[source_update0-news_source_status_provider_type_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags[source_update1-news_source_status_provider_type_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags[source_update2-news_source_status_coverage_tags_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags[source_update3-news_source_status_coverage_tags_required]
FAILED tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags[source_update4-news_source_status_coverage_tags_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_api_source_status_requires_projected_provider_type_and_coverage_tags -q
5 passed in 1.14s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
25 passed in 1.97s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/app/surfaces/api/routes_news.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/surfaces/api/routes_news.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-status provider fields hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6170 passed, 2 skipped in 46.98s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-status identity fields hard cut

News source-status payload shaping now requires projected source identity/config text for `source_id`, `provider_type`, `source_domain`, `source_name`, `source_role`, and `trust_tier`. Damaged rows no longer publish repaired empty strings or stringified non-text values into `/api/news/sources/status`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields -q
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_id-None-news_source_status_source_id_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_id- -news_source_status_source_id_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[provider_type-None-news_source_status_provider_type_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[provider_type- -news_source_status_provider_type_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_domain-None-news_source_status_source_domain_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_domain-123-news_source_status_source_domain_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_name-None-news_source_status_source_name_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_role-None-news_source_status_source_role_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[trust_tier-None-news_source_status_trust_tier_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_coverage_tags tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_uses_plain_quality_diagnostics tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_marks_disabled_and_api_backed_capabilities -q
18 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
42 passed in 0.33s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-status identity fields hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6179 passed, 2 skipped in 51.29s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-status scalar fields hard cut

News source-status payload shaping now requires explicit `source_quality_status`, boolean `enabled` / `managed_by_config`, and non-negative integer config/counter fields (`refresh_interval_seconds`, `item_count`, `sync_high_watermark_ms`, `sync_overlap_ms`, `next_fetch_after_ms`, `consecutive_failures`). The read model no longer repairs missing, string, bool-as-int, or negative scalar values to public defaults.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_boolean_fields tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields -q
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_quality_status-None-news_source_status_source_quality_status_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields[source_quality_status- -news_source_status_source_quality_status_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_boolean_fields[enabled-None-news_source_status_enabled_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_boolean_fields[enabled-true-news_source_status_enabled_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_boolean_fields[managed_by_config-None-news_source_status_managed_by_config_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_boolean_fields[managed_by_config-1-news_source_status_managed_by_config_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[refresh_interval_seconds-None-news_source_status_refresh_interval_seconds_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[refresh_interval_seconds-300-news_source_status_refresh_interval_seconds_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[refresh_interval_seconds-True-news_source_status_refresh_interval_seconds_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[refresh_interval_seconds--1-news_source_status_refresh_interval_seconds_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[item_count-None-news_source_status_item_count_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[sync_high_watermark_ms-None-news_source_status_sync_high_watermark_ms_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[sync_overlap_ms-0-news_source_status_sync_overlap_ms_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[next_fetch_after_ms-None-news_source_status_next_fetch_after_ms_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields[consecutive_failures-0-news_source_status_consecutive_failures_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_source_identity_fields tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_boolean_fields tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_counter_fields tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_uses_plain_quality_diagnostics tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_redacts_secret_error_fragments tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_marks_disabled_and_api_backed_capabilities -q
27 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
57 passed in 0.40s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-status scalar fields hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6194 passed, 2 skipped in 45.45s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-status latest fetch run hard cut

Present `latest_fetch_run_json` payloads now require explicit non-empty `status` plus non-negative integer fetch counters. The source-status read path no longer repairs malformed present fetch-run sections to `unknown` status or zero counts.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars -q
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update0-news_source_status_latest_fetch_run_status_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update1-news_source_status_latest_fetch_run_status_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update2-news_source_status_latest_fetch_run_fetched_count_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update3-news_source_status_latest_fetch_run_fetched_count_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update4-news_source_status_latest_fetch_run_inserted_count_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update5-news_source_status_latest_fetch_run_updated_count_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_fetch_run_scalars[latest_fetch_run_update6-news_source_status_latest_fetch_run_duplicate_count_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.36s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
64 passed in 0.44s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
1 file reformatted, 2 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-status latest fetch run hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6201 passed, 2 skipped in 47.89s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 source-status provider helper hard cut

Source-status provider health and capability helpers now consume already-validated projected fields instead of re-reading and repairing raw row values. Present latest-quality diagnostics also require explicit non-empty `status`; provider health no longer falls back from malformed latest-quality diagnostics to `source_quality_status`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics -q
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics[latest_quality_json2-news_source_status_latest_quality_diagnostics_status_required]
FAILED tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics[latest_quality_json3-news_source_status_latest_quality_diagnostics_status_required]
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_diagnostics tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_uses_plain_quality_diagnostics tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_marks_disabled_and_api_backed_capabilities -q
6 passed in 0.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.48s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_hygiene_uses_projected_provider_health_without_quality_status_fallback -q
66 passed in 0.60s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-status provider helper hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6203 passed, 2 skipped in 48.03s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 current-policy material duplicate diagnostics hard cut

Current-policy material duplicate diagnostics now validate their projected OpenNews row contract before grouping. Missing or malformed `provider_type`, `source_id`, `news_item_id`, `title`, `published_at_ms`, or `provider_token_impacts_json` fails at the diagnostics boundary instead of silently skipping malformed rows, treating timestamps as `0`, or surfacing lower-level material identity errors.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_current_policy_material_duplicate_groups_rejects_malformed_opennews_rows tests/unit/domains/news_intel/test_news_repository_queries.py::test_current_policy_material_duplicate_groups_rejects_missing_opennews_contract_fields -q
21 failed in 0.63s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_policy_material_duplicate_diagnostics_reject_malformed_rows -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_policy_material_duplicate_diagnostics_reject_malformed_rows
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_current_policy_material_duplicate_groups_reports_valid_opennews_duplicates tests/unit/domains/news_intel/test_news_repository_queries.py::test_current_policy_material_duplicate_groups_rejects_malformed_opennews_rows tests/unit/domains/news_intel/test_news_repository_queries.py::test_current_policy_material_duplicate_groups_rejects_missing_opennews_contract_fields tests/unit/domains/news_intel/test_news_repository_queries.py::test_current_policy_material_duplicate_groups_skips_non_opennews_after_provider_type_validation -q
23 passed in 0.14s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_policy_material_duplicate_diagnostics_reject_malformed_rows -q
1 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
383 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
125 passed in 3.89s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after current-policy material duplicate diagnostics hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6227 passed, 2 skipped in 47.84s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ git diff --check
exit code: 0
```

## 2026-06-19 latest-quality source-status scalar hard cut

Source-status latest-quality read payloads now require explicit projected identity and counters. Present latest-quality rows must carry non-empty `row_id`, `source_id`, `window`, and `projection_version`; non-negative integer `computed_at_ms`, `items_fetched`, and `items_inserted`; and optional `median_lag_ms` must be non-negative when present. Malformed rows now fail at the source-status boundary instead of being stringified, cast, or defaulted to `0`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_scalars -q
19 failed in 0.32s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_latest_quality_scalars -q
19 passed in 0.14s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.62s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py -q
83 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
125 passed in 3.97s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
1 file reformatted, 2 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after latest-quality source-status scalar hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6246 passed, 2 skipped in 45.74s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ git diff --check
exit code: 0
```

## 2026-06-19 source-quality write payload scalar hard cut

Source-quality projection writes now require explicit writer payload identity, counters, and diagnostics before payload hash or SQL. Missing or malformed `row_id`, `source_id`, `window`, `projection_version`, `computed_at_ms`, `items_fetched`, `items_inserted`, `median_lag_ms`, or `diagnostics_json` fails before repository SQL instead of being stringified, cast, or defaulted.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_write_payload_rejects_malformed_required_scalars -q
19 failed in 0.38s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_quality_write_payload_rejects_malformed_required_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_quality_write_payload_rejects_malformed_required_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_write_payload_rejects_malformed_required_scalars tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys tests/unit/domains/news_intel/test_source_quality_projection.py::test_replace_source_quality_rows_updates_source_status_freshness -q
21 passed in 0.29s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_quality_write_payload_rejects_malformed_required_sections -q
1 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py -q
102 passed in 0.26s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
126 passed in 4.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-quality write payload scalar hard cut

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6266 passed, 2 skipped in 52.16s.
compileall completed for src and tests.
exit code: 0
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not measured for this targeted backend slice | Not applicable | Not applicable |
| branch | Not measured for this targeted backend slice | Not applicable | Not applicable |

## Skipped tests

- Full integration and runtime golden-path verification are deferred by explicit user instruction on 2026-06-18.
- Frontend `npm run lint`, frontend architecture tests, frontend typecheck, and frontend format check passed as part of `make check`.
- Runtime `/readyz`, `/api/recent`, and WebSocket golden-path checks remain pending for the full final verification gate.

## E2E golden path

Runtime golden path is deferred for the full feature gate.

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

## 2026-06-19 source-quality diagnostics status hard cut

Source-quality writer payloads now require `diagnostics_json.status` before SQL and source-status updates. Missing or blank status fails as malformed projection output instead of updating `news_sources.source_quality_status` to `unknown`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_write_payload_rejects_malformed_required_scalars -q
3 failed, 19 passed in 0.37s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_quality_write_payload_rejects_malformed_required_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_quality_write_payload_rejects_malformed_required_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_write_payload_rejects_malformed_required_scalars tests/unit/domains/news_intel/test_source_quality_projection.py::test_replace_source_quality_rows_updates_source_status_freshness tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys -q
24 passed in 0.20s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_quality_write_payload_rejects_malformed_required_sections -q
1 passed in 0.22s
exit code: 0
```

## 2026-06-19 source-status present section hard cut

Source-status shaping now distinguishes absent latest sections from present malformed sections. `latest_quality_json = {}` and `latest_fetch_run_json = {}` fail through required field validation instead of being treated as missing read-model state.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_empty_present_optional_sections -q
2 failed in 0.18s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_empty_present_optional_sections tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_status_payload_rejects_malformed_present_diagnostic_sections -q
6 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_status_payload_rejects_malformed_present_sections -q
1 passed in 0.55s
exit code: 0
```

## 2026-06-19 configured source policy mapping hard cut

Configured-source write payloads now require `authority_scope`, `fetch_policy`, and `cost_policy` to be mappings when present. Malformed present values fail before SQL instead of being laundered into `{}`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_source_rejects_malformed_policy_mappings_before_sql -q
3 failed in 0.35s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_upsert_returning_row_requires_cursor_rowcount_match -q
FAILED tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_upsert_returning_row_requires_cursor_rowcount_match
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_source_rejects_malformed_policy_mappings_before_sql tests/unit/domains/news_intel/test_news_repository_queries.py::test_upsert_source_returning_row_accepts_matching_required_row -q
4 passed in 0.18s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_source_upsert_returning_row_requires_cursor_rowcount_match -q
1 passed in 0.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py -q
386 passed in 0.90s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py -q
107 passed in 0.52s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
126 passed in 6.58s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
4 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 non-integration regression after source-quality/source-status/source-policy hard cuts

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6274 passed, 2 skipped in 44.98s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ git diff --check
exit code: 0
```

## 2026-06-19 source/projection scalar hard cuts

Additional News runtime/read-model contracts now fail closed instead of repairing malformed values:

- News item source-watermark loaders require positive integer `source_watermark_ms`.
- Source sync cursor reads require explicit non-negative integer `sync_high_watermark_ms` / `sync_overlap_ms` when present.
- Item/story brief target loaders require positive integer `source_updated_at_ms`.
- News dedup diagnostics require typed summary row counts and JSON sections.
- OpenNews fetch cursor high-watermark/overlap scalars reject malformed present values.
- News page projection source payload requires explicit `source_quality_status` instead of defaulting to `unknown`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_item_source_watermark_loaders_require_positive_int_before_dirty_enqueue -q
15 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_source_sync_cursor_requires_explicit_nonnegative_sync_scalars -q
8 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_brief_target_loaders_require_positive_source_updated_at -q
10 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_dedup_diagnostics_rejects_malformed_summary_row -q
7 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_workers.py::test_opennews_fetch_since_rejects_malformed_present_cursor_scalars -q
8 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_page_source_status_requires_explicit_source_quality_status -q
3 failed
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_news_page_projection.py -q
667 passed
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
130 passed
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/services/news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_workers.py
8 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/services/news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_workers.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6328 passed, 2 skipped in 43.15s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ git diff --check
exit code: 0
```

## 2026-06-19 fetch/item aggregate hard cuts

Additional News write/input comparison contracts now fail closed instead of repairing malformed values:

- `finish_fetch_run` requires explicit completion status, finished timestamp, fetch/insert/update/duplicate counts, optional HTTP status, and present `extra_json` mapping before SQL.
- Fetch-worker failed-run closeout now writes explicit zero counts rather than relying on repository defaults.
- Item-brief packet construction requires a positive integer `published_at_ms`.
- Token mention lanes require explicit `resolution_status` instead of defaulting to `unknown`.
- News item aggregate summary comparison requires typed duplicate count and evidence arrays instead of treating malformed rows as `0` / `[]`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_finish_fetch_run_requires_explicit_nonnegative_counts -q
8 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_finish_fetch_run_requires_explicit_completion_scalar_contract -q
12 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_item_packet_requires_explicit_positive_published_at_ms -q
5 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_brief_input.py::test_item_packet_requires_token_resolution_status -q
3 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_item_aggregate_changed_rejects_malformed_summary_fields -q
8 failed
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/unit/domains/news_intel/test_news_workers.py -q
531 passed
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
133 passed
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/services/news_item_brief_input.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_item_brief_input.py tests/architecture/test_news_intel_kiss_simplification.py tests/integration/domains/news_intel/test_news_source_quality_repository.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6367 passed, 2 skipped in 43.28s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 notification projected-payload hard cuts

Additional News high-signal notification contracts now fail closed instead of repairing or publishing malformed projected fields:

- External push signatures require ready-brief `direction` through the required agent-brief text helper; missing ready-brief direction no longer hashes to a `None`-direction signature.
- `duplicate_count` must be an explicit non-negative integer instead of `_int(...)->0` repair.
- `source_domain` must be an explicit projected text field; notification body no longer falls back to `unknown`.
- `agent_admission_status` and `agent_admission_reason` must be explicit projected text fields instead of publishing `None`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_external_push_signature_requires_ready_brief_direction_without_none_signature -q
1 failed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
4 failed, 24 passed
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
6 failed, 28 passed
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_notification_rules.py::test_news_high_signal_uses_ready_agent_brief_for_display_and_builds_push_signatures tests/unit/test_notification_rules.py::test_news_external_push_signature_requires_ready_brief_direction_without_none_signature -q
36 passed in 0.58s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback -q
2 passed in 0.16s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py -q
217 passed in 4.58s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6381 passed, 2 skipped in 43.68s.
compileall completed for src and tests.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ git diff --check
exit code: 0
```

## 2026-06-19 completed-run timestamp hard cuts

Completed-run restore now requires typed positive integer `finished_at_ms` for both story-current and retained item-brief audit workers. String or float timestamps no longer get repaired with `int(value)` before restoring current state.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_malformed_finished_at_without_clock_fallback tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_malformed_finished_at_without_clock_fallback -q
4 failed, 4 passed
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py::test_worker_rejects_completed_story_run_malformed_finished_at_without_clock_fallback tests/unit/domains/news_intel/test_news_item_brief_worker.py::test_worker_rejects_completed_run_malformed_finished_at_without_clock_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_worker_uses_formal_audit_validation_and_admission_contracts_without_reflection tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_worker_restores_started_failed_runs_without_model_fallback -q
10 passed in 0.38s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py -q
240 passed in 5.00s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
5 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6389 passed, 2 skipped in 42.78s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 page projection integer hard cuts

Page projection now requires typed positive integer timing/count inputs for public row identity: item `published_at_ms` and story `member_count` reject bool, string, float, and non-positive values instead of repairing them through `int(value)`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_published_at_without_int_repair tests/unit/domains/news_intel/test_news_page_projection.py::test_story_payload_rejects_malformed_member_count_without_int_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback -q
7 failed, 2 passed in 0.24s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_published_at_without_int_repair tests/unit/domains/news_intel/test_news_page_projection.py::test_story_payload_rejects_malformed_member_count_without_int_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_requires_story_payload_without_item_fallback -q
9 passed in 0.09s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q
208 passed in 4.80s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6397 passed, 2 skipped in 42.79s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 page projection timing hard cuts

Page projection and page-row repository writes now require typed positive integer timing fields. `computed_at_ms`, `agent_brief_computed_at_ms`, and persisted page-row `latest_at_ms` / `computed_at_ms` / `agent_brief_computed_at_ms` reject bool, string, float, and non-positive values instead of repairing them through `int(...)`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_computed_at_without_int_repair tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_agent_brief_computed_at_without_int_repair tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_typed_timing_fields_before_write tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_timing_fields_require_typed_int_without_repair -q
22 failed in 1.07s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_computed_at_without_int_repair tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_agent_brief_computed_at_without_int_repair tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_typed_timing_fields_before_write tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_payload_requires_formal_json_sections_without_defaults tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_timing_fields_require_typed_int_without_repair -q
22 passed in 0.45s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py -q
668 passed in 4.98s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
5 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6418 passed, 2 skipped in 43.02s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 page row nonnegative count hard cuts

Page-row summary count validation now requires typed nonnegative integers. `duplicate_count` and summary `duplicate_observation_count` reject string and float values instead of repairing them through `int(value)`; `0` remains valid count state.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_summary_fields_before_write tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_summary_fields_require_explicit_payload_without_defaults -q
3 failed, 10 passed in 0.48s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_requires_formal_summary_fields_before_write tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_row_summary_fields_require_explicit_payload_without_defaults -q
13 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py -q
587 passed in 5.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
3 files left unchanged
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6420 passed, 2 skipped in 43.19s.
compileall completed for src and tests.
exit code: 0
```

## 2026-06-19 provider score and dirty-target scalar hard cuts

Page projection and item-admission provider rating signals now require a present, typed, nonnegative integer `score`; malformed string/float/bool values fail instead of being repaired through `int(...)`. News projection dirty-target enqueue now requires typed integer `priority` and positive typed integer `due_at_ms`; blank/string/float/bool values and zero due times fail instead of being repaired through `str(...)`, `int(...)`, or `or default_due_at_ms`. Source-quality projection counts and optional timing fields now require typed nonnegative integers when present; missing counts still keep the existing `0` count semantics, but malformed present values fail closed.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_provider_rating_score_without_int_repair -q
3 failed in 0.11s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_provider_rating_rejects_malformed_present_provider_signal -q
1 failed in 0.22s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_item_brief_work_rejects_malformed_priority_without_int_repair tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_story_brief_work_rejects_malformed_priority_without_int_repair -q
6 failed in 0.07s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_malformed_priority_without_int_repair -q
3 failed in 0.47s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py::test_source_quality_refresh_rejects_malformed_due_at_without_int_repair tests/unit/domains/news_intel/test_news_projection_work.py::test_source_quality_window_work_rejects_malformed_due_at_without_int_repair -q
8 failed in 0.07s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_malformed_row_due_at_without_int_repair tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_malformed_default_due_at_without_int_repair -q
8 failed in 0.49s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_provider_rating_rejects_malformed_score_without_int_repair -q
3 failed in 0.05s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_rows_rejects_malformed_present_count_without_int_repair tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_rows_rejects_malformed_optional_timing_without_int_repair tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_row_rejects_malformed_median_lag_without_int_repair -q
12 failed in 0.22s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_rejects_malformed_provider_rating_score_without_int_repair tests/unit/domains/news_intel/test_news_page_projection.py::test_build_news_page_row_does_not_mix_provider_signal_into_ready_agent_brief -q
4 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_item_brief_work_rejects_malformed_priority_without_int_repair tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_story_brief_work_rejects_malformed_priority_without_int_repair tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_item_brief_work_uses_model_work_priority tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_story_brief_work_uses_model_work_priority -q
10 passed in 0.07s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_malformed_priority_without_int_repair tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_stores_priority_due_at_and_reason tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_deduplicates_by_stable_window_key tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_allows_same_target_across_windows -q
4 passed in 0.47s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_work.py::test_source_quality_refresh_rejects_malformed_due_at_without_int_repair tests/unit/domains/news_intel/test_news_projection_work.py::test_source_quality_window_work_rejects_malformed_due_at_without_int_repair tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_source_quality_refresh_updates_all_sources tests/unit/domains/news_intel/test_news_projection_work.py::test_enqueue_source_quality_window_work_inserts_dirty_targets -q
9 passed in 0.07s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_malformed_row_due_at_without_int_repair tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_rejects_malformed_default_due_at_without_int_repair tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_stores_priority_due_at_and_reason tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_deduplicates_by_stable_window_key tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_enqueue_allows_same_target_across_windows -q
8 passed in 0.48s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_provider_rating_rejects_malformed_score_without_int_repair tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_provider_rating_gate_high_score_allows_agent tests/unit/domains/news_intel/test_news_item_agent_admission.py::test_provider_rating_gate_low_score_skips_agent -q
5 passed in 0.04s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_rows_rejects_malformed_present_count_without_int_repair tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_rows_rejects_malformed_optional_timing_without_int_repair tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_rows_are_deterministic tests/unit/domains/news_intel/test_source_quality_projection.py::test_build_source_quality_rows_counts_recent_and_older_items -q
9 passed in 0.05s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py -q
546 passed in 4.65s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/runtime/news_projection_work.py src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/services/news_item_agent_admission.py src/parallax/domains/news_intel/services/source_quality_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/services/news_page_projection.py src/parallax/domains/news_intel/runtime/news_projection_work.py src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py src/parallax/domains/news_intel/services/news_item_agent_admission.py src/parallax/domains/news_intel/services/source_quality_projection.py tests/unit/domains/news_intel/test_news_page_projection.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_agent_admission.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/architecture/test_news_intel_kiss_simplification.py
11 files already formatted
exit code: 0
```

Final non-integration gates after updating this evidence section:

```text
$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6470 passed, 2 skipped in 43.82s.
exit code: 0
```

## 2026-06-19 News high-signal notification scalar hard cuts

News high-signal notification shaping now requires typed story-current notification scalar fields. Malformed `agent_brief.status` fails instead of being treated as a non-ready/pending agent state, and pending/non-ready notification signal fields require projected text `alert_eligibility.decision_class` and signal direction instead of stringifying malformed values.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_agent_brief_status_without_pending_repair -q
1 failed in 0.73s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair -q
1 failed in 0.15s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_pending_signal_direction_without_string_repair -q
1 failed in 0.36s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair -q
1 failed in 0.14s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_agent_brief_status_without_pending_repair tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_pending_signal_direction_without_string_repair -q
2 passed in 0.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair -q
2 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py -q
86 passed in 0.35s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
30 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
1 file reformatted, 2 files left unchanged
exit code: 0
```

Final non-integration gates after this notification hard cut:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
116 passed in 0.81s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6474 passed, 2 skipped in 44.64s.
exit code: 0
```

## 2026-06-19 News high-signal ready summary type hard cut

News high-signal notification shaping now treats a present non-string ready `agent_brief.summary_zh` as malformed projected state instead of stringifying it into a publishable body or external push summary. Missing `summary_zh` still blocks external push as `agent_brief_missing_summary`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_ready_summary_without_string_repair -q
1 failed in 0.38s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
1 failed in 0.18s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_ready_summary_without_string_repair -q
1 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
1 passed in 0.02s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py -q
87 passed in 0.32s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
30 passed in 0.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

Final non-integration gates after this ready-summary hard cut:

```text
$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6476 passed, 2 skipped in 43.03s.
exit code: 0
```

## 2026-06-19 News high-signal public agent-brief payload text hard cut

News high-signal notification payloads now validate public `agent_brief` text fields before copying them into the in-app payload. Pending/non-ready rows with malformed present `direction`, `decision_class`, `title_zh`, `summary_zh`, or `market_read_zh` fail visibly instead of publishing malformed values.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_optional_text_without_payload_passthrough -q
5 failed in 0.42s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_agent_brief_requires_typed_text_without_payload_passthrough -q
1 failed in 0.17s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_optional_text_without_payload_passthrough -q
5 passed in 0.31s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_agent_brief_requires_typed_text_without_payload_passthrough -q
1 passed in 0.03s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py -q
92 passed in 0.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_agent_brief_requires_typed_text_without_payload_passthrough tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_pending_signal_fields_require_projected_text_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
30 passed in 0.13s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

Final non-integration gates after this notification payload hard cut:

```text
$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6490 passed, 2 skipped in 43.24s.
exit code: 0
```

## 2026-06-19 item-brief contract runtime helper cleanup

The retained item-brief contract module now only exposes constants and the SQL predicate still used by audit/source-quality query lanes. The unused Python runtime row gate `is_current_news_item_brief_contract` was removed so old item-current schema checks cannot be reintroduced as a public/runtime compatibility path.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate -q
1 failed in 0.15s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
2 passed in 0.17s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py -q
23 passed in 1.43s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_brief_schema_gate_uses_column_schema_version_only -q
3 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/types/news_item_brief_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/types/news_item_brief_contract.py tests/architecture/test_news_intel_kiss_simplification.py
2 files already formatted
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_brief_schema_gate_uses_column_schema_version_only -q
26 passed in 1.57s
exit code: 0

$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6475 passed, 2 skipped in 43.73s.
exit code: 0
```

## 2026-06-19 public agent-brief nested brief_json repair hard cut

Projected public `agent_brief` shaping now reads only top-level projected public fields. Nested `brief_json` is no longer inspected to repair missing public summary or list fields, so API item detail and page-row shaping cannot silently expose old item-brief payload fields. Malformed top-level public list fields still fail as projected row damage.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_ignores_present_brief_json_without_scalar_repair -q
2 failed in 0.91s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
1 failed in 0.20s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_item_detail_hides_retired_brief_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_ignores_present_brief_json_without_scalar_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
3 passed in 0.84s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py -q
23 passed in 1.19s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current -q
3 passed in 0.44s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_brief_schema_gate_uses_column_schema_version_only -q
26 passed in 1.99s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

## 2026-06-19 public agent-brief optional field shape hard cut

Projected public `agent_brief` shaping now validates present optional text, mapping, list, and non-negative integer fields before returning API payloads. Malformed present `title_zh`, `summary_zh`, `market_read_zh`, `event_type`, `bull_view`, `bear_view`, `computed_at_ms`, or `data_gap_count` fails as projected row damage instead of being exposed as-is.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_text_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_mapping_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_nonnegative_int_fields -q
8 failed in 0.80s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
1 failed in 0.20s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_text_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_mapping_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_nonnegative_int_fields -q
8 passed in 0.74s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
1 passed in 0.18s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py -q
31 passed in 1.32s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_contract_module_has_no_runtime_row_schema_gate tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_brief_schema_gate_uses_column_schema_version_only -q
3 passed in 0.08s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
3 files already formatted
exit code: 0
```

Final non-integration gates after this public agent-brief field-shape hard cut:

```text
$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6484 passed, 2 skipped in 43.68s.
exit code: 0
```

## 2026-06-19 News high-signal display title and affected-entity field hard cut

News high-signal notification candidate generation now validates all display-title sources before compaction: `agent_brief.title_zh`, projected `display_signal.title_zh`, and row `headline` may be absent and fall through to the next source, but malformed present values fail visibly instead of being stringified. Public notification `agent_brief.affected_entities` shaping also validates present member text fields and `evidence_refs` string lists before emitting payloads.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_agent_title_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_falls_back_when_agent_title_is_absent -q
1 failed, 1 passed in 0.37s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_agent_title_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_projected_title_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_headline_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_falls_back_when_agent_title_is_absent -q
2 failed, 2 passed in 0.36s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_affected_entity_text_fields tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_affected_entity_evidence_refs -q
6 failed in 0.40s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_display_title_requires_typed_agent_title_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_affected_entity_requires_typed_fields_without_passthrough -q
2 failed
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_agent_title_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_projected_title_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_rejects_malformed_headline_without_string_repair tests/unit/test_notification_rules.py::test_news_display_title_falls_back_when_agent_title_is_absent tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_optional_text_without_payload_passthrough -q
9 passed in 0.32s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_affected_entity_text_fields tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_affected_entity_evidence_refs -q
6 passed in 0.35s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_display_title_requires_typed_agent_title_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_agent_brief_requires_typed_text_without_payload_passthrough tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_affected_entity_requires_typed_fields_without_passthrough -q
3 passed
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py -q
102 passed in 0.36s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_signature_uses_ready_brief_direction_without_display_signal_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_agent_brief_status_requires_explicit_text_without_pending_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_display_title_requires_typed_agent_title_without_string_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_agent_brief_requires_typed_text_without_payload_passthrough tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_public_affected_entity_requires_typed_fields_without_passthrough tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks -q
8 passed in 0.12s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py tests/unit/test_notification_rules.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 API public agent-brief affected-entity field hard cut

API public `agent_brief.affected_entities` shaping now validates member text fields and `evidence_refs` string lists instead of only checking the outer list shape. Malformed present `label`, `symbol`, `name`, `entity_type`, `reason_zh`, or `evidence_refs` fails as projected payload damage before API response construction.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_affected_entity_text_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_affected_entity_evidence_refs -q
6 failed in 0.82s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
1 failed in 0.22s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_affected_entity_text_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_affected_entity_evidence_refs -q
6 passed in 0.73s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_public_agent_brief_payload_has_no_item_schema_downgrade_gate -q
1 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_news_contract.py -q
37 passed in 1.35s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py -q
102 passed in 0.35s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py -q
144 passed in 4.63s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/test_api_news_contract.py tests/architecture/test_news_intel_kiss_simplification.py
All checks passed!
exit code: 0
```

## 2026-06-19 News high-signal notification API sanitizer field hard cut

The notification API sanitizer now validates stored News high-signal `agent_brief` text fields and `affected_entities` member fields before returning notification payloads. This closes the read API boundary for historical malformed notification payloads even when the current notification rule engine already emits typed payloads.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_agent_brief_text_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_affected_entity_text_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_affected_entity_evidence_refs -q
11 failed in 0.72s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
1 failed in 0.05s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_agent_brief_text_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_affected_entity_text_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_affected_entity_evidence_refs -q
11 passed in 0.55s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
1 passed in 0.01s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py -q
159 passed in 1.70s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
168 passed in 5.00s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0
```

## 2026-06-19 News high-signal public token-impact field hard cut

News high-signal notification generation and API notification payload sanitization now validate present public `token_impacts` text fields before emitting payloads. `symbol` / `target_symbol` may be absent so an empty impact can be omitted, but malformed present `symbol`, `target_symbol`, or `market_type` fails visibly instead of being stringified or copied through.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
2 failed, 34 passed in 0.53s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_token_impact_text_fields -q
2 failed in 0.79s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
2 failed in 0.26s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections -q
36 passed in 0.38s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_token_impact_text_fields -q
2 passed in 0.57s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
2 passed in 0.06s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/unit/test_notification_rules.py -q
126 passed in 0.69s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
168 passed in 4.71s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0
```

## 2026-06-19 News high-signal notification API top-level payload hard cut

The notification API sanitizer now builds stored News high-signal public payloads from typed field groups instead of copying `_NEWS_HIGH_SIGNAL_PAYLOAD_KEYS` through wholesale. Present top-level text fields, `story` / `market_scope` / `agent_admission` mappings, `external_push_eligible`, and `duplicate_count` now fail closed when malformed; historical malformed stored payloads cannot leak through the read API.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_top_level_text_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_top_level_mapping_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_external_push_eligible tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_duplicate_count -q
21 failed in 0.66s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
1 failed in 0.04s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_top_level_text_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_top_level_mapping_fields tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_external_push_eligible tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_duplicate_count tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
22 passed in 0.60s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py -q
67 passed in 0.55s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py tests/unit/test_notification_rules.py tests/unit/test_api_news_contract.py tests/architecture/test_notifications_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py -q
352 passed in 6.21s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_api_notifications_contract.py tests/architecture/test_notifications_hard_cut.py
3 files already formatted
exit code: 0
```

## 2026-06-19 News high-signal notification mapping-member hard cut

News high-signal notification candidate generation and API payload sanitization now validate public members inside `story`, `market_scope`, and `agent_admission` payloads. Malformed story identity/count fields, market-scope public fields, and agent-admission public/status/basis/version/eligible fields now fail visibly instead of being copied through nested public mappings.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_top_level_mapping_member_fields -q
31 failed, 36 passed in 1.08s
exit code: 1

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
2 failed in 0.20s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_rejects_malformed_top_level_mapping_member_fields tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
69 passed in 0.72s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
346 passed in 5.25s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
6 files already formatted
exit code: 0
```

## 2026-06-19 News high-signal nested public mapping allowlist hard cut

News high-signal notification candidate generation and API payload sanitization now emit allowlisted public `story`, `market_scope`, and `agent_admission` objects instead of returning `{**payload, ...}` after validating selected fields. Unknown legacy or audit-like nested fields are dropped, while useful story source lists remain available only through typed optional string-list helpers.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_notification_rules.py::test_news_high_signal_public_mapping_payloads_drop_unknown_fields_without_passthrough tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_mapping_payloads_drop_unknown_fields_without_passthrough tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
5 failed, 53 passed in 0.92s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/unit/test_notification_rules.py::test_news_high_signal_public_mapping_payloads_drop_unknown_fields_without_passthrough tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_mapping_payloads_drop_unknown_fields_without_passthrough tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
58 passed in 0.75s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
349 passed in 5.10s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/notifications/services/notification_rules.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
All checks passed!
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/notifications/services/notification_rules.py src/parallax/app/surfaces/api/routes_notifications.py tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py
6 files already formatted
exit code: 0
```

## 2026-06-19 News high-signal canonical URL typed hard cut

News high-signal notification candidate generation now validates present `canonical_url` values before storing them in the payload or rendering the body. Malformed or blank present URLs fail visibly instead of being stringified, while absent URLs remain omitted.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
3 failed, 54 passed in 0.59s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
57 passed in 0.41s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
351 passed in 5.01s
exit code: 0
```

## 2026-06-19 News high-signal external push block reason typed hard cut

News high-signal external push readiness now validates present `alert_eligibility.external_push_block_reason` values before using them as suppression reasons. Missing block reasons still use `external_push_state_missing`, but malformed present values fail visibly instead of being stringified or collapsed to the default.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
3 failed, 56 passed in 0.51s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
59 passed in 0.39s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
353 passed in 4.88s
exit code: 0
```

## 2026-06-19 News high-signal external push ready bool typed hard cut

News high-signal external push readiness now validates present `alert_eligibility.external_push_ready` values as booleans. Missing values still mean the push state is not ready, but malformed present values fail visibly instead of being treated as ordinary suppression.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
2 failed, 58 passed in 0.55s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
60 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
354 passed in 4.89s
exit code: 0
```

## 2026-06-19 News high-signal present block reason always typed hard cut

News high-signal external push readiness now validates present `alert_eligibility.external_push_block_reason` before branching on `external_push_ready`. Ready push paths no longer allow malformed present block reasons to pass just because the field is not used for suppression.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
2 failed, 59 passed in 0.49s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
61 passed in 0.30s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
355 passed in 4.83s
exit code: 0
```

## 2026-06-19 News high-signal in-app eligibility required-true hard cut

News high-signal notification candidate generation now requires projected `alert_eligibility.in_app_eligible` to be explicitly `true` at the rule boundary. Missing, false, or non-boolean values are treated as a broken candidate/query contract rather than emitted as in-app notifications.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
4 failed, 60 passed in 0.79s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
64 passed in 0.46s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
358 passed in 5.04s
exit code: 0
```

## 2026-06-19 News high-signal external push basis hard cut

News high-signal external push readiness now requires ready projected candidates to carry `alert_eligibility.external_push_basis == "agent_brief"`. Missing, blank, malformed, or wrong basis values fail visibly instead of allowing an external push.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
5 failed, 63 passed in 0.43s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_rejects_malformed_projected_payload_sections tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_external_push_summary_has_no_market_read_fallback -q
68 passed in 0.34s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
362 passed in 5.49s
exit code: 0
```

## 2026-06-19 News high-signal API agent-brief status hard cut

Stored News high-signal notification payload sanitization now requires a present `agent_brief` object to carry typed `status`. Missing status in an otherwise present brief fails visibly instead of emitting a partial public agent brief.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_requires_agent_brief_status_when_present tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
2 failed in 0.58s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_notifications_contract.py::test_news_high_signal_notification_requires_agent_brief_status_when_present tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
2 passed in 0.52s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
363 passed in 5.06s
exit code: 0
```

## 2026-06-19 News high-signal affected-entity alias hard cut

News high-signal notification asset identity now reads only formal `affected_entities[].symbol`. Legacy `ticker` / `asset` aliases no longer drive candidate symbols, semantic signatures, or external push asset buckets, and the persisted top-level `affected_entities` payload is the same public allowlisted shape used inside `agent_brief`.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_affected_entities_ignore_legacy_symbol_aliases tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_affected_entity_symbols_use_formal_symbol_only -q
2 failed in 0.49s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py::test_news_high_signal_affected_entities_ignore_legacy_symbol_aliases tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_affected_entity_symbols_use_formal_symbol_only -q
2 passed in 0.27s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
365 passed in 4.94s
exit code: 0
```

## 2026-06-19 News high-signal dead payload-key set cleanup

The notification API sanitizer no longer keeps the unused `_NEWS_HIGH_SIGNAL_PAYLOAD_KEYS` set after the read path moved to typed field-by-field public shaping. The sanitizer contract is now expressed only by the field groups and helper calls it actually uses.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
1 failed in 0.05s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_notifications_hard_cut.py::test_notification_api_sanitizes_news_high_signal_payloads -q
1 passed in 0.01s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
365 passed in 5.49s
exit code: 0
```

## 2026-06-19 News high-signal unused optional-list helper cleanup

Notification rule shaping no longer keeps the unused `_optional_news_list` helper. News high-signal list contracts now flow through active typed helpers only, so missing/optional list semantics stay attached to the concrete field that owns them.

RED before implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
1 failed in 0.27s
exit code: 1
```

GREEN after implementation:

```text
$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_notification_rejects_malformed_projected_payload_sections -q
1 passed in 0.11s
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_notification_rules.py tests/unit/test_api_notifications_contract.py tests/architecture/test_news_intel_kiss_simplification.py tests/architecture/test_notifications_hard_cut.py -q
365 passed in 4.96s
exit code: 0
```

Final non-integration gates after the display-title, affected-entity, token-impact, notification API sanitizer field, top-level payload, mapping-member, nested public mapping allowlist, canonical URL typed, external push block reason typed, external push ready bool typed, present block reason always typed, in-app eligibility required-true, external push basis, API agent-brief status, affected-entity alias, dead payload-key set, and unused optional-list helper hard cuts:

```text
$ git diff --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup, 2026-06-12-kappa-cqrs-governance-root-fix, 2026-06-16-macro-decision-console, 2026-06-18-news-trading-agent-hard-cut
exit code: 0

$ UV_CACHE_DIR=/tmp/parallax-uv-cache make check
All checks passed!
1079 files already formatted
Success: no issues found in 648 source files
web typecheck passed; web lint passed with 14 architecture test files / 74 tests passed; web format:check passed.
Python unit/architecture/contract lane: 6594 passed, 2 skipped in 45.72s.
exit code: 0
```

## Source review evidence

The research document was rewritten after reviewing:

- `src/parallax/domains/news_intel/types/news_canonical_identity.py`
- `src/parallax/domains/news_intel/types/news_url_identity.py`
- `src/parallax/domains/news_intel/types/news_material_identity.py`
- `src/parallax/domains/news_intel/services/feed_item_normalizer.py`
- `src/parallax/domains/news_intel/services/news_story_identity.py`
- `src/parallax/domains/news_intel/services/news_story_similarity.py`
- `src/parallax/domains/news_intel/services/news_item_agent_admission.py`
- `src/parallax/domains/news_intel/services/news_material_delta.py`
- `src/parallax/domains/news_intel/services/news_item_brief_input.py`
- `src/parallax/domains/news_intel/services/news_page_projection.py`
- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- `src/parallax/domains/news_intel/runtime/news_page_projection_worker.py`
- `src/parallax/domains/news_intel/runtime/news_projection_work.py`
- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `src/parallax/platform/db/alembic/versions/20260531_0131_news_story_projection_hard_cut.py`
- `src/parallax/platform/db/alembic/versions/20260531_0137_news_dirty_projection_hard_cut.py`
- `tests/unit/domains/news_intel/test_news_projection_dirty_targets.py`
- `tests/unit/domains/news_intel/test_news_repository_queries.py`
- Existing News Intel unit/integration/architecture tests around dedupe, admission, dirty targets, projection, and worker reuse.
