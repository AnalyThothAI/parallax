import { compactNumber } from "../lib/format";

type SettlementCoveragePanelProps = {
  settled: number;
  pending: number;
  missing_market: number;
  insufficient: number;
};

export function SettlementCoveragePanel({ settled, pending, missing_market, insufficient }: SettlementCoveragePanelProps) {
  return (
    <section className="settlement-coverage-panel ledger-box">
      <h3>Settlement Coverage</h3>
      <div className="settlement-grid">
        <CoverageCell label="settled" value={settled} tone="good" />
        <CoverageCell label="pending" value={pending} tone="warn" />
        <CoverageCell label="missing_market" value={missing_market} tone="bad" />
        <CoverageCell label="insufficient" value={insufficient} tone="muted" />
      </div>
    </section>
  );
}

function CoverageCell({ label, tone, value }: { label: string; tone: "good" | "warn" | "bad" | "muted"; value: number }) {
  return (
    <div className={`coverage-cell ${tone}`}>
      <span>{label}</span>
      <b>{compactNumber(value)}</b>
    </div>
  );
}
