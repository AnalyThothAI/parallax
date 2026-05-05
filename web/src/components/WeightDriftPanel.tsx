import type { HarnessWeightItem } from "../api/types";

type WeightDriftPanelProps = {
  items: HarnessWeightItem[];
};

export function WeightDriftPanel({ items }: WeightDriftPanelProps) {
  return (
    <section className="weight-drift-panel ledger-box">
      <h3>Weight Drift</h3>
      <p className="ledger-note">MVP weights are report-only until config promotion exists.</p>
      <div className="weight-drift-list">
        {items.map((item) => (
          <article className="weight-drift-row" key={`${item.weight_type}:${item.key}:${item.horizon}`}>
            <strong>{item.key}</strong>
            <span>
              {item.weight_type} · {item.horizon}
            </span>
            <b>{item.n}</b>
            <b>{item.mean_credit.toFixed(3)}</b>
            <b>{item.weight.toFixed(2)}</b>
            <em>{item.status}</em>
          </article>
        ))}
      </div>
      {items.length === 0 ? <div className="empty-state">weight drift read model not available</div> : null}
    </section>
  );
}
