# News Agent Source-Chain Architecture Review

Date: 2026-06-18
Scope: News Intel only. This revision intentionally does not introduce any new cross-domain price, stock, crypto, return-window, eval, or backtest subsystem.

## Executive Position

The previous draft overreached. It treated a News agent as a trading-signal system and introduced cross-domain price/return/eval concepts before the News chain itself had been fully reviewed. That is the wrong production sequence for Parallax today. The current News Intel code already has a sophisticated Kappa/CQRS chain: provider observations are normalized, canonical items are deduped through layered identity, deterministic item processing computes entities/facts/story/admission, the agent worker is admission-gated and hash-reusable, and page projection serves story-shaped rows. The next architecture move should harden that News-only chain before adding cross-domain complexity.

The five-step work method remains correct:

1. **Clarify**: define the product object as a News story intelligence packet, not a cross-domain price object.
2. **Cut**: remove old item-scoped agent exposure and compatibility shims from public/runtime paths.
3. **Refactor**: align agent execution with story identity and observation edges.
4. **Accelerate**: make deterministic reprocessing, dirty-target coalescing, and model-run reuse observable and testable.
5. **Automate**: only after story-level current state is stable, automate notification ranking and operator workflows.

The core correction is: the production object should be **a current story-level News brief/read model** that is derived entirely inside News Intel from `news_items`, `news_item_observation_edges`, deterministic entities/facts, story identity, source authority, source quality, and agent admission. Existing `market_scope_json` remains what the code already uses: deterministic routing/classification metadata on a news item. It must not be expanded into new cross-domain price/return reads in this phase.

## Source Chain As Implemented

The actual chain is not a simple "fetch article, run LLM, render row" path. It has multiple ownership and idempotency boundaries.

### 1. Feed and provider observation normalization

`src/parallax/domains/news_intel/services/feed_item_normalizer.py` turns provider entries into canonical provider observations. It requires a title, chooses canonical URL from link/canonical fields when admitted by `public_url_identity_policy`, and falls back to provider-specific OpenNews item URLs only after validating provider article id/method. It keeps provider raw frames as input evidence, not business truth.

`src/parallax/domains/news_intel/repositories/news_repository.py` then persists observations through `upsert_provider_item`. That method dedupes within a source by `(source_id, source_item_key)` and also checks the same provider article key within the same source. If an existing ready payload is present and a later observation is not ready, the ready payload wins. This matters because provider feeds can regress from full article payloads to thin references, and the repository prevents that regression from erasing useful content.

The first dedupe level is therefore provider-item idempotency, not story identity.

### 2. Canonical item identity

`src/parallax/domains/news_intel/types/news_canonical_identity.py` defines the canonical item identity order:

1. A hard public article URL identity becomes `canonical-url:<normalized-url>`.
2. For provider types with global provider article ids, currently OpenNews, the key becomes `provider:<provider-type>:<article-id>`.
3. A qualified content hash can be used only when URL policy allows it.
4. A weak fallback key uses source, published hour, and title fingerprint.

`src/parallax/domains/news_intel/types/news_url_identity.py` is intentionally conservative. Homepage, aggregator, live page, preview, feed, and generic announcement URLs are blocked from becoming hard canonical identities. Social status URLs can be admitted. This prevents a live-news page or provider index page from collapsing unrelated stories.

`src/parallax/domains/news_intel/types/news_material_identity.py` adds a separate material title fingerprint for bounded OpenNews material duplicate handling. It strips known source prefixes, requires enough title tokens, and checks provider token-impact compatibility so unrelated short headlines are not merged just because they look similar.

### 3. Canonical item upsert and observation edges

`NewsRepository.upsert_canonical_news_item` is the densest part of the chain. It computes canonical identity from the provider observation, may override supplied identity with a hard URL identity, computes provider article keys, and evaluates material duplicate identity for OpenNews observations.

The important production behaviors are:

- It uses an advisory transaction lock on the canonical identity key before item upsert.
- It writes or updates one `news_items` row keyed by `canonical_item_key`.
- It writes `news_item_observation_edges` on `provider_item_id`, allowing many provider observations to attach to one canonical item.
- It refreshes duplicate summaries on the item: duplicate observation count, source ids, source domains, provider article keys.
- It can remap provider-article edges to a stronger target item when a hard URL or ready content identity arrives.
- It can remap material duplicate edges when a public URL item later appears.
- It carefully handles old items after remap: if an old item has no edges it may be deleted; if it still has edges it is reselected and item-scoped derived facts are cleared; if it already has agent outputs it may be retained but dirty targets are remapped or cleanup is enqueued.

That last point is critical. The repository does not blindly delete old items with agent outputs. This is a good audit-safety behavior, but it means the public product must be explicit about which current story output is authoritative. Keeping old item outputs as hidden audit is acceptable; exposing them as current story intelligence is not.

### 4. Deterministic item processing

`NewsItemProcessWorker` owns deterministic item processing after fetch. The domain architecture file states that it extracts entities/token mentions, classifies content, writes fact candidates, computes current scope metadata, computes story identity, reloads admission context through the repository, computes agent admission, and enqueues optional brief work only for provider-rating-gated representative targets.

This stage is allowed to process multiple canonical items that are semantically similar. That is not waste by itself. Different canonical items may carry new sources, new facts, new affected entities, or stronger source roles. The key is that deterministic processing must be cheap, idempotent, and bounded; model execution must be gated harder.

### 5. Story identity

`src/parallax/domains/news_intel/services/news_story_identity.py` is the semantic grouping layer. It is not the same as canonical item identity. It builds story keys from:

- Exchange-listing event structure: venue, asset, quote market, and shifted 24h bucket.
- Strong hardcoded subjects with shifted 12h buckets.
- Material title tokens with shifted 6h buckets.
- Weak item-level fallback keys.

This is a good production compromise: exact item dedupe stays strict, while story grouping can be broader. But the story identity logic is currently embedded in code with special subjects and buckets. The optimization plan should not add a new cross-domain layer; it should make story grouping easier to audit, test, and evolve.

### 6. Exact duplicate and similar story admission

`src/parallax/domains/news_intel/services/news_story_similarity.py` separates exact duplicates from similar stories. Exact duplicate checks include provider article key intersection, same admitted article URL, same content hash, and same article canonical key. Similar story checks use same story key or fallback title fingerprint.

`src/parallax/domains/news_intel/services/news_item_agent_admission.py` turns repository context into an admission decision:

- Base gate requires processed lifecycle, classification, non-suppressed source, and non-future published time.
- OpenNews provider rating must be ready and at least 80.
- Exact duplicates become `exact_duplicate` and do not run the model.
- Similar stories with no material delta become `similar_story_covered`.
- Similar story bursts can become `similar_story_burst`.
- Source role, entity, fact, or meaningful content deltas can produce `eligible_refresh`.

`src/parallax/domains/news_intel/services/news_material_delta.py` defines material delta across source-role upgrade, new entity keys, accepted fact keys, and new material content. This is the second major cost gate after canonical dedupe.

### 7. Agent brief worker

`src/parallax/domains/news_intel/runtime/news_item_brief_worker.py` is already careful:

- It reserves agent capacity before claiming dirty targets.
- It claims only semantic dirty targets for `brief_input`.
- It loads candidates and admission contexts from the repository.
- It recomputes admission before model execution.
- If admission is not eligible, it updates item admission, enqueues page reprojection, marks the dirty target done, and does not call the model.
- It builds a bounded packet with source excerpt, entity lanes, fact lanes, scope metadata, admission, similarity, material delta, and evidence refs.
- It skips a current brief when input hash and version fields match.
- It restores current state from a completed run with the same input/version without a second model call.
- It treats a matching failed run as terminal enough to avoid repeated model calls.
- It validates model output before publication and writes failed current state on domain validation failure.

This is why the answer to "will same-type news be processed multiple times?" has to be nuanced:

- Provider observations can repeat; provider-item upsert absorbs identical source observations.
- Canonical observations can attach to one item through edges; this avoids duplicate canonical items for strong identities.
- Deterministic item processing may run for multiple distinct canonical items inside the same story; that is expected and usually correct.
- Agent model execution should not run for exact duplicates and normally should not run for similar covered stories.
- It can run again for an eligible refresh when material delta is proven.
- It can also run per item because the current brief table is item-scoped. That is the main production gap.

### 8. Dirty target queue

`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py` coalesces work by `(projection_name, target_kind, target_id, window)`. For page and brief item targets, positive `source_watermark_ms` is required. Enqueue keeps earliest due time, best priority, and greatest source watermark. It can release an existing lease if a newer/equally fresh payload hash or dirty reason arrives. Completion requires the claimed payload hash, lease owner, and attempt count.

This means the queue is designed for semantic idempotency and compare-and-set completion. The optimized design should reuse this discipline for story-level brief work instead of creating a parallel ad hoc queue.

### 9. Page projection

`src/parallax/domains/news_intel/runtime/news_page_projection_worker.py` claims item-scoped page dirty targets, loads bounded story projection payloads, builds rows with `build_news_page_row`, and writes story-shaped rows. It also deletes orphaned rows when claimed items no longer belong to the projected member set.

`src/parallax/domains/news_intel/services/news_page_projection.py` builds one row id from `NEWS_PAGE_PROJECTION_VERSION` plus story key or item id. It includes story payload, source payload, provider rating, token/fact lanes, agent admission, compact current brief state, and alert eligibility.

`NewsRepository.replace_page_rows_for_story_targets` deletes rows for the scoped story keys or member ids that are not incoming, then upserts the current rows. This is already a hard-cut serving model: `/api/news` should read projected rows, not raw items.

The weakness is that the projected row's agent signal still comes from the representative item's `news_item_agent_briefs`. The page is story-shaped, but the brief remains item-shaped.

## Dedupe Layers

The News chain has at least eight separate anti-duplication or anti-repeat mechanisms:

1. **Provider-item idempotency**: `(source_id, source_item_key)` and same provider article key within a source.
2. **Canonical item identity**: hard public article URL, provider-global article id, qualified content hash, weak title/source/hour key.
3. **Observation edges**: many provider observations attach to one `news_item`; duplicate counts and source/provider key evidence are aggregated.
4. **OpenNews material duplicate**: same source, material title fingerprint, compatible provider token impacts, bounded time window.
5. **Strong identity remap**: public URL or ready content can remap previous provider/material duplicate edges; old items are deleted, reselected, or retained as audit depending on edges and agent outputs.
6. **Story identity**: semantic grouping across canonical items by event template, strong subject, title bucket, or weak item key.
7. **Agent admission**: exact duplicates skip; similar covered stories skip; bursts skip; material deltas refresh.
8. **Agent run/current reuse**: current brief input hash/version, completed run restore, and failed run reuse prevent repeated model calls for the same material packet.

These layers answer different questions. Canonical identity asks "is this the same item?" Story identity asks "is this the same story?" Admission asks "is this worth model budget now?" Dirty targets ask "is there due work for this current source watermark?" Conflating them creates bad architecture.

## Where Repetition Still Exists

Repetition is not completely eliminated, and not all repetition should be eliminated.

**Desired repetition**:

- Multiple provider observations for the same article should be recorded as observation edges. They improve source evidence.
- Multiple canonical items in the same story should still get deterministic processing. A second source can add a fact, entity, source role upgrade, or stronger confirmation.
- Page projection can rebuild the same story row when a member changes. The unchanged-row logic should produce zero serving-row churn when payload is unchanged.

**Undesired or risky repetition**:

- A story can acquire multiple item-scoped current briefs across representative changes or eligible refresh items.
- Page projection can only show the representative item's current brief, so useful story-level context may be split across item briefs.
- Old item outputs may remain for audit after remap; without a hard public/read-path cut, they can be mistaken for current story intelligence.
- Story identity improvements require broad retesting because subject/template rules are embedded in code and page projection depends on exact story keys.

The optimization should therefore not be "dedupe harder everywhere." The right move is: keep canonical item dedupe strict, keep deterministic item processing per canonical item, but move model current state from item scope to story scope.

## Data Structure And Redundancy Audit

The deeper source review separates three kinds of repetition:

- **Truth repetition is not allowed**: two tables or JSON fields must not both claim to be the authoritative current story signal.
- **Evidence repetition is allowed**: provider observations, observation edges, source ids, and provider article keys can repeat because they prove provenance and dedupe behavior.
- **Projection repetition is allowed only when named as cache/index data**: `news_page_rows` may denormalize fields for hot reads and filters, but the writer must be single-owner and the rows must be rebuildable.

| Structure or field | Current role | Verdict | Reason | Action |
|--------------------|--------------|---------|--------|--------|
| `news_provider_items` | Provider observation input and raw payload audit. | Keep | It is the source-adapter boundary and absorbs provider-level repeats before business facts are written. | Do not expose as product current state. |
| `news_items` | Strict canonical item fact boundary. | Keep | Canonical identity must stay stricter than story identity so source/fact audit remains explainable. | Continue deterministic item processing per canonical item. |
| `news_item_observation_edges` | Many provider observations to one canonical item. | Keep | This is the canonical provenance graph for duplicate/source evidence. | Treat as source of truth for duplicate summaries. |
| Duplicate summaries on `news_items` | Cached duplicate count/source/provider-key lists. | Keep as cache | They are derived from edges and useful for hot repository paths. They are not independent facts. | Rebuild from edges when remapping or repairing. |
| `news_story_groups` / `news_story_members` | Retired story materialization tables. | Cut | Migrations hard-cut them and tests assert repository queries no longer use them. Recreating them would reintroduce an old story subsystem. | Do not add these tables back. |
| `news_items.story_key` / `story_identity_json` | Deterministic story identity on each canonical item. | Keep | This is the current lightweight story grouping mechanism and avoids a second membership table. | Make story identity versioning and tests stronger. |
| `news_page_rows.story_json` | Public story-serving contract. | Keep | Page rows are rebuildable read models and already carry story shape. | Keep as reader contract, not business truth. |
| `news_page_rows.duplicate_count`, `source_ids_json`, `source_domains_json`, `provider_article_keys_json` | Top-level filter/cache copies of story/source evidence. | Simplify semantics | They duplicate data also present in `story_json`, but are useful as hot scalar/list fields. | Define them as projection index/cache fields only; do not let API/UI treat them as separate truth. |
| `news_item_agent_runs` | Item-scoped LLM audit ledger. | Keep as audit during migration | Historical item attempts explain past outputs and cost, but item scope is not the desired product current state. | Stop treating it as story current after hard cut. |
| `news_item_agent_briefs` | Item-scoped current brief table. | Cut from public/runtime current state | This is the main mismatch: story-shaped rows still read representative item brief state. | Retain only hidden audit/internal state until a separate cleanup removes or archives it. |
| `news_story_agent_runs` | Proposed story-scoped run ledger. | Add | A story-scoped run ledger is justified because product identity changes from item to story while run id remains audit identity. | Keep columns aligned with current run audit patterns; avoid a generic global agent-run abstraction in this PR. |
| `news_story_agent_briefs` | Proposed story-scoped current read model. | Add | This becomes the single authoritative current story agent state. | Key by stable `story_brief_key`, not run id, generation, timestamp, or UUID. |
| `news_story_brief_members` | Possible normalized member table. | Do not add initially | Member ids are already derivable from story identity/page projection payloads. A new table would recreate membership materialization before there is a query need. | Store compact member ids in packet/current JSON; add a table only if a measured query requires it. |
| `news_projection_dirty_targets` with `projection_name = 'story'` | Retired dirty projection name. | Cut | Migration `20260531_0131` deletes it and current repository tests reject it. | Use a new `story_brief` projection name if story work is added. |
| `story_brief` dirty targets | Proposed semantic queue target. | Add | Reuses existing CAS/coalescing/backpressure discipline without a parallel queue. | Add DB/repository constraints for `projection_name = 'story_brief'` and `target_kind = 'story'`. |
| `provider_signal_json` / `provider_rating_json` | Provider evidence, rating, and admission clue. | Keep as evidence | Useful for gating and explanation, but not a publishable agent conclusion. | Keep out of product signal truth; include as evidence basis only. |
| `signal_json` on `news_page_rows` | UI/query envelope for alert/filter signal. | Simplify semantics | It currently wraps item-brief-derived state. The envelope is useful; the source must change. | Build from `news_story_agent_briefs` after hard cut. |
| `agent_status` on `news_page_rows` | Denormalized scalar used by filters/indexes. | Keep as cache, then reassess | It duplicates `agent_brief_json.status`, but current queries filter by it. | Define as scalar cache from story current state; remove only if indexes/queries no longer need it. |
| `market_scope_json` | Existing deterministic scope metadata. | Keep but freeze scope | It already exists in item/page contracts. It should not become a new cross-domain subsystem. | Treat as News-owned routing metadata and do not add price/return reads. |
| Story source-quality snapshot table | Possible future cache. | Do not add | Source quality can be loaded from existing source read models when packet building requires it. | Add only if packet build latency proves it is needed. |
| API/UI reconstruction helpers over raw items or old briefs | Compatibility path. | Cut | Runtime reconstruction bypasses single-writer read-model discipline and hides missing current state. | Serve projected rows and explicit pending/failed/skip states only. |

This table changes the proposed implementation shape in two ways. First, it avoids recreating a story membership subsystem: `story_key` plus deterministic packet loading is enough for the first hard cut. Second, it narrows denormalization language: page row scalar/list fields are serving cache, not a second semantic model.

## Architecture Simplification Decisions

The target design should remove ambiguity before adding capability:

1. The authoritative story agent current state is exactly one row in `news_story_agent_briefs`.
2. `news_page_rows.agent_brief_json`, `signal_json`, and `agent_status` are denormalized from that story current state.
3. `story_json` is the public story envelope; top-level duplicate/source/provider-key fields are index/cache copies.
4. `news_item_agent_briefs` and `news_item_agent_runs` are audit/history after the hard cut, not fallback truth.
5. `projection_name = 'story'` remains retired. The new work name is `story_brief` so old inactive story projection semantics cannot leak back.
6. No new member table, source-quality snapshot table, price-read table, return-window table, eval table, or backtest table is part of this phase.

## Revised Five-Step Cut List

1. **Clarify**: name canonical items, observation edges, story identity, story current brief, and page projection as separate ownership boundaries.
2. **Cut**: remove product-facing item brief fallback, retired `story` dirty target usage, and any plan to revive `news_story_groups` / `news_story_members`.
3. **Refactor**: move the model-current writer from item scope to story scope while leaving canonical item facts and observation edges intact.
4. **Accelerate**: keep only measurable caches: edge summaries, page row scalar fields, packet hashes, and dirty-target coalescing.
5. **Automate**: add notification/operator workflows only after the story current read model has single-writer ownership and no compatibility reconstruction path.

## Production Target

The production target is a News-only story agent:

```text
news_fetch
  -> canonical item + observation edges
  -> news_item_process
     -> entities, token mentions, facts, source/scope metadata, story identity, admission
  -> news_story_agent
     -> story packet, story-level run ledger, story-level current brief
  -> news_page_projection
     -> projected story rows only
  -> API/UI read projected current rows
```

This replaces the product-facing item-brief model with a story-brief model. It does not require price data, stock/crypto return windows, or future eval labels.

### New or revised News-only objects

**NewsStoryPacket**: deterministic host-built packet for a story key. It should contain:

- `story_key`, `story_identity_version`, story basis, member ids, representative id.
- Source timeline from observation edges and member items.
- Provider article keys and duplicate/source counts.
- Representative item source text excerpt and bounded additional member snippets.
- Entity lanes and fact lanes merged from story members, with deterministic caps and stable ordering.
- Source authority and source-quality fields.
- Agent admission and material-delta basis.
- Existing scope labels as metadata only, not as a trigger to read external price data.
- Evidence refs that point only to packet material.

**news_story_agent_runs**: append-only audit ledger for story agent attempts. It should use a generated `run_id` for audit identity, but product identity must be stable: `story_brief_key`, `story_key`, `story_identity_version`, `representative_news_item_id`, `input_hash`, prompt/schema/validator/guardrail versions, model audit, status/outcome, validation errors, request/response payloads.

**news_story_agent_briefs**: current read model keyed by stable `story_brief_key = sha256("news-story-brief|<story_identity_version>|<story_key>")`. One runtime writer. No run/generation/timestamp/UUID identity for current serving state. It should carry current `agent_run_id`, `status`, `decision_class`, `direction`, compact `brief_json`, `input_hash`, version fields, `computed_at_ms`, and representative/member evidence.

**story_brief dirty targets**: extend `news_projection_dirty_targets` with projection name `story_brief` and target kind `story`. The source watermark should be the maximum relevant story member source watermark. If implementation chooses item-target compatibility during migration, that should be temporary implementation scaffolding, not a public/runtime compatibility contract.

### Hard cut

The public and runtime read paths should no longer expose `news_item_agent_briefs` as the current story signal once the story agent is enabled. Old item brief tables may be migrated once or retained as hidden audit, but they must not be read as fallback current state. The API/UI should fail visibly or show story brief pending/failed when the story current row is absent; it should not reconstruct current story intelligence from legacy item brief fields.

This matches existing project discipline: raw `news_items` are worker inputs, `news_page_rows` are serving rows, and compatibility reconstruction is not a runtime surface.

## Design Invariants

The revised plan should enforce these invariants:

- News-only: no new cross-domain price reads, return-window tables, future eval labels, or backtest tables.
- Stable product keys: story current state is keyed by story identity version plus story key, never by run id or timestamp.
- Single writer: only `NewsStoryAgentWorker` writes `news_story_agent_runs` and `news_story_agent_briefs`.
- Rebuildable projection: page rows consume current story brief state; unchanged projections write zero serving rows.
- Bounded packets: source text, member snippets, entity lanes, and fact lanes have explicit caps.
- Deterministic ordering: story packet input hash is stable under equivalent data.
- Evidence-only provider data: provider raw frames and provider ratings remain evidence/admission clues, not publishable brief output.
- Explicit skip states: exact duplicate, similar covered, burst, insufficient source, validation failed, and no material delta are visible states.
- No hidden compatibility: API/UI do not read item briefs as fallback after the hard cut.
- Audit retention: old item outputs can remain only as non-serving audit evidence.

## Migration Strategy

The migration should be a hard-cut sequence, not a soft compatibility layer:

1. Add story packet builder and unit tests against existing repository payloads.
2. Add `news_story_agent_runs` and `news_story_agent_briefs`.
3. Add dirty-target support for `story_brief`.
4. Add `NewsStoryAgentWorker` with the same reservation, validation, hash reuse, completed-run restore, failed-run reuse, and CAS queue discipline as the item worker.
5. Update page projection to consume story current brief. Remove item-brief fallback from public projection once story current is authoritative.
6. Update API/UI contract to show story brief state only.
7. Retire or archive item brief runtime paths. Delete public compatibility fields or map them once to the new story contract, not dynamically.

The existing item brief worker provides a strong implementation template. The new work should not invent a second LLM framework, second dirty queue, or direct API-triggered model execution.

## Test Strategy

The test plan should prove architecture, not just snapshots:

- Canonical dedupe: same public URL collapses; provider-global OpenNews id collapses across sources; live/homepage/aggregator URL does not become hard identity; different OpenNews ids with identical content hash do not over-collapse.
- Material duplicate: OpenNews missing/link fallback attaches to public URL items only inside the bounded material identity policy.
- Remap safety: when public URL arrives later, dirty targets move to the current item/story while old item outputs are not exposed as current story outputs.
- Admission: exact duplicate and similar covered stories do not call the model; material deltas can refresh the story current brief.
- Story packet hash: equivalent member order and duplicate observation order produce the same input hash.
- Dirty queue: `story_brief` targets coalesce by stable key and require positive source watermark.
- Worker reuse: fresh current story brief skips; matching completed run restores; matching failed run prevents repeated model calls.
- Projection: one story row per story key, row identity stable, unchanged payload writes zero serving rows.
- Public contract: `/api/news` and item detail read projected story brief state only; no legacy item brief fallback.
- Architecture harness: `news_story_agent_briefs` has one runtime writer; API/UI do not import worker/model clients; no compatibility reconstruction helpers exist for old item brief schema.

## Open Questions

1. Should the initial story packet use only the representative item's source excerpt plus compact member evidence, or include snippets from all authoritative/new-source members? The production-safe default is representative excerpt plus capped member snippets only when they introduce new facts/entities/source roles.
2. Should old `news_item_agent_runs` be migrated into `news_story_agent_runs`? The safer hard cut is no automatic migration for publication. Historical item runs can stay audit-only until a separate offline migration is justified.
3. Should story identity rules become data-driven? The current code works, but production operation would benefit from a reviewed event-template table or config with tests for exchange listings and high-value subject buckets.
4. Should provider rating remain a hard threshold? For now, yes as an LLM budget gate, but story-level admission should also consider source role upgrades and accepted fact deltas so one weak provider score does not suppress a materially stronger story member.

## Conclusion

The current News chain is deeper than the previous plan gave it credit for. It already has provider-item idempotency, strict canonical identity, observation edges, OpenNews material duplicate handling, strong identity remap, story identity, admission skip states, dirty-target CAS, agent capacity reservation, input-hash reuse, completed-run restore, failed-run reuse, and story-shaped page projection.

The production gap is narrower and more architectural: the serving product is story-shaped, but the current agent output is item-scoped. The next step should hard-cut to a News-only story agent current read model, remove public/runtime legacy item-brief exposure, and make same-type-news behavior explicit: deterministic processing may repeat per canonical item, but LLM current output is one current story packet per material story version.
