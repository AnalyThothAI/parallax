import type {
  MacroDecisionConsole,
  MacroDecisionConsoleItem,
} from "../../model/macroWorkbenchModel";
import { hasMacroDecisionConsole } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./macroWorkbench.css";

export function MacroDecisionConsolePanel({
  consoleModel,
}: {
  consoleModel: MacroDecisionConsole;
}) {
  if (!hasMacroDecisionConsole(consoleModel)) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="今日决策台"
      className="macro-workbench-decision-panel"
      meta={decisionMeta(consoleModel)}
      span="full"
      title="今日决策台"
    >
      <div className="macro-workbench-decision-grid">
        <DecisionSection items={consoleModel.topChanges} title="3 个最重要变化" />
        <PairedDecisionSection
          firstItems={consoleModel.confirmations}
          firstLabel="确认"
          secondItems={consoleModel.contradictions}
          secondLabel="背离"
          title="确认 / 背离"
        />
        {consoleModel.liquidityPressure ? (
          <LiquidityPressureSection item={consoleModel.liquidityPressure} />
        ) : null}
        {consoleModel.futureCatalysts.length > 0 ? (
          <FutureCatalystSection items={consoleModel.futureCatalysts} />
        ) : null}
        <TradeSection items={consoleModel.tradeMap} />
        {consoleModel.judgementReview ? (
          <JudgementReviewSection review={consoleModel.judgementReview} />
        ) : null}
        <ScenarioCasesSection items={consoleModel.scenarioCases} />
        {consoleModel.watchlistAlerts ? (
          <WatchlistAlertsSection alerts={consoleModel.watchlistAlerts} />
        ) : null}
        <DataCredibilitySection
          blockers={consoleModel.qualityBlockers}
          credibility={consoleModel.dataCredibility}
        />
      </div>
    </MacroPanel>
  );
}

function DecisionSection({ items, title }: { items: MacroDecisionConsoleItem[]; title: string }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section aria-label={title} className="macro-workbench-decision-section">
      <h4>{title}</h4>
      <ul className="macro-workbench-decision-list">
        {items.map((item) => (
          <li key={item.key}>
            <span>{item.meta}</span>
            <b>{item.label}</b>
            <small>{item.detail}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

function LiquidityPressureSection({
  item,
}: {
  item: NonNullable<MacroDecisionConsole["liquidityPressure"]>;
}) {
  return (
    <section aria-label="流动性压力" className="macro-workbench-decision-section">
      <h4>流动性压力</h4>
      <ul className="macro-workbench-decision-list">
        <li>
          <span>{item.meta}</span>
          <b>{item.label}</b>
          <small>{item.detail}</small>
          {item.drivers.map((driver) => (
            <small key={driver}>{driver}</small>
          ))}
          {item.implication ? <small>{item.implication}</small> : null}
          {item.invalidation ? <small>失效：{item.invalidation}</small> : null}
        </li>
      </ul>
    </section>
  );
}

function FutureCatalystSection({ items }: { items: MacroDecisionConsole["futureCatalysts"] }) {
  return (
    <section aria-label="未来 24/72h 催化剂" className="macro-workbench-decision-section">
      <h4>未来 24/72h 催化剂</h4>
      <ul className="macro-workbench-decision-list">
        {items.map((item) => (
          <li key={item.key}>
            <span>{item.meta}</span>
            <b>{item.label}</b>
            <small>{item.detail}</small>
            {item.sourceUrl ? (
              <a
                className="macro-workbench-event-source-link"
                href={item.sourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                来源
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function WatchlistAlertsSection({
  alerts,
}: {
  alerts: NonNullable<MacroDecisionConsole["watchlistAlerts"]>;
}) {
  return (
    <section aria-label={alerts.label} className="macro-workbench-decision-section">
      <h4>{alerts.label}</h4>
      <ul className="macro-workbench-decision-list">
        {alerts.assets.map((asset) => (
          <li key={`asset:${asset.key}`}>
            <span>资产</span>
            <b>{watchlistAssetLabel(asset)}</b>
          </li>
        ))}
        {alerts.rules.map((rule) => (
          <li key={`rule:${rule.key}`}>
            <span>{rule.meta}</span>
            <b>{rule.label}</b>
            <small>{rule.detail}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

function watchlistAssetLabel(
  asset: NonNullable<MacroDecisionConsole["watchlistAlerts"]>["assets"][number],
): string {
  return [asset.symbol, asset.label, asset.action].filter(Boolean).join(" · ");
}

function DataCredibilitySection({
  blockers,
  credibility,
}: {
  blockers: MacroDecisionConsole["qualityBlockers"];
  credibility: MacroDecisionConsole["dataCredibility"];
}) {
  if (!credibility) {
    return null;
  }

  const title = credibility.label;
  return (
    <section aria-label={title} className="macro-workbench-decision-section">
      <h4>{title}</h4>
      <ul className="macro-workbench-decision-list">
        {credibility.issueLabel ? (
          <li>
            <span>质量问题</span>
            <b>{credibility.issueLabel}</b>
            <small>核心指标来源、as-of 与质量状态</small>
          </li>
        ) : null}
        {credibility.rows.map((row) => (
          <li key={row.key}>
            <span>{[row.source, row.asOf].filter(Boolean).join(" · ")}</span>
            <b>{row.label}</b>
            <small>
              {[row.value, row.source, row.asOf, row.qualityLabel].filter(Boolean).join(" · ")}
            </small>
          </li>
        ))}
        {blockers.map((item) => (
          <li key={item.key}>
            <span>{item.meta}</span>
            <b>{item.label}</b>
            <small>{item.detail}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

function JudgementReviewSection({
  review,
}: {
  review: NonNullable<MacroDecisionConsole["judgementReview"]>;
}) {
  return (
    <section aria-label={review.label} className="macro-workbench-decision-section">
      <h4>{review.label}</h4>
      <ul className="macro-workbench-decision-list">
        {review.itemCountLabel ? (
          <li>
            <span>复盘条目</span>
            <b>{review.itemCountLabel}</b>
            <small>基于 Trade Map 持有期证据</small>
          </li>
        ) : null}
        {review.rows.map((item) => (
          <li key={item.key}>
            <span>{item.meta}</span>
            <b>{item.label}</b>
            <small>{item.detail}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ScenarioCasesSection({ items }: { items: MacroDecisionConsole["scenarioCases"] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section aria-label="未来 2 周情景" className="macro-workbench-decision-section">
      <h4>未来 2 周情景</h4>
      <ul className="macro-workbench-decision-list">
        {items.map((item) => (
          <li key={item.key}>
            {item.meta ? <span>{item.meta}</span> : null}
            <b>{item.label}</b>
            <small>{item.detail}</small>
            <small>{item.trade}</small>
            <small>{item.entry}</small>
            <small>{item.stop}</small>
            <small>{item.invalidation}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PairedDecisionSection({
  firstItems,
  firstLabel,
  secondItems,
  secondLabel,
  title,
}: {
  firstItems: MacroDecisionConsole["confirmations"];
  firstLabel: string;
  secondItems: MacroDecisionConsole["contradictions"];
  secondLabel: string;
  title: string;
}) {
  const rows = [
    ...firstItems.map((item) => ({ ...item, pairLabel: firstLabel })),
    ...secondItems.map((item) => ({ ...item, pairLabel: secondLabel })),
  ];

  if (rows.length === 0) {
    return null;
  }

  return (
    <section aria-label={title} className="macro-workbench-decision-section">
      <h4>{title}</h4>
      <ul className="macro-workbench-decision-list">
        {rows.map((item) => (
          <li key={`${item.pairLabel}:${item.key}`}>
            <span>{pairedMeta(item.pairLabel, item.meta)}</span>
            <b>{item.label}</b>
            <small>{item.detail}</small>
          </li>
        ))}
      </ul>
    </section>
  );
}

function pairedMeta(pairLabel: string, meta: string | null): string {
  return meta ? `${pairLabel} · ${meta}` : pairLabel;
}

function TradeSection({ items }: { items: MacroDecisionConsole["tradeMap"] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section aria-label="交易映射" className="macro-workbench-decision-section">
      <h4>交易映射</h4>
      <ul className="macro-workbench-decision-list">
        {items.map((item) => (
          <li key={item.key}>
            {item.window ? <span>{item.window}</span> : null}
            <b>{item.label}</b>
            {item.legs.length > 0 ? (
              <TradeDetailBlock lines={item.legs} title="当前表达" variant="legs" />
            ) : null}
            {item.history.length > 0 ? (
              <TradeDetailBlock lines={item.history} title="五资产雷达" variant="history" />
            ) : null}
            {item.portfolio.length > 0 ? (
              <TradeDetailBlock lines={item.portfolio} title="组合复盘" variant="portfolio" />
            ) : null}
            {item.trust.length > 0 ? (
              <TradeDetailBlock lines={item.trust} title="历史可信度" variant="trust" />
            ) : null}
            {item.holding.length > 0 ? (
              <TradeDetailBlock lines={item.holding} title="持有期复盘" variant="holding" />
            ) : null}
            {item.checklist.length > 0 ? (
              <TradeDetailBlock lines={item.checklist} title="行动清单" variant="checklist" />
            ) : null}
            {item.confirms ? <small>确认：{item.confirms}</small> : null}
            {item.invalidates ? <small>失效：{item.invalidates}</small> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TradeDetailBlock({
  lines,
  title,
  variant,
}: {
  lines: string[];
  title: string;
  variant: "checklist" | "history" | "holding" | "legs" | "portfolio" | "trust";
}) {
  return (
    <div className={`macro-workbench-trade-block macro-workbench-trade-${variant}`}>
      <h5>{title}</h5>
      <div className="macro-workbench-trade-block-lines">
        {lines.map((line) => (
          <small key={line}>{line}</small>
        ))}
      </div>
    </div>
  );
}

function decisionMeta(consoleModel: MacroDecisionConsole): string {
  const count =
    consoleModel.confirmations.length +
    consoleModel.contradictions.length +
    (consoleModel.dataCredibility ? consoleModel.dataCredibility.rows.length : 0) +
    consoleModel.futureCatalysts.length +
    (consoleModel.judgementReview ? consoleModel.judgementReview.rows.length : 0) +
    (consoleModel.liquidityPressure ? 1 : 0) +
    consoleModel.scenarioCases.length +
    consoleModel.topChanges.length +
    consoleModel.tradeMap.length +
    consoleModel.qualityBlockers.length +
    (consoleModel.watchlistAlerts
      ? consoleModel.watchlistAlerts.assets.length + consoleModel.watchlistAlerts.rules.length
      : 0);
  return `${count} 条`;
}
