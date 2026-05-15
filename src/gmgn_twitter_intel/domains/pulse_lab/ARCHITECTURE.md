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

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Candidate gate | `services/pulse_candidate_gate.py` | none (in-memory admission) | Reads `factor_snapshot_json.market.decision_latest`, `normalization.cohort_status`, and gate fields. Fails closed when target rows lack material `decision_latest` or have an insufficient/all-tied cohort. |
| Agent route policy | `services/agent_routing.py` | none (in-memory decision) | Deterministic route assignment to `cex`, `meme`, or `research_only`. Completeness gates are driven by the `pulse_candidate` worker settings in `workers.yaml`. |
| Stage runtime | `integrations/openai_agents/` (out of domain; called by injection) | none in this domain | Runs Analyst / Critic / Judge stages with typed outputs and returns domain values. Does not own routing, persistence, product thresholds, or SQL. |
| Pulse worker | `runtime/pulse_candidate_worker.py` | `pulse_candidates`, `pulse_agent_runs`, `pulse_agent_run_steps`, `pulse_candidates.decision_*` columns, `pulse_candidates.decision_json` | The only runtime writer of these tables. Inherits `WorkerBase`, is started by `WorkerScheduler`, listens to `token_radar_updated` for wake, and runs `interval_seconds` catch-up. |
| Audit ledger | `repositories/pulse_repository.py` | `pulse_agent_runs`, `pulse_agent_run_steps` | Every worker run writes one `pulse_agent_runs` row. Every Analyst / Critic / Judge stage, plus research-only short-circuits, writes one `pulse_agent_run_steps` row. `prompt_text` is operational audit data and must never contain secrets or credentials. |

## Public Decision Contract

The product-facing decision payload (also documented in
`../../../../docs/CONTRACTS.md`):

```json
{
  "route": "meme | cex | research_only",
  "recommendation": "trade_candidate | token_watch | high_info_rejection | high_conviction | abstain",
  "confidence": 0.0,
  "abstain_reason": "string or null",
  "stage_count": 0,
  "summary_zh": "string",
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

- Only `integrations/openai_agents/` runs OpenAI Agents stages.
- `domains/pulse_lab` may not import OpenAI primitives or any other
  concrete LLM client.
- Composition lives in `app/runtime/providers_wiring.py`, which binds a
  concrete adapter to the `pulse_lab` provider protocol.

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
- Stage runtime interface (Analyst / Critic / Judge contract).
- Decision payload schema or `recommendation` enum.
- Audit ledger column shape.
- Pulse worker wake channels or catch-up cadence.
