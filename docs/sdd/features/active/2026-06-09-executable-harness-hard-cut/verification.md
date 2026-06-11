# Verification — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/plan.md`
**Branch**: `codex/agent-factory-eval-harness`
**Worktree**: `.worktrees/agent-factory-eval-harness`
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Diff**: Pending final diff.

The plan and spec are the contract. This file is the evidence the contract was met. No `done`, `fixed`, or `passing`
claim is allowed without the corresponding output captured below.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — false `Verified` records fail. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q` passed. |
| AC2 — incomplete task coordination fails. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q` passed. |
| AC3 — coordination board is generated and current. | ✅ | `uv run python scripts/regen_sdd_work_index.py --check` passed. |
| AC4 — SQL helper supports semantic query contracts. | ✅ | `uv run pytest tests/unit/test_query_contract.py tests/unit/domains/macro_intel -q` passed. |
| AC5 — `make check-all` includes deterministic harness gates. | ⚠️ | `make check-all` started and ran the new SDD validator/index gates, then was stopped during integration per user instruction. |
| AC6 — development-agent factory/eval loop is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q` passed. |
| AC7 — SDD task context-packet CLI is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q` and `uv run python scripts/build_agent_context_packet.py --feature 2026-06-09-executable-harness-hard-cut --task 7 --mode read-only` passed. |
| AC8 — SDD dry-run dispatcher emits handoff and refuses completed tasks. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q` passed; real Task 5 dispatch emitted a handoff and real Task 8 dispatch was refused. |
| AC9 — task field values are semantically validated. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q` passed. |
| AC10 — Verified evidence parser ignores stale success snippets. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q` passed. |
| AC11 — generated SDD index exposes task-level dispatch state. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` passed. |
| AC12 — dependency-aware task dispatch is executable. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` passed. |
| AC13 — subagent return report validation is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q` passed. |
| AC14 — parent review outcome is task state. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` passed. |
| AC15 — delegated report artifacts are validated. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q` passed. |
| AC16 — completed task verification evidence is executable. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q` passed. |
| AC17 — machine-readable `not delegated` token is exact. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q` passed. |
| AC18 — delegated handoff artifacts are validated. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q` passed. |
| AC19 — artifact lifecycle statuses are consistent. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q` passed after first failing RED run. |
| AC20 — superseded successor metadata is machine-readable. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q` passed after first failing RED run. |
| AC21 — feature directories contain exactly four artifacts. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q` passed after first failing RED run; legacy macro SDD attachments were deleted. |
| AC22 — completed tasks cannot depend on incomplete tasks. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q` passed after first failing RED run; Task 6 dependency was corrected from `Tasks 1-5` to `Tasks 1-4`. |
| AC23 — completed-task evidence only counts inside evidence sections. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q` passed after first failing RED run. |
| AC24 — superseded records still carry approval metadata. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q` passed after first failing RED run; completed SDD records were backfilled. |
| AC25 — superseded records retain structured tasks. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q` passed after first failing RED run; legacy governance completed tasks were converted. |
| AC26 — superseded records share one successor. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q` passed after first failing RED run. |
| AC27 — completed tasks require review evidence. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q` passed after first failing RED run. |
| AC28 — task DAG numbers are unique and contiguous. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q` passed after first failing RED run. |
| AC29 — artifact owning links stay inside the feature. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q` passed after first failing RED run. |
| AC30 — plan commands cover spec acceptance criteria. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q` passed after first failing RED run. |
| AC31 — acceptance numbers are unique and contiguous. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q` passed after first failing RED run. |
| AC32 — plan acceptance commands are command-shaped. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q` passed after first failing RED run. |
| AC33 — plan acceptance command lines are exact. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q` passed after first failing RED run. |
| AC34 — feature slugs and artifact dates are machine-valid. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q` passed after first failing RED run. |
| AC35 — gate sections require structured evidence. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q` passed after first failing RED run. |
| AC36 — acceptance criteria use executable format. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q` passed after first failing RED run. |
| AC37 — Verified spec-compliance rows require command evidence. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q` passed after first failing RED run. |
| AC38 — Worktree/Branch metadata is machine-valid. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q` passed after first failing RED run. |
| AC39 — Spec Background claim blocks are source-backed. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q` passed after first failing RED run. |
| AC40 — Checked plan Pre-flight Worktree/Branch claims match metadata. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q` passed after first failing RED run. |
| AC41 — Delegated subagent handoff artifacts are task-bound. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q` passed after first failing RED run. |
| AC42 — Delegated subagent report mode matches handoff mode. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q` passed after first failing RED run. |
| AC43 — Factory lane values are bounded to the operating model. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q` passed after first failing RED run. |
| AC44 — Analyze Gate result statuses are machine-bounded. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q` passed after first failing RED run. |
| AC45 — Completed task failing-test references are evidenced. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence -q` passed after first failing RED run. |
| AC46 — Generated CLI help docs are freshness-checked. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot -q` passed after first failing RED run; `uv run python scripts/regen_cli_help.py --check` exited 0. |
| AC47 — Public contracts docs are source-bound. | ✅ | `uv run pytest tests/architecture/test_public_contracts_doc_alignment.py -q` failed RED on stale CONTRACTS worker/lane/WS/route docs, then passed after docs and harness updates. |
| AC48 — Generated README source-map rows point to real files. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths -q` failed RED on stale `src/parallax/api/ws.py`, then passed after README/script updates. |
| AC49 — Active touch conflicts catch nested paths and misdirected coordination. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination -q` failed RED with no `active-touch-conflict`, then passed after validator updates. |
| AC50 — Frontend docs and skill are source-aligned. | ✅ | `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts` failed RED on stale CSS bucket/budget/shell/skill wording, then passed after docs and skill updates. |
| AC51 — Frontend feature-boundary scan derives feature roots. | ✅ | `cd web && npm run test -- tests/architecture/featureBoundaries.test.ts` failed RED on omitted `macro/news/ops/token-case` and stale `token-target`, then passed after source-derived scan updates. |
| AC52 — Frontend data ownership gate is executable. | ✅ | `cd web && npm run test -- tests/architecture/frontendDataOwnership.test.ts` failed RED on missing docs binding, then passed after the docs and static source gate were added. |
| AC53 — Agent router frontend guardrails are source-aligned. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness -q` failed RED on missing `macro.css`, then passed after AGENTS/CLAUDE shared router updates. |
| AC54 — Frontend verification skill carries data ownership. | ✅ | `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts` failed RED on missing `frontendDataOwnership.test.ts` in the skill, then passed after the skill and doc-contract update. |
| AC55 — Architecture docs reference executable tests. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing -q` failed RED on bare `test_legacy_asset_repository_is_not_imported`, then passed after path qualification and parser tightening. |
| AC56 — Architecture module map links current domain docs. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc -q` failed RED on the non-linked Narrative row, then passed after converting it to a markdown link. |
| AC57 — Architecture test taxonomy inventory is exact. | ✅ | `uv run pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy -q` failed RED on missing `test_public_contracts_doc_alignment.py`, then passed after exact-set validation and docs update. |
| AC58 — Open tech debt source/test/doc references are live and self-contained. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q` failed RED on stale TECH_DEBT file/function references, bare `::test` shorthand, and unrooted source/doc paths, then passed after removing deleted historical integration rows and making references self-contained. |
| AC59 — Governance rule checks avoid prose overfit. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_rule_ownership tests/architecture/test_harness_structure.py::test_routers_have_no_governance_phrases -q` passed after splitting the mixed rule test and replacing verbatim phrase keys with named multi-anchor contracts. |
| AC60 — Domain type modules are leaf nodes. | ✅ | `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers -q` failed RED on the evidence entity re-export shim, then passed after moving entity value objects and normalization primitives into `types/entity.py`. |
| AC61 — Domain interfaces stay runtime-free. | ✅ | `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules -q` failed RED on `token_intel.interfaces` importing `runtime.token_resolution_refresh`, then passed after moving the use case to `services/token_resolution_refresh.py` and deleting the runtime file. |
| AC62 — Open tech debt duplicate-symbol claims stay source-backed. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources -q` failed RED on the stale resolver-policy duplicate claim, then passed after removing that resolved TECH_DEBT row. |
| AC63 — Generated WebSocket docs expose current message kinds. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals -q` failed RED on class-only `ws-protocol.md`, then passed after the generator emitted source-derived WebSocket `type` literals. |
| AC64 — Generated WebSocket docs are freshness-checked. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot -q` failed RED before `check-all` ran `scripts/regen_ws_protocol.py --check`, then passed after adding the non-mutating generator check and Makefile gate. |
| AC65 — Generated score-version docs are freshness-checked. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot -q` failed RED before `check-all` ran `scripts/regen_score_versions.py --check`, then passed after adding the non-mutating generator check and Makefile gate. |
| AC66 — Non-DB generated docs are freshness-checked from the source map. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots -q` failed RED on missing `scripts/regen_pulse_agent_desk_decisions.py --check`, then passed after adding the non-mutating generator check and README-derived Makefile gate. |
| AC67 — Task-bound subagent reading evidence is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence -q` failed RED before task-bound reports required reading evidence, and `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q` failed RED before the handoff template named `## Required Reading Evidence`; both passed after adding validator and template coverage. |
| AC68 — Spec Background local citations are semantically anchored. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines -q` failed RED when an existing but wrong `docs/WORKFLOW.md:1` citation passed, then passed after requiring cited local lines to mention backticked evidence tokens and updating active Background citations. |
| AC69 — Worker runtime constraints are manifest-owned. | ✅ | `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification -q` passed after adding `WorkerRuntimeConstraint` to `WorkerManifest` and removing the test-owned classification map; the temporary RED assertion failed first because `WorkerManifest` had no `runtime_constraint`. |
| AC70 — Worker Inventory architecture tests use source manifests. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources -q` failed RED on `test_worker_inventory_contract.py` importing `test_worker_runtime_contracts`, then passed after deriving Worker Inventory expectations from `WorkerManifest`. |
| AC71 — Worker table ownership composition is manifest-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract -q` failed RED before `WorkerManifest` exposed `owned_tables`, then passed after adding the source-owned ownership contract and using it in manifest queue-health validation. |
| AC72 — Read-model writer mapping is manifest-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping -q` failed RED before `worker_manifest.py` exposed `read_model_writer_by_table()`, then passed after adding the source-owned read-model writer map and using it in Worker Inventory docs checks. |
| AC73 — Read-model writer uniqueness is manifest-validated. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers -q` failed RED when patched duplicate read-model writers did not raise, then passed after manifest validation reused `read_model_writer_by_table()`. |
| AC74 — Read-model identity ownership is manifest-validated. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities -q` failed RED when a patched unowned `current_read_model_identities` row did not raise, then passed after adding reverse ownership validation. |
| AC75 — Read-model identity entries are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries -q` failed RED when a patched duplicate `current_read_model_identities` entry did not raise, then passed after adding duplicate identity-entry validation. |
| AC76 — Worker table declarations are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations -q` failed RED when a patched duplicate `writes_control_plane` table declaration did not raise, then passed after adding per-field duplicate table-declaration validation. |
| AC77 — Read-model identity columns are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns -q` and `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q` failed RED when duplicate stable identity columns did not raise, then passed after adding manifest and publisher duplicate-column validation. |
| AC78 — Read-model identity columns are non-empty. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns -q` failed RED when a patched empty `current_read_model_identities` column tuple did not raise, then passed after adding manifest empty-column validation. |
| AC79 — Worker table declarations are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations -q` failed RED when a patched blank `writes_control_plane` table declaration did not raise, then passed after adding blank table-declaration validation. |
| AC80 — Read-model identity columns are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns -q` and `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q` failed RED when blank stable identity columns did not raise, then passed after adding manifest and publisher blank-column validation. |
| AC81 — Read-model identity tables are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables -q` failed RED when a patched blank `current_read_model_identities` table name was masked by a later missing-identity error, then passed after adding manifest blank identity-table validation. |
| AC82 — Dirty-target consumers declare dirty targets. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets -q` failed RED when a patched `DIRTY_TARGET_CONSUMER` manifest with no `dirty_target_tables` did not raise, then passed after adding runtime-constraint validation. |
| AC83 — Leased-job consumers declare queue depth tables. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth -q` failed RED when a patched `LEASED_JOB_CONSUMER` manifest with no `queue_depth_table` did not raise, then passed after adding runtime-constraint validation. |
| AC84 — Bounded provider schedulers declare provider I/O. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io -q` failed RED when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest with `uses_provider_io=False` did not raise, then passed after adding runtime-constraint validation. |
| AC133 — Bounded provider schedulers do not declare dirty targets. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_dirty_targets -q` failed RED when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest could declare `dirty_target_tables`, then passed after adding provider scheduler dirty-target validation. |
| AC134 — Bounded provider schedulers do not declare queue depth tables. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_depth -q` failed RED when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest could declare `queue_depth_table`, then passed after adding provider scheduler queue-depth validation. |
| AC135 — Bounded provider schedulers do not declare queue health tables. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_health_tables -q` failed RED when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest could declare `queue_health_tables`, then passed after adding provider scheduler queue-health validation. |
| AC85 — Queue depth tables are worker-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q` failed RED when a patched `queue_depth_table` outside `owned_tables` did not raise, then passed after adding queue-depth ownership validation. |
| AC136 — Queue depth tables are control-plane-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane -q` failed RED when a patched owned fact table could masquerade as `queue_depth_table`, then passed after adding queue-depth control-plane ownership validation. |
| AC137 — Queue health tables are control-plane-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane -q` failed RED when a patched owned read-model table could masquerade as `queue_health_tables`, then passed after adding queue-health control-plane ownership validation. |
| AC86 — Side-effect ledgers belong to side-effect workers. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q` failed RED when a patched non-side-effect manifest with `side_effect_ledgers` did not raise, then passed after adding ledger-kind validation. |
| AC87 — Wake channels are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q` failed RED when a patched blank `wakes_out` channel did not raise, then passed after adding wake-channel validation. |
| AC88 — Wake channels are unique per worker field. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q` failed RED when a patched duplicate `wakes_on` channel did not raise, then passed after adding wake-channel duplicate validation. |
| AC89 — Advisory lock keys are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q` failed RED when two patched manifests shared one `advisory_lock_key`, then passed after adding advisory-lock duplicate validation. |
| AC90 — Advisory lock keys are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q` failed RED when a patched blank `advisory_lock_key` did not raise, then passed after adding advisory-lock blank-key validation. |
| AC91 — Worker identity fields are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q` failed RED when a patched blank `name` did not raise, then passed after adding identity-field validation. |
| AC92 — Idempotency evidence is non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence -q` failed RED when a patched blank `idempotency_evidence` did not raise, then passed after adding evidence validation. |
| AC93 — Input contracts are non-empty. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts -q` failed RED when a patched empty `input_contract` did not raise, then passed after adding input-contract validation. |
| AC94 — Input contracts are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts -q` failed RED when a patched blank `input_contract` entry did not raise, then passed after adding input-contract blank-entry validation. |
| AC95 — Ordering keys are non-empty. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys -q` failed RED when a patched empty `ordering_keys` declaration did not raise, then passed after adding ordering-key validation. |
| AC96 — Ordering keys are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys -q` failed RED when a patched blank `ordering_keys` entry did not raise, then passed after adding ordering-key blank-entry validation. |
| AC97 — Ordering keys are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys -q` failed RED when a patched duplicate `ordering_keys` entry did not raise, then passed after adding ordering-key duplicate validation. |
| AC98 — Input contracts are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts -q` failed RED when a patched duplicate `input_contract` entry did not raise, then passed after adding input-contract duplicate validation. |
| AC99 — Idempotency evidence is unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence -q` failed RED when a patched duplicate `idempotency_evidence` entry did not raise, then passed after adding idempotency-evidence duplicate validation. |
| AC100 — Worker runtime classes are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes -q` failed RED when a patched duplicate `worker_class` did not raise, then passed after adding worker-class duplicate validation. |
| AC101 — Worker start priorities are non-negative. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities -q` failed RED when a patched negative `start_priority` did not raise, then passed after adding start-priority validation. |
| AC102 — Worker start priorities are integer bands. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities -q` failed RED when a patched fractional `start_priority` did not raise, then passed after adding start-priority type validation. |
| AC103 — Worker factories are real source files. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules -q` failed RED when a patched missing `factory` did not raise, then passed after adding factory source-file validation. |
| AC104 — Worker class modules resolve. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules -q` failed RED when a patched missing `worker_class` module did not raise, then passed after adding worker-class module validation. |
| AC105 — Worker class names resolve. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names -q` failed RED when a patched missing `worker_class` class name did not raise, then passed after adding worker-class symbol validation. |
| AC106 — Worker domains are real source directories. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_domain_directories -q` failed RED when a patched missing `domain` did not raise, then passed after adding domain source-directory validation. |
| AC107 — Worker classifications are enum-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_raw_classification_values -q` failed RED when a patched raw string `lane` did not raise, then passed after adding classification enum validation. |
| AC108 — Provider I/O flags are boolean. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_boolean_provider_io_flags -q` failed RED when a patched truthy string `uses_provider_io` did not raise, then passed after adding provider-I/O flag type validation. |
| AC109 — Tuple manifest contracts reject compatibility lists. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_contract_fields -q` failed RED when a patched list-shaped `input_contract` did not raise, then passed after adding tuple-field validation. |
| AC110 — Tuple string contracts reject non-string entries. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_contract_entries -q` failed RED when a patched numeric `input_contract` entry leaked to `AttributeError`, then passed after adding tuple-entry validation. |
| AC111 — Read-model identity columns are tuples. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_columns -q` failed RED when a patched list-shaped stable identity column declaration did not raise, then passed after adding identity-column tuple validation. |
| AC112 — Read-model identity entries are tuples. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_entries -q` failed RED when a patched list-shaped stable identity entry did not raise, then passed after adding identity-entry tuple validation. |
| AC113 — Worker manifest imports are explicit. | ✅ | `uv run pytest tests/architecture/test_src_domain_architecture.py::test_worker_manifest_imports_in_clean_process_without_importlib_util_side_effect -q` failed RED in a temporary HEAD workspace when `worker_manifest.py` relied on `importlib.util` as an incidental package attribute, then passed after adding an explicit `import importlib.util`. |
| AC114 — Read-model identity entries are pairs. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_malformed_read_model_identity_entries -q` failed RED when a patched three-field stable identity entry leaked a Python unpacking error, then passed after adding identity-entry arity validation. |
| AC115 — Root visual artifacts are absent. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_repo_root_has_no_loose_visual_artifacts -q` failed RED in a temporary HEAD workspace with six root PNG artifacts, then passed after adding the root-artifact harness and removing those root PNG files. |
| AC116 — Queue-depth table declarations are strings. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_queue_depth_tables -q` failed RED when a patched numeric `queue_depth_table` leaked to `AttributeError`, then passed after adding queue-depth table type validation. |
| AC117 — Advisory lock declarations are strings. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_advisory_lock_keys -q` failed RED when a patched numeric `advisory_lock_key` leaked to `AttributeError`, then passed after adding advisory-lock key type validation. |
| AC118 — Worker identity fields are strings. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_identity_fields -q` failed RED when patched numeric identity fields leaked to `AttributeError`, then passed after adding identity-field type validation. |
| AC119 — Read-model identity tables are strings. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_tables -q` failed RED when a patched numeric stable identity table name leaked to `AttributeError`, then passed after adding identity-table type validation. |
| AC120 — Read-model identity columns are strings. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_columns -q` failed RED when a patched numeric stable identity column leaked to `AttributeError`, then passed after adding identity-column type validation. |
| AC121 — Publisher identity columns are strings. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q` failed RED when a numeric publisher identity column leaked to `AttributeError`, then passed after adding publisher identity-column type validation. |
| AC122 — Publisher payload hash columns are strings. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column -q` failed RED when a numeric payload hash column was silently accepted, then passed after adding publisher payload-hash column type validation. |
| AC123 — Publisher payload columns are tuples. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns -q` failed RED when list-shaped payload columns were silently accepted, then passed after adding publisher payload-column tuple validation. |
| AC124 — Publisher payload column entries are strings. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns -q` failed RED when a numeric payload column entry was silently accepted, then passed after adding publisher payload-column entry type validation. |
| AC125 — Publisher payload column entries are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns -q` failed RED when a blank payload column entry was silently accepted, then passed after adding publisher payload-column blank validation. |
| AC126 — Publisher payload hash columns are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column -q` failed RED when a blank payload hash column was silently accepted, then passed after adding publisher payload-hash column blank validation. |
| AC127 — Publisher payload column entries are unique. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_payload_columns -q` failed RED when duplicate payload column entries were silently accepted, then passed after adding publisher payload-column duplicate validation. |
| AC128 — Publisher payload hash columns are not lifecycle columns. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_hash_column -q` failed RED when a lifecycle payload hash column was silently accepted, then passed after adding publisher payload-hash lifecycle-column validation. |
| AC129 — Publisher payload columns exclude the payload hash column. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_payload_hash_payload_columns -q` failed RED when explicit payload columns could include the payload hash column, then passed after adding publisher payload hash self-reference validation. |
| AC130 — Publisher payload columns exclude lifecycle columns. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_columns -q` failed RED when explicit lifecycle payload columns were silently accepted, then passed after adding publisher payload lifecycle-column validation. |
| AC131 — Publisher payload hash columns are not identity columns. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_identity_payload_hash_column -q` failed RED when a payload hash column overlapping stable identity columns was silently accepted, then passed after adding publisher payload-hash identity-column validation. |
| AC132 — Publisher explicit payload columns exist in rows. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q` failed RED when a missing explicit payload column was silently hashed as `None`, then passed after making explicit payload hashing require declared row keys. |
| AC140 — Publisher missing payload columns use dedicated row-shape errors. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q` failed RED when missing explicit payload columns leaked as raw `KeyError`, then passed after adding a dedicated missing-payload-column validation error. |
| AC138 — Publisher changed rows require identity columns before hashing. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_identity_column_before_payload_hashing -q` failed RED when missing stable identity columns leaked as payload `KeyError`, then passed after validating row identity before payload hashing. |
| AC139 — Publisher changed-row batches reject duplicate identities. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_row_identities_in_batch -q` failed RED when duplicate stable row identities in one batch were accepted, then passed after adding batch identity uniqueness validation. |
| AC141 — Publisher changed rows reject non-string row columns. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_row_columns_before_write_preparation -q` failed RED when a non-string row key was accepted into changed-row write preparation, then passed after adding row-column validation. |
| AC142 — Publisher changed rows reject null identity values. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_null_row_identity_values_before_hashing -q` failed RED when `None` was accepted as a stable current-row identity value, then passed after adding null identity-value validation. |
| AC143 — Publisher changed rows reject blank identity values. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_row_identity_values_before_hashing -q` failed RED when a blank string was accepted as a stable current-row identity value, then passed after adding blank identity-value validation. |
| AC144 — Publisher identity columns reject list-shaped declarations. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_identity_columns -q` failed RED when list-shaped identity columns were accepted, then passed after adding tuple-shape validation. |
| AC145 — Publisher changed rows reject non-mapping row containers. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_rows_before_column_validation -q` failed RED when a list-shaped row was reported as non-string columns, then passed after adding dedicated mapping validation. |
| AC146 — Publisher changed rows reject non-mapping existing hashes. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_existing_hashes_before_hash_lookup -q` failed RED when list-shaped `existing_hashes` leaked as `AttributeError`, then passed after adding dedicated mapping validation. |
| AC147 — Publisher changed rows reject non-tuple existing-hash identities. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_existing_hash_identity_keys_before_hash_lookup -q` failed RED when string-shaped `existing_hashes` keys were accepted, then passed after adding dedicated identity-key validation. |
| AC148 — Publisher changed rows reject wrong-arity existing-hash identities. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_wrong_arity_existing_hash_identity_keys_before_hash_lookup -q` failed RED when wrong-arity tuple keys were accepted, then passed after adding dedicated identity-arity validation. |
| AC149 — Publisher changed rows reject non-string existing-hash values. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_existing_hash_values_before_hash_lookup -q` failed RED when numeric existing-hash values were accepted, then passed after adding dedicated hash-value validation. |
| AC150 — Publisher changed rows reject malformed existing-hash strings. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_malformed_existing_hash_values_before_hash_lookup -q` failed RED when malformed existing-hash strings were accepted, then passed after adding canonical payload-hash validation. |
| AC151 — Publisher changed rows reject malformed row batches. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q` failed RED when scalar batches leaked `TypeError` and mapping/string batches were iterated as rows, then passed after adding dedicated row-batch validation. |
| AC152 — Stable payload hash rejects malformed payload containers. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads -q` failed RED when scalar/string payloads leaked `dict(...)` errors and list-of-pairs payloads were accepted, then passed after adding dedicated payload-shape validation. |
| AC153 — Stable payload hash rejects non-string payload keys. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys -q` failed RED when numeric payload keys were stringified into a hash, then passed after adding dedicated payload-key validation. |
| AC154 — Stable payload hash rejects nested non-string payload keys. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys -q` failed RED when nested numeric payload keys were stringified into a hash, then passed after adding recursive payload-key validation and removing mapping-key string coercion from `_json_ready()`. |
| AC155 — Stable payload hash rejects generic isoformat payload values. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values -q` failed RED when an arbitrary `isoformat()` object was accepted into a hash, then passed after adding recursive payload-value validation and restricting ISO formatting to real date/time values. |
| AC156 — Stable payload hash rejects non-finite payload numbers. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers -q` failed RED when float NaN/Infinity leaked raw JSON errors and Decimal NaN/Infinity was accepted, then passed after adding recursive non-finite number validation. |
| AC157 — Stable payload hash rejects unordered payload containers. | ✅ | `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers -q` failed RED when set/frozenset payload values were sorted into hashes, then passed after rejecting unordered containers and removing set/frozenset sorting from `_json_ready()`. |
| AC158 — CEX board hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys -q` failed RED when the CEX local hash normalizer stringified `score_components` keys, then passed after replacing it with shared `stable_current_payload_hash()` and deleting the local normalizer. |
| AC159 — Runtime package imports avoid scheduler side effects. | ✅ | `uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q` failed RED during collection when package-root `WorkerScheduler` re-export triggered `worker_manifest` validation before `CexOiRadarBoardWorker` was fully importable, then passed after removing the scheduler re-export from `parallax.app.runtime.__init__`. |
| AC160 — CEX detail hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys -q` failed RED when the CEX detail local normalizer stringified `level_bands` keys, then passed after replacing the local normalizer with shared `stable_current_payload_hash()` and updating overfitted migration-golden numeric tests. |
| AC161 — CEX detail source refs reject legacy keys before filtering. | ✅ | `uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q` failed RED when source-ref metadata filtering stringified a non-string key, then passed after validating source-ref keys before filtering. |
| AC162 — Token profile current hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys -q` failed RED when the profile-current local hash normalizer accepted a non-string `source_payload_json` key, then passed after validating JSON payload blocks before sanitation and replacing the local normalizer with `stable_current_payload_hash()`. |
| AC163 — News source-quality hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys -q` failed RED when the News local hash normalizer accepted a non-string `diagnostics_json` key, then passed after replacing the local normalizer with `stable_current_payload_hash()` and strict `Jsonb` unwrapping. |
| AC164 — News page-row hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write -q` failed RED when page-row hashing bypassed shared current payload validation and reached the insert path, then passed after restoring `stable_current_payload_hash()` for page-row hashes. |
| AC165 — Narrative admission hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys -q` failed RED when the Narrative local hash normalizer accepted a non-string admission payload key, then passed after replacing the local normalizer with `stable_current_payload_hash()` and strict `Jsonb` unwrapping. |
| AC166 — Narrative admission hash unwraps only real Jsonb adapters. | ✅ | `uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values -q` failed RED when generic `obj` attribute unwrapping accepted a Jsonb-like object, then passed after restricting adapter unwrapping to real `Jsonb` instances. |
| AC167 — Macro daily brief hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys -q` failed RED when the Macro daily brief local hash normalizer accepted a non-string payload key, then passed after replacing it with `stable_current_payload_hash()` while continuing to exclude `computed_at_ms`. |
| AC168 — Macro view snapshot hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_snapshot_payload_hash_rejects_legacy_feature_keys -q` failed RED when the Macro snapshot local hash normalizer accepted a non-string `features_json` key, then passed after replacing it with `stable_current_payload_hash()` while preserving the explicit snapshot payload field list. |
| AC169 — Macro observation series row hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys -q` failed RED when the Macro series row local hash normalizer accepted a non-string `raw_payload_json` key, then passed after replacing the current series row hash path with `stable_current_payload_hash()`. |
| AC170 — Token Radar stable payload hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers -q` failed RED when Token Radar stable hashing accepted non-string keys and unordered containers, then passed after delegating final hash generation to `stable_current_payload_hash()` and rejecting compatibility-shaped payloads before canonicalization. |
| AC171 — Shared current payload hash stays outside runtime imports. | ✅ | `uv run pytest tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime -q` failed RED when domain repositories imported the shared hash helper from `parallax.app.runtime.current_read_model_publisher`, then passed after moving the pure hash contract to `parallax.platform.current_read_model_payload_hash` and updating domain imports. |
| AC172 — Token Radar dirty queue hashes use shared current payload contract. | ✅ | `uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_dirty_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys -q` failed RED when dirty queue hash helpers accepted non-string keys through local key stringification, then passed after filtering lifecycle fields with strict string-key validation and delegating final hash generation to `stable_dirty_target_payload_hash()`. |
| AC173 — Pulse trigger dirty queue hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_ignores_queue_lifecycle_fields -q` failed RED when Pulse trigger dirty hashing accepted non-string keys and treated scheduling lifecycle fields as payload drift, then passed after filtering lifecycle fields with strict string-key validation and delegating final hash generation to `stable_dirty_target_payload_hash()`. |
| AC174 — Narrative admission dirty queue hash uses shared current payload contract. | ✅ | `uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_ignores_queue_lifecycle_fields -q` failed RED when Narrative dirty hashing accepted non-string keys and treated scheduling lifecycle fields as payload drift, then passed after filtering lifecycle fields with strict string-key validation and delegating final hash generation to `stable_dirty_target_payload_hash()`. |
| AC175 — Asset Market dirty-control-plane hashes use shared dirty payload contract. | ✅ | `uv run pytest tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py -q` failed RED when Asset Market dirty queue hashes accepted compatibility-shaped payload keys, treated queue lifecycle fields as payload drift, and sanitized token-image raw refs before validation; it passed after adding `stable_dirty_target_payload_hash()`, switching Asset Market dirty queues to it, and validating raw refs before DB JSON safety. |
| AC176 — Token Capture Tier dirty rank-set fingerprint uses shared current payload contract. | ✅ | `uv run pytest tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers -q` failed RED when rank-set fingerprinting emitted bare hex hashes, stringified nested factor-snapshot keys, and accepted unordered containers; it passed after replacing local JSON/sha256 fingerprinting with `stable_current_payload_hash()` and deleting `_json_ready()`. |
| AC177 — Macro projection dirty-control-plane hash uses shared dirty payload contract. | ✅ | `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_target_coalesces_current_target tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes -q` failed RED when Macro dirty target hashes emitted bare hex hashes and accepted compatibility-shaped nested keys, then passed after delegating current and concept dirty hash generation to `stable_dirty_target_payload_hash()`. |
| AC178 — Agent execution docs name live read-only tool contract. | ✅ | `uv run pytest tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_doc_names_current_read_tool_contract -q` failed RED when `docs/AGENT_EXECUTION.md` still documented stale `AgentReadTool`, then passed after updating the docs to name the live `ReadOnlySqlAgentTool` source contract. |
| AC179 — Active SDD current paths exclude removed files. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_missing_current_file_and_touch_paths tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_removed_file_records_outside_current_touch_surface tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_current_glob_touch_paths_when_they_match -q` failed RED when active task `File(s)`/`Touch set` paths could advertise missing files and matching glob paths were treated as missing, then passed after adding current path/glob validation, optional `Removed file(s)`, and moving deleted Task61/Task115 paths out of current touch scope. |
| AC180 — SDD lifecycle gates have first-class CLI checks. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_individual_gates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q` failed RED when no per-gate CLI existed, then passed after adding `scripts/check_sdd_gate.py`, documenting `clarify/checklist/analyze/implement` commands, and binding Analyze failures to gate result cells rather than historical RED/GREEN prose. |
| AC181 — Tasks do not duplicate final verification evidence. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface -q` failed RED when task artifacts and the tasks template still allowed `## Final verification`, then passed after adding `tasks-final-verification-duplicated` and removing the duplicate section. |
| AC182 — All active SDD gates run in `check-all`. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_all_active_features tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_any_failed_active_feature -q` failed RED when `check-all` did not call the gate checker and the CLI rejected `--all-active`, then passed after adding the all-active sweep and Makefile gate. |
| AC183 — Implement gate forwards delegated task drift. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift -q` failed RED when `--gate implement` passed despite missing subagent handoff/report artifacts, then passed after forwarding all `task-*` validator issues through the implement gate. |
| AC184 — Gate evidence rejects header-only tables. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_header_only_gate_tables -q` failed RED when `clarify` passed on a header-only table, then passed after `_has_table_evidence()` skipped table headers and required a non-placeholder body row. |
| AC185 — Gate evidence shares validator placeholder semantics. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_placeholder_gate_rows -q` failed RED when `<pending>`/`YYYY-MM-DD` placeholder rows satisfied `clarify`, then passed after gate evidence parsing reused `is_placeholder_table_cell()` from the full SDD validator. |
| AC186 — Implement gate covers tasks gate compliance. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance -q` failed RED when `--gate implement` passed despite missing `tasks.md` `## Gate Compliance`, then passed after forwarding tasks artifact gate issues. |
| AC187 — Analyze gate result statuses are bounded. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unbounded_analyze_status tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q` failed RED when `Warn:` passed as an Analyze result, then passed after requiring `Pass:` or `Blocked:`. |
| AC188 — SDD sections require Markdown heading lines. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_must_be_markdown_heading_lines tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_requires_markdown_heading_lines -q` failed RED when backticked `## Clarifications` prose satisfied section detection, then passed after line-level heading parsing was shared by validator and gate CLI. |
| AC189 — SDD section parser ignores fenced headings. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_fenced_heading_tokens -q` failed RED when fenced `## Clarifications` tokens satisfied section detection, then passed after section parsing ignored fenced blocks. |
| AC190 — SDD fenced parser covers tilde fences. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_tilde_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens -q` failed RED when `~~~` fenced headings passed the gate and triggered citation noise, then passed after fence parsing covered both Markdown fence forms. |
| AC191 — Gate evidence rejects single-cell rows. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_single_cell_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_single_cell_gate_rows -q` failed RED when a one-cell body row satisfied gate evidence, then passed after validator and gate CLI shared a multi-cell evidence-row predicate. |
| AC192 — Gate evidence tables require separators. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_tables_without_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows -q` failed RED when separator-less pipe rows satisfied gate evidence, then passed after validator and gate CLI shared separator-aware table-body parsing. |
| AC193 — Gate evidence body rows follow separators. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_rows_before_separator tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_rows_before_separator -q` failed RED when pre-separator body rows satisfied gate evidence, then passed after table parsing required the second pipe row to be the separator. |
| AC194 — Gate evidence separators require hyphens. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_empty_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_empty_separator_rows -q` failed RED when an empty separator row satisfied gate evidence, then passed after separator cells required hyphens. |
| AC195 — Gate evidence table rows share arity. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_separator_arity_mismatch tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_row_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_separator_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_row_arity_mismatch -q` failed RED when separator/body rows with mismatched column counts satisfied gate evidence, then passed after table parsing required header/separator/body arity alignment. |
| AC196 — Gate evidence tables are contiguous blocks. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_non_contiguous_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_contiguous_body_rows -q` failed RED when parser joined pipe rows across prose, then passed after table parsing evaluated only contiguous pipe-row blocks. |
| AC197 — Gate evidence headers are canonical. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_wrong_clarification_header tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_wrong_clarification_header -q` failed RED when a generic but valid table header satisfied Clarifications evidence, then passed after gate evidence required canonical section headers. |
| AC198 — Analyze results use canonical gate rows. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_ignores_non_canonical_tables tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables -q` failed RED when non-canonical context tables inside Analyze Gate triggered result-status failures, then passed after Analyze result validation used canonical gate rows only. |
| AC199 — Analyze invalid-result semantics are shared. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check -q` failed RED when the gate CLI skipped an invalid `Warn:` result because the check column was `<pending>`, then passed after the CLI reused the full validator's Analyze result helper. |
| AC200 — Gate evidence rejects repeated separators. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_separator_rows -q` failed RED when a repeated separator row was skipped before accepting later evidence, then passed after repeated separators invalidated the table block. |
| AC201 — Gate evidence rejects repeated headers. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_header_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_header_rows -q` failed RED when a copied header row in the body satisfied evidence, then passed after repeated header rows invalidated the table block. |
| AC202 — Gate evidence rows must close pipes. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_unclosed_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unclosed_table_rows -q` failed RED when an unclosed pipe row satisfied evidence, then passed after table parsing required rows to start and end with `|`. |
| AC203 — Gate evidence rows use single boundary pipes. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_doubled_boundary_pipes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_doubled_boundary_pipes -q` failed RED when doubled boundary pipes were stripped into canonical-looking cells, then passed after table parsing required single boundary pipes. |
| AC204 — Gate evidence tables are top-level. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_indented_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_indented_table_rows -q` failed RED when indented table rows satisfied evidence, then passed after table parsing preserved leading whitespace. |
| AC205 — Clarification approvals use canonical dates. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_clarification_gate_evidence_rejects_non_canonical_approval_dates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates -q` failed RED when `20260609` satisfied Clarifications evidence, then passed after shared gate evidence validation required canonical `YYYY-MM-DD` approval dates. |
| AC206 — Artifact metadata dates are canonical. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_metadata_dates_require_canonical_real_dates -q` failed RED with only `feature-slug-invalid`, then passed after artifact metadata validation emitted `metadata-date-invalid` for compact or impossible date values. |
| AC207 — Gate Compliance rows are canonical. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_requires_all_canonical_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance -q` failed RED when partial Gate Compliance rows satisfied implementation readiness, then passed after the shared evidence helper required all five canonical gate rows. |
| AC208 — Analyze status rows include evidence. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_status_without_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_analyze_status_without_evidence -q` failed RED when `Pass:` without evidence satisfied analysis readiness, then passed after the shared Analyze result predicate required non-placeholder evidence after the status prefix. |
| AC209 — Gate Compliance rows are exact. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_duplicate_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_duplicate_task_gate_compliance -q` failed RED when duplicate `Clarify` rows satisfied implementation readiness, then passed after Gate Compliance evidence required the exact canonical lifecycle sequence. |
| AC210 — Gate Compliance is a single table block. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_split_table_blocks tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_split_task_gate_compliance -q` failed RED when split Gate Compliance table blocks were stitched into a false pass, then passed after Gate Compliance required one canonical table block. |
| AC211 — Verify gate is first-class. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_missing_check_all_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_spec_compliance tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_spec_compliance_rows -q` failed RED when the CLI rejected `--gate verify` and Verified records accepted pending Spec compliance rows, then passed after verify became a first-class final-evidence gate. |
| AC212 — Spec compliance rows are required. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_empty_spec_compliance -q` failed RED when empty Spec compliance tables satisfied final verification, then passed after final evidence required a canonical Spec compliance row. |
| AC213 — Spec compliance covers every AC. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_partial_spec_compliance -q` failed RED when final verification covered only AC1 while `spec.md` declared AC2, then passed after Spec compliance rows had to match spec acceptance criteria. |
| AC214 — Coverage rows must pass. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_passing_coverage_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_coverage tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q` failed RED when Pending coverage rows satisfied final verification, then passed after Coverage required canonical complete rows. |
| AC215 — E2E golden path must pass. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q` failed RED when unchecked or not-applicable E2E rows satisfied final verification, then passed after all required E2E runtime signals had to be checked. |
| AC216 — Skipped-test count must be numeric. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_numeric_skipped_test_count tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_skipped_count -q` failed RED when `Pending` skipped-count evidence satisfied final verification, then passed after final evidence required a numeric skipped-test count. |
| AC217 — Skipped-test count is section-local. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_count_inside_skipped_tests_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_skipped_count_outside_skipped_section -q` failed RED when stale `Other commands run` skipped-count output satisfied final verification, then passed after skipped-test evidence was scoped to `## Skipped tests`. |
| AC218 — Skipped-test explanation table is canonical. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_canonical_skipped_tests_table tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_freeform_skipped_table -q` failed RED when freeform pipe rows satisfied skipped-test explanations, then passed after skipped-test explanations reused the canonical Markdown table parser. |
| AC219 — Coverage cells are concrete. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_coverage_values tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_coverage_value -q` failed RED when Coverage `value` stayed `Pending` while `status` was `Pass`, then passed after every canonical Coverage cell had to be non-placeholder. |
| AC220 — Spec compliance evidence is concrete. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence -q` failed RED when Spec compliance `Evidence` stayed `Pending.` while `Status` was `Pass`, then passed after completed rows required non-placeholder evidence and sentence-punctuated placeholders were normalized. |
| AC221 — Spec compliance evidence is command-shaped. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_command_shaped_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_prose_only_spec_compliance_evidence -q` failed RED when prose-only Spec compliance evidence satisfied final verification, then passed after completed rows had to cite command-shaped evidence. |
| AC222 — E2E evidence ignores fenced examples. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_fenced_e2e_golden_path -q` failed RED when fenced checklist examples satisfied final verification, then passed after E2E evidence stripped fenced blocks. |
| AC223 — make check-all evidence uses its own exit code. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_make_check_all_own_exit_code_zero tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_failed_check_all_before_helper_success -q` failed RED when later helper success could satisfy failed check-all evidence, then passed after command transcript segmentation. |
| AC224 — Task Board exposes repair pressure. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` failed RED before the generated Task Board exposed `Kill/defer criteria` and `Eval/repair signal`, then passed after index generation rendered those columns. |
| AC225 — Completion gate has a Make target. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate -q` failed RED before `check-sdd-completion` existed, then passed after the Make target and docs were added. |
| AC226 — Makefile pytest targets reject empty collections. | ✅ | `uv run pytest tests/architecture/test_harness_structure.py::test_makefile_pytest_targets_do_not_accept_empty_collections -q` failed RED while Makefile pytest targets translated pytest exit code 5 into success, then passed after those compatibility shims were removed. |
| AC227 — Golden corpus has a dedicated marker. | ✅ | `python -m pytest tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker -q` failed RED while golden corpus tests used the e2e marker, then passed after `test-golden` and `tests/golden/` moved to `golden`; collect-only checks proved `-m golden` selects the corpus and `-m e2e` does not. |
| AC228 — Final runtime lanes fail closed. | ✅ | `python -m pytest tests/architecture/test_harness_structure.py::test_final_runtime_lanes_do_not_expose_skip_env_switches -q` failed RED while E2E/golden fixtures and the verification template exposed skip switches, then passed after those branches and template instructions were removed. |
| AC229 — Contract lane has one Make entrypoint. | ✅ | `python -m pytest tests/architecture/test_harness_structure.py::test_contract_lane_has_no_duplicate_make_alias -q` failed RED while `contract-check` remained in `.PHONY`, then passed after the duplicate Make target was removed. |
| AC230 — Architecture harness tests fail closed. | ✅ | `python -m pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_do_not_skip_contracts -q` failed RED on worker runtime architecture skips and `python -m pytest tests/architecture/test_test_lane_contracts.py::test_pytest_empty_parameter_sets_fail_at_collect -q` failed RED while pytest could skip empty parametrized sets, then `uv run pytest tests/architecture/test_test_lane_contracts.py tests/architecture/test_worker_runtime_contracts.py -q` passed after skip branches, the empty stubbed-worker allowlist, and the empty runtime-owner parameter source were removed. |
| AC231 — SDD validator has no report-only soft mode. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_validator_cli_fails_on_issues_without_check_flag -q` failed RED while invalid SDD roots returned 0 without `--check`, then passed after the CLI returned 1 for any emitted issue. |
| AC232 — Coverage keeps empty source files visible. | ✅ | `python -m pytest tests/architecture/test_test_lane_contracts.py::test_coverage_report_does_not_hide_empty_source_files -q` failed RED while `coverage.report.skip_empty` was true, then passed after coverage config set it to false. |
| AC233 — SDD task selectors are numeric only. | ✅ | `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_title_substring_selectors -q` failed RED while `--task "Dispatch packet"` selected Task 1, then passed after context packet, dispatch, and subagent report CLIs rejected non-numeric task selectors. |
| AC234 — Final runtime evidence rejects golden skip switches. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_golden_skip_switch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_golden_skip_switch -q` passed after separate RED runs proved `SKIP_GOLDEN=1` passed both the pure validator and verify gate. |
| AC235 — Final verification commands are single-source evidence. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_command tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_command -q` passed after separate RED runs proved helper commands in `Verification commands` passed both the pure validator and verify gate. |
| AC236 — Final command scan includes unfenced shell lines. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_unfenced_extra_verification_command tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_unfenced_extra_verification_command -q` passed after separate RED runs proved unfenced helper commands in `Verification commands` passed both the pure validator and verify gate. |
| AC237 — Final verification command sequence is exact. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_unfenced_make_check_all tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_unfenced_make_check_all -q` passed after separate RED runs proved duplicate unfenced `make check-all` command sources passed both the pure validator and verify gate. |
| AC238 — Final make-check-all transcript has one exit code. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_multiple_check_all_exit_codes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_multiple_check_all_exit_codes -q` passed after separate RED runs proved a later `exit code: 0` in the same `make check-all` segment could overwrite an earlier failed exit code. |
| AC239 — Final verification commands have one transcript block. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_output_block tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_output_block -q` passed after separate RED runs proved extra fenced output blocks without command lines passed both the pure validator and verify gate. |
| AC240 — Required SDD sections are unique. | ✅ | `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_verification_commands_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_verification_commands_section -q` passed after separate RED runs proved duplicate `## Verification commands` headings passed both the pure validator and verify gate. |

Deviations from spec:

- None.

Deviations from plan:

- `make check-all` was not completed. User requested on 2026-06-09: "不跑集成测试了 先合并到main吧".

## Verification commands

The only command whose output may be pasted as completion evidence is `make check-all`. Paste the full output below,
including the exit code line, before moving this feature to `completed`.

```text
$ make check-all
SDD artifact validation passed.
make check passed, including frontend typecheck/lint/architecture/format,
Python unit/architecture/contract tests, and compileall.
Stopped during tests/integration per user instruction before integration/e2e/golden/coverage completed.
exit code: 2
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line   | Not run | >= 80% | ❌ |
| branch | Not run | >= 70% | ❌ |

## Skipped tests

Number of skipped tests in the completed `make check` segment: 3

| count | reason | acceptable? |
|-------|--------|-------------|
| 1 | PostgreSQL test database unavailable in non-integration check segment. | Yes for `make check`; not final `check-all` evidence. |
| 1 | Empty architecture parameter set for worker runtime table allowlist. | Yes; existing architecture skip. |
| 1 | Opt-in provider drift check requires `GMGN_PROVIDER_DRIFT=1`. | Yes; live drift diagnostic is opt-in. |

## E2E golden path

Confirm each runtime signal from the spec was asserted:

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

Not run because integration/e2e/golden gates were intentionally skipped before merging to `main`.

## Other commands run

```text
$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules -q
F                                                                        [100%]
AssertionError: 违规:
- ('src/parallax/domains/token_intel/interfaces.py', 'parallax.domains.token_intel.runtime.token_resolution_refresh')
原因: Domain interfaces are cross-domain contracts; importing runtime modules leaks orchestration into callers.
exit code: 1

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules -q
1 passed in 0.22s
exit code: 0

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules tests/architecture/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces -q
2 passed in 0.44s
exit code: 0

$ uv run pytest tests/unit/test_token_resolution_refresh.py tests/unit/test_resolution_refresh_worker.py -q
10 passed in 0.22s
exit code: 0

$ uv run ruff check src/parallax/domains/token_intel/interfaces.py src/parallax/domains/token_intel/services/token_resolution_refresh.py src/parallax/domains/token_intel/runtime/token_intent_rebuild.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/test_token_resolution_refresh.py tests/architecture/test_src_domain_architecture.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources -q
F                                                                        [100%]
AssertionError: open TECH_DEBT duplicate-symbol claims are stale: ['TOKEN_RADAR_RESOLVER_POLICY_VERSION is absent from src/parallax/domains/asset_market/repositories/registry_repository.py']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals -q
F                                                                        [100%]
AssertionError: assert 'Message type literal' in '<!-- AUTO-GENERATED by scripts/regen_ws_protocol.py — do not hand-edit -->...'
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot -q
F                                                                        [100%]
AssertionError: assert 'scripts/regen_ws_protocol.py --check' in ' ## the only command that may produce verification-artefact evidence (gates 1+2+3)...'
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/regen_ws_protocol.py --check
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot -q
F                                                                        [100%]
AssertionError: assert 'scripts/regen_score_versions.py --check' in ' ## the only command that may produce verification-artefact evidence (gates 1+2+3)...'
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/regen_score_versions.py --check
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots -q
F                                                                        [100%]
AssertionError: assert 'scripts/regen_pulse_agent_desk_decisions.py --check' in ' ## the only command that may produce verification-artefact evidence (gates 1+2+3)...'
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/regen_pulse_agent_desk_decisions.py --check
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q
F                                                                        [100%]
AssertionError: assert 'Required Reading Evidence' in '# Subagent Handoff Template...'
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift -q
4 passed in 0.11s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines -q
F                                                                        [100%]
AssertionError: assert 'spec-background-uncited' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines -q
1 passed in 0.04s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/unit/test_query_contract.py tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness -q
10 passed in 0.18s

$ uv run pytest tests/architecture -m architecture -q
365 passed, 1 skipped in 13.00s

$ uv run pytest tests/unit/domains/macro_intel tests/unit/test_query_contract.py -q
154 passed in 0.92s

$ make check
2630 passed, 3 skipped in 24.03s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_filled_coordination_fields -q
5 passed in 0.09s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
12 passed in 0.15s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
367 passed, 1 skipped in 32.73s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
16 passed in 0.11s
exit code: 0

$ uv run python scripts/build_agent_context_packet.py --feature 2026-06-09-executable-harness-hard-cut --task 7 --mode read-only
# Context Packet - 2026-06-09-executable-harness-hard-cut / Task 7
...
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q
2 passed in 0.07s
exit code: 0

$ uv run python scripts/dispatch_sdd_task.py --feature 2026-06-09-executable-harness-hard-cut --task 5 --mode read-only
# Subagent Handoff - 2026-06-09-executable-harness-hard-cut / Task 5
...
exit code: 0

$ uv run python scripts/dispatch_sdd_task.py --feature 2026-06-09-executable-harness-hard-cut --task 8 --mode read-only
error: task is already complete and cannot be dispatched: Task 8 — SDD dry-run dispatch CLI
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
3 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
26 passed in 0.59s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/dispatch_sdd_task.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
381 passed, 1 skipped in 103.08s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q
5 passed in 0.17s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
30 passed in 0.37s
exit code: 0

$ uv run ruff check scripts/validate_subagent_report.py scripts/dispatch_sdd_task.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
385 passed, 1 skipped in 99.84s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
4 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
32 passed in 0.33s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
387 passed, 1 skipped in 104.76s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q
3 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q
14 passed in 0.12s
exit code: 0

$ uv run pytest tests/architecture/test_test_lane_contracts.py -q
5 passed in 0.23s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q
10 passed in 0.16s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
1 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
2 passed in 0.05s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
35 passed in 0.36s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q
3 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q
F                                                                        [100%]
AssertionError: assert 'artifact-status-mismatch' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
38 passed in 0.53s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q
F                                                                        [100%]
AssertionError: assert 'superseded-missing-successor' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
39 passed in 0.44s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q
F                                                                        [100%]
AssertionError: assert 'unexpected-artifact' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q
1 passed in 0.02s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
error: unexpected-artifact: docs/sdd/features/completed/2026-06-09-macro-intel-redesign/macro-actual-assets-desktop.png: feature directories must contain only spec.md, plan.md, tasks.md, verification.md
...
error: unexpected-artifact: docs/sdd/features/completed/2026-06-09-macro-intel-redesign/timsun-assets-comparison.txt: feature directories must contain only spec.md, plan.md, tasks.md, verification.md
exit code: 1

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
40 passed in 0.48s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q
F                                                                        [100%]
AssertionError: assert 'task-invalid-dependencies' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
error: task-invalid-dependencies: docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/tasks.md: Task 6 — Agent factory and eval/repair loop gate complete before dependencies: Task 5
exit code: 1

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
41 passed in 0.40s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q
F                                                                        [100%]
AssertionError: assert 'task-complete-missing-verification-evidence' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q
1 passed in 0.03s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
42 passed in 0.37s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q
F                                                                        [100%]
AssertionError: assert 'missing-approval-metadata' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q
1 passed in 0.02s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
error: missing-approval-metadata: docs/sdd/features/completed/2026-06-09-macro-intel-redesign/plan.md: missing metadata fields: approved by, approved at
...
error: missing-approval-metadata: docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/verification.md: missing metadata fields: worktree, approved by, approved at
exit code: 1

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
43 passed in 0.43s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q
F                                                                        [100%]
AssertionError: assert 'task-missing-coordination-fields' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q
1 passed in 0.02s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
error: task-missing-coordination-fields: docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/tasks.md: Superseded tasks.md must retain structured Task sections
exit code: 1

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
44 passed in 0.43s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q
F                                                                        [100%]
AssertionError: assert 'superseded-successor-mismatch' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q
1 passed in 0.02s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
45 passed in 0.43s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q
F                                                                        [100%]
AssertionError: assert 'task-complete-missing-review-evidence' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q
1 passed in 0.02s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
46 passed in 0.68s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q
F                                                                        [100%]
AssertionError: assert 'task-invalid-numbering' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q
1 passed in 0.03s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
47 passed in 0.64s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q
F                                                                        [100%]
AssertionError: assert 'artifact-owning-link-mismatch' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q
1 passed in 0.03s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
48 passed in 0.44s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q
F                                                                        [100%]
AssertionError: assert 'acceptance-command-mismatch' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q
1 passed in 0.03s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
49 passed in 0.40s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q
F                                                                        [100%]
AssertionError: assert 'acceptance-numbering-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q
1 passed in 0.21s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
50 passed in 1.39s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q
F                                                                        [100%]
AssertionError: assert 'acceptance-command-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q
F                                                                        [100%]
AssertionError: assert 'acceptance-command-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q
F                                                                        [100%]
AssertionError: assert 'feature-slug-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q
F                                                                        [100%]
AssertionError: assert 'gate-evidence-missing' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q
1 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q
F                                                                        [100%]
AssertionError: assert 'acceptance-criterion-format-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q
F                                                                        [100%]
AssertionError: assert 'verified-missing-spec-compliance-evidence' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q
F                                                                        [100%]
AssertionError: assert 'worktree-metadata-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q
F                                                                        [100%]
AssertionError: assert 'spec-background-uncited' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q
F                                                                        [100%]
AssertionError: assert 'plan-preflight-metadata-mismatch' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q
F                                                                        [100%]
AssertionError: assert 'task-invalid-subagent-handoff-artifact' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q
F                                                                        [100%]
AssertionError: assert 'task-invalid-subagent-report-artifact' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q
1 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q
F                                                                        [100%]
assert []
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q
F                                                                        [100%]
AssertionError: assert 'plan-analyze-gate-invalid' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence -q
F                                                                        [100%]
AssertionError: assert 'task-complete-missing-failing-test-evidence' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot -q
F                                                                        [100%]
AssertionError: assert 'scripts/regen_cli_help.py --check' in ' ## the only command that may produce verification-artefact evidence (gates 1+2+3)\n\t@uv run python scripts/validate_sdd_artifacts.py --check\n\t@uv run python scripts/regen_sdd_work_index.py --check\n\t@$(MAKE) check\n\t@$(MAKE) test-integration\n\t@$(MAKE) test-e2e\n\t@$(MAKE) test-golden\n\t@$(MAKE) coverage'
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot -q
1 passed in 0.09s
exit code: 0

$ uv run python scripts/regen_cli_help.py --check
exit code: 0

$ uv run pytest tests/architecture/test_public_contracts_doc_alignment.py -q
FFFF                                                                     [100%]
FAILED tests/architecture/test_public_contracts_doc_alignment.py::test_contracts_worker_keys_match_manifest_registry
FAILED tests/architecture/test_public_contracts_doc_alignment.py::test_contracts_agent_runtime_lanes_match_settings_defaults
FAILED tests/architecture/test_public_contracts_doc_alignment.py::test_contracts_websocket_payloads_match_current_surface
FAILED tests/architecture/test_public_contracts_doc_alignment.py::test_contracts_news_item_detail_route_matches_fastapi_route
exit code: 1

$ uv run pytest tests/architecture/test_public_contracts_doc_alignment.py -q
4 passed in 0.11s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths -q
F                                                                        [100%]
AssertionError: generated README source path does not exist: src/parallax/api/ws.py
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination -q
F                                                                        [100%]
AssertionError: assert 'active-touch-conflict' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination -q
1 passed in 0.04s
exit code: 0

$ cd web && npm run test -- tests/architecture/frontendDocContract.test.ts
FAIL tests/architecture/frontendDocContract.test.ts
AssertionError: expected docs/FRONTEND.md to contain `macro.css`
AssertionError: expected docs/FRONTEND.md to contain `@features/<name>/shell`
exit code: 1

$ cd web && npm run test -- tests/architecture/frontendDocContract.test.ts
Test Files  1 passed (1)
Tests  4 passed (4)
exit code: 0

$ cd web && npm run test -- tests/architecture/featureBoundaries.test.ts
FAIL tests/architecture/featureBoundaries.test.ts
AssertionError: expected [ 'cockpit', 'live', ...(6) ] to deeply equal [ 'cockpit', 'live', 'macro', ...(8) ]
Missing: macro, news, ops, token-case; stale: token-target
exit code: 1

$ cd web && npm run test -- tests/architecture/featureBoundaries.test.ts
Test Files  1 passed (1)
Tests  2 passed (2)
exit code: 0

$ cd web && npm run test -- tests/architecture/frontendDataOwnership.test.ts
FAIL tests/architecture/frontendDataOwnership.test.ts
AssertionError: expected docs/FRONTEND.md to contain `frontendDataOwnership.test.ts`
exit code: 1

$ cd web && npm run test -- tests/architecture/frontendDataOwnership.test.ts
Test Files  1 passed (1)
Tests  2 passed (2)
exit code: 0

$ cd web && npm run test:architecture -- frontendDataOwnership.test.ts
Test Files  13 passed (13)
Tests  72 passed (72)
exit code: 0

$ cd web && npx prettier --check tests/architecture/frontendDataOwnership.test.ts && npx eslint tests/architecture/frontendDataOwnership.test.ts --max-warnings=0
All matched files use Prettier code style!
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness -q
F                                                                        [100%]
AssertionError: assert '`macro.css`' in agents
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_router_shared_blocks_match_and_reference_agent_playbook -q
1 passed in 0.02s
exit code: 0

$ cd web && npm run test -- tests/architecture/frontendDocContract.test.ts
FAIL tests/architecture/frontendDocContract.test.ts
AssertionError: expected frontend verification skill to contain `frontendDataOwnership.test.ts`
exit code: 1

$ cd web && npm run test -- tests/architecture/frontendDocContract.test.ts
Test Files  1 passed (1)
Tests  5 passed (5)
exit code: 0

$ cd web && npm run test:architecture -- frontendDocContract.test.ts
Test Files  13 passed (13)
Tests  73 passed (73)
exit code: 0

$ cd web && npx prettier --check tests/architecture/frontendDocContract.test.ts && npx eslint tests/architecture/frontendDocContract.test.ts --max-warnings=0
All matched files use Prettier code style!
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing -q
F                                                                        [100%]
AssertionError: docs/ARCHITECTURE.md test references must be path-qualified: test_legacy_asset_repository_is_not_imported
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc -q
F                                                                        [100%]
AssertionError: assert linked == expected
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy -q
F                                                                        [100%]
AssertionError: tests/architecture/test_public_contracts_doc_alignment.py needs a harness taxonomy entry
exit code: 1

$ uv run pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
F                                                                        [100%]
AssertionError: open TECH_DEBT references missing files: ['tests/test_harness_structure.py', 'tests/integration/test_price_observation_repository.py', 'tests/integration/test_enrichment_worker.py::test_enrichment_worker_times_out_hung_llm_job', 'tests/integration/test_enrichment_repository.py::test_complete_social_event_job_records_agents_sdk_run_audit']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
F                                                                        [100%]
AssertionError: open TECH_DEBT references missing test functions: ['tests/integration/test_resolution_refresh_worker.py::test_resolution_refresh_worker_resolves_recent_symbol_and_rebuilds_radar', 'tests/integration/test_resolution_refresh_worker.py::test_dex_symbol_discovery_demotes_old_unretained_search_assets', 'tests/integration/test_cli.py::CliTests::test_recent_search_asset_flow_harness_and_alerts_use_postgres_runtime_store']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
F                                                                        [100%]
AssertionError: open TECH_DEBT test references must include their source file: ['::test_cli_ops_sync_gmgn_directory_emits_error_on_directory_failure']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
F                                                                        [100%]
AssertionError: open TECH_DEBT source/test references must be repo-root paths: ['regen_ws_protocol.py', 'app/surfaces/api/ws.py', 'ws-protocol.md', 'domains/token_intel/_constants.py', 'domains/asset_market/repositories/registry_repository.py', 'domains/token_intel/interfaces.py', 'domains/token_intel/interfaces.py', 'domains/evidence/types/entity.py', 'services/entity_extractor.py', 'entity_extractor.py', 'config.yaml']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
F                                                                        [100%]
AssertionError: open TECH_DEBT source/test references must be repo-root paths: ['docs/generated/ws-protocol.md']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_rule_ownership tests/architecture/test_harness_structure.py::test_routers_have_no_governance_phrases -q
2 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers -q
F                                                                        [100%]
AssertionError: 违规:
- ('src/parallax/domains/evidence/types/entity.py', 'parallax.domains.evidence.services.entity_extractor')
原因: Type modules are leaf value objects; importing services, repositories, queries, read models, or runtime recreates hidden compatibility shims.
exit code: 1

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers -q
1 passed in 0.12s
exit code: 0

$ uv run pytest tests/unit/test_entity_extractor.py -q
7 passed in 0.16s
exit code: 0

$ uv run ruff check src/parallax/domains/evidence/types/entity.py src/parallax/domains/evidence/services/entity_extractor.py src/parallax/domains/evidence/interfaces.py src/parallax/app/surfaces/api/ws.py tests/architecture/test_src_domain_architecture.py tests/unit/test_entity_extractor.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_test_lane_contracts.py -q
5 passed in 0.13s
exit code: 0

$ uv run ruff check tests/architecture/test_test_lane_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py -q
16 passed in 0.19s
exit code: 0

$ uv run ruff check tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py -q
22 passed in 0.60s
exit code: 0

$ uv run ruff check tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
64 passed in 1.51s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_completion_gates.py -q
15 passed in 0.30s
exit code: 0

$ uv run python scripts/regen_cli_help.py --check
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run ruff check scripts/regen_cli_help.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_worker_runtime_constraint_classification_lives_on_manifest -q
F                                                                        [100%]
AttributeError: 'WorkerManifest' object has no attribute 'runtime_constraint'
exit code: 1

$ uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_health_adapter_registry_covers_manifest_queue_tables_exactly_once -q
2 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources -q
F                                                                        [100%]
AssertionError: assert ['tests/architecture/test_worker_inventory_contract.py imports tests.architecture.test_worker_runtime_contracts'] == []
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources -q
1 passed in 0.08s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
5 passed in 0.19s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract -q
F                                                                        [100%]
AttributeError: 'WorkerManifest' object has no attribute 'owned_tables'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
6 passed in 0.16s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping -q
F                                                                        [100%]
AttributeError: module 'parallax.app.runtime.worker_manifest' has no attribute 'read_model_writer_by_table'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
7 passed in 0.16s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
8 passed in 0.15s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
9 passed in 0.15s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
10 passed in 0.16s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
2 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
2 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables -q
F                                                                        [100%]
AssertionError: Regex pattern did not match.
Actual message: "current read model tables missing stable identities: {'market_tick_current_projection': ['market_tick_current']}"
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities -q
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules -q
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names -q
1 passed in 0.39s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_domain_directories -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_domain_directories -q
1 passed in 0.37s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_raw_classification_values -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_raw_classification_values -q
1 passed in 0.37s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_boolean_provider_io_flags -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_boolean_provider_io_flags -q
1 passed in 0.36s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_contract_fields -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_contract_fields -q
1 passed in 0.37s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_contract_entries -q
F                                                                        [100%]
E   AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_contract_entries -q
1 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_columns -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_columns -q
1 passed in 0.48s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_entries -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_entries -q
1 passed in 1.00s
exit code: 0

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_worker_manifest_imports_in_clean_process_without_importlib_util_side_effect -q
F                                                                        [100%]
E   AttributeError: module 'importlib' has no attribute 'util'
exit code: 1

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_worker_manifest_imports_in_clean_process_without_importlib_util_side_effect -q
1 passed in 0.53s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_malformed_read_model_identity_entries -q
F                                                                        [100%]
E   ValueError: too many values to unpack (expected 2)
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_malformed_read_model_identity_entries -q
1 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_repo_root_has_no_loose_visual_artifacts -q
F                                                                        [100%]
AssertionError: visual verification artifacts must live under an owned artifact directory, not repo root: ['news-provider-rating-1366.png', 'parallax-macro-assets-after-1366.png', 'parallax-macro-assets-after-390.png', 'parallax-macro-assets-before-1366.png', 'parallax-macro-assets-before-390.png', 'timsun-assets-1366.png']
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_repo_root_has_no_loose_visual_artifacts -q
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_queue_depth_tables -q
F                                                                        [100%]
E   AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_queue_depth_tables -q
1 passed in 0.52s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_advisory_lock_keys -q
F                                                                        [100%]
E   AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_advisory_lock_keys -q
1 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_identity_fields -q
FFFF                                                                     [100%]
E   AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_identity_fields -q
4 passed in 0.67s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_tables -q
F                                                                        [100%]
E   AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_tables -q
1 passed in 0.51s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_columns -q
F                                                                        [100%]
E   AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_columns -q
1 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/worker_manifest.py tests/architecture/test_worker_inventory_contract.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.54s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
F                                                                        [100%]
E       AttributeError: 'int' object has no attribute 'strip'
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
1 passed in 0.39s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q
1 passed in 0.57s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
6 passed in 0.67s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.86s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column -q
1 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column -q
1 passed in 0.70s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
7 passed in 0.51s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.64s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns -q
1 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns -q
1 passed in 1.35s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
8 passed in 0.48s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.56s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns -q
1 passed in 0.44s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns -q
1 passed in 0.43s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
9 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.49s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns -q
1 passed in 0.42s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns -q
1 passed in 0.46s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
10 passed in 0.39s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.50s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column -q
1 passed in 0.32s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_payload_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column -q
1 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_payload_columns -q
1 passed in 0.43s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
12 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.53s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_hash_column -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_payload_hash_payload_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_hash_column -q
1 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_payload_hash_payload_columns -q
1 passed in 0.42s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_columns -q
1 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
15 passed in 0.66s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.41s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_identity_payload_hash_column -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'KeyError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_identity_payload_hash_column -q
1 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q
1 passed in 0.42s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
17 passed in 0.50s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
56 passed in 0.59s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_dirty_targets -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_depth -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_dirty_targets -q
1 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_depth -q
1 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_health_tables -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_health_tables -q
1 passed in 0.43s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/worker_manifest.py tests/architecture/test_worker_inventory_contract.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
58 passed in 0.65s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
17 passed in 0.58s
exit code: 0

$ git diff --check
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/worker_manifest.py tests/architecture/test_worker_inventory_contract.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
59 passed in 0.64s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
17 passed in 0.55s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane -q
1 passed in 0.42s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane -q
1 passed in 0.42s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q
1 passed in 0.42s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/worker_manifest.py tests/architecture/test_worker_inventory_contract.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.52s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
17 passed in 0.44s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane -q
2 passed in 0.45s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/worker_manifest.py tests/architecture/test_worker_inventory_contract.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.54s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_identity_column_before_payload_hashing -q
F                                                                        [100%]
E           KeyError: 'target_id'
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_identity_column_before_payload_hashing -q
1 passed in 0.42s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
18 passed in 0.42s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
18 passed in 0.40s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.49s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_row_identities_in_batch -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_row_identities_in_batch -q
1 passed in 0.39s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
19 passed in 0.39s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
19 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.51s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q
F                                                                        [100%]
E           KeyError: 'score'
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q
1 passed in 0.39s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
19 passed in 0.25s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
19 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.53s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_row_columns_before_write_preparation -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_row_columns_before_write_preparation -q
1 passed in 0.35s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
20 passed in 0.30s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
20 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.50s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_null_row_identity_values_before_hashing -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_null_row_identity_values_before_hashing -q
1 passed in 0.37s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
21 passed in 0.26s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
21 passed in 0.39s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.47s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_row_identity_values_before_hashing -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_row_identity_values_before_hashing -q
1 passed in 0.37s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
22 passed in 0.31s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
22 passed in 0.40s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.46s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_identity_columns -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_identity_columns -q
1 passed in 0.30s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
23 passed in 0.31s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
23 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.50s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_rows_before_column_validation -q
F                                                                        [100%]
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'current read model row must be mapping'
E         Actual message: "current read model row has non-string columns: (('target_id', 'asset-1'), ('score', 10))"
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_rows_before_column_validation -q
1 passed in 0.37s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
24 passed in 0.27s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
24 passed in 0.47s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.58s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_existing_hashes_before_hash_lookup -q
F                                                                        [100%]
E           AttributeError: 'list' object has no attribute 'get'
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_existing_hashes_before_hash_lookup -q
1 passed in 0.40s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
25 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
25 passed in 0.44s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.51s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_existing_hash_identity_keys_before_hash_lookup -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_existing_hash_identity_keys_before_hash_lookup -q
1 passed in 0.25s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
26 passed in 0.25s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
26 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.50s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_wrong_arity_existing_hash_identity_keys_before_hash_lookup -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_wrong_arity_existing_hash_identity_keys_before_hash_lookup -q
1 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
27 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
27 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.51s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_existing_hash_values_before_hash_lookup -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_existing_hash_values_before_hash_lookup -q
1 passed in 0.25s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
28 passed in 0.25s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
28 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.51s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_malformed_existing_hash_values_before_hash_lookup -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_malformed_existing_hash_values_before_hash_lookup -q
1 passed in 0.41s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
29 passed in 0.41s
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
29 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
61 passed in 0.52s
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q
FFF                                                                      [100%]
E       TypeError: 'int' object is not iterable
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'current read model rows must be sequence'
E         Actual message: 'current read model row must be mapping: target_id'
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'current read model rows must be sequence'
E         Actual message: 'current read model row must be mapping: l'
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q
...                                                                      [100%]
3 passed in 0.35s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q
...                                                                      [100%]
3 passed in 0.46s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
................................                                         [100%]
32 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.53s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
SIM101 Multiple `isinstance` calls for `rows`, merge into a single call
exit code: 1

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q
...                                                                      [100%]
3 passed in 0.48s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
................................                                         [100%]
32 passed in 0.47s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.55s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads -q
FFF                                                                      [100%]
E       TypeError: 'int' object is not iterable
E       Failed: DID NOT RAISE <class 'ValueError'>
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'current payload hash payload must be mapping'
E         Actual message: 'dictionary update sequence element #0 has length 1; 2 is required'
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads -q
...                                                                      [100%]
3 passed in 0.23s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads -q
...                                                                      [100%]
3 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
...................................                                      [100%]
35 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.52s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys -q
.                                                                        [100%]
1 passed in 0.34s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys -q
.                                                                        [100%]
1 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
....................................                                     [100%]
36 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.55s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys -q
.                                                                        [100%]
1 passed in 0.23s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys -q
.                                                                        [100%]
1 passed in 0.46s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
.....................................                                    [100%]
37 passed in 0.47s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.53s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values -q
.                                                                        [100%]
1 passed in 0.39s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values -q
.                                                                        [100%]
1 passed in 0.51s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
......................................                                   [100%]
38 passed in 0.50s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.60s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers -q
FFFF                                                                     [100%]
E       ValueError: Out of range float values are not JSON compliant: nan
E       ValueError: Out of range float values are not JSON compliant: inf
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers -q
....                                                                     [100%]
4 passed in 0.25s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers -q
....                                                                     [100%]
4 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
..........................................                               [100%]
42 passed in 0.45s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.52s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers -q
FF                                                                       [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers -q
..                                                                       [100%]
2 passed in 0.40s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
............................................                             [100%]
44 passed in 0.40s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers -q
..                                                                       [100%]
2 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
............................................                             [100%]
44 passed in 0.43s
exit code: 0

$ uv run pytest tests/architecture/test_worker_inventory_contract.py -q
.............................................................            [100%]
61 passed in 0.53s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys -q
.                                                                        [100%]
1 passed in 0.47s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py -q
.........                                                                [100%]
9 passed in 0.46s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q
ERROR tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py
E   ValueError: missing worker manifest class names: {'cex_oi_radar_board': 'parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker.CexOiRadarBoardWorker'}
exit code: 2

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q
...........                                                              [100%]
11 passed in 0.04s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys -q
.                                                                        [100%]
1 passed in 0.13s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py -q
.........                                                                [100%]
9 passed in 0.14s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py::test_cex_oi_radar_board_worker_publishes_current_board -q
.                                                                        [100%]
1 passed in 0.06s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q
...........                                                              [100%]
11 passed in 0.06s
exit code: 0

$ uv run pytest tests/unit/test_worker_scheduler.py tests/unit/test_bootstrap_worker_runtime_wiring.py -q
.............................                                            [100%]
29 passed in 4.26s
exit code: 0

$ uv run pytest tests/architecture/test_cex_oi_kappa_contract.py tests/architecture/test_worker_manifest_static_contracts.py tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_runtime_uses_current_board_lifecycle tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_manifest_uses_current_board_lifecycle -q
...............................................                          [100%]
47 passed in 0.56s
exit code: 0

$ uv run ruff check src/parallax/app/runtime/__init__.py src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py src/parallax/app/runtime/current_read_model_publisher.py tests/architecture/test_worker_manifest_static_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys -q
.                                                                        [100%]
1 passed in 0.14s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py -q
...FFF.....                                                              [100%]
E       AssertionError: assert 'sha256:44200...56b00aeb22706' == 'sha256:6284d...fb7ea9badf4cd'
E       AssertionError: assert 'sha256:b3fe5...ed96ecc3569e0' == 'sha256:6284d...fb7ea9badf4cd'
E       AssertionError: assert 'sha256:b3fe5...ed96ecc3569e0' == 'sha256:6284d...fb7ea9badf4cd'
exit code: 1

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py -q
..........                                                               [100%]
10 passed in 0.11s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q
..                                                                       [100%]
2 passed in 0.16s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q
.                                                                        [100%]
1 passed in 0.13s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py -q
...........                                                              [100%]
11 passed in 0.17s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys -q
.                                                                        [100%]
1 passed in 0.19s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q
.                                                                        [100%]
1 passed in 0.15s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py -q
...........                                                              [100%]
11 passed in 0.20s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q
....................                                                     [100%]
20 passed in 0.21s
exit code: 0

$ uv run pytest tests/architecture/test_cex_oi_kappa_contract.py tests/architecture/test_worker_manifest_static_contracts.py tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_runtime_uses_current_board_lifecycle tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_manifest_uses_current_board_lifecycle -q
...............................................                          [100%]
47 passed in 0.91s
exit code: 0

$ uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys -q
.                                                                        [100%]
1 passed in 0.09s
exit code: 0

$ uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/unit/test_token_profile_current_repository.py -q
.....                                                                    [100%]
5 passed in 0.08s
exit code: 0

$ uv run pytest tests/unit/test_token_profile_read_model.py -q
.....                                                                    [100%]
5 passed in 0.26s
exit code: 0

$ uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
...................................                                      [100%]
35 passed in 0.66s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_workers_declare_explicit_table_identities_without_fallback tests/architecture/test_worker_manifest_static_contracts.py::test_dirty_target_workers_declare_claim_tables_and_read_model_identity -q
..                                                                       [100%]
2 passed in 0.48s
exit code: 0

$ uv run pytest tests/architecture/test_worker_runtime_contracts.py::test_token_profile_current_owns_image_source_admission tests/architecture/test_worker_runtime_contracts.py::test_read_model_single_writers -q
...................                                                      [100%]
19 passed in 1.40s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys -q
.                                                                        [100%]
1 passed in 0.17s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write -q
F                                                                        [100%]
KeyError: 'inserted'
exit code: 1

$ uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write -q
.                                                                        [100%]
1 passed in 0.18s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/domains/news_intel/test_news_repository_queries.py -q
..............................                                           [100%]
30 passed in 0.18s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_source_quality_worker_enqueues_page_dirty_when_source_quality_status_changes tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_page_projection_worker_loads_only_claimed_news_item_targets_and_marks_done_with_tokens -q
..                                                                       [100%]
2 passed in 0.36s
exit code: 0

$ uv run pytest tests/architecture/test_projection_worker_idle_cost_contract.py tests/architecture/test_worker_runtime_contracts.py::test_news_page_projection_manifest_uses_row_id_identity tests/architecture/test_worker_runtime_contracts.py::test_worker_manifest_declares_dirty_target_consumers -q
.....                                                                    [100%]
5 passed in 0.71s
exit code: 0

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys -q
.                                                                        [100%]
1 passed in 0.13s
exit code: 0

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values -q
.                                                                        [100%]
1 passed in 0.13s
exit code: 0

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values -q
..                                                                       [100%]
2 passed in 0.12s
exit code: 0

$ uv run pytest tests/unit/domains/narrative_intel -q
......................................                                   [100%]
38 passed in 0.24s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys -q
.                                                                        [100%]
1 passed in 0.09s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_snapshot_payload_hash_rejects_legacy_feature_keys -q
F                                                                        [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_snapshot_payload_hash_rejects_legacy_feature_keys -q
.                                                                        [100%]
1 passed in 0.11s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py -q
....................                                                     [100%]
20 passed in 0.12s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_generation_swap.py -q
..................................                                       [100%]
34 passed in 0.57s
exit code: 0

$ uv run pytest tests/architecture/test_macro_kappa_contract.py tests/architecture/test_worker_runtime_contracts.py::test_read_model_single_writers tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
.......................................................                  [100%]
55 passed in 1.35s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check src/parallax/domains/asset_market/repositories/token_profile_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/unit/test_token_profile_current_repository.py
All checks passed!
exit code: 0

$ git diff --check
src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:178: new blank line at EOF.
exit code: 2

$ uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/unit/test_token_profile_current_repository.py -q
.....                                                                    [100%]
5 passed in 0.10s
exit code: 0

$ uv run ruff check src/parallax/domains/asset_market/repositories/token_profile_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/unit/test_token_profile_current_repository.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run ruff check src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys -q
FAILED tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_observation_identity.py -q
.....                                                                    [100%]
5 passed in 0.03s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_generation_swap.py tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py -q
.............                                                            [100%]
13 passed in 0.18s
exit code: 0

$ uv run pytest tests/architecture/test_macro_kappa_contract.py tests/architecture/test_worker_runtime_contracts.py::test_read_model_single_writers tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
.......................................................                  [100%]
55 passed in 1.33s
exit code: 0

$ uv run ruff check src/parallax/domains/macro_intel/observation_identity.py tests/unit/domains/macro_intel/test_macro_observation_identity.py
All checks passed!
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
docs/generated/sdd-work-index.md is stale; run `uv run python scripts/regen_sdd_work_index.py`.
exit code: 1

$ uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ uv run pytest tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers -q
FAILED tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys
FAILED tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers
exit code: 1

$ uv run pytest tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers -q
..                                                                       [100%]
2 passed in 0.08s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_payload_hash.py -q
.....                                                                    [100%]
5 passed in 0.07s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_repository.py -q
............................                                             [100%]
28 passed in 0.22s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_projection.py::test_projection_downstream_payload_hash_ignores_factor_snapshot_computed_at_noise tests/unit/test_token_radar_projection.py::test_current_row_builder_sets_scalar_score_and_quality_without_legacy_blocks -q
..                                                                       [100%]
2 passed in 0.26s
exit code: 0

$ uv run pytest tests/architecture/test_token_radar_publication_state_hard_cut.py tests/architecture/test_token_radar_sql_surface_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py::test_read_model_single_writers -q
............................                                             [100%]
28 passed in 1.74s
exit code: 0

$ uv run pytest tests/architecture/test_src_domain_architecture.py -q
FAILED tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime
exit code: 1

$ uv run pytest tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime -q
.                                                                        [100%]
1 passed in 0.16s
exit code: 0

$ uv run pytest tests/architecture/test_src_domain_architecture.py -q
.........................                                                [100%]
25 passed in 2.83s
exit code: 0

$ uv run pytest tests/architecture/test_worker_manifest_static_contracts.py -q
............................................                             [100%]
44 passed in 0.39s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_payload_hash.py tests/unit/test_token_radar_repository.py tests/unit/test_token_radar_projection.py::test_projection_downstream_payload_hash_ignores_factor_snapshot_computed_at_noise tests/unit/test_token_radar_projection.py::test_current_row_builder_sets_scalar_score_and_quality_without_legacy_blocks -q
...................................                                      [100%]
35 passed in 0.24s
exit code: 0

$ uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys -q
.......                                                                  [100%]
7 passed in 0.18s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_dirty_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys -q
FF                                                                       [100%]
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_dirty_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys -q
..                                                                       [100%]
2 passed in 0.29s
exit code: 0

$ uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_ignores_queue_lifecycle_fields -q
FF                                                                       [100%]
Failed: DID NOT RAISE <class 'ValueError'>
AssertionError: assert second == first
exit code: 1

$ uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_ignores_queue_lifecycle_fields -q
..                                                                       [100%]
2 passed in 0.24s
exit code: 0

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_ignores_queue_lifecycle_fields -q
FF                                                                       [100%]
Failed: DID NOT RAISE <class 'ValueError'>
AssertionError: assert second == first
exit code: 1

$ uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_ignores_queue_lifecycle_fields -q
..                                                                       [100%]
2 passed in 0.25s
exit code: 0

$ uv run pytest tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py -q
FFFFFFFFF                                                                [100%]
Failed: DID NOT RAISE <class 'ValueError'>
TypeError: '<' not supported between instances of 'str' and 'int'
AssertionError: assert second == first
exit code: 1

$ uv run pytest tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py -q
.........                                                                [100%]
9 passed in 0.08s
exit code: 0

$ uv run pytest tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py::test_dirty_payload_hash_excludes_queue_lifecycle_fields -q
F                                                                        [100%]
AssertionError: assert 71 == 64
exit code: 1

$ uv run pytest tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py::test_dirty_payload_hash_excludes_queue_lifecycle_fields -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py::test_dirty_payload_hash_excludes_queue_lifecycle_fields -q
..........                                                               [100%]
10 passed in 0.12s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers -q
FFF                                                                      [100%]
AssertionError: assert False
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers -q
...                                                                      [100%]
3 passed in 0.21s
exit code: 0

$ uv run pytest tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_ignores_source_watermark_metadata tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_includes_live_market_key tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_accepts_decimal_rank_scores tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_factor_snapshot_live_market_key -q
.......                                                                  [100%]
7 passed in 0.19s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_target_coalesces_current_target tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes -q
FFFF                                                                     [100%]
AssertionError: assert False
Failed: DID NOT RAISE <class 'ValueError'>
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_target_coalesces_current_target tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes -q
....                                                                     [100%]
4 passed in 0.08s
exit code: 0

$ uv run pytest tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_doc_names_current_read_tool_contract -q
F                                                                        [100%]
AssertionError: assert '`ReadOnlySqlAgentTool`' in doc_text
exit code: 1

$ uv run pytest tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_doc_names_current_read_tool_contract -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_missing_current_file_and_touch_paths tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_removed_file_records_outside_current_touch_surface -q
F.                                                                       [100%]
AssertionError: assert []
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_current_glob_touch_paths_when_they_match -q
F                                                                        [100%]
AssertionError: assert 'task-invalid-coordination-fields' not in _issue_codes(issues)
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_missing_current_file_and_touch_paths tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_removed_file_records_outside_current_touch_surface tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_current_glob_touch_paths_when_they_match -q
...                                                                      [100%]
3 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_individual_gates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q
FF                                                                       [100%]
AssertionError: assert False
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_individual_gates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q
..                                                                       [100%]
2 passed in 0.24s
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-06-09-executable-harness-hard-cut --gate clarify --check
clarify gate passed: 2026-06-09-executable-harness-hard-cut
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-06-09-executable-harness-hard-cut --gate checklist --check
checklist gate passed: 2026-06-09-executable-harness-hard-cut
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-06-09-executable-harness-hard-cut --gate analyze --check
analyze gate passed: 2026-06-09-executable-harness-hard-cut
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-06-09-executable-harness-hard-cut --gate implement --check
implement gate passed: 2026-06-09-executable-harness-hard-cut
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface -q
FF                                                                       [100%]
AssertionError: assert 'tasks-final-verification-duplicated' in set()
AssertionError: assert '## Final verification' not in text
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface -q
..                                                                       [100%]
2 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface -q
..                                                                       [100%]
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
...................................................................F.... [ 96%]
...                                                                      [100%]
AssertionError: assert 'make check-all' in tasks-template.md
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 4.52s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ if rg -n '^## Final verification\s*$' docs/sdd/features/active docs/sdd/_templates/tasks-template.md; then exit 1; else echo 'no active task/template final-verification headings'; fi
no active task/template final-verification headings
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_all_active_features tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_any_failed_active_feature -q
FFF                                                                      [100%]
AssertionError: assert 'scripts/check_sdd_gate.py --all-active --check' in check_all
check_sdd_gate.py: error: the following arguments are required: --feature, --gate
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_all_active_features tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_any_failed_active_feature -q
...                                                                      [100%]
3 passed in 0.07s
exit code: 0

$ uv run python scripts/check_sdd_gate.py --all-active --check
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-09-executable-harness-hard-cut
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift -q
F                                                                        [100%]
AssertionError: assert 0 == 1
stdout='implement gate passed: 2026-06-09-context-packet-fixture'
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift -q
.                                                                        [100%]
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_header_only_gate_tables -q
F                                                                        [100%]
AssertionError: assert 0 == 1
stdout='clarify gate passed: 2026-06-09-context-packet-fixture'
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_header_only_gate_tables -q
.                                                                        [100%]
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_placeholder_gate_rows -q
F                                                                        [100%]
AssertionError: assert 0 == 1
stdout='clarify gate passed: 2026-06-09-context-packet-fixture'
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_placeholder_gate_rows -q
.                                                                        [100%]
1 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance -q
F                                                                        [100%]
AssertionError: assert 0 == 1
stdout='implement gate passed: 2026-06-09-context-packet-fixture'
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance -q
.                                                                        [100%]
1 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unbounded_analyze_status -q
F                                                                        [100%]
AssertionError: assert 0 == 1
stdout='analyze gate passed: 2026-06-09-context-packet-fixture'
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unbounded_analyze_status tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q
..                                                                       [100%]
2 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_must_be_markdown_heading_lines tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_requires_markdown_heading_lines -q
FF                                                                       [100%]
AssertionError: assert 'missing-gate-section' in {'spec-background-uncited'}
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_must_be_markdown_heading_lines tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_requires_markdown_heading_lines -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_fenced_heading_tokens -q
FF                                                                       [100%]
AssertionError: assert 'missing-gate-section' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_fenced_heading_tokens -q
..                                                                       [100%]
2 passed in 0.08s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_tilde_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens -q
FF                                                                       [100%]
AssertionError: assert 'missing-gate-section' in {'spec-background-uncited'}
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_tilde_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_single_cell_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_single_cell_gate_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_single_cell_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_single_cell_gate_rows -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_tables_without_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_tables_without_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_rows_before_separator tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_rows_before_separator -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_rows_before_separator tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_rows_before_separator -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_empty_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_empty_separator_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_empty_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_empty_separator_rows -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_separator_arity_mismatch tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_row_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_separator_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_row_arity_mismatch -q
FFFF                                                                     [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_separator_arity_mismatch tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_row_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_separator_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_row_arity_mismatch -q
....                                                                     [100%]
4 passed in 0.08s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_non_contiguous_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_contiguous_body_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_non_contiguous_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_contiguous_body_rows -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_wrong_clarification_header tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_wrong_clarification_header -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_wrong_clarification_header tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_wrong_clarification_header -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_ignores_non_canonical_tables tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables -q
FF                                                                       [100%]
AssertionError: assert 'plan-analyze-gate-invalid' not in {'plan-analyze-gate-invalid'}
AssertionError: plan-analyze-gate-invalid: docs/sdd/features/active/2026-06-09-context-packet-fixture/plan.md analyze gate results must start with Pass: or Blocked: This table is context, not an Analyze Gate result.
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_ignores_non_canonical_tables tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check -q
.                                                                        [100%]
1 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_separator_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_separator_rows -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_header_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_header_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_header_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_header_rows -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_unclosed_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unclosed_table_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_unclosed_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unclosed_table_rows -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_doubled_boundary_pipes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_doubled_boundary_pipes -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_doubled_boundary_pipes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_doubled_boundary_pipes -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_indented_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_indented_table_rows -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_indented_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_indented_table_rows -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_clarification_gate_evidence_rejects_non_canonical_approval_dates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_clarification_gate_evidence_rejects_non_canonical_approval_dates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_metadata_dates_require_canonical_real_dates -q
F                                                                        [100%]
AssertionError: assert 'metadata-date-invalid' in {'feature-slug-invalid'}
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_metadata_dates_require_canonical_real_dates -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_requires_all_canonical_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_requires_all_canonical_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance -q
..                                                                       [100%]
2 passed in 0.08s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_status_without_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_analyze_status_without_evidence -q
FF                                                                       [100%]
AssertionError: assert 'plan-analyze-gate-invalid' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_status_without_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_analyze_status_without_evidence -q
..                                                                       [100%]
2 passed in 0.08s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_duplicate_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_duplicate_task_gate_compliance -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_duplicate_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_duplicate_task_gate_compliance -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_split_table_blocks tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_split_task_gate_compliance -q
FF                                                                       [100%]
AssertionError: assert 'gate-evidence-missing' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_split_table_blocks tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_split_task_gate_compliance -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_missing_check_all_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_spec_compliance tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_spec_compliance_rows -q
FFFF                                                                     [100%]
AssertionError: assert 2 == 1
AssertionError: assert 2 == 1
AssertionError: usage: check_sdd_gate.py ... invalid choice: 'verify'
AssertionError: assert 'verified-incomplete-spec-compliance' in set()
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_missing_check_all_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_spec_compliance tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_spec_compliance_rows -q
....                                                                     [100%]
4 passed in 0.18s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_empty_spec_compliance -q
FF                                                                       [100%]
AssertionError: assert 'verified-incomplete-spec-compliance' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_empty_spec_compliance -q
..                                                                       [100%]
2 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_partial_spec_compliance -q
FF                                                                       [100%]
AssertionError: assert 'verified-incomplete-spec-compliance' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_partial_spec_compliance -q
..                                                                       [100%]
2 passed in 0.10s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_passing_coverage_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_coverage -q
FF                                                                       [100%]
AssertionError: assert 'verified-coverage-incomplete' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_passing_coverage_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_coverage tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q
...                                                                      [100%]
3 passed in 0.13s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q
FF.                                                                      [100%]
AssertionError: assert 'verified-e2e-incomplete' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q
...                                                                      [100%]
3 passed in 0.11s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_numeric_skipped_test_count tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_skipped_count -q
FF                                                                       [100%]
AssertionError: assert 'verified-unexplained-skips' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_numeric_skipped_test_count tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_skipped_count -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_count_inside_skipped_tests_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_skipped_count_outside_skipped_section -q
FF                                                                       [100%]
AssertionError: assert 'verified-unexplained-skips' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_count_inside_skipped_tests_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_skipped_count_outside_skipped_section -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_canonical_skipped_tests_table tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_freeform_skipped_table -q
FF                                                                       [100%]
AssertionError: assert 'verified-unexplained-skips' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_canonical_skipped_tests_table tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_freeform_skipped_table -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_coverage_values tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_coverage_value -q
FF                                                                       [100%]
AssertionError: assert 'verified-coverage-incomplete' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_coverage_values tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_coverage_value -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence -q
FF                                                                       [100%]
AssertionError: assert 'verified-incomplete-spec-compliance' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence -q
FF                                                                       [100%]
AssertionError: assert 'verified-incomplete-spec-compliance' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence -q
..                                                                       [100%]
2 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_command_shaped_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_prose_only_spec_compliance_evidence -q
FF                                                                       [100%]
AssertionError: assert 'verified-missing-spec-compliance-evidence' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_command_shaped_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_prose_only_spec_compliance_evidence -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_fenced_e2e_golden_path -q
FF                                                                       [100%]
AssertionError: assert 'verified-e2e-incomplete' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_fenced_e2e_golden_path -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_make_check_all_own_exit_code_zero tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_failed_check_all_before_helper_success -q
FF                                                                       [100%]
AssertionError: assert 'verified-missing-check-all' in set()
AssertionError: assert 0 == 1
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_make_check_all_own_exit_code_zero tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_failed_check_all_before_helper_success -q
..                                                                       [100%]
2 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
F                                                                        [100%]
AssertionError: assert '| Feature | Task | Status | Dispatch | Factory lane | Owner | Depends on | Touch set | Conflict set | Kill/defer criteria | Eval/repair signal | Subagent report | Review result | Verification |' in text
exit code: 1

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate -q
F                                                                        [100%]
AssertionError: assert 'check-sdd-completion:' in makefile
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_makefile_pytest_targets_do_not_accept_empty_collections -q
F                                                                        [100%]
AssertionError: assert '[ $$ec -eq 5 ] && exit 0' not in 'PARALLAX :=...k_index.py\n'
exit code: 1

$ uv run pytest tests/architecture/test_harness_structure.py::test_makefile_pytest_targets_do_not_accept_empty_collections -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker -q
F                                                                        [100%]
AssertionError: assert '"golden: curated corpus tests against the real ingest/projection pipeline' in '[project]\nname = "parallax"\n...'
exit code: 1

$ UV_NO_SYNC=1 uv run pytest tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ python -m pytest tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ UV_NO_SYNC=1 uv run python -m pytest tests/golden --collect-only -m golden -q
tests/golden/test_token_radar_corpus.py::test_versa_symbol_and_ca_build_one_intent
tests/golden/test_token_radar_corpus.py::test_unresolved_attention_never_projects_as_driver
tests/golden/test_token_radar_corpus.py::test_address_like_payload_symbol_does_not_mask_missing_real_symbol
tests/golden/test_token_radar_corpus.py::test_gmgn_payload_identity_does_not_project_market_snapshot_into_radar
4 tests collected in 0.49s
exit code: 0

$ UV_NO_SYNC=1 uv run python -m pytest tests/golden --collect-only -m e2e -q
no tests collected (4 deselected) in 0.49s
exit code: 5

$ python -m pytest tests/architecture/test_harness_structure.py::test_final_runtime_lanes_do_not_expose_skip_env_switches -q
F                                                                        [100%]
AssertionError: assert 'SKIP_E2E' not in '"""End-to-e...'
exit code: 1

$ python -m pytest tests/architecture/test_harness_structure.py::test_final_runtime_lanes_do_not_expose_skip_env_switches -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ python -m pytest tests/architecture/test_harness_structure.py::test_contract_lane_has_no_duplicate_make_alias -q
F                                                                        [100%]
AssertionError: assert 'contract-check' not in [...]
exit code: 1

$ python -m pytest tests/architecture/test_harness_structure.py::test_contract_lane_has_no_duplicate_make_alias -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ python -m pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_do_not_skip_contracts -q
F                                                                        [100%]
AssertionError: architecture harness contracts must fail closed instead of skipping:
tests/architecture/test_worker_runtime_contracts.py:238: pytest.skip(
tests/architecture/test_worker_runtime_contracts.py:240: pytest.skip(
tests/architecture/test_worker_runtime_contracts.py:254: pytest.skip(
tests/architecture/test_worker_runtime_contracts.py:272: pytest.skip(
exit code: 1

$ python -m pytest tests/architecture/test_test_lane_contracts.py::test_pytest_empty_parameter_sets_fail_at_collect -q
F                                                                        [100%]
KeyError: 'empty_parameter_set_mark'
exit code: 1

$ export UV_NO_SYNC=1
$ export UV_CACHE_DIR=/private/tmp/parallax-uv-cache
$ uv run pytest tests/architecture/test_test_lane_contracts.py tests/architecture/test_worker_runtime_contracts.py -q
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 4.32s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_validator_cli_fails_on_issues_without_check_flag -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_validator_cli_fails_on_issues_without_check_flag -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ python -m pytest tests/architecture/test_test_lane_contracts.py::test_coverage_report_does_not_hide_empty_source_files -q
F                                                                        [100%]
AssertionError: assert True is False
exit code: 1

$ python -m pytest tests/architecture/test_test_lane_contracts.py::test_coverage_report_does_not_hide_empty_source_files -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_title_substring_selectors -q
F                                                                        [100%]
AssertionError: build_agent_context_packet.py
# Context Packet - 2026-06-09-context-packet-fixture / Task 1
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_title_substring_selectors -q
.                                                                        [100%]
1 passed in 0.12s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_golden_skip_switch -q
F                                                                        [100%]
AssertionError: assert 'verified-e2e-incomplete' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_golden_skip_switch -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_golden_skip_switch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_golden_skip_switch -q
..                                                                       [100%]
2 passed in 0.10s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_command -q
F                                                                        [100%]
AssertionError: assert 'verified-extra-verification-command' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_command -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_command tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_command -q
..                                                                       [100%]
2 passed in 0.09s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_unfenced_extra_verification_command -q
F                                                                        [100%]
AssertionError: assert 'verified-extra-verification-command' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_unfenced_extra_verification_command -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_unfenced_extra_verification_command tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_unfenced_extra_verification_command -q
..                                                                       [100%]
2 passed in 0.09s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_unfenced_make_check_all -q
F                                                                        [100%]
AssertionError: assert 'verified-extra-verification-command' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_unfenced_make_check_all -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_unfenced_make_check_all tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_unfenced_make_check_all -q
..                                                                       [100%]
2 passed in 0.11s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_multiple_check_all_exit_codes -q
F                                                                        [100%]
AssertionError: assert 'verified-missing-check-all' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_multiple_check_all_exit_codes -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_multiple_check_all_exit_codes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_multiple_check_all_exit_codes -q
..                                                                       [100%]
2 passed in 0.07s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_output_block -q
F                                                                        [100%]
AssertionError: assert 'verified-extra-verification-output' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_output_block -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_output_block tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_output_block -q
..                                                                       [100%]
2 passed in 0.05s
exit code: 0

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_verification_commands_section -q
F                                                                        [100%]
AssertionError: assert 'duplicate-gate-section' in set()
exit code: 1

$ python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_verification_commands_section -q
F                                                                        [100%]
AssertionError: assert 0 == 1
exit code: 1

$ python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_verification_commands_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_verification_commands_section -q
..                                                                       [100%]
2 passed in 0.08s
exit code: 0
```

## Diff summary

Files changed:

- SDD executable harness: `scripts/validate_sdd_artifacts.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `scripts/regen_sdd_work_index.py`, SDD templates, `docs/generated/sdd-work-index.md`.
- Development-agent factory/eval loop: `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/agent-playbook/task-reading-matrix.md`.
- Test taxonomy and gate wiring: `docs/TESTING.md`, `docs/WORKFLOW.md`, `Makefile`, architecture tests.
- SQL query-contract helper and macro request-path hard cut: `tests/support/query_contract.py`, macro repository/tests.
- Macro dirty-control-plane hard cut: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`.
- Agent execution docs/source alignment: `docs/AGENT_EXECUTION.md`, `tests/architecture/test_agent_execution_plane_contracts.py`.
- Active SDD current-path hard cut: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/_templates/tasks-template.md`.
- First-class SDD gate checks: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`.
- Tasks final-verification duplication hard cut: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/_templates/tasks-template.md`.
- All-active SDD gate sweep: `Makefile`, `scripts/check_sdd_gate.py`, `tests/architecture/test_harness_structure.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`.
- Implement gate delegated drift forwarding: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Gate evidence header-only hard cut: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Gate placeholder semantics sharing: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Implement gate task compliance forwarding: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Analyze gate bounded result status: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- SDD section heading-line parsing: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Fence-aware SDD section parsing: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Tilde-fence SDD section parsing: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Multi-cell gate evidence rows: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Separator-aware gate evidence parsing: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Strict gate evidence table order: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Hyphen-bearing gate table separators: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Equal-arity gate evidence tables: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Contiguous gate evidence table blocks: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Canonical gate evidence headers: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Canonical Analyze Gate result rows: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Shared Analyze Gate invalid-result semantics: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Repeated separator gate evidence rejection: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Repeated header gate evidence rejection: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Closed pipe-row gate evidence parsing: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Single-boundary pipe gate evidence parsing: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Top-level gate evidence table parsing: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Clarification canonical approval dates: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Artifact metadata canonical dates: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`.
- Canonical Gate Compliance rows: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Analyze status evidence requirement: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Exact Gate Compliance row sequence: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Single-block Gate Compliance table: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- First-class verify gate: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`.
- Required Spec compliance rows: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Full Spec compliance AC coverage: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified Coverage row completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified E2E golden path completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified skipped-test numeric count completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified skipped-test section-local count completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified skipped-test canonical explanation table completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified concrete Coverage row completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified concrete Spec compliance evidence completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified command-shaped Spec compliance evidence completion: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified fenced E2E evidence rejection: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Verified make-check-all command segment exit-code binding: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Generated Task Board repair-pressure visibility: `scripts/regen_sdd_work_index.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`.
- Single-feature SDD completion Make target: `Makefile`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`.
- Makefile pytest targets reject empty pytest collections: `Makefile`, `docs/TESTING.md`, `tests/architecture/test_harness_structure.py`.
- Dedicated golden corpus pytest marker: `Makefile`, `docs/TESTING.md`, `tests/conftest.py`, `tests/golden/conftest.py`, `tests/architecture/test_harness_structure.py`.
- Final runtime lanes fail closed without skip switches: `docs/TESTING.md`, `docs/sdd/_templates/verification-template.md`, `tests/e2e/conftest.py`, `tests/golden/conftest.py`, `tests/architecture/test_harness_structure.py`.
- Single Make contract-test entrypoint: `Makefile`, `tests/architecture/test_harness_structure.py`.
- Architecture harness fail-closed skip ban and empty-parameter-set hard cut: `pyproject.toml`, `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`, `tests/architecture/test_worker_runtime_contracts.py`.
- SDD validator soft-mode hard cut: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`.
- Coverage empty-source visibility: `pyproject.toml`, `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`.
- Numeric-only SDD task selectors: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Final runtime skip-switch rejection: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Final verification single-command evidence: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Final verification unfenced-command scan: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Final verification exact command sequence: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Final make-check-all exit-code tuple validation: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Final verification single transcript block: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Required SDD section uniqueness: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- Mechanical frontend Prettier drift cleanup: macro pages, macro component test, `web/vite.config.ts`.

Migrations applied:

- None.

Schema or contract changes that consumers must be aware of:

- None.

## Risks observed

- Integration, e2e, golden, and coverage gates were not completed before merging to `main` by explicit user instruction.
- Full `uv run pytest tests/architecture -m architecture -q` is currently blocked by unrelated uncommitted News migration files writing `news_projection_dirty_targets` outside the architecture allowlist.

## Follow-ups

- Re-run `make check-all` when ready and move this feature record to `completed/` only after exit code 0 evidence exists.
