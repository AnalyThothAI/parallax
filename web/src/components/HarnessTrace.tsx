import type { AttentionSeedItem, HarnessCreditItem, HarnessOutcomeItem, HarnessSnapshotItem, SocialEventItem } from "../api/types";
import { formatPercentShare } from "../lib/format";

type HarnessTraceProps = {
  socialEvent?: SocialEventItem | null;
  seed?: AttentionSeedItem | null;
  snapshot?: HarnessSnapshotItem | null;
  outcome?: HarnessOutcomeItem | null;
  credits: HarnessCreditItem[];
};

export function HarnessTrace({ socialEvent, seed, snapshot, outcome, credits }: HarnessTraceProps) {
  return (
    <div className="harness-trace">
      <TraceStep index={1} title="Extracted">
        {socialEvent ? (
          <>
            <p>
              @{socialEvent.author_handle ?? "watched"} · {socialEvent.event_type}
            </p>
            <p>anchor: {socialEvent.anchor_terms.map((item) => `"${item.term}"`).join(", ") || "none"}</p>
            <p className="mono">
              impact {formatPercentShare(socialEvent.impact_hint)} · novelty {formatPercentShare(socialEvent.semantic_novelty_hint)} · conf {formatPercentShare(socialEvent.confidence)}
            </p>
          </>
        ) : (
          <p>social event not selected</p>
        )}
      </TraceStep>
      <TraceStep index={2} title="Seed">
        {seed ? (
          <>
            <p>
              {seed.seed_status} · token uptake {seed.token_uptake_count}
            </p>
            <p>{seed.top_linked_symbols.join(", ") || "no linked token yet"}</p>
          </>
        ) : (
          <p>attention seed not linked</p>
        )}
      </TraceStep>
      <TraceStep index={3} title="Snapshot">
        {snapshot ? (
          <>
            <p>
              {snapshot.asset} · {snapshot.horizon} · score {snapshot.combined_score.toFixed(2)}
            </p>
            <p>
              shadow {snapshot.shadow_signal} · policy {snapshot.policy_signal}
            </p>
          </>
        ) : (
          <p>snapshot not frozen</p>
        )}
      </TraceStep>
      <TraceStep index={4} title="Outcome">
        {outcome ? <p>normalized outcome {outcome.normalized_outcome.toFixed(2)}</p> : <p>{snapshot?.outcome_status ?? "outcome pending"}</p>}
      </TraceStep>
      <TraceStep index={5} title="Credit">
        <p>{credits.length ? `${credits.length} credit rows assigned` : "credit not assigned"}</p>
        <p className="ledger-note">Predictive credit, not causal proof.</p>
      </TraceStep>
    </div>
  );
}

function TraceStep({ children, index, title }: { children: React.ReactNode; index: number; title: string }) {
  return (
    <article className="harness-trace-step">
      <span>{index}</span>
      <div>
        <strong>{title}</strong>
        {children}
      </div>
    </article>
  );
}
