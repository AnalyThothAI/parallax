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
`EvidenceCompletenessGate` consumes the formal `PulseEvidencePacket` model
directly. Dict, `SimpleNamespace`, arbitrary `model_dump`, `__dict__`, or
`vars()` compatibility inputs are outside the runtime contract because they
would turn malformed evidence wiring into ordinary insufficient-evidence
decisions.
`ClaimEvidenceVerifier` consumes the same formal packet plus the strict
`FinalDecision` model. Dict/object decision shims are outside the agent-output
contract because unknown-ref and unsupported-claim outcomes must be judged from
validated fields, not from whatever attributes a test object happens to expose.
`PulseDecisionRuntimeService.pulse_decision_stage_spec(...)` also consumes the
formal packet and `EvidenceCompletenessGateResult` directly. Integration
adapters may carry JSON context, but they must re-validate it into the formal
packet/gate contracts before entering the domain runtime stage builder.
Pulse stage-output normalization consumes that same formal sealed packet before
`FinalDecision` validation. Dict packet compatibility and dict/object evidence
refs are outside the adapter contract.
Deterministic eval cases are JSON audit records, but the embedded
`evidence_packet` must still validate as `PulseEvidencePacket` before allowed
refs are graded. Minimal hash/ref dict packets are malformed eval artefacts.
Request-audit input hashes and trace packet/gate metadata also come from a
validated `context["evidence_packet"]` and formal
`EvidenceCompletenessGateResult`. Top-level packet-hash fallback and raw gate
dict payloads are outside the runtime contract.
The same audit boundary requires a non-empty `runtime_manifest["runtime_version"]`;
missing runtime version is malformed replay metadata, not an empty default.
Request-audit also requires non-empty agent run identity fields: run id, job id,
model, artifact hash, workflow name, and agent name. Empty identity strings are
malformed execution lineage, not harmless placeholders.
The runtime manifest model/artifact fields must match that request-audit model
and artifact hash; otherwise runtime hash lineage and run audit lineage would
describe different executable artifacts.
The job service validates claimed-row `job_id`, `trigger_signature`,
`timeline_signature`, and positive `attempt_count` before deriving `run_id` or
opening repository sessions. Empty claimed identity segments are malformed queue
state, not compatibility placeholders.
Claimed `pulse_agent_jobs.context_json` is also a formal worker-generated
payload. Rebuilding `PulseCandidateContext` requires non-empty string identity
fields, mapping-shaped gate/edge state, and JSON-list-shaped posts, clusters,
edge events, source event ids, and evidence event ids. Malformed context fields
fail the job as missing context before evidence-packet construction; the worker
must not repair them with string coercion, empty mappings, empty lists, or
filtered event refs.
The job service persists the agent-run ledger from the validated request-audit
payload directly. Missing or mismatched backend, workflow, agent, artifact,
prompt/schema, input hash, trace metadata, runtime version, or runtime hash is
a contract failure, not a value to be restored from local constants.
Stage audit construction consumes formal `AgentExecutionResult` and
`AgentExecutionRequestAudit` / `AgentExecutionResultAudit` objects only. Loose
gateway namespaces or reflective audit fields are execution-plane contract
failures, not Pulse abstain cases.
The model-execution adapter validates request-audit trace `run_id` and stage
packet group identity before building `AgentStageSpec`. Missing trace metadata
or missing packet group identity is malformed runtime output, not an empty or
pipeline-run fallback.
Workflow identity is validated at adapter construction: omitted input uses the
canonical Pulse workflow constant, while blank or `None` workflow input is
malformed wiring rather than a defaultable value.
No-start provider backpressure is classified only from formal
`AgentExecutionError.error_class` with `execution_started=False`; loose audit
dicts or alias exception fields are ordinary failures, not cooldown release
signals.
Worker hard-timeout cleanup reads execution-started state only from formal
`AgentExecutionCancelled`; otherwise it uses the job service's `run_started`
state. Loose cancellation audit dicts cannot classify before/after-execution
timeout cleanup.

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

`PulseCandidateJobService` writes agent run/step/eval/candidate/playbook/admission
and job terminal rows inside `RepositorySession.transaction`; missing session
transaction support is a worker/session contract failure and must not fall back
to `nullcontext` or raw `conn.transaction()`.
It requires the claimed `pulse_agent_jobs.attempt_count` before constructing the
agent run id or request audit, so malformed claims fail before the pipeline
enters repository state.
`PulseJobsRepository` terminal/dead job paths write `pulse_agent_jobs` state and
`worker_queue_terminal_events` evidence inside a callable connection
transaction; missing transaction support fails before job or ledger SQL and must
not fall back to `nullcontext` or manual commit compatibility. Batch terminal
paths that use `UPDATE ... RETURNING` validate PostgreSQL `cursor.rowcount`
before writing terminal ledger rows, and rowcount must match the returned rows;
missing, invalid, or mismatched rowcount is malformed driver state.
`PulseJobsRepository` job enqueue, success marking, running-job release, and
stale agent-run failure cleanup use the same connection transaction when the
repository owns the commit. Missing transaction support fails before job/run SQL;
runtime code must not fall back to manual `self.conn.commit()` compatibility.
Single-row `pulse_agent_jobs` `RETURNING` mutations are also execution evidence,
not returned-row hints: required enqueue writes must be rowcount=1 with a row,
while claim, success, retry, failure, timeout, and release paths accept only
rowcount=0 with no row or rowcount=1 with one row before job state, retry
classification, or terminal ledger effects are reported.
`PulseJobsRepository.enqueue_job(...)` also requires an explicit `max_attempts`
argument from the caller. The worker is the policy owner through
`settings.workers.pulse_candidate.max_attempts`; the repository must not synthesize
that retry budget with a local default.
Running-job release, timeout cancellation, provider cooldown, and failure
retry/dead classification require the claimed `attempt_count`; failure
classification also requires `max_attempts`. Missing or non-positive values are
malformed job claims, not repository-local defaults.
Stale running-job timeout is owned by
`settings.workers.pulse_candidate.job_running_timeout_ms`. The DB/repository
session composition root passes that value into `PulseJobsRepository`
explicitly, and no Pulse repository owns a local running-timeout default.
Stale `pulse_agent_runs` timeout cleanup returns changed-run counts only from
PostgreSQL `cursor.rowcount`; missing or invalid rowcount is malformed
repository/driver state, not zero stale agent runs.
Stale exhausted running-job terminalization width is also formal worker policy:
`PulseCandidateWorker` passes
`settings.workers.pulse_candidate.stale_running_terminalization_batch_size`
into `PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)`, and
the repository must not keep a local `limit` default.
Pulse agent write repositories (`PulseRunsRepository`, `PulseAgentEvalRepository`,
`PulseEvidenceRepository`, `PulseCandidatesRepository`,
`PulsePlaybooksRepository`, and ordinary `PulseAdmissionRepository` mutation
methods) use the shared Pulse connection transaction when the repository owns
`commit=True`; `commit=False` is reserved for the outer
`RepositorySession.transaction`. Missing transaction support fails before agent
run, step, eval, packet, candidate, playbook, edge, or budget SQL; runtime code
must not fall back to manual `self.conn.commit()` compatibility.
`PulseRunsRepository` agent run and run-step audit writes require PostgreSQL
`cursor.rowcount` evidence before returning run or step rows. Required insert
paths accept only rowcount=1 with a returned row, while `finish_agent_run(...)`
validates rowcount against returned-row presence after the run existence check.
Missing, invalid, or mismatched rowcount is malformed driver state.
`PulseAgentEvalRepository` runtime-version, eval-case, and eval-result audit
`RETURNING` writes are also required single-row writes: rowcount must be 1 and a
row must be returned before eval audit rows are exposed.
`PulseCandidatesRepository` public candidate upsert and low-information hide
`RETURNING` writes require PostgreSQL `cursor.rowcount` evidence. Unchanged
candidate projections and no-op hide attempts are valid only as rowcount=0 with
no returned row; changed candidate writes require rowcount=1 with a returned row,
and the repository must not use fallback `SELECT` to turn existing public rows
into apparent writes.
`PulseAdmissionRepository` single-row `RETURNING` writes for edge observation,
job-enqueued state, budget rejection, run-finished state, suppression/admission
state, and candidate edge-budget claims also require PostgreSQL `cursor.rowcount`
evidence. Rowcount must be valid 0/1 and match returned-row presence before edge
rows, optional state rows, or budget booleans are returned; missing, invalid, or
mismatched rowcount is malformed driver state, not a returned-row success signal.
`PulsePlaybooksRepository` applies the same rule to playbook snapshot/outcome
`RETURNING` writes. Snapshot updates accept the no-change case only as
rowcount=0 with no returned row; changed snapshot and outcome writes require
rowcount=1 with a returned row, and the repository must not use fallback `SELECT`
to turn unchanged projections into apparent writes.
`PulseTriggerDirtyTargetRepository` queue mutations enqueue changed targets,
claim due targets, delete completed claims, retry errored claims, and reschedule
claims inside the shared Pulse connection transaction when the repository owns
`commit=True`; missing transaction support fails before dirty-target SQL and
must not fall back to manual `self.conn.commit()` compatibility.
Dirty-trigger enqueue requires a positive producer-supplied
`source_watermark_ms`; missing, zero, negative, boolean, or string watermarks
fail before queue SQL, and enqueue SQL does not carry a zero-watermark
compatibility branch.
`PulseAdmissionRepository.claim_pulse_admission(...)` writes edge observation,
suppression/admission state, and target/candidate run-budget rows inside a
callable connection transaction; missing transaction support fails before edge or
budget SQL and must not fall back to `nullcontext` compatibility.

`PulseCandidateWorker` claims trigger dirty targets, writes admission/edge/public
visibility/job enqueue state, and marks dirty targets done/error inside
`RepositorySession.transaction`; missing session transaction support is a
worker/session contract failure before claim/write and must not fall back to raw
`conn.transaction()`.
Claimed dirty-target `window` and `scope` must be members of the formal
`workers.pulse_candidate` settings before any exact Token Radar or timeline
payload read. Malformed dimensions fail the dirty trigger for retry instead of
being interpreted as all-public source reads.
Admission policy reads failed existing job retry state from formal
`pulse_agent_jobs.attempt_count` / `max_attempts` fields. Malformed failed job
rows fail the dirty trigger for retry instead of being interpreted through
policy-local attempt defaults.

`PulseCandidateWorker` and `PulseCandidateJobService` use the formal
`workers.pulse_candidate` settings object for candidate windows/scopes, claim
and enqueue limits, dirty-trigger lease/retry intervals, target/candidate edge
budgets, failure-circuit threshold/reasons, timeline-debounce policy, agent job
budgets, stale running-job timeout and terminalization batch size, evidence market-freshness window,
timeline context window/scope, trigger/gate thresholds, and worker-session statement timeout. Missing
settings, DB bundle, or decision client support is a runtime wiring failure;
the Pulse runtime must not keep local product-default windows,
trigger/admission magic constants, policy-service defaults,
timeline-context `1h`/`all` fallbacks, builder/repository-local freshness
defaults, repository-local timeout defaults, or statement-timeout compatibility
paths.

## Runtime Map

| Component | Code owner | Writes | Invariant |
|---|---|---|---|
| Candidate gate | `services/pulse_candidate_gate.py` | none | Deterministic admission from `factor_snapshot_json`; fails closed on low score, hard risks, insufficient projection quality, or insufficient independent-source quality. |
| Trigger control plane | `repositories/pulse_trigger_dirty_target_repository.py`, `runtime/pulse_candidate_worker.py` | `pulse_trigger_dirty_targets` | Token Radar producers enqueue changed target/window/scope edges with positive `source_watermark_ms`; missing or invalid watermarks fail before queue SQL and are never repaired to zero. Runtime claims dirty targets before loading evidence and never scans current Radar rows on an empty queue. Claim `UPDATE ... RETURNING` rowcount must match returned claimed rows before evidence loading. Claimed window/scope values must match formal worker settings before payload reads; malformed dimensions fail through dirty-trigger retry instead of widening to all-public timeline reads. Done/error/reschedule completion keys require the positive `attempt_count`, non-empty `lease_owner`, and `payload_hash` returned by `claim_due`; exit-suppression `trigger_signature` also uses the claimed payload hash. Malformed keys fail before SQL or admission writes instead of being restored to zero attempts, empty owners, or empty payload hashes. Done/error/reschedule changed-row counts require PostgreSQL `cursor.rowcount`; missing or invalid rowcount is malformed driver state, not zero dirty-trigger work. |
| Evidence source repository | `repositories/pulse_evidence_source_repository.py` | none | Reads events, enriched events, market ticks/price observations, and identity/profile facts from the formal `PulseCandidateContext`. Market-fact freshness requires explicit `max_age_ms` and job-run `now_ms` from the caller; the repository owns no default clock or freshness policy. Provider raw frames and dict-like context shims are not facts. |
| Evidence packet builder | `services/evidence_packet_builder.py` | `pulse_evidence_packets` through repository | Constructs a sealed packet with stable `allowed_evidence_refs`, source fingerprints, quality metrics, and data gaps before any LLM call. It calls formal evidence source methods for source events, enriched events, market facts, identity facts, and current discussion digest directly, and reads `PulseCandidateContext` fields directly; the market-fact freshness window is injected from formal `workers.pulse_candidate` settings. Missing methods, malformed context, or missing freshness policy are wiring failures, not empty evidence. Persisting the packet is a required single-row `RETURNING` write: the repository validates PostgreSQL `cursor.rowcount=1` with a returned packet row, then validates the separate `pulse_agent_runs` run-link `UPDATE` also affected exactly one row before packet persistence is reported. |
| Evidence completeness gate | `services/evidence_completeness_gate.py` | run-step audit only | Decides whether packet evidence is complete, partial, stale, or insufficient; sets max decision status and public display ceiling. |
| Decision runtime | `services/pulse_decision_runtime.py` | none | Builds packet-only request audit and prompt payloads, loads the prompt, normalizes stage output against the formal sealed packet, validates final refs, and prepares final decisions. No provider SDK import. |
| Model execution adapter | `integrations/model_execution/pulse_decision_agent_client.py` | none directly | Runs one tool-free `pulse_decision` stage when the cost guard permits public judging. Tools are not registered for Pulse. The client does not expose provider timeout policy; `LiteLLMPulseDecisionProvider` maps the formal `pulse.decision` lane timeout into the runtime manifest. Workflow identity is validated at construction. `AgentStageSpec` requires validated request-audit trace run identity and stage packet group identity; stage audit rows are built only from formal agent-execution result/audit models. |
| Job service | `services/pulse_candidate_job_service.py` | runs, steps, packets, candidates, eval, playbooks, admission/job terminal state | Owns per-job orchestration and persistence; writes hidden audit rows for invalid/abstain/hold-publish outputs inside `RepositorySession.transaction`. Claimed job run identity is validated before repository sessions or `run_id` derivation. Agent-run identity and prompt/schema metadata are copied from the validated request-audit payload, never recomputed through compatibility defaults. |
| Public read model | `read_models/signal_pulse_service.py` and `repositories/pulse_read_repository.py` | none | Lists only public `display_*` rows with `evidence_packet_hash`; hidden states remain operator/audit data. Public list/detail payloads expose decision, factor, gate, fact, and version fields only; `agent_run_id` and run-step `stages` stay in the audit ledger. Present `pulse_candidates` rows must expose formal public JSON fields: `decision_json` is mapping-shaped, and gate/risk/evidence/source id JSON fields are list-shaped. Malformed present rows fail instead of being repaired into empty decision text or empty public arrays. Public list width is a caller/API contract: `SignalPulseService` passes an explicit `limit` into `PulseReadRepository.list_candidates(...)`, and the repository owns no `limit=50` default. Notification candidate discovery is a separate worker-read contract: `PulseReadRepository.list_signal_pulse_notification_candidates(...)` takes configured scopes/statuses as PostgreSQL keysets and applies `ROW_NUMBER() OVER (PARTITION BY scope,status ...)` to bound each bucket in one SQL. The notification rule engine must not loop through public `list_candidates(...)` cursor pages to find Signal Pulse candidates. Freshness health is read through the formal `PulseReadRepository.freshness_health(...)` contract; the service must not inspect private repository connections or treat missing support as empty health. |

Public `q` search strips whitespace and treats a blank value as no search filter.
When non-empty `q` search uses substring matching over `pulse_candidates.symbol`,
`pulse_candidates.subject_key`, `pulse_candidates.target_id`,
`pulse_agent_jobs.subject_key`, or `pulse_agent_jobs.target_id`, PostgreSQL
trigram GIN indexes must support that contract; public reads must not reintroduce
`ILIKE '%%'` scans or JSONB event-array expansion as a search substrate.

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
The `recommendation_clipper` and `write_gate` stages consume the formal
`PulseGateResult`, `EvidenceCompletenessGateResult`,
`ClaimEvidenceVerificationResult`, and `PulseSourceQualityDecision` contracts
directly. Duck-typed gate objects must fail before recommendation clipping or
public/playbook write decisions.
The `deterministic_eval` stage reads stored eval-case JSON only as an audit
container; evidence refs are checked after re-validating the embedded packet
JSON into `PulseEvidencePacket`.
Run outcome classification also consumes the formal
`ClaimEvidenceVerificationResult`; unknown-ref outcomes come from verifier
fields, not a bool plus optional object fallback.

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
When a previously public row falls below the low-information gate, the worker
must update that row through
`PulseCandidatesRepository.hide_public_candidate_for_low_information`. Missing
hide support is a dirty-trigger failure and retry, not a no-op that leaves a
stale public row visible.

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
- Recommendation clipping preserves the validated playbook monitoring horizon;
  missing `playbook.monitoring_horizon` is malformed decision output, not a
  local `1h` fallback.
- Dirty-trigger admission reads `pulse_agent_jobs`,
  `pulse_candidate_edge_state`, recent-failure counts, pending job counts, and
  trigger queue depth through their PostgreSQL repositories directly. Missing
  repository support is a dirty-trigger failure/retry, not empty job, edge,
  capacity, or queue state.
- Dirty-trigger claim, admission write, public visibility transition, job
  enqueue, and dirty-target terminal updates use `RepositorySession.transaction`
  directly. Missing session transaction support fails before claim/write.
- Pulse never writes Token Radar current/history/audit read models.

## Update Triggers

Update this file with any change to packet schema, evidence refs, stage names,
display states, recommendation enum, worker wake channels, or public Signal
Pulse contract.
