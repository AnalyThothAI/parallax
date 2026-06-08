# Pulse Lab Architecture

> **Scope.** Owns Signal Pulse admission, sealed evidence packets, evidence-bound
> agent synthesis, decision persistence, public display state, and replay audit.
> Global boundaries live in `../../../../docs/ARCHITECTURE.md`; public API
> contracts live in `../../../../docs/CONTRACTS.md`.

Signal Pulse is an evidence-first read-model producer. It turns Token Radar
projection rows into replayable Pulse decisions on the `1h` and `4h` horizons,
but PostgreSQL material facts remain the only business truth. The LLM never
acquires critical facts itself: the worker first builds a sealed
`PulseEvidencePacket`, then the Pulse agent workflow can only synthesize,
challenge, judge, and cite refs inside that packet. Token Radar may still
compute `5m` rows for other surfaces; Pulse Agent admission must not scan or
enqueue `5m`.

## Data Flow

```text
pulse_trigger_dirty_targets
  -> PulseCandidateWorker claim
  -> exact token_radar_current_rows + events + enriched_events + market facts + identity facts
  -> deterministic admission
  -> PulseEvidenceBuilder
  -> pulse_evidence_packets
  -> EvidenceCompletenessGate
  -> CostGuard
  -> pulse_decision LLM when public decision is allowed
  -> ClaimEvidenceVerifier
  -> RecommendationClipper
  -> deterministic eval
  -> WriteGate
  -> pulse_candidates / pulse_playbooks / public Signal Pulse read model
```

Hard-blocked packets do not call the LLM. Source-quality or eligibility ceilings
can skip the single public decision stage. Both paths still write packet, gate,
run, eval, and write-gate audit rows so operators can see why nothing was
published.

## Runtime Map

| Component | Code owner | Writes | Invariant |
|---|---|---|---|
| Candidate gate | `services/pulse_candidate_gate.py` | none | Deterministic admission from `factor_snapshot_json`; fails closed on low score, hard risks, insufficient projection quality, or insufficient independent-source quality. |
| Trigger control plane | `repositories/pulse_trigger_dirty_target_repository.py`, `runtime/pulse_candidate_worker.py` | `pulse_trigger_dirty_targets` | Token Radar producers enqueue changed target/window/scope edges. Runtime claims dirty targets before loading evidence and never scans current Radar rows on an empty queue. |
| Evidence source repository | `repositories/pulse_evidence_source_repository.py` | none | Reads events, enriched events, market ticks/price observations, and identity/profile facts. Provider raw frames are not facts. |
| Evidence packet builder | `services/evidence_packet_builder.py` | `pulse_evidence_packets` through repository | Constructs a sealed packet with stable `allowed_evidence_refs`, source fingerprints, quality metrics, and data gaps before any LLM call. |
| Evidence completeness gate | `services/evidence_completeness_gate.py` | run-step audit only | Decides whether packet evidence is complete, partial, stale, or insufficient; sets max decision status and public display ceiling. |
| Decision runtime | `services/pulse_decision_runtime.py` | none | Builds the packet-only decision payload, loads the prompt, validates final refs, and prepares final decisions. No provider SDK import. |
| Model execution adapter | `integrations/model_execution/pulse_decision_agent_client.py` | none directly | Runs one tool-free `pulse_decision` stage when the cost guard permits public judging. Tools are not registered for Pulse. |
| Job service | `services/pulse_candidate_job_service.py` | runs, steps, packets, candidates, eval, playbooks | Owns per-job orchestration and persistence; writes hidden audit rows for invalid/abstain/hold-publish outputs. |
| Public read model | `read_models/signal_pulse_service.py` and `repositories/pulse_read_repository.py` | none | Lists only public `display_*` rows with `evidence_packet_hash`; hidden states remain operator/audit data. Public list/detail payloads expose decision, factor, gate, fact, and version fields only; `agent_run_id` and run-step `stages` stay in the audit ledger. |

## Stage Contract

`pulse_agent_run_steps.stage` is evidence-first only:

- `evidence_pack`
- `evidence_completeness_gate`
- `pulse_decision`
- `claim_verifier`
- `recommendation_clipper`
- `deterministic_eval`
- `write_gate`

There is no public legacy stage alias runtime. Older exploratory role names are
not stage names. `research_only` can still be a route value, but cost execution
uses the single decision stage only when public judging is allowed; hard blocking
is represented by `evidence_completeness_gate` plus hidden display state, not by
a separate compatibility stage.

## Public Decision Contract

Final decisions retain narrative and playbook fields, and add hard evidence refs:

```json
{
  "route": "meme | cex | research_only",
  "recommendation": "high_conviction | trade_candidate | watchlist | ignore | abstain",
  "confidence": 0.0,
  "abstain_reason": "string or null",
  "summary_zh": "string",
  "narrative_archetype": "string",
  "narrative_thesis_zh": "string",
  "bull_view": {"strength": "absent | weak | moderate | strong"},
  "bear_view": {"strength": "absent | weak | moderate | strong"},
  "playbook": {"has_playbook": true},
  "evidence_event_ids": ["event-id"],
  "supporting_evidence_refs": ["event:event-id"],
  "risk_evidence_refs": ["market:..."],
  "data_gap_refs": ["gate:pulse:..."],
  "invalidation_conditions": ["string"],
  "residual_risks": ["string"]
}
```

Non-abstain decisions must cite `supporting_evidence_refs`. Legacy
`evidence_event_ids` cannot substitute for packet refs.

## Display State

`pulse_status` remains admission/gate state. Public visibility is controlled by:

- `evidence_status`: `complete | partial | insufficient | stale | invalid`
- `decision_status`: `trade_candidate | token_watch | risk_rejected_high_info | abstain | invalid`
- `display_status`: `display_*` or `hidden_*`

Signal Pulse listings only expose `display_trade_candidate`,
`display_token_watch`, and `display_risk_rejected_high_info` rows with a packet
hash. `hidden_source_quality` rows are retained for debugging, eval, and replay
when matched or watched context exists but independent public-source quality is
not good enough for default discovery.

## Provider Boundary

- Only `integrations/model_execution/` imports LiteLLM primitives.
- Pulse domain services own prompt loading, packet validation, evidence
  verification, runtime manifests, and deterministic eval.
- `app/runtime/provider_wiring/model_execution.py` composes `PulseDecisionRuntimeService`
  with `LiteLLMPulseDecisionClient`; it does not register Pulse tools.

## Hard Boundaries

- No LLM fact acquisition for critical Pulse facts.
- No fallback to legacy thesis, radar-score, or market-context JSON payloads.
- No public row without `evidence_packet_hash`.
- No public Signal Pulse list/detail payload with `agent_run_id` or run-step `stages`.
- No non-abstain decision without `supporting_evidence_refs`.
- No decision without an audit row.
- Pulse never writes Token Radar current/history/audit read models.

## Update Triggers

Update this file with any change to packet schema, evidence refs, stage names,
display states, recommendation enum, worker wake channels, or public Signal
Pulse contract.
