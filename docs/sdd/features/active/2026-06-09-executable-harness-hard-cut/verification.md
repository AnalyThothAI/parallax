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
| AC85 — Queue depth tables are worker-owned. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q` failed RED when a patched `queue_depth_table` outside `owned_tables` did not raise, then passed after adding queue-depth ownership validation. |
| AC86 — Side-effect ledgers belong to side-effect workers. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q` failed RED when a patched non-side-effect manifest with `side_effect_ledgers` did not raise, then passed after adding ledger-kind validation. |
| AC87 — Wake channels are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q` failed RED when a patched blank `wakes_out` channel did not raise, then passed after adding wake-channel validation. |
| AC88 — Wake channels are unique per worker field. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q` failed RED when a patched duplicate `wakes_on` channel did not raise, then passed after adding wake-channel duplicate validation. |
| AC89 — Advisory lock keys are unique. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q` failed RED when two patched manifests shared one `advisory_lock_key`, then passed after adding advisory-lock duplicate validation. |
| AC90 — Advisory lock keys are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q` failed RED when a patched blank `advisory_lock_key` did not raise, then passed after adding advisory-lock blank-key validation. |
| AC91 — Worker identity fields are non-blank. | ✅ | `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q` failed RED when a patched blank `name` did not raise, then passed after adding identity-field validation. |

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
```

## Diff summary

Files changed:

- SDD executable harness: `scripts/validate_sdd_artifacts.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `scripts/regen_sdd_work_index.py`, SDD templates, `docs/generated/sdd-work-index.md`.
- Development-agent factory/eval loop: `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/agent-playbook/task-reading-matrix.md`.
- Test taxonomy and gate wiring: `docs/TESTING.md`, `docs/WORKFLOW.md`, `Makefile`, architecture tests.
- SQL query-contract helper and macro request-path hard cut: `tests/support/query_contract.py`, macro repository/tests.
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
