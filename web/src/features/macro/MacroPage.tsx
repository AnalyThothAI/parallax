import type {
  MacroChainNode,
  MacroIndicator,
  MacroPanel,
  MacroScenario,
  MacroScorecard,
  MacroTrigger,
} from "@lib/types";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import {
  Activity,
  AlertTriangle,
  CircleDot,
  Gauge,
  GitBranch,
  Map,
  Route,
  ShieldCheck,
} from "lucide-react";

import { useMacroQuery } from "./api/useMacroQuery";
import "./macro.css";

const PANEL_ORDER = ["liquidity", "rates", "volatility", "credit", "cross_asset"];
const CHAIN_ORDER = [
  "liquidity",
  "rates",
  "fed_corridor",
  "volatility",
  "credit",
  "positioning",
  "cross_asset",
];

type ScenarioSignal = NonNullable<MacroScenario["confirmations"]>[number];
type TradeMapEntry = NonNullable<MacroScenario["trade_map"]>[number];

export function MacroPage({ token }: { token: string }) {
  const query = useMacroQuery({ token });
  const data = query.data;
  const snapshot = data?.snapshot ?? null;
  const panels = data?.panels ?? {};
  const panelEntries = orderedPanels(panels);
  const chainEntries = orderedChain(data?.chain ?? {});
  const indicators = Object.entries(data?.indicators ?? {});
  const triggers = data?.triggers ?? [];
  const gaps = data?.data_gaps ?? [];
  const scenario = data?.scenario ?? {};
  const scorecard = data?.scorecard ?? {};

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
          <section className="macro-scoreboard" aria-label="macro panel scores">
            {panelEntries.map(([key, panel]) => (
              <MacroPanelCell key={key} panelKey={key} panel={panel} />
            ))}
          </section>

          <section className="macro-chain-section" aria-label="macro transmission chain">
            <div className="macro-section-head">
              <GitBranch aria-hidden />
              <h3>Transmission Chain</h3>
            </div>
            <div className="macro-chain-grid">
              {chainEntries.map(([key, node]) => (
                <ChainNodeCell key={key} nodeKey={key} node={node} />
              ))}
              {chainEntries.length === 0 ? (
                <span className="macro-muted">no chain nodes</span>
              ) : null}
            </div>
          </section>

          <section className="macro-scenario-section" aria-label="macro scenario path">
            <div className="macro-section-head">
              <Route aria-hidden />
              <h3>Scenario Path</h3>
            </div>
            <ScenarioPath scenario={scenario} scorecard={scorecard} />
          </section>

          <section
            className="macro-confirmation-section"
            aria-label="macro confirmations and contradictions"
          >
            <div className="macro-section-head">
              <ShieldCheck aria-hidden />
              <h3>Confirmations / Contradictions</h3>
            </div>
            <div className="macro-signal-columns">
              <SignalColumn
                emptyLabel="no confirmations"
                items={scenario.confirmations ?? []}
                label="confirm"
                tone="confirm"
              />
              <SignalColumn
                emptyLabel="no contradictions"
                items={scenario.contradictions ?? []}
                label="contradict"
                tone="contradict"
              />
            </div>
          </section>

          <section className="macro-trade-map-section" aria-label="macro trade map">
            <div className="macro-section-head">
              <Map aria-hidden />
              <h3>Trade Map</h3>
            </div>
            <TradeMapList entries={scenario.trade_map ?? []} />
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

function ChainNodeCell({ nodeKey, node }: { nodeKey: string; node: MacroChainNode }) {
  const regime = node.regime ?? "data_gap";
  const evidence = node.evidence ?? [];
  const dataGaps = node.data_gaps ?? [];
  return (
    <article className={clsx("macro-chain-node", regimeTone(regime))}>
      <div>
        <span>{nodeTitle(nodeKey)}</span>
        <b>{scoreLabel(node.score)}</b>
      </div>
      <strong>{regime}</strong>
      <small>{evidence[0] ?? dataGaps[0] ?? "awaiting chain evidence"}</small>
    </article>
  );
}

function ScenarioPath({
  scenario,
  scorecard,
}: {
  scenario: MacroScenario;
  scorecard: MacroScorecard;
}) {
  return (
    <div className="macro-scenario-body">
      <div className="macro-scenario-metrics">
        <MetricTile label="regime" value={scenario.current_regime ?? "scenario pending"} />
        <MetricTile label="confidence" value={percentLabel(scenario.confidence)} />
        <MetricTile label="window" value={scenario.time_window ?? "-"} />
        <MetricTile label="chain avg" value={scoreLabel(scorecard.chain_average)} />
        <MetricTile label="coverage" value={coverageLabel(scorecard)} />
      </div>
      <div className="macro-signal-columns">
        <SignalColumn
          emptyLabel="no watch triggers"
          items={scenario.watch_triggers ?? []}
          label="watch"
          tone="watch"
        />
        <SignalColumn
          emptyLabel="no invalidations"
          items={scenario.invalidations ?? []}
          label="invalidate"
          tone="contradict"
        />
      </div>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <span className="macro-metric-tile">
      <small>{label}</small>
      <b>{value}</b>
    </span>
  );
}

function SignalColumn({
  emptyLabel,
  items,
  label,
  tone,
}: {
  emptyLabel: string;
  items: ScenarioSignal[];
  label: string;
  tone: "confirm" | "contradict" | "watch";
}) {
  return (
    <div className="macro-signal-column">
      <span className="macro-column-label">{label}</span>
      <SignalList emptyLabel={emptyLabel} items={items} tone={tone} />
    </div>
  );
}

function SignalList({
  emptyLabel,
  items,
  tone,
}: {
  emptyLabel: string;
  items: ScenarioSignal[];
  tone: "confirm" | "contradict" | "watch";
}) {
  if (items.length === 0) {
    return <span className="macro-muted">{emptyLabel}</span>;
  }
  return (
    <div className="macro-signal-list">
      {items.map((item, index) => {
        const code = item.code || `signal_${index + 1}`;
        const detail = signalDetail(item);
        return (
          <article className={clsx("macro-signal-item", tone)} key={`${code}-${index}`}>
            <b>{code}</b>
            {detail ? <small>{detail}</small> : null}
          </article>
        );
      })}
    </div>
  );
}

function TradeMapList({ entries }: { entries: TradeMapEntry[] }) {
  if (entries.length === 0) {
    return <span className="macro-muted">no trade map</span>;
  }
  return (
    <div className="macro-trade-map-list">
      {entries.map((entry, index) => {
        const expression = entry.expression || `trade_map_${index + 1}`;
        return (
          <article className="macro-trade-map-item" key={`${expression}-${index}`}>
            <div>
              <b>{expression}</b>
              <span>{entry.time_window ?? "-"}</span>
            </div>
            <TokenLine label="confirms" tokens={entry.confirms_on ?? []} />
            <TokenLine label="invalidates" tokens={entry.invalidates_on ?? []} />
          </article>
        );
      })}
    </div>
  );
}

function TokenLine({ label, tokens }: { label: string; tokens: string[] }) {
  if (tokens.length === 0) {
    return null;
  }
  return (
    <div className="macro-token-line">
      <span>{label}</span>
      <div>
        {tokens.map((token) => (
          <small key={token}>{token}</small>
        ))}
      </div>
    </div>
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

function orderedChain(chain: Record<string, MacroChainNode>): Array<[string, MacroChainNode]> {
  const ordered: Array<[string, MacroChainNode]> = [];
  for (const key of CHAIN_ORDER) {
    if (chain[key]) {
      ordered.push([key, chain[key]]);
    }
  }
  const remaining = Object.entries(chain).filter(([key]) => !CHAIN_ORDER.includes(key));
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

function nodeTitle(key: string): string {
  const titles: Record<string, string> = {
    liquidity: "Liquidity",
    rates: "Rates",
    fed_corridor: "Fed Corridor",
    volatility: "Volatility",
    credit: "Credit",
    positioning: "Positioning",
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

function percentLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function coverageLabel(scorecard: MacroScorecard): string {
  if (scorecard.observed_series_count !== null && scorecard.observed_series_count !== undefined) {
    if (scorecard.required_series_count !== null && scorecard.required_series_count !== undefined) {
      return `${scorecard.observed_series_count}/${scorecard.required_series_count}`;
    }
    return String(scorecard.observed_series_count);
  }
  return percentLabel(scorecard.coverage_ratio);
}

function signalDetail(item: ScenarioSignal): string {
  if (item.description) {
    return item.description;
  }
  if (item.node || item.regime) {
    return [item.node, item.regime].filter(Boolean).join(" / ");
  }
  return item.evidence?.[0] ?? "";
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
