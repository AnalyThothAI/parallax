# Spec — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owner**: Codex
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Related**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `scripts/regen_sdd_work_index.py`

## Background

Parallax routes non-trivial coding-agent work through one SDD feature directory in `docs/WORKFLOW.md:7`.
The lane's canonical artifacts are `spec.md` in `docs/WORKFLOW.md:13`, `plan.md` in `docs/WORKFLOW.md:14`,
`tasks.md` in `docs/WORKFLOW.md:15`, and `verification.md` in `docs/WORKFLOW.md:16`.
Production work follows `spec -> clarify -> checklist -> plan -> tasks -> analyze -> implement -> verify`
in `docs/WORKFLOW.md:27`, and completion requires `make check-all` evidence in `docs/WORKFLOW.md:95`.
The generated index now renders a `Coordination Board` in `scripts/regen_sdd_work_index.py:86` and a
`Task Board` in `scripts/regen_sdd_work_index.py:117`.

Latest external SDD and agent-loop references reinforce the same direction: GitHub Spec Kit documents specify, plan, tasks, and implement commands plus clarify/checklist/analyze gates (https://github.com/github/spec-kit), OpenAI's agent evaluation docs emphasize reproducible evals and trace grading (https://platform.openai.com/docs/guides/agent-evals), Claude Code docs separate deterministic hooks and bounded subagents (https://code.claude.com/docs/en/agent-sdk/hooks, https://code.claude.com/docs/en/sub-agents), and GitHub Copilot task guidance emphasizes scoped task prompts for coding agents (https://docs.github.com/en/enterprise-cloud@latest/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks).

## Problem

The harness proves that SDD files exist and have lane-valid status strings, but it does not prove that the
records are truthful, coordinated, or useful for multi-agent execution. A completed record can say `Verified`
while its verification text admits that `make check-all` did not produce final evidence. Test architecture also
contains useful hard-cut tripwires mixed with brittle wording, source-shape, and exact SQL checks, so the harness
can both miss real process drift and block healthy refactors.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should old SDD compatibility lanes or retired planning trees remain supported? | No. The current `docs/sdd/` lane is the only planning lane. | qinghuan | 2026-06-09 |
| Should `Verified` ever allow partial `make check-all` evidence? | No. Use `Review`, `Blocked`, or `Superseded` until final evidence exists. | qinghuan | 2026-06-09 |
| Should brittle tests be deleted without replacement? | No. Hard-cut tripwires stay when they defend retired runtime surfaces, but behavior contracts replace accidental shape locks. | qinghuan | 2026-06-09 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| SDD truth must be executable. | A script fails false `Verified` records, missing gate sections, missing approval metadata, and incomplete task coordination fields. |
| Active work must be coordinatable. | The generated SDD index includes owner, worktree, branch, factory lanes, touch set, conflict set, blocked state, and verification status. |
| Test harness intent must be explicit. | Architecture tests classify permanent invariants, migration tripwires, behavior contracts, and generated hygiene. |
| Worker runtime constraints must be manifest-owned. | `WorkerManifest` carries each worker's runtime constraint classification, so architecture tests do not maintain a second worker inventory. |
| Worker classification fields must be enum-owned. | `WorkerManifest` validation rejects raw `lane`, `kind`, and `runtime_constraint` values that are not manifest enum members. |
| Worker identity fields must be non-blank. | `WorkerManifest` validation rejects blank `name`, `domain`, `factory`, and `worker_class` values before registries, settings, or docs harnesses consume them. |
| Worker domains must be source directories. | `WorkerManifest` validation rejects `domain` values that do not name an existing `src/parallax/domains/<domain>` source directory. |
| Worker factory modules must be source files. | `WorkerManifest` validation rejects `factory` values that do not name an existing `worker_factories/*.py` source file. |
| Worker runtime classes must be unique. | `WorkerManifest` validation rejects duplicate `worker_class` values before registry, factory, settings, or docs harnesses consume them. |
| Worker runtime class modules must exist. | `WorkerManifest` validation rejects `worker_class` values whose module path cannot be resolved before registry, factory, settings, or docs harnesses consume them. |
| Worker runtime class names must exist. | `WorkerManifest` validation rejects `worker_class` values whose class name is absent from the resolved module before registry, factory, settings, or docs harnesses consume them. |
| Worker start priorities must be non-negative. | `WorkerManifest` validation rejects negative `start_priority` values before scheduler, registry, settings, or docs harnesses consume them. |
| Worker start priorities must be integer bands. | `WorkerManifest` validation rejects non-integer `start_priority` values before scheduler, registry, settings, or docs harnesses consume them. |
| Idempotency evidence must be non-blank. | `WorkerManifest` validation rejects blank `idempotency_evidence` entries before lifecycle, ownership, or review harnesses consume them. |
| Idempotency evidence must be unique. | `WorkerManifest` validation rejects duplicate `idempotency_evidence` entries before lifecycle, ownership, or review harnesses consume them. |
| Provider I/O flags must be boolean. | `WorkerManifest` validation rejects non-boolean `uses_provider_io` values before provider-boundary or worker inventory harnesses consume them. |
| Worker identity fields must be strings. | `WorkerManifest` validation rejects non-string `name`, `domain`, `factory`, and `worker_class` values before blank checks, path checks, imports, registries, settings, or docs harnesses consume them. |
| Tuple-valued manifest contracts must be tuples. | `WorkerManifest` validation rejects list-shaped compatibility values for tuple contract fields before registry, factory, settings, or docs harnesses consume them. |
| Tuple-valued string contracts must contain strings. | `WorkerManifest` validation rejects non-string entries inside tuple-valued string contract fields before registry, factory, settings, or docs harnesses consume them. |
| Input contracts must be non-empty. | `WorkerManifest` validation rejects empty `input_contract` declarations before registry, factory, settings, or docs harnesses consume them. |
| Input contracts must be non-blank. | `WorkerManifest` validation rejects blank `input_contract` entries before registry, factory, settings, or docs harnesses consume them. |
| Input contracts must be unique. | `WorkerManifest` validation rejects duplicate `input_contract` entries before registry, factory, settings, or docs harnesses consume them. |
| Ordering keys must be non-empty. | `WorkerManifest` validation rejects empty `ordering_keys` declarations before lifecycle, idempotency, registry, factory, settings, or docs harnesses consume them. |
| Ordering keys must be non-blank. | `WorkerManifest` validation rejects blank `ordering_keys` entries before lifecycle, idempotency, registry, factory, settings, or docs harnesses consume them. |
| Ordering keys must be unique. | `WorkerManifest` validation rejects duplicate `ordering_keys` entries before lifecycle, idempotency, registry, factory, settings, or docs harnesses consume them. |
| Dirty-target consumers must declare dirty targets. | `WorkerManifest` validation rejects `DIRTY_TARGET_CONSUMER` manifests that omit `dirty_target_tables`. |
| Leased-job consumers must declare queue depth tables. | `WorkerManifest` validation rejects `LEASED_JOB_CONSUMER` manifests that omit `queue_depth_table`. |
| Bounded provider schedulers must declare provider I/O. | `WorkerManifest` validation rejects `BOUNDED_PROVIDER_SCHEDULER` manifests that do not set `uses_provider_io`. |
| Bounded provider schedulers must not declare dirty targets. | `WorkerManifest` validation rejects `BOUNDED_PROVIDER_SCHEDULER` manifests that declare `dirty_target_tables` before source adapters can masquerade as dirty-target consumers. |
| Bounded provider schedulers must not declare queue depth tables. | `WorkerManifest` validation rejects `BOUNDED_PROVIDER_SCHEDULER` manifests that declare `queue_depth_table` before source adapters can masquerade as leased queue consumers. |
| Bounded provider schedulers must not declare queue health tables. | `WorkerManifest` validation rejects `BOUNDED_PROVIDER_SCHEDULER` manifests that declare `queue_health_tables` before source adapters can masquerade as queue-health consumers. |
| Queue depth tables must be worker-owned. | `WorkerManifest` validation rejects `queue_depth_table` values absent from the same manifest's owned tables. |
| Queue depth tables must be control-plane-owned. | `WorkerManifest` validation rejects `queue_depth_table` values absent from the same manifest's `writes_control_plane` before facts or read models can masquerade as leased queues. |
| Queue health tables must be control-plane-owned. | `WorkerManifest` validation rejects `queue_health_tables` values absent from the same manifest's `writes_control_plane` before facts or read models can masquerade as queue-health surfaces. |
| Queue depth tables must be strings. | `WorkerManifest` validation rejects non-string `queue_depth_table` declarations before table hygiene and queue-health harnesses consume them. |
| Side-effect ledgers must belong to side-effect workers. | `WorkerManifest` validation rejects non-side-effect worker kinds that declare `side_effect_ledgers`. |
| Wake channels must be non-blank. | `WorkerManifest` validation rejects blank `wakes_on` and `wakes_out` channel declarations before listener/notify harnesses consume them. |
| Wake channels must be unique per worker field. | `WorkerManifest` validation rejects duplicate `wakes_on` and `wakes_out` entries before listener/notify harnesses consume them. |
| Advisory lock keys must be unique. | `WorkerManifest` validation rejects duplicate `advisory_lock_key` values before runtime lifecycle or worker inventory harnesses consume them. |
| Advisory lock keys must be non-blank. | `WorkerManifest` validation rejects blank `advisory_lock_key` values before runtime lifecycle or worker inventory harnesses consume them. |
| Advisory lock keys must be strings. | `WorkerManifest` validation rejects non-string `advisory_lock_key` declarations before lifecycle or advisory-lock harnesses consume them. |
| Worker Inventory docs must be manifest-owned. | Architecture tests derive worker class and read-model writer expectations from `WorkerManifest`, not from peer architecture-test constants. |
| Worker table ownership must be manifest-owned. | `WorkerManifest.owned_tables` exposes the canonical written-table set so harness checks do not reassemble ownership fields ad hoc. |
| Read-model writer mapping must be manifest-owned. | `read_model_writer_by_table()` exposes the unique read-model writer map from `WorkerManifest`, so docs harnesses do not derive their own registry. |
| Read-model writer uniqueness must be import-time validated. | `WorkerManifest` validation rejects duplicate read-model writers before docs or worker harnesses consume the manifest. |
| Read-model identity ownership must be import-time validated. | `WorkerManifest` validation rejects stable identity declarations for read models the worker does not write. |
| Read-model identity declarations must be unique. | `WorkerManifest` validation rejects duplicate stable identity entries for the same read model table in one worker. |
| Read-model identity entries must be tuples. | `WorkerManifest` validation rejects list-shaped current read-model identity entries before ownership or docs harnesses consume them. |
| Read-model identity entries must be pairs. | `WorkerManifest` validation rejects malformed current read-model identity entries before table/column unpacking can raise implementation-detail errors. |
| Read-model identity tables must be non-blank. | `WorkerManifest` validation rejects blank table names inside `current_read_model_identities` before ownership checks. |
| Read-model identity tables must be strings. | `WorkerManifest` validation rejects non-string table names inside `current_read_model_identities` before blank, duplicate, missing, or ownership checks consume them. |
| Read-model identity columns must be unique. | `WorkerManifest` validation and `CurrentReadModelPublisher` reject duplicate stable identity columns inside one read-model identity declaration. |
| Read-model identity columns must be non-empty. | `WorkerManifest` validation rejects current read-model identity declarations whose stable identity column list is empty. |
| Read-model identity columns must be non-blank. | `WorkerManifest` validation and `CurrentReadModelPublisher` reject blank stable identity column names. |
| Read-model identity columns must be tuples. | `WorkerManifest` validation rejects list-shaped stable identity column declarations before ownership or docs harnesses consume them. |
| Read-model identity columns must be strings. | `WorkerManifest` validation rejects non-string stable identity column names inside `current_read_model_identities` before blank, duplicate, forbidden-lifecycle, ownership, registry, settings, or worker inventory harnesses consume them. |
| Publisher identity columns must be tuples. | `CurrentReadModelPublisher` rejects list-shaped or scalar identity column declarations before stable identity validation can consume compatibility-shaped field lists. |
| Publisher identity columns must be strings. | `CurrentReadModelPublisher` rejects non-string stable identity column names before blank, duplicate, lifecycle-column, row-identity, or changed-row hashing logic consumes them. |
| Publisher payload hash columns must be strings. | `CurrentReadModelPublisher` rejects non-string payload hash column names before row hashing or changed-row writes can use them as serving-row keys. |
| Publisher payload hash columns must be non-blank. | `CurrentReadModelPublisher` rejects blank payload hash column names before changed-row writes can add empty serving-row keys. |
| Publisher payload hash columns must not be lifecycle columns. | `CurrentReadModelPublisher` rejects lifecycle payload hash column names before changed-row writes can overwrite runtime lifecycle fields. |
| Publisher payload hash columns must not be identity columns. | `CurrentReadModelPublisher` rejects payload hash column names that overlap stable identity columns before changed-row writes can overwrite serving identity keys. |
| Publisher payload columns must be tuples. | `CurrentReadModelPublisher` rejects list-shaped or scalar payload column declarations before row payload hashing can treat them as field lists. |
| Publisher payload column entries must be strings. | `CurrentReadModelPublisher` rejects non-string payload column entries before row payload hashing can look up invalid payload keys. |
| Publisher payload column entries must be non-blank. | `CurrentReadModelPublisher` rejects blank payload column entries before row payload hashing can look up empty payload keys. |
| Publisher payload column entries must be unique. | `CurrentReadModelPublisher` rejects duplicate payload column entries before row payload hashing can silently collapse repeated keys. |
| Publisher payload columns must not include the payload hash column. | `CurrentReadModelPublisher` rejects explicit payload column sets that include the configured payload hash column before row hashing can self-reference prior hashes. |
| Publisher payload columns must not include lifecycle columns. | `CurrentReadModelPublisher` rejects explicit lifecycle payload columns before row hashing can reintroduce run/generation/timestamp drift that the default payload path excludes. |
| Publisher explicit payload columns must exist in rows. | `CurrentReadModelPublisher` raises on missing explicit payload columns instead of hashing absent fields as `None`. |
| Publisher missing payload columns must use dedicated row-shape errors. | `CurrentReadModelPublisher.row_payload_hash()` reports missing explicit payload columns as publisher row-shape validation errors, not raw mapping `KeyError`s. |
| Publisher changed rows must contain identity columns. | `CurrentReadModelPublisher.changed_rows()` validates stable identity columns before payload hashing so query drift cannot surface as a payload `KeyError` or hash a row without serving identity. |
| Publisher changed-row batches must have unique identities. | `CurrentReadModelPublisher.changed_rows()` rejects duplicate stable identities inside one batch before a current read-model row can be prepared twice. |
| Publisher changed rows must be mappings. | `CurrentReadModelPublisher.changed_rows()` rejects list-shaped or scalar row values before column, identity, payload hash, or write-preparation validation can consume them. |
| Publisher existing hashes must be mappings. | `CurrentReadModelPublisher.changed_rows()` rejects list-shaped or scalar existing-hash maps before row, identity, payload hash, hash-lookup, or write-preparation validation can consume them. |
| Publisher existing hash identities must be tuples. | `CurrentReadModelPublisher.changed_rows()` rejects string or scalar existing-hash identity keys before hash lookup can miss unchanged rows and prepare unnecessary serving writes. |
| Publisher existing hash identity arity must match identity columns. | `CurrentReadModelPublisher.changed_rows()` rejects existing-hash identity tuples whose length differs from the publisher stable identity columns before hash lookup can miss unchanged rows. |
| Publisher existing hash values must be strings or null. | `CurrentReadModelPublisher.changed_rows()` rejects non-string, non-null existing-hash values before hash lookup can miss unchanged rows and prepare unnecessary serving writes. |
| Publisher existing hash values must be canonical payload hashes. | `CurrentReadModelPublisher.changed_rows()` rejects malformed existing-hash strings before hash lookup can miss unchanged rows and prepare unnecessary serving writes. |
| Publisher changed rows must use string row columns. | `CurrentReadModelPublisher.changed_rows()` rejects non-string row keys before payload hashing or changed-row write preparation can preserve compatibility-shaped mapping keys. |
| Publisher changed rows must have non-null identity values. | `CurrentReadModelPublisher.changed_rows()` rejects rows whose stable identity columns resolve to `None` before payload hashing or changed-row write preparation. |
| Publisher changed rows must have non-blank identity values. | `CurrentReadModelPublisher.changed_rows()` rejects rows whose stable identity string values are blank before payload hashing or changed-row write preparation. |
| Publisher changed-row batches must be sequences. | `CurrentReadModelPublisher.changed_rows()` rejects scalar, mapping, and string-shaped row batches before row, column, identity, payload hash, duplicate-identity, or write-preparation validation can consume compatibility-shaped containers. |
| Stable payload hash inputs must be mappings. | `stable_current_payload_hash()` rejects scalar, list-of-pairs, and string-shaped payloads before `dict(...)` coercion or JSON hashing can preserve compatibility-shaped payload containers. |
| Stable payload hash keys must be strings. | `stable_current_payload_hash()` rejects non-string top-level payload keys before `_json_ready()` can stringify compatibility-shaped mapping keys into serving hashes. |
| Nested stable payload hash keys must be strings. | `stable_current_payload_hash()` rejects non-string keys inside nested mapping payload values before `_json_ready()` can stringify compatibility-shaped factor snapshots or JSON payload blocks into serving hashes. |
| Stable payload hash values must reject generic isoformat objects. | `stable_current_payload_hash()` rejects arbitrary payload objects that merely expose `isoformat()` before `_json_ready()` can preserve compatibility-shaped values as serving hashes; only real date/time values may use ISO formatting. |
| Stable payload hash numbers must be finite. | `stable_current_payload_hash()` rejects float and Decimal NaN/Infinity values before JSON serialization or Decimal stringification can consume non-finite numbers as serving hashes. |
| Stable payload hash containers must be ordered. | `stable_current_payload_hash()` rejects set and frozenset payload values before `_json_ready()` can sort unordered compatibility containers into serving hashes. |
| CEX board payload hashing must use the shared current payload hash contract. | `CexOiRadarRepository` uses `stable_current_payload_hash()` for board publication hashes instead of a local compatibility normalizer that stringifies keys, sorts unordered containers, or accepts arbitrary `isoformat()` payload values. |
| Runtime package imports must avoid scheduler side effects. | `parallax.app.runtime.__init__` does not import `WorkerScheduler`, `worker_manifest`, or manifest validation while domain code imports shared runtime helpers such as `stable_current_payload_hash()`. |
| CEX detail payload hashing must use the shared current payload hash contract. | `CexDetailSnapshotRepository` uses `stable_current_payload_hash()` for detail snapshot hashes instead of a local compatibility normalizer or historical migration-golden numeric canonicalizer. |
| CEX detail source refs must keep strict mapping keys. | Detail snapshot source refs reject non-string keys before source-ref metadata filtering can stringify compatibility-shaped payload keys. |
| Token profile current payload hashing must use the shared current payload hash contract. | `TokenProfileCurrentRepository` uses `stable_current_payload_hash()` for current profile rows and validates JSON payload blocks before `postgres_safe_json()` can stringify compatibility-shaped keys. |
| News source-quality payload hashing must use the shared current payload hash contract. | `NewsRepository.replace_source_quality_rows()` uses `stable_current_payload_hash()` for `news_source_quality_rows` instead of a local compatibility normalizer that stringifies `diagnostics_json` keys. |
| News page-row payload hashing must use the shared current payload hash contract. | `NewsRepository.replace_page_rows_for_items()` uses `stable_current_payload_hash()` for `news_page_rows` instead of a local compatibility normalizer that stringifies story or payload-envelope keys. |
| Narrative admission payload hashing must use the shared current payload hash contract. | `admission_payload_hash()` uses `stable_current_payload_hash()` for `narrative_admissions` instead of a local compatibility normalizer that stringifies payload keys, sorts unordered containers, or stringifies unsupported values. |
| Narrative admission hash unwrapping must be Jsonb-only. | `admission_payload_hash()` unwraps only real `psycopg.types.json.Jsonb` values before shared current payload validation and rejects arbitrary objects that merely expose an `obj` attribute. |
| Macro daily brief payload hashing must use the shared current payload hash contract. | `_macro_daily_brief_payload_hash()` uses `stable_current_payload_hash()` for `macro_daily_briefs` instead of a local compatibility normalizer that routes current brief payloads through `postgres_safe_json()` and generic `default=str` conversion. |
| Macro view snapshot payload hashing must use the shared current payload hash contract. | `_macro_snapshot_payload_hash()` uses `stable_current_payload_hash()` for `macro_view_snapshots` instead of a local compatibility normalizer that routes current snapshot payloads through `postgres_safe_json()` and generic `default=str` conversion. |
| Macro observation series row payload hashing must use the shared current payload hash contract. | `macro_series_current_row_payload_hash()` uses `stable_current_payload_hash()` for `macro_observation_series_rows` instead of a local compatibility normalizer that stringifies current row `raw_payload_json` keys. |
| Token Radar stable payload hashing must use the shared current payload hash contract. | `stable_token_radar_payload_hash()` delegates final hash generation to `stable_current_payload_hash()` after Token Radar product canonicalization, rejecting compatibility-shaped non-string keys and unordered containers before current row, dirty target, or generation hashes consume them. |
| Shared current payload hashing must be outside runtime imports. | Domain repositories and services import `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; `CurrentReadModelPublisher` remains in runtime and reuses the platform helper without making repositories depend on `app.runtime`. |
| Worker manifest imports must be explicit. | `worker_manifest.py` imports `importlib.util` directly so clean-process manifest validation never depends on incidental package attribute side effects. |
| Root visual artifacts must be absent. | Architecture harness rejects loose visual verification files at the repository root so screenshots live only under owned artifact directories. |
| Worker table declarations must be unique. | `WorkerManifest` validation rejects duplicated table names inside each manifest table-declaration field before `owned_tables` dedupes them. |
| Worker table declarations must be non-blank. | `WorkerManifest` validation rejects blank table names in table-declaration fields and queue-depth table declarations. |
| SQL tests must avoid accidental alias/order coupling. | A query-contract helper checks tables, predicates, locks, params, and forbidden surfaces without pinning formatting. |
| Completion gates must be deterministic. | `make check-all` runs the SDD validator and stale generated index check. |
| Generated CLI docs must stay source-backed. | `make check-all` runs a non-mutating CLI help snapshot freshness check before integration gates. |
| Multi-agent development loops must be bounded. | Task records declare factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal. |
| Factory lanes must be deterministic tokens. | Task `Factory lane` values must match the six development-agent lane tokens from the operating model. |
| Analyze gates must be machine-statused. | Plan `Analyze Gate` result cells must use explicit `Pass:` or `Blocked:` status tokens. |
| Task dependencies must be executable. | Task dependency references are parsed, unresolved references fail validation, and unmet dependencies block dry-run dispatch. |
| Subagent return evidence must be executable. | Subagent reports are validated against the owning SDD task for scope adherence, changed-file claims, expected verification command, exit status, and secret hygiene before parent integration. |
| Task-bound subagent reports must prove reading discipline. | Subagent report validation requires task classification and required-reading evidence for task-bound reports, including root agent instructions, the task reading matrix, and task on-demand context paths. |
| Parent review outcome must be visible. | Task records expose subagent report and review result fields, and the generated Task Board surfaces review state including `needs-repair`. |
| Referenced report artifacts must be real. | Delegated task report paths are checked for existence and validated against the task-bound report contract by the SDD validator. |
| Completed task status must be evidenced. | A `[x]` task requires matching `verification.md` command evidence with exit code 0. |
| Failing-test-first metadata must be evidenced. | A `[x]` task requires successful verification evidence covering each test file path declared in `Failing test first`. |
| Machine fields must be exact tokens. | `Subagent handoff` accepts only the exact `not delegated` token or a repo path, not prose suffixes. |
| Delegated handoff artifacts must be real. | Delegated task handoff paths are checked for existence before dispatch or review. |
| Delegated handoff artifacts must be task-bound. | Existing delegated handoff files must name the current feature, task, mode, context packet, and report validator command. |
| Delegated report mode must come from handoff. | Report artifacts are validated with the handoff mode, so a report cannot self-upgrade from read-only to write-allowed. |
| Verified spec-compliance rows must be evidenced. | A `Verified` record cannot mark a compliance row complete unless command-shaped evidence in that row has exit code 0 in canonical evidence sections. |
| Worktree and branch metadata must be machine-valid. | `plan.md`, `tasks.md`, and `verification.md` must agree on either `codex/<slug>` with `.worktrees/<slug>` or exact `main`/`main` metadata. |
| Spec background must be source-backed. | Each `spec.md` Background claim block must cite an existing repo `path:line` or an external `https://` source. |
| Spec background citations must be semantically anchored. | When a Background claim uses backticked evidence tokens, the cited local lines must mention those tokens rather than merely exist. |
| Public contracts must be source-bound. | Architecture tests compare `docs/CONTRACTS.md` runtime lists and routes against manifest/settings/API source. |
| Generated README source maps must be real. | Architecture tests require `docs/generated/README.md` rows to name existing generated files, generator scripts, and source paths. |
| Generated WebSocket docs must expose source message kinds. | Architecture tests compare `docs/generated/ws-protocol.md` against current `type` literals in `src/parallax/app/surfaces/api/ws.py`. |
| Generated WebSocket docs must be freshness-checked. | `scripts/regen_ws_protocol.py --check` fails stale `docs/generated/ws-protocol.md`, and `make check-all` runs it before integration gates. |
| Generated score-version docs must be freshness-checked. | `scripts/regen_score_versions.py --check` fails stale `docs/generated/score-versions.md`, and `make check-all` runs it before integration gates. |
| Non-DB generated docs must be freshness-checked from the source map. | Architecture tests derive generator scripts from `docs/generated/README.md` and require each non-DB generator to run with `--check` inside `make check-all`. |
| Active touch conflicts must catch nested paths. | The SDD validator treats parent/child touch paths as overlaps and requires coordination that names the overlapping feature or path. |
| Frontend docs and skills must be harness-bound. | Frontend architecture tests compare `docs/FRONTEND.md` and the frontend verification skill against current CSS and navigation harness source. |
| Frontend feature-boundary scans must follow source roots. | Frontend architecture tests derive feature root names from `web/src/features` instead of a stale hard-coded subset. |
| Frontend data ownership must be executable. | Frontend architecture tests reject route modules or presentational UI that directly call server-state primitives instead of feature-owned hooks/controllers. |
| Agent routers must stay source-aligned. | Architecture tests compare AGENTS/CLAUDE frontend guardrails against current frontend CSS harness constants. |
| Frontend verification skills must carry current gates. | Architecture tests compare the frontend verification skill against the data-ownership harness, not only generic commands. |
| Architecture docs must reference executable tests. | Architecture tests reject bare or missing test references in `docs/ARCHITECTURE.md`. |
| Architecture module maps must be complete links. | Architecture tests compare the global module map against domain `ARCHITECTURE.md` files. |
| Test taxonomy inventory must be exact. | Architecture tests compare `docs/TESTING.md` architecture-test rows against the current `tests/architecture` files. |
| Open tech debt references must be live. | Architecture tests require open `docs/TECH_DEBT.md` source/test/doc references to be self-contained repo-root paths and resolve to current files and test functions. |
| Open tech debt duplicate-symbol claims must be source-backed. | Architecture tests require open `docs/TECH_DEBT.md` rows that claim a symbol is duplicated in source files to find that symbol in each cited source file. |
| Governance rule checks must not overfit prose. | Architecture tests use named rule anchors and separate ownership from router-leak checks. |
| Domain type modules must be leaf nodes. | Architecture tests reject `domains/*/types` imports from services, repositories, queries, read models, or runtime. |
| Domain interfaces must not import runtime. | Architecture tests reject `domains/*/interfaces.py` imports from runtime modules. |

## First principles

- Material facts and runtime behavior remain the source of product truth; SDD files are execution records, as stated in `docs/sdd/README.md:13`.
- Development-agent orchestration must stay separate from product LLM agents; `docs/AGENT_EXECUTION.md:3` owns the product runtime boundary.
- Hard cuts should delete compatibility surfaces, not wrap them; `docs/WORKFLOW.md:49` already requires isolated worktrees for non-trivial coding work.

## Goals

- G1. A `Verified` SDD artifact set with missing or contradicted `make check-all` evidence fails `uv run python scripts/validate_sdd_artifacts.py --check`.
- G2. A filled `tasks.md` without owner, touch set, conflict set, verification command, review owner, or task status fails the same validator.
- G3. `docs/generated/sdd-work-index.md` renders a coordination board with owner, worktree, branch, touch set, conflict set, blocked state, and verification status.
- G4. Tests that rely on SQL shape can use a query-contract helper to assert semantic SQL contracts without exact alias or whitespace coupling.
- G5. `make check-all` includes SDD artifact validation and generated index freshness so harness drift blocks completion.
- G6. Development-agent work follows an explicit factory/eval loop that separates deterministic constraints from on-demand context, keeps product LLM agents outside development lanes, and records repair signals.
- G7. Parent agents can generate a bounded subagent context packet from a validated active SDD task without hand-copying template prose.
- G8. Parent agents can generate a dry-run subagent handoff from a dispatchable active SDD task and the harness refuses completed tasks.
- G9. Task coordination fields are semantically validated, not accepted by mere presence.
- G10. `Verified` evidence is parsed from the canonical verification command block, not from old success snippets elsewhere in the file.
- G11. The generated SDD work index exposes task-level dispatch state, not only feature-level coordination.
- G12. Task dependencies are parsed as task references/ranges, unresolved references fail validation, and dispatch/index state blocks tasks whose dependencies are incomplete.
- G13. Subagent handoffs include a task-bound report contract, and returned reports are machine-validated against the owning SDD task before parent integration.
- G14. Parent review outcome is a structured task field and a generated Task Board state, not prose hidden in a handoff note.
- G15. SDD validation follows delegated `Subagent report` paths and fails missing or invalid report artifacts.
- G16. SDD validation fails any `[x]` task whose `Verification` command is not recorded in `verification.md` with exit code 0.
- G17. SDD validation treats machine-readable task tokens as exact values and rejects prose appended to `not delegated`.
- G18. SDD validation follows delegated `Subagent handoff` paths and fails missing handoff artifacts.
- G19. SDD validation rejects delegated `Subagent handoff` artifacts that are stale or bound to a different feature, task, mode, context packet, or report validator command.
- G20. SDD validation uses delegated handoff mode as the expected report mode, preventing returned reports from loosening their own scope after dispatch.
- G21. SDD validation rejects task `Factory lane` values outside the six development-agent lanes defined by the operating model.
- G22. SDD validation rejects plan `Analyze Gate` result cells that are `Fail:` or freeform prose instead of `Pass:` or `Blocked:` machine statuses.
- G23. SDD validation rejects `[x]` tasks whose `Failing test first` test file paths are absent from successful verification evidence.
- G24. `make check-all` rejects stale `docs/generated/cli-help.md` snapshots without running database-backed docs regeneration.
- G25. `docs/CONTRACTS.md` runtime worker keys, agent runtime lanes, WebSocket payloads, and News item route are checked against current source.
- G26. `docs/generated/README.md` source-map rows point at real generated files, generator scripts, and source paths.
- G27. Active SDD touch-set conflicts detect exact and parent/child path overlaps, and unrelated `coordinate with ...` prose does not suppress them.
- G28. `docs/FRONTEND.md` and `.agents/skills/parallax-frontend-verification/SKILL.md` are checked against current frontend CSS/navigation architecture source.
- G29. Frontend feature-boundary grep scans derive feature roots from `web/src/features`, so new feature roots are covered without regex updates.
- G30. Frontend data ownership is checked by a route/UI static architecture gate rather than a docs-only convention.
- G31. Root agent routers stay mirrored and source-aligned with frontend harness constants instead of preserving stale guardrail examples.
- G32. The repo-scoped frontend verification skill names the data-ownership harness and forbidden route/UI server-state primitives.
- G33. `docs/ARCHITECTURE.md` enforcement references are path-qualified and checked against real architecture test files/functions.
- G34. `docs/ARCHITECTURE.md` module map links every current domain `ARCHITECTURE.md` file and fails missing or stale links.
- G35. `docs/TESTING.md` architecture taxonomy rows are an exact inventory of current `tests/architecture/test_*.py` files.
- G36. Open `docs/TECH_DEBT.md` source/test/doc references are checked as self-contained repo-root paths against current files and test functions, so old follow-up breadcrumbs do not remain as active work.
- G37. Governance rule checks are split into ownership and router-leak gates, and use multi-anchor rule contracts rather than single verbatim phrase strings.
- G38. Domain `types/` modules are enforced as leaf value-object modules, so thin re-export shims from services cannot hide upward dependencies.
- G39. Domain `interfaces.py` modules remain cross-domain contracts and cannot re-export runtime orchestration modules.
- G40. Open `docs/TECH_DEBT.md` duplicate-symbol claims are checked against current source content, so resolved duplicated constants do not remain as active debt.
- G41. `docs/generated/ws-protocol.md` includes the current WebSocket message `type` literals from `src/parallax/app/surfaces/api/ws.py`, so generated public-surface docs do not stay class-only while runtime payloads are dict-shaped.
- G42. `make check-all` runs `scripts/regen_ws_protocol.py --check` before integration gates, so stale generated WebSocket docs cannot hide until optional/generated-doc integration checks.
- G43. `make check-all` runs `scripts/regen_score_versions.py --check` before integration gates, so stale score/version docs cannot hide until optional/generated-doc integration checks.
- G44. `make check-all` runs every non-DB generated-doc script named by `docs/generated/README.md` with `--check` before integration gates, so generated-doc freshness coverage is source-derived instead of one hard-coded assertion per file.
- G45. Task-bound subagent reports include task classification and required-reading evidence, so subagents cannot pass the parent integration harness with only generic findings and command output.
- G46. Local Background citations that claim backticked evidence must point at lines mentioning those evidence tokens, so stale line-number drift cannot satisfy SDD audit requirements.
- G47. Worker runtime constraint classifications live on `WorkerManifest`, so worker additions update the runtime inventory once instead of also updating a test-only classification map.
- G48. Worker Inventory documentation checks derive worker classes and read-model writer rows from `WorkerManifest`, so architecture tests cannot import peer architecture tests as hidden source registries.
- G49. Worker table ownership is exposed by `WorkerManifest.owned_tables`, so queue-health and Worker Inventory harness checks share the same source-owned ownership contract.
- G50. Read-model writer maps are exposed by `read_model_writer_by_table()`, so Worker Inventory docs checks do not rebuild a second writer registry from manifest internals.
- G51. Duplicate read-model writers fail during `WorkerManifest` validation, so a source manifest drift cannot wait until docs harness comparison to be caught.
- G52. Stable read-model identities must point only at tables written by the same worker manifest, so stale identity rows cannot survive as compatibility breadcrumbs.
- G53. Stable read-model identity declarations are unique per worker/table, so old identity definitions cannot coexist with the current one as ambiguous manifest truth.
- G54. Worker table-declaration fields reject duplicate table names before `owned_tables` deduplication, so stale compatibility breadcrumbs cannot hide inside the source manifest.
- G55. Stable read-model identity column lists reject duplicate columns at manifest validation and publisher construction time, so malformed current identity keys cannot be normalized accidentally.
- G56. Stable read-model identity declarations must include at least one identity column in the source manifest, so empty placeholder identities cannot satisfy harness checks.
- G57. Worker table declarations reject blank table names before ownership, queue health, or docs harnesses consume them, so empty placeholders cannot satisfy source-manifest truth.
- G58. Stable read-model identity column names reject blank strings at manifest validation and publisher construction time, so whitespace placeholders cannot become serving identity keys.
- G59. Stable read-model identity table names reject blank strings before ownership checks, so whitespace placeholders cannot be normalized into missing or unowned identity drift.
- G60. Dirty-target consumer runtime classification requires declared dirty target tables, so worker lifecycle semantics cannot drift away from queue ownership declarations.
- G61. Leased-job consumer runtime classification requires a declared queue depth table, so leased queue workers cannot lose their queue-health source identity.
- G62. Bounded provider scheduler runtime classification requires declared provider I/O, so provider-polling or streaming workers cannot lose their external-data boundary marker.
- G63. Queue depth table declarations require same-manifest table ownership, so queue-health harnesses cannot point at tables owned by another runtime.
- G64. Side-effect ledger declarations require a side-effect worker kind, so ordinary fact/projection workers cannot acquire ledger ownership by stale manifest breadcrumb.
- G65. Wake channel declarations reject blank strings, so listener and NOTIFY topology cannot include placeholder channels.
- G66. Wake channel declarations reject duplicate strings per worker field, so listener and NOTIFY topology cannot hide stale repeated channels.
- G67. Advisory lock declarations reject duplicate keys, so unrelated workers cannot silently share a long-lived single-writer lock boundary.
- G68. Advisory lock declarations reject blank keys, so lifecycle code cannot inherit a whitespace placeholder as a lock boundary.
- G69. Worker identity declarations reject blank fields, so registry, factory, settings, and docs harnesses cannot consume anonymous or unresolvable workers.
- G70. Idempotency evidence declarations reject blank strings, so workers cannot satisfy review and lifecycle gates with placeholder evidence.
- G71. Input contract declarations require at least one entry, so workers cannot enter registry, factory, settings, or docs harnesses without a declared input boundary.
- G72. Input contract declarations reject blank entries, so workers cannot satisfy input-boundary review with whitespace placeholders.
- G73. Ordering-key declarations require at least one entry, so workers cannot enter lifecycle, idempotency, registry, factory, settings, or docs harnesses without a declared processing order boundary.
- G74. Ordering-key declarations reject blank entries, so workers cannot satisfy ordering and idempotency review with whitespace placeholders.
- G75. Ordering-key declarations reject duplicate entries, so workers cannot satisfy ordering and idempotency review with repeated placeholders.
- G76. Input contract declarations reject duplicate entries, so workers cannot satisfy input-boundary review with repeated placeholders.
- G77. Idempotency evidence declarations reject duplicate entries, so workers cannot satisfy lifecycle and review gates with repeated evidence placeholders.
- G78. Worker runtime class declarations reject duplicate classes, so registry, factory, settings, and docs harnesses cannot silently map two manifest workers onto one runtime implementation boundary.
- G79. Worker start-priority declarations reject negative values, so scheduler ordering cannot silently place a worker before the manifest's non-negative runtime startup band.
- G80. Worker start-priority declarations reject non-integer values, so scheduler ordering remains an explicit integer band rather than an implicit fractional convention.
- G81. Worker factory declarations reject missing source files, so registry and docs harnesses cannot preserve a worker that no worker factory can instantiate.
- G82. Worker runtime class declarations reject missing modules, so registry and docs harnesses cannot preserve a worker whose runtime implementation path cannot resolve.
- G83. Worker runtime class declarations reject missing class names, so registry and docs harnesses cannot preserve stale symbols inside otherwise valid runtime modules.
- G84. Worker domain declarations reject missing source directories, so registry and docs harnesses cannot preserve a worker owned by a non-existent bounded context.
- G85. Worker classification declarations reject raw string values, so scheduler, docs, and lifecycle harnesses cannot silently accept compatibility-shaped values outside the manifest enum boundary.
- G86. Provider I/O declarations reject truthy non-boolean values, so provider-boundary harnesses cannot silently accept compatibility-shaped flags.
- G87. Tuple-valued manifest declarations reject list-shaped compatibility values, so registry and docs harnesses consume immutable source-truth contract fields.
- G88. Tuple-valued string manifest declarations reject non-string entries, so blank, duplicate, ownership, and wake-channel checks fail with manifest errors instead of implementation-detail attribute errors.
- G89. Stable read-model identity column declarations reject list-shaped compatibility values, so serving identity checks consume immutable column tuples.
- G90. Stable read-model identity entries reject list-shaped compatibility values, so serving identity table/column pairs remain immutable manifest source truth.
- G91. Worker manifest module imports declare `importlib.util` directly, so source-owned manifest validation survives clean-process imports without depending on prior import side effects.
- G92. Stable read-model identity entries reject malformed arity, so manifest validation owns the table/column pair shape instead of leaking Python unpacking errors.
- G93. Root-level visual verification artifacts are rejected, so old screenshots cannot remain as loose project files outside owned artifact directories.
- G94. Queue depth table declarations reject non-string values, so queue-health table hygiene fails with manifest errors instead of implementation-detail attribute errors.
- G95. Advisory lock declarations reject non-string values, so lifecycle lock hygiene fails with manifest errors instead of implementation-detail attribute errors.
- G96. Worker identity field declarations reject non-string values, so registry and source-path validation fail with manifest errors instead of implementation-detail attribute errors.
- G97. Current read-model identity table declarations reject non-string values, so stable serving identity checks fail with manifest errors instead of implementation-detail attribute errors.
- G98. Current read-model identity column declarations reject non-string values, so stable serving identity checks fail with manifest errors instead of implementation-detail attribute errors.
- G99. Current read-model publisher identity columns reject non-string values, so direct publisher construction fails with contract errors instead of implementation-detail attribute errors.
- G100. Current read-model publisher payload hash column declarations reject non-string values, so changed-row hashing cannot silently write serving rows with invalid hash keys.
- G101. Current read-model publisher payload column declarations reject non-tuple values, so payload hashing cannot silently iterate compatibility lists or scalar strings.
- G102. Current read-model publisher payload column entries reject non-string values, so payload hashing cannot silently look up invalid payload keys.
- G103. Current read-model publisher payload column entries reject blank values, so payload hashing cannot silently look up empty payload keys.
- G104. Current read-model publisher payload hash column declarations reject blank values, so changed-row writes cannot silently add empty serving-row keys.
- G105. Current read-model publisher payload column entries reject duplicate values, so payload hashing cannot silently collapse repeated payload keys.
- G106. Current read-model publisher payload hash column declarations reject lifecycle column names, so changed-row writes cannot overwrite runtime lifecycle fields.
- G107. Current read-model publisher payload column declarations reject the configured payload hash column, so explicit payload hashing cannot self-reference prior hashes.
- G108. Current read-model publisher payload column declarations reject lifecycle column names, so explicit payload hashing cannot reintroduce run/generation/timestamp drift.
- G109. Current read-model publisher payload hash column declarations reject stable identity column names, so changed-row writes cannot overwrite serving identity keys.
- G110. Current read-model publisher explicit payload hashing requires declared payload keys to exist in each row, so query drift cannot silently hash missing fields as null.
- G111. Bounded provider scheduler runtime classification rejects dirty-target table declarations, so provider source adapters cannot silently acquire dirty-target consumer semantics.
- G112. Bounded provider scheduler runtime classification rejects queue-depth table declarations, so provider source adapters cannot silently acquire leased queue consumer semantics.
- G113. Bounded provider scheduler runtime classification rejects queue-health table declarations, so provider source adapters cannot silently acquire queue-health consumer semantics.
- G114. Queue-depth table declarations require control-plane ownership, so fact and read-model tables cannot silently masquerade as leased queues.
- G115. Explicit queue-health table declarations require control-plane ownership, so fact and read-model tables cannot silently masquerade as queue-health surfaces.
- G116. Current read-model changed-row publishing validates stable identity columns before payload hashing, so query drift cannot produce serving writes without identity keys or opaque payload `KeyError` failures.
- G117. Current read-model changed-row publishing rejects duplicate stable row identities inside one batch, so a projection query cannot prepare multiple writes for one current serving row.
- G118. Explicit current-read-model payload hashing reports missing declared payload keys as row-shape validation errors, so query drift does not leak opaque mapping errors into harness evidence.
- G119. Current read-model changed-row publishing rejects non-string row columns before hashing or write preparation, so DB row-shape drift cannot survive as compatibility-shaped serving payload keys.
- G120. Current read-model changed-row publishing rejects null stable identity values before hashing or write preparation, so absent product/window keys cannot become current serving identities.
- G121. Current read-model changed-row publishing rejects blank stable identity string values before hashing or write preparation, so whitespace placeholders cannot become current serving identities.
- G122. Current read-model publisher identity column declarations reject list-shaped compatibility values, so row identity checks consume immutable column tuples.
- G123. Current read-model changed-row publishing rejects non-mapping row values before column, identity, hash, or write preparation checks consume compatibility-shaped row containers.
- G124. Current read-model changed-row publishing rejects non-mapping existing-hash indexes before row validation, hash lookup, or write preparation can consume compatibility-shaped unchanged-row state.
- G125. Current read-model changed-row publishing rejects non-tuple existing-hash identity keys before hash lookup can miss unchanged rows and reprepare current serving writes.
- G126. Current read-model changed-row publishing rejects wrong-arity existing-hash identity tuples before hash lookup can miss unchanged rows and reprepare current serving writes.
- G127. Current read-model changed-row publishing rejects non-string, non-null existing-hash values before hash lookup can miss unchanged rows and reprepare current serving writes.
- G128. Current read-model changed-row publishing rejects malformed existing-hash strings before hash lookup can miss unchanged rows and reprepare current serving writes.
- G129. Current read-model changed-row publishing rejects scalar, mapping, and string-shaped row batches before row validation can split compatibility containers into fake row values.
- G130. Stable current payload hashing rejects scalar, list-of-pairs, and string-shaped payloads before `dict(...)` coercion can turn compatibility containers into serving hashes.
- G131. Stable current payload hashing rejects non-string payload keys before JSON normalization can stringify compatibility-shaped mapping keys into serving hashes.
- G132. Stable current payload hashing rejects non-string keys inside nested mapping payload values before JSON normalization can stringify compatibility-shaped factor snapshots into serving hashes.
- G133. Stable current payload hashing rejects arbitrary `isoformat()` objects before JSON normalization can turn compatibility-shaped payload values into serving hashes.
- G134. Stable current payload hashing rejects non-finite float and Decimal payload values before JSON serialization or Decimal stringification can consume them as serving hashes.
- G135. Stable current payload hashing rejects unordered set and frozenset payload containers before JSON normalization can sort compatibility-shaped values into serving hashes.
- G136. CEX OI radar board publication hashing uses the shared stable current payload hash contract instead of a local compatibility normalizer.
- G137. Runtime package initialization stays side-effect-light so domain imports of shared runtime helpers do not trigger scheduler import, worker manifest validation, or worker class import cycles.
- G138. CEX detail snapshot hashing uses the shared stable current payload hash contract instead of a local compatibility normalizer or migration-golden numeric canonicalizer.
- G139. CEX detail snapshot source-ref filtering rejects non-string source-ref keys before metadata filtering can stringify compatibility-shaped payload keys.

## Non-goals

- N1. This does not add a product LLM agent runtime, background agent task queue, or shared tool loop.
- N2. This does not preserve legacy planning-lane compatibility.
- N3. This does not rewrite every existing SQL test; it establishes the harness and converts the currently blocking obsolete macro contract.

## Target architecture

The SDD lane becomes an executable control plane for development work. A validator parses feature records,
emits explicit issue codes, and exits non-zero when active/completed records violate gate semantics. The generated
work index becomes a compact coordination board for parent agents and subagents, including bounded factory lanes.
Test taxonomy is documented and enforced so string tripwires are deliberate, expiring safeguards rather than
accidental design locks.

## Conceptual data flow

```text
SDD records -> validate_sdd_artifacts -> regen_sdd_work_index -> make check-all
      |                    |                       |
      |                    v                       v
      +------------> issue codes ------------> coordination board
```

The new arrows are harness-only and do not affect runtime product data flow.

## Core models

- `SddFeature`: feature slug, lane, artifact paths, status values, owner, branch, worktree, approval metadata,
  touch set, conflict set, factory lanes, verification status, blocked reason, and issue codes.
- `SddIssue`: code, severity, path, and message for deterministic gate failures.
- `SqlContract`: required tables, forbidden tables, required predicates, forbidden fragments, required locks, and
  expected params.

## Interface contracts

- CLI: `uv run python scripts/validate_sdd_artifacts.py --check` exits 0 when all SDD records satisfy the executable harness and exits 1 with issue lines otherwise.
- CLI: `uv run python scripts/regen_sdd_work_index.py --check` fails when `docs/generated/sdd-work-index.md` is stale.
- CLI: `uv run python scripts/build_agent_context_packet.py --feature <slug> --task <number> --mode <mode>` prints a bounded subagent context packet from active SDD task metadata.
- CLI: `uv run python scripts/dispatch_sdd_task.py --feature <slug> --task <number> --mode <mode>` prints a dry-run handoff prompt and refuses completed, non-dispatchable, or dependency-blocked tasks.
- CLI: `uv run python scripts/validate_subagent_report.py --feature <slug> --task <number> --mode <mode> --report <report.md>` validates a returned subagent report against the owning SDD task before parent integration.
- Test helper: `tests.support.query_contract.assert_query_contract(sql, ...)` raises `AssertionError` with contract-specific messages.

## Acceptance criteria

- AC1. WHEN a completed feature is marked `Verified` without full successful `make check-all` evidence THEN the validator SHALL exit non-zero and report a `verified-missing-check-all` or `verified-contradicts-evidence` issue.
- AC2. WHEN a feature task omits owner/touch/conflict/verification/review/status fields THEN the validator SHALL exit non-zero and report a task coordination issue.
- AC3. WHEN the SDD index is regenerated THEN it SHALL include a coordination board with owner, worktree, branch, factory lanes, touch set, conflict set, blocked state, verification status, and flags.
- AC4. WHEN a SQL unit test uses the query-contract helper THEN it SHALL be able to assert required/forbidden tables and predicates without depending on alias names or whitespace.
- AC5. WHEN `make check-all` runs THEN SDD artifact validation and generated index freshness SHALL be part of the deterministic gate.
- AC6. WHEN task records are created or updated THEN each task SHALL declare factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal; missing fields SHALL report `task-missing-agent-loop-fields`.
- AC7. WHEN a parent agent prepares a subagent handoff THEN the context packet CLI SHALL read a validated active SDD task and output mode, factory lane, owned scope, conflict scope, deterministic constraints, on-demand context, kill/defer criteria, eval/repair signal, verification evidence, redactions, and the product-agent boundary.
- AC8. WHEN a parent agent dispatches a task dry-run THEN the dispatcher SHALL output a handoff prompt containing the generated context packet, and SHALL refuse `[x]` completed tasks.
- AC9. WHEN task records contain non-path file/touch fields, malformed conflict rules, non-test failing-test-first values, non-command verification values, or invalid task statuses THEN the validator SHALL report `task-invalid-coordination-fields`.
- AC10. WHEN a completed SDD record is marked `Verified` THEN the validator SHALL require the `## Verification commands` fenced block to contain the single successful `make check-all` evidence and SHALL reject stale success blocks or unexplained skipped tests.
- AC11. WHEN `docs/generated/sdd-work-index.md` is regenerated THEN it SHALL include a `Task Board` with one row per SDD task showing task status, dispatch state, factory lane, owner, dependency, touch set, conflict set, and verification command.
- AC12. WHEN a task references missing dependency task numbers or a dispatchable task depends on incomplete tasks THEN the validator SHALL report `task-invalid-dependencies` for unresolved references, the dispatcher SHALL refuse the task, and the generated `Task Board` SHALL show `blocked-by-dependencies`.
- AC13. WHEN a subagent report lacks required report sections, lists changed files outside the task touch set, overlaps the conflict set, runs a verification command different from the task command, or records a non-zero exit code THEN the report validator SHALL fail, and generated handoffs SHALL instruct the parent to run that task-bound validator before integration.
- AC14. WHEN a task is delegated or reviewed THEN `tasks.md` SHALL contain `Subagent report` and `Review result`, the validator SHALL reject missing or inconsistent review fields, and the generated `Task Board` SHALL expose review result and `needs-repair` dispatch state.
- AC15. WHEN a delegated task references a `Subagent report` path THEN the SDD validator SHALL require that file to exist and pass the same task-bound subagent report validator.
- AC16. WHEN a task is marked `[x]` THEN its `Verification` command SHALL appear in `verification.md` with exit code 0, otherwise the validator SHALL report `task-complete-missing-verification-evidence`.
- AC17. WHEN `Subagent handoff` starts with `not delegated` but includes extra prose THEN the validator SHALL reject it as `task-invalid-review-fields`; rationale belongs in deterministic constraints, implementation, or verification evidence.
- AC18. WHEN a delegated task references a `Subagent handoff` path THEN the SDD validator SHALL require that file to exist and report `task-missing-subagent-handoff-artifact` when it does not.
- AC19. WHEN one SDD feature has mixed `Status` values across `spec.md`, `plan.md`, `tasks.md`, and `verification.md` THEN the validator SHALL report `artifact-status-mismatch` before any lifecycle transition is trusted.
- AC20. WHEN a `Superseded` artifact only mentions a successor in prose, omits `**Superseded by**`, names a non-path value, or names a missing path THEN the validator SHALL report `superseded-missing-successor`.
- AC21. WHEN an SDD feature directory contains any file or subdirectory besides `spec.md`, `plan.md`, `tasks.md`, and `verification.md` THEN the validator SHALL report `unexpected-artifact`; historical screenshots, mockups, logs, and notes SHALL be removed from feature directories.
- AC22. WHEN a task is marked `[x]` while any declared dependency task is missing or not `[x]` THEN the validator SHALL report `task-invalid-dependencies`; completion order is evidence, not prose.
- AC23. WHEN a completed task's `Verification` command appears only outside `## Verification commands` and `## Other commands run` fenced blocks THEN the validator SHALL report `task-complete-missing-verification-evidence`.
- AC24. WHEN an artifact is `Superseded` but lacks required approval/execution metadata THEN the validator SHALL still report `missing-approval-metadata`; superseded status only skips content-section gates, not metadata truth.
- AC25. WHEN a `Superseded` feature has a legacy checkbox-only `tasks.md` with no structured `### Task` sections THEN the validator SHALL report `task-missing-coordination-fields`.
- AC26. WHEN artifacts in the same `Superseded` feature declare different `Superseded by` paths THEN the validator SHALL report `superseded-successor-mismatch`.
- AC27. WHEN a task is marked `[x]` but `Review result` is not `parent-reviewed` or `accepted` THEN the validator SHALL report `task-complete-missing-review-evidence`; completion requires a review outcome, not just non-delegation.
- AC28. WHEN structured task headings skip, duplicate, or omit machine-readable task numbers THEN the validator SHALL report `task-invalid-numbering`; dispatch dependency graphs require a unique contiguous `Task 1..N` sequence.
- AC29. WHEN `plan.md`, `tasks.md`, or `verification.md` owning links point outside the same feature's canonical `spec.md` or `plan.md` THEN the validator SHALL report `artifact-owning-link-mismatch`; old feature links cannot satisfy current Spec→Plan→Tasks→Verification lineage.
- AC30. WHEN `spec.md` declares an acceptance criterion without a matching `plan.md` `Acceptance test commands` entry, or `plan.md` declares an AC command not present in `spec.md`, THEN the validator SHALL report `acceptance-command-mismatch`; spec criteria and plan commands must have exact machine coverage.
- AC31. WHEN `spec.md` acceptance criteria or `plan.md` acceptance command entries skip, duplicate, or reorder AC numbers THEN the validator SHALL report `acceptance-numbering-invalid`; acceptance criteria must form one unique contiguous `AC1..N` sequence.
- AC32. WHEN `plan.md` acceptance test command entries are prose or otherwise not command-shaped THEN the validator SHALL report `acceptance-command-invalid`; acceptance coverage requires runnable command-shaped evidence, not backticked narration.
- AC33. WHEN `plan.md` acceptance test command bullets contain trailing prose, ranges, or non-AC command labels THEN the validator SHALL report `acceptance-command-invalid`; acceptance test commands must be exact AC-numbered command-only machine lines.
- AC34. WHEN an SDD feature directory uses a freeform slug or an artifact `Date` does not match the slug date THEN the validator SHALL report `feature-slug-invalid`; executable SDD records must use `YYYY-MM-DD-kebab-slug` identity.
- AC35. WHEN required clarify, checklist, analyze, or gate-compliance sections contain only empty template rows or placeholders THEN the validator SHALL report `gate-evidence-missing`; SDD gates require structured evidence, not headings alone.
- AC36. WHEN a `spec.md` acceptance criterion omits the executable `WHEN ... THEN ... SHALL ...` structure THEN the validator SHALL report `acceptance-criterion-format-invalid`; vague acceptance prose cannot satisfy plan-command coverage.
- AC37. WHEN a `Verified` `verification.md` Spec compliance row marks an acceptance criterion complete and references a command-shaped backticked command THEN the validator SHALL require matching exit code 0 evidence for that command in canonical evidence sections and report `verified-missing-spec-compliance-evidence` otherwise.
- AC38. WHEN `plan.md`, `tasks.md`, or `verification.md` declares malformed, template-placeholder, prose, mismatched, or cross-artifact inconsistent Worktree/Branch metadata THEN the validator SHALL report `worktree-metadata-invalid`; execution location metadata must be machine-readable.
- AC39. WHEN a non-superseded `spec.md` Background claim block lacks an existing repo `path:line` citation or external `https://` source THEN the validator SHALL report `spec-background-uncited`; specs must audit current docs/code or external references before planning.
- AC40. WHEN a checked `plan.md` Pre-flight row claims a Worktree/Branch verification that disagrees with the artifact's Worktree/Branch metadata THEN the validator SHALL report `plan-preflight-metadata-mismatch`; checked setup evidence cannot preserve stale worktree names.
- AC41. WHEN a delegated task references an existing `Subagent handoff` artifact whose title, embedded context packet, mode, or report-validation command is not bound to the same feature and task THEN the validator SHALL report `task-invalid-subagent-handoff-artifact`; stale handoff artifacts cannot satisfy the agent loop.
- AC42. WHEN a delegated task's handoff artifact declares one mode but the returned subagent report declares another mode THEN the SDD validator SHALL report `task-invalid-subagent-report-artifact`; report artifacts must not self-select broader execution scope than dispatch granted.
- AC43. WHEN a task declares a `Factory lane` outside `Spec/plan`, `Domain implementation`, `Harness/tests`, `Docs/contracts`, `Risk radar`, or `Final integration` THEN the validator SHALL report `task-invalid-agent-loop-fields`; lane budgets are deterministic constraints, not freeform prose.
- AC44. WHEN `plan.md` `Analyze Gate` rows use `Fail:`, `Pass.`, or any result that does not begin with `Pass:` or `Blocked:` THEN the validator SHALL report `plan-analyze-gate-invalid`; failed analysis must stop or block before implementation.
- AC45. WHEN a task is marked `[x]` and its `Failing test first` field references a test file path absent from successful verification evidence THEN the validator SHALL report `task-complete-missing-failing-test-evidence`; TDD metadata cannot drift away from commands actually run.
- AC46. WHEN `docs/generated/cli-help.md` drifts from `parallax --help`, `parallax db --help`, or `parallax ops --help` THEN `scripts/regen_cli_help.py --check` SHALL exit non-zero and `make check-all` SHALL run that check before integration, e2e, golden, or coverage gates.
- AC47. WHEN `docs/CONTRACTS.md` lists retired worker keys, stale agent runtime lanes, removed WebSocket payload keys, or the old News item detail route THEN architecture tests SHALL fail against `WorkerManifest`, `WorkersSettings`, `ws.py`, and `routes_news.py`.
- AC48. WHEN `docs/generated/README.md` names a missing generated file, missing generator script, or stale backticked source path such as a retired WebSocket module path THEN architecture tests SHALL fail before generated-doc instructions are trusted.
- AC49. WHEN two active SDD features touch exact or parent/child paths and a feature's conflict set only coordinates with an unrelated slug or path THEN the validator SHALL report `active-touch-conflict`.
- AC50. WHEN `docs/FRONTEND.md` or `.agents/skills/parallax-frontend-verification/SKILL.md` omits current retired CSS buckets, names the old side-effect CSS line budget, omits sanctioned shell entrypoints, or documents drawer routes absent from `APP_NAVIGATION_GROUPS` THEN frontend architecture tests SHALL fail.
- AC51. WHEN `web/src/features` contains a feature root omitted from the relative-import feature-boundary scan, or the scan lists a removed feature root, THEN frontend architecture tests SHALL fail before deep-import coverage is trusted.
- AC52. WHEN a route module under `web/src/routes` or a presentational component under `web/src/features/*/ui` directly references `useQuery`, `useMutation`, `useInfiniteQuery`, `getApi`, `postApi`, or `queryClient.set*` THEN frontend architecture tests SHALL fail and point at the owning file.
- AC53. WHEN `AGENTS.md` or `CLAUDE.md` frontend guardrails omit a retired CSS bucket declared by `cssArchitectureHarness.test.ts` THEN architecture tests SHALL fail while still requiring their shared router blocks to match.
- AC54. WHEN `.agents/skills/parallax-frontend-verification/SKILL.md` omits `frontendDataOwnership.test.ts` or any forbidden data-ownership primitive checked by that harness THEN frontend architecture tests SHALL fail.
- AC55. WHEN `docs/ARCHITECTURE.md` references a test as a bare `test_*` name or references a missing `tests/architecture/...py::test_*` function THEN architecture tests SHALL fail.
- AC56. WHEN a `src/parallax/domains/*/ARCHITECTURE.md` file lacks a markdown link in `docs/ARCHITECTURE.md`, or the module map links a removed domain architecture file, THEN architecture tests SHALL fail.
- AC57. WHEN `docs/TESTING.md` omits a current `tests/architecture/test_*.py` file or lists a removed architecture test file THEN architecture tests SHALL fail.
- AC58. WHEN the open section of `docs/TECH_DEBT.md` names an unrooted or missing source/test/doc file, uses a bare `::test_*` shorthand, or references a missing test function THEN architecture tests SHALL fail.
- AC59. WHEN a governance rule is duplicated across root docs, absent from its owner, or copied into `AGENTS.md`/`CLAUDE.md` router prose THEN architecture tests SHALL fail with separate ownership and router-leak failures.
- AC60. WHEN any `src/parallax/domains/*/types/*.py` module imports services, repositories, queries, read models, or runtime modules THEN architecture tests SHALL fail.
- AC61. WHEN any `src/parallax/domains/*/interfaces.py` module imports a runtime module THEN architecture tests SHALL fail.
- AC62. WHEN an open `docs/TECH_DEBT.md` row claims a backticked symbol is duplicated in one or more backticked `src/**/*.py` files but a cited file no longer contains that symbol THEN architecture tests SHALL fail.
- AC63. WHEN `docs/generated/ws-protocol.md` omits a WebSocket message `type` literal currently present in `src/parallax/app/surfaces/api/ws.py` THEN architecture tests SHALL fail.
- AC64. WHEN `docs/generated/ws-protocol.md` drifts from `src/parallax/app/surfaces/api/ws.py` THEN `scripts/regen_ws_protocol.py --check` SHALL exit non-zero and `make check-all` SHALL run that check before integration, e2e, golden, or coverage gates.
- AC65. WHEN `docs/generated/score-versions.md` drifts from score/version literals in `src/` THEN `scripts/regen_score_versions.py --check` SHALL exit non-zero and `make check-all` SHALL run that check before integration, e2e, golden, or coverage gates.
- AC66. WHEN `docs/generated/README.md` names any non-DB generator script THEN `make check-all` SHALL run that script with `--check` before integration, e2e, golden, or coverage gates.
- AC67. WHEN a subagent report is validated against an SDD task THEN it SHALL include task classification and required-reading evidence for `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, and task on-demand context paths.
- AC68. WHEN a `spec.md` Background claim block contains backticked evidence tokens and local `path:line` citations THEN at least one cited line SHALL mention each evidence token, otherwise the validator SHALL report `spec-background-uncited`.
- AC69. WHEN a worker is registered in `WorkerManifest` THEN its runtime constraint classification SHALL be declared on the manifest and architecture tests SHALL NOT maintain a separate worker classification inventory.
- AC70. WHEN an architecture test needs worker inventory source facts THEN it SHALL import them from runtime source such as `WorkerManifest` and SHALL NOT import peer architecture tests as source registries.
- AC71. WHEN harness code needs the complete set of tables a worker owns THEN it SHALL read `WorkerManifest.owned_tables` instead of rebuilding that set from individual write fields.
- AC72. WHEN harness code needs read-model writer ownership by table THEN it SHALL read `read_model_writer_by_table()` from `worker_manifest.py` instead of rebuilding a writer registry locally.
- AC73. WHEN `WorkerManifest` contains two workers writing the same read model table THEN manifest validation SHALL raise before the manifest can be treated as canonical source truth.
- AC74. WHEN `WorkerManifest.current_read_model_identities` names a table absent from the same manifest's `writes_read_models` THEN manifest validation SHALL raise before the manifest can be treated as canonical source truth.
- AC75. WHEN `WorkerManifest.current_read_model_identities` contains two entries for the same read model table in one worker THEN manifest validation SHALL raise before the manifest can be treated as canonical source truth.
- AC76. WHEN any `WorkerManifest` table-declaration field contains the same table name twice THEN manifest validation SHALL raise before `owned_tables` or downstream harnesses can dedupe it silently.
- AC77. WHEN a current read-model identity declaration contains the same identity column twice THEN manifest validation and `CurrentReadModelPublisher` SHALL raise before the identity can be used as stable serving truth.
- AC78. WHEN a `WorkerManifest.current_read_model_identities` entry has an empty identity column list THEN manifest validation SHALL raise before the manifest can be treated as canonical source truth.
- AC79. WHEN any `WorkerManifest` table-declaration field or `queue_depth_table` contains a blank table name THEN manifest validation SHALL raise before the manifest can be treated as canonical source truth.
- AC80. WHEN a current read-model identity declaration contains a blank identity column name THEN manifest validation and `CurrentReadModelPublisher` SHALL raise before the identity can be used as stable serving truth.
- AC81. WHEN a `WorkerManifest.current_read_model_identities` entry contains a blank read-model table name THEN manifest validation SHALL raise before ownership, missing-identity, or downstream harness checks consume the manifest.
- AC82. WHEN a `WorkerManifest` is classified as `DIRTY_TARGET_CONSUMER` and has no `dirty_target_tables` THEN manifest validation SHALL raise before worker lifecycle, ownership, or queue-health harnesses consume the manifest.
- AC83. WHEN a `WorkerManifest` is classified as `LEASED_JOB_CONSUMER` and has no `queue_depth_table` THEN manifest validation SHALL raise before worker lifecycle, ownership, or queue-health harnesses consume the manifest.
- AC84. WHEN a `WorkerManifest` is classified as `BOUNDED_PROVIDER_SCHEDULER` and does not set `uses_provider_io` THEN manifest validation SHALL raise before provider-boundary, lifecycle, or worker inventory harnesses consume the manifest.
- AC85. WHEN a `WorkerManifest.queue_depth_table` names a table absent from the same manifest's owned tables THEN manifest validation SHALL raise before queue-health, ownership, or worker inventory harnesses consume the manifest.
- AC86. WHEN a non-side-effect `WorkerManifest.kind` declares `side_effect_ledgers` THEN manifest validation SHALL raise before ownership, side-effect, or worker inventory harnesses consume the manifest.
- AC87. WHEN a `WorkerManifest.wakes_on` or `WorkerManifest.wakes_out` entry is blank THEN manifest validation SHALL raise before listener, NOTIFY, or worker inventory harnesses consume the manifest.
- AC88. WHEN a `WorkerManifest.wakes_on` or `WorkerManifest.wakes_out` field repeats a channel THEN manifest validation SHALL raise before listener, NOTIFY, or worker inventory harnesses consume the manifest.
- AC89. WHEN two `WorkerManifest` entries declare the same `advisory_lock_key` THEN manifest validation SHALL raise before runtime lifecycle, advisory-lock, or worker inventory harnesses consume the manifest.
- AC90. WHEN a `WorkerManifest.advisory_lock_key` value is blank THEN manifest validation SHALL raise before runtime lifecycle, advisory-lock, or worker inventory harnesses consume the manifest.
- AC91. WHEN a `WorkerManifest.name`, `domain`, `factory`, or `worker_class` value is blank THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC92. WHEN a `WorkerManifest.idempotency_evidence` entry is blank THEN manifest validation SHALL raise before lifecycle, ownership, review, or worker inventory harnesses consume the manifest.
- AC93. WHEN a `WorkerManifest.input_contract` declaration is empty THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC94. WHEN a `WorkerManifest.input_contract` entry is blank THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC95. WHEN a `WorkerManifest.ordering_keys` declaration is empty THEN manifest validation SHALL raise before lifecycle, idempotency, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC96. WHEN a `WorkerManifest.ordering_keys` entry is blank THEN manifest validation SHALL raise before lifecycle, idempotency, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC97. WHEN a `WorkerManifest.ordering_keys` entry repeats within one manifest THEN manifest validation SHALL raise before lifecycle, idempotency, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC98. WHEN a `WorkerManifest.input_contract` entry repeats within one manifest THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC99. WHEN a `WorkerManifest.idempotency_evidence` entry repeats within one manifest THEN manifest validation SHALL raise before lifecycle, ownership, review, or worker inventory harnesses consume the manifest.
- AC100. WHEN two `WorkerManifest.worker_class` values are the same THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC101. WHEN a `WorkerManifest.start_priority` value is negative THEN manifest validation SHALL raise before scheduler, registry, settings, or worker inventory harnesses consume the manifest.
- AC102. WHEN a `WorkerManifest.start_priority` value is not an integer THEN manifest validation SHALL raise before scheduler, registry, settings, or worker inventory harnesses consume the manifest.
- AC103. WHEN a `WorkerManifest.factory` value does not name an existing `src/parallax/app/runtime/worker_factories/*.py` source file THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC104. WHEN a `WorkerManifest.worker_class` module path cannot be resolved THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC105. WHEN a `WorkerManifest.worker_class` class name is absent from its resolved module THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC106. WHEN a `WorkerManifest.domain` value does not name an existing `src/parallax/domains/<domain>` source directory THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC107. WHEN a `WorkerManifest.lane`, `WorkerManifest.kind`, or `WorkerManifest.runtime_constraint` value is not the corresponding manifest enum type THEN manifest validation SHALL raise before scheduler, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC108. WHEN a `WorkerManifest.uses_provider_io` value is not a boolean THEN manifest validation SHALL raise before provider-boundary, registry, settings, or worker inventory harnesses consume the manifest.
- AC109. WHEN a tuple-valued `WorkerManifest` contract field is not a tuple THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC110. WHEN a tuple-valued string `WorkerManifest` contract field contains a non-string entry THEN manifest validation SHALL raise before registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC111. WHEN a `WorkerManifest.current_read_model_identities` entry declares identity columns that are not a tuple THEN manifest validation SHALL raise before ownership, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC112. WHEN a `WorkerManifest.current_read_model_identities` entry is not a tuple THEN manifest validation SHALL raise before ownership, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC113. WHEN `worker_manifest.py` is imported in a clean process where `importlib.util` is not already attached to the imported `importlib` package object THEN the import SHALL succeed without relying on incidental import side effects.
- AC114. WHEN a `WorkerManifest.current_read_model_identities` entry does not contain exactly the read-model table name and stable identity columns THEN manifest validation SHALL raise before table/column unpacking, ownership, registry, factory, settings, or worker inventory harnesses consume the manifest.
- AC115. WHEN visual verification artifacts such as PNG, JPG, WEBP, or GIF files exist at the repository root THEN the architecture harness SHALL fail until those loose root artifacts are removed or moved under an owned artifact directory.
- AC116. WHEN a `WorkerManifest.queue_depth_table` value is neither `None` nor a string THEN manifest validation SHALL raise before table hygiene, queue ownership, queue-health, registry, settings, or worker inventory harnesses consume it.
- AC117. WHEN a `WorkerManifest.advisory_lock_key` value is neither `None` nor a string THEN manifest validation SHALL raise before advisory-lock blank checks, duplicate checks, lifecycle, registry, settings, or worker inventory harnesses consume it.
- AC118. WHEN a `WorkerManifest.name`, `domain`, `factory`, or `worker_class` value is not a string THEN manifest validation SHALL raise before identity blank checks, source-path checks, class import checks, registry, settings, or worker inventory harnesses consume it.
- AC119. WHEN a `WorkerManifest.current_read_model_identities` entry has a read-model table name that is not a string THEN manifest validation SHALL raise before identity table blank checks, duplicate checks, missing-identity checks, ownership checks, registry, settings, or worker inventory harnesses consume it.
- AC120. WHEN a `WorkerManifest.current_read_model_identities` identity column value is not a string THEN manifest validation SHALL raise before identity column blank checks, duplicate checks, forbidden lifecycle-column checks, missing-identity checks, ownership checks, registry, settings, or worker inventory harnesses consume it.
- AC121. WHEN `CurrentReadModelPublisher.identity_columns` contains a non-string value THEN publisher construction SHALL raise before identity column blank checks, duplicate checks, forbidden lifecycle-column checks, row identity reads, changed-row hashing, or worker static harnesses consume it.
- AC122. WHEN `CurrentReadModelPublisher.payload_hash_column` is not a string THEN publisher construction SHALL raise before row payload hashing, changed-row writes, or worker static harnesses consume it as a serving-row key.
- AC123. WHEN `CurrentReadModelPublisher.payload_columns` is neither `None` nor a tuple THEN publisher construction SHALL raise before row payload hashing, changed-row writes, or worker static harnesses consume it as the payload field list.
- AC124. WHEN `CurrentReadModelPublisher.payload_columns` contains a non-string entry THEN publisher construction SHALL raise before row payload hashing, changed-row writes, or worker static harnesses consume it as a payload key.
- AC125. WHEN `CurrentReadModelPublisher.payload_columns` contains a blank entry THEN publisher construction SHALL raise before row payload hashing, changed-row writes, or worker static harnesses consume it as a payload key.
- AC126. WHEN `CurrentReadModelPublisher.payload_hash_column` is blank THEN publisher construction SHALL raise before row payload hashing, changed-row writes, or worker static harnesses consume it as the serving-row hash key.
- AC127. WHEN `CurrentReadModelPublisher.payload_columns` contains a duplicate entry THEN publisher construction SHALL raise before row payload hashing, changed-row writes, or worker static harnesses collapse repeated payload keys.
- AC128. WHEN `CurrentReadModelPublisher.payload_hash_column` names a serving lifecycle column THEN publisher construction SHALL raise before changed-row writes can overwrite runtime lifecycle fields.
- AC129. WHEN `CurrentReadModelPublisher.payload_columns` contains the configured payload hash column THEN publisher construction SHALL raise before row payload hashing can self-reference prior serving hashes.
- AC130. WHEN `CurrentReadModelPublisher.payload_columns` contains a serving lifecycle column THEN publisher construction SHALL raise before explicit row payload hashing can reintroduce run, generation, attempt, or timestamp drift.
- AC131. WHEN `CurrentReadModelPublisher.payload_hash_column` names a stable identity column THEN publisher construction SHALL raise before changed-row writes can overwrite serving identity keys.
- AC132. WHEN `CurrentReadModelPublisher.payload_columns` names a field missing from a row THEN explicit row payload hashing SHALL raise instead of hashing the absent field as `None`.
- AC133. WHEN a `WorkerManifest` is classified as `BOUNDED_PROVIDER_SCHEDULER` and declares `dirty_target_tables` THEN manifest validation SHALL raise before worker lifecycle, queue-health, or inventory harnesses can treat that provider source adapter as a dirty-target consumer.
- AC134. WHEN a `WorkerManifest` is classified as `BOUNDED_PROVIDER_SCHEDULER` and declares `queue_depth_table` THEN manifest validation SHALL raise before worker lifecycle, queue-health, or inventory harnesses can treat that provider source adapter as a leased queue consumer.
- AC135. WHEN a `WorkerManifest` is classified as `BOUNDED_PROVIDER_SCHEDULER` and declares `queue_health_tables` THEN manifest validation SHALL raise before worker lifecycle, queue-health, or inventory harnesses can treat that provider source adapter as a queue-health consumer.
- AC136. WHEN a `WorkerManifest.queue_depth_table` value is owned only through facts, read models, input observations, or side-effect ledgers and not through `writes_control_plane` THEN manifest validation SHALL raise before queue-health or inventory harnesses can treat the table as a leased queue.
- AC137. WHEN a `WorkerManifest.queue_health_tables` value is owned only through facts, read models, input observations, or side-effect ledgers and not through `writes_control_plane` THEN manifest validation SHALL raise before queue-health or inventory harnesses can treat the table as a queue-health surface.
- AC138. WHEN `CurrentReadModelPublisher.changed_rows()` receives a row missing any stable identity column THEN it SHALL raise a dedicated missing-identity error before payload hashing, existing-hash lookup, or changed-row write preparation.
- AC139. WHEN `CurrentReadModelPublisher.changed_rows()` receives more than one row with the same stable identity tuple in a single batch THEN it SHALL raise before returning changed rows or preparing duplicate writes for the same current read-model identity.
- AC140. WHEN `CurrentReadModelPublisher.row_payload_hash()` receives a row missing any declared explicit payload column THEN it SHALL raise a dedicated missing-payload-column error instead of leaking a raw `KeyError`.
- AC141. WHEN `CurrentReadModelPublisher.changed_rows()` receives a row with any non-string column key THEN it SHALL raise a dedicated row-column validation error before payload hashing or changed-row write preparation.
- AC142. WHEN `CurrentReadModelPublisher.changed_rows()` receives a row whose stable identity column value is `None` THEN it SHALL raise a dedicated null-identity validation error before payload hashing or changed-row write preparation.
- AC143. WHEN `CurrentReadModelPublisher.changed_rows()` receives a row whose stable identity column value is a blank string THEN it SHALL raise a dedicated blank-identity validation error before payload hashing or changed-row write preparation.
- AC144. WHEN `CurrentReadModelPublisher.identity_columns` is not a tuple THEN publisher construction SHALL raise before stable identity validation can consume list-shaped or scalar compatibility values.
- AC145. WHEN `CurrentReadModelPublisher.changed_rows()` receives a row that is not a mapping THEN it SHALL raise a dedicated row-shape validation error before column, identity, payload hash, or changed-row write-preparation validation.
- AC146. WHEN `CurrentReadModelPublisher.changed_rows()` receives `existing_hashes` that is not a mapping THEN it SHALL raise a dedicated existing-hash validation error before row, identity, payload hash, hash-lookup, or changed-row write-preparation validation.
- AC147. WHEN `CurrentReadModelPublisher.changed_rows()` receives `existing_hashes` with a non-tuple identity key THEN it SHALL raise a dedicated existing-hash identity validation error before row, payload hash, hash-lookup, unchanged-row skip, or changed-row write-preparation validation.
- AC148. WHEN `CurrentReadModelPublisher.changed_rows()` receives `existing_hashes` with an identity tuple whose arity differs from `identity_columns` THEN it SHALL raise a dedicated existing-hash identity arity validation error before row, payload hash, hash-lookup, unchanged-row skip, or changed-row write-preparation validation.
- AC149. WHEN `CurrentReadModelPublisher.changed_rows()` receives `existing_hashes` with a value that is neither a string nor `None` THEN it SHALL raise a dedicated existing-hash value validation error before row, payload hash, hash-lookup, unchanged-row skip, or changed-row write-preparation validation.
- AC150. WHEN `CurrentReadModelPublisher.changed_rows()` receives `existing_hashes` with a string value that is not `sha256:` followed by 64 lowercase hex characters THEN it SHALL raise a dedicated existing-hash value-format validation error before row, payload hash, hash-lookup, unchanged-row skip, or changed-row write-preparation validation.
- AC151. WHEN `CurrentReadModelPublisher.changed_rows()` receives `rows` that is scalar, mapping-shaped, or string-shaped THEN it SHALL raise a dedicated row-batch validation error before row, column, identity, payload hash, duplicate-identity, or changed-row write-preparation validation consumes compatibility-shaped row containers.
- AC152. WHEN `stable_current_payload_hash()` receives a payload that is scalar, list-of-pairs-shaped, or string-shaped THEN it SHALL raise a dedicated payload-shape validation error before `dict(...)` coercion, JSON normalization, or hash generation consumes compatibility-shaped payload containers.
- AC153. WHEN `stable_current_payload_hash()` receives a mapping payload with any non-string top-level key THEN it SHALL raise a dedicated payload-key validation error before JSON normalization, key stringification, or hash generation consumes compatibility-shaped payload keys.
- AC154. WHEN `stable_current_payload_hash()` receives a mapping payload containing nested mapping values with any non-string key THEN it SHALL raise a dedicated payload-key validation error before JSON normalization, key stringification, or hash generation consumes compatibility-shaped nested payload keys.
- AC155. WHEN `stable_current_payload_hash()` receives a mapping payload containing an arbitrary object that exposes `isoformat()` but is not a supported date/time value THEN it SHALL raise a dedicated payload-value validation error before JSON normalization, generic ISO formatting, or hash generation consumes compatibility-shaped payload values.
- AC156. WHEN `stable_current_payload_hash()` receives a mapping payload containing float or Decimal NaN/Infinity values THEN it SHALL raise a dedicated payload-number validation error before JSON serialization, Decimal stringification, or hash generation consumes non-finite payload numbers.
- AC157. WHEN `stable_current_payload_hash()` receives a mapping payload containing set or frozenset values THEN it SHALL raise a dedicated payload-container validation error before JSON normalization, container sorting, or hash generation consumes unordered compatibility-shaped payload containers.
- AC158. WHEN CEX OI radar board publication payload hashing receives row `score_components` with non-string keys THEN it SHALL raise the shared current payload-key validation error before local key stringification, JSON normalization, or board hash generation consumes compatibility-shaped score component payloads.
- AC159. WHEN a CEX worker module imports repository code that imports shared runtime payload hash helpers THEN package initialization SHALL NOT import `WorkerScheduler`, `worker_manifest`, or run manifest validation before the worker class is fully importable.
- AC160. WHEN CEX detail snapshot payload hashing receives `level_bands` entries with non-string keys THEN it SHALL raise the shared current payload-key validation error before local key stringification, historical numeric canonicalization, JSON normalization, or detail hash generation consumes compatibility-shaped level-band payloads.
- AC161. WHEN CEX detail snapshot payload hashing receives `source_refs` entries with non-string keys THEN it SHALL raise the shared current payload-key validation error before source-ref metadata filtering, local key stringification, JSON normalization, or detail hash generation consumes compatibility-shaped source-ref payloads.
- AC162. WHEN token profile current row hashing receives `source_payload_json` with non-string keys THEN it SHALL raise the shared current payload-key validation error before `postgres_safe_json()`, local key stringification, JSON normalization, or profile current hash generation consumes compatibility-shaped source payloads.
- AC163. WHEN News source-quality row hashing receives `diagnostics_json` with non-string keys THEN it SHALL raise the shared current payload-key validation error before local key stringification, JSON normalization, or source-quality hash generation consumes compatibility-shaped diagnostics payloads.
- AC164. WHEN News page-row hashing receives `story` payloads with non-string keys THEN it SHALL raise the shared current payload-key validation error before local key stringification, JSON normalization, page-row hash generation, or serving-row writes consume compatibility-shaped story payloads.
- AC165. WHEN Narrative admission row hashing receives a payload with non-string keys THEN it SHALL raise the shared current payload-key validation error before local key stringification, JSON normalization, unordered-container sorting, generic `default=str` conversion, or admission hash generation consumes compatibility-shaped payloads.
- AC166. WHEN Narrative admission row hashing receives an arbitrary object that exposes an `obj` attribute but is not a `Jsonb` adapter THEN it SHALL raise the shared current payload unsupported-value error before generic adapter unwrapping, JSON normalization, or admission hash generation consumes compatibility-shaped adapter payloads.
- AC167. WHEN Macro daily brief payload hashing receives a current brief payload with non-string keys THEN it SHALL raise the shared current payload-key validation error before `postgres_safe_json()`, local key stringification, JSON normalization, generic `default=str` conversion, or daily brief hash generation consumes compatibility-shaped payloads.
- AC168. WHEN Macro view snapshot payload hashing receives current snapshot JSON such as `features_json` with non-string keys THEN it SHALL raise the shared current payload-key validation error before `postgres_safe_json()`, local key stringification, JSON normalization, generic `default=str` conversion, or snapshot hash generation consumes compatibility-shaped payloads.
- AC169. WHEN Macro observation series row hashing receives current row JSON such as `raw_payload_json` with non-string keys THEN it SHALL raise the shared current payload-key validation error before local key stringification, JSON normalization, unordered-container sorting, generic ISO formatting, or series-row hash generation consumes compatibility-shaped payloads.
- AC170. WHEN Token Radar stable payload hashing receives current payload JSON with non-string keys or unordered containers THEN it SHALL raise the shared current payload validation errors before Token Radar canonicalization can stringify keys, sort containers, unwrap generic adapter-like objects, or generate current-row/downstream dirty-target hashes from compatibility-shaped payloads.
- AC171. WHEN domain repositories or queries use shared current payload hashing THEN they SHALL import the pure hash contract from `parallax.platform.current_read_model_payload_hash` rather than `parallax.app.runtime.current_read_model_publisher`, so the repository/query architecture gate continues to reject upward runtime dependencies.
- AC172. WHEN Token Radar dirty target or source dirty event payload hashing receives payloads with non-string keys THEN it SHALL raise the shared current payload-key validation error before lifecycle-field filtering, `postgres_safe_json()`, local key stringification, JSON normalization, or dirty queue payload hash generation consumes compatibility-shaped payloads.
- AC173. WHEN Pulse trigger dirty target payload hashing receives payloads with non-string keys or queue lifecycle fields such as `priority` and `due_at_ms` THEN it SHALL raise the shared current payload-key validation error for non-string keys and SHALL exclude lifecycle fields from the stable payload before `postgres_safe_json()`, local key stringification, JSON normalization, or dirty queue payload hash generation consumes compatibility-shaped queue state.
- AC174. WHEN Narrative admission dirty target payload hashing receives payloads with non-string keys or queue lifecycle fields such as `priority` and `due_at_ms` THEN it SHALL raise the shared current payload-key validation error for non-string keys and SHALL exclude lifecycle fields from the stable payload before `postgres_safe_json()`, local key stringification, JSON normalization, or dirty queue payload hash generation consumes compatibility-shaped queue state.
- AC175. WHEN Asset Market dirty-control-plane payload hashing for `market_tick_current_dirty_targets`, `token_profile_current_dirty_targets`, `token_image_source_dirty_targets`, or `asset_profile_refresh_targets` receives payloads with non-string keys or queue lifecycle fields such as `priority`, `due_at_ms`, lease fields, attempt counts, errors, or update timestamps THEN it SHALL raise the shared current payload-key validation error for non-string keys and SHALL exclude lifecycle fields from the stable payload before `postgres_safe_json()`, `default=str`, local key stringification, JSON normalization, or dirty queue payload hash generation consumes compatibility-shaped queue state.
- AC176. WHEN Token Capture Tier dirty rank-set fingerprinting receives rank payloads with non-string nested keys, unordered containers, or compatibility-shaped factor snapshots THEN it SHALL raise shared current payload validation errors and emit `sha256:`-prefixed stable hashes before local `_json_ready()` key stringification, set-to-list conversion, generic adapter unwrapping, or repository-local JSON/sha256 normalization can generate `token_capture_tier_dirty_targets.payload_hash`.
- AC177. WHEN Macro projection dirty-control-plane payload hashing for current or concept dirty targets receives compatibility-shaped values with non-string nested keys THEN it SHALL raise shared current payload validation errors and emit `sha256:`-prefixed stable dirty hashes before `postgres_safe_json()`, `default=str`, local key stringification, or repository-local JSON/sha256 normalization can generate `macro_projection_dirty_targets.payload_hash`.
- AC178. WHEN `docs/AGENT_EXECUTION.md` documents the product read-only context registry THEN it SHALL name live source symbols from `src/parallax/platform/agent_read_tools.py` and SHALL reject stale tool class names before product-agent docs can drift from the audited runtime surface.
- AC179. WHEN active SDD task metadata lists `File(s)` or `Touch set` entries THEN those entries SHALL resolve to current repository paths or matching globs, and deleted artifacts SHALL be recorded only in `Removed file(s)` before generated coordination indexes can advertise stale files as active work surfaces.
- AC180. WHEN a production feature advances through `clarify`, `checklist`, `analyze`, or `implement` THEN each gate SHALL have an explicit non-mutating CLI check that can pass or fail independently of the full SDD validator before the lane is documented as executable.
- AC181. WHEN `tasks.md` contains a `## Final verification` checklist THEN SDD artifact validation SHALL reject it before task records can duplicate or diverge from the canonical evidence in `verification.md`.
- AC182. WHEN `make check-all` runs SDD harness gates THEN it SHALL execute a non-mutating all-active `clarify`/`checklist`/`analyze`/`implement` sweep before generated index freshness can pass.
- AC183. WHEN the `implement` SDD gate checks a feature with delegated subagent handoff or report drift THEN it SHALL fail on the underlying task issue before agent-loop delegation can be treated as executable.
- AC184. WHEN a `clarify`, `checklist`, or `analyze` gate section contains only table headers or placeholder rows THEN the gate checker SHALL fail with `gate-evidence-missing` before a header-only table can satisfy executable gate evidence.
- AC185. WHEN a gate table body row contains placeholder cells such as `<pending>` or `YYYY-MM-DD` THEN the gate checker SHALL reuse the full SDD validator placeholder-cell semantics and fail before template rows can satisfy executable gate evidence.
- AC186. WHEN the `implement` SDD gate checks a feature whose `tasks.md` is missing `## Gate Compliance` evidence THEN it SHALL fail on the tasks artifact gate issue before task records can be treated as executable.
- AC187. WHEN the `analyze` SDD gate checks Analyze Gate result rows THEN every non-placeholder result SHALL start with `Pass:` or `Blocked:` before the feature can advance past analysis.
- AC188. WHEN required SDD section names appear only as prose or backticked tokens instead of Markdown heading lines THEN the validator and gate checker SHALL treat the section as missing before artifact evidence can be accepted.
- AC189. WHEN required SDD section names appear inside fenced code blocks THEN the validator and gate checker SHALL ignore those tokens as headings before artifact evidence can be accepted or section bodies can be truncated.
- AC190. WHEN SDD fenced code blocks use tilde fences (`~~~`) instead of backtick fences THEN the validator and gate checker SHALL apply the same heading-ignore and citation-ignore semantics before gate evidence can pass.
- AC191. WHEN gate evidence tables contain body rows with fewer than two non-placeholder cells THEN the validator and gate checker SHALL reject the section as lacking evidence before lifecycle gates can pass.
- AC192. WHEN gate evidence pipe rows omit the Markdown table separator row THEN the validator and gate checker SHALL reject the section as lacking evidence before lifecycle gates can pass.
- AC193. WHEN gate evidence pipe rows put body rows before the Markdown table separator row THEN the validator and gate checker SHALL reject the section as lacking evidence before lifecycle gates can pass.
- AC194. WHEN gate evidence separator rows contain empty cells or cells without hyphens THEN the validator and gate checker SHALL reject the section as lacking evidence before lifecycle gates can pass.
- AC195. WHEN gate evidence header, separator, and body rows have mismatched column counts THEN the validator and gate checker SHALL reject the section as lacking evidence before lifecycle gates can pass.
- AC196. WHEN gate evidence body rows are separated from their header and separator by prose or blank lines THEN the validator and gate checker SHALL reject those rows as outside the Markdown table before lifecycle gates can pass.
- AC197. WHEN gate evidence tables use non-canonical headers for their lifecycle section THEN the validator and gate checker SHALL reject the section as lacking evidence before lifecycle gates can pass.
- AC198. WHEN Analyze Gate contains additional non-canonical Markdown tables THEN the validator and gate checker SHALL ignore those tables for `Pass:` or `Blocked:` result validation before contextual notes can create false lifecycle failures.
- AC199. WHEN an Analyze Gate canonical row contains an invalid non-placeholder result and placeholder text in another column THEN the gate checker SHALL still reject the row with the validator's Analyze result semantics before placeholder checks can hide lifecycle failures.
- AC200. WHEN a gate evidence table contains repeated separator rows after the header separator THEN the validator and gate checker SHALL reject the table as lacking evidence before malformed Markdown can satisfy lifecycle gates.
- AC201. WHEN a gate evidence table contains a repeated header row in the body THEN the validator and gate checker SHALL reject the table as lacking evidence before copied headers can satisfy lifecycle gates.
- AC202. WHEN a gate evidence table row starts with `|` but is not closed with a trailing `|` THEN the validator and gate checker SHALL reject that row as table evidence before partial pipe text can satisfy lifecycle gates.
- AC203. WHEN a gate evidence table row uses doubled boundary pipes such as `|| ... ||` THEN the validator and gate checker SHALL reject the row as table evidence before extra boundary pipes can be stripped into canonical-looking cells.
- AC204. WHEN a gate evidence table is indented as a code block or nested block THEN the validator and gate checker SHALL reject those rows as table evidence before non-top-level Markdown can satisfy lifecycle gates.
- AC205. WHEN Clarifications gate evidence uses an approval date outside canonical `YYYY-MM-DD` form THEN the validator and gate checker SHALL reject the row as lacking evidence before freeform or compact dates can satisfy lifecycle gates.
- AC206. WHEN SDD artifact `Date` or `Approved at` metadata uses compact, freeform, or impossible dates THEN the validator SHALL report `metadata-date-invalid` before lifecycle metadata can satisfy executable SDD gates.
- AC207. WHEN `tasks.md` Gate Compliance omits any canonical lifecycle row for Clarify, Checklist, Analyze, Implement, or Verify THEN the validator and implement gate SHALL report `gate-evidence-missing` before partial task gate tables can satisfy implementation readiness.
- AC208. WHEN an Analyze Gate result uses only `Pass:` or `Blocked:` without non-placeholder evidence text after the status THEN the validator and analyze gate checker SHALL report `plan-analyze-gate-invalid` before status-only rows can satisfy analysis readiness.
- AC209. WHEN `tasks.md` Gate Compliance repeats, reorders, or adds rows beyond the canonical Clarify, Checklist, Analyze, Implement, Verify sequence THEN the validator and implement gate SHALL report `gate-evidence-missing` before non-canonical lifecycle tables can satisfy implementation readiness.
- AC210. WHEN `tasks.md` Gate Compliance splits canonical lifecycle rows across multiple table blocks THEN the validator and implement gate SHALL report `gate-evidence-missing` before stitched table fragments can satisfy implementation readiness.
- AC211. WHEN an SDD feature reaches final verification THEN `scripts/check_sdd_gate.py --gate verify` SHALL enforce `verification.md` final evidence, including a successful `make check-all` block and complete Spec compliance rows, before a completion claim can pass.
- AC212. WHEN `verification.md` Spec compliance has no canonical evidence rows THEN the validator and verify gate SHALL report `verified-incomplete-spec-compliance` before an empty completion matrix can satisfy final verification.
- AC213. WHEN `verification.md` Spec compliance omits any acceptance criterion declared in `spec.md` THEN the validator and verify gate SHALL report `verified-incomplete-spec-compliance` before partial contract coverage can satisfy final verification.
- AC214. WHEN `verification.md` Coverage rows are missing or remain non-complete THEN the validator and verify gate SHALL report `verified-coverage-incomplete` before coverage placeholders can satisfy final verification.
- AC215. WHEN `verification.md` E2E golden path omits or leaves unchecked any required runtime signal THEN the validator and verify gate SHALL report `verified-e2e-incomplete` before skipped or not-applicable E2E evidence can satisfy final verification.
- AC216. WHEN `verification.md` Skipped tests evidence omits a numeric skipped-test count or leaves it as non-numeric placeholder text THEN the validator and verify gate SHALL report `verified-unexplained-skips` before pending skipped-test evidence can satisfy final verification.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Validator becomes another wording-only scanner. | High | Parse stable metadata and issue codes; reserve phrase scans for forbidden contradiction language. |
| Coordination board grows into canonical runtime truth. | Medium | Index states that code/docs/runtime contracts remain canonical truth. |
| SQL helper over-promises parsing. | Medium | Keep it a lightweight contract normalizer for test assertions, not a SQL parser. |
| `make check-all` becomes too slow. | Low | Validator and index checks are pure filesystem scans. |

## Evolution path

The next expansion is a richer active-work dispatch CLI that can split context packets across multiple lanes and
optionally write reviewed packets to generated artifacts. This work should not foreclose that path, but it must avoid
adding durable runtime agent queues.

## Alternatives considered

- Keep prose-only SDD checks — rejected because prose allowed false `Verified` records.
- Add a second planning tree — rejected because `docs/sdd/` is the current hard-cut lane and old lanes should not remain as compatibility paths.
- Fully parse PostgreSQL SQL grammar in tests — rejected because the immediate need is stable contract assertions, not query rewriting.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Validate SDD truth, render coordination fields, classify harness tests, and include the new checks in `make check-all`. |
| Ask first | Large-scale conversion of every SQL test family. |
| Never | Recreate legacy planning folders, accept partial `Verified` evidence, or add compatibility shims for old harness surfaces. |
