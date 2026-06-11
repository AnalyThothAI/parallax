# Plan — Executable Harness Hard Cut

**Status**: Superseded
**Superseded by**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/`
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut/spec.md`
**Worktree**: `.worktrees/agent-factory-eval-harness`
**Branch**: `codex/agent-factory-eval-harness`
**Approved by**: qinghuan
**Approved at**: 2026-06-09

## Pre-flight

- [x] Spec is approved by delegated user goal.
- [x] Worktree exists at `.worktrees/agent-factory-eval-harness` and `git branch --show-current` matches `codex/agent-factory-eval-harness`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes or known failures are listed in verification.

Known-failing baseline tests:

- None accepted without verification evidence.

## File-level edits

### `scripts/validate_sdd_artifacts.py`

- Create a pure filesystem validator with `scan_sdd_features(root: Path)`, `validate_sdd_root(root: Path)`, and a default fail-closed CLI.
- Emit deterministic issue codes for missing gate sections, missing approval metadata, incomplete task fields, false `Verified` evidence, stale generated index, and active touch/conflict overlap.
- Treat active touch-set parent/child path overlaps as conflicts and require coordination that names the overlapping feature slug or path.
- Validate `Owning spec` and `Owning plan` links point at the same feature's canonical artifacts before trusting the lifecycle record.
- Validate every `spec.md` acceptance criterion has exactly one matching `plan.md` acceptance test command entry.
- Validate spec and plan AC numbers are unique and contiguous before AC command coverage is trusted.
- Validate plan acceptance test commands are command-shaped, not backticked prose.
- Validate plan acceptance test command bullets are exact AC-numbered machine lines with no trailing prose or side labels.
- Validate feature directory slugs and artifact date metadata so old/freeform planning records cannot pass as current executable SDD.
- Validate clarify, checklist, analyze, and gate-compliance sections have non-placeholder structured evidence rows.
- Validate spec acceptance criteria use executable `WHEN ... THEN ... SHALL ...` structure before plan-command coverage is trusted.
- Validate `Verified` Spec compliance rows by requiring every command-shaped backticked command in completed rows to have exit code 0 evidence in canonical evidence sections.
- Validate Worktree/Branch metadata as machine-readable execution-location state, rejecting template placeholders, prose values, slug mismatches, and cross-artifact disagreement.
- Validate checked plan Pre-flight Worktree/Branch claims against the artifact metadata so stale setup evidence cannot remain checked.
- Validate plan Analyze Gate result cells as machine-statused `Pass:` or `Blocked:` values; freeform `Pass.` or `Fail:` rows are invalid.
- Validate spec Background paragraphs as source-backed claims with existing repo `path:line` citations or external `https://` references, and require backticked evidence tokens to appear in cited local lines.
- Validate task field semantics, not just presence: path-shaped file/touch values, structured conflict rules, command-shaped verification, test-shaped failing-test-first values, and known task status tokens.
- Validate task headings form a unique contiguous `Task 1..N` sequence before dependency or dispatch state is trusted.
- Parse task dependency references and ranges, reject unsupported dependency syntax, and report unresolved task numbers as `task-invalid-dependencies`.
- Reject `[x]` tasks whose declared dependency tasks are not also `[x]`.
- Validate task review evidence: delegated tasks must name a subagent report path and review result, non-delegated tasks must say `not delegated` / `parent-reviewed`, and completed tasks must have explicit `parent-reviewed` or `accepted` review evidence.
- Validate delegated subagent report artifacts by following the report path and running the shared task-bound report contract.
- Validate completed task evidence by requiring each `[x]` task's `Verification` command to appear in `verification.md` with exit code 0.
- Limit completed task evidence to the `## Verification commands` and `## Other commands run` evidence sections.
- Validate machine-token fields strictly so `not delegated` cannot carry prose suffixes.
- Validate delegated subagent handoff artifacts by following the handoff path before dispatch/review.
- Validate delegated subagent handoff artifacts against the owning feature/task/mode so stale handoff prompts cannot pass as current loop evidence.
- Validate delegated subagent reports against the mode granted by the owning handoff artifact, not the mode claimed by the report itself.
- Validate `Factory lane` values as one of the six development-agent lane tokens from the operating model.
- Validate completed task `Failing test first` references by requiring successful verification evidence that covers each referenced test file path.
- Validate `Superseded` artifact metadata before skipping content-section gates.
- Validate `Superseded` tasks files retain structured `### Task` records instead of legacy checkbox lists.
- Validate all artifacts in a `Superseded` feature point at the same successor record.
- Parse `Verified` completion evidence from the `## Verification commands` fenced block and require final `make check-all` exit code 0 plus explained skipped-test rows.

### `scripts/regen_cli_help.py`

- Add a non-mutating `--check` mode that renders CLI help from source and fails when `docs/generated/cli-help.md` is stale.
- Capture CLI warning output so normal freshness checks stay quiet while command failures still report stderr.

### `scripts/regen_sdd_work_index.py`

- Replace artifact-only rows with feature-level summaries and a coordination board.
- Reuse the validator metadata rather than duplicating SDD parsing rules.
- Add a task-level dispatch board with per-task status, dispatchability, factory lane, owner, dependencies, touch/conflict scopes, and verification command.
- Mark active tasks with incomplete dependencies as `blocked-by-dependencies`.
- Add subagent report and review result columns, and surface `needs-repair` as dispatch state.

### `scripts/build_agent_context_packet.py`

- Add a pure filesystem CLI that validates SDD records, selects one active feature task, and renders a bounded
  subagent context packet from the task's coordination and agent-loop fields.
- Keep it development-harness only; do not create a product LLM task queue, persistent runtime state, or compatibility
  path for old planning records.

### `scripts/dispatch_sdd_task.py`

- Add a pure filesystem dry-run dispatcher that validates SDD records, selects one active feature task, refuses
  completed, non-dispatchable, or dependency-blocked task statuses, and renders a subagent handoff containing the generated context packet.
- Keep dispatch non-persistent for this slice; no task claiming table, product agent queue, or runtime side effect.
- Include a report contract that routes returned subagent output through `scripts/validate_subagent_report.py`.

### `scripts/validate_subagent_report.py`

- Add a pure filesystem report validator for subagent return packets, with optional `--feature` and `--task` binding.
- Require stable sections for findings, scope adherence, changed files, verification evidence, and remaining risks.
- Reject read-only/review-only reports that list changed files, reject write-allowed reports outside the task touch set or inside the conflict set, reject verification sections without the task's expected command and exit status 0, and reject common secret-bearing fields.
- For task-bound reports, require `## Required Reading Evidence` with task classification, root agent instructions, the task reading matrix, and task on-demand context paths.

### `tests/architecture/test_agent_playbook_contracts.py`

- Update generated-index assertions from string counters to semantic coordination-board requirements.
- Require the SDD validator to pass as part of the architecture harness.
- Require explicit development-agent factory and eval/repair loop playbook contracts.
- Require the context-packet CLI to build a bounded packet from an active SDD task.
- Require the dry-run dispatch CLI to emit a handoff for in-progress tasks and refuse completed tasks.
- Require the generated SDD index to render task-level dispatch rows from `TaskRecord` metadata.
- Require dependency-blocked tasks to be refused by dispatch and surfaced in the task board.
- Require returned subagent reports to pass a machine-readable report contract before integration.

### `tests/architecture/test_sdd_artifact_validator.py`

- Add fixture tests for invalid task coordination field values and valid explicit `none` dependencies / `not delegated` handoffs.
- Add fixture tests proving old successful `make check-all` snippets outside the canonical verification block do not satisfy `Verified`.
- Add fixture coverage for nested active touch-set overlaps and conflict rules that coordinate with the wrong feature/path.

### `tests/architecture/test_harness_structure.py`

- Assert `make check-all` includes the CLI help snapshot freshness check, so generated public CLI docs cannot drift outside integration-only docs tests.
- Assert `make check-all` includes the score-version snapshot freshness check, so generated score/version docs cannot drift outside integration-only generated-doc tests.
- Assert `make check-all` includes the WebSocket protocol snapshot freshness check, so generated WebSocket docs cannot drift outside integration-only generated-doc tests.
- Assert `make check-all` includes `--check` for every non-DB generated-doc script listed in `docs/generated/README.md`, so freshness coverage is source-derived instead of one assertion per generated file.
- Assert `docs/generated/README.md` source-map rows point at existing generated files, generator scripts, and source paths.
- Assert `docs/generated/ws-protocol.md` lists the current WebSocket `type` literals from `src/parallax/app/surfaces/api/ws.py`.
- Assert open `docs/TECH_DEBT.md` source/test/doc references use self-contained repo-root paths, point at current files, and `::test_*` references point at existing Python test functions.
- Assert open `docs/TECH_DEBT.md` duplicate-symbol claims are backed by the current contents of each cited source file.
- Split governance rule checks into ownership and router-leak gates, backed by named multi-anchor rule contracts instead of single verbatim phrase strings.

### `tests/architecture/test_src_domain_architecture.py`

- Assert domain `types/` modules do not import upward layers such as services, repositories, queries, read models, or runtime.
- Assert domain `interfaces.py` modules do not import runtime modules.

### `web/tests/architecture/frontendDocContract.test.ts`

- Add a static Vitest gate that compares `docs/FRONTEND.md` and `.agents/skills/parallax-frontend-verification/SKILL.md` against current frontend CSS architecture constants and `APP_NAVIGATION_GROUPS`.

### `web/tests/architecture/featureBoundaries.test.ts`

- Replace the stale hard-coded feature-name regex with a source-derived feature root list from `web/src/features`.
- Add RED coverage proving the boundary scan cannot omit current feature roots or keep removed roots.

### `web/tests/architecture/frontendDataOwnership.test.ts`

- Add a static Vitest gate for the documented data ownership boundary.
- Scan `web/src/routes` and `web/src/features/*/ui` for direct server-state primitives while allowing feature-owned API hooks, page hooks, and controllers to own server reads/writes.
- Bind `docs/FRONTEND.md` to the executable harness so the rule cannot remain prose-only.

### `.agents/skills/parallax-frontend-verification/SKILL.md`, `web/tests/architecture/frontendDocContract.test.ts`

- Keep the repo-scoped frontend verification skill aligned with the data-ownership harness, not only CSS and route-shell commands.
- Require the skill to name `frontendDataOwnership.test.ts` and the route/UI forbidden server-state primitives from the harness.

### `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`

- Require architecture-document enforcement references to be path-qualified `tests/architecture/...py::test_*` references.
- Check referenced architecture test files and functions exist so docs cannot point agents at stale or bare test names.
- Require the global module map to include markdown links for every current `src/parallax/domains/*/ARCHITECTURE.md` file.

### `AGENTS.md`, `CLAUDE.md`, `tests/architecture/test_agent_playbook_contracts.py`

- Keep the shared agent router blocks mirrored and short while checking their frontend guardrails against current CSS harness constants.
- Parse `retiredGlobalCssBuckets` from `web/tests/architecture/cssArchitectureHarness.test.ts` so AGENTS/CLAUDE cannot preserve stale retired-bucket examples.

### `tests/architecture/test_public_contracts_doc_alignment.py`

- Add source-bound checks that compare `docs/CONTRACTS.md` worker keys, agent runtime lanes, WebSocket payloads, and News item route against current runtime/API source.

### `tests/architecture/test_test_lane_contracts.py`

- Add taxonomy checks for permanent invariants, migration tripwires, behavior contracts, and generated hygiene.
- Require the architecture test taxonomy table to exactly match current `tests/architecture/test_*.py` files, preventing both missing and stale inventory rows.

### `docs/agent-playbook/factory-operating-model.md`

- Codify development-agent lanes as bounded factory lanes, separate from product LLM agents.
- Split deterministic constraints from on-demand context so subagents receive small, precise packets.
- Define parent integrator ownership, maximum lane count, and kill/defer criteria.
- Route subagent handoffs through `scripts/build_agent_context_packet.py` instead of hand-copying template prose.
- Route dispatch prompts through `scripts/dispatch_sdd_task.py` so completed tasks are not handed off again.

### `docs/agent-playbook/eval-repair-loop.md`

- Define trace datasets, review defects, harness failures, token cost, and repair-loop closeout evidence.
- Require verification evidence before any production claim.

### `tests/support/query_contract.py`

- Create a lightweight SQL contract assertion helper that normalizes SQL and supports required tables, forbidden tables, required predicates, forbidden fragments, required locks, and params.

### `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

- Move worker runtime constraint classification into `WorkerManifest` and assert the architecture test no longer owns a parallel worker classification inventory.

### `tests/architecture/test_worker_inventory_contract.py`

- Replace peer architecture-test imports with source-derived `WorkerManifest` expectations for Worker Inventory worker keys and read-model writer rows.
- Add a static architecture gate that rejects architecture tests importing other architecture tests as source registries.

### `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`

- Add `WorkerManifest.owned_tables` as the source-owned table ownership contract and use it inside manifest validation instead of rebuilding ownership tuples in harness checks.
- Reject raw `lane`, `kind`, and `runtime_constraint` declarations that are not manifest enum values before scheduler, registry, factory, settings, or docs harnesses consume them.
- Reject blank `name`, `domain`, `factory`, and `worker_class` declarations before registry, factory, settings, or docs harnesses consume them.
- Reject `domain` declarations that do not name an existing `src/parallax/domains/<domain>` source directory before registry, factory, settings, or docs harnesses consume them.
- Reject `factory` declarations that do not name an existing `worker_factories/*.py` source file before registry, factory, settings, or docs harnesses consume them.
- Reject duplicate `worker_class` declarations before registry, factory, settings, or docs harnesses consume them.
- Reject `worker_class` declarations whose module path cannot be resolved before registry, factory, settings, or docs harnesses consume them.
- Reject `worker_class` declarations whose class name is absent from the resolved module before registry, factory, settings, or docs harnesses consume them.
- Reject non-boolean `uses_provider_io` declarations before provider-boundary, registry, settings, or docs harnesses consume them.
- Reject non-string `name`, `domain`, `factory`, and `worker_class` declarations before identity blank checks, source-path checks, class import checks, registry, settings, or docs harnesses consume them.
- Reject non-tuple values for tuple-valued manifest contract fields before registry, factory, settings, or docs harnesses consume them.
- Reject non-string entries inside tuple-valued string manifest contract fields before registry, factory, settings, or docs harnesses consume them.
- Reject negative `start_priority` declarations before scheduler, registry, settings, or docs harnesses consume them.
- Reject non-integer `start_priority` declarations before scheduler, registry, settings, or docs harnesses consume them.
- Reject blank `idempotency_evidence` declarations before lifecycle, ownership, review, or worker inventory harnesses consume them.
- Reject duplicate `idempotency_evidence` declarations before lifecycle, ownership, review, or worker inventory harnesses consume them.
- Reject empty `input_contract` declarations before registry, factory, settings, or docs harnesses consume them.
- Reject blank `input_contract` entries before registry, factory, settings, or docs harnesses consume them.
- Reject duplicate `input_contract` entries before registry, factory, settings, or docs harnesses consume them.
- Reject empty `ordering_keys` declarations before lifecycle, idempotency, registry, factory, settings, or docs harnesses consume them.
- Reject blank `ordering_keys` entries before lifecycle, idempotency, registry, factory, settings, or docs harnesses consume them.
- Reject duplicate `ordering_keys` entries before lifecycle, idempotency, registry, factory, settings, or docs harnesses consume them.
- Reject `DIRTY_TARGET_CONSUMER` manifests that omit `dirty_target_tables` before worker lifecycle harnesses trust runtime classification.
- Reject `LEASED_JOB_CONSUMER` manifests that omit `queue_depth_table` before queue-health harnesses trust runtime classification.
- Reject `BOUNDED_PROVIDER_SCHEDULER` manifests that omit `uses_provider_io` before provider-boundary harnesses trust runtime classification.
- Reject `BOUNDED_PROVIDER_SCHEDULER` manifests that declare `dirty_target_tables` before provider source adapters can masquerade as dirty-target consumers.
- Reject `BOUNDED_PROVIDER_SCHEDULER` manifests that declare `queue_depth_table` before provider source adapters can masquerade as leased queue consumers.
- Reject `BOUNDED_PROVIDER_SCHEDULER` manifests that declare `queue_health_tables` before provider source adapters can masquerade as queue-health consumers.
- Reject `queue_depth_table` declarations absent from the same manifest's owned tables before queue-health harnesses consume them.
- Reject `queue_depth_table` declarations absent from the same manifest's `writes_control_plane` before fact or read-model tables can masquerade as leased queues.
- Reject `queue_health_tables` declarations absent from the same manifest's `writes_control_plane` before fact or read-model tables can masquerade as queue-health surfaces.
- Reject non-string `queue_depth_table` declarations before table hygiene, queue ownership, queue-health, registry, settings, or worker inventory harnesses consume them.
- Reject non-side-effect worker kinds that declare `side_effect_ledgers` before ownership harnesses consume them.
- Reject blank `wakes_on` and `wakes_out` channel declarations before listener/notify harnesses consume them.
- Reject duplicate `wakes_on` and `wakes_out` channel declarations before listener/notify harnesses consume them.
- Reject duplicate `advisory_lock_key` declarations before lifecycle and advisory-lock harnesses consume them.
- Reject blank `advisory_lock_key` declarations before lifecycle and advisory-lock harnesses consume them.
- Reject non-string `advisory_lock_key` declarations before lifecycle, advisory-lock, registry, settings, or worker inventory harnesses consume them.
- Add `read_model_writer_by_table()` as the source-owned read-model writer map and use it in Worker Inventory docs checks.
- Run the read-model writer map inside manifest validation so duplicate read-model writers fail before downstream harness consumers trust the manifest.
- Reject `current_read_model_identities` entries for tables absent from the same manifest's `writes_read_models`.
- Reject duplicate `current_read_model_identities` entries for the same table within one worker manifest.
- Reject list-shaped `current_read_model_identities` entries before ownership, registry, factory, settings, or docs harnesses consume them.
- Reject malformed `current_read_model_identities` entries whose tuple arity is not exactly `(table_name, identity_columns)`.
- Reject non-string table names inside `current_read_model_identities` before blank, duplicate, missing-identity, ownership, registry, settings, or worker inventory harnesses consume them.
- Reject blank table names inside `current_read_model_identities` before ownership and missing-identity checks.
- Reject duplicate stable identity columns inside each `current_read_model_identities` entry and inside `CurrentReadModelPublisher`.
- Reject empty stable identity column lists inside each `current_read_model_identities` entry.
- Reject blank stable identity column names inside each `current_read_model_identities` entry and inside `CurrentReadModelPublisher`.
- Reject list-shaped stable identity column declarations inside `current_read_model_identities` before ownership, registry, factory, settings, or docs harnesses consume them.
- Reject list-shaped `CurrentReadModelPublisher.identity_columns` declarations before publisher validation consumes compatibility-shaped field lists.
- Reject non-string stable identity column names inside `CurrentReadModelPublisher` before blank, duplicate, lifecycle-column, row-identity, or changed-row hashing logic consumes them.
- Reject non-string `CurrentReadModelPublisher.payload_hash_column` values before row hashing or changed-row writes can use them as serving-row keys.
- Reject blank `CurrentReadModelPublisher.payload_hash_column` values before changed-row writes can add empty serving-row keys.
- Reject lifecycle `CurrentReadModelPublisher.payload_hash_column` values before changed-row writes can overwrite runtime lifecycle fields.
- Reject identity `CurrentReadModelPublisher.payload_hash_column` values before changed-row writes can overwrite serving identity keys.
- Reject non-tuple `CurrentReadModelPublisher.payload_columns` values before row hashing can treat compatibility lists or scalar strings as payload field lists.
- Reject non-string entries inside `CurrentReadModelPublisher.payload_columns` before row hashing can look up invalid payload keys.
- Reject blank entries inside `CurrentReadModelPublisher.payload_columns` before row hashing can look up empty payload keys.
- Reject duplicate entries inside `CurrentReadModelPublisher.payload_columns` before row hashing can silently collapse repeated payload keys.
- Reject explicit `CurrentReadModelPublisher.payload_columns` that include the configured payload hash column before row hashing can self-reference prior hashes.
- Reject explicit `CurrentReadModelPublisher.payload_columns` that include lifecycle columns before row hashing can reintroduce run/generation/timestamp drift.
- Require every explicit `CurrentReadModelPublisher.payload_columns` entry to exist in each row before hashing, so query drift fails instead of hashing missing fields as `None`.
- Report missing explicit `CurrentReadModelPublisher.payload_columns` entries as dedicated row-shape validation errors instead of raw `KeyError`.
- Require every `CurrentReadModelPublisher.identity_columns` entry to exist in each changed row before payload hashing, so query drift fails as missing stable identity instead of payload `KeyError`.
- Reject duplicate stable identity tuples inside one `CurrentReadModelPublisher.changed_rows()` batch before a projection can prepare multiple writes for the same current read-model row.
- Reject list-shaped or scalar rows inside `CurrentReadModelPublisher.changed_rows()` before row-column validation can mask row-shape drift.
- Reject list-shaped or scalar `existing_hashes` inside `CurrentReadModelPublisher.changed_rows()` before hash lookup can leak opaque mapping errors.
- Reject string or scalar existing-hash identity keys inside `CurrentReadModelPublisher.changed_rows()` before unchanged-row lookup can silently miss stable current rows.
- Reject wrong-arity existing-hash identity tuples inside `CurrentReadModelPublisher.changed_rows()` before unchanged-row lookup can silently miss stable current rows.
- Reject non-string, non-null existing-hash values inside `CurrentReadModelPublisher.changed_rows()` before unchanged-row lookup can silently miss stable current rows.
- Reject malformed existing-hash strings inside `CurrentReadModelPublisher.changed_rows()` before unchanged-row lookup can silently miss stable current rows.
- Reject non-string row keys inside `CurrentReadModelPublisher.changed_rows()` before payload hashing or write preparation can preserve compatibility-shaped mapping keys.
- Reject `None` values for stable identity columns inside `CurrentReadModelPublisher.changed_rows()` before absent product/window keys can become current serving identities.
- Reject blank string values for stable identity columns inside `CurrentReadModelPublisher.changed_rows()` before whitespace placeholders can become current serving identities.
- Reject scalar, mapping, and string-shaped row batches inside `CurrentReadModelPublisher.changed_rows()` before row validation can split compatibility containers into fake row values.
- Reject scalar, list-of-pairs, and string-shaped payloads inside `stable_current_payload_hash()` before `dict(...)` coercion can turn compatibility containers into serving hashes.
- Reject non-string top-level payload keys inside `stable_current_payload_hash()` before JSON normalization can stringify compatibility-shaped mapping keys.
- Reject non-string nested mapping keys inside `stable_current_payload_hash()` before JSON normalization can stringify compatibility-shaped factor snapshots or JSON payload blocks.
- Reject arbitrary `isoformat()` payload objects inside `stable_current_payload_hash()` before JSON normalization can turn compatibility-shaped values into serving hashes.
- Reject float and Decimal NaN/Infinity payload values inside `stable_current_payload_hash()` before JSON serialization or Decimal stringification can consume non-finite numbers as serving hashes.
- Reject set and frozenset payload values inside `stable_current_payload_hash()` before JSON normalization can sort unordered compatibility containers into serving hashes.
- Replace the CEX OI radar board's local payload-hash normalizer with the shared `stable_current_payload_hash()` contract so score component keys are not stringified by a domain-local compatibility shim.
- Remove the `WorkerScheduler` re-export from `parallax.app.runtime.__init__` so importing shared runtime helper modules from domains does not trigger scheduler import, `worker_manifest` validation, or worker class import cycles.
- Replace the CEX detail snapshot local payload-hash normalizer with the shared `stable_current_payload_hash()` contract and stop coupling runtime tests to historical migration-golden numeric canonicalization.
- Reject non-string CEX detail source-ref keys before source-ref metadata filtering can stringify compatibility-shaped payload keys.
- Replace the token profile current local payload-hash normalizer with the shared `stable_current_payload_hash()` contract and validate JSON payload blocks before `postgres_safe_json()` can stringify compatibility-shaped keys.
- Replace the News source-quality and page-row local payload-hash normalizer with the shared `stable_current_payload_hash()` contract and keep only strict `Jsonb` adapter unwrapping that preserves mapping keys before validation.
- Replace the Narrative admission local payload-hash normalizer with the shared `stable_current_payload_hash()` contract and keep only strict `Jsonb` adapter unwrapping that preserves mapping keys before validation.
- Reject Narrative admission Jsonb-like adapter objects that only expose an `obj` attribute before generic adapter unwrapping can preserve compatibility-shaped payloads.
- Replace the Macro daily brief local payload-hash normalizer with the shared `stable_current_payload_hash()` contract so current `macro_daily_briefs` hashes reject compatibility-shaped payload keys before `postgres_safe_json()` or generic `default=str` conversion.
- Replace the Macro view snapshot local payload-hash normalizer with the shared `stable_current_payload_hash()` contract so current `macro_view_snapshots` hashes reject compatibility-shaped nested snapshot keys before `postgres_safe_json()` or generic `default=str` conversion.
- Replace Token Radar stable payload hash finalization with the shared `stable_current_payload_hash()` contract while keeping only product-specific canonical removal of `factor_snapshot_json.provenance.computed_at_ms`.
- Move the shared current payload hash contract to `src/parallax/platform/current_read_model_payload_hash.py` so domain repositories and services can use it without importing `app.runtime`.
- Import `importlib.util` directly inside `worker_manifest.py` so manifest validation does not depend on prior import side effects in clean processes.
- Reject loose visual verification artifacts at the repository root and keep screenshots under owned artifact directories.
- Reject duplicate table names inside each `WorkerManifest` table-declaration field before `owned_tables` dedupes them.
- Reject blank table names inside each `WorkerManifest` table-declaration field and `queue_depth_table`.

### `tests/unit/domains/macro_intel/test_macro_migration_contract.py`

- Replace the obsolete `concept_history_counts` raw-fact assertion with a projected-row request-path contract using the query-contract helper.

### `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`

- Update `concept_history_counts` to read `macro_observation_series_rows` for request-path history counts.

### `Makefile`

- Add `uv run python scripts/validate_sdd_artifacts.py` and keep `uv run python scripts/regen_sdd_work_index.py --check` in `check-all`.
- Add `uv run python scripts/regen_cli_help.py --check` to `check-all` before integration, e2e, golden, and coverage gates.

### `docs/CONTRACTS.md`

- Replace retired worker keys and agent lane prose with source-bound current manifest/settings lists.
- Replace retired WebSocket `enrichment` payload wording with current event token-intent/resolution, notification, social update, and live market payload wording.
- Replace old News item detail route with `/api/news/items/{news_item_id}`.

### `docs/generated/README.md`, `scripts/regen_ws_protocol.py`

- Replace the stale `src/parallax/api/ws.py` generated-doc source pointer with the current public API WebSocket source path.
- Keep the WebSocket protocol generator docstring aligned with its current source boundary.

### `docs/FRONTEND.md`, `.agents/skills/parallax-frontend-verification/SKILL.md`

- Align CSS retired-bucket and side-effect line-budget wording with current frontend architecture tests.
- Document sanctioned `@features/<name>/shell` route-shell entrypoints and current feature-owned page/controller hook data ownership.
- Document that the relative-import boundary gate derives feature roots from `web/src/features`.
- Keep the frontend verification skill's deterministic commands and retired CSS list aligned with the same architecture harness.

### `docs/sdd/_templates/*.md`, `docs/WORKFLOW.md`, `docs/sdd/README.md`

- Add machine-readable approval, gate, worktree, touch set, conflict set, analysis, and verification metadata expected by the validator.
- Add factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal fields to task records.
- Add subagent report and review result fields so parent review outcome is task state, not prose.

## PR breakdown

1. **PR 1 — executable SDD harness**: scripts, templates, generated index, architecture tests, Makefile.
2. **PR 2 — SQL contract and macro obsolete test removal**: query helper, macro repository/test update.

This branch implements both slices together because the user requested a thorough hard cut in one pass.

## Rollout order

1. Write failing tests for SDD validator/index/query contract behavior.
2. Implement validator and index generator changes.
3. Regenerate `docs/generated/sdd-work-index.md`.
4. Refactor macro request-path test and implementation.
5. Run focused tests, then broad gates.

## Rollback

This is a development harness hard cut. Rollback is reverting this branch before merge. After merge, false positives should be fixed by adjusting the validator with tests, not by preserving legacy compatibility paths.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to plan edits. | Pass: G1-G5 map to script, generated index, tests, query helper, and Makefile edits. |
| Product runtime boundary is untouched. | Pass: no product LLM runtime or queue changes planned. |
| Compatibility paths are removed rather than wrapped. | Pass: no retired planning-lane support planned. |
| Multi-agent coordination is represented as metadata. | Pass: owner/worktree/branch/touch/conflict/review fields are planned. |
| Development-agent loops are separated from product agents. | Pass: factory/eval playbooks explicitly keep product LLM agents outside development-agent lanes. |
| Context packets are executable, not prose-only. | Pass: a new CLI reads active SDD task metadata and emits a bounded handoff packet. |
| Dispatch is dry-run and non-runtime. | Pass: dispatcher emits prompts only and refuses completed tasks without creating durable product state. |
| Task fields are semantically checked. | Pass: validator rejects `none` touch sets, non-command verification, non-test failing-test-first values, and unknown task statuses. |
| Verified evidence is replayable. | Pass: validator reads the canonical command block and rejects positive skipped-test counts. |
| Task dispatch state is visible. | Pass: generated index includes a `Task Board` with dispatchable/complete/blocked/closed task state. |
| Task dependencies are executable. | Pass: validator checks dependency syntax/resolution and dispatcher/index block incomplete dependencies. |
| Subagent return evidence is executable. | Pass: report validator checks scope adherence, changed files against task scope, verification command/exit code, and secret hygiene. |
| Parent review outcome is task state. | Pass: validator rejects missing/inconsistent review evidence and index exposes review result / needs-repair. |
| Referenced report artifacts are verified. | Pass: SDD validator fails missing or invalid delegated report files. |
| Completed task status is evidenced. | Pass: SDD validator fails `[x]` tasks without matching exit-code evidence. |
| Machine-readable tokens are exact. | Pass: validator rejects `not delegated` values with prose suffixes. |
| Referenced handoff artifacts are verified. | Pass: SDD validator fails missing delegated handoff files. |
| Acceptance commands are executable. | Pass: plan AC command entries must be command-shaped before they count as coverage. |
| Acceptance command lines are exact. | Pass: plan AC command bullets reject trailing prose, ranges, and non-AC labels. |
| Feature identity is machine-valid. | Pass: SDD feature slugs and artifact dates must match the current lane grammar. |
| Gate sections carry evidence. | Pass: required SDD gate sections must contain non-placeholder table rows. |
| Acceptance criteria are executable. | Pass: spec AC lines must use WHEN/THEN/SHALL structure. |
| Verified compliance rows are evidenced. | Pass: command-shaped evidence cited by completed Spec compliance rows must have exit code 0 in canonical evidence sections. |
| Worktree metadata is machine-valid. | Pass: validator rejects placeholder, prose, mismatched, or cross-artifact inconsistent Worktree/Branch fields. |
| Checked Pre-flight setup matches metadata. | Pass: validator rejects checked Worktree/Branch setup claims that disagree with plan metadata. |
| Spec background is source-backed. | Pass: Background claim blocks must cite existing repo `path:line` evidence or external `https://` sources. |
| Spec background citations are semantically anchored. | Pass: validator rejects local Background citations whose cited lines do not mention backticked evidence tokens from the claim block. |
| Worker runtime constraints are manifest-owned. | Pass: `WorkerManifest` carries the runtime constraint enum for every worker and architecture tests no longer define a separate worker classification map. |
| Worker classification fields are enum-owned. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares raw string `lane`. |
| Worker identity fields are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank `name`. |
| Worker domains are real source directories. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares missing `domain`. |
| Worker factory modules are real source files. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares missing `factory`. |
| Worker runtime classes are unique. | Pass: `_validate_worker_manifests()` raises when a patched manifest reuses another manifest's `worker_class`. |
| Worker runtime class modules resolve. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares missing `worker_class` module. |
| Worker runtime class names resolve. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares missing `worker_class` class name. |
| Worker start priorities are non-negative. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares negative `start_priority`. |
| Worker start priorities are integer bands. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares non-integer `start_priority`. |
| Provider I/O flags are boolean. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares truthy non-boolean `uses_provider_io`. |
| Worker identity fields are strings. | Pass: `_validate_worker_manifests()` raises before blank checks when patched manifests declare numeric `name`, `domain`, `factory`, or `worker_class`. |
| Tuple-valued manifest fields are tuples. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares list-shaped `input_contract`. |
| Tuple-valued string manifest fields contain strings. | Pass: `_validate_worker_manifests()` raises before blank checks when a patched manifest declares numeric `input_contract`. |
| Idempotency evidence is non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares blank `idempotency_evidence`. |
| Idempotency evidence is unique. | Pass: `_validate_worker_manifests()` raises when a patched manifest repeats one `idempotency_evidence` entry. |
| Input contracts are non-empty. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares an empty `input_contract`. |
| Input contracts are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank `input_contract` entry. |
| Input contracts are unique. | Pass: `_validate_worker_manifests()` raises when a patched manifest repeats one `input_contract` entry. |
| Ordering keys are non-empty. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares empty `ordering_keys`. |
| Ordering keys are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank `ordering_keys` entry. |
| Ordering keys are unique. | Pass: `_validate_worker_manifests()` raises when a patched manifest repeats one `ordering_keys` entry. |
| Dirty-target consumers declare dirty targets. | Pass: `_validate_worker_manifests()` raises when a patched `DIRTY_TARGET_CONSUMER` manifest omits `dirty_target_tables`. |
| Leased-job consumers declare queue depth tables. | Pass: `_validate_worker_manifests()` raises when a patched `LEASED_JOB_CONSUMER` manifest omits `queue_depth_table`. |
| Bounded provider schedulers declare provider I/O. | Pass: `_validate_worker_manifests()` raises when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest clears `uses_provider_io`. |
| Bounded provider schedulers do not declare dirty targets. | Pass: `_validate_worker_manifests()` raises when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest declares `dirty_target_tables`. |
| Bounded provider schedulers do not declare queue depth tables. | Pass: `_validate_worker_manifests()` raises when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest declares `queue_depth_table`. |
| Bounded provider schedulers do not declare queue health tables. | Pass: `_validate_worker_manifests()` raises when a patched `BOUNDED_PROVIDER_SCHEDULER` manifest declares `queue_health_tables`. |
| Queue depth tables are worker-owned. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares an unowned `queue_depth_table`. |
| Queue depth tables are control-plane-owned. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a fact table as `queue_depth_table`. |
| Queue health tables are control-plane-owned. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a read-model table as `queue_health_tables`. |
| Queue depth tables are strings. | Pass: `_validate_worker_manifests()` raises before blank table checks when a patched manifest declares numeric `queue_depth_table`. |
| Side-effect ledgers belong to side-effect workers. | Pass: `_validate_worker_manifests()` raises when a patched non-side-effect manifest declares `side_effect_ledgers`. |
| Wake channels are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank `wakes_out` channel. |
| Wake channels are unique per worker field. | Pass: `_validate_worker_manifests()` raises when a patched manifest repeats a `wakes_on` channel. |
| Advisory lock keys are unique. | Pass: `_validate_worker_manifests()` raises when two patched manifests share an `advisory_lock_key`. |
| Advisory lock keys are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank `advisory_lock_key`. |
| Advisory lock keys are strings. | Pass: `_validate_worker_manifests()` raises before blank lock checks when a patched manifest declares numeric `advisory_lock_key`. |
| Worker Inventory docs are manifest-owned. | Pass: worker inventory architecture tests import source manifest data directly and reject peer architecture-test imports. |
| Worker table ownership is manifest-owned. | Pass: `WorkerManifest.owned_tables` exposes the deduped owned-table contract and queue-health validation consumes it. |
| Read-model writer mapping is manifest-owned. | Pass: `read_model_writer_by_table()` exposes unique read-model ownership and Worker Inventory docs checks consume it. |
| Read-model writer uniqueness is import-time validated. | Pass: `_validate_worker_manifests()` raises when a patched manifest set writes the same read model from two workers. |
| Read-model identity ownership is import-time validated. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a stable identity for an unowned read model table. |
| Read-model identity entries are unique. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares two stable identity entries for one read model table. |
| Read-model identity entries are tuples. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a list-shaped stable identity entry. |
| Read-model identity entries are pairs. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a three-field stable identity entry before Python unpacking errors leak. |
| Read-model identity tables are strings. | Pass: `_validate_worker_manifests()` raises before blank table checks when a patched identity table name is numeric. |
| Read-model identity tables are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank `current_read_model_identities` table name before ownership checks. |
| Read-model identity columns are unique. | Pass: `_validate_worker_manifests()` and `CurrentReadModelPublisher` raise when a read-model identity repeats the same stable identity column. |
| Read-model identity columns are non-empty. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares an empty stable identity column list. |
| Read-model identity columns are non-blank. | Pass: `_validate_worker_manifests()` and `CurrentReadModelPublisher` raise when a read-model identity declares a blank stable identity column. |
| Read-model identity columns are tuples. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares list-shaped stable identity columns. |
| Read-model identity columns are strings. | Pass: `_validate_worker_manifests()` raises before blank column checks when a patched stable identity column is numeric. |
| Publisher identity columns are tuples. | Pass: `CurrentReadModelPublisher` raises at construction when given list-shaped stable identity columns. |
| Publisher identity columns are strings. | Pass: `CurrentReadModelPublisher` raises before blank column checks when constructed with a numeric stable identity column. |
| Publisher payload hash columns are strings. | Pass: `CurrentReadModelPublisher` raises at construction when given a numeric payload hash column name. |
| Publisher payload hash columns are non-blank. | Pass: `CurrentReadModelPublisher` raises at construction when given a blank payload hash column name. |
| Publisher payload hash columns are not lifecycle columns. | Pass: `CurrentReadModelPublisher` raises at construction when the payload hash column is a serving lifecycle column. |
| Publisher payload hash columns are not identity columns. | Pass: `CurrentReadModelPublisher` raises at construction when the payload hash column overlaps a stable identity column. |
| Publisher payload columns are tuples. | Pass: `CurrentReadModelPublisher` raises at construction when given list-shaped payload columns. |
| Publisher payload column entries are strings. | Pass: `CurrentReadModelPublisher` raises at construction when given a numeric payload column entry. |
| Publisher payload column entries are non-blank. | Pass: `CurrentReadModelPublisher` raises at construction when given a blank payload column entry. |
| Publisher payload column entries are unique. | Pass: `CurrentReadModelPublisher` raises at construction when given duplicate payload column entries. |
| Publisher payload columns exclude the payload hash column. | Pass: `CurrentReadModelPublisher` raises at construction when explicit payload columns include the configured hash column. |
| Publisher payload columns exclude lifecycle columns. | Pass: `CurrentReadModelPublisher` raises at construction when explicit payload columns include a serving lifecycle column. |
| Publisher explicit payload columns exist in rows. | Pass: `CurrentReadModelPublisher.row_payload_hash()` raises when a declared explicit payload column is missing from the row. |
| Publisher missing payload columns use dedicated row-shape errors. | Pass: `CurrentReadModelPublisher.row_payload_hash()` raises `current read model row missing payload columns` instead of raw `KeyError`. |
| Publisher changed rows contain identity columns. | Pass: `CurrentReadModelPublisher.changed_rows()` raises a dedicated missing-identity error before payload hashing when a row lacks a stable identity column. |
| Publisher changed-row batches have unique identities. | Pass: `CurrentReadModelPublisher.changed_rows()` raises when two rows in one batch share the same stable identity tuple. |
| Publisher changed rows are mappings. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model row must be mapping` before column validation when a row is list-shaped. |
| Publisher existing hashes are mappings. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model existing hashes must be mapping` before hash lookup when `existing_hashes` is list-shaped. |
| Publisher existing hash identities are tuples. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model existing hash identities must be tuples` before hash lookup when an `existing_hashes` key is string-shaped. |
| Publisher existing hash identity arity matches identity columns. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model existing hash identity arity must match identity columns` before hash lookup when an `existing_hashes` key has the wrong tuple length. |
| Publisher existing hash values are strings or null. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model existing hash values must be strings or None` before hash lookup when an `existing_hashes` value is numeric. |
| Publisher existing hash values are canonical payload hashes. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model existing hash values must be sha256 payload hashes` before hash lookup when an `existing_hashes` value is a malformed string. |
| Publisher changed rows use string row columns. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model row has non-string columns` before write preparation when a row contains a non-string key. |
| Publisher changed rows have non-null identity values. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model row has null identity values` before payload hashing when a stable identity value is `None`. |
| Publisher changed rows have non-blank identity values. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model row has blank identity values` before payload hashing when a stable identity value is blank. |
| Publisher changed-row batches are sequences. | Pass: `CurrentReadModelPublisher.changed_rows()` raises `current read model rows must be sequence` before row validation when `rows` is scalar, mapping-shaped, or string-shaped. |
| Stable payload hash inputs are mappings. | Pass: `stable_current_payload_hash()` raises `current payload hash payload must be mapping` before dict coercion when payload input is scalar, list-of-pairs-shaped, or string-shaped. |
| Stable payload hash keys are strings. | Pass: `stable_current_payload_hash()` raises `current payload hash payload has non-string keys` before JSON normalization when payload input contains a numeric key. |
| Nested stable payload hash keys are strings. | Pass: `stable_current_payload_hash()` raises `current payload hash payload has non-string keys` before JSON normalization when a nested factor snapshot contains a numeric key. |
| Stable payload hash values reject generic isoformat objects. | Pass: `stable_current_payload_hash()` raises `current payload hash payload has unsupported values` before generic ISO formatting when payload input contains an arbitrary object with `isoformat()`. |
| Stable payload hash numbers are finite. | Pass: `stable_current_payload_hash()` raises `current payload hash payload has non-finite numbers` before JSON serialization or Decimal stringification when payload input contains float or Decimal NaN/Infinity. |
| Stable payload hash containers are ordered. | Pass: `stable_current_payload_hash()` raises `current payload hash payload has unsupported containers` before JSON normalization when payload input contains set or frozenset values. |
| CEX board payload hashing uses the shared current payload hash contract. | Pass: `_board_payload_hash()` raises `current payload hash payload has non-string keys` when `score_components` contains a non-string key, and the repository no longer defines a local stable payload hash normalizer. |
| Runtime package imports avoid scheduler side effects. | Pass: importing and running the CEX OI radar board worker test module succeeds after `parallax.app.runtime.__init__` stops importing `WorkerScheduler` during package initialization. |
| CEX detail payload hashing uses the shared current payload hash contract. | Pass: `_detail_payload_hash()` raises `current payload hash payload has non-string keys` when `level_bands` contains a non-string key, and the repository no longer defines local stable payload hash or generic JSON normalizer functions. |
| CEX detail source refs keep strict mapping keys. | Pass: `_detail_payload_hash()` raises `current payload hash payload has non-string keys` when `source_refs` contains a non-string key before metadata filtering can stringify it. |
| Token profile current payload hashing uses the shared current payload hash contract. | Pass: `TokenProfileCurrentRepository.upsert_current()` raises `current payload hash payload has non-string keys` when `source_payload_json` contains a non-string key before JSONB sanitation can stringify it, and the repository no longer defines a local stable payload hash normalizer. |
| News source-quality payload hashing uses the shared current payload hash contract. | Pass: `NewsRepository.replace_source_quality_rows()` raises `current payload hash payload has non-string keys` when `diagnostics_json` contains a non-string key, and the repository no longer defines a local stable payload hash normalizer. |
| News page-row payload hashing uses the shared current payload hash contract. | Pass: `NewsRepository.replace_page_rows_for_items()` raises `current payload hash payload has non-string keys` when `story` contains a non-string key before serving-row insert, and the repository no longer defines a local stable payload hash normalizer. |
| Narrative admission payload hashing uses the shared current payload hash contract. | Pass: `admission_payload_hash()` raises `current payload hash payload has non-string keys` when the admission payload contains a non-string key, and the repository no longer defines a local stable payload hash normalizer. |
| Narrative admission hash unwrapping is Jsonb-only. | Pass: `admission_payload_hash()` raises `current payload hash payload has unsupported values` when an arbitrary object exposes an `obj` attribute but is not a real `Jsonb` adapter. |
| Macro daily brief payload hashing uses the shared current payload hash contract. | Pass: `_macro_daily_brief_payload_hash()` raises `current payload hash payload has non-string keys` when a current brief payload contains a non-string key, and the function no longer hashes through `postgres_safe_json()` or generic `default=str` conversion. |
| Macro view snapshot payload hashing uses the shared current payload hash contract. | Pass: `_macro_snapshot_payload_hash()` raises `current payload hash payload has non-string keys` when `features_json` contains a non-string key, and the function no longer hashes through `postgres_safe_json()` or generic `default=str` conversion. |
| Macro observation series row payload hashing uses the shared current payload hash contract. | Pass: `macro_series_current_row_payload_hash()` raises `current payload hash payload has non-string keys` when current row `raw_payload_json` contains a non-string key, and the function no longer hashes series rows through the local `_stable_payload_hash()` compatibility normalizer. |
| Token Radar stable payload hashing uses the shared current payload hash contract. | Pass: `stable_token_radar_payload_hash()` raises shared current payload validation errors when Token Radar payloads contain non-string keys or unordered containers, while still ignoring the product-ephemeral factor snapshot `computed_at_ms` path. |
| Shared current payload hashing stays outside runtime imports. | Pass: `tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime` passes after domain repositories import the shared hash contract from `parallax.platform.current_read_model_payload_hash` instead of `parallax.app.runtime.current_read_model_publisher`. |
| Worker manifest imports are explicit. | Pass: importing `parallax.app.runtime.worker_manifest` in a clean process succeeds even after removing an incidental `importlib.util` package attribute. |
| Root visual artifacts are absent. | Pass: architecture harness rejects loose root-level PNG/JPG/WEBP/GIF verification artifacts. |
| Worker table declarations are unique. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares the same table twice inside one table-declaration field. |
| Worker table declarations are non-blank. | Pass: `_validate_worker_manifests()` raises when a patched manifest declares a blank table name in a table-declaration field. |
| Delegated handoff artifacts are task-bound. | Pass: validator rejects existing delegated handoff files that name another feature/task/mode or stale report-validation command. |
| Delegated report mode matches handoff mode. | Pass: validator rejects report artifacts whose `Mode:` differs from the owning handoff mode. |
| Factory lanes are bounded. | Pass: validator rejects task `Factory lane` values outside the six operating-model lanes. |
| Analyze gate statuses are bounded. | Pass: validator rejects plan Analyze Gate results that do not begin with `Pass:` or `Blocked:`. |
| Failing-test-first evidence is covered. | Pass: validator rejects completed tasks whose failing-test test file paths never appear in successful command evidence. |
| Generated CLI docs are freshness-checked. | Pass: `check-all` runs `scripts/regen_cli_help.py --check` before integration gates. |
| Generated score-version docs are freshness-checked. | Pass: `check-all` runs `scripts/regen_score_versions.py --check` before integration gates. |
| Generated WebSocket docs are freshness-checked. | Pass: `check-all` runs `scripts/regen_ws_protocol.py --check` before integration gates. |
| Non-DB generated docs are freshness-checked from the source map. | Pass: architecture tests derive generator scripts from `docs/generated/README.md` and require each non-DB generator to run with `--check` inside `check-all`. |
| Task-bound subagent reading evidence is executable. | Pass: subagent report validator rejects task-bound reports without task classification, root instructions, reading matrix, and task on-demand context evidence. |
| Public contracts are source-bound. | Pass: architecture tests compare CONTRACTS worker keys, agent lanes, WS payloads, and News route against current source. |
| Generated README source map is real. | Pass: architecture tests fail any README source-map row that names a missing generated file, generator script, or source path. |
| Active touch conflicts are path-aware. | Pass: validator rejects parent/child active touch overlaps when coordination names an unrelated target. |
| Frontend docs and skill are harness-bound. | Pass: frontend architecture tests compare docs/skill wording against CSS architecture constants and app navigation source. |
| Frontend boundary scans derive feature roots. | Pass: feature-boundary architecture tests fail stale hard-coded root lists and scan all current feature roots. |
| Frontend data ownership is executable. | Pass: `frontendDataOwnership.test.ts` blocks direct route/UI server-state references while keeping feature-owned hooks/controllers as the owning boundary. |
| Agent routers are source-aligned. | Pass: `test_agent_router_frontend_guardrails_match_css_harness` compares AGENTS/CLAUDE frontend guardrails with the CSS architecture harness. |
| Frontend verification skill carries data ownership. | Pass: `frontendDocContract.test.ts` compares the skill against `frontendDataOwnership.test.ts` primitives. |
| Architecture docs reference executable tests. | Pass: `test_architecture_doc_test_references_are_path_qualified_and_existing` rejects bare or missing enforcement test references. |
| Architecture module maps are source-complete. | Pass: `test_architecture_module_map_links_every_domain_architecture_doc` compares docs links against current domain architecture files. |
| Test taxonomy inventory is exact. | Pass: `test_architecture_tests_declare_harness_taxonomy` compares `docs/TESTING.md` rows against `tests/architecture`. |
| Generated WebSocket docs expose message kinds. | Pass: `test_generated_ws_protocol_documents_current_type_literals` compares generated WS docs against current `ws.py` type literals. |
| Open tech debt references are live. | Pass: `test_open_tech_debt_references_current_source_and_test_paths` checks open `docs/TECH_DEBT.md` source/test/doc repo-root paths and test functions against the current tree. |
| Open tech debt duplicate-symbol claims are live. | Pass: `test_open_tech_debt_duplicate_symbol_claims_match_current_sources` checks duplicate-symbol claims against cited source contents. |
| Governance rule checks avoid prose overfit. | Pass: `test_rule_ownership` and `test_routers_have_no_governance_phrases` split ownership from router-leak checks and use multi-anchor contracts. |
| Domain types are leaf nodes. | Pass: `test_domain_types_do_not_import_upward_layers` prevents types modules from hiding service/repository/runtime shims. |
| Domain interfaces stay runtime-free. | Pass: `test_domain_interfaces_do_not_import_runtime_modules` prevents public interfaces from re-exporting runtime orchestration. |

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_successful_make_check_all_evidence -q`
- AC2: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_filled_coordination_fields -q`
- AC3: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows -q`
- AC5: `make check-all`
- AC6: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined -q`
- AC7: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- AC8: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q`
- AC9: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q`
- AC10: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q`
- AC11: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC12: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC13: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q`
- AC14: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC15: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q`
- AC16: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- AC17: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- AC18: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- AC19: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q`
- AC20: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q`
- AC21: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q`
- AC22: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q`
- AC23: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q`
- AC24: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q`
- AC25: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q`
- AC26: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q`
- AC27: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q`
- AC28: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q`
- AC29: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q`
- AC30: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q`
- AC31: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q`
- AC32: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q`
- AC33: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q`
- AC34: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q`
- AC35: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q`
- AC36: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q`
- AC37: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q`
- AC38: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q`
- AC39: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q`
- AC40: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q`
- AC41: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q`
- AC42: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q`
- AC43: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q`
- AC44: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q`
- AC45: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence -q`
- AC46: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot -q`
- AC47: `uv run pytest tests/architecture/test_public_contracts_doc_alignment.py -q`
- AC48: `uv run pytest tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths -q`
- AC49: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination -q`
- AC50: `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts`
- AC51: `cd web && npm run test -- tests/architecture/featureBoundaries.test.ts`
- AC52: `cd web && npm run test -- tests/architecture/frontendDataOwnership.test.ts`
- AC53: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness -q`
- AC54: `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts`
- AC55: `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing -q`
- AC56: `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc -q`
- AC57: `uv run pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy -q`
- AC58: `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q`
- AC59: `uv run pytest tests/architecture/test_harness_structure.py::test_rule_ownership tests/architecture/test_harness_structure.py::test_routers_have_no_governance_phrases -q`
- AC60: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers -q`
- AC61: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules -q`
- AC62: `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources -q`
- AC63: `uv run pytest tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals -q`
- AC64: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot -q`
- AC65: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot -q`
- AC66: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots -q`
- AC67: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q`
- AC68: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines -q`
- AC69: `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification -q`
- AC70: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources -q`
- AC71: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract -q`
- AC72: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping -q`
- AC73: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers -q`
- AC74: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities -q`
- AC75: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries -q`
- AC76: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations -q`
- AC77: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- AC78: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns -q`
- AC79: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations -q`
- AC80: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- AC81: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables -q`
- AC82: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets -q`
- AC83: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth -q`
- AC84: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io -q`
- AC85: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q`
- AC86: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q`
- AC87: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q`
- AC88: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q`
- AC89: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q`
- AC90: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q`
- AC91: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q`
- AC92: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence -q`
- AC93: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts -q`
- AC94: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts -q`
- AC95: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys -q`
- AC96: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys -q`
- AC97: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys -q`
- AC98: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts -q`
- AC99: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence -q`
- AC100: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes -q`
- AC101: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities -q`
- AC102: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities -q`
- AC103: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules -q`
- AC104: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules -q`
- AC105: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names -q`
- AC106: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_domain_directories -q`
- AC107: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_raw_classification_values -q`
- AC108: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_boolean_provider_io_flags -q`
- AC109: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_contract_fields -q`
- AC110: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_contract_entries -q`
- AC111: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_columns -q`
- AC112: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_entries -q`
- AC113: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_worker_manifest_imports_in_clean_process_without_importlib_util_side_effect -q`
- AC114: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_malformed_read_model_identity_entries -q`
- AC115: `uv run pytest tests/architecture/test_harness_structure.py::test_repo_root_has_no_loose_visual_artifacts -q`
- AC116: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_queue_depth_tables -q`
- AC117: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_advisory_lock_keys -q`
- AC118: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_identity_fields -q`
- AC119: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_tables -q`
- AC120: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_columns -q`
- AC121: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- AC122: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column -q`
- AC123: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns -q`
- AC124: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns -q`
- AC125: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns -q`
- AC126: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column -q`
- AC127: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_payload_columns -q`
- AC128: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_hash_column -q`
- AC129: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_payload_hash_payload_columns -q`
- AC130: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_columns -q`
- AC131: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_identity_payload_hash_column -q`
- AC132: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q`
- AC133: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_dirty_targets -q`
- AC134: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_depth -q`
- AC135: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_health_tables -q`
- AC136: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane -q`
- AC137: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane -q`
- AC138: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_identity_column_before_payload_hashing -q`
- AC139: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_row_identities_in_batch -q`
- AC140: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q`
- AC141: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_row_columns_before_write_preparation -q`
- AC142: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_null_row_identity_values_before_hashing -q`
- AC143: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_row_identity_values_before_hashing -q`
- AC144: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_identity_columns -q`
- AC145: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_rows_before_column_validation -q`
- AC146: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_existing_hashes_before_hash_lookup -q`
- AC147: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_existing_hash_identity_keys_before_hash_lookup -q`
- AC148: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_wrong_arity_existing_hash_identity_keys_before_hash_lookup -q`
- AC149: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_existing_hash_values_before_hash_lookup -q`
- AC150: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_malformed_existing_hash_values_before_hash_lookup -q`
- AC151: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q`
- AC152: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads -q`
- AC153: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys -q`
- AC154: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys -q`
- AC155: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values -q`
- AC156: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers -q`
- AC157: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers -q`
- AC158: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys -q`
- AC159: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q`
- AC160: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys -q`
- AC161: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q`
- AC162: `uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys -q`
- AC163: `uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys -q`
- AC164: `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write -q`
- AC165: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys -q`
- AC166: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values -q`
- AC167: `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys -q`
- AC168: `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_snapshot_payload_hash_rejects_legacy_feature_keys -q`
- AC169: `uv run pytest tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys -q`
- AC170: `uv run pytest tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers -q`
- AC171: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime -q`
- AC172: `uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_dirty_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys -q`
- AC173: `uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_ignores_queue_lifecycle_fields -q`
- AC174: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_ignores_queue_lifecycle_fields -q`
- AC175: `uv run pytest tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py::test_dirty_payload_hash_excludes_queue_lifecycle_fields -q`
- AC176: `uv run pytest tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers -q`
- AC177: `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_target_coalesces_current_target tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes -q`
- AC178: `uv run pytest tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_doc_names_current_read_tool_contract -q`
- AC179: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_missing_current_file_and_touch_paths tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_removed_file_records_outside_current_touch_surface tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_current_glob_touch_paths_when_they_match -q`
- AC180: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_individual_gates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q`
- AC181: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface -q`
- AC182: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_all_active_features tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_any_failed_active_feature -q`
- AC183: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift -q`
- AC184: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_header_only_gate_tables -q`
- AC185: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_placeholder_gate_rows -q`
- AC186: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance -q`
- AC187: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unbounded_analyze_status tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q`
- AC188: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_must_be_markdown_heading_lines tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_requires_markdown_heading_lines -q`
- AC189: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_fenced_heading_tokens -q`
- AC190: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_tilde_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens -q`
- AC191: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_single_cell_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_single_cell_gate_rows -q`
- AC192: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_tables_without_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows -q`
- AC193: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_rows_before_separator tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_rows_before_separator -q`
- AC194: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_empty_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_empty_separator_rows -q`
- AC195: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_separator_arity_mismatch tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_row_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_separator_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_row_arity_mismatch -q`
- AC196: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_non_contiguous_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_contiguous_body_rows -q`
- AC197: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_wrong_clarification_header tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_wrong_clarification_header -q`
- AC198: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_ignores_non_canonical_tables tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables -q`
- AC199: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check -q`
- AC200: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_separator_rows -q`
- AC201: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_header_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_header_rows -q`
- AC202: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_unclosed_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unclosed_table_rows -q`
- AC203: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_doubled_boundary_pipes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_doubled_boundary_pipes -q`
- AC204: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_indented_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_indented_table_rows -q`
- AC205: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_clarification_gate_evidence_rejects_non_canonical_approval_dates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates -q`
- AC206: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_metadata_dates_require_canonical_real_dates -q`
- AC207: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_requires_all_canonical_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance -q`
- AC208: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_status_without_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_analyze_status_without_evidence -q`
- AC209: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_duplicate_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_duplicate_task_gate_compliance -q`
- AC210: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_split_table_blocks tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_split_task_gate_compliance -q`
- AC211: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_missing_check_all_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_spec_compliance tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_spec_compliance_rows -q`
- AC212: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_empty_spec_compliance -q`
- AC213: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_partial_spec_compliance -q`
- AC214: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_passing_coverage_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_coverage tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q`
- AC215: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q`
- AC216: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_numeric_skipped_test_count tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_skipped_count -q`
- AC217: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_count_inside_skipped_tests_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_skipped_count_outside_skipped_section -q`
- AC218: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_positive_skipped_test_count_with_freeform_table tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_positive_skipped_count_with_freeform_table -q`
- AC219: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_coverage_values tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_coverage_value -q`
- AC220: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence -q`
- AC221: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_command_shaped_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_prose_only_spec_compliance_evidence -q`
- AC222: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_fenced_e2e_golden_path -q`
- AC223: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_make_check_all_own_exit_code_zero tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_failed_check_all_before_helper_success -q`
- AC224: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC225: `uv run pytest tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate -q`
- AC226: `uv run pytest tests/architecture/test_harness_structure.py::test_makefile_pytest_targets_do_not_accept_empty_collections -q`
- AC227: `python -m pytest tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker -q`
- AC228: `python -m pytest tests/architecture/test_harness_structure.py::test_final_runtime_lanes_do_not_expose_skip_env_switches -q`
- AC229: `python -m pytest tests/architecture/test_harness_structure.py::test_contract_lane_has_no_duplicate_make_alias -q`
- AC230: `uv run pytest tests/architecture/test_test_lane_contracts.py tests/architecture/test_worker_runtime_contracts.py -q`
- AC231: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_validator_cli_fails_on_issues_without_check_flag -q`
- AC232: `python -m pytest tests/architecture/test_test_lane_contracts.py::test_coverage_report_does_not_hide_empty_source_files -q`
- AC233: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_title_substring_selectors -q`
- AC234: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_golden_skip_switch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_golden_skip_switch -q`
- AC235: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_command tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_command -q`
- AC236: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_unfenced_extra_verification_command tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_unfenced_extra_verification_command -q`
- AC237: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_unfenced_make_check_all tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_unfenced_make_check_all -q`
- AC238: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_multiple_check_all_exit_codes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_multiple_check_all_exit_codes -q`
- AC239: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_extra_verification_output_block tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_extra_verification_output_block -q`
- AC240: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_duplicate_verification_commands_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_duplicate_verification_commands_section -q`
- AC241: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_verification_template_keeps_completion_gate_outside_final_command_section -q`
- AC242: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_positive_skipped_count_with_placeholder_reason tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_positive_skipped_count_with_placeholder_reason -q`
- AC243: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_keeps_one_task_for_single_pr_work -q`
- AC244: `python -m pytest tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate tests/architecture/test_sdd_artifact_validator.py::test_validator_cli_rejects_legacy_check_flag tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_legacy_check_flag -q`
- AC245: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_non_verification_artifact_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q`
- AC246: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q`
- AC247: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_validator_issue_codes_are_registered_for_generated_lifecycle_index -q`
- AC248: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q`
- AC249: `python -m pytest tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate -q`
- AC250: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_tasks_with_final_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q`
- AC251: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_lanes_reject_loose_legacy_files -q`
- AC252: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_fenced_table_rows tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_spec_compliance_and_coverage_tables -q`
- AC253: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_fenced_task_sections tests/architecture/test_sdd_artifact_validator.py::test_tasks_must_live_inside_tasks_section -q`
- AC254: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_must_live_in_acceptance_section tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_live_in_acceptance_section tests/architecture/test_sdd_artifact_validator.py::test_spec_requires_at_least_one_acceptance_criterion -q`
- AC255: `python -m pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_acceptance_command_drift -q`
- AC256: `python -m pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_canonical_artifact_sections tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_rejects_acceptance_command_drift -q`

## Verification

Verification evidence lives in `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut/verification.md`.
