# Pulse Lab Architecture

> **Scope.** Owns Signal Pulse: candidate gate, agent route policy, stage
> runtime, decision persistence, and the audit ledger. Global package
> boundaries live in `../../../../docs/ARCHITECTURE.md`; the public Pulse
> decision contract lives in `../../../../docs/CONTRACTS.md`; operational
> rules for the audit ledger live in
> `../../../../docs/RELIABILITY.md`.

Signal Pulse is the first concrete strategy on the unified Agent Runtime
Core. It turns Token Radar projection rows into agent decisions and
persists a replayable audit trail. It does not own ranking, projection,
asset identity, or market data.

## Stage Map

v2 (plan 2026-05-16) replaces the prior three-stage
`analyst / critic / judge` runtime with a two-stage
`investigator → decision_maker` flow plus a `research_only_gate`
short-circuit for hard-blocked candidates. The DB CHECK constraint on
`pulse_agent_run_steps.stage` enforces this enum; historical rows from
the v1 era remain readable but are no longer producible.

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Candidate gate | `services/pulse_candidate_gate.py` | none (in-memory admission) | Reads the public `factor_snapshot_json.market.decision_latest` response key, `normalization.cohort_status`, and gate fields. That market key is generated from `enriched_events` and `market_ticks`, not an internal DB role. Fails closed when target rows lack current market context or have an insufficient/all-tied cohort. |
| Agent route policy | `services/agent_routing.py` | none (in-memory decision) | Deterministic route assignment to `cex`, `meme`, or `research_only`. Completeness gates are driven by the `pulse_candidate` worker settings in `workers.yaml`. |
| Stage contract runtime | `services/pulse_decision_runtime.py` | none (in-memory stage specs / validation / audit assembly) | Loads prompts, builds stage input payloads, computes request/output hashes, validates cited evidence ids, and enriches final evidence URLs. Pure domain code: no OpenAI SDK or integration imports. |
| Tool query runtime | `services/agent_tool_runtime.py` | none (read-only query facade) | Owns tool budgets, query parameter bounds, result truncation, and contributed event ids for Investigator tools. Pure domain code over `queries/agent_tool_queries.py`. |
| OpenAI SDK adapter | `integrations/openai_agents/` (out of domain; called by injection) | none in this domain | Wraps Agent / Runner / `function_tool`, schema parsing, usage/tool-call extraction, safety net and SDK errors. It calls injected Pulse runtimes and may import provider protocols/types only, not Pulse queries or services. |
| Pulse candidate job service | `services/pulse_candidate_job_service.py` | `pulse_candidates`, `pulse_agent_runs`, `pulse_agent_run_steps`, `pulse_candidates.decision_*` columns, `pulse_candidates.decision_json` | Per-job orchestration and persistence owner. Claims admission, creates audit rows, runs the injected decision client, persists final decisions through focused repositories, and writes `research_only_gate` short-circuit rows for hard-blocked candidates. |
| Pulse worker | `runtime/pulse_candidate_worker.py` | none directly; writes only through `PulseCandidateJobService` and repository session | Scheduler / scanner / claimer. Inherits `WorkerBase`, is started by `WorkerScheduler`, listens to `token_radar_updated` for wake, and runs `interval_seconds` catch-up. It scans radar rows, claims due jobs, and delegates per-job persistence to the service. |
| Audit ledger | `repositories/pulse_runs_repository.py` | `pulse_agent_runs`, `pulse_agent_run_steps` | Every worker run writes one `pulse_agent_runs` row. Every `investigator` / `decision_maker` stage, plus `research_only_gate` short-circuits, writes one `pulse_agent_run_steps` row. `prompt_text` is operational audit data and must never contain secrets or credentials. |

### Investigator tools

The `investigator` stage runs with three fact-lookup tools so it can
reach behind the pre-computed `factor_snapshot` instead of consuming a
flattened blob:

- `get_target_recent_tweets` — recent KOL / watched-author tweet text for
  the candidate subject.
- `get_target_price_action` — latest `market_ticks` derived summary
  (price, liquidity, market cap, holders) for the resolved target.
- `get_official_token_profile` — official asset description / metadata from
  `asset_profiles`.

Tool invocations are persisted on the investigator step under
`input_json.tool_calls` (worker-side ledger; see P1-1 in the spec) and
deterministic eval R2 (`tool_calls_present`) asserts that non
hard-blocked runs always invoke at least one tool. Adding or renaming a
tool is an Update Trigger. The harness manifest's
`runtime.tool_names_by_stage` is the only tool contract: "tools enabled"
means a stage has a non-empty tool list; there is no separate boolean
flag.

## Public Decision Contract

The product-facing decision payload (full v2 shape with semantics
documented in `../../../../docs/CONTRACTS.md`):

```json
{
  "route": "meme | cex | research_only",
  "recommendation": "high_conviction | trade_candidate | watchlist | ignore | abstain",
  "confidence": 0.0,
  "abstain_reason": "string or null",
  "stage_count": 0,
  "summary_zh": "string",
  "narrative_archetype": "string (<= 20 chars)",
  "narrative_thesis_zh": "string (30-300 chars)",
  "bull_view": {
    "strength": "absent | weak | moderate | strong",
    "thesis_zh": "string",
    "supporting_event_ids": ["event-id"]
  },
  "bear_view": {
    "strength": "absent | weak | moderate | strong",
    "thesis_zh": "string",
    "supporting_event_ids": ["event-id"]
  },
  "playbook": {
    "has_playbook": true,
    "watch_signals": ["string"],
    "exit_triggers": ["string"],
    "monitoring_horizon": "1h | 4h | 24h"
  },
  "evidence_event_urls": {"event-id": "https://..."},
  "invalidation_conditions": ["string"],
  "residual_risks": ["string"],
  "evidence_event_ids": ["event-id"]
}
```

- Default Signal Pulse listings hide rows where
  `decision.recommendation = "abstain"`. Abstain is decision semantics,
  not a `pulse_status`.
- Rows with insufficient data return an abstain decision with the audit
  row written. No path may return a non-abstain decision without an audit
  row, and no path may invent a confidence or display status to avoid
  abstaining.

## Wake Channels

| Channel | Direction | Counterpart |
|---------|-----------|-------------|
| `token_radar_updated` | listen | emitted by `TokenRadarProjectionWorker` after a successful window write |

Pulse worker also runs `interval_seconds` catch-up so a missed
`NOTIFY` cannot stall agent decisions.

## Provider Boundary

- Only `integrations/openai_agents/` imports OpenAI Agents SDK primitives.
- Pulse-specific stage contracts, prompt loading, evidence validation, URL
  enrichment, harness/audit assembly, and tool query behavior live under
  `domains/pulse_lab/services/`.
- `domains/pulse_lab` may not import OpenAI primitives or any other
  concrete LLM client.
- Composition lives in `app/runtime/provider_wiring/openai.py`, which creates
  `AgentToolRuntime` / `PulseDecisionRuntimeService` and injects them into
  `OpenAIAgentsPulseDecisionClient`.

## Hard Boundaries

- No fallback to legacy Signal Pulse `thesis_json`, `radar_score_json`,
  or `market_context_json`. Public Signal Pulse payloads expose
  `factor_snapshot`, `decision`, `gate`, and `fact_card`, not old
  score/thesis JSON fields.
- No decision without an audit row.
- Route policy is deterministic and driven by `workers.yaml`; routes are
  not selected by the LLM.
- `agent_brief` is a search-side payload, not a Pulse-side payload.
- Pulse never writes `token_radar_rows`; that is
  `TokenRadarProjectionWorker`'s table.

## Update Triggers

Update this file in the same change as any of:

- Candidate gate inputs or thresholds.
- Agent route values (`cex` / `meme` / `research_only`) or the policy
  that selects them.
- Stage runtime interface (`investigator` / `decision_maker` contract).
- Decision payload schema or `recommendation` enum.
- Audit ledger column shape.
- Pulse worker wake channels or catch-up cadence.
