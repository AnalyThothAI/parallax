import type { HarnessHealth } from "../api/types";
import { compactNumber, formatPercentShare } from "../lib/format";

type HarnessHealthStripProps = {
  health: HarnessHealth;
};

export function HarnessHealthStrip({ health }: HarnessHealthStripProps) {
  return (
    <div className="harness-health-strip" aria-label="harness health">
      <Metric label="schema" tone={schemaTone(health.schema_success_rate)} value={formatHealthPercent(health.schema_success_rate)} />
      <Metric label="snap" value={compactNumber(health.snapshots_24h)} />
      <Metric label="pending" tone={health.pending_outcomes > 0 ? "warn" : "muted"} value={compactNumber(health.pending_outcomes)} />
      <Metric label="settled" tone="good" value={formatHealthPercent(health.settlement_coverage)} />
    </div>
  );
}

function Metric({ label, tone = "muted", value }: { label: string; tone?: "good" | "warn" | "bad" | "muted"; value: string }) {
  return (
    <div className={`harness-health-metric ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function formatHealthPercent(value?: number | null): string {
  return value === null || value === undefined ? "-" : formatPercentShare(value);
}

function schemaTone(value?: number | null): "good" | "warn" | "bad" | "muted" {
  if (value === null || value === undefined) return "muted";
  if (value >= 0.95) return "good";
  if (value >= 0.8) return "warn";
  return "bad";
}
