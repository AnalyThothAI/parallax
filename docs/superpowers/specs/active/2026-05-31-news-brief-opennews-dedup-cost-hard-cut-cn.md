# Spec - News Brief OpenNews Dedup + LLM Cost Hard Cut

Status: Draft  
Date: 2026-05-31  
Owner: Qinghuan / Codex  
Related specs:

- `docs/superpowers/specs/active/2026-05-20-news-item-agent-brief-deployment.md`
- `docs/superpowers/specs/active/2026-05-28-news-intel-dedup-root-fix-cn.md`
- `docs/superpowers/specs/active/2026-05-30-news-item-brief-llm-cost-root-fix-cn.md`

This spec extends the 2026-05-30 LLM cost root-fix spec. The new root cause is broader than unstable brief input hashes: OpenNews historical/backfill entries and material duplicate news items are reaching the brief LLM path, and validation retries multiply the damage.

## One-Line Goal

News brief LLM must run only for fresh, canonical-deduplicated, high-value news items. Historical OpenNews backfill, mirror/preview duplicates, URL-case duplicates, and non-representative duplicate items must be excluded before provider execution. Database raw observations must be preserved, but serving/canonical items and `brief_input` work must collapse to one material event.

## Context

The operator expectation is correct: with an 80-point threshold, the brief path should be cheap. In the recent 8-hour production window, the number of truly fresh 80+ items was small. The high token spend came from old OpenNews entries fetched recently, material duplicate rows in `news_items`, and repeated full-model retries after domain validation failures.

Runtime config was verified with:

```bash
uv run parallax config
```

The reported runtime paths were:

- config: `/Users/qinghuan/.parallax/config.yaml`
- workers config: `/Users/qinghuan/.parallax/workers.yaml`

No secret values were printed or copied.

Relevant runtime settings observed:

- `news_fetch`: enabled, interval 60s, batch size 5
- `news_item_process`: enabled, batch size 100, wakes on `news_item_written`
- `news_item_brief`: enabled, interval 10s, batch size 1, max attempts 3, wakes on `news_item_processed`
- `agent_runtime.news.item_brief`: model `deepseek-v4-flash`, max concurrency 1, no lane RPM limit
- `opennews-news`: enabled, `rest_limit=100`, `max_rest_pages=5`, `rest_overlap_ms=900000`
- `opennews-listing`: enabled, `rest_limit=100`, `max_rest_pages=5`, `rest_overlap_ms=900000`

## Production Evidence

Window: recent 8 hours on 2026-05-31.

News volume by fetched/created time:

- fetched/created/processed items: about 855 to 863
- provider score `>=80`: 65
- provider score `>=85`: 34

News volume by true `published_at`:

- published in the last 8 hours: 199
- published in the last 8 hours and score `>=80`: 12
- published in the last 8 hours and score `>=85`: 6

This means most 80+ items processed in the window were not fresh news. They were historical items fetched or reprocessed now.

LLM cost for score `>=80` items in the same window:

- agent runs: 82
- distinct news items: 65
- total tokens: 421,494
- prompt tokens: 344,554
- output tokens: 76,940
- cache-hit prompt tokens: 246,400
- cache-miss prompt tokens: 98,154
- estimated DeepSeek v4-flash cost: about 0.036 USD, about 0.255 CNY at 7.10 CNY/USD

Breakdown:

- `opennews-listing`, historical published items: 38 items, 52 runs, 272,413 tokens, about 0.024 USD
- `opennews-news`, fresh published items: 12 items, 14 runs, 68,423 tokens, about 0.0052 USD
- `opennews-news`, historical published items: 15 items, 16 runs, 80,658 tokens, about 0.0068 USD

Expected steady-state for fresh 80+ items should have looked closer to the 12-item fresh slice, not the full 65-item fetched slice.

## Database Duplicate Evidence

The database does prevent exact canonical-key duplicates:

- `news_items.canonical_item_key` has a unique index.
- `news_provider_items` has a unique `(source_id, source_item_key)` constraint.
- `news_item_observation_edges` is keyed by provider item id.

However, this is not sufficient. The current canonical key can split one material business event into multiple `news_items`.

Recent 8-hour duplicate observations:

- exact `content_hash` duplicate groups: 0
- `provider_article_key` mapping to multiple `news_items`: 0
- same `source_id + title_fingerprint` groups: 109 groups, 237 rows
- duplicate rows implied by same-source/title grouping: 128
- score `>=80` rows inside same-source/title duplicate groups: 30
- score `>=80` duplicate rows implied by same-source/title grouping: 16
- case-insensitive canonical URL duplicate groups: 28 groups, 56 rows
- score `>=80` rows inside case-insensitive URL duplicate groups: 9
- score `>=80` duplicate rows implied by case-insensitive URL grouping: 4

Representative duplicate examples:

- `https://twitter.com/coinbasemarkets/status/...` and `https://twitter.com/CoinbaseMarkets/status/...` became separate canonical items even though they are the same status id.
- Binance listing announcements appeared as separate `news_items` via:
  - official generic support URL: `https://www.binance.com/en/support/announcement`
  - `https://news.6551.io/preview/...`
  - `https://www.treeofalpha.com/preview_article?...`
  - content-hash fallback rows

The duplicate problem is therefore not raw provider-frame duplication. It is material event duplication caused by overly strong URL identity and weak event-level canonicalization.

## Agent Retry Evidence

For score `>=80` items:

- 65 items produced 82 LLM runs.
- There were 17 extra runs beyond one run per item.
- Retried items consumed about 149,164 tokens.
- `domain_validation_failed` accounted for 22 runs and about 110,275 tokens.
- `forbidden_execution_language` accounted for 21 runs and about 105,881 tokens.

Observed false-positive pattern:

- The validator flagged terms such as factual exchange/listing language, product names, or copied provider phrases.
- Examples include Chinese phrases around leverage, buying crypto, price movement, or English listing phrases such as `Buy Crypto`.
- These failures happen after the model call, then dirty-target retry can execute the full provider request again up to `max_attempts=3`.

## Code Findings

Canonical identity:

- `src/parallax/domains/news_intel/services/news_canonical_identity.py`
- Public canonical URL is selected before content hash, provider article id, or title fallback.
- URL identity is case-sensitive for important paths such as Twitter/X handles.
- Preview/mirror domains such as `news.6551.io/preview` and `treeofalpha.com/preview_article` can become strong canonical identities.
- Generic announcement URLs, especially exchange support pages, can also become strong identity even when they are not item-specific.

Repository upsert:

- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `upsert_canonical_news_item` reuses an existing item only when the provider article key already maps through observation edges.
- This does not collapse mirror URLs, preview URLs, generic URLs, or same-title exchange listing duplicates.
- `ON CONFLICT (canonical_item_key)` prevents exact duplicates but does not prevent material duplicates with different canonical keys.

OpenNews fetch:

- `src/parallax/app/runtime/provider_wiring/news.py`
- `RegistryBackedNewsSourceProvider.fetch` removes generic `since_ms` and relies on provider cursor semantics.

- `src/parallax/integrations/news_feeds/opennews_client.py`
- REST fetch uses cursor/high-watermark and page limits.
- REST search body supports source policy score/min_score, but no published-time cutoff.
- On initial cursor, recovery, or overlap, high-score historical listings can enter the system.

Brief eligibility:

- `src/parallax/domains/news_intel/services/news_item_agent_policy.py`
- Current policy is score-only: provider signal source and score threshold.
- It does not check true published age, backfill/replay status, source class, or canonical representative status.

Brief queue:

- `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Both enqueue or dirty `brief_input` from the score-only policy.

Brief worker:

- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- The worker can skip low-score targets before provider execution, but historically eligible high-score backfill and duplicate rows still reach the worker.
- Domain validation is performed after provider execution.
- Validation failure is retried through dirty-target retry up to max attempts.

Agent harness:

- `src/parallax/integrations/model_execution/news_item_brief_agent_client.py`
- `src/parallax/integrations/model_execution/execution_gateway.py`
- `src/parallax/integrations/model_execution/structured_json_strategy.py`
- The news brief path uses the agent execution gateway and usage audit path.
- This is not primarily a harness bypass. The root issue is that the harness is being asked to process the wrong units of work, and it has no business-level freshness/dedup/budget gate.

## Root Causes

1. OpenNews fetch can admit historical high-score entries because the provider request has no hard `published_at` cutoff and the generic `since_ms` boundary is not passed through.

2. News brief eligibility is score-only. It ignores true publish time, source mode, backfill/replay status, duplicate material-event status, and whether the item is the canonical representative.

3. Canonical identity treats public URL as a strong identity too early. Mirror/preview URLs, generic exchange announcement URLs, and case variants of social URLs split one business event into multiple `news_items`.

4. Database constraints prevent exact canonical duplicates but not material duplicates. Raw provider observations are correctly unique, but material news-event identity is not strong enough.

5. Brief dirty targets are created before dedup/freshness is proven. Once duplicate or historical rows exist, each row can independently produce LLM work.

6. Domain validation failures are expensive because they happen after the model call and then retry full LLM execution. `forbidden_execution_language` is currently too broad for exchange/listing news and is not treated as a terminal or locally repairable failure.

7. Agent harness is present, but it lacks a lane-level token/hour or item/hour budget for news brief. It records cost but does not prevent an unexpected workload expansion.

## Goals

- Freshness gate: news brief LLM runs only for items whose true `published_at` is inside a configured recent window.
- Dedup gate: only the canonical representative of a material event can enqueue or execute `brief_input`.
- Raw preservation: provider raw frames and observation edges are preserved; dedup must not destroy evidence.
- Canonical repair: mirror/preview/generic URLs should attach as observations or aliases, not split canonical `news_items`.
- Retry hard cut: validation failures must not repeatedly spend full LLM calls for the same bad output class.
- Auditability: operators can answer "how many fresh 80+ items", "how many duplicate groups", "how many skipped historical items", and "how many tokens/hour" from one diagnostic.
- Compatibility: existing serving surfaces continue to read from canonical facts and derived read models.

## Non-Goals

- Do not delete historical provider observations.
- Do not remove OpenNews as a provider.
- Do not use an LLM to decide dedup identity.
- Do not solve PushDeer delivery in this spec. PushDeer needs its own delivery/credential/retry spec.
- Do not rewrite the entire agent harness.
- Do not retroactively erase historical agent run ledgers. They are audit evidence.

## Proposed Design

### 1. Freshness Policy

Add an explicit brief freshness policy:

- Config name: `NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS`
- Default: 8 hours
- Policy input: `now_ms`, `published_at_ms`, provider score, source id, source kind, and optional backfill/replay marker
- Required for LLM:
  - source is a provider signal source
  - provider score is at or above the configured threshold
  - `published_at_ms` exists
  - `published_at_ms >= now_ms - max_age_ms`
  - item is not marked as historical backfill/replay
  - item is the canonical material-event representative

If `published_at_ms` is missing, the item must be ineligible for auto brief. Missing publish time can still be shown in operator UI and repaired manually.

### 2. OpenNews Published-Time Cutoff

OpenNews REST requests should include a hard published-time lower bound when fetching for live workers.

Required behavior:

- Worker computes the allowed lower bound from freshness policy plus a small overlap.
- OpenNews provider passes the bound to the API if supported.
- If the API cannot enforce it, client-side filtering must drop older entries before repository upsert for live fetch mode.
- A separate explicit repair/backfill mode can ingest old entries, but backfill mode must mark rows so they do not enter auto brief.

This keeps the fetch layer from filling the database with historical high-score items during live operation.

### 3. Material Event Identity

Introduce deterministic material-event identity in `news_canonical_identity.py`.

Identity priority should become:

1. Strong item-specific source id, when trustworthy.
2. Normalized item-specific public URL.
3. Source-event key for known exchange/listing/social templates.
4. Provider article key.
5. Content hash.
6. Weak title/source/window fallback.

URL normalization requirements:

- Lowercase scheme and host.
- Strip tracking params and volatile preview params.
- For Twitter/X status URLs, extract the numeric status id and canonicalize to one key independent of handle case or host variant.
- For known preview/mirror domains, do not treat the preview URL as a strong public URL identity:
  - `news.6551.io/preview/...`
  - `treeofalpha.com/preview_article?...`
- For generic exchange announcement landing pages, avoid using the generic URL alone as canonical item identity.

Source-event key requirements:

- For exchange/listing templates, derive a key from deterministic facts:
  - source family
  - venue, for example Binance
  - action, for example list, launch futures, add earn, extend monitoring tag
  - symbols/tickers
  - product type
  - effective date when present
  - normalized title fingerprint as a fallback component
- The key must not include fetched time, attempt id, run id, UUID, or provider preview URL.

### 4. Repository Merge Semantics

When a new provider item resolves to an existing material event:

- Reuse the existing canonical `news_items` row.
- Insert or update `news_provider_items` as usual.
- Attach observation edge to the existing `news_item_id`.
- Preserve provider payload, source item key, provider article key, and raw references.
- Merge or update provider score/source metadata conservatively.

When an existing duplicate group is discovered during repair:

- Select one representative item.
- Move observation edges to the representative where safe.
- Repoint derived facts and mentions to the representative where schema supports it.
- Keep old duplicate rows only if necessary for audit, but mark them as superseded/non-representative so they cannot enqueue brief or serving rows.
- Do not delete provider raw frames.

Representative ranking:

1. Official item-specific URL over preview/mirror URL.
2. Non-generic URL over generic support landing URL.
3. Existing current brief over no brief.
4. Highest provider score.
5. Earliest created canonical fact.

### 5. Brief Queue Guard

Every path that creates or executes `brief_input` must use the same eligibility function.

Required enforcement points:

- fetch worker before adding dirty target
- process worker before adding dirty target
- brief worker immediately before provider execution
- repair command when cleaning existing dirty targets

The brief worker must complete/skip ineligible targets without making a provider request. The skip reason must be written to diagnostics or target metadata.

Skip reasons:

- `below_score_threshold`
- `published_at_missing`
- `published_too_old`
- `backfill_or_replay`
- `not_material_representative`
- `source_not_auto_briefable`

### 6. Validation and Retry Policy

Domain validation failures must not cause repeated full LLM execution by default.

Required behavior:

- `forbidden_execution_language` is terminal after one provider call unless a deterministic sanitizer can fix it locally.
- `unknown_evidence_ref` may retry once only if the input packet changed.
- Any validation retry must include a stable input hash and previous validation code to prevent retrying the same prompt/output class.
- Retry count for domain validation should be separate from transient provider failures.

Validator precision improvements:

- Do not flag factual product names or copied source phrases such as `Buy Crypto` when they are part of an exchange announcement title or product surface.
- Do not flag neutral factual descriptions of listing availability as trading advice.
- Continue blocking explicit instructions to buy, sell, long, short, lever, enter, exit, set targets, or execute trades.

### 7. Cost Guard and Diagnostics

Add a diagnostic command or report section for news brief cost:

- items fetched in window
- items published in window
- items score `>=threshold`
- eligible fresh representative items
- skipped historical items
- skipped duplicate/non-representative items
- due `brief_input` targets
- LLM runs, tokens, estimated cost, cost/hour
- validation failures by code
- duplicate groups by identity type

Add an optional lane guard:

- max news brief starts per hour
- max news brief tokens per hour, based on audited usage
- warning-only mode first, then hard cap if needed

This is a guardrail. It must not replace the freshness and dedup fixes.

## Data Repair Plan

### Read-Only Audit

Before mutation, add or document SQL diagnostics for:

- recent high-score items fetched now but published before the freshness window
- same-source/title duplicate groups
- case-insensitive URL duplicate groups
- preview/mirror URL duplicate groups
- generic exchange announcement URL duplicate groups
- `brief_input` dirty targets for historical or duplicate items
- repeated agent runs by news item and by material-event group

### Safe Repair

Repair should run in explicit operator mode only.

Steps:

1. Build duplicate groups using the new material-event identity function.
2. Select representative per group.
3. Repoint observation edges and derived facts where safe.
4. Mark non-representative duplicate `news_items` as superseded if schema supports it, or record alias mapping in a new table if needed.
5. Delete or complete pending `brief_input` targets for superseded/non-representative items.
6. Preserve all provider raw items and agent run audit rows.
7. Emit a before/after report with row counts.

## Acceptance Criteria

1. With the observed 8-hour production window, 65 fetched score-80+ items no longer imply 65 LLM-brief candidates. Only the 12 truly fresh score-80+ material representatives are eligible by default.

2. A Binance listing item published on 2026-05-21 and fetched on 2026-05-31 is stored only as historical evidence and does not enqueue or execute `brief_input` during live operation.

3. A Binance announcement seen through official URL, `news.6551.io/preview`, `treeofalpha.com/preview_article`, and content-hash fallback resolves to one material event or at minimum one brief-eligible representative.

4. Twitter/X status URL case variants resolve to the same canonical identity.

5. Exact provider raw observations remain preserved. Dedup does not delete `news_provider_items` evidence.

6. `news_projection_dirty_targets` has no due `brief_input` rows for historical, superseded, or non-representative duplicate items after the repair command runs.

7. `forbidden_execution_language` cannot create three full LLM calls for the same unchanged item/input hash.

8. Domain validation still blocks explicit trading instructions, but factual exchange/listing product language does not repeatedly fail and retry.

9. The steady-state score-80+ brief path for the observed window would consume roughly the fresh slice only: target below 100,000 tokens per 8 hours for equivalent conditions, absent an actual surge in fresh high-score news.

10. The operator diagnostic can explain token spend by source, freshness, duplicate class, retry class, and estimated price.

## Verification Plan

Unit tests:

- `news_item_agent_policy`:
  - score threshold
  - published age cutoff
  - missing publish time
  - backfill/replay marker
  - non-representative marker
- `news_canonical_identity`:
  - Twitter/X status URL case normalization
  - preview/mirror URL demotion
  - Binance generic support URL is not enough for unique item identity
  - exchange listing source-event key stability
- `news_item_brief_validation`:
  - explicit trade instruction remains blocked
  - factual listing/product language is not treated as trading advice

Worker tests:

- fetch worker does not create `brief_input` for old published items.
- process worker does not create `brief_input` for old published items.
- brief worker completes/skips ineligible existing targets before provider execution.
- validation failure retry policy does not call provider repeatedly for the same unchanged validation failure.

Repository/integration tests:

- multiple provider observations for the same material event attach to one canonical item.
- provider raw rows remain unique and preserved.
- duplicate repair repoints or marks non-representatives and clears their pending brief targets.

Manual production verification:

```bash
uv run parallax config
uv run python -m pytest tests/unit/domains/news_intel/test_news_item_agent_policy.py
uv run python -m pytest tests/unit/domains/news_intel/test_news_canonical_identity.py
uv run python -m pytest tests/unit/domains/news_intel/test_news_item_brief_worker.py
uv run python -m pytest tests/integration/domains/news_intel/test_news_repository.py
```

Then run the read-only diagnostic against the real database and verify:

- fresh score-80+ count
- eligible brief count
- skipped historical count
- skipped duplicate count
- due brief targets
- agent tokens/hour and estimated cost/hour

## Rollout Plan

1. Ship read-only diagnostics first.
2. Ship freshness gate in all brief enqueue and execution paths.
3. Ship URL normalization and preview/mirror demotion with tests.
4. Ship material-event identity for exchange/listing templates.
5. Ship validation retry hard cut.
6. Run read-only duplicate audit.
7. Run explicit repair on a small recent window.
8. Rebuild affected read models if needed.
9. Expand repair window only after counts match expectations.

## Open Questions

- Should the default freshness window be exactly 8 hours or 12 hours? Recommendation: 8 hours for automatic LLM brief, configurable for operator repair.
- Should `opennews-listing` ever auto-brief older listings? Recommendation: no, except explicit manual repair/backfill mode.
- Should duplicate rows be physically merged or marked as superseded with alias mapping? Recommendation: mark/alias first unless schema ownership is clear.
- Should the lane token/hour guard be warning-only or hard cap at first rollout? Recommendation: warning-only until dedup/freshness repair is verified.

