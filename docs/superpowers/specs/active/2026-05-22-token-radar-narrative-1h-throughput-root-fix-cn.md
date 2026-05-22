# Spec — Token Radar Narrative 1h Throughput Root Fix

**Status**: Draft
**Date**: 2026-05-22
**Owner**: Qinghuan / Codex
**Related**:

- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `docs/superpowers/specs/active/2026-05-20-token-radar-narrative-backlog-hard-cut-cn.md`
- `docs/superpowers/specs/active/2026-05-19-agent-execution-plane-backpressure-and-backlog-root-fix-cn.md`

## Background

Narrative Intelligence currently sits downstream of Token Radar as three
read-model workers: `NarrativeAdmissionWorker`, `MentionSemanticsWorker`, and
`TokenDiscussionDigestWorker`. The global worker inventory documents this flow
as `token_radar_projection -> narrative_admission -> mention_semantics /
token_discussion_digest` in `docs/WORKERS.md:67-74`, and the domain architecture
states that public reads compose `token_discussion_digests` with the current
`narrative_admissions` frontier in
`src/gmgn_twitter_intel/domains/narrative_intel/ARCHITECTURE.md:5-22`.

The current admission worker reads configured windows and scopes from settings,
then admits up to `admission_limit` Radar rows per `(window, scope)` pair. The
runtime loop is in
`src/gmgn_twitter_intel/domains/narrative_intel/runtime/narrative_admission_worker.py:47-120`.
Default settings currently include `windows=("5m", "1h", "4h", "24h")`,
`scopes=("all", "matched")`, `admission_limit=200`, and `min_rank_score=30` in
`src/gmgn_twitter_intel/platform/config/settings.py:915-920`.

The semantics worker claims existing due rows before enqueueing missing rows.
That ordering is explicit in
`src/gmgn_twitter_intel/domains/narrative_intel/runtime/mention_semantics_worker.py:46-57`.
Only when no rows are claimable does it call `_enqueue_missing_from_admissions_sync`.
The enqueue path is bounded by per-cycle, per-admission, and per-target budgets
in `mention_semantics_worker.py:280-358`; defaults are
`provider_batch_size=10`, `max_semantic_rows_enqueued_per_cycle=120`,
`max_semantic_rows_enqueued_per_admission=20`, and
`max_semantics_claimed_per_target_per_cycle=3` in
`src/gmgn_twitter_intel/platform/config/settings.py:928-943`.

The digest worker reads all due admissions from `narrative_admissions`, not from
a digest-window allowlist. `due_digest_targets` only filters
`status='admitted'` and `next_digest_due_at_ms <= now` in
`src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py:991-1002`.
The worker then evaluates each target through `NarrativeEpochPolicy` and
`DiscussionDigestService`, as shown in
`src/gmgn_twitter_intel/domains/narrative_intel/runtime/token_discussion_digest_worker.py:69-170`.
The epoch policy intentionally marks windows outside `1h/4h/24h` as unsupported
in `src/gmgn_twitter_intel/domains/narrative_intel/services/narrative_epoch_policy.py:69-76`,
but `5m` can still be admitted and scanned before that decision.

`DiscussionDigestService.refresh_decision()` requires every current source row
to have a semantic row before a ready digest can be requested. If
`missing_semantic_count + pending_semantic_count + retryable_semantic_count > 0`,
it returns `semantic_labeling_pending` and writes a `pending` status digest. This
gate is in
`src/gmgn_twitter_intel/domains/narrative_intel/services/discussion_digest_service.py:45-90`.
The public read path returns either the latest ready digest or a missing digest
sentinel with a reason from `_not_ready_reason_for_admission`; it also exposes
missing semantics as backlog metadata in
`src/gmgn_twitter_intel/domains/narrative_intel/repositories/narrative_repository.py:1413-1493`.

The frontend maps `semantic_labeling_pending` to "叙事分析中" in
`web/src/shared/model/narrativeDataGaps.ts:41-52`, and maps `pending` to the same
label in `web/src/shared/model/tokenRadarCompactCase.ts:245-252`. This is why
users see many Token Radar items as "叙事分析中" even when the row is actually
waiting on source admission, queue enqueue budget, provider timeout, or digest
cycle capacity.

Live production evidence on 2026-05-22 showed the shape of the problem:

- `1h/all` Token Radar top 20 returned 19 pending/not-ready narrative states.
- 18 of those were `semantic_labeling_pending`.
- Current admitted source coverage had `1h/all: 456 source rows, 327 missing
  semantics` and `4h/all: 1418 source rows, 701 missing semantics`.
- Recent worker status showed `narrative_admission` upserted hundreds of
  admissions per cycle, `mention_semantics` claimed only 10 rows and hit provider
  timeout, and `token_discussion_digest` processed mostly status-only pending
  digests with `llm_cycle_budget_exhausted`.
- `token_radar_rows` retained about 17 million historical rows, while
  `narrative_admissions` retained about 14k rows and
  `token_discussion_digests` about 23k rows.

## Problem

Token Radar is a high-recall scanner, but Narrative digest is a comparatively
expensive semantic read model. Production currently asks the narrative lane to
track too many windows and too many targets, then requires full source-set
semantic completion before a digest can be ready. The result is a permanent
arrival-rate versus service-rate mismatch: fresh Radar rows keep entering the
frontier faster than semantics and digest workers can drain them, so public rows
remain "叙事分析中" even though Token Radar itself is fresh.

## First principles

1. **Radar scans; Narrative explains.** Token Radar may scan `5m/1h/4h/24h`, but
   realtime narrative digest should only explain the product horizon that users
   can act on. A scanner window must not automatically create an LLM SLA.
2. **One product SLA beats many fake SLAs.** A reliable `1h` narrative lane is
   better than eight nominal window/scope lanes that all show pending. Production
   should expose non-trigger windows honestly instead of pretending they are
   independently being analyzed.
3. **Backlog is a throughput contract.** The system must be testable as
   `admitted source rows -> semantic rows -> ready/status digest` under bounded
   arrival rates. Passing unit tests for status transitions is insufficient if a
   production-shaped batch cannot drain.
4. **No hidden compatibility paths.** Hard-cut runtime behavior must delete
   obsolete window support, fallback digest behavior, and misleading health
   semantics rather than keeping aliases that hide backlog.
5. **Analysis window is not surface window.** A `5m`, `4h`, or `24h` Radar row
   may display a same-target `1h` narrative overlay, but the API and UI must say
   that the source/analysis window is `1h`. Reuse is a read-model fanout of one
   authoritative current narrative, not a claim that the surface window's full
   source set was analyzed.

## Goals

- **G1 — Production narrative scope is `1h` only.** Runtime narrative admission
  and discussion digest workers SHALL admit and service only `1h` Token Radar
  rows for realtime Token Radar narrative hydration. `5m`, `4h`, and `24h` may
  remain Token Radar scanner windows, but they are not realtime narrative digest
  SLA windows.
- **G2 — Scope policy is explicit.** The allowed narrative scopes for the `1h`
  lane SHALL be configurable, but production defaults SHALL start with the
  smallest useful surface: `1h/all` and optionally `1h/matched` only when the
  watched-account source volume justifies it. The spec does not require serving
  all scopes by default.
- **G3 — Non-trigger windows can reuse `1h` narrative honestly.** Public Token
  Radar rows for `5m`, `4h`, and `24h` SHALL NOT trigger independent realtime
  narrative work by default. They MAY attach a same-target `1h` narrative digest
  as a read-only overlay when one is current enough for the product contract, but
  the payload SHALL expose `analysis_window/source_window = "1h"`,
  `surface_window = <requested window>`, and a reuse reason such as
  `target_current_1h_narrative`. If no compatible `1h` narrative exists, they
  SHALL return an explicit `no_reusable_1h_digest`/non-SLA reason. They SHALL NOT
  show "叙事分析中" merely because the surface window itself is not being
  analyzed.
- **G4 — Admission is capacity-gated.** `NarrativeAdmissionWorker` SHALL admit a
  bounded `1h` frontier sized to the measured semantics service rate. It SHALL
  not admit more source rows per cycle than the semantics lane can enqueue and
  label within the target freshness SLO.
- **G5 — Semantics enqueue cannot be blocked by a small due queue.**
  `MentionSemanticsWorker` SHALL enqueue missing source rows from admitted
  `1h` source sets even when a small number of due rows exists. Claiming and
  enqueueing may share a cycle budget, but existing due rows SHALL NOT starve
  missing rows indefinitely.
- **G6 — Digest readiness can use a partial-complete policy.** A `1h` digest
  SHALL be allowed to refresh when semantic coverage is above the configured
  threshold and the remaining missing rows are below a bounded tolerance. Full
  source-set completeness MAY remain a health signal, but it SHALL NOT be the
  only path to a ready digest.
- **G7 — Throughput test proves drain.** A production-shaped test harness SHALL
  inject a deterministic backlog of `1h` admissions and source rows, then prove
  that semantics enqueue, semantics labeling, and digest refresh drain within a
  bounded number of worker cycles using fake providers and PostgreSQL-backed
  repositories.
- **G8 — Health exposes service-rate math.** Narrative health SHALL report
  current admitted source rows, missing semantics, queued/retryable semantics,
  labeled rows, ready digest count, pending digest count, and computed drain
  estimate for the `1h` lane. The drain estimate SHALL be based on configured
  per-cycle budgets and observed recent success rates, not only raw queue depth.
- **G9 — Rollout has a cleanup path.** The ops rebuild/drain command SHALL
  suppress or terminalize non-`1h` realtime narrative admissions and stale
  current digests, then rebuild the `1h` frontier. No manual SQL is required for
  the hard cut.
- **G10 — Frontend wording matches backend truth.** Token Radar SHALL only show
  "叙事分析中" for an admitted `1h` target with real semantic or digest work due.
  Reused `1h` overlays, non-trigger windows, out-of-frontier rows, insufficient
  source volume, and provider-unavailable rows SHALL render distinct labels.

## Non-goals

- Do not change Token Radar scoring, identity resolution, market capture, or
  factor snapshot contracts.
- Do not remove `5m`, `4h`, or `24h` Token Radar rows.
- Do not make Pulse depend on narrative readiness.
- Do not introduce a central durable `agent_tasks` queue.
- Do not promise a ready digest for every `1h` row. Insufficient source volume,
  low independent-author count, provider unavailability, and low semantic
  coverage remain valid non-ready states.
- Do not fix unrelated worker hard timeouts such as token image mirroring or
  news item briefs in this spec.

## Target architecture

After this change, Token Radar and Narrative have different production scopes:

```text
Token Radar scanner
  -> still projects 5m / 1h / 4h / 24h rows

Narrative realtime lane
  -> admits bounded 1h frontier only
  -> enqueues missing 1h semantics every cycle
  -> labels semantics through the narrative LLM lane
  -> writes ready/status 1h digests
  -> hydrates 1h Token Radar / Token Case with truthful currentness
  -> may fan out same-target 1h digest as an explicit overlay on 5m/4h/24h rows
```

The narrative lane becomes an SLO-bound read model rather than a best-effort
mirror of every scanner window. `5m` remains the fast scanner; `4h/24h` remain
Radar and historical context windows. They can consume the current `1h`
same-target narrative lens, but that lens is not a `4h` or `24h` digest. If
future product work needs true `4h` or `24h` narrative, it must be added as a
separate explicit lane with its own budget and drain tests.

## Conceptual data flow

```text
latest ready 1h Token Radar rows
  -> capacity-gated narrative_admissions
  -> explicit missing semantics enqueue
  -> label mentions with bounded fake/real provider capacity
  -> digest refresh using coverage threshold + missing tolerance
  -> public hydration for 1h rows
  -> read-only same-target 1h overlay for non-trigger Radar windows
```

Changed arrows:

- `Token Radar rows -> narrative_admissions`: filters to `1h` realtime SLA and
  applies a capacity budget.
- `narrative_admissions -> token_mention_semantics`: enqueue runs even when
  there are claimable due rows.
- `token_mention_semantics -> token_discussion_digests`: digest readiness uses
  coverage threshold plus bounded missing tolerance, not absolute zero missing
  rows.
- `token_discussion_digests -> frontend label`: reused `1h` overlays and
  non-trigger states no longer collapse into "叙事分析中".

No new provider arrows are introduced. HTTP routes still only read persisted
read models.

## Core models

**Narrative realtime window**

- The set of windows for which the production service promises realtime
  narrative digest work.
- Initial value: `("1h",)`.
- Scanner windows outside this set are public read states, not work admission
  states.

**Surface narrative overlay**

- A public read-model attachment that lets a non-trigger Radar surface display
  the same target's current `1h` narrative.
- It is valid only when the `1h` digest/admission passes the configured
  compatibility policy for freshness, scope, and schema version.
- It SHALL carry `analysis_window/source_window`, `surface_window`, and
  `reuse_reason` metadata so clients cannot confuse it with a true surface-window
  digest.
- Missing compatible `1h` narrative returns a non-trigger reason instead of
  creating new work for the requested surface window.

**Admission capacity budget**

- Maximum targets and source rows admitted per `1h` cycle.
- Derived from configured semantics enqueue budget, provider batch size,
  digest batch size, and target freshness SLO.
- Prevents admission from creating more new work than downstream workers can
  drain.

**Semantic drain estimate**

- Read-only health calculation:
  `remaining_semantic_work / effective_labeled_rows_per_minute`.
- Uses recent `narrative_model_runs` success/failure and configured worker
  budgets.
- Reports `unknown` when there is not enough recent data.

**Digest partial-complete policy**

- Allows digest refresh when:
  - source volume and author thresholds pass;
  - semantic coverage is at or above the configured threshold;
  - missing/retryable rows are below a bounded tolerance; and
  - no blocking provider/circuit condition is active.
- The digest still carries backlog metadata so the UI can show that more source
  rows are being incorporated.

## Code-level constraints

- `NarrativeRepository.admitted_radar_rows()` and
  `NarrativeRepository.source_set_for_admission()` currently take an exact
  `window`; keep that invariant. The admission worker should call them only for
  configured realtime narrative windows, defaulting to `1h`.
- `NarrativeRepository.current_narrative_snapshots_for_targets()` currently
  performs an exact `(target_type, target_id, window, scope)` lookup. Do not
  change this method into a hidden cross-window fallback because other domain
  reads may rely on exact digest semantics.
- Add the reuse policy as an explicit read-model/hydration path, for example a
  `surface_window -> analysis_window` lookup used by `NarrativeReadModel` for
  Token Radar surfaces. That path may request the `1h` digest for a `5m/4h/24h`
  surface and then decorate the public payload with overlay metadata.
- `public_currentness()` currently evaluates freshness against the supplied
  `window`. A reused overlay must evaluate digest/admission currentness against
  `analysis_window = "1h"`, then separately expose the requested
  `surface_window`. It must not ask `public_currentness()` to judge a `1h` digest
  as though it were a `5m`, `4h`, or `24h` digest.
- `NarrativeRepository.due_digest_targets()` currently reads all due admitted
  rows. After the hard cut, either stale non-`1h` admissions must be terminalized
  by the rollout command or the digest worker must apply the realtime-window
  allowlist before refresh. Otherwise old `4h/24h` admissions can continue to
  consume digest budget.

## Interface contracts

**Worker configuration**

- `narrative_admission.windows` production default becomes `["1h"]`.
- `token_discussion_digest.windows` production default becomes `["1h"]` or is
  ignored in favor of a shared narrative realtime window policy.
- Non-SLA windows must not be silently accepted as realtime digest work by
  default config.

**HTTP `/api/token-radar`**

- For `window=1h`, rows may include `discussion_digest` with `ready`,
  `updating`, `not_ready`, `insufficient`, or `semantic_unavailable` states.
- For `window in {"5m", "4h", "24h"}`, rows must not surface
  `semantic_labeling_pending` as if realtime work is underway unless that window
  is explicitly enabled in config. Default response either attaches a compatible
  same-target `1h` overlay with explicit `analysis_window/source_window` metadata
  or uses an explicit `no_reusable_1h_digest`/non-SLA currentness reason.

**HTTP `/api/status/narrative-health`**

- Must succeed within statement timeout on production-sized tables.
- Must expose `1h` lane backlog and service-rate fields:
  `admitted_targets`, `current_source_rows`, `missing_semantic_rows`,
  `queued_semantic_rows`, `retryable_semantic_rows`, `labeled_source_rows`,
  `ready_digest_targets`, `pending_digest_targets`,
  `estimated_semantic_drain_seconds`, and `estimated_digest_drain_seconds`.

**CLI `ops rebuild-narrative-intel`**

- Must support a hard-cut mode that rebuilds only the realtime narrative window.
- Must clean non-SLA realtime admissions/digests without deleting Radar facts.
- Must report before/after counts by window and scope.

## Acceptance criteria

- **AC1.** WHEN default settings are loaded THEN narrative realtime windows SHALL
  be `["1h"]` and tests SHALL prove `5m`, `4h`, and `24h` are not admitted by
  default.
- **AC2.** WHEN Token Radar is requested for `window=5m`, `4h`, or `24h` under
  default config AND a compatible same-target `1h` digest exists THEN the row
  SHALL include that digest as a read-only overlay with `analysis_window` or
  `source_window = "1h"`, `surface_window = <requested window>`, and a reuse
  reason; it SHALL NOT claim the requested surface window's full source set was
  analyzed.
- **AC2b.** WHEN Token Radar is requested for `window=5m`, `4h`, or `24h` under
  default config AND no compatible same-target `1h` digest exists THEN the row's
  `discussion_digest.currentness` SHALL report an explicit
  `no_reusable_1h_digest`/non-SLA state and SHALL NOT use
  `semantic_labeling_pending` or display "叙事分析中".
- **AC3.** WHEN a `1h` admission has missing source semantics and existing due
  rows also exist THEN `MentionSemanticsWorker.run_once()` SHALL both claim a
  bounded due batch and enqueue a bounded missing batch in the same cycle.
- **AC4.** WHEN a `1h` admission reaches semantic coverage threshold with
  missing rows under tolerance THEN `TokenDiscussionDigestWorker` SHALL be
  allowed to request or publish a ready digest rather than writing only
  `semantic_labeling_pending`.
- **AC5.** WHEN semantic coverage is below threshold or source/author volume is
  insufficient THEN digest status SHALL remain `pending`, `insufficient`, or
  `semantic_unavailable` with the specific reason preserved.
- **AC6.** WHEN the throughput harness seeds a production-shaped `1h` backlog
  using fake providers THEN the configured worker cycle SHALL reduce
  `missing_semantic_rows` to zero or below tolerance and produce ready/status
  digest rows within the expected number of cycles.
- **AC7.** WHEN `/api/status/narrative-health` is called against a database with
  historical `token_radar_rows`, `narrative_admissions`, semantics, and digests
  THEN it SHALL return successfully within statement timeout and include drain
  estimate fields.
- **AC8.** WHEN `ops rebuild-narrative-intel --drain` is run in hard-cut mode
  THEN it SHALL suppress/clean non-`1h` realtime narrative state and report
  before/after counts without deleting Token Radar rows.
- **AC9.** WHEN frontend receives `target_current_1h_narrative`,
  `no_reusable_1h_digest`, `unsupported_window`, `not_in_current_frontier`,
  `insufficient`, `semantic_unavailable`, or `semantic_labeling_pending` THEN it
  SHALL render distinct labels; only the last one may render "叙事分析中".
- **AC10.** WHEN architecture tests scan runtime writes THEN single-writer
  ownership SHALL remain unchanged: admission worker writes
  `narrative_admissions`, semantics worker writes `token_mention_semantics`, and
  digest worker writes `token_discussion_digests`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| 1h-only feels like a feature regression for users browsing 4h/24h | Medium | Reuse compatible same-target `1h` overlays with explicit source-window metadata; keep true 4h/24h narrative as future budgeted lanes. |
| Partial-complete digest could miss late source rows | Medium | Carry backlog metadata in digest/currentness and refresh on material delta or TTL. |
| Admission capacity too low hides useful narratives | Medium | Expose admission skipped/suppressed counts and tune via measured drain rate, not guesswork. |
| Throughput test becomes too synthetic | Medium | Use PostgreSQL-backed repositories and fake providers, seed multiple targets/source volumes, and assert DB-visible state transitions. |
| Health query times out on large historical tables | High | Restrict health calculations to current `1h` admissions and indexed joins; add regression test with seeded historical noise. |
| Operator config still contains old windows | Medium | Hard-cut validation should fail or warn loudly; rollout command reports effective realtime windows. |

## Evolution path

After `1h` is stable, `4h` and `24h` can return as explicit separate lanes:

- own admission limits;
- own semantics/digest budgets;
- own drain SLOs;
- own UI labels;
- own throughput tests.

Do not re-expand windows by simply adding them back to `windows` defaults. A new
window becomes production-supported only when its service rate is measured and
its backlog health has a pass/fail threshold.

## Alternatives considered

- **Raise all LLM budgets and keep every window** — rejected because it treats
  symptoms as capacity shortage while preserving the product/worker mismatch.
  It also increases cost and still fails under bursty Radar arrivals.
- **Keep full semantic completion as the only ready path** — rejected because one
  missing low-value source row can block a digest despite sufficient labeled
  evidence. Full completion should remain a health signal, not the only product
  readiness gate.
- **Show less status in frontend** — rejected because hiding
  `semantic_labeling_pending` does not reduce backlog or fix the operator
  contract.
- **Add a central durable agent task queue now** — rejected because it violates
  the current architecture direction. Domain workers should own product state;
  the execution plane should own provider mechanics.
- **Delete old narrative rows manually** — rejected because production hard cuts
  need repeatable ops commands and audit output.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Realtime Narrative admits only configured SLA windows, defaulting to `1h`; non-trigger Radar surfaces may display compatible same-target `1h` overlays with explicit metadata; health exposes missing semantics and drain estimates; throughput tests prove drain. |
| Ask first | Re-enable `matched`, `4h`, or `24h` narrative lanes; change public labels; relax semantic coverage threshold below current production value. |
| Never | Delete Token Radar facts; call LLM from HTTP routes; present a `1h` overlay as a true 5m/4h/24h digest; hide unsupported windows as "分析中"; introduce a central durable agent queue in this spec. |
