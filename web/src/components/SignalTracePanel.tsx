import type { SignalLabChain } from "../api/types";
import { formatPercentShare, formatRelativeTime } from "../lib/format";
import { signalLabLabel } from "../lib/signalLab";

type SignalTracePanelProps = {
  chain: SignalLabChain;
};

export function SignalTracePanel({ chain }: SignalTracePanelProps) {
  return (
    <div className="signal-trace">
      <TraceStep index={1} title="Extracted" complete={Boolean(chain.social_event)}>
        {chain.social_event ? (
          <>
            <Field label="extraction" value={chain.social_event.extraction_id} />
            <Field label="event" value={chain.social_event.event_id} />
            <p>
              @{chain.social_event.author_handle ?? "unknown"} · {chain.social_event.event_type}
            </p>
            <p>{chain.social_event.subject}</p>
            <p>
              {chain.social_event.source_action} · {chain.social_event.attention_mechanism} · {chain.social_event.direction_hint}
            </p>
            <p className="mono">
              impact {formatPercentShare(chain.social_event.impact_hint)} · novelty {formatPercentShare(chain.social_event.semantic_novelty_hint)} · conf {formatPercentShare(chain.social_event.confidence)}
            </p>
            <p>anchors: {chain.social_event.anchor_terms.slice(0, 3).map((item) => item.term).join(", ") || "none"}</p>
            <p>candidates: {chain.social_event.token_candidates.slice(0, 3).map((item) => item.symbol ?? item.address ?? item.project_name ?? "-").join(", ") || "none"}</p>
          </>
        ) : (
          <p>not extracted</p>
        )}
      </TraceStep>
      <TraceStep index={2} title="Seed" complete={Boolean(chain.seed)}>
        {chain.seed ? (
          <>
            <Field label="seed" value={chain.seed.seed_id} />
            <Field label="event" value={chain.seed.event_id} />
            <p>
              {chain.seed.seed_status} · token uptake {chain.seed.token_uptake_count}
            </p>
            <p>{chain.seed.top_linked_symbols.join(", ") || "asset unresolved"}</p>
          </>
        ) : (
          <p>not seeded</p>
        )}
      </TraceStep>
      <TraceStep index={3} title="Snapshot" complete={Boolean(chain.snapshot)}>
        {chain.snapshot ? (
          <>
            <Field label="snapshot" value={chain.snapshot.snapshot_id} />
            <Field label="source" value={chain.snapshot.source_event_id} />
            <p>
              {chain.snapshot.asset} · {chain.snapshot.horizon} · score {chain.snapshot.combined_score.toFixed(2)}
            </p>
            <p>
              shadow {chain.snapshot.shadow_signal} · policy {chain.snapshot.policy_signal}
            </p>
            <p>{formatRelativeTime(chain.snapshot.decision_time_ms)} ago</p>
          </>
        ) : (
          <p>No snapshot for this chain and horizon.</p>
        )}
      </TraceStep>
      <TraceStep index={4} title="Outcome" complete={Boolean(chain.outcome)}>
        {chain.outcome ? (
          <>
            <p>normalized outcome {chain.outcome.normalized_outcome.toFixed(2)}</p>
            <p>abnormal return {formatPercentShare(chain.outcome.abnormal_return)}</p>
          </>
        ) : (
          <p>{chain.outcome_status === "pending" || !chain.outcome_status ? "Outcome pending. Settlement waits for decision_time + horizon." : chain.outcome_status}</p>
        )}
      </TraceStep>
      <TraceStep index={5} title="Credit" complete={chain.credits.length > 0}>
        <p>{chain.credits.length ? `${chain.credits.length} credit rows assigned` : "Credit not assigned."}</p>
        <p className="ledger-note">Predictive credit, not causal proof.</p>
      </TraceStep>
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  return (
    <p className="signal-trace-field">
      <span>{label}</span>
      <b>{signalLabLabel(value)}</b>
    </p>
  );
}

function TraceStep({ children, complete, index, title }: { children: React.ReactNode; complete: boolean; index: number; title: string }) {
  return (
    <article className={`signal-trace-step ${complete ? "complete" : ""}`}>
      <span>{index}</span>
      <div>
        <strong>{title}</strong>
        {children}
      </div>
    </article>
  );
}
