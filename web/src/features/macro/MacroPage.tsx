import type { MacroIndicator, MacroPanel, MacroTrigger } from "@lib/types";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { Activity, AlertTriangle, CircleDot, Gauge } from "lucide-react";

import { useMacroQuery } from "./api/useMacroQuery";
import "./macro.css";

const PANEL_ORDER = ["liquidity", "rates", "volatility", "credit", "cross_asset"];

export function MacroPage({ token }: { token: string }) {
  const query = useMacroQuery({ token });
  const data = query.data;
  const snapshot = data?.snapshot ?? null;
  const panels = data?.panels ?? {};
  const panelEntries = orderedPanels(panels);
  const indicators = Object.entries(data?.indicators ?? {});
  const triggers = data?.triggers ?? [];
  const gaps = data?.data_gaps ?? [];

  return (
    <section className="macro-page-panel" aria-label="Macro">
      <header className="macro-page-toolbar">
        <div>
          <h2>Macro</h2>
          <span>
            REGIME <b>{snapshot?.regime ?? "pending"}</b>
          </span>
        </div>
        <div className="macro-regime-strip" aria-label="macro regime status">
          <MetricPill label="status" value={snapshot?.status ?? "missing"} />
          <MetricPill label="score" value={scoreLabel(snapshot?.overall_score)} />
          <MetricPill label="asof" value={snapshot?.asof_date ?? "-"} />
        </div>
      </header>

      {query.isLoading ? <RemoteState.Loading layout="route" label="loading macro" /> : null}
      {query.isError ? <RemoteState.Error error={query.error} /> : null}
      {!query.isLoading && !query.isError && !snapshot ? (
        <div className="macro-empty-state">
          <AlertTriangle aria-hidden />
          <b>Macro pending</b>
          <span>{gaps[0] ?? "macro_view_snapshot_missing"}</span>
        </div>
      ) : null}

      {snapshot ? (
        <div className="macro-page-grid">
          <section className="macro-scoreboard" aria-label="macro transmission chain">
            {panelEntries.map(([key, panel]) => (
              <MacroPanelCell key={key} panelKey={key} panel={panel} />
            ))}
          </section>

          <section className="macro-indicators" aria-label="macro validation indicators">
            <div className="macro-section-head">
              <Gauge aria-hidden />
              <h3>Validation Indicators</h3>
            </div>
            <div className="macro-indicator-table">
              {indicators.map(([key, indicator]) => (
                <IndicatorRow indicator={indicator} indicatorKey={key} key={key} />
              ))}
              {indicators.length === 0 ? <span className="macro-muted">no indicators</span> : null}
            </div>
          </section>

          <section className="macro-trigger-lane" aria-label="macro triggers and gaps">
            <div className="macro-trigger-column">
              <div className="macro-section-head">
                <Activity aria-hidden />
                <h3>Triggers</h3>
              </div>
              <TriggerList triggers={triggers} />
            </div>
            <div className="macro-trigger-column">
              <div className="macro-section-head">
                <CircleDot aria-hidden />
                <h3>Data Gaps</h3>
              </div>
              <GapList gaps={gaps} />
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <span>
      {label} <b>{value}</b>
    </span>
  );
}

function MacroPanelCell({ panelKey, panel }: { panelKey: string; panel: MacroPanel }) {
  return (
    <article className={clsx("macro-panel-cell", regimeTone(panel.regime))}>
      <div>
        <span>{panelTitle(panelKey)}</span>
        <b>{scoreLabel(panel.score)}</b>
      </div>
      <strong>{panel.regime}</strong>
      <small>{panel.evidence[0] ?? panel.data_gaps[0] ?? "awaiting confirmation"}</small>
    </article>
  );
}

function IndicatorRow({
  indicatorKey,
  indicator,
}: {
  indicatorKey: string;
  indicator: MacroIndicator;
}) {
  return (
    <article className="macro-indicator-row">
      <span>
        <b>{indicator.label || indicatorKey}</b>
        <small>{indicator.series_keys?.join(" / ") || indicatorKey}</small>
      </span>
      <strong>
        {valueLabel(indicator.value)}
        {indicator.unit ? <em>{indicator.unit}</em> : null}
      </strong>
      <small>{indicator.observed_at ?? "-"}</small>
    </article>
  );
}

function TriggerList({ triggers }: { triggers: MacroTrigger[] }) {
  if (triggers.length === 0) {
    return <span className="macro-muted">no active triggers</span>;
  }
  return (
    <div className="macro-chip-list">
      {triggers.map((trigger) => (
        <span key={trigger.code} className="macro-chip hot">
          <b>{trigger.code}</b>
          {trigger.description ? <small>{trigger.description}</small> : null}
        </span>
      ))}
    </div>
  );
}

function GapList({ gaps }: { gaps: string[] }) {
  if (gaps.length === 0) {
    return <span className="macro-muted">coverage complete</span>;
  }
  return (
    <div className="macro-chip-list">
      {gaps.map((gap) => (
        <span key={gap} className="macro-chip gap">
          {gap}
        </span>
      ))}
    </div>
  );
}

function orderedPanels(panels: Record<string, MacroPanel>): Array<[string, MacroPanel]> {
  const ordered: Array<[string, MacroPanel]> = [];
  for (const key of PANEL_ORDER) {
    if (panels[key]) {
      ordered.push([key, panels[key]]);
    }
  }
  const remaining = Object.entries(panels).filter(([key]) => !PANEL_ORDER.includes(key));
  return [...ordered, ...remaining];
}

function panelTitle(key: string): string {
  const titles: Record<string, string> = {
    liquidity: "Liquidity",
    rates: "Rates",
    volatility: "Volatility",
    credit: "Credit",
    cross_asset: "Cross-Asset",
  };
  return titles[key] ?? key;
}

function scoreLabel(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return value.toFixed(2).replace(/\.?0+$/, "");
  }
  return String(value);
}

function valueLabel(value: number | string | null | undefined): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function regimeTone(regime: string): string {
  if (regime.includes("stress") || regime.includes("pressure")) return "stress";
  if (regime.includes("risk_on") || regime.includes("carry")) return "constructive";
  if (regime.includes("gap") || regime.includes("pending")) return "gap";
  return "neutral";
}
