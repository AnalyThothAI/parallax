# Equity Event Intel Architecture

`equity_event_intel` is the event-first U.S. equity update domain. It tracks
official company-reporting events for the configured universe, materializes
earnings/calendar read models, and publishes cited agent briefs. It is not a
stock-first profile store and it does not write News Intel, Token Radar, Pulse,
or market-tick facts.

## Truth Tables

Provider observations and material event facts live in PostgreSQL:

- `equity_event_sources`: configured SEC/IR/calendar sources, CIK/ticker/company
  identity, refresh cadence, cursor state, and redacted source health.
- `equity_event_universe_members`: configured company universe and display
  priority used by projections.
- `equity_expected_events`: expected earnings/call/filing events and matching
  lifecycle state.
- `equity_event_fetch_runs`: provider fetch audit and retry/backoff state.
- `equity_provider_documents`: provider-natural-key observations and raw
  provider metadata hashes.
- `equity_event_documents`: normalized official documents/releases/transcripts
  attached to source/company identity.
- `equity_company_events`: material company-event facts classified from
  official documents.
- `equity_event_source_spans`: cited source snippets extracted from official
  documents.
- `equity_event_fact_candidates`: typed facts/candidates with metric/value,
  period, source span, validation status, and rejection reasons.
- `equity_event_agent_runs`: append-only brief-agent audit ledger.
- `equity_event_agent_briefs`: current cited brief state per company event.

Provider raw frames and HTTP responses are inputs. Product surfaces must read
facts and read models, not provider raw payloads.

## Read Models

Read models are rebuildable and have exactly one runtime writer:

- `equity_event_story_groups` and `equity_event_story_members` are written only
  by `EquityEventStoryProjectionWorker`.
- `equity_event_agent_runs` and `equity_event_agent_briefs` are written only by
  `EquityEventBriefWorker`.
- `equity_event_page_rows`, `equity_event_calendar_rows`,
  `equity_event_alert_candidates`, and `equity_company_timeline_rows` are
  written only by `EquityEventPageProjectionWorker`.

The public API reads through `EquityEventQuery` and repository read methods.
Routes under `/api/equity-events*` are read-only: no provider calls, no filing
parsing, no worker imports, no LLM calls, and no projection rebuilds.

## Worker Flow

```text
configured company universe / expected events
  -> EquityEventSourceReconcileWorker
  -> equity_event_sources + equity_expected_events
  -> EquityEventFetchWorker
  -> equity_provider_documents + equity_event_documents
  -> EquityEventProcessWorker
  -> equity_company_events + source spans + fact candidates
  -> EquityEventStoryProjectionWorker
  -> story groups + story members
  -> EquityEventBriefWorker
  -> cited agent runs + current briefs
  -> EquityEventPageProjectionWorker
  -> feed/calendar/alert/timeline read models
  -> /api/equity-events* -> web /earnings
```

Every worker wakes from PostgreSQL `NOTIFY` only as a hint and also has bounded
`interval_seconds` catch-up. Missed wakes must not stall the event chain.

## Source Roles

The domain keeps source roles explicit because official company reporting is not
generic news:

- `official_regulator`: SEC submission or regulator-hosted filing.
- `official_issuer`: investor-relations release, shareholder letter, deck, or
  company-hosted transcript.
- `calendar`: expected event schedule or call timing.
- `transcript`: earnings-call or conference transcript source.
- `media_context`: non-official context only; it must not become accepted fact
  without official evidence.

`EquityEventBriefWorker` only builds publishable briefs from bounded official
evidence packets. Missing evidence is represented as `insufficient` plus
`data_gaps`, not inferred in the frontend.

## Boundaries

- This domain must not write `news_items`, `news_page_rows`,
  `token_radar_rows`, `pulse_candidates`, or `market_ticks`.
- API/frontend code must not import equity event workers, SEC clients,
  provider libraries, event classifiers, or fact extractors.
- `/earnings` renders backend read models and persisted brief states directly.
  It must not infer event type, surprise, bull/bear thesis, or trading decision
  from headlines, summaries, or local keyword rules.
