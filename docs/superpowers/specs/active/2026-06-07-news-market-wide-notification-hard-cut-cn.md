# Spec - News 市场级 Agent 与通知准入硬切根修

**Status**: Approved for implementation planning
**Date**: 2026-06-07
**Owner**: Qinghuan / Codex
**Supersedes**:

- `docs/superpowers/specs/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md`
- `docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-cn.md`
- `docs/superpowers/plans/active/2026-06-05-news-intel-hard-cut-root-fix-verification-cn.md`
- `docs/superpowers/specs/active/2026-06-06-news-agent-market-wide-dedup-admission-cn.md`
- `docs/superpowers/plans/active/2026-06-06-news-agent-market-wide-hard-cut-plan-cn.md`

The older active artefacts either scoped the change to agent admission only, preserved `analysis_admission_*` as a compatibility surface, or described stock/macro news as visible but not brief/push eligible. This spec is the root-fix contract for the full News chain.

## Background

News Intel already fetches configured news sources, persists provider items and normalized `news_items`, extracts deterministic entity/fact evidence, builds current item briefs, projects `news_page_rows`, and feeds `news_high_signal` notifications.

The product direction is now clear: News agent analysis is market-wide, not crypto-only. A high-quality news item can matter because of crypto, U.S. equities, macro/rates, commodities, FX, AI semiconductors, energy/geopolitics, private-company access, or broad market risk. The current prompt already says provider score >=80 news should be analyzed across those markets, not only crypto.

The current source still contains a second, older concept: `analysis_admission_*`. Its reason strings include `non_crypto_subject`, `no_crypto_native_evidence`, `provider_evidence_only`, and `analysis_not_admitted`. Those names were useful when News was crypto-analysis gated, but they are now wrong as product eligibility gates. They make a market-relevant SpaceX, equity, macro, rates, semis, or geopolitics item look like a crypto false positive rather than a market news candidate.

The 2026-06-07 sub-agent audit confirmed that this is not a single-line naming problem. The agent harness can produce and persist `decision_class=watch` or `driver`, but projection, repository, notification, API, docs, and tests still allow the old crypto admission state to override that market-wide outcome. The implementation must therefore cut the old state out of every runtime product path.

The root issue is not the LLM. It is that the runtime still has multiple overlapping gates:

- `NewsItemBriefAgent` prompt and schema are market-wide.
- `news_item_agent_admission` is mostly market-wide and score/duplicate/time/source based.
- `news_page_projection` still derives `alert_eligibility` from `analysis_admission_status == admitted`.
- `news_high_signal` repository and notification rules still filter candidates to `analysis_admission_status = 'admitted'`.
- Public API and frontend still expose `analysis_admission_*` as if it were product state.

That split lets a row be agent `watch` while still being notification-held by an old crypto gate. The fix must remove the old product gate, not add another compatibility layer around it.

## Current Audit

The current code path shows the split:

- `src/parallax/domains/news_intel/prompts/news_item_brief.md` describes market-wide analysis for crypto, U.S. equities, macro/rates, commodities, FX, sectors, and broad risk.
- `src/parallax/domains/news_intel/services/news_item_agent_admission.py` admits agent work based on processed state, provider source, provider score, published time, and duplicate/similar story evidence.
- `src/parallax/domains/news_intel/services/news_analysis_admission.py` still emits crypto-era reasons such as `non_crypto_subject`, `provider_evidence_only`, and `no_crypto_native_evidence`.
- `src/parallax/domains/news_intel/services/news_page_projection.py` still blocks `in_app_eligible` and `external_push_ready` when `analysis_admission_status != admitted`.
- `src/parallax/domains/news_intel/repositories/news_repository.py::list_news_high_signal_notification_candidates` still has `AND analysis_admission_status = 'admitted'`.
- `src/parallax/domains/notifications/services/notification_rules.py` still rechecks `analysis_admission_status == admitted` before building `news_high_signal` candidates.
- `src/parallax/domains/news_intel/repositories/news_repository.py::get_news_item_detail` still returns `analysis_admission_*` on the public item detail payload.
- `src/parallax/app/surfaces/api/schemas.py` exposes News list/detail as broad JSON objects, so generated OpenAPI cannot enforce removal of old public fields.
- `web/src/features/news/model/newsSignalViewModel.ts` and `web/src/features/news/ui/NewsTape.tsx` do not render `non_crypto_subject` directly, but they derive agent-ready/hold text from `external_push_ready`; when that field is legacy-blocked, the UI makes an agent `watch` look like a product hold.
- `src/parallax/integrations/model_execution/news_item_brief_agent_client.py` and `src/parallax/integrations/model_execution/execution_gateway.py` compute artifact hashes from prompt version/schema/runtime, but not the actual prompt text. Prompt edits can therefore drift if a version bump is missed.
- `src/parallax/domains/news_intel/services/news_item_brief_validation.py` validates market impact labels against item/entity/fact text but not provider market-impact labels, so provider-only market scopes can be stripped from otherwise valid non-crypto briefs.
- Active 2026-06-05 and 2026-06-06 specs/plans still define conflicting News eligibility behavior and must not remain active after this root fix starts.

These are not independent policy choices. They are stale crypto-only compatibility seams in a market-wide News product.

## Problem

The system cannot explain push eligibility cleanly because it mixes two decisions:

1. **Market research decision**: is this item/story worth a market-wide agent brief?
2. **Notification decision**: is the current market-wide brief strong and fresh enough to notify?

`analysis_admission_*` answers neither question cleanly anymore. It asks whether an item has crypto-native evidence. That makes it the wrong abstraction for News.

The product failure mode is:

- high-quality non-crypto market news may be analyzed by the agent;
- the agent may return `driver` or `watch`;
- projection/notifications can still suppress it with `analysis_not_admitted` or `non_crypto_subject`;
- users see contradictory states and cannot tell what would be pushed.
- future agents can follow an older active spec/plan and reintroduce compatibility code because the planning lane itself still contains conflicting active truth.

## Goal

Hard-cut News from crypto-only admission to one market-wide product policy:

```text
provider/news facts
  -> deterministic story and duplicate/similar evidence
  -> market-wide agent admission
  -> NewsItemBriefAgent
  -> market-wide notification eligibility
  -> in-app / external delivery
```

No public or runtime product gate may use `non_crypto_subject`, `no_crypto_native_evidence`, `provider_evidence_only`, or `analysis_not_admitted`.

## Non-Goals

- Do not remove `NON_CRYPTO` / `non_crypto` from token identity, deterministic resolver, or Stocks Radar. Those are correct identity classifications. This spec removes crypto-only **News product gates**, not the ability to identify equities or non-crypto instruments.
- Do not add an LLM agent/actor that queries the database for duplicate news. Duplicate and story decisions must stay deterministic and repository/service owned.
- Do not create dual-read compatibility from old `analysis_admission_*` fields.
- Do not keep old API fields as deprecated aliases.
- Do not run agents from API handlers, frontend code, or notification delivery code.
- Do not lower thresholds in this spec. Defaults remain policy/config choices.

## First Principles

1. **One product gate per concern.** Agent admission decides whether to run a brief. Notification eligibility decides whether to notify. No hidden third crypto gate.
2. **Market scope is metadata, not exclusion.** `crypto`, `us_equity`, `macro_rates`, `energy_geopolitics`, `ai_semiconductors`, `private_company`, and `unknown` help prompt/UI/diagnostics; they do not block high-score market news by themselves.
3. **Provider score opens the candidate door; duplicate/similar closes it.** For score-qualified processed provider items, deterministic duplicate/similar/source/time/capacity rules are the only normal reasons not to produce a new brief.
4. **Agent output is not a fact.** The model can explain impact and choose `driver/watch/context/discard`; it cannot decide identity, story membership, or duplicate evidence.
5. **Notifications require a ready market brief.** Provider score alone is evidence, not a publishable notification. In-app and external notifications use the same ready-brief decision basis, with external delivery allowed to have stricter channel/score/cooldown rules.
6. **Hard cut beats compatibility.** Remove old callers, fields, tests, and docs. Reproject/backfill state into the new shape rather than reading old and new shapes together.
7. **The harness must fail on the old abstraction.** Architecture, API, schema, and notification tests must reject product-path references to `analysis_admission_*` and the old not-crypto reason strings.
8. **Prompt content is part of the agent artefact.** A prompt edit must change the artifact hash or fail freshness checks even if a human forgets to bump a version constant.

## Target Model

### Market Scope

Market scope is a compact classification payload derived from content, source, provider impacts, entities, and facts.

Example values:

- `crypto`
- `us_equity`
- `macro_rates`
- `energy_geopolitics`
- `commodities`
- `fx`
- `ai_semiconductors`
- `private_company`
- `broad_risk`
- `unknown`

Invariant: market scope never has values like `non_crypto_subject` or `no_crypto_native_evidence`. It describes what market the item may affect; it does not encode rejection.

### Agent Admission

Agent admission is the only runtime gate for item/story brief work.

Allowed statuses:

- `eligible`
- `eligible_refresh`
- `exact_duplicate`
- `similar_story_covered`
- `similar_story_burst`
- `materially_superseded`
- `score_below_threshold`
- `source_suppressed`
- `operational_disabled`
- `needs_review`

Allowed skip reasons for score-qualified market news:

- `exact_duplicate`
- `similar_story_covered`
- `similar_story_burst`
- `material_delta_absent`
- `materially_superseded`
- `source_suppressed`
- `published_too_old`
- `published_in_future`
- `classification_missing`
- `source_not_provider_signal`
- `below_score_threshold`
- `operational_disabled`
- `agent_backpressure`

Forbidden skip reasons:

- `non_crypto_subject`
- `no_crypto_native_evidence`
- `provider_evidence_only`
- `analysis_not_admitted`
- `legacy_crypto_gate`
- any reason whose only meaning is "not crypto"

### Agent Brief

The current `NewsItemBriefPayload` remains market-wide:

- `status`: `ready | insufficient | failed`
- `decision_class`: `driver | watch | context | discard`
- `direction`: `bullish | bearish | mixed | neutral`
- market-wide `market_impacts[]`
- `watch_triggers[]`
- `invalidation_conditions[]`
- `data_gaps[]`

`status=insufficient` is allowed for thin or low-confidence inputs; it does not become a push candidate.

### Notification Eligibility

Projection writes one explicit `signal.alert_eligibility` envelope derived from market-wide state only.

Fields:

- `agent_status`
- `decision_class`
- `provider_score`
- `in_app_eligible`
- `external_push_ready`
- `external_push_block_reason`
- `external_push_basis`
- `agent_admission_status`
- `agent_admission_reason`
- `market_scope`

Rules:

- `in_app_eligible = true` only when:
  - source is enabled and current projection is fresh;
  - provider score meets the `news_high_signal.combined_score_min` threshold;
  - current representative agent brief is `ready`;
  - `decision_class in {"driver", "watch"}`;
  - row is not exact/similar duplicate suppressed, stale, or operationally disabled.
- `external_push_ready = true` only when all in-app conditions hold and:
  - configured external channel exists;
  - provider score meets `news_high_signal.external_score_min`;
  - brief has publishable `summary_zh` or `market_read_zh`;
  - story/entity cooldown allows delivery.
- `context`, `discard`, `insufficient`, `failed`, `pending`, `exact_duplicate`, `similar_story_covered`, and `similar_story_burst` are not push-ready.

Forbidden block reasons:

- `analysis_not_admitted`
- `non_crypto_subject`
- `no_crypto_native_evidence`
- `provider_evidence_only`

Replacement block reasons:

- `agent_brief_not_ready`
- `agent_brief_missing_summary`
- `decision_not_notifiable`
- `score_below_notification_threshold`
- `source_suppressed`
- `story_duplicate_suppressed`
- `similar_story_suppressed`
- `external_channel_not_configured`
- `cooldown_active`
- `stale_projection`

## Target Runtime Flow

```text
news_fetch
  -> news_provider_items / news_items
  -> news_item_process
     -> deterministic entities / token mentions / fact candidates
     -> content classification + market_scope metadata
     -> story identity
     -> market-wide agent admission
     -> enqueue representative brief_input only when eligible/refresh
  -> news_item_brief
     -> recheck market-wide admission
     -> reserve news.item_brief
     -> AgentExecutionGateway structured JSON call
     -> validate NewsItemBriefPayload
     -> write news_item_agent_runs / news_item_agent_briefs
  -> news_page_projection
     -> project story row, compact brief, market_scope, alert_eligibility
  -> notification_worker
     -> query market-wide high-signal rows
     -> create in-app/external notification candidates
```

No stage reads `analysis_admission_*`.

The only allowed appearances of `analysis_admission`, `non_crypto_subject`, `no_crypto_native_evidence`, `provider_evidence_only`, or `analysis_not_admitted` after the hard cut are:

- historical completed specs/plans;
- migration downgrade or drop-column comments;
- one-off cleanup/audit scripts that explicitly identify the old state as removed.

## Required Hard Cuts

### Runtime Code

- Delete `news_analysis_admission.py` or replace it with a market-scope classifier that has no rejected/not-crypto status.
- Remove calls to `decide_news_analysis_admission` from `NewsItemProcessWorker`.
- Remove `analysis_admission` from story identity inputs and replace it with market scope/content/fact evidence.
- Remove `analysis_admission_status`, `analysis_admission_reason`, and `analysis_admission_json` from `build_news_page_row`.
- Remove `analysis_admission_status == "admitted"` from `_alert_eligible`.
- Remove `analysis_admission_status == "admitted"` from `_external_push_readiness`.
- Remove `analysis_admission_status = 'admitted'` from `list_news_high_signal_notification_candidates`.
- Remove the duplicate admitted recheck from `NotificationRuleEngine._news_high_signal_candidates`.
- Remove old reason assertions from notification and projection tests.
- Keep provider score thresholds and external channel/cooldown checks.
- Include the prompt text hash in News item brief artifact/audit hashes.
- Treat provider market-impact labels as source-backed evidence during brief validation.

### Storage

Add one hard-cut migration:

- Drop `news_items.analysis_admission_status`.
- Drop `news_items.analysis_admission_reason`.
- Drop `news_items.analysis_admission_json`.
- Drop `news_items.analysis_admission_version`.
- Drop `news_items.analysis_admission_computed_at_ms` if present.
- Drop the matching `news_page_rows.analysis_admission_*` columns.
- Drop indexes whose only purpose is `analysis_admission_*` filtering.
- Add `news_items.market_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb`.
- Add `news_page_rows.market_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb`.

There is no compatibility mode. After the migration, code must not reference the dropped columns.

### API And Frontend

- Remove `analysis_admission_status`, `analysis_admission_reason`, and `analysis_admission` from public `/api/news` and `/api/news/items/{news_item_id}` contracts.
- Expose `market_scope` and `agent_admission` instead.
- Replace broad News API response models with explicit row/detail models that make old-field regressions visible in OpenAPI/type generation.
- Item detail should explain:
  - whether the row has a ready brief;
  - whether it is a representative, exact duplicate, similar-story covered, burst-suppressed, or refresh;
  - why it is or is not notification eligible.
- UI text must not say "non crypto", "not admitted", or "page material not admitted" as a push explanation.
- Generated OpenAPI/frontend contract files must be regenerated, not manually patched with optional legacy fields.

### Docs

Update canonical docs in the same implementation PR:

- `docs/CONTRACTS.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKERS.md`
- `docs/AGENT_EXECUTION.md` if the packet/stage contract changes
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `AGENTS.md` and `CLAUDE.md` only if router wording changes
- Move or replace the superseded 2026-06-05 and 2026-06-06 active specs/plans with short superseded pointers. Do not leave active artefacts that define crypto-only or compatibility News eligibility rules.

Docs must state that News item brief and notifications are market-wide, while token identity can still classify instruments as non-crypto.

## Acceptance Criteria

- AC1. WHEN a processed provider item has score >= the agent threshold, valid published time, enabled source, and no duplicate/similar suppression THEN `NewsItemProcessWorker` SHALL enqueue or mark pending a News item brief regardless of crypto evidence.
- AC2. WHEN a score-qualified US equity, private-company, macro/rates, semis, commodity, FX, or energy/geopolitics item lacks crypto evidence THEN no runtime product state SHALL use `non_crypto_subject`, `no_crypto_native_evidence`, `provider_evidence_only`, or `analysis_not_admitted`.
- AC3. WHEN a representative brief is `ready`, provider score meets notification threshold, and `decision_class` is `driver` or `watch` THEN projection SHALL mark `in_app_eligible=true` without checking crypto admission.
- AC4. WHEN the same row also has external channels configured, meets external score threshold, has a publishable summary/market read, and passes cooldown THEN projection/notification SHALL allow external push.
- AC5. WHEN `decision_class` is `context` or `discard` THEN the row SHALL remain visible in News but SHALL NOT become a high-signal notification.
- AC6. WHEN brief status is `pending`, `insufficient`, or `failed` THEN the row SHALL NOT become a high-signal notification, and block reason SHALL be brief/status specific.
- AC7. WHEN a row is exact duplicate or similar-story covered without material delta THEN it SHALL not run a new model call and SHALL not create its own notification candidate.
- AC8. WHEN a similar-story item has material delta THEN it SHALL enqueue a refresh target and notification eligibility SHALL be evaluated from the refreshed representative brief.
- AC9. WHEN `rg "analysis_admission|non_crypto_subject|no_crypto_native_evidence|analysis_not_admitted" src/parallax/domains/news_intel src/parallax/domains/notifications web/src` runs after implementation THEN no runtime product-path references SHALL remain. References are allowed only in a migration downgrade, historical docs, or explicit cleanup/audit scripts.
- AC10. WHEN tests inspect `news_item_brief.md` THEN it SHALL remain market-wide and include equities/macro/rates/commodities/FX/broad risk language.
- AC11. WHEN generated API types are checked THEN public News row/detail schemas SHALL not include `analysis_admission_*`.
- AC12. WHEN `news_high_signal` repository query is inspected THEN it SHALL not filter on `analysis_admission_status`.
- AC13. WHEN notification rules are inspected THEN they SHALL not recheck `analysis_admission_status`.
- AC14. WHEN fixtures cover crypto, US equity, private company, macro/rates, and energy/geopolitics high-score rows THEN notification eligibility SHALL be decided by ready brief, decision class, score, recency, source, duplicate/similar, external channel, and cooldown only.
- AC15. WHEN the same repair/reprojection command is run twice on an unchanged window THEN the second run SHALL write zero unchanged serving rows and enqueue zero duplicate brief targets.
- AC16. WHEN docs are updated THEN no canonical doc SHALL describe News item brief or `news_high_signal` as crypto-admitted only.
- AC17. WHEN active specs are listed THEN no other active spec SHALL define a conflicting crypto-only News agent or notification gate.
- AC18. WHEN OpenAPI is regenerated THEN News list/detail schemas SHALL explicitly expose `market_scope`, `agent_admission`, `agent_brief`, and `signal.alert_eligibility`, and SHALL NOT expose `analysis_admission_*`.
- AC19. WHEN `NewsItemBriefAgent` prompt text changes THEN the agent artifact hash and request audit SHALL change even if version constants are unchanged.
- AC20. WHEN a provider-only market impact label is present in the input packet THEN `news_item_brief_validation` SHALL treat that label as source-backed and SHALL NOT strip it solely because it is absent from item text/entity/fact lanes.
- AC21. WHEN `web/src` renders agent status THEN an agent `ready + watch/driver` outcome SHALL not be labelled as agent hold merely because external push is blocked by channel/threshold/cooldown.
- AC22. WHEN storage schema tests inspect the head migration graph THEN old `analysis_admission_*` columns and indexes SHALL be absent from `news_items` and `news_page_rows`, and `market_scope_json` SHALL be present on both.

## Test Plan

Unit tests:

- `tests/unit/domains/news_intel/test_news_item_agent_admission.py`
  - score-qualified non-crypto market examples are eligible;
  - duplicate/similar examples are suppressed;
  - forbidden reasons never appear.
- `tests/unit/domains/news_intel/test_news_page_projection.py`
  - ready `driver/watch` brief with high score sets `in_app_eligible=true`;
  - non-crypto market scope does not block eligibility;
  - `context/discard/insufficient/failed/pending` block for explicit reasons.
- `tests/unit/test_notification_rules.py`
  - `news_high_signal` no longer skips page-only/non-crypto rows;
  - external push readiness uses score/channel/summary/cooldown, not analysis admission.
- `tests/architecture/test_news_intel_kiss_simplification.py`
  - runtime product paths contain no `analysis_admission`, `non_crypto_subject`, `no_crypto_native_evidence`, `analysis_not_admitted`.
- `tests/architecture/test_news_active_spec_hygiene.py`
  - no active News spec/plan except this spec and its plan may define `analysis_admission_*` as a product gate.
- `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
  - provider market impact labels are source-backed evidence.
- `tests/unit/integrations/model_execution/test_news_item_brief_artifact_hash.py`
  - prompt text hash participates in request audit/artifact hash.
- `tests/unit/test_api_news_contract.py`
  - public News detail exposes market scope and agent state but not old admission fields.
- `tests/unit/test_postgres_schema.py`
  - head migration drops old columns/indexes and adds `market_scope_json`.

Integration tests:

- News repository high-signal candidate query returns high-score market-wide rows without crypto admission columns.
- API `/api/news` and `/api/news/items/{id}` expose market scope and agent/notification state, not `analysis_admission_*`.
- Notification worker creates one story-level candidate for a market-wide ready `watch` row and suppresses duplicate/similar rows.
- Alembic migration drops old columns and indexes.
- The repair command enqueues page/brief dirty targets and never writes `news_page_rows` directly outside `NewsPageProjectionWorker`.

Operational checks:

- `uv run parallax config` confirms live config paths before any real-data diagnosis.
- Dry-run repair/reprojection reports counts by new agent/notification reason.
- No secrets or provider tokens are printed.

## Migration And Repair

Implementation SHALL include a bounded operator repair path:

```text
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80 --dry-run
uv run parallax ops repair-news-market-signal --since-hours 8 --min-score 80
```

The command SHALL:

- recompute market scope;
- recompute market-wide agent admission;
- enqueue missing representative brief targets;
- reproject affected page rows;
- report counts by new status/reason;
- never execute LLM calls inline;
- never read or write old `analysis_admission_*`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Notification volume increases after non-crypto market rows become eligible | High | Keep score thresholds, ready-brief requirement, `driver/watch` requirement, story dedup, external cooldown, and source enabled checks. |
| Agent cost increases | High | Agent admission remains score/time/source/duplicate/similar gated; representative-first target selection prevents per-duplicate calls. |
| Removing `analysis_admission_*` breaks stale API/UI expectations | Medium | This is intentional hard cut; regenerate API types and update UI in same PR. |
| Non-crypto identity classification is accidentally deleted from token resolver | High | Scope hard cut to News product gates only; tests should allow resolver `NON_CRYPTO` and Stocks Radar behavior. |
| Provider score alone triggers notifications | Medium | Require ready agent brief and `driver/watch`; provider score alone is never push-ready. |
| Similar story suppression hides a material update | High | Material delta forces `eligible_refresh`; tests cover source-role upgrade, new entity/fact, score upgrade, stale brief. |
| Historical rows keep stale eligibility | Medium | Migration plus repair/reprojection; unchanged projections write zero serving rows. |

## Alternatives Rejected

- **Keep `analysis_admission_*` but reinterpret non-crypto as market scope.** Rejected. Reusing rejected-status names as metadata is confusing and keeps compatibility code alive.
- **Only remove `non_crypto_subject` string.** Rejected. The root problem is the old crypto gate, not one reason name.
- **Let notification rules override projection eligibility.** Rejected. That creates another hidden policy layer.
- **Allow provider score alone to notify while agent is pending.** Rejected. Provider score is evidence; notifications need a validated market-wide brief.
- **Add an LLM dedup actor.** Rejected. Dedup/story membership is product truth and must be deterministic, auditable, and replayable.
- **Leave old API fields optional for old clients.** Rejected. This is an internal app hard cut; optional legacy fields invite regressions.

## Reader Checklist

Before writing the implementation plan, confirm:

- The desired behavior is market-wide News, not crypto-only News.
- External push is allowed for non-crypto market news when the same ready-brief/score/channel/cooldown rules pass.
- `NON_CRYPTO` identity classification remains valid outside News product gating.
- Old `analysis_admission_*` fields should be hard-dropped from runtime schema/API, not merely hidden in UI.
