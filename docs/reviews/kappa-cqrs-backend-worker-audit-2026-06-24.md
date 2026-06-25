# Kappa/CQRS Backend Worker Audit - 2026-06-24

Scope: backend runtime, worker manifest, read-model ownership, public API/CLI surfaces, and current Kappa/CQRS hard-cut contracts.

## Sources Read

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKER_FLOW.md`
- `docs/WORKERS.md`
- `docs/RELIABILITY.md`
- `docs/agent-playbook/task-reading-matrix.md`
- `docs/agent-playbook/read-model-change-checklist.md`
- `src/parallax/app/runtime/worker_manifest.py`
- Domain architecture maps under `src/parallax/domains/*/ARCHITECTURE.md`

## Runtime Inventory

- Worker manifests: 26
- Manifest read-model tables: 25
- Queue-health workers: 16
- Wake input channels: 10
- Wake output channels: 11

Worker names:

`collector`, `market_tick_stream`, `market_tick_poll`, `market_tick_current_projection`, `event_anchor_backfill`, `token_capture_tier`, `live_price_gateway`, `resolution_refresh`, `asset_profile_refresh`, `token_image_mirror`, `token_profile_current`, `token_radar_projection`, `narrative_admission`, `news_fetch`, `news_item_process`, `news_item_brief`, `news_story_brief`, `news_page_projection`, `news_source_quality_projection`, `cex_oi_radar_board`, `macro_sync`, `macro_view_projection`, `macro_daily_brief_projection`, `pulse_candidate`, `notification_rule`, `notification_delivery`.

## Read-Model Writer Map

Runtime SQL write scan, excluding migrations, found one runtime write path per manifest read model:

| Read model | Manifest writer |
| --- | --- |
| `cex_detail_snapshots` | `cex_oi_radar_board` |
| `cex_oi_radar_publication_state` | `cex_oi_radar_board` |
| `cex_oi_radar_rows` | `cex_oi_radar_board` |
| `macro_daily_briefs` | `macro_daily_brief_projection` |
| `macro_observation_series_publication_state` | `macro_view_projection` |
| `macro_observation_series_rows` | `macro_view_projection` |
| `macro_view_snapshots` | `macro_view_projection` |
| `market_tick_current` | `market_tick_current_projection` |
| `narrative_admissions` | `narrative_admission` |
| `news_item_agent_briefs` | `news_item_brief` |
| `news_page_rows` | `news_page_projection` |
| `news_source_quality_rows` | `news_source_quality_projection` |
| `news_story_agent_briefs` | `news_story_brief` |
| `projection_offsets` | `token_radar_projection` |
| `pulse_candidate_edge_state` | `pulse_candidate` |
| `pulse_candidates` | `pulse_candidate` |
| `pulse_playbook_snapshots` | `pulse_candidate` |
| `token_capture_tier` | `token_capture_tier` |
| `token_profile_current` | `token_profile_current` |
| `token_radar_current_rows` | `token_radar_projection` |
| `token_radar_publication_state` | `token_radar_projection` |
| `token_radar_rank_source_events` | `token_radar_projection` |
| `token_radar_target_features` | `token_radar_projection` |
| `token_radar_target_first_seen` | `token_radar_projection` |
| `token_score_evaluations` | `token_radar_projection` |

`token_radar_rank_source_events` is written by `TokenRadarRankSourceQuery`, but transaction ownership remains with `TokenRadarRankSourceRepository` / `TokenRadarProjection`. This is not a second runtime writer.

## Audit Conclusions

- Kappa/CQRS read-model single-writer ownership is intact in runtime code.
- Retired online tables such as `token_radar_rows`, `token_radar_rank_history`, `token_radar_snapshot_audit`, `token_radar_projection_coverage`, `news_story_groups`, and `news_story_members` do not reappear in runtime serving paths. Remaining hits are migrations, docs, or architecture guards.
- Public API routes are repository/read-model consumers. No direct API SQL mutation was found outside explicit notification read-state actions.
- CLI ops mutation paths are explicit repair/sync surfaces, not hidden serving compatibility paths.
- Generic `JobQueue` executor dead code is already removed. `job_queue.py` is descriptor-only metadata for ops diagnostics.
- Runtime worker settings are being hardened slice by slice so workers fail on
  malformed non-positive policy values instead of repairing them locally.
  Token Radar, News, and Notification runtime paths now have explicit
  no-one-repair guards; remaining worker setting repairs should be removed only
  with matching focused tests.
- News item-brief rows remain an audit/reuse read model owned by `news_item_brief`.
  Public News serving paths use `news_page_rows` plus current
  `news_story_agent_briefs`; no `news_item_agent_briefs` or item run summary
  fallback was found in page list, item detail, source quality, notifications,
  or page projection.
- Notification rule/delivery follows the expected split: `notification_rule`
  derives persisted notifications from configured read/fact surfaces and
  enqueues external delivery control rows, while `notification_delivery` is a
  leased side-effect consumer over `notification_deliveries`. The delivery
  state machine now requires claim-scoped completion/failure so a stale worker
  cannot overwrite a newer retry attempt.
- Narrative hard-cut contracts were rechecked without code changes. The deleted
  mention-semantics and token-discussion LLM workers/providers/prompts remain
  absent; public Narrative hydration reads current `narrative_admissions` and
  does not expose the retired semantic backlog or write Narrative tables from
  API routes.
- Resolution Refresh / Discovery was rechecked against live read-only queue
  aggregates and the current `DiscoveryRepository` / `ResolutionRefreshWorker`
  code. Current code does not permanently skip over-budget discovery rows:
  `claim_due_lookup_keys(...)` has no `attempt_count < max_attempts` exclusion,
  and claimed exhausted provider-error, provider-unavailable, and hot not-found
  paths delete the active source row and terminalize from the deleted queue
  snapshot. The live high-attempt active backlog was not claim-eligible in the
  sampled probe because `resolution_refresh` was stopped and rows still had to
  pass the queue/result due gate. No live repair mutation or provider fetch was
  run for this check.
- Discovery lookup retry budget is currently carried by active lookup key rather
  than reset on every payload-hash update. This is consistent with treating
  repeated unresolved lookup keys as poison-control-plane work, but it is an
  explicit compatibility boundary: changing it would need a fresh Kappa/CQRS
  decision and tests, because it can re-admit repeatedly observed unresolved
  symbols or addresses.
- A refreshed read-only `resolution_refresh` slice on 2026-06-25 found the
  current code/test contract intact and did not apply a new runtime repair. The
  live queue shape was 3,300 active discovery dirty rows, 9 immediately due
  rows in the SELECT-only probe, 3,291 rows with `last_error`, max active
  attempt count 167, and 8,736 unresolved Queue Terminal rows in the
  `retry_budget_exhausted` bucket. Static scan found no retained due-list
  helper, direct commit fallback, loose DEX candidate reflection, or retired
  compatibility path in `ResolutionRefreshWorker`, `DiscoveryRepository`,
  `RegistryRepository`, the worker factory, or the one-shot ops runner.
- A refreshed read-only `token_radar_projection` slice on 2026-06-25 found
  current/publication serving state healthy and the remaining queue risk
  isolated to source-dirty backlog. The sampled serving layer had 423 current
  rows, 423 distinct stable current keys, 48 ready publication-state rows, and
  no missing current-row payload hashes. The sampled control plane had 0 active
  generic target dirty rows in the SELECT-only probe, then 8 due target dirty
  rows in an adjacent CLI queue-health sample; source dirty had about 269-275
  active rows, about 189-215 due rows, about 257-269 failed rows, max active
  attempt count 4,453, and no unresolved Token Radar Queue Terminal rows. Error
  bucketing was dominated by Asset identity contract/lookup failures, matching
  the already-applied source-dirty batch-isolation repair. No live worker pass,
  queue retry/archive, or serving-row mutation was run.
- A refreshed read-only `macro_view_projection` slice on 2026-06-25 found the
  serving read models healthy but the dirty-target queue still degraded by a
  real feature-engine contract gap. The live queue had 137 active failed
  `macro_projection_dirty_targets`, 0 due rows in the SELECT-only sample, max
  active attempt count 399, and all failures bucketed as
  `feature_frequency_unknown`. The read model had 79,938 current series rows,
  188 latest rows, 0 missing payload hashes, 0 duplicate stable keys, and one
  ready `macro_regime_v4` snapshot. The failing source shape was one core
  concept with three persisted `irregular` frequency series rows; no live queue
  row or read-model row was mutated during the diagnostic.
- A refreshed read-only `token_profile_current` slice on 2026-06-25 found the
  public profile-current chain healthy and did not apply a code repair. An
  adjacent queue-health sample saw 30 due dirty targets with max attempt 0;
  the SELECT-only SQL sample moments later saw 0 active dirty rows, consistent
  with normal worker catch-up. The current read model had 25,890 rows and
  25,890 stable keys, 15,186 ready rows, 10,571 missing rows, 133 unsupported
  CEX rows, 0 error rows, 0 missing payload hashes, 0 missing formal JSON
  fields, and 0 non-local public logo URLs. Static review confirmed the worker
  uses the formal `RepositorySession.source_query`, does not construct ad hoc
  source SQL from `repos.conn`, and admits image mirror source work only through
  `token_image_source_dirty_targets`. The remaining 7 unresolved image-source
  terminal rows are operator triage state, not profile-current projection
  damage.
- A refreshed read-only `event_anchor_backfill` slice on 2026-06-25 found no
  active stuck work and did not apply a code repair. The active queue had 0
  due pending, 0 stale pending, 0 stale running, 0 leased running, and 0
  ready-historical pending jobs. The unresolved terminal ledger contained
  21,727 event-anchor rows, dominated by provider/no-quote/no-market-data
  buckets; these are control-plane terminal evidence and not product truth.
  The fact side remained active, with 199,783 `tier3_inline` market ticks,
  183 rows in the preceding hour, and 201,863 enriched events already attached
  through async backfill. Static review confirmed provider IO occurs outside
  write transactions, terminal retry derives a fresh active window from the
  terminal source snapshot, and job/enriched-event returning writes require
  cursor rowcount evidence.
- A refreshed read-only `market_tick_current_projection` slice on 2026-06-25
  found the current market read model exactly caught up with append-only market
  facts and did not apply a code repair. The live table had 29,500
  `market_tick_current` rows, 29,500 distinct `(target_type, target_id)` stable
  keys, 0 duplicate key groups, 0 missing payload hashes, and 0 stale or
  payload-hash-mismatched rows versus the latest `market_ticks` fact per target.
  The dirty queue had 0 active, due, leased, failed, or unresolved terminal rows;
  Token Radar had 0 active market-dirty rows from the current projection. Static
  review confirmed the runtime writer is `MarketTickCurrentProjectionWorker`;
  `MarketTickCurrentRebuildService` is an operator maintenance path protected by
  the same projection advisory lock, not a concurrent runtime writer.
- A refreshed `token_capture_tier` slice on 2026-06-25 found the capture-control
  projection healthy and one small compatibility hard-cut in the worker's changed
  count accounting. The live read model had 20,672 rows, 20,672 stable keys, 0
  duplicate key groups, 0 missing identities, and 0 invalid tier values; Tier 1
  contained 10 `chain_token` rows and no non-chain targets. The dirty queue had
  one fresh due global rank-set row with attempt count 0, positive source
  watermark, no `last_error`, and no unresolved terminal rows; repeated sampling
  showed the due age being refreshed by ongoing Token Radar rank-set updates
  rather than accumulating high retry attempts. Static review confirmed
  `TokenCaptureTierWorker` is the only runtime writer, has no provider slots,
  reads formal settings directly, and runs claim/projection/done inside one
  `RepositorySession.transaction`.
- A refreshed `market_tick_stream` / `market_tick_poll` writer slice on
  2026-06-25 found the append-only market fact layer fresh and did not apply a
  code repair. Live writer targets were 10 Tier 1 chain tokens, 33 Tier 2 chain
  tokens, and 20 Tier 2 CEX symbols. `market_ticks` had 3,896,373 total facts
  across 29,512 targets, 10,333 facts in the preceding hour, and 0 missing
  identity, tick id, payload hash, or positive price fields. Recent writer lanes
  showed Tier 1 OKX DEX WS, Tier 2 GMGN DEX poll, and Tier 2 Binance CEX poll
  all active; `market_tick_current_dirty_targets` had 0 active rows. Static
  review confirmed provider IO runs outside DB sessions, persistence opens a
  worker transaction only for fact insert plus current-dirty enqueue, and
  `MarketTickRepository` remains append-only with deterministic tick ids and
  cursor rowcount evidence for insert-returning results.
- A refreshed `live_price_gateway` slice on 2026-06-25 confirmed the gateway is
  cache/fan-out only: it reads bounded `token_capture_tier` rows and latest
  `market_ticks`, publishes through the async WebSocket hub contract, and writes
  no facts, read models, control-plane rows, or wake channels. Live diagnostics
  found 59 selected Tier 1/2 targets under the current `target_limit`, all using
  formal market target types, with 38 fresh ticks inside the 300 second TTL. The
  code repair removed the last gateway-local compatibility conversion from old
  `Asset` / `CexToken` target rows to `chain_token` / `cex_symbol`; those
  identities must now be produced formally upstream instead of repaired in the
  presentation fan-out layer.
- A refreshed `token_image_mirror` slice on 2026-06-25 found the local media
  mirror boundary healthy and applied one small rowcount-evidence normalization.
  The live mirror queue had 0 active, due, leased, or failed dirty targets,
  while `token_image_assets` had 17,742 ready local images with 0 missing cache
  files, 0 ready rows missing local metadata, 0 remote public URLs, and 0
  non-ready public URLs. Static review confirmed the worker only claims due
  `token_image_source_dirty_targets`, performs provider/file IO outside the
  claim transaction, writes image lifecycle rows through repository-owned
  transactions with rowcount evidence, and fans out profile-current dirty targets
  using the claimed positive source watermark. The current `source_limit` worker
  setting remains a schema/default-YAML field for existing operator config, but
  it is not a runtime source-scan limit because the mirror now reads only dirty
  targets.
- A refreshed `macro_sync` slice on 2026-06-25 found the macro fact-ingest lane
  healthy and did not apply a code repair. Live `macro_observations` contained
  84,330 fact rows across 188 concepts with 0 missing fact payload hashes; recent
  `macro_sync_runs` were still completing for all configured product bundles.
  `macro_sync_windows` had no running, expired-running, or active over-budget
  rows; the 21 pending due windows all had attempt count 0. Static review
  confirmed provider execution happens after a bounded window claim and outside
  DB sessions, successful imports write observations/import audit/sync audit and
  complete the claimed window inside one unit of work, noop overlaps do not
  enqueue projection dirty targets or wakes, and provider failures record retry
  or failed sync-window state without fabricating observations.
- A refreshed `macro_daily_brief_projection` slice on 2026-06-25 found the
  derived daily-brief read model healthy and did not apply a code repair. Live
  `macro_daily_briefs` had exactly one stable `assets_today` row, 0 missing
  payload hashes, 0 malformed payloads, and a `ready` status/as-of date aligned
  with the current `macro_view_snapshots` row. Static review confirmed the worker
  has no provider IO, reads only the current Macro View snapshot through the
  repository session, writes `macro_daily_briefs` as the only read model with
  stable `brief_key` identity, and excludes `computed_at_ms` from the payload
  hash so unchanged projections write zero serving rows.
- A refreshed News worker-chain slice on 2026-06-25 found the live serving
  read models healthy and applied three code repairs. Live `news_page_rows` had
  6,400 stable rows with 0 missing payload hashes, `news_source_quality_rows`
  had 6 stable source/window rows with 0 missing payload hashes, and
  `news_projection_dirty_targets` had only 4 future source-quality schedule rows
  with 0 due, failed, invalid, missing-hash, missing-watermark, or over-budget
  rows. Static review confirmed `news_fetch` remains provider fact ingest,
  `news_item_process` remains fact lifecycle expansion, story/page/source
  projections have single writers, and public News serving uses story-current
  briefs through `news_page_rows` rather than item-brief fallback. The repairs
  removed News runtime settings one-value repair, terminalized exhausted News
  projection dirty claims through Queue Terminal, and hard-cut stale
  `news_page_projection` wake overrides back to the formal story-current wake
  graph.

## Fixes Applied

1. `TokenRadarProjection.rebuild_dirty_targets(...)` no longer silently repairs non-positive `lease_ms` / `retry_ms` / `max_attempts` with `max(1, int(...))` at the service boundary. It now fails before opening the projection transaction or claiming dirty work.
2. News public agent brief validation helper naming now matches the strict schema-validation contract expected by the architecture harness.
3. `docs/ARCHITECTURE.md` no longer links `watchlist_intel/ARCHITECTURE.md` twice.
4. `docs/WORKER_FLOW.md` no longer says runtime readiness keeps an unused notification-summary helper; it now matches the actual hard-cut contract.
5. Token Radar target/source dirty error completion now uses the formal worker retry budget. Retryable claims are rescheduled; exhausted claims are deleted with `RETURNING queue.*` and written to `worker_queue_terminal_events` in the projection transaction instead of accumulating active high-attempt rows indefinitely.
6. Queue Terminal retry transitions now support Token Radar target/source dirty terminal rows through the formal repository enqueue methods, and `ops queue-resolve-bucket` provides bounded bucket-level dry-run/execute triage for unresolved terminal rows.
7. Token Radar resolved Asset rank changes now fan out to provider-scoped `asset_profile_refresh_targets` so the enabled asset-profile source-cache lane has a normal runtime producer.
8. Macro View Projection dirty-target error completion now uses formal `settings.workers.macro_view_projection.max_attempts`. Retryable claims keep the delayed retry path; exhausted claims are deleted with `RETURNING queue.*` and terminalized in `worker_queue_terminal_events`, and Queue Terminal retry transitions can requeue Macro projection terminal snapshots through formal Macro enqueue methods.
9. Resolution Refresh provider-unavailable handling now uses the same formal retry budget as provider-error and hot not-found paths. Retryable discovery lookup claims are rescheduled, while exhausted claims are deleted and terminalized instead of cycling in the active queue indefinitely.
10. Event Anchor Backfill terminal retry now restores a meaningful active window from the terminal source snapshot when `event_anchor_backfill_jobs` are retried through Queue Terminal. This avoids requeueing old expired terminal jobs at `active_until_ms = now_ms`, which could immediately expire again before a worker claim.
11. Watchlist public contract documentation no longer describes the retired
    summary-agent endpoint, social-event extraction filter, or watchlist summary
    read models. The current contract is a provider-free read over persisted
    `events` plus current token resolutions, and an architecture guard now
    rejects reintroducing the retired public-doc surface.
12. WebSocket public contract documentation no longer advertises the retired
    `social_event_enrichment_update` payload. The documented push surface now
    matches the current API WebSocket code: event, notification, and live market
    updates only.
13. `PulseTriggerDirtyTargetRepository.mark_error(...)` now uses the formal
    `pulse_candidate.max_attempts` retry budget. Retryable trigger claims keep
    the delayed retry path; exhausted claims are deleted with `RETURNING
    queue.*` and terminalized into `worker_queue_terminal_events` in the same
    transaction. Queue Terminal retry transitions can requeue
    `pulse_trigger_dirty_targets` through the formal repository enqueue method.
14. Notification worker factory disabled-state construction no longer probes
    worker settings dynamically with `getattr(workers, name)`. It uses the
    formal `workers.notification_rule` and `workers.notification_delivery`
    settings fields in both enabled and disabled construction paths.
15. Market Tick Current dirty-target error completion now uses the formal
    `market_tick_current_projection.max_attempts` retry budget. Retryable
    claims keep the delayed retry path; exhausted claims are deleted with
    `RETURNING queue.*` and terminalized into `worker_queue_terminal_events` in
    the same transaction. Queue Terminal retry transitions can requeue
    `market_tick_current_dirty_targets` through the formal repository enqueue
    method.
16. Asset Profile Refresh now has a bounded current-row catch-up before provider
    claims. It reads stable default-venue `token_radar_current_rows` Asset
    identities, excludes existing provider source-cache rows and active refresh
    targets, and enqueues missing provider-scoped `asset_profile_refresh_targets`
    with the source row's positive watermark. This fixes the live gap where
    `asset_profile_refresh` was enabled but unchanged historical current rows
    did not seed the source-cache queue.
17. Token Radar source/target dirty `claim_due(...)` paths now require
    PostgreSQL cursor rowcount evidence matching the returned claimed rows.
    The repositories no longer use chained `execute(...).fetchall()` for claim
    mutations, so malformed adapters cannot hand projection code claimed work
    without rowcount proof.
18. The same claim-rowcount contract was applied horizontally to dirty-target
    claim paths for Asset Profile Refresh, Market Tick Current, Token Capture
    Tier, Token Image Source, Token Profile Current, Macro Projection,
    Narrative Admission, and Pulse Trigger. Each claim now keeps the cursor,
    fetches returned rows, and validates PostgreSQL rowcount against those rows
    before any worker can treat the batch as claimed.
19. A broader static pass over DML `RETURNING` paths that fetch multiple rows
    found no additional missing rowcount helpers. Notification read-marker bulk
    writes already use `_returned_write_count(...)`; Token Image Source's
    terminal-delete helper had equivalent inline rowcount matching and was
    normalized to `_returned_rowcount(...)` for consistency.
20. News provider contract validation now treats `runtime.settings.news_intel.sources`
    as a formal settings boundary. Plain mapping sources are rejected with
    `news_provider_settings_contract_required`, readiness marks that contract
    failure unhealthy, and the runtime fallback payload no longer reopens a
    dict/attribute compatibility path.
21. Queue Terminal operator inspection now rejects non-positive limits before
    sampling active queue health, terminal events, or bucket terminal ids. This
    removes the previous `--limit 0` behavior that silently fell back to the
    default sample size.
22. Queue Terminal Macro retry transitions no longer probe Macro repository
    methods with `getattr(..., None)`. The transition now requires the formal
    Macro repository enqueue methods and reports `macro_intel_repository_required`
    when that contract is absent.
23. News provider wiring now requires the formal `FeedFetchResult.feed`
    contract when building provider diagnostics. The helper no longer probes
    `feed_result` with `getattr(..., None)`, so malformed registry/provider
    return objects fail at the integration contract boundary instead of being
    silently treated as diagnostics-free.
24. OKX DEX WebSocket synchronous cleanup now reads the provider's public
    `connection_state_payload()` contract. It no longer probes the private
    `_websocket` attribute, so connected cleanup must use the async close path
    even if internal provider storage changes.
25. Macro feature freshness now formally supports `intraday` frequency with a
    bounded two-day stale window and `irregular` frequency with a conservative
    140-day stale window. Unknown frequencies still fail fast; the feature
    engine does not silently repair them to daily semantics.
26. Token Radar source-dirty projection now isolates affected-target failures.
    One malformed affected target marks only matching source dirty claims
    failed, while successful targets in the same claimed batch can still be
    marked done. This prevents one missing asset-identity contract from
    poisoning an entire source dirty batch.
27. News item agent-brief priority now accepts runtime admission only as the
    formal `NewsItemAgentAdmission` domain result. Loose objects with
    `status` / `reason` / `basis` attributes fail with an explicit contract
    error instead of being reflected as compatibility input.
28. News item brief factory wiring now keeps the retired item-brief wake path
    hard-cut even when runtime config supplies old `wakes_on` channels. The
    worker remains interval-only with an empty wake listener, while
    `news_story_brief` keeps the formal `news_item_processed` wake.
29. The audit-only `news_item_brief_updated` wake-out was removed from the
    current runtime surface. `news_item_brief` had no legitimate consumer for
    that channel after the story-current hard cut, so the manifest, worker,
    `WakeBus`, worker factory dependency injection, and `docs/WORKERS.md`
    now model item-brief as a pure poll/audit worker with no downstream wake
    output.
30. The manifest DB wake graph is now horizontally guarded against orphaned
    and non-`WakeBus` channels. Manifest-only `collector -> event_written` and
    `notification_rule -> notification_delivery_due` outputs were removed,
    real DB wake producers were added for `news_fetch -> news_item_written /
    news_page_dirty`, `news_source_quality_projection -> news_page_dirty`, and
    `event_anchor_backfill -> market_tick_written`, and `docs/WORKERS.md`
    now matches the manifest Wake-out cells. New architecture tests require
    every manifest DB wake output to be exposed by `WakeBus`, have a manifest
    consumer, and have Worker Inventory documentation in lock-step.
31. `PulseCandidateWorker` now records agent backpressure only from the formal
    `AgentCapacityReservation` contract. Loose reservation-like objects and
    string/enum-like `reason` values fail explicitly instead of being reflected
    through `getattr(..., "value", ...)` as compatibility input.
32. `ResolutionRefreshWorker` now consumes DEX discovery candidates only as the
    formal `DexTokenCandidate` provider DTO. Symbol/address matching, provider
    ranking, candidate writes, raw payload hashing, and quality scoring no longer
    reflect arbitrary objects with `chain_id` / `address` / `symbol` attributes;
    malformed provider output fails at the discovery boundary.
33. `NewsItemBriefWorker` and `NewsStoryBriefWorker` now require formal
    `AgentCapacityReservation` objects and `AgentExecutionErrorClass` reason
    values for agent backpressure classification. Loose reservation-like objects
    and string reason aliases no longer pass through `StrEnum` equality or
    generic value reflection; malformed provider/runtime output fails at the
    worker contract boundary.
34. `LiteLLMPulseDecisionClient` now validates `AgentExecutionError.error_class`
    as the formal `AgentExecutionErrorClass` enum before stage-audit timeout
    classification or no-start backpressure handling. String aliases no longer
    pass through `StrEnum` equality and either degrade a stage to timeout or
    rethrow as normal agent backpressure.
35. Asset Market Binance USDT perpetual route sync now consumes formal
    `BinanceUsdtPerpRoute` DTOs at the domain service boundary. The CLI adapter
    maps integration `BinanceUsdmRoute` rows into that DTO explicitly, while the
    service rejects loose route-like objects instead of reflecting
    `native_market_id` / `base_symbol` / `quote_symbol` attributes.
36. `IngestService` now treats token intents and event market captures as formal
    boundary DTOs. Token intent registry, lookup, and alert writes require
    `TokenIntentInput`; event capture commit accepts only `CaptureResult` or
    `EnrichedEventCapture` and rejects loose objects with matching `tick` /
    `capture` attributes before any fact rows are written.
37. `TokenIntentRepository` now accepts only formal `TokenIntentInput` objects
    or mapping rows as write input. Evidence-link writes are taken from
    `TokenIntentInput`; loose `__slots__` objects with token-intent-shaped
    attributes are rejected before SQL instead of being reflected into material
    facts.
38. `TokenEvidenceRepository` now accepts only formal `TokenEvidenceInput`
    objects or mapping rows as write input. Loose `__slots__` evidence-like
    objects are rejected before SQL instead of being reflected into
    `token_evidence` facts.
39. `IntentResolutionRepository` now accepts only formal
    `DeterministicResolution` objects or mapping rows as write input.
    Loose `__slots__` resolution-like objects are rejected before SQL instead
    of being reflected into `token_intent_resolutions` facts.
40. `TokenIntentResolver` now accepts only formal `TokenIntentInput` /
    `TokenEvidenceInput` objects or mapping rows as resolution input. Loose
    intent/evidence objects with similarly named attributes are rejected at the
    resolver boundary instead of being reflected into deterministic decisions.
41. `PulseCandidateWorker` now treats claimed `pulse_agent_jobs.context_json`
    as a formal persisted worker payload. Malformed scalar identity fields,
    gate/edge mapping fields, and list-shaped evidence/timeline fields fail as
    missing job context before evidence packet construction instead of being
    coerced into strings, empty mappings, empty lists, or filtered event refs.
42. `TokenCaptureTierWorker` no longer treats invalid changed-count values from
    its formal tier repository as zero changed rows. Tier upsert and demotion
    paths now accept only boolean or non-negative integer repository results and
    raise `token_capture_tier_changed_count_invalid` instead of reporting zero
    capture-tier work from malformed rowcount evidence.
43. `LivePriceGateway` no longer repairs legacy `Asset` / `CexToken`
    target-type rows into market target keys. The gateway accepts only formal
    `chain_token` / `cex_symbol` rows from `token_capture_tier`, so stale
    upstream identities cannot be silently rewritten in the cache/fan-out layer.
44. `TokenImageSourceDirtyTargetRepository._delete_claims_returning(...)` now
    records cursor rowcount evidence explicitly in the delete-returning helper
    before comparing it with returned exhausted rows. This keeps image-source
    terminalization aligned with the repository rowcount contract instead of
    hiding the proof inside a generic helper call.
45. News runtime workers now read batch, lease, retry, max-attempt, and
    backpressure settings through a strict positive-integer helper. They no
    longer repair malformed or non-positive `settings.workers.news_*` values
    with `max(1, int(...))` at runtime.
46. News projection dirty-target error completion now uses each worker's formal
    `max_attempts` retry budget. Retryable claimed rows keep the delayed retry
    path, while exhausted claims are deleted from
    `news_projection_dirty_targets` and written to
    `worker_queue_terminal_events` with `retry_budget_exhausted` evidence in the
    same repository transaction.
47. News worker factory wiring now hard-cuts `news_page_projection` wake
    channels to the formal graph even when runtime `workers.yaml` still contains
    the retired `news_item_brief_updated` channel. Page projection listens for
    `news_story_brief_updated` plus fact/source dirty wakes; item-brief remains
    interval-only.
48. Notification runtime workers now read batch size and delivery max-attempt
    settings through strict positive-integer helpers. They no longer repair
    malformed non-positive values with `max(1, int(...))` during worker
    construction.
49. `NotificationRepository` now requires positive delivery running timeout,
    stale-running terminalization batch size, and delivery max attempts before
    writing queue rows. Delivery stale-running terminalization now records
    bounded rowcount evidence before the claim path proceeds.
50. Notification delivery completion and failure updates are claim-scoped with
    `status = 'running'`, claimed `attempt_count`, and claimed `updated_at_ms`.
    Late workers with stale delivery claims become zero-row no-ops instead of
    overwriting a newer reclaimed attempt, and both terminal update paths now
    require cursor rowcount evidence.
51. `PulseCandidateWorker` now reads batch, enqueue, capacity, retry, edge
    budget, failure-circuit, trigger-lease, and stale-running terminalization
    settings through strict positive or non-negative integer helpers. It no
    longer repairs malformed runtime settings with `max(1, int(...))` while
    constructing worker state or terminalizing stale running agent jobs.
52. `PulseJobsRepository` now scopes agent job success, failure, backpressure
    release, and provider-cooldown release to the exact claimed job id,
    `attempt_count`, and claimed `updated_at_ms`. A late agent worker with a
    stale claim becomes a zero-row no-op instead of completing, failing, or
    releasing a newer reclaimed attempt.
53. `PulseTriggerDirtyTargetRepository.claim_due(...)` and `mark_error(...)`
    now reject malformed/non-positive claim limits, lease durations, retry
    delays, max attempts, and empty lease owners before SQL. Dirty-trigger
    queue parameters are explicit repository contracts, not runtime one-value
    repairs.
54. `CexOiRadarBoardWorker`, `CexOiRadarRepository`,
    `build_binance_oi_radar_rows(...)`, and CoinGlass detail enrichment now
    reject malformed CEX board limits/settings at their boundaries instead of
    repairing them with `max(1, int(...))` or `max(0, int(...))`. Explicit
    zero remains valid only for the CoinGlass enrichment and level-band disable
    knobs.
55. `NarrativeAdmissionWorker` and `NarrativeAdmissionService` now read
    admission/source limits, lease/retry intervals, retry budget, and admission
    thresholds through strict positive/non-negative helpers instead of repairing
    malformed runtime values. `NarrativeAdmissionWorkerSettings` now declares
    `max_attempts` as a formal worker setting, and
    `NarrativeAdmissionDirtyTargetRepository.claim_due(...)` /
    `mark_error(...)` reject malformed claim limits, lease durations, retry
    delays, max attempts, and empty lease owners before SQL. Exhausted
    Narrative dirty-target claims are deleted with `RETURNING queue.*` and
    terminalized into `worker_queue_terminal_events`; Queue Terminal retry can
    requeue `narrative_admission_dirty_targets` through the formal repository
    enqueue method.
56. Runtime orchestration now treats scheduler, wake-listener sizing, and
    queue-health adapter rows as formal contracts. `WorkerScheduler` rejects
    negative, boolean, or non-numeric shutdown timeouts instead of repairing
    them to zero; `DBPoolBundle` wake-listener capacity rejects malformed
    worker concurrency instead of repairing to one; and Queue Health reports
    malformed adapter rows as unavailable adapter errors instead of converting
    them into empty/idle queue metrics.
57. Collector ingest and `IngestService` now consume
    `event_anchor_backfill.active_window_ms` as a formal positive integer
    contract. `_PooledIngestStore` and the domain service reject zero, negative,
    boolean, or non-integer active-window values instead of repairing malformed
    runtime wiring with `max(1, int(...))` before writing event-anchor backfill
    jobs.
58. `WorkerBase` now treats interval, soft/hard timeout, and backoff settings
    as formal runtime contracts. Zero intervals/timeouts and zero backoff remain
    valid, but negative, boolean, or non-numeric values fail explicitly instead
    of being repaired with `max(0, ...)` or `float(...)` coercions inside the
    shared worker lifecycle loop.
59. `WakeWaiter.wait(...)` and `async_wait(...)` now reject malformed timeout
    arguments before entering the LISTEN loop. Negative, boolean, or non-numeric
    timeout values fail with `wake_waiter_timeout_seconds_required` instead of
    being coerced through `max(0.0, float(timeout))`; elapsed internal remaining
    time is still bounded to zero for normal timeout accounting.
60. `DBPoolBundle` worker-session statement timeout formatting now rejects
    malformed timeout values before setting PostgreSQL `statement_timeout`.
    Negative, boolean, or non-numeric values fail with
    `db_statement_timeout_seconds_required` and discard the checked-out
    connection instead of being coerced into `0ms`.
61. The notification factory's shared local delivery wake helper now uses the
    same timeout contract as PostgreSQL `WakeWaiter`. Malformed local wait
    timeouts fail with `wake_waiter_timeout_seconds_required` instead of being
    coerced through `max(0.0, float(timeout))` before notification delivery
    waits.
62. Model-execution provider wiring now treats agent lane and Pulse pipeline
    timeouts as formal positive runtime contracts. `litellm_pulse_decision`
    setup rejects zero, negative, boolean, or non-numeric lane/pipeline timeout
    values instead of coercing them through `float(...)` before constructing the
    Pulse decision provider.
63. Collector ingest bootstrap now requires the formal `PreparedIngest` object
    returned by `IngestService.prepare_event(...)`. `_prepared_value(...)` no
    longer accepts dict-shaped prepared payloads, so malformed collector ingest
    fakes or compatibility callers fail with `prepared_ingest_contract_required`
    before event-anchor capture/backfill work is derived.
64. The lower-level PostgreSQL client now rejects malformed runtime timeout
    options before composing connection `options`. Statement and
    idle-in-transaction timeout values fail with
    `postgres_runtime_timeout_seconds_required` when they are negative,
    boolean, or non-numeric instead of being converted to `0ms`.
65. Watchlist public read services and repositories now treat window and sample
    limits as formal read-path contracts. Malformed window days, overview
    source/cluster limits, and timeline limits fail before SQL with explicit
    watchlist contract errors instead of being repaired with `max(1, int(...))`
    or `max(0, int(...))`.
66. Event Anchor Backfill worker and job repository now treat runtime sizing,
    lease, active-window, stale-retry, and terminal snapshot windows as formal
    contracts. Malformed worker settings or repository parameters fail before
    provider work, SQL, or transactions with explicit event-anchor contract
    errors instead of being repaired with `max(1, int(...))`,
    `max(0, int(...))`, or `max(1, active_until_ms - created_at_ms)`.
67. Asset Market live market runtime entrypoints now reject malformed worker
    sizing and fan-out settings at the boundary. `market_tick_poll`,
    `market_tick_stream`, `live_price_gateway`, and `token_capture_tier`
    no longer coerce batch/concurrency/subscription/target/tier limits, TTLs,
    claim leases, or `project_once` projection limits through `max(...,
    int/float(...))` before touching providers, SQL, or dirty-target claims.
68. Asset Market current/profile refresh workers now reject malformed claim,
    retry, and refresh-policy settings before queue writes or provider work.
    `market_tick_current_projection`, `token_profile_current`,
    `token_image_mirror`, and `asset_profile_refresh` no longer repair
    batch sizes, leases, retry delays, max attempts, provider retry delays, or
    ready/missing/error refresh intervals with `max(1, int(...))`.
69. Resolution Refresh now rejects malformed discovery and reprocess runtime
    settings at the worker boundary. Max attempts, lease duration,
    hot-not-found retry delay, discovery batch size, reprocess limit, and
    helper retry-budget inputs fail with explicit resolution-refresh contract
    errors instead of being coerced through `max(1, int(...))`.
70. Macro Sync and Macro View Projection now reject malformed worker batch,
    lookback, per-series, lease, retry, and max-attempt settings before sync
    claim loops, macro dirty-target claims, source refresh, or dirty-target
    error writes. Macro worker runtime settings are no longer repaired with
    `max(1, int(...))` at execution time.
71. Token Radar Projection worker runtime settings now fail as explicit
    contracts before dirty-target claims, projection service calls, or private
    cache retention pruning. Batch size, lease, retry, max attempts, retention
    enablement, retention TTL, cold interval, debug override limit, and elapsed
    interval inputs no longer use runtime `max/int/float/bool` repair.
72. Macro repository projection/history entrypoints now reject malformed
    dirty-target claim limits, leases, retry delays, max attempts, latest
    observation limits, source-refresh history windows, per-series limits, and
    concept-history lookbacks before SQL or transactions. This closes the
    repository side of the Macro Sync/View control-plane hard cut.
73. News Page Projection and News Source Quality Projection workers now
    validate batch, lease, retry, and max-attempt settings before opening
    repository sessions or dirty-target transactions. Their architecture tests
    now enforce the shared `positive_worker_setting_int` contract rather than
    stale `max(1, int(...))` expectations.
74. News Item Brief and Story Brief workers now reject malformed queue-depth
    and reservation claim-limit values before LLM capacity reservation,
    dirty-target claims, or repository sessions. Queue depth must be a
    nonnegative integer, claim limits must be positive integers, and neither
    path can be silently repaired to `1`.
75. News runtime shared setting helpers now expose explicit positive and
    nonnegative integer contracts for non-settings values, so Item/Story brief
    workers use the same strict boundary for queue depth and reservation
    limits as they already use for worker settings.
76. News Projection Dirty Target repository now rejects malformed claim
    leases, claim limits, and retry delays before transactions or SQL. The
    shared News projection control-plane path no longer repairs those values
    with `max(..., int(...))` in repository-owned claim/error mutations.
77. Token Radar target/source dirty repositories now reject malformed claim
    limits, claim leases, retry delays, max attempts, and bounded repair/list
    limits before transactions or SQL. The Token Radar projection control
    plane no longer repairs queue policy values with `max(..., int(...))` at
    repository boundaries.
78. Market Tick Current dirty-target repository now rejects malformed claim
    limits, claim leases, retry delays, max attempts, and claimed attempt
    counts before transactions or SQL. The market-current projection control
    plane no longer repairs those queue policy values with `max(...,
    int(...))` in repository-owned mutations.
79. Asset Profile Refresh target repository now rejects malformed bounded
    backfill limits, claim limits, claim leases, retry delays, and claimed
    attempt counts before transactions or SQL. Provider profile refresh
    scheduling no longer repairs those control-plane values with `max(...,
    int(...))` at repository boundaries.
80. Token Profile Current dirty-target repository now rejects malformed claim
    limits, claim leases, retry delays, and claimed attempt counts before
    transactions or SQL. The current-profile projection control plane no
    longer repairs those queue policy values with `max(..., int(...))` in
    repository-owned mutations.
81. Token Image Source dirty-target repository now rejects malformed claim
    limits, claim leases, retry delays, max attempts, and claimed attempt
    counts before transactions or SQL. The image mirror control plane no
    longer repairs those queue policy values with `max(..., int(...))` or
    string-to-int max-attempt compatibility at repository boundaries.
82. Token Capture Tier dirty-target repository now rejects malformed claim
    limits, claim leases, and claimed attempt counts before transactions or
    SQL. Rank-set projection completion now consumes a formal claim token
    instead of converting completion attempt counts while building SQL params.
83. Discovery lookup control-plane repository now rejects malformed enqueue
    intent counts, claim limits, claim leases, running timeouts, hot
    not-found retry windows, and claimed attempt counts before transactions or
    SQL. Resolution Refresh discovery lookup claims and result-start timeouts
    no longer repair those queue policy values with `max(..., int(...))` or
    optional timestamp string conversion.
84. News Projection Dirty Target completion now rejects malformed claimed
    attempt counts before transactions or SQL. Page, story, source-quality,
    and brief-input projection completion no longer accepts `0`, bools, or
    string attempt counts through `int(key["attempt_count"])`.
85. Narrative Admission dirty-target completion now rejects malformed claimed
    attempt counts before transactions or SQL. Narrative admission done/error/
    reschedule completion now follows the documented positive claim-token
    contract instead of accepting bool or string attempts.
86. Pulse Trigger dirty-target completion now rejects malformed claimed
    attempt counts before transactions or SQL. Pulse dirty done/error/
    reschedule completion now follows the formal positive claim-token contract
    instead of accepting bool or string attempts.
87. News source fetch/canonical rebuild repository parameters now reject
    malformed source refresh intervals, canonical rebuild limits, source claim
    limits, and source claim leases before SQL. The News source fetch and
    canonical rebuild control paths no longer repair those values with
    `max(..., int(...))` in the reviewed functions.
88. News public page/high-signal read-path limits now reject malformed values
    before SQL. Public News page rows and high-signal notification candidates
    no longer repair request limits with `max(0, int(limit))` in the reviewed
    serving read functions.
89. News item processing claim parameters now reject malformed claim limits
    and leases before SQL. The raw/retryable item claim path no longer repairs
    worker claim policy values with `max(0, int(limit))` or
    `max(1, int(lease_ms))` inside the repository-owned mutation.
90. News current-brief schema maintenance now rejects malformed cleanup list
    limits before SQL. The stale schema cleanup selector no longer repairs
    operator maintenance limits with `max(1, int(limit))`.
91. News source-quality projection input queries now reject malformed window
    durations before SQL. Source-quality aggregate reads no longer repair
    projection window policy values with `max(1, int(window_ms))`.
92. News dedup diagnostics now reject malformed diagnostic windows at both CLI
    and repository boundaries. The operator command no longer clamps negative
    `--window-hours`, and the repository no longer repairs `window_ms` with
    `max(0, int(...))` or SQL `GREATEST`.
93. Notification read/list repository paths now reject malformed limits before
    SQL. Notification and delivery list reads no longer repair list limits with
    `max(0, int(limit))`.
94. News canonical rebuild operator limits now reject malformed values at the
    CLI and ops helper boundaries. The operator rebuild flow no longer repairs
    limits before calling the strict News repository selector.
95. Evidence and entity read repositories now reject malformed limits before
    SQL. Event, token-filter, and entity lookup reads no longer repair caller
    limits with `max(0, int(...))`.
96. Token intent and lookup read repositories now reject malformed limits
    before SQL. Recent unresolved intent reads and lookup-key intent reads no
    longer repair caller limits with `max(0, int(limit))`.
97. Token Capture Tier repository read paths now reject malformed limits before
    SQL. Tier list and live target reads no longer repair caller limits with
    `max(0, int(limit))`.
98. Registry ranked live-market target reads now reject malformed limits before
    SQL. The asset/cex target candidate query no longer repairs caller limits
    with `max(0, int(limit))`.
99. Projection repository diagnostic and claim reads now reject malformed
    limits before SQL. Projection run lists, dirty-range claims, and dirty-range
    lists no longer repair caller limits with `max(0, int(limit))`.
100. Signal alert and Token Target timeline read paths now reject malformed
     limits before SQL. Account alert reads and target timeline reads no longer
     repair caller limits with `max(0, int(limit))`; the event-id timeline keeps
     its explicit `limit=0` empty/no-SQL contract.
101. Account Quality token-row, Event Rebuild recent-event, and Token Radar
     Rank Source prune/chunk boundaries now reject malformed values before SQL
     or batching. Account Quality and Event Rebuild keep explicit `limit=0`
     empty-page semantics, while Rank Source prune/chunk budgets require
     positive integers instead of repairing `0` or strings to a live delete or
     batch.
102. Token Target posts/timeline and Asset Flow read-model services now reject
     malformed limits before repository reads. Public token-target pagination
     and asset-flow row fetches no longer repair negative, bool, or string
     limits; `limit=0` remains an explicit empty-page contract.
103. Token Search service and SearchEvents query limits now reject malformed
     values before route selection or SQL. Search page limits, route limits,
     target page limits, and fallback route limits no longer repair negative,
     bool, or string values with `max(0, int(...))`; `limit=0` remains an
     explicit empty-page/no-SQL route contract where applicable.
104. Catalyst Ranking, Stocks Radar, and Token Factor Evaluation service limits
     now reject malformed values before scoring, read-model queries, or
     evaluation repository reads. These services no longer repair negative,
     bool, or string limits with `max(0, int(limit))`; `limit=0` remains an
     explicit empty-result contract.
105. Token Radar private-cache pruning, current-row reads, target-feature
     pruning, and lane ranking now reject malformed limits before transactions,
     SQL, or rank selection. Private-cache retention/limit budgets require
     positive integers, serving current-row reads keep explicit nonnegative
     limits, and rank-lane selection no longer repairs malformed limits.
106. News Page query, Narrative admission upsert, and Search Inspect limits
     now reject malformed values before repository calls, write transactions,
     or token dossier hydration. These paths no longer repair `0`, negative,
     bool, or string limits into one-row work.
107. API limit validators, Token Case posts limit, Token Radar/Capture Tier
     operator enqueue limits, Token Profile image repair limits, and Market
     Tick stream subscription target selection now reject malformed boundaries
     before repository reads, repair transactions, provider stream target
     construction, or DB bundle creation. Public API nonnegative limits keep
     explicit `limit=0` empty-page semantics, while one-shot repair/positive
     page-size paths now fail fast instead of repairing `0` or negative values
     into live work.
108. Market Tick Stream and OKX DEX WebSocket subscription boundaries now share
     the formal positive subscription-limit contract from runtime settings.
     Direct worker construction, stream target selection, OKX WS provider
     construction, subscription-arg selection, and circuit-failure thresholds
     now reject malformed values instead of repairing `0`, negative, bool, or
     string inputs into one live subscription or one circuit attempt.
109. GMGN OpenAPI, RSS-like FeedClient, OpenNews REST, and CryptoPanic provider
     parameter boundaries now reject malformed request-governor values before
     provider calls or transport construction. GMGN token kline limits, gateway
     rate/retry/cache settings, FeedClient retry/timeout settings, OpenNews REST
     page and policy integers, and CryptoPanic `max_items` no longer repair
     `0`, negative, bool, or malformed values into live provider requests.
110. Macro sync scheduler boundaries now reject malformed bootstrap lookback,
     window width, steady overlap, steady interval, bootstrap cycle cap, and
     max-attempt values before reading scheduler state or enqueueing macro sync
     windows. MacroSyncService now passes formal settings fields through to the
     scheduler/operator enqueue paths instead of repairing selected values with
     `int(...)` casts.
111. Dirty-target enqueue conflict handling now resets `attempt_count` only
     when the effective work payload changes. Same-payload retries preserve
     their retry budget, while fresh payload hashes no longer inherit stale
     over-budget attempts from earlier failed work.
112. News page projection direct builder paths now build search text from a
     formal search-document payload extracted from the page row. Token,
     fact, story, and source fields remain searchable without reintroducing
     retired search aliases into the canonical `news_page_search` helper.
113. News story/source-quality and worker-status regression fixtures were
     upgraded to the current runtime contracts: story agent rows carry formal
     LiteLLM backend evidence, source-quality aggregation uses current story
     briefs, News fetch settings use `NewsSourceConfig`, projection workers
     declare explicit `max_attempts`, dirty-target failure calls provide
     worker/max-attempt evidence, and worker-status fakes expose Queue
     Terminal metrics.
114. Generated schema documentation was refreshed after the story-agent table
     additions. `docs/generated/db-schema.md` now includes
     `news_story_agent_runs` and `news_story_agent_briefs`, so
     `make docs-generated` is clean again.
115. GMGN OpenAPI gateway route weights and provider cooldowns now use formal
     numeric contracts. Malformed route weights and malformed provider
     cooldowns from unavailable-provider exceptions fail explicitly instead of
     being clamped to zero-token or zero-cooldown behavior.
116. Macrodata bundle runner timeout handling now requires a finite timeout
     of at least one second at the runner boundary. It no longer repairs
     zero, negative, boolean, or string timeout settings with
     `max(1.0, float(...))` before invoking the external macrodata CLI.

## Verification

Commands run:

```bash
uv run pytest tests/architecture -q
uv run pytest tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_projection.py tests/unit/domains/token_intel/test_token_radar_market_only_projection.py -q
uv run pytest tests/unit/test_cli_queue_ops.py tests/unit/test_queue_terminal.py tests/architecture/test_token_radar_source_width_contract.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py -q
uv run pytest tests/golden/test_token_radar_corpus.py tests/integration/test_cli.py tests/integration/test_token_radar_idempotency.py -q
uv run pytest tests/unit/test_token_radar_projection.py -q
uv run pytest tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/unit/test_cli_queue_ops.py -q
uv run pytest tests/unit/test_settings.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/architecture/test_macro_kappa_contract.py -q
uv run pytest tests/unit/test_resolution_refresh_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_terminal_returning_counts_require_cursor_rowcount_match tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_claim_due_requires_returning_rowcount_match tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_terminal_paths_require_connection_transaction_without_nullcontext -q
uv run pytest tests/integration/test_resolution_refresh_worker.py::test_discovery_terminalize_claimed_payload_hash_deletes_active_row -q
uv run pytest tests/unit/test_event_anchor_backfill_job_repository.py tests/unit/test_event_anchor_backfill_worker.py tests/unit/test_cli_queue_ops.py -q
uv run pytest tests/unit/test_api_news_contract.py -q
uv run pytest tests/unit/test_api_news_contract.py::test_news_public_agent_brief_requires_status_without_pending_default tests/unit/test_api_news_contract.py::test_news_public_agent_brief_rejects_malformed_optional_text_fields tests/unit/test_api_news_contract.py::test_news_public_agent_brief_ignores_present_brief_json_without_scalar_repair tests/unit/test_notification_rules.py::test_news_high_signal_public_agent_brief_rejects_malformed_optional_text_without_payload_passthrough -q
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_current_write_does_not_dirty_page_projection tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_process_enqueues_story_brief_not_item_brief_after_hard_cut tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_detail_requires_projected_page_row_contract_without_raw_item_fallbacks tests/architecture/test_news_intel_kiss_simplification.py::test_news_agent_admission_representative_current_state_uses_story_current tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_agent_status_has_no_secondary_pending_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_story_brief_packet_requires_story_context_without_item_fallback tests/architecture/test_news_intel_kiss_simplification.py::test_news_high_signal_ready_brief_public_signal_fields_do_not_use_projection_fallbacks tests/unit/test_api_news_contract.py tests/unit/test_notification_rules.py::test_news_high_signal_requires_projected_representative_identity_without_item_fallback tests/unit/test_notification_rules.py::test_news_high_signal_external_push_requires_current_summary_without_market_read_fallback tests/unit/test_notification_rules.py::test_news_high_signal_external_push_and_payload_require_ready_brief_signal_fields_without_display_signal_fallback -q
uv run pytest tests/architecture/test_watchlist_agent_hard_cut.py tests/architecture/test_api_read_paths_provider_free.py::test_watchlist_handle_overview_bounds_source_sample_without_repository_defaults tests/unit/watchlist/test_watchlist_intel_api.py tests/unit/watchlist/test_watchlist_overview_api.py -q
uv run pytest tests/architecture/test_public_contracts_doc_alignment.py tests/architecture/test_watchlist_agent_hard_cut.py -q
uv run pytest tests/architecture/test_agent_harness_cleanup_contracts.py::test_narrative_llm_workers_are_hard_removed_from_runtime_contract tests/architecture/test_agent_harness_cleanup_contracts.py::test_narrative_llm_provider_client_and_prompts_are_removed tests/architecture/test_agent_input_identity_contracts.py::test_deleted_narrative_llm_agents_do_not_reintroduce_input_hash_paths tests/architecture/test_worker_runtime_contracts.py::test_narrative_hard_cut_contracts_are_documented tests/architecture/test_worker_runtime_contracts.py::test_global_architecture_does_not_describe_retired_narrative_llm_lanes_as_current tests/architecture/test_worker_runtime_contracts.py::test_public_narrative_reads_do_not_expose_retired_semantic_backlog tests/architecture/test_worker_runtime_contracts.py::test_deleted_narrative_llm_workers_are_not_runtime_contracts tests/architecture/test_worker_runtime_contracts.py::test_no_exact_fingerprint_only_public_narrative_hydration tests/architecture/test_worker_runtime_contracts.py::test_removed_narrative_llm_writer_methods_are_not_repository_contracts tests/architecture/test_worker_runtime_contracts.py::test_token_radar_narrative_read_model_does_not_reuse_1h_digest_for_other_windows tests/architecture/test_worker_runtime_contracts.py::test_token_radar_narrative_read_model_requires_formal_target_identity_without_type_id_aliases tests/architecture/test_worker_runtime_contracts.py::test_narrative_runtime_does_not_keep_removed_digest_not_ready_reason tests/architecture/test_worker_runtime_contracts.py::test_deleted_narrative_llm_service_modules_are_not_runtime_contracts tests/architecture/test_worker_runtime_contracts.py::test_api_routes_do_not_import_narrative_providers_or_write_narrative_tables -q
uv run pytest tests/architecture/test_pulse_no_compat.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_cli_queue_ops.py -q
uv run pytest tests/architecture/test_notifications_hard_cut.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_notification_workers_with_shared_local_wake_waiter tests/unit/test_bootstrap_worker_runtime_wiring.py::test_notification_delivery_without_enabled_channel_is_disabled_not_unavailable -q
uv run pytest tests/unit/test_notification_rules.py tests/unit/test_notification_worker_runtime.py tests/integration/test_notification_delivery.py tests/integration/test_notification_worker.py -q
uv run pytest tests/unit/test_market_tick_current_repository.py tests/unit/test_market_tick_current_projection_worker.py tests/unit/test_cli_queue_ops.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_runtime_worker_constraint_hard_cut.py -q
uv run pytest tests/unit/test_market_tick_stream_worker.py tests/unit/test_market_tick_poll_worker.py tests/unit/test_live_price_gateway.py tests/unit/test_market_tick_repository.py tests/unit/test_token_capture_tier_worker.py tests/unit/test_token_capture_tier_repository.py tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/unit/domains/asset_market/test_token_capture_tier_repository.py -q
uv run pytest tests/unit/test_live_price_gateway.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_live_price_gateway_publish_uses_async_hub_contract_without_isawaitable_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_live_price_gateway_target_rows_use_formal_market_target_types_without_legacy_repair tests/architecture/test_worker_runtime_contracts.py::test_live_price_gateway_constructor_uses_formal_settings_contract_without_synthetic_defaults tests/architecture/test_runtime_lifecycle_hard_cut.py::test_manifest_classifies_cache_and_delivery_without_product_fact_drift -q
uv run pytest tests/unit/test_token_image_mirror.py tests/unit/test_token_image_mirror_worker.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/domains/asset_market/test_token_image_asset_repository.py tests/architecture/test_worker_runtime_contracts.py::test_token_image_mirror_worker_uses_formal_settings_contract_without_runtime_defaults tests/architecture/test_worker_runtime_contracts.py::test_token_image_mirror_is_only_token_image_assets_writer tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_completion_counts_require_real_cursor_rowcount tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_target_source_watermark_has_no_runtime_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_asset_repository_uses_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_asset_lifecycle_writes_require_real_cursor_rowcount tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_completion_requires_claim_source_url_hash_without_fallback -q
uv run pytest tests/unit/domains/macro_intel/test_macro_sync_worker.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_fact_import_change_semantics.py tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_is_fact_ingest_and_projection_remains_read_model_writer tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_bundle_import_requires_session_unit_of_work_without_conn_transaction_fallback tests/architecture/test_macro_no_compatibility_contract.py::test_macro_sync_queue_summary_requires_repository_contract_without_optional_probe tests/architecture/test_macro_no_compatibility_contract.py::test_macrodata_runner_and_sync_service_use_formal_fred_and_timeout_settings_without_provider_shape_fallback tests/architecture/test_macro_no_compatibility_contract.py::test_macro_sync_window_returning_writes_require_cursor_rowcount_match -q
uv run pytest tests/unit/domains/macro_intel/test_macro_daily_brief.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_upsert_macro_daily_brief_is_stable_key_payload_hash_read_model tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_upsert_macro_daily_brief_requires_returning_rowcount_match tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys tests/architecture/test_worker_runtime_contracts.py::test_macro_daily_brief_projection_worker_uses_formal_settings_contract_without_runtime_defaults tests/architecture/test_macro_kappa_contract.py::test_macro_daily_brief_worker_is_projection_read_model_without_provider_io tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_is_fact_ingest_and_projection_remains_read_model_writer -q
uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_fetch_by_default tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_hard_cuts_news_page_projection_retired_item_brief_wake_override tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_keeps_news_item_brief_interval_only_when_config_overrides_wakes tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_story_brief_when_configured tests/architecture/test_news_intel_kiss_simplification.py::test_news_runtime_worker_settings_require_positive_int_without_runtime_one_repair tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_error_paths_use_worker_retry_budget_terminalization tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_projection_work.py tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/domains/news_intel/test_news_source_quality_dirty_targets.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/domains/news_intel/test_news_story_brief_worker.py tests/unit/domains/news_intel/test_news_page_projection.py -q
uv run ruff check src/parallax/app/runtime/worker_factories/news_intel.py src/parallax/domains/news_intel/runtime/news_runtime_settings.py src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/runtime/news_item_process_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/runtime/news_page_projection_worker.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py src/parallax/domains/news_intel/runtime/news_projection_work.py tests/architecture/test_news_intel_kiss_simplification.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py
uv run mypy src/parallax/app/runtime/worker_factories/news_intel.py src/parallax/domains/news_intel/runtime/news_runtime_settings.py src/parallax/domains/news_intel/runtime/news_fetch_worker.py src/parallax/domains/news_intel/runtime/news_item_process_worker.py src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/domains/news_intel/runtime/news_story_brief_worker.py src/parallax/domains/news_intel/runtime/news_page_projection_worker.py src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py src/parallax/domains/news_intel/runtime/news_projection_work.py
uv run pytest tests/architecture/test_notifications_hard_cut.py tests/unit/test_notification_worker_runtime.py tests/integration/test_notification_repository.py tests/integration/test_notification_delivery.py -q
uv run ruff check src/parallax/domains/notifications/runtime/notification_runtime_settings.py src/parallax/domains/notifications/runtime/notification_worker.py src/parallax/domains/notifications/runtime/notification_delivery.py src/parallax/domains/notifications/repositories/notification_repository.py tests/architecture/test_notifications_hard_cut.py tests/unit/test_notification_worker_runtime.py tests/integration/test_notification_repository.py tests/integration/test_notification_delivery.py
uv run mypy src/parallax/domains/notifications/runtime/notification_runtime_settings.py src/parallax/domains/notifications/runtime/notification_worker.py src/parallax/domains/notifications/runtime/notification_delivery.py src/parallax/domains/notifications/repositories/notification_repository.py
uv run pytest tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_pulse_no_compat.py tests/architecture/test_worker_runtime_contracts.py::test_pulse_candidate_worker_and_job_service_use_formal_settings_without_runtime_defaults tests/integration/test_pulse_repositories.py -q
uv run ruff check src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py tests/architecture/test_pulse_no_compat.py tests/architecture/test_worker_runtime_contracts.py tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/test_pulse_candidate_worker.py tests/integration/test_pulse_repositories.py
uv run mypy src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py
uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py tests/unit/domains/cex_market_intel/test_binance_oi_radar_builder.py tests/unit/domains/cex_market_intel/test_coinglass_detail_enricher.py tests/architecture/test_cex_oi_kappa_contract.py tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_board_worker_uses_formal_settings_and_provider_contract_without_runtime_defaults -q
uv run pytest tests/unit/test_cex_market_intel_provider_wiring.py tests/unit/test_api_cex_contract.py tests/architecture/test_worker_manifest_static_contracts.py tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_runtime_uses_current_board_lifecycle tests/architecture/test_worker_runtime_contracts.py::test_cex_oi_radar_manifest_uses_current_board_lifecycle tests/architecture/test_worker_runtime_contracts.py::test_cex_market_intel_provider_wiring_uses_formal_worker_settings_fields_without_defaults -q
uv run pytest tests/architecture/test_runtime_lifecycle_hard_cut.py::test_cex_failure_attempts_do_not_clear_current_board_rows -q
uv run ruff check src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py src/parallax/domains/cex_market_intel/services/coinglass_detail_enricher.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py tests/unit/domains/cex_market_intel/test_binance_oi_radar_builder.py tests/unit/domains/cex_market_intel/test_coinglass_detail_enricher.py tests/architecture/test_cex_oi_kappa_contract.py tests/architecture/test_worker_runtime_contracts.py
uv run mypy src/parallax/domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py src/parallax/domains/cex_market_intel/services/binance_oi_radar_builder.py src/parallax/domains/cex_market_intel/services/coinglass_detail_enricher.py
uv run pytest tests/unit/test_asset_profile_refresh_worker.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/domains/asset_market/test_asset_profile_repository.py -q
uv run pytest tests/unit/test_token_profile_current_worker.py tests/unit/test_token_profile_current_projection.py tests/unit/test_token_profile_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/test_token_image_source_admission.py tests/unit/test_token_image_mirror_worker.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/domains/asset_market/test_token_image_asset_repository.py -q
uv run pytest tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/test_token_profile_current_worker.py tests/unit/test_token_profile_current_projection.py tests/unit/test_token_profile_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_repository.py tests/architecture/test_token_profile_current_hard_cut.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_dirty_repository_queue_policy_rejects_runtime_int_repair tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_profile_current_dirty_completion_counts_require_real_cursor_rowcount -q
uv run pytest tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/test_token_image_mirror_worker.py tests/unit/test_token_image_mirror.py tests/unit/test_token_image_source_admission.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_repository_queue_policy_rejects_runtime_int_repair tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_completion_counts_require_real_cursor_rowcount tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_image_source_dirty_target_source_watermark_has_no_runtime_fallback -q
uv run pytest tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/unit/test_token_capture_tier_worker.py tests/unit/test_token_capture_tier_repository.py tests/unit/domains/asset_market/test_token_capture_tier_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_dirty_repository_queue_policy_rejects_runtime_int_repair tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_dirty_write_counts_require_real_cursor_rowcount tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_dirty_enqueue_source_watermark_has_no_row_or_runtime_fallback -q
uv run pytest tests/unit/test_discovery_repository.py tests/unit/test_resolution_refresh_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_completion_keys_require_claim_attempt_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_queue_policy_rejects_runtime_int_repair tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_lookup_write_counts_require_real_cursor_rowcount tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_claim_due_requires_returning_rowcount_match tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_repository_result_writes_require_rowcount_without_readback_fallback -q
uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_target_completion_keys_require_claim_attempt_contract tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_completion_counts_require_real_cursor_rowcount -q
uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/narrative_intel/test_narrative_workers.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_discovery_and_narrative_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_narrative_admission_dirty_completion_counts_require_real_cursor_rowcount tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_narrative_admission_dirty_claim_and_retry_contracts_reject_runtime_repairs -q
uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_completion_keys_require_claim_attempt_contract tests/architecture/test_pulse_no_compat.py::test_pulse_trigger_dirty_claim_and_retry_contracts_reject_runtime_repairs -q
uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_canonical_rebuild_list_reads_only_current_servable_news_items tests/unit/domains/news_intel/test_news_repository_queries.py::test_canonical_rebuild_list_rejects_malformed_limit_before_sql tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_due_sources_returning_counts_require_cursor_rowcount tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_due_sources_returning_counts_reject_invalid_or_mismatched_rowcount tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_due_sources_returning_counts_accept_zero_row_noop tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_due_sources_returning_counts_accept_matching_claim_rows tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_due_sources_rejects_malformed_parameters_before_sql tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_repository_source_reconcile_noop_does_not_update_timestamp tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_repository_material_source_reconcile_reports_updated_status tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_repository_upsert_source_rejects_malformed_refresh_interval_before_sql tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_claim_due_sources_returning_counts_require_cursor_rowcount_match tests/architecture/test_news_intel_kiss_simplification.py::test_ops_news_canonical_rebuild_reads_current_servable_story_keyset tests/architecture/test_news_intel_kiss_simplification.py::test_news_repository_source_fetch_policy_numbers_reject_runtime_repairs -q
uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_news_page_rows_requires_formal_projected_sections_without_public_defaults tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_news_page_rows_rejects_malformed_limit_before_sql tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_news_page_rows_omits_blank_optional_text_from_failed_agent_brief tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_news_page_rows_filters_and_requires_macro_event_flow_when_requested tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_news_page_rows_rejects_macro_event_flow_rows_without_projection_contract tests/unit/domains/news_intel/test_news_repository_queries.py::test_high_signal_notification_candidates_require_projected_agent_brief_without_pending_fallback tests/unit/domains/news_intel/test_news_repository_queries.py::test_high_signal_notification_candidates_reject_malformed_limit_before_sql tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_list_requires_projected_page_row_contract_without_public_defaults -q
uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_unprocessed_item_loader_selects_provider_article_keys_for_story_identity tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_unprocessed_items_returning_rows_require_cursor_rowcount tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_unprocessed_items_returning_rows_reject_invalid_or_mismatched_rowcount tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_unprocessed_items_returning_rows_accept_zero_row_noop tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_unprocessed_items_returning_rows_accept_matching_claim_rows tests/unit/domains/news_intel/test_news_repository_queries.py::test_claim_unprocessed_items_rejects_malformed_parameters_before_sql tests/architecture/test_news_intel_kiss_simplification.py::test_news_claim_unprocessed_items_returning_rows_require_cursor_rowcount_match -q
uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_current_brief_ids_outside_schema_uses_explicit_limit tests/unit/domains/news_intel/test_news_repository_queries.py::test_list_current_brief_ids_outside_schema_rejects_malformed_limit_before_sql tests/unit/domains/news_intel/test_news_repository_queries.py::test_clear_current_briefs_outside_schema_returning_rows_require_cursor_rowcount tests/unit/domains/news_intel/test_news_repository_queries.py::test_clear_current_briefs_outside_schema_returning_rows_reject_invalid_or_mismatched_rowcount tests/unit/domains/news_intel/test_news_repository_queries.py::test_clear_current_briefs_outside_schema_returning_rows_accept_zero_row_noop tests/unit/domains/news_intel/test_news_repository_queries.py::test_clear_current_briefs_outside_schema_returning_rows_accept_matching_deleted_rows tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_brief_schema_cleanup_returning_rows_require_cursor_rowcount_match tests/architecture/test_news_intel_kiss_simplification.py::test_news_current_brief_schema_gate_uses_column_schema_version_only -q
uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_source_quality_inputs_rejects_malformed_window_before_sql tests/architecture/test_news_intel_kiss_simplification.py::test_old_item_outputs_are_audit_only_after_story_agent_hard_cut -q
uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_dedup_diagnostics_rejects_malformed_summary_row tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_dedup_diagnostics_uses_explicit_positive_window tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_dedup_diagnostics_rejects_malformed_window_before_sql tests/unit/test_cli.py::test_ops_news_dedup_commands_are_registered_without_compatibility_flags tests/architecture/test_news_intel_kiss_simplification.py::test_news_dedup_diagnostics_requires_summary_row_contract_without_defaults -q
uv run pytest tests/unit/test_notification_worker_runtime.py::test_notification_repository_read_lists_reject_malformed_limits_before_sql tests/architecture/test_notifications_hard_cut.py::test_notification_repository_read_lists_reject_runtime_limit_repairs -q
uv run pytest tests/unit/test_cli.py::test_ops_news_dedup_commands_are_registered_without_compatibility_flags tests/unit/test_cli.py::test_rebuild_news_canonical_items_rejects_malformed_limit_before_repo tests/architecture/test_news_intel_kiss_simplification.py::test_ops_news_canonical_rebuild_reads_current_servable_story_keyset -q
uv run pytest tests/unit/domains/evidence/test_evidence_repositories.py::test_recent_events_pushes_since_window_to_postgres tests/unit/domains/evidence/test_evidence_repositories.py::test_recent_events_zero_limit_returns_empty_without_sql tests/unit/domains/evidence/test_evidence_repositories.py::test_recent_events_rejects_malformed_limit_before_sql tests/unit/domains/evidence/test_evidence_repositories.py::test_recent_events_for_token_filters_uses_single_keyset_sql_with_bucket_budget tests/unit/domains/evidence/test_evidence_repositories.py::test_recent_events_for_token_filters_rejects_malformed_limits_before_sql tests/unit/domains/evidence/test_evidence_repositories.py::test_entity_find_rejects_malformed_limit_before_sql tests/architecture/test_evidence_repository_contracts.py -q
uv run pytest tests/unit/domains/token_intel/test_token_fact_repositories.py::test_token_intent_recent_unresolved_zero_limit_returns_empty_without_sql tests/unit/domains/token_intel/test_token_fact_repositories.py::test_token_intent_recent_unresolved_rejects_malformed_limit_before_sql tests/unit/domains/token_intel/test_token_fact_repositories.py::test_token_intent_lookup_reads_reject_malformed_limit_before_sql tests/architecture/test_token_intent_repository_contracts.py -q
uv run pytest tests/unit/test_token_capture_tier_repository.py::test_list_by_tier_prioritizes_missing_or_incomplete_market_ticks tests/unit/test_token_capture_tier_repository.py::test_list_by_tier_excludes_recently_attempted_keys_without_offset tests/unit/test_token_capture_tier_repository.py::test_token_capture_tier_read_limits_reject_malformed_before_sql tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_capture_tier_repository_read_limits_reject_runtime_repairs -q
uv run pytest tests/unit/test_token_capture_tier_worker.py::test_registry_ranked_live_market_targets_projects_rank_score_from_factor_snapshot tests/unit/test_token_capture_tier_worker.py::test_registry_ranked_live_market_targets_rejects_malformed_limit_before_sql tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_registry_ranked_live_market_targets_limit_rejects_runtime_repairs -q
uv run pytest tests/unit/domains/token_intel/test_projection_repository.py::test_projection_repository_diagnostic_reads_require_explicit_limits_without_defaults tests/unit/domains/token_intel/test_projection_repository.py::test_projection_repository_limits_reject_malformed_before_sql tests/unit/domains/token_intel/test_projection_repository.py::test_projection_repository_claim_dirty_ranges_accepts_zero_rowcount_with_no_rows tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_projection_repository_diagnostic_reads_require_explicit_limits_without_defaults -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_token_radar_source_width_contract.py -q
uv run pytest tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/unit/test_token_radar_projection_worker.py tests/unit/test_token_radar_projection.py tests/architecture/test_token_radar_source_width_contract.py -q
uv run pytest tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_token_radar_source_width_contract.py -q
uv run pytest tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/test_market_tick_current_repository.py tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_target_claim_due_returning_rows_require_cursor_rowcount_match -q
uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_token_radar_source_width_contract.py -q
uv run ruff check .
uv run ruff check src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/architecture/test_token_radar_source_width_contract.py
uv run ruff check src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py tests/unit/test_asset_profile_refresh_worker.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py
uv run ruff check src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py src/parallax/app/surfaces/cli/commands/queue_ops.py tests/unit/test_market_tick_current_repository.py tests/unit/test_market_tick_current_projection_worker.py tests/unit/test_cli_queue_ops.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run ruff check src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py src/parallax/app/surfaces/cli/commands/queue_ops.py src/parallax/app/runtime/worker_factories/notifications.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/unit/test_cli_queue_ops.py tests/architecture/test_pulse_no_compat.py tests/architecture/test_notifications_hard_cut.py
uv run mypy src/parallax/domains/macro_intel/repositories/macro_intel_repository.py src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py src/parallax/app/surfaces/cli/commands/queue_ops.py
uv run mypy src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py
uv run mypy src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py src/parallax/domains/token_intel/services/token_radar_projection.py src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py src/parallax/app/surfaces/cli/commands/queue_ops.py
uv run mypy src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py
uv run mypy src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py src/parallax/app/surfaces/cli/commands/queue_ops.py src/parallax/app/runtime/worker_factories/notifications.py
uv run mypy src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py src/parallax/app/surfaces/cli/commands/queue_ops.py
uv run mypy src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/discovery_repository.py tests/unit/test_discovery_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/discovery_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py
uv run ruff check src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py
uv run ruff check src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/architecture/test_pulse_no_compat.py
uv run mypy src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/unit/test_cli.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py
uv run ruff check src/parallax/domains/notifications/repositories/notification_repository.py tests/unit/test_notification_worker_runtime.py tests/architecture/test_notifications_hard_cut.py
uv run mypy src/parallax/domains/notifications/repositories/notification_repository.py
uv run ruff check src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py tests/unit/test_cli.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/app/surfaces/cli/parser.py src/parallax/app/surfaces/cli/commands/ops.py
uv run ruff check src/parallax/domains/evidence/repositories/evidence_repository.py src/parallax/domains/evidence/repositories/entity_repository.py tests/unit/domains/evidence/test_evidence_repositories.py tests/architecture/test_evidence_repository_contracts.py
uv run mypy src/parallax/domains/evidence/repositories/evidence_repository.py src/parallax/domains/evidence/repositories/entity_repository.py
uv run ruff check src/parallax/domains/token_intel/repositories/token_intent_repository.py src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_token_intent_repository_contracts.py
uv run mypy src/parallax/domains/token_intel/repositories/token_intent_repository.py src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py tests/unit/test_token_capture_tier_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/registry_repository.py tests/unit/test_token_capture_tier_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/registry_repository.py
uv run ruff check src/parallax/domains/token_intel/repositories/projection_repository.py tests/unit/domains/token_intel/test_projection_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/token_intel/repositories/projection_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py
uv run ruff check src/parallax/domains/news_intel/repositories/news_repository.py tests/unit/domains/news_intel/test_news_repository_queries.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_repository.py
uv run ruff check src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py src/parallax/domains/macro_intel/repositories/macro_intel_repository.py src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py tests/unit/test_market_tick_current_repository.py tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py src/parallax/domains/macro_intel/repositories/macro_intel_repository.py src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py
uv run pytest tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_dirty_target_claim_due_returning_rows_require_cursor_rowcount_match -q
uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py -q
uv run pytest tests/unit/test_cli_queue_ops.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes -q
uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/test_cli_queue_ops.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_contract_validation_uses_static_contract_not_provider_object tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_news_fetch_validates_provider_contract_before_reconcile tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes -q
uv run pytest tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_wiring_requires_feed_fetch_result_contract_without_diagnostics_probe tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_news_provider_wiring_constructs_opennews_rest_client_without_websocket_kwargs -q
uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/test_cli_queue_ops.py tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_contract_validation_uses_static_contract_not_provider_object tests/architecture/test_news_intel_kiss_simplification.py::test_news_provider_wiring_requires_feed_fetch_result_contract_without_diagnostics_probe tests/architecture/test_runtime_performance_architecture_hard_cut.py::test_news_fetch_validates_provider_contract_before_reconcile tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_queue_ops_retry_transitions_require_repository_contracts_without_optional_probes tests/unit/integrations/news_feeds/test_provider_registry.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_news_provider_wiring_constructs_opennews_rest_client_without_websocket_kwargs -q
uv run ruff check src/parallax/app/runtime/app.py src/parallax/domains/news_intel/services/news_provider_contract.py src/parallax/app/surfaces/cli/commands/queue_ops.py tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/test_cli_queue_ops.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/app/runtime/app.py src/parallax/domains/news_intel/services/news_provider_contract.py src/parallax/app/surfaces/cli/commands/queue_ops.py
uv run ruff check src/parallax/app/runtime/provider_wiring/news.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/app/runtime/provider_wiring/news.py
uv run ruff check src/parallax/app/runtime/app.py src/parallax/app/runtime/provider_wiring/news.py src/parallax/domains/news_intel/services/news_provider_contract.py src/parallax/app/surfaces/cli/commands/queue_ops.py tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/test_cli_queue_ops.py tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/app/runtime/app.py src/parallax/app/runtime/provider_wiring/news.py src/parallax/domains/news_intel/services/news_provider_contract.py src/parallax/app/surfaces/cli/commands/queue_ops.py
uv run pytest tests/unit/test_providers_wiring.py::test_okx_dex_ws_adapter_sync_close_rejects_connected_public_state tests/unit/test_providers_wiring.py::test_okx_dex_ws_adapter_sync_close_uses_public_state_not_private_websocket tests/architecture/test_worker_runtime_contracts.py::test_provider_wiring_cleanup_uses_formal_close_contracts_without_optional_probes -q
uv run pytest tests/unit/domains/macro_intel/test_macro_feature_engine.py::test_feature_engine_requires_supported_frequency_without_daily_fallback tests/unit/domains/macro_intel/test_macro_feature_engine.py::test_feature_engine_supports_intraday_crypto_derivatives_frequency_without_daily_fallback -q
uv run pytest tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_marks_claim_done_with_payload_hash tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_isolates_source_target_failures tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_attempt_contract_before_work tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_identity_contract_without_alias_fallback tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_lease_owner_contract_before_work tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_requires_source_claim_payload_hash_contract_before_work tests/unit/test_token_radar_projection.py::test_projection_rebuild_dirty_targets_processes_claims_inside_explicit_transaction -q
uv run pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py -q
uv run pytest tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_keeps_news_item_brief_interval_only_when_config_overrides_wakes tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_item_brief_when_configured tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_story_brief_when_configured -q
uv run ruff check src/parallax/app/runtime/provider_wiring/okx.py src/parallax/domains/macro_intel/services/macro_feature_engine.py src/parallax/domains/token_intel/services/token_radar_projection.py tests/unit/test_providers_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/unit/domains/macro_intel/test_macro_feature_engine.py tests/unit/test_token_radar_projection.py
uv run mypy src/parallax/app/runtime/provider_wiring/okx.py src/parallax/domains/macro_intel/services/macro_feature_engine.py src/parallax/domains/token_intel/services/token_radar_projection.py
uv run ruff check src/parallax/domains/news_intel/services/news_item_agent_policy.py tests/unit/domains/news_intel/test_news_item_agent_policy.py
uv run mypy src/parallax/domains/news_intel/services/news_item_agent_policy.py
uv run ruff check src/parallax/app/runtime/worker_factories/news_intel.py tests/unit/test_bootstrap_worker_runtime_wiring.py
uv run mypy src/parallax/app/runtime/worker_factories/news_intel.py
uv run pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_item_brief_when_configured tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_keeps_news_item_brief_interval_only_when_config_overrides_wakes tests/architecture/test_worker_runtime_contracts.py::test_news_item_brief_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults tests/architecture/test_worker_runtime_contracts.py::test_wake_bus_is_emit_only tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current tests/architecture/test_news_intel_kiss_simplification.py::test_news_item_brief_current_write_does_not_dirty_page_projection -q
uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py::test_news_item_brief_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults tests/architecture/test_worker_runtime_contracts.py::test_wake_bus_is_emit_only tests/architecture/test_news_intel_kiss_simplification.py::test_news_page_projection_wakes_from_story_current_not_item_brief_current tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_item_brief_when_configured tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_keeps_news_item_brief_interval_only_when_config_overrides_wakes -q
uv run ruff check src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/app/runtime/worker_factories/news_intel.py src/parallax/app/runtime/wake_bus.py src/parallax/app/runtime/worker_manifest.py tests/unit/domains/news_intel/test_news_item_brief_worker.py tests/unit/test_bootstrap_worker_runtime_wiring.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/runtime/news_item_brief_worker.py src/parallax/app/runtime/worker_factories/news_intel.py src/parallax/app/runtime/wake_bus.py src/parallax/app/runtime/worker_manifest.py
uv run pytest tests/architecture/test_worker_inventory_contract.py::test_documented_wake_outputs_match_worker_manifest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_db_wake_graph_has_no_orphaned_or_non_wakebus_channels tests/architecture/test_worker_inventory_contract.py::test_wake_bus_notify_channels_are_documented_as_wake_outputs tests/architecture/test_worker_inventory_contract.py::test_documented_wake_inputs_match_default_worker_settings -q
uv run pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py::test_worker_manifest_matches_workers_yaml_schema tests/architecture/test_worker_runtime_contracts.py::test_worker_manifest_keeps_provider_raw_frames_out_of_business_facts tests/architecture/test_worker_runtime_contracts.py::test_worker_manifest_declares_dirty_target_consumers -q
uv run ruff check src/parallax/app/runtime/worker_manifest.py tests/architecture/test_worker_inventory_contract.py
uv run mypy src/parallax/app/runtime/worker_manifest.py
uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py::test_record_agent_backpressure_requires_formal_agent_capacity_reservation tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py::test_record_agent_backpressure_requires_formal_reason_enum tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py::test_record_agent_backpressure_uses_formal_reason_value tests/architecture/test_pulse_no_compat.py::test_pulse_candidate_worker_backpressure_requires_formal_reservation_without_reflection -q
uv run pytest tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_pulse_no_compat.py -q
uv run ruff check src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_pulse_no_compat.py
uv run mypy src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py
uv run pytest tests/unit/test_resolution_refresh_worker.py::test_symbol_lookup_requires_formal_dex_token_candidate_without_reflection tests/architecture/test_worker_runtime_contracts.py::test_resolution_refresh_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults -q
uv run pytest tests/unit/test_resolution_refresh_worker.py tests/architecture/test_worker_runtime_contracts.py::test_resolution_refresh_worker_uses_formal_settings_and_wake_contract_without_runtime_defaults tests/architecture/test_worker_runtime_contracts.py::test_token_resolution_refresh_requires_formal_resolution_decision_without_reflection -q
uv run ruff check src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py tests/unit/test_resolution_refresh_worker.py tests/architecture/test_worker_runtime_contracts.py
uv run mypy src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py
uv run pytest tests/integration/test_asset_ingest_flow.py tests/unit/test_ingest_service_token_radar_dirty_targets.py tests/architecture/test_token_radar_source_width_contract.py::test_ingest_source_dirty_requires_formal_resolution_decisions_without_dict_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ingest_service_requires_formal_repository_session_contracts_without_constructor_fallbacks tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_ingest_service_requires_formal_intent_and_capture_contracts_without_reflection -q
uv run ruff check src/parallax/domains/evidence/services/ingest_service.py src/parallax/domains/asset_market/interfaces.py src/parallax/domains/token_intel/interfaces.py tests/integration/test_asset_ingest_flow.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/evidence/services/ingest_service.py src/parallax/domains/asset_market/interfaces.py src/parallax/domains/token_intel/interfaces.py
uv run pytest tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_use_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_require_real_cursor_rowcount_for_fact_writes tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_repository_requires_formal_input_without_slots_reflection -q
uv run ruff check src/parallax/domains/token_intel/repositories/token_intent_repository.py tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/token_intel/repositories/token_intent_repository.py
uv run pytest tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_use_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_require_real_cursor_rowcount_for_fact_writes tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_repository_requires_formal_input_without_slots_reflection tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_evidence_repository_requires_formal_input_without_slots_reflection -q
uv run ruff check src/parallax/domains/token_intel/repositories/token_evidence_repository.py src/parallax/domains/token_intel/repositories/token_intent_repository.py tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/token_intel/repositories/token_evidence_repository.py src/parallax/domains/token_intel/repositories/token_intent_repository.py
uv run pytest tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_use_connection_transaction_without_manual_commit_fallback tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_fact_repositories_require_real_cursor_rowcount_for_fact_writes tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_repository_requires_formal_input_without_slots_reflection tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_evidence_repository_requires_formal_input_without_slots_reflection tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_intent_resolution_repository_requires_formal_input_without_slots_reflection -q
uv run ruff check src/parallax/domains/token_intel/repositories/token_evidence_repository.py src/parallax/domains/token_intel/repositories/token_intent_repository.py src/parallax/domains/token_intel/repositories/intent_resolution_repository.py tests/unit/domains/token_intel/test_token_fact_repositories.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/token_intel/repositories/token_evidence_repository.py src/parallax/domains/token_intel/repositories/token_intent_repository.py src/parallax/domains/token_intel/repositories/intent_resolution_repository.py
uv run pytest tests/unit/test_token_intent_resolver.py tests/unit/test_token_resolution_refresh.py tests/unit/test_token_intent_rebuild_runtime.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_resolution_refresh_batches_evidence_reads_for_reprocess_intents tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_token_intent_resolver_requires_formal_inputs_without_object_reflection tests/architecture/test_worker_runtime_contracts.py::test_token_resolution_refresh_requires_formal_resolution_decision_without_reflection -q
uv run ruff check src/parallax/domains/token_intel/services/token_intent_resolver.py tests/unit/test_token_intent_resolver.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/token_intel/services/token_intent_resolver.py src/parallax/domains/token_intel/services/token_resolution_refresh.py src/parallax/domains/token_intel/runtime/token_intent_rebuild.py
uv run pytest tests/unit/test_pulse_candidate_worker.py tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py tests/architecture/test_pulse_no_compat.py -q
uv run ruff check src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py tests/unit/test_pulse_candidate_worker.py tests/architecture/test_pulse_no_compat.py
uv run mypy src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py
uv run pytest tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_claim_due_rejects_malformed_parameters_before_transaction tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_mark_error_rejects_malformed_retry_before_transaction tests/unit/domains/news_intel/test_news_projection_dirty_targets.py::test_news_projection_dirty_claim_due_returning_rows_accept_matching_claim_rows tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_claim_due_returning_rows_require_cursor_rowcount_match tests/architecture/test_news_intel_kiss_simplification.py::test_news_projection_dirty_completion_counts_require_real_cursor_rowcount -q
uv run ruff check src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py tests/unit/domains/news_intel/test_news_projection_dirty_targets.py tests/architecture/test_news_intel_kiss_simplification.py
uv run mypy src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py
uv run pytest tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/unit/test_token_radar_projection.py tests/unit/test_token_radar_projection_worker.py tests/architecture/test_token_radar_source_width_contract.py -q
uv run ruff check src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py tests/unit/test_token_radar_dirty_target_repository.py tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py tests/architecture/test_token_radar_source_width_contract.py
uv run mypy src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py src/parallax/domains/token_intel/services/token_radar_projection.py src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py
uv run pytest tests/unit/test_market_tick_current_repository.py tests/unit/test_market_tick_current_projection_worker.py -q
uv run ruff check src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py tests/unit/test_market_tick_current_repository.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py
uv run pytest tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/unit/test_asset_profile_refresh_worker.py tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_refresh_target_repository_queue_policy_rejects_runtime_int_repair tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_asset_profile_refresh_completion_counts_require_real_cursor_rowcount -q
uv run ruff check src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py tests/architecture/test_runtime_worker_constraint_hard_cut.py
uv run mypy src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py
git diff --check
```

Results:

- Architecture suite: `1309 passed`
- Token Radar source/target/projection/worker unit suites: `300 passed`
- Queue Terminal / queue ops / targeted architecture suites: `181 passed`
- Worker inventory/runtime architecture suites: `226 passed`
- Token Radar golden/integration smoke: `35 passed, 2 subtests passed`
- Token Radar projection unit suite: `196 passed` in the first static pass
- Macro View Projection / Macro repository / queue ops suites: `151 passed`
- Settings suite: `81 passed`
- Worker runtime/inventory/hard-cut architecture suites: `355 passed`
- Macro no-compatibility/Kappa architecture suites: `152 passed`
- Resolution Refresh worker / Discovery hard-cut architecture subset: `17 passed`
- Discovery terminalization integration smoke: `1 passed`
- Event Anchor repository / worker / queue ops suites: `79 passed`
- API News contract suite: `37 passed`
- Targeted News/notification public-agent brief contracts: `11 passed`
- Targeted News hard-cut/API/notification contracts: `50 passed`
- Watchlist hard-cut/API/provider-free contracts: `11 passed`
- Public contract alignment plus Watchlist hard-cut contracts: `9 passed`
- Narrative hard-cut/no-provider/no-API-write contracts: `14 passed`
- Pulse no-compat / dirty-trigger repository / dirty-trigger worker / queue ops
  suites: `113 passed`
- Notification hard-cut and worker factory bootstrap contracts: `27 passed`
- Notification rules/runtime/integration suites: `217 passed`
- Market Tick Current repository/worker plus Queue Terminal ops suite:
  `61 passed`
- Worker runtime/inventory/hard-cut architecture suites after Asset Market
  changes: `355 passed`
- Market stream/poll/live gateway/tick repository/capture-tier suites:
  `112 passed`
- Asset Profile Refresh repository/worker/source-cache suites: `30 passed`
- Token Profile Current / Token Image Mirror profile-icon suites: `160 passed`
- Worker runtime/hard-cut/source-width architecture subset after Asset Profile
  catch-up: `307 passed`
- Token Radar dirty repository/projection worker/service/source-width guard
  suites after claim rowcount hardening: `316 passed`
- Worker runtime/inventory/source-width architecture suite after Token Radar
  claim rowcount hardening: `241 passed`
- Cross-domain dirty-target claim rowcount suite after horizontal hardening:
  `313 passed`
- Worker runtime/hard-cut/inventory/source-width architecture suite after
  horizontal claim hardening: `371 passed`
- Ruff: passed
- Targeted Ruff over modified Token Radar dirty repositories/tests: passed
- Targeted Ruff over modified Asset Profile source/tests: passed
- Targeted Ruff over modified Asset Market/queue/tests: passed
- Targeted Ruff over modified Pulse/notification/queue files: passed
- Targeted mypy over modified Macro/queue source files: passed
- Targeted mypy over modified Resolution Refresh source file: passed
- Targeted mypy over modified Token Radar/queue source files: passed
- Targeted mypy over modified Token Radar dirty repositories: passed
- Targeted mypy over modified Pulse/notification/queue source files: passed
- Targeted mypy over modified Asset Market/queue source files: passed
- Targeted mypy over modified Asset Profile source files: passed
- Targeted Ruff over horizontally hardened dirty-target repositories/tests:
  passed
- Targeted mypy over horizontally hardened dirty-target repositories: passed
- Static AST scan found no chained DML `RETURNING` `execute(...).fetchall()`
  calls remaining under `src/parallax`.
- Token Image Source dirty-target suite after helper normalization: `23 passed`
- Broader static AST scan found no DML `RETURNING` + `fetchall()` functions
  missing a rowcount helper under `src/parallax`.
- News provider-contract unit suite after settings-boundary hardening:
  `11 passed`
- Queue Terminal CLI suite plus queue retry architecture guard after limit and
  Macro retry hardening: `20 passed`
- Combined News provider contract / Queue Terminal / targeted architecture
  suite: `33 passed`
- News provider wiring contract / provider registry / bootstrap wiring subset:
  `7 passed`
- Final combined News provider / Queue Terminal / provider wiring hard-cut
  subset: `40 passed`
- Targeted Ruff over this pass's runtime/contract/queue/test files: passed
- Targeted mypy over this pass's runtime/contract/queue source files: passed
- Targeted Ruff over News provider wiring hard-cut files: passed
- Targeted mypy over News provider wiring source: passed
- OKX provider formal cleanup contract subset: `3 passed`
- Macro feature-frequency no-fallback/intraday subset: `4 passed`
- Macro irregular-frequency feature/projection/repository architecture subset:
  `221 passed`
- Read-only live Macro irregular series feature replay: `ok=true`, 3 persisted
  series rows produced 1 feature and no feature-frequency exception
- Token Radar source-dirty claim completion/isolation subset: `10 passed`
- Token Radar live-follow-up source/target dirty and projection contract subset:
  `297 passed`
- Token Profile Current worker/projection/repository/source-query contract
  subset: `108 passed`
- Event Anchor Backfill worker/repository/queue-terminal contract subset:
  `73 passed`
- Market Tick Current projection/repository/rebuild/queue-terminal contract
  subset: `65 passed`
- Token Capture Tier worker/repository/dirty-target/source-watermark contract
  subset: `68 passed`
- Targeted Ruff/mypy over Token Capture Tier changed-count hard-cut files:
  passed
- Market Tick Stream/Poll writer plus append-only market tick repository
  contract subset: `60 passed`
- Live Price Gateway cache/fan-out formal target and manifest contract subset:
  `13 passed`
- Targeted Ruff/mypy over Live Price Gateway hard-cut files: passed
- Token Image Mirror worker/service/repository and architecture contract subset:
  `84 passed`
- Macro Sync fact-ingest worker/service/repository/runner contract subset:
  `189 passed`
- Macro Daily Brief projection read-model contract subset: `15 passed`
- News worker-chain settings, dirty retry-budget, factory wake, projection, and
  agent current subset: `523 passed`
- Targeted Ruff/mypy over refreshed News worker-chain files: passed
- Notification strict settings, delivery rowcount, and stale-claim CAS subset:
  `130 passed`
- Targeted Ruff/mypy over refreshed Notification runtime/repository files:
  passed
- Read-only live Notification queue probe: 36,163 notifications, 983 delivery
  rows, all delivery rows settled as delivered, 0 pending/running/failed/dead,
  0 stale running, 0 active rows at or over retry budget, and 0 delivery
  orphans.
- Pulse strict settings, dirty-trigger contract, and stale-claim CAS subset:
  `298 passed`
- Targeted Ruff/mypy over refreshed Pulse worker/repository/job-service files:
  passed
- Read-only live Pulse queue probe: `pulse_candidate` disabled, 0
  `pulse_candidates`, 0 `pulse_agent_jobs`, 0 `pulse_agent_runs`, 0 unresolved
  Pulse terminal events, and 14,252 due/unleased `pulse_trigger_dirty_targets`
  at attempt 0.
- CEX OI board settings/repository/builder/enricher hard-cut subset:
  `111 passed`; broader CEX wiring/API/manifest/lifecycle subset: `69 passed`
- Targeted Ruff/mypy over refreshed CEX OI worker/repository/builder/enricher
  files: passed
- Read-only live CEX OI probe: `cex_oi_radar_board` disabled, 0
  `cex_oi_radar_publication_state`, 0 `cex_oi_radar_rows`, 0
  `cex_detail_snapshots`, and 0 `cex_derivative_series` rows.
- Narrative Admission strict settings, dirty-target retry-budget, CLI retry
  transition, and architecture subset: `115 passed`
- Narrative Admission PostgreSQL dirty-target integration subset: `4 passed`
- Narrative Admission widened unit/CLI/architecture subset: `178 passed`
- Targeted Ruff/mypy over refreshed Narrative worker/repository/service,
  Queue Terminal retry, and settings files: passed
- Read-only live Narrative Admission probe: `narrative_admission` disabled, 0
  `narrative_admission_dirty_targets`, 0 `narrative_admissions`, and 0
  unresolved Narrative Admission terminal events.
- Runtime orchestration Queue Health / scheduler / DB pool subset: `61 passed`
- Targeted Ruff over refreshed runtime orchestration files and architecture
  guards: passed
- Targeted mypy over refreshed runtime orchestration source files: passed
- Collector ingest active-window formal contract subset: `20 passed`
- Targeted Ruff/mypy over refreshed bootstrap and ingest service files: passed
- WorkerBase lifecycle timing/backoff formal contract subset: `42 passed`
- Targeted Ruff/mypy over refreshed WorkerBase lifecycle files: passed
- WakeWaiter timeout formal contract subset: `15 passed`
- Targeted Ruff/mypy over refreshed WakeWaiter files: passed
- DBPoolBundle statement-timeout formal contract subset: `28 passed`
- Targeted Ruff/mypy over refreshed DBPoolBundle files: passed
- Notification local wake timeout formal contract subset: `5 passed`
- Targeted Ruff/mypy over refreshed notification factory files: passed
- Model execution provider timeout formal contract subset: `16 passed`
- Targeted Ruff/mypy over refreshed model-execution provider wiring files:
  passed
- Collector prepared-ingest formal contract subset: `21 passed`
- Targeted Ruff/mypy over refreshed collector bootstrap files: passed
- PostgreSQL client runtime timeout formal contract subset: `22 passed`
- Targeted Ruff/mypy over refreshed PostgreSQL client files: passed
- Combined runtime/provider/PostgreSQL compatibility hard-cut subset:
  `205 passed`
- Combined runtime/provider/PostgreSQL architecture guard subset: `7 passed`
- Watchlist public read-path limit/window contract subset: `39 passed`
- Targeted Ruff/mypy over refreshed Watchlist read-path files: passed
- Event Anchor Backfill runtime/repository parameter contract subset:
  `115 passed`
- Targeted Ruff/mypy over refreshed Event Anchor Backfill worker/repository
  files: passed
- Asset Market live runtime settings contract subset: `103 passed`
- Targeted Ruff/mypy over refreshed Asset Market live runtime worker files:
  passed
- Asset Market current/profile refresh settings contract subset: `82 passed`
- Targeted Ruff/mypy over refreshed Asset Market current/profile worker files:
  passed
- Market Tick Current dirty-target repository queue-policy contract subset:
  `72 passed`
- Targeted Ruff/mypy over refreshed Market Tick Current dirty-target
  repository files: passed
- Asset Profile Refresh target repository queue-policy contract subset:
  `57 passed`
- Targeted Ruff/mypy over refreshed Asset Profile Refresh target repository
  files: passed
- Token Profile Current dirty-target repository queue-policy contract subset:
  `112 passed`
- Targeted Ruff/mypy over refreshed Token Profile Current dirty-target
  repository files: passed
- Token Image Source dirty-target repository queue-policy contract subset:
  `87 passed`
- Targeted Ruff/mypy over refreshed Token Image Source dirty-target
  repository files: passed
- Token Capture Tier dirty-target repository queue-policy contract subset:
  `86 passed`
- Targeted Ruff/mypy over refreshed Token Capture Tier dirty-target
  repository files: passed
- Discovery lookup control-plane repository queue-policy contract subset:
  `127 passed`
- Targeted Ruff/mypy over refreshed Discovery repository files: passed
- Resolution Refresh runtime settings contract subset: `34 passed`
- Targeted Ruff/mypy over refreshed Resolution Refresh worker files: passed
- Macro Sync/View runtime settings contract subset: `38 passed`
- Targeted Ruff/mypy over refreshed Macro runtime worker files: passed
- Token Radar projection worker runtime settings contract subset: `49 passed`
- Targeted Ruff/mypy over refreshed Token Radar projection worker files: passed
- Token Radar target/source dirty repository queue-policy contract subset:
  `389 passed`
- Targeted Ruff/mypy over refreshed Token Radar dirty repository/projection
  files: passed
- Macro repository projection/history parameter contract subset: `189 passed`
- Targeted Ruff/mypy over refreshed Macro repository files: passed
- News Page/Source Quality projection runtime settings contract subset:
  `29 passed`
- Targeted Ruff/mypy over refreshed News Page/Source Quality worker files:
  passed
- News Item/Story brief queue-depth and claim-limit contract subset:
  `11 passed`
- Targeted Ruff/mypy over refreshed News brief runtime helper/worker files:
  passed
- News Projection dirty-target repository parameter contract subset:
  `12 passed`
- Targeted Ruff/mypy over refreshed News projection dirty-target repository
  files: passed
- News Projection dirty-target completion-token contract subset:
  `184 passed`
- Targeted Ruff/mypy over refreshed News projection completion-token files:
  passed
- Narrative Admission dirty-target completion-token contract subset:
  `72 passed`
- Targeted Ruff/mypy over refreshed Narrative Admission dirty-target files:
  passed
- Pulse Trigger dirty-target completion-token contract subset: `70 passed`
- Targeted Ruff/mypy over refreshed Pulse Trigger dirty-target files: passed
- News source fetch/canonical rebuild repository parameter subset:
  `28 passed`
- Targeted Ruff/mypy over refreshed News repository source-fetch files:
  passed
- News public page/high-signal read-path limit subset: `35 passed`
- Targeted Ruff/mypy over refreshed News public read-path files: passed
- News item processing claim parameter hard-cut subset: `18 passed`
- Targeted Ruff/mypy over refreshed News item claim files: passed
- News current-brief schema maintenance limit subset: `17 passed`
- Targeted Ruff/mypy over refreshed News schema maintenance files: passed
- News source-quality projection input window subset: `5 passed`
- Targeted Ruff/mypy over refreshed News source-quality input files: passed
- News dedup diagnostics window hard-cut subset: `14 passed`
- Targeted Ruff/mypy over refreshed News dedup diagnostics files: passed
- Notification read/list limit hard-cut subset: `7 passed`
- Targeted Ruff/mypy over refreshed Notification read-list files: passed
- News canonical rebuild operator limit hard-cut subset: `6 passed`
- Targeted Ruff/mypy over refreshed News canonical rebuild ops files: passed
- Evidence/entity read repository limit hard-cut subset: `18 passed`
- Targeted Ruff/mypy over refreshed Evidence/entity repository files: passed
- Token intent/lookup read repository limit hard-cut subset: `13 passed`
- Targeted Ruff/mypy over refreshed Token intent/lookup repository files:
  passed
- Token Capture Tier repository read limit hard-cut subset: `9 passed`
- Targeted Ruff/mypy over refreshed Token Capture Tier repository files:
  passed
- Registry ranked live-market target limit hard-cut subset: `5 passed`
- Targeted Ruff/mypy over refreshed Registry repository files: passed
- Projection repository diagnostic/claim limit hard-cut subset: `12 passed`
- Targeted Ruff/mypy over refreshed Projection repository files: passed
- Signal / Token Target timeline read limit hard-cut subset: `31 passed`
- Targeted Ruff/mypy over refreshed Signal / Token Target files: passed
- Account Quality / Event Rebuild / Rank Source limit hard-cut subset:
  `62 passed`
- Targeted Ruff/mypy over refreshed Account Quality / Event Rebuild / Rank
  Source files: passed
- Token Target posts/timeline and Asset Flow read-model limit hard-cut subset:
  `36 passed`
- Targeted Ruff/mypy over refreshed Token Target posts/timeline and Asset Flow
  files: passed
- Token Search service/query limit hard-cut subset: `28 passed`
- Targeted Ruff/mypy over refreshed Token Search service/query files: passed
- Catalyst / Stocks Radar / Token Factor Evaluation service limit hard-cut
  subset: `35 passed`
- Targeted Ruff/mypy over refreshed Catalyst / Stocks Radar / Token Factor
  Evaluation files: passed
- Token Radar private-cache/current-row/prune/rank-lane limit hard-cut subset:
  `23 passed`
- Targeted Ruff/mypy over refreshed Token Radar projection/repository files:
  passed
- News Page query / Narrative admission / Search Inspect limit hard-cut subset:
  `20 passed`
- Targeted Ruff/mypy over refreshed News Page / Narrative / Search Inspect
  files: passed
- API / ops / Market Tick stream boundary hard-cut subset: `440 passed`
- Targeted Ruff over refreshed API validator, CLI ops/parser, Market Tick
  stream, and tests: passed
- Targeted mypy over refreshed API validator, CLI ops/parser, and Market Tick
  stream source files: passed
- OKX WS / Market Tick stream positive subscription subset: `220 passed`
- Targeted Ruff over refreshed OKX WS / Market Tick stream files: passed
- Targeted mypy over refreshed OKX WS / Market Tick stream source files:
  passed
- GMGN / News feed provider boundary hard-cut subset: `85 passed`
- Targeted Ruff over refreshed GMGN / News feed provider files: passed
- Targeted mypy over refreshed GMGN / News feed provider source files: passed
- Macro sync scheduler/service boundary subset: `205 passed`
- Targeted Ruff over refreshed Macro sync scheduler/service files: passed
- Targeted mypy over refreshed Macro sync scheduler/service source files:
  passed
- Agent Execution / structured JSON numeric boundary subset: `71 passed`
- Targeted Ruff over refreshed Agent Execution gateway / structured JSON files:
  passed
- Targeted mypy over refreshed Agent Execution gateway / structured JSON source
  files: passed
- Notification / Pulse admission-timeline-freshness boundary subset:
  `613 passed`, with `531 passed` after helper type tightening
- Targeted Ruff over refreshed Notification / Pulse boundary files: passed
- Targeted mypy over refreshed Notification / Pulse boundary source files:
  passed
- Pulse repository/query boundary subset: `358 passed`
- Targeted Ruff over refreshed Pulse repository/query boundary files: passed
- Targeted mypy over refreshed Pulse repository/query boundary source files:
  passed
- Ops diagnostics / projection audit / token image / resolution refresh
  boundary subset: `317 passed`
- Targeted Ruff over refreshed Ops diagnostics / audit / asset-market
  boundary files: passed
- Targeted mypy over refreshed Ops diagnostics / audit / asset-market
  boundary source files: passed
- Pulse audit ledger / candidate decision-stage boundary subset: `132 passed`
- Targeted Ruff over refreshed Pulse audit/candidate files: passed
- Targeted mypy over refreshed Pulse audit/candidate source files: passed
- Resolution Refresh claim retry/backoff boundary subset: `217 passed`
- Targeted Ruff over refreshed Resolution Refresh claim-boundary files:
  passed
- Targeted mypy over refreshed Resolution Refresh worker source: passed
- Token Radar dirty-claim attempt-count boundary subset: `233 passed`
- Targeted Ruff over refreshed Token Radar dirty-claim files: passed
- Targeted mypy over refreshed Token Radar projection source: passed
- Token Radar legacy discovery-results input hard-cut subset: `277 passed`
- Targeted Ruff over refreshed Token Radar projection/query files: passed
- Targeted mypy over refreshed Token Radar projection/query source: passed
- Pulse decision stage audit numeric boundary subset: `91 passed`
- Targeted Ruff over refreshed Pulse decision client files: passed
- Targeted mypy over refreshed Pulse decision client source: passed
- Agent Execution gateway safety-net retry boundary subset: `73 passed`
- Targeted Ruff over refreshed Agent Execution gateway safety-net files:
  passed
- Targeted mypy over refreshed Agent Execution gateway source: passed
- Agent Execution gateway LLM surface hard-cut subset: `91 passed`
- Targeted Ruff over refreshed Agent Execution LLM surface files: passed
- Targeted mypy over refreshed Agent Execution gateway source: passed
- Combined resumed hard-cut regression subset: `637 passed`
- Combined Ruff over refreshed resumed hard-cut files: passed
- Combined mypy over refreshed resumed hard-cut source files: passed
- News item agent policy formal-admission subset: `15 passed`
- News item/story brief factory wake wiring subset: `3 passed`
- News item brief no-dead-wake runtime subset: `82 passed`
- Worker inventory plus News item brief no-dead-wake subset: `143 passed`
- Worker manifest DB wake graph subset: `4 passed`
- Worker inventory / manifest wake graph suite: `67 passed`
- Pulse formal backpressure-reservation subset: `4 passed`
- Pulse dirty-trigger worker plus no-compat architecture suite: `67 passed`
- Resolution Refresh formal DEX candidate subset: `2 passed`
- Resolution Refresh worker and contract subset: `17 passed`
- News item brief formal backpressure-reservation subset: `3 passed`
- News item brief worker/architecture subset: `96 passed`
- News story brief formal backpressure-reservation subset: `3 passed`
- News story brief worker/architecture subset: `37 passed`
- Pulse decision client formal agent-error-class subset: `2 passed`
- Pulse decision client plus agent execution plane architecture suite:
  `76 passed`
- Asset Market Binance route DTO sync subset: `6 passed`
- CLI integration / queue ops suite after route DTO sync and asset-profile
  payload expectation alignment: `49 passed, 2 subtests passed`
- Evidence ingest formal intent/capture boundary subset: `13 passed`
- Targeted Ruff over ingest boundary files: passed
- Targeted mypy over ingest boundary source files: passed
- Token intent repository formal input subset: `45 passed`
- Targeted Ruff over token intent repository boundary files: passed
- Targeted mypy over token intent repository source: passed
- Token evidence/intent repository formal input subset: `48 passed`
- Targeted Ruff over token evidence/intent repository boundary files: passed
- Targeted mypy over token evidence/intent repository sources: passed
- Token fact repository formal input subset: `51 passed`
- Targeted Ruff over token fact repository boundary files: passed
- Targeted mypy over token fact repository sources: passed
- Token intent resolver formal input/reprocess subset: `19 passed`
- Targeted Ruff over token intent resolver boundary files: passed
- Targeted mypy over token intent resolver and caller source files: passed
- Pulse candidate job-context hard-cut subset: `138 passed`
- Targeted Ruff over Pulse candidate job-context files: passed
- Targeted mypy over Pulse candidate worker/job service source files: passed
- Resolution Refresh live-follow-up worker/integration/architecture subset:
  `31 passed`
- Final targeted Ruff over OKX/Macro/Token Radar resumed-pass files: passed
- Final targeted mypy over OKX/Macro/Token Radar resumed-pass source files:
  passed
- Targeted Ruff/mypy over News item agent policy files: passed
- Targeted Ruff/mypy over News factory wake wiring files: passed
- Targeted Ruff over News item brief no-dead-wake files: passed
- Targeted mypy over News item brief no-dead-wake source files: passed
- Targeted Ruff over worker manifest wake graph files: passed
- Targeted mypy over worker manifest source: passed
- Targeted Ruff over Pulse backpressure reservation files: passed
- Targeted mypy over Pulse candidate worker source: passed
- Targeted Ruff over Resolution Refresh formal candidate files: passed
- Targeted mypy over Resolution Refresh worker source: passed
- Targeted Ruff/mypy over News item brief formal backpressure files: passed
- Targeted Ruff/mypy over News story brief formal backpressure files: passed
- Targeted Ruff over Pulse decision client formal-error-class files: passed
- Targeted mypy over Pulse decision client source: passed
- Targeted Ruff/mypy over Asset Market route sync source and CLI adapter:
  passed
- Final targeted Ruff over this pass's modified runtime/queue/News test files:
  passed
- Final targeted mypy over this pass's modified runtime/queue source files:
  passed
- Dirty queue retry-budget inheritance contract subset: `354 passed`
- Dirty queue touched repository regression subset: `399 passed`
- Asset Profile Refresh / Token Capture Tier dirty queue subset: `120 passed`
- Targeted Ruff over dirty queue retry-budget inheritance source/test files:
  passed
- Targeted mypy over dirty queue retry-budget inheritance source files:
  passed
- News page/search and final suite-regression subset:
  `uv run pytest tests/integration/domains/news_intel/test_news_repository.py tests/unit/domains/news_intel/test_news_page_projection.py tests/integration/domains/news_intel/test_news_source_quality_repository.py tests/integration/domains/news_intel/test_news_story_agent_repository.py tests/integration/test_market_tick_wake_idempotency.py tests/integration/test_pulse_candidate_dirty_triggers.py tests/integration/test_worker_missed_wake_recovery.py tests/unit/domains/news_intel/test_news_workers.py tests/unit/domains/news_intel/test_source_quality_projection.py tests/unit/test_cli_worker_status_contract.py -q`:
  `371 passed`
- Ordered full-suite continuation after `test_docs_generated` was run in split
  batches because the macrodata subprocess checks made a single rerun take
  multiple hours. The initial ordered run passed up to the generated-docs
  guard after prior fixes; `test_make_docs_generated_clean_diff` then passed;
  every remaining file after that guard passed after the targeted fixture
  updates above.
- `uv run pytest tests/integration/test_docs_generated.py::test_make_docs_generated_clean_diff -q`:
  `1 passed`
- `uv run pytest tests/architecture -q`: `1374 passed`
- `uv run ruff check src tests`: passed
- `uv run mypy src/parallax`: passed
- GMGN OpenAPI and Macrodata runner boundary subset:
  `uv run pytest tests/unit/test_gmgn_openapi_gateway.py tests/unit/test_cli_macro_commands.py -q`:
  `61 passed`
- Targeted Ruff over GMGN OpenAPI and Macrodata runner files: passed
- Targeted mypy over GMGN OpenAPI and Macrodata runner source files: passed
- Diff whitespace check: passed

## Residual Boundaries

- Live provider diagnostics against `~/.parallax/config.yaml` / `workers.yaml` were run read-only and recorded in `docs/reviews/live-provider-diagnostics-2026-06-24.md`. No live mutation was executed.
- The 2026-06-26 live follow-up found current Token Radar/Macro serving
  surfaces healthy in sampled read-only checks, but found over-budget active
  dirty rows in worker control queues. The code repair resets dirty queue
  `attempt_count` when a new effective `payload_hash` is enqueued, preventing a
  fresh work payload from inheriting an old failed retry budget while preserving
  same-payload retry accounting.
- Remaining work is post-deploy/live confirmation, not an additional
  compatibility hard-cut found in this audit pass: rerun the listed
  `~/.parallax` diagnostics after workers restart to confirm active queue
  pressure moves into the expected done/terminal states.
- The full repository still has documented type/format debt in `docs/TECH_DEBT.md`; this audit kept scope to Kappa/CQRS, worker ownership, compatibility hard cuts, and touched areas.
